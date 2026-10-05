from decimal import Decimal as D

import pytest

from app.config import Settings
from app.execution.models import OrderRequest
from app.execution.order_manager import OrderManager
from app.execution.paper import PaperExecutionAdapter
from app.market_data.history import MarketPriceHistory
from app.strategy.inventory import build_inventory_state
from app.strategy.models import StrategyConfig
from app.strategy.market_adaptation import MarketAdaptationPolicy
from app.strategy.quote_engine import QuoteEngine
from app.market_data.mock import MockMarketDataAdapter
from app.runtime import HyperAmmRuntime


@pytest.mark.asyncio
async def test_market_version_change_blocks_stale_transmission():
    rt=HyperAmmRuntime(Settings())
    snap1=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap1)
    rt.strategy.running=True
    rt.inventory=rt._paper_inventory()
    rt.market_history.add_snapshot(snap1)
    rt._expected_inventory_version=rt.inventory.version
    rt._expected_market_version=rt.market_history.version

    snap2=MockMarketDataAdapter().snapshot_for(2)
    rt.market_history.add_snapshot(snap2)
    with pytest.raises(RuntimeError,match="market/adaptation state changed"):
        await rt._execution_authority()


@pytest.mark.asyncio
async def test_refresh_exposes_warmup_adaptation_without_fake_volatility():
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    await rt.refresh_once()
    d=rt.market_adaptation_decision
    assert d is not None
    assert d.volatility_ready is False
    assert d.realized_volatility is None
    assert d.spread_multiplier==1
    assert d.global_size_multiplier==1
    assert rt.quotes


@pytest.mark.asyncio
async def test_invalid_adaptation_cancels_active_strategy_orders(monkeypatch):
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    rt.paper.update_market(snap)
    await rt.paper.submit_orders([
        OrderRequest(
            client_order_id="resting",
            market="ETH",
            side="BID",
            price=snap.best_bid-D("100"),
            size=D(".2"),
            level_index=0,
        )
    ])
    assert await rt.paper.get_open_orders()
    rt.strategy.running=True

    def fail(*args,**kwargs):
        raise ValueError("invalid Phase 6 math")

    monkeypatch.setattr(MarketAdaptationPolicy,"apply",fail)
    await rt.refresh_once()
    assert await rt.paper.get_open_orders()==[]
    assert rt.strategy.quote_health=="DEGRADED"
    assert "invalid Phase 6 math" in rt.strategy.last_error


@pytest.mark.asyncio
async def test_kill_switch_remains_authoritative_with_phase6():
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    rt.strategy.running=True
    await rt.activate_kill()
    await rt.refresh_once()
    assert rt.risk.kill_switch_active is True
    assert rt.strategy.quote_health=="HALTED"
    assert rt.quotes==[]


@pytest.mark.asyncio
async def test_market_adaptation_summary_serializes_warmup_state():
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    payload=await rt.market_adaptation_summary()
    assert payload["market"]=="ETH"
    assert payload["volatility_ready"] is False
    assert payload["realized_volatility"] is None
    assert payload["sample_count"]==1
    assert payload["source"]=="NORMALIZED_MID_L2"


@pytest.mark.asyncio
async def test_meaningful_phase6_change_reuses_reconciliation_replace_actions():
    adapter=MockMarketDataAdapter()
    quiet=adapter.snapshot_for(1)
    later=adapter.snapshot_for(2)
    config=StrategyConfig(
        volatility_window_samples=2,
        volatility_min_samples=2,
        volatility_low_threshold=D("0"),
        volatility_high_threshold=D("0.0000001"),
        volatility_spread_strength=D("1"),
        volatility_size_strength=D(".5"),
        imbalance_spread_strength=D("0"),
        imbalance_size_strength=D("0"),
    )
    inventory=build_inventory_state(
        market="ETH",position=D("0"),target=D("0"),soft_limit=D("5"),source="PAPER"
    )
    engine=QuoteEngine()
    history=MarketPriceHistory()
    history.add_snapshot(quiet)
    _,_,quiet_quotes,_=engine.generate_inventory_aware(config,quiet,inventory)

    execution=PaperExecutionAdapter()
    execution.update_market(quiet)
    manager=OrderManager(execution)
    initial=await manager.reconcile("ETH",quiet_quotes,config.replace_tolerance_bps,config.size_tolerance)
    assert any(action.action=="CREATE" for action in initial)

    history.add_snapshot(later)
    _,_,adaptive,_,decision=engine.generate_market_adaptive(config,later,inventory,history)
    assert decision.spread_multiplier>1
    actions=await manager.reconcile("ETH",adaptive,config.replace_tolerance_bps,config.size_tolerance)
    assert any(action.action=="REPLACE" for action in actions)


@pytest.mark.asyncio
async def test_neutral_phase6_output_can_keep_existing_quotes():
    snap=MockMarketDataAdapter().snapshot_for(1)
    config=StrategyConfig(volatility_min_samples=10)
    inventory=build_inventory_state(
        market="ETH",position=D("0"),target=D("0"),soft_limit=D("5"),source="PAPER"
    )
    history=MarketPriceHistory(); history.add_snapshot(snap)
    _,_,quotes,_,decision=QuoteEngine().generate_market_adaptive(config,snap,inventory,history)
    assert decision.volatility_ready is False

    execution=PaperExecutionAdapter(); execution.update_market(snap)
    manager=OrderManager(execution)
    await manager.reconcile("ETH",quotes,config.replace_tolerance_bps,config.size_tolerance)
    actions=await manager.reconcile("ETH",quotes,config.replace_tolerance_bps,config.size_tolerance)
    assert actions and all(action.action=="KEEP" for action in actions)


@pytest.mark.asyncio
async def test_adaptive_quote_distance_risk_violation_fails_closed():
    rt=HyperAmmRuntime(Settings())
    rt.config.volatility_window_samples=2
    rt.config.volatility_min_samples=2
    rt.config.volatility_low_threshold=D("0")
    rt.config.volatility_high_threshold=D("0.0000001")
    rt.config.volatility_spread_strength=D("2")
    rt.config.imbalance_spread_strength=D("0")
    rt.risk.max_quote_distance_bps=D("120")

    adapter=MockMarketDataAdapter()
    first=adapter.snapshot_for(1)
    second=adapter.snapshot_for(2)
    await rt.market._accept(first)
    await rt.market._accept(second)
    rt.strategy.running=True
    await rt.refresh_once()

    assert rt.strategy.quote_health=="DEGRADED"
    assert rt.quotes==[]
    assert "quote distance exceeds limit" in rt.strategy.last_error
