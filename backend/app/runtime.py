from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from datetime import datetime, timezone

from app.config import Settings
from app.market_data.models import MarketDataMode, utcnow
from app.market_data.service import MarketDataService
from app.market_data.history import MarketPriceHistory
from app.market_data.perp_context import PerpContextService, PerpPositionContext, demo_perp_context
from app.references.service import ReferenceService
from app.strategy.models import StrategyConfig, StrategyState, ExecutionMode
from app.strategy.quote_engine import QuoteEngine
from app.strategy.fair_value import calculate_fair_value
from app.strategy.inventory import InventoryPolicy, InventoryState, build_inventory_state
from app.strategy.market_adaptation import MarketAdaptationPolicy
from app.strategy.perp_policy import PerpContextPolicy
from app.execution.paper import PaperExecutionAdapter
from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
from app.execution.order_manager import OrderManager
from app.execution.models import OrderRequest
from app.risk.models import RiskStatus
from app.risk.kill_switch import KillSwitch
from app.risk.limits import validate_quotes, validate_execution_authority
from app.risk.firewall import RiskFirewall, RiskFirewallConfig, RiskState, exposure_metrics
from app.risk.authorization import authorize, fingerprint
from app.agents import AgentConfig,AgentSupervisor,AgentTelemetryStore,build_agent_evidence,transform_quotes
from app.accounting import AccountingConfig, AccountingService
from app.accounting.pnl import to_pnl_drawdown
from app.accounting.vault import reserved_capital
from app.terminal import TerminalService

log = logging.getLogger(__name__)


class HyperAmmRuntime:
    def __init__(self, settings: Settings):
        mode = MarketDataMode(settings.market_data_mode.upper())
        self.settings = settings
        self.config = StrategyConfig(
            market=settings.market,
            market_data_mode=mode,
            execution_mode=ExecutionMode(settings.execution_mode.upper()),
        )
        self.strategy = StrategyState(config=self.config)
        self.market = MarketDataService(
            settings.market, mode, settings.market_stale_after_seconds, settings.demo_update_interval_seconds
        )
        self.paper = PaperExecutionAdapter()
        self.testnet = HyperliquidTestnetExecutionAdapter(
            enabled=settings.enable_hyperliquid_testnet_orders,
            private_key=settings.hyperliquid_private_key,
            account_address=settings.hyperliquid_account_address,
            base_url=settings.hyperliquid_testnet_url,
        )
        self.execution = self.paper if self.config.execution_mode == ExecutionMode.PAPER else self.testnet
        self.execution_lock = asyncio.Lock()
        self._strategy_wakeup = asyncio.Event()
        self.orders = OrderManager(self.execution, self.execution_lock, self._execution_authority)
        self.quote_engine = QuoteEngine()
        self.market_history = MarketPriceHistory(max_samples=1000)
        self.perp_context_service = PerpContextService(
            settings.market, self.config.perp_context_stale_after_seconds
        )
        self.reference_service = ReferenceService(
            settings, market=settings.market, mode=mode, wakeup=self._strategy_wakeup
        )
        self.risk = RiskStatus()
        self.risk_config = RiskFirewallConfig(enabled=settings.reference_firewall_enabled)
        self.firewall = RiskFirewall(self.risk_config)
        self.agent_config = AgentConfig()
        self.agent_telemetry = AgentTelemetryStore()
        self.agent_supervisor = AgentSupervisor(self.agent_config)
        self.accounting_config = AccountingConfig()
        self.accounting_service = AccountingService(settings.market, self.config.execution_mode.value, self.accounting_config)
        self.vault_snapshot = self.accounting_service.snapshot()
        self.kill = KillSwitch(self.risk, self.execution_lock)
        self.fair_value = None
        self.pool = None
        self.quotes = []
        self.strategy_quotes = []
        self.agent_quotes = []
        self.agent_evidence = None
        self.agent_decision = None
        self.last_actions = []
        self.references = None
        self.risk_decision = None
        self.authorization = None
        self.inventory: InventoryState | None = None
        self.inventory_decision = None
        self.market_adaptation_decision = None
        self.perp_context = None
        self.perp_reference_decision = None
        self.perp_position: PerpPositionContext | None = None
        self._expected_inventory_version: int | None = None
        self._expected_market_version: int | None = None
        self._expected_perp_version: int | None = None
        self._expected_reference_version: int | None = None
        self._expected_agent_version: int | None = None
        self._expected_agent_fingerprint: str | None = None
        self._expected_risk_version: int | None = None
        self._expected_accounting_version: int | None = None
        self._expected_accounting_fingerprint: str | None = None
        self._strategy_task = None
        self._venue_task = None
        self._closing = False
        self.terminal_service = TerminalService()
        self._terminal_task = None
        self._terminal_latest = None
        self._terminal_clients = set()
        self.testnet.authority = self._execution_authority
        self.paper.on_fill = self._on_paper_fill
        self.paper.orders.observer = self.agent_telemetry.observe_orders
        self.testnet._orders.observer = self.agent_telemetry.observe_orders
        self.market.add_listener(self._on_market)
        self.market.add_perp_listener(self._on_perp_context)

    def _on_paper_fill(self, fill):
        reference_price=None
        if self.references is not None:
            reference_price=self.references.consensus.consensus_price
        self.agent_telemetry.observe_fill(fill,reference_price)
        try:
            self.accounting_service.ingest_fill(fill)
        except Exception as exc:
            # Execution already happened; retain it and fail new authority closed.
            self.accounting_service.fail(exc)
        self.accounting_service.observe_execution_fills(self.paper.fills.all(), retired_count=self.paper.fills.retired_count,
                                                         duplicate_fills=self.paper.fills.duplicate_pending(self.accounting_service))
        self.paper.fills.acknowledge(fill, self.accounting_service, agent_consumed=True)
        self.vault_snapshot = self.accounting_service.snapshot()
        self._strategy_wakeup.set()

    def _paper_perp_position(self, inventory: InventoryState) -> PerpPositionContext:
        return PerpPositionContext(
            market=inventory.market,
            signed_position_base=inventory.position_base,
            updated_at=inventory.updated_at,
            stale=inventory.stale,
            version=inventory.version,
            source="PAPER",
        )

    def _paper_inventory(self) -> InventoryState:
        self._sync_paper_fills_locked()
        return build_inventory_state(
            market=self.config.market,
            position=self.accounting_service.position.position_base,
            target=self.config.target_inventory_base,
            soft_limit=self.config.soft_inventory_limit_base,
            source="PAPER",
            updated_at=self.paper.last_fill_at or utcnow(),
            stale=False,
            version=self.accounting_service.position.version,
        )

    async def _testnet_inventory_locked(self, *, refresh: bool) -> InventoryState:
        if refresh:
            await self.testnet.refresh_position(self.config.market)
        snapshot = self.testnet.position_snapshot(self.config.market)
        if snapshot is None:
            raise RuntimeError("authoritative TESTNET inventory is unavailable")
        position, updated_at, version, error = snapshot
        age = (datetime.now(timezone.utc) - updated_at).total_seconds()
        stale = age < 0 or age > self.config.inventory_stale_after_seconds
        if self.testnet.reconciliation_error:
            error = f"venue reconciliation unresolved: {self.testnet.reconciliation_error}"
        if self.testnet.has_unknown_exposure():
            error = "authoritative TESTNET inventory is uncertain while venue exposure is UNKNOWN"
        state = build_inventory_state(
            market=self.config.market,
            position=position,
            target=self.config.target_inventory_base,
            soft_limit=self.config.soft_inventory_limit_base,
            source="TESTNET",
            updated_at=updated_at,
            stale=stale,
            version=version,
            error=error,
        )
        if state.stale:
            raise RuntimeError("authoritative TESTNET inventory is stale")
        if state.error:
            raise RuntimeError(state.error)
        position_context = self.testnet.perp_position_snapshot(self.config.market)
        if position_context is None:
            raise RuntimeError("authoritative TESTNET perp position context is unavailable")
        if position_context.signed_position_base != state.position_base:
            raise RuntimeError("Phase 5 inventory and Phase 7 perp position disagree")
        self.perp_position = position_context
        return state

    async def _inventory_state_locked(self, *, refresh: bool = False) -> InventoryState:
        if self.config.execution_mode == ExecutionMode.PAPER:
            return self._paper_inventory()
        return await self._testnet_inventory_locked(refresh=refresh)

    def _validate_final_testnet(self, quotes, snapshot, inventory, perp, refs, existing, vault):
        """Check actual final economics without advancing firewall hysteresis.

        TESTNET has partial accounting: full-notional research reservation is
        bounded by authoritative account equity, without assuming leverage.
        Existing account margin is also reserved conservatively.
        """
        validate_quotes(quotes, snapshot, self.risk, final_venue=True)
        c=self.risk_config
        exp=exposure_metrics(quotes, inventory.position_base, refs.consensus.consensus_price or perp.mark_price,
                             max(c.max_projected_long_base,c.max_projected_short_base), existing)
        if (exp.projected_long_base > c.max_projected_long_base
                or exp.projected_short_base < -c.max_projected_short_base
                or exp.gross_quote_notional > c.max_gross_quote_notional
                or max(exp.projected_long_notional,exp.projected_short_notional) > c.max_projected_position_notional):
            raise ValueError("final venue-normalized exposure exceeds risk limit")
        if vault.stale or vault.error or vault.accounting_complete == "UNAVAILABLE":
            raise RuntimeError("final TESTNET accounting authority unavailable")
        equity=vault.equity_quote
        margin=vault.margin_used_quote
        if equity is None or margin is None or not equity.is_finite() or not margin.is_finite() or margin < 0:
            raise RuntimeError("final TESTNET capital evidence unavailable")
        required=reserved_capital(inventory.position_base, perp.mark_price, quotes, existing)+margin
        if required > max(Decimal("0"),equity)*self.accounting_config.max_capital_utilization:
            raise ValueError("final TESTNET capital reservation exceeds equity limit")
        return exp

    async def _execution_authority(self, request: OrderRequest | None = None):
        if self.config.execution_mode == ExecutionMode.PAPER:
            self.accounting_service.observe_execution_fills(self.paper.fills.all(), retired_count=self.paper.fills.retired_count,
                                                         duplicate_fills=self.paper.fills.duplicate_pending(self.accounting_service))
        current_market = await self.market.snapshot()
        market_fair = calculate_fair_value(current_market)
        self.market_history.add_snapshot(current_market)
        validate_execution_authority(
            risk=self.risk,
            execution_mode=self.config.execution_mode.value,
            strategy_running=self.strategy.running,
        )
        if self.config.execution_mode == ExecutionMode.TESTNET:
            self.testnet._require_enabled()

        inventory = await self._inventory_state_locked(refresh=False)
        if self._expected_inventory_version is not None and inventory.version != self._expected_inventory_version:
            raise RuntimeError("inventory changed after quote authorization; recompute before transmission")
        if self._expected_market_version is not None and self.market_history.version != self._expected_market_version:
            raise RuntimeError("market/adaptation state changed after quote authorization; recompute before transmission")

        current_perp = None
        if self.config.perp_context_enabled or self.risk_config.enabled:
            current_perp = self.perp_context_service.snapshot(market_fair)
            if self._expected_perp_version is not None and current_perp.version != self._expected_perp_version:
                raise RuntimeError("perp context changed after quote authorization; recompute before transmission")

        if self.authorization is None or not self.authorization.authorized:
            raise PermissionError("current Phase 8 FinalQuoteAuthorization is not authorized")
        if self.risk_decision is None or self.references is None:
            raise RuntimeError("Phase 8 risk evidence is unavailable")
        if current_perp is None:
            current_perp = self.perp_context_service.snapshot(market_fair)

        current_refs = self.reference_service.snapshot(
            current_market,
            current_perp,
            agreement_bps=self.risk_config.source_agreement_bps,
            outlier_bps=self.risk_config.source_outlier_bps,
        )
        if self._expected_reference_version is not None and current_refs.version != self._expected_reference_version:
            raise RuntimeError("reference evidence changed after quote authorization; recompute before transmission")
        if self.agent_decision is None:
            raise RuntimeError("Phase 9 agent authority is unavailable")
        if self._expected_agent_version is not None and (
            self.agent_supervisor.version != self._expected_agent_version
            or self.agent_decision.version != self._expected_agent_version
        ):
            raise RuntimeError("agent decision changed after quote authorization; recompute before transmission")
        if self._expected_agent_fingerprint is not None and (
            self.agent_supervisor.fingerprint != self._expected_agent_fingerprint
            or self.agent_decision.fingerprint != self._expected_agent_fingerprint
            or self.authorization.agent_fingerprint != self._expected_agent_fingerprint
        ):
            raise RuntimeError("agent fingerprint changed after quote authorization; recompute before transmission")
        if self.authorization.agent_version != self.agent_decision.version:
            raise RuntimeError("authorized agent version is stale")
        if self._expected_risk_version is not None and self.risk_decision.version != self._expected_risk_version:
            raise RuntimeError("risk decision changed after quote authorization; recompute before transmission")
        if fingerprint(self.quotes) != self.authorization.quote_fingerprint:
            raise RuntimeError("authorized quote ladder fingerprint mismatch")
        if request is not None and self.config.execution_mode == ExecutionMode.TESTNET:
            matches=[q for q in self.quotes if q.side == request.side and q.level_index == request.level_index]
            if (request.market != self.config.market or len(matches) != 1
                    or (request.price,request.size) != (matches[0].price,matches[0].size)):
                raise PermissionError("concrete request does not match exactly one authorized quote")
        if self.config.execution_mode == ExecutionMode.TESTNET:
            # Account value can change without the market position version changing.
            self.accounting_service.observe_testnet(self.perp_position, self.testnet.account_risk_snapshot(),
                                                   mark=current_perp.mark_price)
        vault = self.accounting_service.require_fresh()
        if self.accounting_service.config != self.accounting_config:
            raise RuntimeError("accounting configuration changed; internal context rebind required")
        if (vault.accounting_version != self._expected_accounting_version
                or vault.accounting_version != self.authorization.accounting_version
                or vault.accounting_fingerprint != self._expected_accounting_fingerprint
                or vault.accounting_fingerprint != self.authorization.accounting_fingerprint):
            raise RuntimeError("accounting changed after quote authorization; recompute before transmission")
        if self.config.execution_mode == ExecutionMode.PAPER:
            if current_perp.mark_price != vault.mark_price:
                raise RuntimeError("accounting mark changed after quote authorization")
            actual = reserved_capital(vault.position_base, vault.mark_price, self.quotes,
                                      await self.execution.get_open_orders())
            if vault.reserved_capital_quote is None or actual > vault.reserved_capital_quote:
                raise RuntimeError("accounting order reservation changed after authorization")
        else:
            self._validate_final_testnet(self.quotes, current_market, inventory, current_perp, current_refs,
                                         await self.execution.get_open_orders(), vault)

    async def _invalidate_locked(self, reason, health="DEGRADED"):
        self.quotes = []
        self.strategy_quotes = []
        self.agent_quotes = []
        self.agent_evidence = None
        self.agent_decision = None
        self.authorization = None
        self.fair_value = None
        self.pool = None
        self.inventory_decision = None
        self.market_adaptation_decision = None
        self.perp_reference_decision = None
        self._expected_market_version = None
        self._expected_perp_version = None
        self._expected_reference_version = None
        self._expected_agent_version = None
        self._expected_agent_fingerprint = None
        self._expected_risk_version = None
        self._expected_accounting_version = None
        self._expected_accounting_fingerprint = None
        self.last_actions = []
        self.strategy.last_error = reason
        self.strategy.quote_health = "HALTED" if self.risk.kill_switch_active else health
        try:
            await self.execution.cancel_all()
        except Exception as exc:
            self.strategy.quote_health = "HALTED"
            self.strategy.last_error = f"{reason}; cancellation unconfirmed: {exc}"
            self.risk.kill_switch_active = True
            self.risk.last_reason = self.strategy.last_error
            raise
        if (self.config.execution_mode == ExecutionMode.PAPER and self.accounting_service.config.enabled
                and not self.accounting_service.error and self.accounting_service.position.mark_price is not None):
            try:
                self.accounting_service.reserve(existing=await self.paper.get_open_orders())
                self.vault_snapshot = self.accounting_service.snapshot()
            except Exception as exc:
                # Cancellation already succeeded. Accounting failure must never be
                # reported as an unconfirmed venue cancellation.
                self.accounting_service.fail(exc)
                self.vault_snapshot = self.accounting_service.snapshot()

    async def _on_perp_context(self, context):
        async with self.execution_lock:
            try:
                if isinstance(context, Exception):
                    raise ValueError(str(context))
                changed = self.perp_context_service.accept(context)
                if changed:
                    self.perp_context = self.perp_context_service._context
                    self._strategy_wakeup.set()
                self._mark_accounting_locked(self.perp_context_service.snapshot(context.market_mid))
                if self.config.execution_mode == ExecutionMode.PAPER:
                    self.accounting_service.reserve(self.quotes, await self.paper.get_open_orders())
                self.vault_snapshot = self.accounting_service.snapshot()
            except Exception as exc:
                if self.config.perp_context_enabled or self.risk_config.enabled:
                    try:
                        await self._invalidate_locked(f"perp context update failed: {exc}")
                    except Exception:
                        log.exception("perp context invalidation failed")

    async def _on_market(self, snapshot):
        from app.strategy.fair_value import calculate_fair_value

        async with self.execution_lock:
            try:
                snapshot = await self.market.snapshot()
                calculate_fair_value(snapshot)
                self.market_history.add_snapshot(snapshot)
            except Exception as exc:
                await self._invalidate_locked(
                    str(exc), "HALTED" if self.risk.kill_switch_active else "DEGRADED"
                )
                return
            if self.config.execution_mode == ExecutionMode.PAPER:
                before = self.paper.inventory_version
                self.paper.update_market(snapshot)
                if self.paper.inventory_version != before:
                    self.inventory = self._paper_inventory()
                try:
                    context = self.perp_context_service.snapshot(calculate_fair_value(snapshot))
                    self._mark_accounting_locked(context)
                    self.accounting_service.reserve(self.quotes, await self.paper.get_open_orders())
                    self.vault_snapshot = self.accounting_service.snapshot()
                except Exception:
                    # Perp freshness and accounting authority are checked at refresh
                    # and before transmission; feed startup may precede perp startup.
                    pass
            self._strategy_wakeup.set()

    async def start_services(self):
        if self._terminal_task is not None and not self._terminal_task.done():
            raise RuntimeError("Runtime services already started")
        self._closing = False
        await self.market.start()
        await self.reference_service.start()
        self._venue_task = asyncio.create_task(self._venue_loop(), name="venue-reconciliation")
        self._terminal_task = asyncio.create_task(self._terminal_observer(), name="terminal-observation")

    async def _terminal_observer(self):
        while not self._closing:
            try:
                await self._publish_terminal_snapshot()
            except Exception:
                log.exception("terminal observation failed")
            await asyncio.sleep(1)

    async def _venue_loop(self):
        while not self._closing:
            try:
                await asyncio.wait_for(self.testnet.venue_changed.wait(), timeout=5)
            except TimeoutError:
                pass
            self.testnet.venue_changed.clear()
            if self._closing:
                break
            async with self.execution_lock:
                if self.execution is not self.testnet or not self.testnet.enabled:
                    continue
                try:
                    await self.testnet.reconcile_venue()
                    changed=self.agent_telemetry.observe_orders(await self.testnet.get_open_orders())
                    self.inventory = await self._testnet_inventory_locked(refresh=True)
                    if changed or self.inventory is not None:
                        self._strategy_wakeup.set()
                except Exception as exc:
                    try:
                        await self._invalidate_locked(f"venue reconciliation/inventory refresh failed: {exc}")
                    except Exception:
                        log.exception("venue exposure unresolved; execution halted")

    async def stop_services(self):
        if self._terminal_task:
            self._terminal_task.cancel()
            try:
                await self._terminal_task
            except asyncio.CancelledError:
                pass
            self._terminal_task = None
        await self.stop_strategy()
        await self.market.stop()
        await self.reference_service.stop()
        self._closing = True
        self.testnet.venue_changed.set()
        if self._venue_task:
            await self._venue_task
        await self.testnet.close()

    def _pnl_drawdown_locked(self, mark_price):
        return to_pnl_drawdown(self.accounting_service.snapshot())

    def _sync_paper_fills_locked(self):
        # No cursor can advance past failed evidence. Never clear a latched error.
        if self.accounting_service.config != self.accounting_config:
            self.accounting_service.fail("accounting configuration changed; internal context rebind required")
        if self.paper.fills.pending():
            self.accounting_service.reconcile_paper_fills(self.paper.fills.pending())
        for fill in self.paper.fills.pending():
            self.agent_telemetry.observe_fill(fill, None)
            self.paper.fills.acknowledge(fill, self.accounting_service, agent_consumed=True)
        self.paper.orders.prune()
        self.accounting_service.observe_execution_fills(self.paper.fills.all(), retired_count=self.paper.fills.retired_count,
                                                         duplicate_fills=self.paper.fills.duplicate_pending(self.accounting_service))

    def _mark_accounting_locked(self, context):
        if self.config.execution_mode == ExecutionMode.PAPER:
            self._sync_paper_fills_locked()
            self.accounting_service.observe_funding(context)
            self.accounting_service.mark(context.mark_price, observed_at=context.updated_at)
        else:
            self.accounting_service.observe_testnet(self.perp_position, self.testnet.account_risk_snapshot(),
                                                   mark=context.mark_price)
            if not self.accounting_service.error:
                self.testnet.acknowledge_accounting(self.perp_position, self.testnet.account_risk_snapshot())
        self.vault_snapshot = self.accounting_service.snapshot()

    async def refresh_once(self):
        async with self.execution_lock:
            if self.risk.kill_switch_active:
                await self._invalidate_locked(self.risk.last_reason or "kill switch is active", "HALTED")
                return
            try:
                snap = await self.market.snapshot()
                self.market_history.add_snapshot(snap)
                market_fair = calculate_fair_value(snap)
                venue_reconciled = False
                if self.config.execution_mode == ExecutionMode.TESTNET:
                    self.testnet._require_enabled()
                    await self.testnet.reconcile_venue()
                    venue_reconciled = True
                    inventory = await self._testnet_inventory_locked(refresh=True)
                else:
                    inventory = self._paper_inventory()
                    self.perp_position = self._paper_perp_position(inventory)

                if self.config.market_data_mode == MarketDataMode.DEMO and self.perp_context_service._context is None:
                    self.perp_context_service.accept(demo_perp_context(snap))
                perp_context = self.perp_context_service.snapshot(market_fair)
                self._mark_accounting_locked(perp_context)
                if self.config.execution_mode == ExecutionMode.PAPER:
                    if self.accounting_service.position.position_base != inventory.position_base:
                        raise RuntimeError("PAPER inventory and accounting position disagree")

                if self.config.perp_context_enabled:
                    fair, pool, proposed, inventory_decision, market_decision, perp_decision = (
                        self.quote_engine.generate_perp_market_adaptive(
                            self.config, snap, inventory, self.market_history, perp_context
                        )
                    )
                    self.perp_reference_decision = perp_decision
                else:
                    fair, pool, proposed, inventory_decision, market_decision = self.quote_engine.generate_market_adaptive(
                        self.config, snap, inventory, self.market_history
                    )
                    self.perp_reference_decision = None

                refs = self.reference_service.snapshot(
                    snap,
                    perp_context,
                    agreement_bps=self.risk_config.source_agreement_bps,
                    outlier_bps=self.risk_config.source_outlier_bps,
                )
                self.agent_telemetry.observe_orders(await self.execution.get_open_orders())
                agent_evidence = build_agent_evidence(
                    market_decision=market_decision,
                    inventory=inventory,
                    perp_context=perp_context,
                    refs=refs,
                    history=self.market_history,
                    momentum_window=self.agent_config.regime_momentum_window_samples,
                )
                agent_decision = self.agent_supervisor.evaluate(
                    evidence=agent_evidence,
                    telemetry=self.agent_telemetry,
                    history=self.market_history,
                    execution_mode=self.config.execution_mode.value,
                )
                agent_candidate = transform_quotes(
                    proposed,
                    agent_decision,
                    center=inventory_decision.reservation_price,
                    tick_size=self.config.tick_size,
                    size_precision=self.config.size_precision,
                )
                pnl = self._pnl_drawdown_locked(perp_context.mark_price)
                existing_orders = await self.execution.get_open_orders()
                self.vault_snapshot = (self.accounting_service.reservation_snapshot(agent_candidate, existing_orders)
                    if self.config.execution_mode == ExecutionMode.PAPER else self.accounting_service.snapshot())
                risk_decision = self.firewall.evaluate(
                    refs=refs,
                    quotes=agent_candidate,
                    current_position=inventory.position_base,
                    mark=perp_context.mark_price,
                    liquidation=self.perp_position.liquidation_price if self.perp_position else None,
                    pnl=pnl,
                    market_version=market_decision.version,
                    inventory_version=inventory.version,
                    perp_version=perp_context.version,
                    venue_uncertain=self.config.execution_mode == ExecutionMode.TESTNET and self.testnet.has_unknown_exposure(),
                    existing_orders=existing_orders,
                    capital=self.vault_snapshot,
                    max_capital_utilization=self.accounting_config.max_capital_utilization,
                )
                authorized = self.firewall.transform(
                    agent_candidate,
                    risk_decision,
                    center=inventory_decision.reservation_price,
                    tick_size=self.config.tick_size,
                    size_precision=self.config.size_precision,
                    base_order_size=self.config.base_order_size,
                )
                if self.config.execution_mode == ExecutionMode.TESTNET:
                    authorized = await self.testnet.normalize_quotes(self.config.market, authorized,
                                                                    center=inventory_decision.reservation_price)
                    final_exposure=self._validate_final_testnet(
                        authorized, snap, inventory, perp_context, refs, existing_orders,
                        self.accounting_service.require_fresh())
                    risk_decision=risk_decision.model_copy(update={"exposure":final_exposure,
                        "projected_long_base":final_exposure.projected_long_base,
                        "projected_short_base":final_exposure.projected_short_base})
                validate_quotes(authorized, snap, self.risk)
                if self.config.execution_mode == ExecutionMode.PAPER:
                    self.accounting_service.reserve(authorized, existing_orders)
                self.vault_snapshot = self.accounting_service.snapshot()
                authorization = authorize(authorized, refs, risk_decision, agent_decision, self.vault_snapshot)

                self.inventory = inventory
                self.inventory_decision = inventory_decision
                self.market_adaptation_decision = market_decision
                self.perp_context = perp_context
                self.references = refs
                self.agent_evidence = agent_evidence
                self.agent_decision = agent_decision
                self.agent_quotes = agent_candidate
                self.risk_decision = risk_decision
                self.authorization = authorization
                self.strategy_quotes = proposed
                self.fair_value, self.pool, self.quotes = fair, pool, authorized
                self._expected_inventory_version = inventory.version
                self._expected_market_version = market_decision.version
                self._expected_perp_version = perp_context.version
                self._expected_reference_version = refs.version
                self._expected_agent_version = agent_decision.version
                self._expected_agent_fingerprint = agent_decision.fingerprint
                self._expected_risk_version = risk_decision.version
                self._expected_accounting_version = self.vault_snapshot.accounting_version
                self._expected_accounting_fingerprint = self.vault_snapshot.accounting_fingerprint

                if self.strategy.running:
                    if authorized:
                        await self._execution_authority()
                    self.last_actions = await self.orders.reconcile_locked(
                        self.config.market,
                        authorized,
                        self.config.replace_tolerance_bps,
                        self.config.size_tolerance,
                        venue_reconciled=venue_reconciled,
                    )
                    self.agent_telemetry.observe_reconcile(self.last_actions,await self.execution.get_open_orders())
                    if authorized:
                        await self._execution_authority()
                    if self.config.execution_mode == ExecutionMode.PAPER:
                        self.accounting_service.reserve(authorized, await self.execution.get_open_orders())
                        self.vault_snapshot = self.accounting_service.snapshot()
                        if self.accounting_service.version != self._expected_accounting_version:
                            self._strategy_wakeup.set()
                    self.strategy.quote_health = "HALTED" if risk_decision.state == RiskState.HALT else "HEALTHY"
                else:
                    self.last_actions = []
                    self.strategy.quote_health = "NO_QUOTES"
                self.strategy.last_error = (
                    "; ".join(risk_decision.reasons) if risk_decision.state == RiskState.HALT else None
                )
            except Exception as exc:
                try:
                    self.inventory = await self._inventory_state_locked(refresh=False)
                except Exception:
                    pass
                await self._invalidate_locked(
                    str(exc), "HALTED" if self.risk.kill_switch_active else "DEGRADED"
                )

    async def _loop(self):
        while self.strategy.running:
            self._strategy_wakeup.clear()
            try:
                await self.refresh_once()
            except Exception:
                log.exception("quote cancellation failed; execution halted")
            deadline = asyncio.get_running_loop().time() + self.config.quote_refresh_interval_ms / 1000
            while self.strategy.running:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(self._strategy_wakeup.wait(), timeout=min(1.0, remaining))
                    self._strategy_wakeup.clear()
                    break
                except TimeoutError:
                    pass
                async with self.execution_lock:
                    try:
                        from app.strategy.fair_value import calculate_fair_value
                        current_market = await self.market.snapshot()
                        calculate_fair_value(current_market)
                        self.market_history.add_snapshot(current_market)
                        inventory = await self._inventory_state_locked(refresh=False)
                        perp_changed = False
                        if self.config.perp_context_enabled:
                            current_perp = self.perp_context_service.snapshot(calculate_fair_value(current_market))
                            perp_changed = (
                                self._expected_perp_version is not None
                                and current_perp.version != self._expected_perp_version
                            )
                        inventory_changed = (
                            self._expected_inventory_version is not None
                            and inventory.version != self._expected_inventory_version
                        )
                        market_changed = (
                            self._expected_market_version is not None
                            and self.market_history.version != self._expected_market_version
                        )
                        reference_changed = False
                        if self.risk_config.enabled and self._expected_reference_version is not None:
                            current_perp = self.perp_context_service.snapshot(calculate_fair_value(current_market))
                            current_refs = self.reference_service.snapshot(
                                current_market,
                                current_perp,
                                agreement_bps=self.risk_config.source_agreement_bps,
                                outlier_bps=self.risk_config.source_outlier_bps,
                            )
                            reference_changed = current_refs.version != self._expected_reference_version
                        if inventory_changed or market_changed or perp_changed or reference_changed:
                            self._strategy_wakeup.set()
                            break
                    except Exception as exc:
                        try:
                            await self._invalidate_locked(
                                str(exc), "HALTED" if self.risk.kill_switch_active else "DEGRADED"
                            )
                        except Exception:
                            log.exception("quote cancellation failed; execution halted")

    async def start_strategy(self):
        async with self.execution_lock:
            if self.risk.kill_switch_active:
                raise PermissionError("kill switch is active")
            if self.config.execution_mode == ExecutionMode.TESTNET:
                self.testnet._require_enabled()
                await self.testnet.reconcile_venue()
                self.inventory = await self._testnet_inventory_locked(refresh=True)
            else:
                self.inventory = self._paper_inventory()
                self.perp_position = self._paper_perp_position(self.inventory)
            if self.config.perp_context_enabled or self.risk_config.enabled:
                snap = await self.market.snapshot()
                if self.config.market_data_mode == MarketDataMode.DEMO and self.perp_context_service._context is None:
                    self.perp_context_service.accept(demo_perp_context(snap))
                self.perp_context = self.perp_context_service.snapshot(calculate_fair_value(snap))
            self.strategy.running = True
            if not self._strategy_task or self._strategy_task.done():
                self._strategy_task = asyncio.create_task(self._loop(), name="strategy")
            return self.strategy

    async def stop_strategy(self):
        self.strategy.running = False
        async with self.execution_lock:
            self.strategy.running = False
            if self._strategy_task:
                self._strategy_task.cancel()
                try:
                    await self._strategy_task
                except asyncio.CancelledError:
                    pass
                self._strategy_task = None
            await self._invalidate_locked("strategy stopped", "NO_QUOTES")
        return self.strategy

    async def activate_kill(self):
        self.strategy.running = False
        self.risk.kill_switch_active = True
        self.risk.last_reason = "manual kill switch"
        async with self.execution_lock:
            await self._invalidate_locked(self.risk.last_reason, "HALTED")
        return self.risk

    async def resume(self):
        async with self.execution_lock:
            await self.execution.cancel_all()
            self.kill.resume()
            self.strategy.running = False
            self.strategy.quote_health = "NO_QUOTES"
            self.strategy.last_error = None
        return self.risk

    async def update_config(self, new_config: StrategyConfig):
        old_market = None
        old_references = None
        async with self.execution_lock:
            mode_changed = (
                new_config.market_data_mode != self.config.market_data_mode
                or new_config.market != self.config.market
            )
            agent_context_changed = mode_changed or new_config.execution_mode != self.config.execution_mode
            await self._invalidate_locked("configuration changed", "NO_QUOTES")
            if mode_changed:
                old_market = self.market
                old_references = self.reference_service
                self.market = MarketDataService(
                    new_config.market,
                    new_config.market_data_mode,
                    self.settings.market_stale_after_seconds,
                    self.settings.demo_update_interval_seconds,
                )
                self.market.add_listener(self._on_market)
                self.market.add_perp_listener(self._on_perp_context)
            self.execution = self.paper if new_config.execution_mode == ExecutionMode.PAPER else self.testnet
            self.orders.execution = self.execution
            self.config = new_config
            self.strategy.config = new_config
            self._expected_inventory_version = None
            self._expected_market_version = None
            self._expected_perp_version = None
            self._expected_reference_version = None
            self._expected_agent_version = None
            self._expected_agent_fingerprint = None
            self._expected_risk_version = None
            self.inventory = None
            self.inventory_decision = None
            self.market_adaptation_decision = None
            self.perp_context = None
            self.perp_reference_decision = None
            self.perp_position = None
            self.references = None
            self.risk_decision = None
            self.authorization = None
            self.strategy_quotes = []
            self.agent_quotes = []
            self.agent_evidence = None
            self.agent_decision = None
            if agent_context_changed:
                self.agent_telemetry = AgentTelemetryStore()
                self.agent_supervisor = AgentSupervisor(self.agent_config)
                # Serialized, internal new research session. Old PAPER economics
                # must never seed TESTNET or a different market/session.
                self.paper = PaperExecutionAdapter()
                self.paper.on_fill = self._on_paper_fill
                self.paper.orders.observer = self.agent_telemetry.observe_orders
                self.testnet._orders.observer = self.agent_telemetry.observe_orders
                self.execution = self.paper if new_config.execution_mode == ExecutionMode.PAPER else self.testnet
                self.orders.execution = self.execution
                self.accounting_service = AccountingService(new_config.market, new_config.execution_mode.value,
                                                            self.accounting_config)
                self.vault_snapshot = self.accounting_service.snapshot()
                self._expected_accounting_version = None
                self._expected_accounting_fingerprint = None
            if mode_changed:
                self.market_history.clear()
                self.perp_context_service = PerpContextService(
                    new_config.market, new_config.perp_context_stale_after_seconds
                )
                self.reference_service = ReferenceService(
                    self.settings,
                    market=new_config.market,
                    mode=new_config.market_data_mode,
                    wakeup=self._strategy_wakeup,
                )
            else:
                self.perp_context_service.stale_after_seconds = new_config.perp_context_stale_after_seconds
        if old_market:
            await old_market.stop()
            if old_references:
                await old_references.stop()
            await self.market.start()
            await self.reference_service.start()
        if self.strategy.running:
            await self.refresh_once()
        return self.strategy

    def _inventory_payload(self, state: InventoryState, decision) -> dict:
        return {
            **state.model_dump(mode="json"),
            "reservation_price": str(decision.reservation_price) if decision else None,
            "price_skew_bps": str(decision.price_skew_bps) if decision else None,
            "inventory_ratio_effective": str(decision.inventory_ratio_effective) if decision else None,
            "bid_size_multiplier": str(decision.bid_size_multiplier) if decision else None,
            "ask_size_multiplier": str(decision.ask_size_multiplier) if decision else None,
            "hard_limit_state": decision.hard_limit_state.value if decision else None,
            "market_fair_value": str(decision.market_fair_value) if decision else None,
            "reference_price": str(decision.reference_price) if decision else None,
        }

    async def inventory_summary(self, *, refresh: bool = False):
        from app.strategy.fair_value import calculate_fair_value

        async with self.execution_lock:
            if self.config.execution_mode == ExecutionMode.TESTNET and refresh:
                self.testnet._require_enabled()
                await self.testnet.reconcile_venue()
            state = await self._inventory_state_locked(refresh=refresh)
            decision = None
            try:
                snap = await self.market.snapshot()
                fair = self.fair_value if self.fair_value is not None else calculate_fair_value(snap)
                reference = (
                    self.perp_reference_decision.final_reference_price
                    if self.perp_reference_decision is not None
                    else fair
                )
                decision = InventoryPolicy(self.config).decision(fair, state, reference)
            except ValueError:
                # Position observability remains available while market-derived strategy
                # metrics are temporarily unavailable. Inventory-source failures are
                # raised before this point and are never converted to zero/default state.
                pass
            self.inventory = state
            self.inventory_decision = decision
            return self._inventory_payload(state, decision)

    def _perp_payload(self) -> dict | None:
        if self.perp_context is None:
            return None
        data = self.perp_context.model_dump(mode="json")
        decision = self.perp_reference_decision
        data.update({
            "market_fair_value": str(decision.market_fair_value) if decision else str(self.perp_context.market_mid),
            "funding_score": str(decision.funding_score) if decision else None,
            "funding_shift_bps": str(decision.funding_shift_bps) if decision else None,
            "strategy_reference_price": str(decision.final_reference_price) if decision else None,
            "reference_shift_bps": str(decision.final_reference_shift_bps) if decision else None,
            "position": self.perp_position.model_dump(mode="json") if self.perp_position else None,
        })
        return data

    async def perp_context_summary(self):
        from app.strategy.fair_value import calculate_fair_value
        async with self.execution_lock:
            snap = await self.market.snapshot()
            market_fair = calculate_fair_value(snap)
            if self.config.market_data_mode == MarketDataMode.DEMO and self.perp_context_service._context is None:
                self.perp_context_service.accept(demo_perp_context(snap))
            context = self.perp_context_service.snapshot(market_fair)
            decision = PerpContextPolicy(self.config).decision(market_fair, context)
            inventory = await self._inventory_state_locked(
                refresh=self.config.execution_mode == ExecutionMode.TESTNET
            )
            self.perp_context = context
            self.perp_reference_decision = decision
            if self.config.execution_mode == ExecutionMode.PAPER:
                self.perp_position = self._paper_perp_position(inventory)
            return self._perp_payload()

    def _market_adaptation_payload(self, decision) -> dict | None:
        return decision.model_dump(mode="json") if decision is not None else None

    async def market_adaptation_summary(self):
        from app.strategy.fair_value import calculate_fair_value

        async with self.execution_lock:
            snapshot = await self.market.snapshot()
            calculate_fair_value(snapshot)
            self.market_history.add_snapshot(snapshot)
            decision = MarketAdaptationPolicy(self.config).decision(snapshot, self.market_history)
            self.market_adaptation_decision = decision
            return self._market_adaptation_payload(decision)

    async def references_summary(self):
        async with self.execution_lock:
            snap=await self.market.snapshot()
            fair=calculate_fair_value(snap)
            if self.config.market_data_mode==MarketDataMode.DEMO and self.perp_context_service._context is None:
                self.perp_context_service.accept(demo_perp_context(snap))
            perp=self.perp_context_service.snapshot(fair)
            refs=self.reference_service.snapshot(snap,perp,agreement_bps=self.risk_config.source_agreement_bps,outlier_bps=self.risk_config.source_outlier_bps)
            self.references=refs
            return refs.model_dump(mode="json")

    def agents_payload(self):
        return {
            "config":self.agent_config.model_dump(mode="json"),
            "evidence":self.agent_evidence.model_dump(mode="json") if self.agent_evidence else None,
            "regime":self.agent_decision.regime.model_dump(mode="json") if self.agent_decision else None,
            "toxic_flow":self.agent_decision.toxic_flow.model_dump(mode="json") if self.agent_decision else None,
            "execution_quality":self.agent_decision.execution_quality.model_dump(mode="json") if self.agent_decision else None,
            "supervisor":self.agent_decision.model_dump(mode="json") if self.agent_decision else None,
            "agent_version":self.agent_decision.version if self.agent_decision else self.agent_supervisor.version,
            "agent_fingerprint":self.agent_decision.fingerprint if self.agent_decision else self.agent_supervisor.fingerprint,
            "telemetry":self.agent_telemetry.summary(),
        }

    async def agents_summary(self):
        if self.agent_decision is None:
            await self.refresh_once()
        return self.agents_payload()

    def agent_events_summary(self):
        return self.agent_supervisor.event_payload()

    def risk_firewall_payload(self):
        return {
            "manual_kill_active":self.risk.kill_switch_active,
            "manual_kill_reason":self.risk.last_reason,
            "config":self.risk_config.model_dump(mode="json"),
            "state":self.risk_decision.state.value if self.risk_decision else self.firewall.state.value,
            "decision":self.risk_decision.model_dump(mode="json") if self.risk_decision else None,
        }

    async def risk_evidence_summary(self):
        if self.references is None or self.risk_decision is None:
            await self.refresh_once()
        return {
            "references":self.references.model_dump(mode="json") if self.references else None,
            "risk":self.risk_decision.model_dump(mode="json") if self.risk_decision else None,
        }

    def risk_events_summary(self):
        return [event.model_dump(mode="json") for event in self.firewall.events]

    def authorization_summary(self):
        return self.authorization.model_dump(mode="json") if self.authorization else {
            "authorized":False,
            "risk_state":self.firewall.state.value,
            "reasons":["no current FinalQuoteAuthorization"],
        }

    def accounting_payload(self):
        if self.config.execution_mode == ExecutionMode.PAPER:
            self.accounting_service.observe_execution_fills(self.paper.fills.all(), retired_count=self.paper.fills.retired_count,
                                                         duplicate_fills=self.paper.fills.duplicate_pending(self.accounting_service))
        vault = self.accounting_service.snapshot()
        return {
            "config": self.accounting_config.model_dump(mode="json"),
            "accounting_version": vault.accounting_version,
            "accounting_fingerprint": vault.accounting_fingerprint,
            "ledger_version": vault.ledger_version,
            "ledger_fingerprint": vault.ledger_fingerprint,
            "retention_policy": self.accounting_service.ledger.retention_policy,
            "execution_accounting": vault.execution_accounting.model_dump(mode="json"),
            "pnl": self.accounting_service.pnl().model_dump(mode="json"),
            "events": [e.model_dump(mode="json") for e in self.accounting_service.events(20)],
        }

    async def vault_summary(self):
        async with self.execution_lock:
            try:
                snap = await self.market.snapshot()
                fair = calculate_fair_value(snap)
                if self.config.market_data_mode == MarketDataMode.DEMO and self.perp_context_service._context is None:
                    self.perp_context_service.accept(demo_perp_context(snap))
                context = self.perp_context_service.snapshot(fair)
                if self.config.execution_mode == ExecutionMode.TESTNET:
                    self.perp_position = self.testnet.perp_position_snapshot(self.config.market)
                self._mark_accounting_locked(context)
                if self.config.execution_mode == ExecutionMode.PAPER:
                    self.accounting_service.reserve(self.quotes, await self.paper.get_open_orders())
            except Exception as exc:
                # Read-only observability retains prior evidence and reports error.
                # Market outages do not overwrite balances with defaults.
                self.vault_snapshot = self.accounting_service.snapshot()
                return self.vault_snapshot.model_copy(update={"stale": True, "error": str(exc),
                    "accounting_complete": "UNAVAILABLE"}).model_dump(mode="json")
            self.vault_snapshot = self.accounting_service.snapshot()
            return self.vault_snapshot.model_dump(mode="json")

    async def terminal_state(self):
        """Read the last published observation without observing domain state."""
        from copy import deepcopy
        return deepcopy(self._terminal_latest)

    def subscribe_terminal(self):
        if len(self._terminal_clients) >= 32:
            raise RuntimeError("Local terminal client limit reached")
        queue = asyncio.Queue(maxsize=1)
        self._terminal_clients.add(queue)
        if self._terminal_latest is not None:
            queue.put_nowait(self._terminal_wire)
        return queue

    def unsubscribe_terminal(self, queue):
        self._terminal_clients.discard(queue)

    async def _publish_terminal_snapshot(self):
        if self.config.execution_mode == ExecutionMode.PAPER:
            self.accounting_service.observe_execution_fills(self.paper.fills.all(), retired_count=self.paper.fills.retired_count,
                                                         duplicate_fills=self.paper.fills.duplicate_pending(self.accounting_service))
        snap = await self.market.snapshot()
        inventory = None
        if self.inventory is not None:
            inventory = self._inventory_payload(self.inventory, self.inventory_decision)
        data = {
            "market": snap.model_dump(mode="json"),
            "strategy": self.strategy.model_dump(mode="json"),
            "fair_value": str(self.fair_value) if self.fair_value is not None else None,
            "pool": self.pool.model_dump(mode="json") if self.pool else None,
            "quotes": [q.model_dump(mode="json") for q in self.quotes],
            "inventory": inventory,
            "market_adaptation": self._market_adaptation_payload(self.market_adaptation_decision),
            "perp_context": self._perp_payload(),
            "references": self.references.model_dump(mode="json") if self.references else None,
            "reference_consensus": self.references.consensus.model_dump(mode="json") if self.references else None,
            "agents": self.agents_payload(),
            "agent_events": self.agent_events_summary()[-20:],
            "agent_quotes": [q.model_dump(mode="json") for q in self.agent_quotes],
            "strategy_quotes": [q.model_dump(mode="json") for q in self.strategy_quotes],
            "risk_firewall": self.risk_firewall_payload(),
            "risk_authorization": self.authorization_summary(),
            "risk_events": self.risk_events_summary()[-20:],
            "projected_exposure": self.risk_decision.exposure.model_dump(mode="json") if self.risk_decision else None,
            "pnl_drawdown": self.risk_decision.pnl_drawdown.model_dump(mode="json") if self.risk_decision else None,
            "vault": self.accounting_service.snapshot().model_dump(mode="json"),
            "accounting": self.accounting_payload(),
            "risk": self.risk.model_dump(mode="json"),
            "orders": [o.model_dump(mode="json") for o in self.paper.recent_orders()]
            if self.config.execution_mode == ExecutionMode.PAPER
            else [o.model_dump(mode="json") for o in self.testnet.recent_orders()],
            "fills": [f.model_dump(mode="json") for f in self.paper.fills.recent()]
            if self.config.execution_mode == ExecutionMode.PAPER
            else [],
            "execution_totals": {"fill_count": self.paper.fills.version,
                                 "filled_notional": str(self.paper.fills.filled_notional)},
            "venue_reconciliation": {
                "last_reconciled_at": self.testnet.last_reconciled_at.isoformat()
                if self.testnet.last_reconciled_at
                else None,
                "error": self.testnet.reconciliation_error,
            },
            "reconciliation": [a.model_dump(mode="json") for a in self.last_actions],
        }
        snapshot = self.terminal_service.observe(data, diagnostics={
            "testnet_enabled": self.testnet.enabled,
            "reference_firewall_enabled": self.risk_config.enabled,
        }).model_dump(mode="json")

        import json
        self._terminal_wire = json.dumps(snapshot)
        self._terminal_latest = snapshot
        for queue in self._terminal_clients:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(self._terminal_wire)
        return snapshot
