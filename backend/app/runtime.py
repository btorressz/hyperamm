from __future__ import annotations

import asyncio
import logging
from app.config import Settings
from app.market_data.models import MarketDataMode
from app.market_data.service import MarketDataService
from app.strategy.models import StrategyConfig, StrategyState, ExecutionMode
from app.strategy.quote_engine import QuoteEngine
from app.execution.paper import PaperExecutionAdapter
from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
from app.execution.order_manager import OrderManager
from app.risk.models import RiskStatus
from app.risk.kill_switch import KillSwitch
from app.risk.limits import validate_quotes, validate_execution_authority

log=logging.getLogger(__name__)


class HyperAmmRuntime:
    def __init__(self, settings: Settings):
        mode=MarketDataMode(settings.market_data_mode.upper())
        self.settings=settings
        self.config=StrategyConfig(market=settings.market, market_data_mode=mode, execution_mode=ExecutionMode(settings.execution_mode.upper()))
        self.strategy=StrategyState(config=self.config)
        self.market=MarketDataService(settings.market,mode,settings.market_stale_after_seconds,settings.demo_update_interval_seconds)
        self.paper=PaperExecutionAdapter()
        self.testnet=HyperliquidTestnetExecutionAdapter(enabled=settings.enable_hyperliquid_testnet_orders,private_key=settings.hyperliquid_private_key,account_address=settings.hyperliquid_account_address,base_url=settings.hyperliquid_testnet_url)
        self.execution=self.paper if self.config.execution_mode==ExecutionMode.PAPER else self.testnet
        self.execution_lock=asyncio.Lock()
        self.orders=OrderManager(self.execution,self.execution_lock,self._execution_authority)
        self.quote_engine=QuoteEngine()
        self.risk=RiskStatus()
        self.kill=KillSwitch(self.risk,self.execution_lock)
        self.fair_value=None; self.pool=None; self.quotes=[]; self.last_actions=[]
        self._strategy_task=None
        self._venue_task=None
        self._closing=False
        self.testnet.authority=self._execution_authority
        self.market.add_listener(self._on_market)

    async def _execution_authority(self):
        from app.strategy.fair_value import calculate_fair_value
        calculate_fair_value(await self.market.snapshot())
        validate_execution_authority(risk=self.risk,execution_mode=self.config.execution_mode.value,
                                     strategy_running=self.strategy.running)
        if self.config.execution_mode==ExecutionMode.TESTNET:
            self.testnet._require_enabled()

    async def _invalidate_locked(self, reason, health="DEGRADED"):
        self.quotes=[]; self.fair_value=None; self.pool=None; self.last_actions=[]
        self.strategy.last_error=reason
        self.strategy.quote_health="HALTED" if self.risk.kill_switch_active else health
        try:
            await self.execution.cancel_all()
        except Exception as exc:
            self.strategy.quote_health="HALTED"
            self.strategy.last_error=f"{reason}; cancellation unconfirmed: {exc}"
            # Unknown venue exposure must require explicit operator recovery.
            self.risk.kill_switch_active=True
            self.risk.last_reason=self.strategy.last_error
            raise

    async def _on_market(self,snapshot):
        from app.strategy.fair_value import calculate_fair_value
        async with self.execution_lock:
            try:
                snapshot=await self.market.snapshot()
                calculate_fair_value(snapshot)
            except Exception as exc:
                await self._invalidate_locked(str(exc),"HALTED" if self.risk.kill_switch_active else "DEGRADED")
                return
            if self.config.execution_mode==ExecutionMode.PAPER:
                self.paper.update_market(snapshot)

    async def start_services(self):
        self._closing=False
        await self.market.start()
        self._venue_task=asyncio.create_task(self._venue_loop(),name="venue-reconciliation")

    async def _venue_loop(self):
        while not self._closing:
            try:
                await asyncio.wait_for(self.testnet.venue_changed.wait(),timeout=5)
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
                except Exception as exc:
                    try:
                        await self._invalidate_locked(f"venue reconciliation failed: {exc}")
                    except Exception:
                        log.exception("venue exposure unresolved; execution halted")
    async def stop_services(self):
        await self.stop_strategy(); await self.market.stop()
        self._closing=True
        self.testnet.venue_changed.set()
        if self._venue_task:
            await self._venue_task
        await self.testnet.close()

    async def refresh_once(self):
        async with self.execution_lock:
            if self.risk.kill_switch_active:
                await self._invalidate_locked(self.risk.last_reason or "kill switch is active","HALTED")
                return
            try:
                snap=await self.market.snapshot()
                fair,pool,quotes=self.quote_engine.generate(self.config,snap)
                validate_quotes(quotes,snap,self.risk)
                if self.strategy.running:
                    await self._execution_authority()
                    self.last_actions=await self.orders.reconcile_locked(self.config.market,quotes,self.config.replace_tolerance_bps,self.config.size_tolerance)
                    await self._execution_authority()
                    self.strategy.quote_health="HEALTHY"
                else:
                    self.last_actions=[]
                    self.strategy.quote_health="NO_QUOTES"
                self.fair_value,self.pool,self.quotes=fair,pool,quotes
                self.strategy.last_error=None
            except Exception as exc:
                await self._invalidate_locked(str(exc),"HALTED" if self.risk.kill_switch_active else "DEGRADED")

    async def _loop(self):
        while self.strategy.running:
            try:
                await self.refresh_once()
            except Exception:
                log.exception("quote cancellation failed; execution halted")
            # Keep the safety cadence bounded even with a 60-second quote interval.
            deadline=asyncio.get_running_loop().time()+self.config.quote_refresh_interval_ms/1000
            while self.strategy.running:
                remaining=deadline-asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(1.0,remaining))
                async with self.execution_lock:
                    try:
                        from app.strategy.fair_value import calculate_fair_value
                        calculate_fair_value(await self.market.snapshot())
                    except Exception as exc:
                        try:
                            await self._invalidate_locked(str(exc),"HALTED" if self.risk.kill_switch_active else "DEGRADED")
                        except Exception:
                            log.exception("quote cancellation failed; execution halted")

    async def start_strategy(self):
        async with self.execution_lock:
            if self.risk.kill_switch_active: raise PermissionError("kill switch is active")
            if self.config.execution_mode==ExecutionMode.TESTNET:
                self.testnet._require_enabled()
            self.strategy.running=True
            if not self._strategy_task or self._strategy_task.done():
                self._strategy_task=asyncio.create_task(self._loop(),name="strategy")
            return self.strategy

    async def stop_strategy(self):
        self.strategy.running=False
        async with self.execution_lock:
            self.strategy.running=False
            # The lock proves the strategy task is not inside a transmission.
            # Finish task teardown before a concurrent start can acquire it.
            if self._strategy_task:
                self._strategy_task.cancel()
                try: await self._strategy_task
                except asyncio.CancelledError: pass
                self._strategy_task=None
            await self._invalidate_locked("strategy stopped","NO_QUOTES")
        return self.strategy

    async def activate_kill(self):
        self.strategy.running=False
        # Resolve the adapter only after the lock, so a config switch cannot leave
        # the new adapter outside the cancellation barrier.
        self.risk.kill_switch_active=True
        self.risk.last_reason="manual kill switch"
        async with self.execution_lock:
            await self._invalidate_locked(self.risk.last_reason,"HALTED")
        return self.risk

    async def resume(self):
        async with self.execution_lock:
            # Verify cancellation before removing a latch caused by a venue error.
            await self.execution.cancel_all()
            self.kill.resume()
            self.strategy.running=False
            self.strategy.quote_health="NO_QUOTES"
            self.strategy.last_error=None
        return self.risk

    async def update_config(self,new_config: StrategyConfig):
        old_market=None
        async with self.execution_lock:
            mode_changed = new_config.market_data_mode != self.config.market_data_mode or new_config.market != self.config.market
            await self._invalidate_locked("configuration changed","NO_QUOTES")
            if mode_changed:
                old_market=self.market
                self.market=MarketDataService(new_config.market,new_config.market_data_mode,self.settings.market_stale_after_seconds,self.settings.demo_update_interval_seconds)
                self.market.add_listener(self._on_market)
            self.execution=self.paper if new_config.execution_mode==ExecutionMode.PAPER else self.testnet
            self.orders.execution=self.execution
            self.config=new_config; self.strategy.config=new_config
        if old_market:
            await old_market.stop()
            await self.market.start()
        if self.strategy.running: await self.refresh_once()
        return self.strategy

    async def terminal_state(self):
        snap=await self.market.snapshot()
        return {
            "market":snap.model_dump(mode="json"),
            "strategy":self.strategy.model_dump(mode="json"),
            "fair_value":str(self.fair_value) if self.fair_value is not None else None,
            "pool":self.pool.model_dump(mode="json") if self.pool else None,
            "quotes":[q.model_dump(mode="json") for q in self.quotes],
            "risk":self.risk.model_dump(mode="json"),
            "orders":[o.model_dump(mode="json") for o in self.paper.all_orders()] if self.config.execution_mode==ExecutionMode.PAPER else [o.model_dump(mode="json") for o in self.testnet.all_orders()],
            "fills":[f.model_dump(mode="json") for f in self.paper.fills.all()] if self.config.execution_mode==ExecutionMode.PAPER else [],
            "venue_reconciliation":{"last_reconciled_at":self.testnet.last_reconciled_at.isoformat() if self.testnet.last_reconciled_at else None,"error":self.testnet.reconciliation_error},
            "reconciliation":[a.model_dump(mode="json") for a in self.last_actions],
        }
