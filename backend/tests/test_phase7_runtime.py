from datetime import timedelta
from decimal import Decimal as D

import pytest

from app.config import Settings
from app.execution.models import OrderRequest
from app.execution.order_manager import OrderManager
from app.execution.paper import PaperExecutionAdapter
from app.market_data.history import MarketPriceHistory
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.perp_context import build_perp_market_context, utcnow
from app.runtime import HyperAmmRuntime
from app.strategy.inventory import build_inventory_state
from app.strategy.models import StrategyConfig
from app.strategy.quote_engine import QuoteEngine


def perp(
    *,
    mid="3000",
    mark="3000",
    oracle="3000",
    funding="0",
    oi="100000",
    version=1,
    updated_at=None,
):
    return build_perp_market_context(
        market="ETH",
        market_mid=D(mid),
        provider_mid_price=D(mid),
        mark_price=D(mark),
        oracle_price=D(oracle),
        funding_rate=D(funding),
        open_interest_base=D(oi),
        premium=D("0"),
        updated_at=updated_at or utcnow(),
        source="HYPERLIQUID",
        simulated=False,
        version=version,
    )


def inventory(position="0"):
    return build_inventory_state(
        market="ETH",position=D(position),target=D("0"),soft_limit=D("5"),source="PAPER"
    )


def phase6_ready_history():
    adapter=MockMarketDataAdapter()
    h=MarketPriceHistory()
    for i in range(1,11):
        h.add_snapshot(adapter.snapshot_for(i))
    return h


def test_phase7_disabled_preserves_phase6_executable_ladder_exactly():
    config=StrategyConfig(perp_context_enabled=False)
    snap=MockMarketDataAdapter().snapshot_for(11)
    history=phase6_ready_history()
    engine=QuoteEngine()
    old=engine.generate_market_adaptive(config,snap,inventory("2.5"),history)
    new=engine.generate_perp_market_adaptive(config,snap,inventory("2.5"),history,perp())
    _,old_pool,old_quotes,old_inv,old_market=old
    _,new_pool,new_quotes,new_inv,new_market,perp_decision=new
    assert new_pool==old_pool
    assert perp_decision.enabled is False
    assert [(q.side,q.price,q.size,q.distance_bps,q.level_index) for q in new_quotes] == [
        (q.side,q.price,q.size,q.distance_bps,q.level_index) for q in old_quotes
    ]
    assert new_inv.reservation_price==old_inv.reservation_price
    assert new_market.spread_multiplier==old_market.spread_multiplier


def test_phase7_reference_recenters_amm_before_inventory_and_phase6():
    config=StrategyConfig(
        perp_context_enabled=True,
        perp_mark_weight=D(".5"),
        perp_oracle_weight=D(".25"),
        funding_reference_abs_rate=D(".00025"),
        max_funding_reference_shift_bps=D("5"),
        market_adaptation_enabled=False,
    )
    snap=MockMarketDataAdapter(start_price=D("3000")).snapshot_for(1)
    history=MarketPriceHistory(); history.add_snapshot(snap)
    fair,pool,quotes,inv_decision,market_decision,perp_decision=QuoteEngine().generate_perp_market_adaptive(
        config,snap,inventory(),history,perp(mid=str(snap.mid_price),mark="3010",oracle="3005",funding="0")
    )
    assert fair==snap.mid_price
    assert pool.reference_price==perp_decision.final_reference_price
    assert inv_decision.market_fair_value==fair
    assert inv_decision.reference_price==perp_decision.final_reference_price
    assert inv_decision.reservation_price==perp_decision.final_reference_price
    assert market_decision.spread_multiplier==1
    assert all(q.market_fair_value==fair for q in quotes)
    assert all(q.perp_reference_price==perp_decision.final_reference_price for q in quotes)


def test_phase6_warmup_preserves_phase5_output_built_on_phase7_reference():
    config=StrategyConfig(volatility_min_samples=10)
    snap=MockMarketDataAdapter(start_price=D("3000")).snapshot_for(1)
    history=MarketPriceHistory(); history.add_snapshot(snap)
    ctx=perp(mid=str(snap.mid_price),mark="3010",oracle="3005",funding="0")
    engine=QuoteEngine()
    fair=engine.generate_at_reference(
        config,snap,
        __import__("app.strategy.perp_policy",fromlist=["PerpContextPolicy"]).PerpContextPolicy(config).decision(snap.mid_price,ctx).final_reference_price
    )
    _,_,neutral=fair
    reference=__import__("app.strategy.perp_policy",fromlist=["PerpContextPolicy"]).PerpContextPolicy(config).decision(snap.mid_price,ctx).final_reference_price
    from app.strategy.inventory import InventoryPolicy
    phase5,inv_decision=InventoryPolicy(config).apply(neutral,snap.mid_price,inventory("2.5"),reference)
    _,_,final,_,market_decision,_=engine.generate_perp_market_adaptive(config,snap,inventory("2.5"),history,ctx)
    assert market_decision.volatility_ready is False
    assert [(q.side,q.price,q.size,q.distance_bps) for q in final] == [
        (q.side,q.price,q.size,q.distance_bps) for q in phase5
    ]


@pytest.mark.parametrize("position,forbidden",[("10","BID"),("-10","ASK")])
def test_phase7_never_restores_hard_inventory_side(position,forbidden):
    config=StrategyConfig(volatility_min_samples=2,volatility_window_samples=2)
    adapter=MockMarketDataAdapter()
    s1=adapter.snapshot_for(1); s2=adapter.snapshot_for(2)
    history=MarketPriceHistory(); history.add_snapshot(s1); history.add_snapshot(s2)
    _,_,quotes,decision,_,_=QuoteEngine().generate_perp_market_adaptive(
        config,s2,inventory(position),history,
        perp(mid=str(s2.mid_price),mark=str(s2.mid_price+D("20")),oracle=str(s2.mid_price-D("20")),funding="0.00025"),
    )
    assert decision.hard_limit_state in {"LONG_LIMIT","SHORT_LIMIT"}
    assert not any(q.side==forbidden for q in quotes)


@pytest.mark.asyncio
async def test_perp_version_change_blocks_transmission():
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    rt.strategy.running=True
    rt.inventory=rt._paper_inventory()
    rt.market_history.add_snapshot(snap)
    initial_time=utcnow()-timedelta(seconds=1)
    rt.perp_context_service.accept(perp(mid=str(snap.mid_price),updated_at=initial_time))
    current=rt.perp_context_service.snapshot(snap.mid_price)
    rt._expected_inventory_version=rt.inventory.version
    rt._expected_market_version=rt.market_history.version
    rt._expected_perp_version=current.version
    rt.perp_context_service.accept(perp(mid=str(snap.mid_price),mark="3001",updated_at=initial_time+timedelta(milliseconds=1)))
    with pytest.raises(RuntimeError,match="perp context changed"):
        await rt._execution_authority()


@pytest.mark.asyncio
async def test_stale_perp_context_fails_closed_and_cancels():
    rt=HyperAmmRuntime(Settings())
    rt.config.perp_context_stale_after_seconds=.01
    rt.perp_context_service.stale_after_seconds=.01
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    rt.perp_context_service.accept(perp(mid=str(snap.mid_price),updated_at=utcnow()-timedelta(seconds=1)))
    rt.paper.update_market(snap)
    await rt.paper.submit_orders([
        OrderRequest(
            client_order_id="resting-before-stale-perp",
            market="ETH",
            side="BID",
            price=snap.best_bid-D("100"),
            size=D(".2"),
            level_index=0,
        )
    ])
    assert await rt.paper.get_open_orders()
    rt.strategy.running=True
    await rt.refresh_once()
    assert rt.strategy.quote_health=="DEGRADED"
    assert rt.quotes==[]
    assert await rt.paper.get_open_orders()==[]
    assert "perpetual market context is stale" in rt.strategy.last_error


@pytest.mark.asyncio
async def test_demo_runtime_exposes_phase7_context_without_wallet():
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(3)
    await rt.market._accept(snap)
    await rt.refresh_once()
    assert rt.perp_context is not None
    assert rt.perp_context.source=="DEMO"
    assert rt.perp_context.simulated is True
    assert rt.perp_position is not None
    assert rt.perp_position.source=="PAPER"
    assert rt.perp_position.signed_position_base==rt.inventory.position_base
    assert rt.perp_reference_decision is not None


@pytest.mark.asyncio
async def test_reference_change_reuses_existing_reconciliation_replace():
    config=StrategyConfig(
        market_adaptation_enabled=False,
        perp_mark_weight=D(".5"),
        perp_oracle_weight=D(".5"),
        max_perp_reference_shift_bps=D("50"),
    )
    snap=MockMarketDataAdapter(start_price=D("3000")).snapshot_for(1)
    history=MarketPriceHistory(); history.add_snapshot(snap)
    engine=QuoteEngine()
    execution=PaperExecutionAdapter(); execution.update_market(snap)
    manager=OrderManager(execution)
    _,_,first,_,_,_=engine.generate_perp_market_adaptive(
        config,snap,inventory(),history,perp(mid=str(snap.mid_price),mark="3000",oracle="3000")
    )
    await manager.reconcile("ETH",first,config.replace_tolerance_bps,config.size_tolerance)
    _,_,second,_,_,_=engine.generate_perp_market_adaptive(
        config,snap,inventory(),history,perp(mid=str(snap.mid_price),mark="3010",oracle="3010",version=2)
    )
    actions=await manager.reconcile("ETH",second,config.replace_tolerance_bps,config.size_tolerance)
    assert any(a.action=="REPLACE" for a in actions)


def test_same_user_state_feeds_phase5_and_phase7_position_consistently():
    from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
    from app.market_data.perp_context import normalize_user_position_context
    state={"assetPositions":[{"position":{
        "coin":"ETH","szi":"-2.25","entryPx":"3000","leverage":{"type":"cross","value":4},
        "liquidationPx":"3500","marginUsed":"1000","positionValue":"6750",
        "unrealizedPnl":"-10","returnOnEquity":"-0.01"
    }}]}
    phase5=HyperliquidTestnetExecutionAdapter.normalize_user_position(state,"ETH")
    phase7=normalize_user_position_context(state,"ETH").signed_position_base
    assert phase5==phase7==D("-2.25")
