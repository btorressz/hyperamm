from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.config import Settings
from app.market_data.models import MarketDataMode, utcnow
from app.market_data.service import MarketDataService
from app.strategy.models import StrategyConfig, StrategyState, ExecutionMode
from app.strategy.quote_engine import QuoteEngine
from app.strategy.inventory import InventoryPolicy, InventoryState, build_inventory_state
from app.execution.paper import PaperExecutionAdapter
from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
from app.execution.order_manager import OrderManager
from app.risk.models import RiskStatus
from app.risk.kill_switch import KillSwitch
from app.risk.limits import validate_quotes, validate_execution_authority

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
        self.orders = OrderManager(self.execution, self.execution_lock, self._execution_authority)
        self.quote_engine = QuoteEngine()
        self.risk = RiskStatus()
        self.kill = KillSwitch(self.risk, self.execution_lock)
        self.fair_value = None
        self.pool = None
        self.quotes = []
        self.last_actions = []
        self.inventory: InventoryState | None = None
        self.inventory_decision = None
        self._expected_inventory_version: int | None = None
        self._strategy_task = None
        self._venue_task = None
        self._closing = False
        self._strategy_wakeup = asyncio.Event()
        self.testnet.authority = self._execution_authority
        self.paper.on_fill = lambda _fill: self._strategy_wakeup.set()
        self.market.add_listener(self._on_market)

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
        return state

    async def _inventory_state_locked(self, *, refresh: bool = False) -> InventoryState:
        if self.config.execution_mode == ExecutionMode.PAPER:
            return self._paper_inventory()
        return await self._testnet_inventory_locked(refresh=refresh)

    async def _execution_authority(self):
        from app.strategy.fair_value import calculate_fair_value

        calculate_fair_value(await self.market.snapshot())
        validate_execution_authority(
            risk=self.risk,
            execution_mode=self.config.execution_mode.value,
            strategy_running=self.strategy.running,
        )
        if self.config.execution_mode == ExecutionMode.TESTNET:
            self.testnet._require_enabled()
        inventory = await self._inventory_state_locked(refresh=False)
        if self._expected_inventory_version is not None and inventory.version != self._expected_inventory_version:
            raise RuntimeError("inventory changed after quote generation; recompute before transmission")

    async def _invalidate_locked(self, reason, health="DEGRADED"):
        self.quotes = []
        self.fair_value = None
        self.pool = None
        self.inventory_decision = None
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

    async def _on_market(self, snapshot):
        from app.strategy.fair_value import calculate_fair_value

        async with self.execution_lock:
            try:
                snapshot = await self.market.snapshot()
                calculate_fair_value(snapshot)
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
        self._closing = True
        self.testnet.venue_changed.set()
        if self._venue_task:
            await self._venue_task
        await self.testnet.close()

    async def refresh_once(self):
        async with self.execution_lock:
            if self.risk.kill_switch_active:
                await self._invalidate_locked(self.risk.last_reason or "kill switch is active", "HALTED")
                return
            try:
                snap = await self.market.snapshot()
                venue_reconciled = False
                if self.config.execution_mode == ExecutionMode.TESTNET:
                    self.testnet._require_enabled()
                    await self.testnet.reconcile_venue()
                    venue_reconciled = True
                    inventory = await self._testnet_inventory_locked(refresh=True)
                else:
                    inventory = self._paper_inventory()
                fair, pool, quotes, decision = self.quote_engine.generate_inventory_aware(
                    self.config, snap, inventory
                )
                validate_quotes(quotes, snap, self.risk)
                self.inventory = inventory
                self.inventory_decision = decision
                self._expected_inventory_version = inventory.version
                if self.strategy.running:
                    await self._execution_authority()
                    self.last_actions = await self.orders.reconcile_locked(
                        self.config.market,
                        quotes,
                        self.config.replace_tolerance_bps,
                        self.config.size_tolerance,
                        venue_reconciled=venue_reconciled,
                    )
                    await self._execution_authority()
                    self.strategy.quote_health = "HEALTHY"
                else:
                    self.last_actions = []
                    self.strategy.quote_health = "NO_QUOTES"
                self.fair_value, self.pool, self.quotes = fair, pool, quotes
                self.strategy.last_error = None
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
                        calculate_fair_value(await self.market.snapshot())
                        inventory = await self._inventory_state_locked(refresh=False)
                        if self._expected_inventory_version is not None and inventory.version != self._expected_inventory_version:
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
        async with self.execution_lock:
            mode_changed = (
                new_config.market_data_mode != self.config.market_data_mode
                or new_config.market != self.config.market
            )
            await self._invalidate_locked("configuration changed", "NO_QUOTES")
            if mode_changed:
                old_market = self.market
                self.market = MarketDataService(
                    new_config.market,
                    new_config.market_data_mode,
                    self.settings.market_stale_after_seconds,
                    self.settings.demo_update_interval_seconds,
                )
                self.market.add_listener(self._on_market)
            self.execution = self.paper if new_config.execution_mode == ExecutionMode.PAPER else self.testnet
            self.orders.execution = self.execution
            self.config = new_config
            self.strategy.config = new_config
            self._expected_inventory_version = None
            self.inventory = None
            self.inventory_decision = None
        if old_market:
            await old_market.stop()
            await self.market.start()
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
        }

    async def inventory_summary(self, *, refresh: bool = False):
        from app.strategy.fair_value import calculate_fair_value

        async with self.execution_lock:
            if self.config.execution_mode == ExecutionMode.TESTNET and refresh:
                self.testnet._require_enabled()
                await self.testnet.reconcile_venue()
            state = await self._inventory_state_locked(refresh=refresh)
            snap = await self.market.snapshot()
            fair = self.fair_value if self.fair_value is not None else calculate_fair_value(snap)
            decision = InventoryPolicy(self.config).decision(fair, state)
            self.inventory = state
            self.inventory_decision = decision
            return self._inventory_payload(state, decision)

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
