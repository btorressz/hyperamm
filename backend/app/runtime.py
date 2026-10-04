from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
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
        self.orders=OrderManager(self.execution)
        self.quote_engine=QuoteEngine()
        self.risk=RiskStatus()
        self.kill=KillSwitch(self.risk)
        self.fair_value=None; self.pool=None; self.quotes=[]; self.last_actions=[]
        self._strategy_task=None
        self.market.add_listener(self._on_market)

    async def _on_market(self,snapshot):
        if self.config.execution_mode==ExecutionMode.PAPER: self.paper.update_market(snapshot)

    async def start_services(self): await self.market.start()
    async def stop_services(self):
        await self.stop_strategy(); await self.market.stop()

    async def refresh_once(self):
        snap=await self.market.snapshot()
        if self.risk.kill_switch_active: return
        try:
            fair,pool,quotes=self.quote_engine.generate(self.config,snap)
            validate_quotes(quotes,snap,self.risk)
            self.fair_value,self.pool,self.quotes=fair,pool,quotes
            if self.strategy.running:
                validate_execution_authority(risk=self.risk, execution_mode=self.config.execution_mode.value, strategy_running=True)
                self.last_actions=await self.orders.reconcile(self.config.market,quotes,self.config.replace_tolerance_bps,self.config.size_tolerance)
            else:
                self.last_actions=[]
            self.strategy.last_error=None
        except Exception as exc:
            self.strategy.last_error=str(exc)

    async def _loop(self):
        while self.strategy.running:
            await self.refresh_once()
            await asyncio.sleep(self.config.quote_refresh_interval_ms/1000)

    async def start_strategy(self):
        if self.risk.kill_switch_active: raise PermissionError("kill switch is active")
        if self.config.execution_mode==ExecutionMode.TESTNET and not self.settings.enable_hyperliquid_testnet_orders:
            raise PermissionError("testnet execution selected but ENABLE_HYPERLIQUID_TESTNET_ORDERS is false")
        self.strategy.running=True
        if not self._strategy_task or self._strategy_task.done(): self._strategy_task=asyncio.create_task(self._loop(),name="strategy")
        return self.strategy

    async def stop_strategy(self):
        self.strategy.running=False
        if self._strategy_task:
            self._strategy_task.cancel()
            try: await self._strategy_task
            except asyncio.CancelledError: pass
            self._strategy_task=None
        await self.execution.cancel_all()
        return self.strategy

    async def update_config(self,new_config: StrategyConfig):
        mode_changed = new_config.market_data_mode != self.config.market_data_mode or new_config.market != self.config.market
        execution_changed = new_config.execution_mode != self.config.execution_mode
        was_running=self.strategy.running
        if mode_changed:
            await self.market.stop()
            self.market=MarketDataService(new_config.market,new_config.market_data_mode,self.settings.market_stale_after_seconds,self.settings.demo_update_interval_seconds)
            self.market.add_listener(self._on_market); await self.market.start()
        if execution_changed:
            await self.execution.cancel_all()
            self.execution=self.paper if new_config.execution_mode==ExecutionMode.PAPER else self.testnet
            self.orders=OrderManager(self.execution)
        self.config=new_config; self.strategy.config=new_config
        if was_running: await self.refresh_once()
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
            "orders":[o.model_dump(mode="json") for o in self.paper.all_orders()] if self.config.execution_mode==ExecutionMode.PAPER else [o.model_dump(mode="json") for o in await self.execution.get_open_orders()],
            "fills":[f.model_dump(mode="json") for f in self.paper.fills.all()] if self.config.execution_mode==ExecutionMode.PAPER else [],
            "reconciliation":[a.model_dump(mode="json") for a in self.last_actions],
        }
