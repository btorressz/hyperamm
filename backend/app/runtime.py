from __future__ import annotations

import asyncio
import logging
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
from app.risk.models import RiskStatus
from app.risk.kill_switch import KillSwitch
from app.risk.limits import validate_quotes, validate_execution_authority
from app.risk.firewall import PnlDrawdown, RiskFirewall, RiskFirewallConfig, RiskState, paper_pnl
from app.risk.authorization import authorize, fingerprint

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
        self.kill = KillSwitch(self.risk, self.execution_lock)
        self.fair_value = None
        self.pool = None
        self.quotes = []
        self.strategy_quotes = []
        self.last_actions = []
        self.references = None
        self.risk_decision = None
        self.authorization = None
        self._session_start_equity = None
        self._peak_equity = None
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
        self._expected_risk_version: int | None = None
        self._strategy_task = None
        self._venue_task = None
        self._closing = False
        self.testnet.authority = self._execution_authority
        self.paper.on_fill = lambda _fill: self._strategy_wakeup.set()
        self.market.add_listener(self._on_market)
        self.market.add_perp_listener(self._on_perp_context)

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
        return build_inventory_state(
            market=self.config.market,
            position=self.paper.position_base(self.config.market),
            target=self.config.target_inventory_base,
            soft_limit=self.config.soft_inventory_limit_base,
            source="PAPER",
            updated_at=self.paper.last_fill_at or utcnow(),
            stale=False,
            version=self.paper.inventory_version,
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

    async def _execution_authority(self):
        current_market = await self.market.snapshot()
        market_fair = calculate_fair_value(current_market)
        self.market_history.add_snapshot(current_market)
        validate_execution_authority(
            risk=self.risk,
            execution_mode=self.config.execution_mode.value,
            strategy_running=self.strategy.running,
        )
        if self.authorization is None or not self.authorization.authorized:
            raise PermissionError("current Phase 8 FinalQuoteAuthorization is not authorized")
        if self.risk_decision is None or self.references is None:
            raise RuntimeError("Phase 8 risk evidence is unavailable")
        if self.config.execution_mode == ExecutionMode.TESTNET:
            self.testnet._require_enabled()
        inventory = await self._inventory_state_locked(refresh=False)
        current_perp = self.perp_context_service.snapshot(market_fair)
        current_refs = self.reference_service.snapshot(
            current_market,
            current_perp,
            agreement_bps=self.risk_config.source_agreement_bps,
            outlier_bps=self.risk_config.source_outlier_bps,
        )
        if self._expected_perp_version is not None and current_perp.version != self._expected_perp_version:
            raise RuntimeError("perp context changed after quote authorization; recompute before transmission")
        if self._expected_inventory_version is not None and inventory.version != self._expected_inventory_version:
            raise RuntimeError("inventory changed after quote authorization; recompute before transmission")
        if self._expected_market_version is not None and self.market_history.version != self._expected_market_version:
            raise RuntimeError("market/adaptation state changed after quote authorization; recompute before transmission")
        if self._expected_reference_version is not None and current_refs.version != self._expected_reference_version:
            raise RuntimeError("reference evidence changed after quote authorization; recompute before transmission")
        if self._expected_risk_version is not None and self.risk_decision.version != self._expected_risk_version:
            raise RuntimeError("risk decision changed after quote authorization; recompute before transmission")
        if fingerprint(self.quotes) != self.authorization.quote_fingerprint:
            raise RuntimeError("authorized quote ladder fingerprint mismatch")

    async def _invalidate_locked(self, reason, health="DEGRADED"):
        self.quotes = []
        self.strategy_quotes = []
        self.authorization = None
        self.fair_value = None
        self.pool = None
        self.inventory_decision = None
        self.market_adaptation_decision = None
        self.perp_reference_decision = None
        self._expected_market_version = None
        self._expected_perp_version = None
        self._expected_reference_version = None
        self._expected_risk_version = None
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

    async def _on_perp_context(self, context):
        async with self.execution_lock:
            try:
                if isinstance(context, Exception):
                    raise ValueError(str(context))
                changed = self.perp_context_service.accept(context)
                if changed:
                    self.perp_context = self.perp_context_service._context
                    self._strategy_wakeup.set()
            except Exception as exc:
                if self.config.perp_context_enabled:
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
            self._strategy_wakeup.set()

    async def start_services(self):
        self._closing = False
        await self.market.start()
        await self.reference_service.start()
        self._venue_task = asyncio.create_task(self._venue_loop(), name="venue-reconciliation")

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
                    self.inventory = await self._testnet_inventory_locked(refresh=True)
                    self._strategy_wakeup.set()
                except Exception as exc:
                    try:
                        await self._invalidate_locked(f"venue reconciliation/inventory refresh failed: {exc}")
                    except Exception:
                        log.exception("venue exposure unresolved; execution halted")

    async def stop_services(self):
        await self.stop_strategy()
        await self.market.stop()
        await self.reference_service.stop()
        self._closing = True
        self.testnet.venue_changed.set()
        if self._venue_task:
            await self._venue_task
        await self.testnet.close()

    def _pnl_drawdown_locked(self, mark_price):
        if self.config.execution_mode == ExecutionMode.PAPER:
            return paper_pnl(self.paper.fills.all(), self.config.market, mark_price)
        account = self.testnet.account_risk_snapshot()
        current_equity = account.get("account_value") if account else None
        if current_equity is not None:
            if self._session_start_equity is None:
                self._session_start_equity = current_equity
            self._peak_equity = current_equity if self._peak_equity is None else max(self._peak_equity, current_equity)
            session_pnl = current_equity - self._session_start_equity
            drawdown = (
                (self._peak_equity - current_equity) / self._peak_equity
                if self._peak_equity is not None and self._peak_equity > 0
                else None
            )
        else:
            session_pnl = None
            drawdown = None
        return PnlDrawdown(
            realized_pnl=None,
            unrealized_pnl=self.perp_position.unrealized_pnl if self.perp_position else None,
            session_pnl=session_pnl,
            current_equity=current_equity,
            peak_equity=self._peak_equity,
            drawdown_pct=drawdown,
            source="TESTNET AUTHORITATIVE USER STATE",
            simulated=False,
        )

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
                pnl = self._pnl_drawdown_locked(perp_context.mark_price)
                existing_orders = await self.execution.get_open_orders()
                risk_decision = self.firewall.evaluate(
                    refs=refs,
                    quotes=proposed,
                    current_position=inventory.position_base,
                    mark=perp_context.mark_price,
                    liquidation=self.perp_position.liquidation_price if self.perp_position else None,
                    pnl=pnl,
                    market_version=market_decision.version,
                    inventory_version=inventory.version,
                    perp_version=perp_context.version,
                    venue_uncertain=self.config.execution_mode == ExecutionMode.TESTNET and self.testnet.has_unknown_exposure(),
                    existing_orders=existing_orders,
                )
                authorized = self.firewall.transform(
                    proposed,
                    risk_decision,
                    center=inventory_decision.reservation_price,
                    tick_size=self.config.tick_size,
                    size_precision=self.config.size_precision,
                    base_order_size=self.config.base_order_size,
                )
                validate_quotes(authorized, snap, self.risk)
                authorization = authorize(authorized, refs, risk_decision)

                self.inventory = inventory
                self.inventory_decision = inventory_decision
                self.market_adaptation_decision = market_decision
                self.perp_context = perp_context
                self.references = refs
                self.risk_decision = risk_decision
                self.authorization = authorization
                self.strategy_quotes = proposed
                self.fair_value, self.pool, self.quotes = fair, pool, authorized
                self._expected_inventory_version = inventory.version
                self._expected_market_version = market_decision.version
                self._expected_perp_version = perp_context.version
                self._expected_reference_version = refs.version
                self._expected_risk_version = risk_decision.version

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
                    if authorized:
                        await self._execution_authority()
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
                        if inventory_changed or market_changed or perp_changed:
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
            if self.config.perp_context_enabled:
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

    async def terminal_state(self):
        snap = await self.market.snapshot()
        inventory = None
        if self.inventory is not None:
            inventory = self._inventory_payload(self.inventory, self.inventory_decision)
        return {
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
            "risk_firewall": self.risk_firewall_payload(),
            "risk_authorization": self.authorization_summary(),
            "risk_events": self.risk_events_summary()[-20:],
            "projected_exposure": self.risk_decision.exposure.model_dump(mode="json") if self.risk_decision else None,
            "pnl_drawdown": self.risk_decision.pnl_drawdown.model_dump(mode="json") if self.risk_decision else None,
            "risk": self.risk.model_dump(mode="json"),
            "orders": [o.model_dump(mode="json") for o in self.paper.all_orders()]
            if self.config.execution_mode == ExecutionMode.PAPER
            else [o.model_dump(mode="json") for o in self.testnet.all_orders()],
            "fills": [f.model_dump(mode="json") for f in self.paper.fills.all()]
            if self.config.execution_mode == ExecutionMode.PAPER
            else [],
            "venue_reconciliation": {
                "last_reconciled_at": self.testnet.last_reconciled_at.isoformat()
                if self.testnet.last_reconciled_at
                else None,
                "error": self.testnet.reconciliation_error,
            },
            "reconciliation": [a.model_dump(mode="json") for a in self.last_actions],
        }
