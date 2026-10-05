from decimal import Decimal as D

import pytest

from app.config import Settings
from app.execution.models import OrderRequest
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

    monkeypatch.setattr(rt.quote_engine,"generate_market_adaptive",fail)
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
