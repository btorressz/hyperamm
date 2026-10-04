import asyncio
from decimal import Decimal as D
import pytest
from app.config import Settings
from app.runtime import HyperAmmRuntime
from app.market_data.service import MarketDataService
from app.market_data.models import MarketDataMode
from app.market_data.mock import MockMarketDataAdapter


@pytest.mark.asyncio
async def test_phase_1_to_4_demo_pipeline_places_paper_quotes():
    settings=Settings(
        market='ETH',market_data_mode='DEMO',execution_mode='PAPER',
        demo_update_interval_seconds=0.01,market_stale_after_seconds=1,
    )
    rt=HyperAmmRuntime(settings)
    await rt.start_services()
    try:
        await asyncio.sleep(0.03)
        await rt.start_strategy()
        await asyncio.sleep(0.03)
        assert rt.fair_value is not None
        assert rt.pool is not None
        assert len(rt.quotes)==rt.config.levels_per_side*2
        assert len(await rt.paper.get_open_orders())==rt.config.levels_per_side*2
        assert not rt.risk.kill_switch_active
    finally:
        await rt.stop_services()


@pytest.mark.asyncio
async def test_market_service_rejects_older_sequence():
    service=MarketDataService('ETH',MarketDataMode.DEMO,stale_after_seconds=10,demo_interval=1)
    mock=MockMarketDataAdapter()
    newer=mock.snapshot_for(10)
    older=mock.snapshot_for(9)
    await service._accept(newer)
    await service._accept(older)
    snap=await service.snapshot()
    assert snap.book is not None
    assert snap.book.sequence==10
