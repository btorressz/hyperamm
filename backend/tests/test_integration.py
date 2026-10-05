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

from datetime import timedelta
from app.market_data.models import MarketConnectionState, utcnow
from app.execution.models import OrderStatus


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['stale','DEGRADED','DISCONNECTED','RECONNECTING','missing_bid','missing_ask','crossed','nan','infinity','zero','risk','generation','snapshot'])
async def test_fail_closed_and_recovery(failure,monkeypatch):
    rt=HyperAmmRuntime(Settings())
    healthy=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(healthy)
    rt.strategy.running=True
    await rt.refresh_once()
    old=list(await rt.paper.get_open_orders())
    assert len(old)==16 and rt.strategy.quote_health=='HEALTHY'
    bad=healthy.model_copy(deep=True)
    if failure=='stale': bad.latest_valid_update=utcnow()-timedelta(seconds=10)
    elif failure in {'DEGRADED','DISCONNECTED','RECONNECTING'}: bad.connection_state=MarketConnectionState(failure)
    elif failure=='missing_bid': bad.best_bid=None
    elif failure=='missing_ask': bad.best_ask=None
    elif failure=='crossed': bad.best_bid=bad.best_ask
    elif failure=='nan': bad.best_bid=D('NaN')
    elif failure=='infinity': bad.best_ask=D('Infinity')
    elif failure=='zero': bad.best_bid=D('0')
    elif failure=='risk': rt.risk.max_order_size=D('.0001')
    original_generate=rt.quote_engine.generate_at_reference
    original_snapshot=rt.market.snapshot
    def broken(*args): raise ValueError('generation failed')
    async def unavailable(): raise ValueError('snapshot unavailable')
    if failure=='generation': monkeypatch.setattr(rt.quote_engine,'generate_at_reference',broken)
    if failure=='snapshot': monkeypatch.setattr(rt.market,'snapshot',unavailable)
    # Inject provider state without invoking the listener: timer path must cancel too.
    rt.market._snapshot=bad
    await rt.refresh_once()
    assert not await rt.paper.get_open_orders()
    assert all(o.status==OrderStatus.CANCELLED for o in old)
    assert rt.quotes==[] and rt.fair_value is None and rt.pool is None
    assert rt.strategy.running and rt.strategy.quote_health=='DEGRADED'
    assert rt.strategy.last_error
    monkeypatch.setattr(rt.quote_engine,'generate_at_reference',original_generate)
    monkeypatch.setattr(rt.market,'snapshot',original_snapshot)
    rt.risk.max_order_size=D('25')
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(2))
    await rt.refresh_once()
    assert len(await rt.paper.get_open_orders())==16
    assert rt.strategy.quote_health=='HEALTHY' and rt.strategy.last_error is None


@pytest.mark.asyncio
async def test_market_listener_cancels_before_paper_can_fill_invalid_bbo():
    rt=HyperAmmRuntime(Settings())
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(1))
    rt.strategy.running=True
    await rt.refresh_once()
    bad=MockMarketDataAdapter().snapshot_for(2)
    bad.best_ask=D('1'); bad.best_bid=D('2')
    await rt.market._accept(bad)
    assert not await rt.paper.get_open_orders()
    assert not rt.paper.fills.all()
    assert rt.strategy.quote_health=='DEGRADED'


@pytest.mark.asyncio
async def test_completed_kill_is_barrier_for_inflight_and_queued_refresh(monkeypatch):
    rt=HyperAmmRuntime(Settings())
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(1))
    rt.strategy.running=True
    entered=asyncio.Event(); release=asyncio.Event()
    original=rt.paper.submit_orders
    async def blocked(orders):
        entered.set()
        await release.wait()
        return await original(orders)
    monkeypatch.setattr(rt.paper,'submit_orders',blocked)
    refresh=asyncio.create_task(rt.refresh_once())
    await asyncio.wait_for(entered.wait(),1)
    kill=asyncio.create_task(rt.activate_kill())
    await asyncio.sleep(0)
    assert rt.risk.kill_switch_active and not kill.done()
    queued=asyncio.create_task(rt.refresh_once())
    release.set()
    await asyncio.wait_for(asyncio.gather(refresh,kill,queued),2)
    assert not await rt.paper.get_open_orders()
    assert not rt.strategy.running and rt.strategy.quote_health=='HALTED'
    await rt.refresh_once()
    assert not await rt.paper.get_open_orders()
    await rt.resume()
    await rt.refresh_once()
    assert not rt.strategy.running and not await rt.paper.get_open_orders()


@pytest.mark.asyncio
async def test_failed_cancel_latches_halt_and_exposes_uncertainty(monkeypatch):
    rt=HyperAmmRuntime(Settings())
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(1))
    rt.strategy.running=True
    await rt.refresh_once()
    async def fail(): raise RuntimeError('venue unavailable')
    monkeypatch.setattr(rt.paper,'cancel_all',fail)
    rt.risk.max_order_size=D('.0001')
    with pytest.raises(RuntimeError,match='venue unavailable'):
        await rt.refresh_once()
    assert not rt.quotes and rt.risk.kill_switch_active
    assert rt.strategy.quote_health=='HALTED'
    assert 'cancellation unconfirmed' in rt.strategy.last_error


@pytest.mark.asyncio
async def test_stale_watchdog_with_long_quote_interval():
    rt=HyperAmmRuntime(Settings(market_stale_after_seconds=.1))
    rt.config.quote_refresh_interval_ms=60000
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(1))
    await rt.start_strategy()
    try:
        async def resting():
            while not await rt.paper.get_open_orders(): await asyncio.sleep(.001)
        await asyncio.wait_for(resting(),.5)
        async def cancelled():
            while rt.strategy.quote_health!='DEGRADED': await asyncio.sleep(.01)
        await asyncio.wait_for(cancelled(),2)
        assert not await rt.paper.get_open_orders()
        assert rt.strategy.running
    finally:
        await rt.stop_strategy()


@pytest.mark.asyncio
async def test_expired_timestamp_cannot_trigger_paper_fill():
    rt=HyperAmmRuntime(Settings())
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(1))
    rt.strategy.running=True
    await rt.refresh_once()
    old=MockMarketDataAdapter().snapshot_for(2)
    old.latest_valid_update=utcnow()-timedelta(seconds=10)
    old.best_bid=D('1'); old.best_ask=D('2')
    await rt.market._accept(old)
    assert not await rt.paper.get_open_orders() and not rt.paper.fills.all()
    assert rt.strategy.quote_health=='DEGRADED'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['missing','crossed','nonfinite'])
async def test_invalid_live_payload_publishes_degraded_state(kind,monkeypatch):
    from app.market_data.hyperliquid import HyperliquidMarketDataAdapter
    states=[]; got=asyncio.Event()
    payload={'time':int(utcnow().timestamp()*1000),'levels':[[{'px':'2999','sz':'1'}],[{'px':'3001','sz':'1'}]]}
    if kind=='missing': payload['levels'][0]=[]
    if kind=='crossed': payload['levels'][0][0]['px']='3002'
    if kind=='nonfinite': payload['levels'][0][0]['px']='NaN'
    class InfoFixture:
        def __init__(self,*args,**kwargs): pass
        def subscribe(self,*args): return 1
        def l2_snapshot(self,*args): return payload
        def unsubscribe(self,*args): pass
    monkeypatch.setattr('hyperliquid.info.Info',InfoFixture)
    adapter=HyperliquidMarketDataAdapter('ETH')
    async def accepted(snapshot): states.append(snapshot); got.set()
    task=asyncio.create_task(adapter.start(accepted))
    try:
        await asyncio.wait_for(got.wait(),1)
        assert states[-1].connection_state==MarketConnectionState.DEGRADED
        assert states[-1].stale and states[-1].best_bid is None
    finally:
        await adapter.stop(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
