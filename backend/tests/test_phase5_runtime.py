from datetime import timedelta
from decimal import Decimal as D
import pytest

from app.config import Settings
from app.execution.models import Fill
from app.execution.order_manager import OrderManager
from app.execution.paper import PaperExecutionAdapter
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.models import utcnow
from app.runtime import HyperAmmRuntime
from app.strategy.inventory import build_inventory_state
from app.strategy.models import StrategyConfig
from app.strategy.quote_engine import QuoteEngine


@pytest.mark.asyncio
async def test_hard_limit_reconciliation_cancels_resting_increasing_side():
    snap=MockMarketDataAdapter().snapshot_for(1)
    config=StrategyConfig()
    engine=QuoteEngine()
    ex=PaperExecutionAdapter(); ex.update_market(snap)
    _,_,neutral=engine.generate(config,snap)
    manager=OrderManager(ex)
    await manager.reconcile("ETH",neutral,config.replace_tolerance_bps,config.size_tolerance)
    inventory=build_inventory_state(
        market="ETH",position=D("10"),target=D("0"),soft_limit=D("5"),source="PAPER"
    )
    _,_,limited,_=engine.generate_inventory_aware(config,snap,inventory)
    actions=await manager.reconcile("ETH",limited,config.replace_tolerance_bps,config.size_tolerance)
    assert any(a.action=="CANCEL" and a.existing.side=="BID" for a in actions)
    assert all(o.side=="ASK" for o in await ex.get_open_orders())


@pytest.mark.asyncio
async def test_paper_fill_changes_next_runtime_ladder():
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    await rt.refresh_once()
    neutral=rt.inventory_decision.reservation_price
    rt.paper.fills.add(Fill(client_order_id="economic",market="ETH",side="BID",price=snap.best_ask,size=D("2.5")))
    await rt.refresh_once()
    assert rt.inventory.position_base==D("2.5")
    assert rt.inventory_decision.reservation_price < neutral
    assert rt.inventory_decision.bid_size_multiplier < 1 < rt.inventory_decision.ask_size_multiplier


@pytest.mark.asyncio
async def test_inventory_version_blocks_stale_transmission():
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    rt.strategy.running=True
    rt.inventory=rt._paper_inventory()
    rt._expected_inventory_version=rt.inventory.version
    rt.paper.fills.add(Fill(client_order_id="late",market="ETH",side="BID",price=snap.best_ask,size=D("1")))
    with pytest.raises(RuntimeError,match="inventory changed"):
        await rt._execution_authority()


@pytest.mark.asyncio
async def test_missing_or_stale_testnet_inventory_never_defaults_to_zero():
    rt=HyperAmmRuntime(Settings())
    rt.config.execution_mode="TESTNET"
    rt.strategy.config.execution_mode="TESTNET"
    with pytest.raises(RuntimeError,match="unavailable"):
        await rt._testnet_inventory_locked(refresh=False)
    rt.testnet._positions["ETH"]=D("3")
    rt.testnet._position_updated_at=utcnow()-timedelta(seconds=30)
    rt.testnet._position_version=1
    rt.config.inventory_stale_after_seconds=1
    with pytest.raises(RuntimeError,match="stale"):
        await rt._testnet_inventory_locked(refresh=False)
