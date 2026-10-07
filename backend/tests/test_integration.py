import asyncio
from decimal import Decimal as D
import pytest
from app.config import Settings
from app.runtime import HyperAmmRuntime
from app.market_data.service import MarketDataService
from app.market_data.models import MarketDataMode, MarketSnapshot
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
async def test_invalid_live_payload_publishes_degraded_state(kind,sdk_market):
    from app.market_data.hyperliquid import HyperliquidMarketDataAdapter
    states=[]; got=asyncio.Event()
    payload={'time':int(utcnow().timestamp()*1000),'levels':[[{'px':'2999','sz':'1'}],[{'px':'3001','sz':'1'}]]}
    if kind=='missing': payload['levels'][0]=[]
    if kind=='crossed': payload['levels'][0][0]['px']='3002'
    if kind=='nonfinite': payload['levels'][0][0]['px']='NaN'
    sdk_market.plans.append({'book':payload})
    adapter=sdk_market.adapter
    async def accepted(snapshot): states.append(snapshot); got.set()
    task=asyncio.create_task(adapter.start(accepted))
    try:
        await asyncio.wait_for(got.wait(),1)
        assert states[-1].connection_state==MarketConnectionState.DEGRADED
        assert states[-1].stale and states[-1].best_bid is None
    finally:
        await adapter.stop()
        await task


async def record_snapshot(states, snapshot):
    states.append(snapshot)


async def eventually(predicate, timeout=2):
    async def wait():
        while not predicate():
            await asyncio.sleep(.001)
    await asyncio.wait_for(wait(), timeout)


@pytest.fixture
def sdk_market(monkeypatch):
    """Real SDK 0.24 Info subscription methods/manager/threads, fake transport/HTTP."""
    import json
    import threading
    from types import SimpleNamespace
    from hyperliquid.info import Info as SDKInfo
    from hyperliquid.websocket_manager import WebsocketManager
    from app.market_data.hyperliquid import HyperliquidMarketDataAdapter

    class Socket:
        def __init__(self, url, on_message, on_open):
            self.on_message = on_message
            self.on_open = on_open
            self.keep_running = True
            self.sock = SimpleNamespace(connected=False)
            self.ended = threading.Event()
            self.opened = threading.Event()
            self.sent = []
        def run_forever(self):
            self.sock.connected = True
            self.on_open(self)
            self.opened.set()
            self.ended.wait()
            self.sock.connected = False
            self.keep_running = False
        def send(self, message):
            if not self.sock.connected:
                raise ConnectionError('fixture socket closed')
            self.sent.append(json.loads(message))
        def close(self):
            self.keep_running = False
            self.sock.connected = False
            self.ended.set()
        def emit(self, channel, data):
            self.on_message(self, json.dumps({'channel':channel, 'data':data}))

    monkeypatch.setattr('hyperliquid.websocket_manager.websocket.WebSocketApp', Socket)
    instances = []
    plans = []
    def book():
        return {'coin':'ETH','time':int(utcnow().timestamp()*1000),
                'levels':[[{'px':'2999','sz':'1','n':1}],[{'px':'3001','sz':'1','n':1}]]}
    ctx = {'markPx':'3000','oraclePx':'3000','midPx':'3000','funding':'0','openInterest':'100','premium':'0'}

    class InfoFixture(SDKInfo):
        def __init__(self, *args, **kwargs):
            assert not any(x.ws_manager.is_alive() or x.ws_manager.ping_sender.is_alive() for x in instances)
            self.plan = plans[len(instances)] if len(instances) < len(plans) else {}
            self.name_to_coin = {'ETH':'ETH','BTC':'BTC'}
            self.disconnects = 0
            self.snapshot_calls = 0
            self.ctx_calls = 0
            self.ws_manager = WebsocketManager('https://fixture.invalid')
            instances.append(self)
            self.ws_manager.start()
            assert self.ws_manager.ws.opened.wait(1)
            if self.plan.get('init_gate'):
                assert self.plan['init_gate'].wait(2)
            if self.plan.get('init_error'):
                raise RuntimeError('fixture metadata initialization failure')
        def l2_snapshot(self, market):
            self.snapshot_calls += 1
            if self.plan.get('snapshot_gate'):
                assert self.plan['snapshot_gate'].wait(2)
            if self.plan.get('snapshot_error'):
                raise ValueError('fixture invalid snapshot')
            return self.plan.get('book', book())
        def meta_and_asset_ctxs(self):
            self.ctx_calls += 1
            return [{'universe':[{'name':'ETH'},{'name':'BTC'}]}, [ctx,ctx]]
        def disconnect_websocket(self):
            self.disconnects += 1
            return super().disconnect_websocket()

    monkeypatch.setattr('hyperliquid.info.Info', InfoFixture)
    adapter = HyperliquidMarketDataAdapter('ETH')
    adapter._health_interval = .002
    adapter._retry_initial = .002
    adapter._retry_max = .008
    adapter._shutdown_timeout = .2
    harness = SimpleNamespace(adapter=adapter, instances=instances, plans=plans, book=book, ctx=ctx)
    yield harness
    # Cleanup even a failing assertion; verify both real SDK threads were joined.
    for info in instances:
        if info.ws_manager.is_alive() or info.ws_manager.ping_sender.is_alive():
            info.disconnect_websocket()
            info.ws_manager.join(1)
        assert not info.ws_manager.is_alive()
        assert not info.ws_manager.ping_sender.is_alive()


@pytest.mark.asyncio
async def test_sdk_socket_termination_reconnects_once_and_disconnects_old_threads(sdk_market):
    h = sdk_market
    states = []
    task = asyncio.create_task(h.adapter.start(lambda snap:record_snapshot(states, snap)))
    try:
        await eventually(lambda:len(states)==1)
        old = h.instances[0]
        old_callback = old.ws_manager.active_subscriptions['l2Book:eth'][0].callback
        old.ws_manager.ws.close()
        await eventually(lambda:len(h.instances)==2 and states[-1].connection_state=='CONNECTED')
        assert [s.connection_state for s in states] == ['CONNECTED','DEGRADED','RECONNECTING','CONNECTED']
        assert old.disconnects == 1
        assert not old.ws_manager.is_alive() and not old.ws_manager.ping_sender.is_alive()
        current = h.instances[1]
        subscriptions = [x for x in current.ws_manager.ws.sent if x['method']=='subscribe']
        assert subscriptions == [{'method':'subscribe','subscription':{'type':'l2Book','coin':'ETH'}}]
        assert current.snapshot_calls == 1
        count = len(states)
        late = h.book(); late['levels'][0][0]['sz'] = '999'
        old_callback({'data':late})
        await asyncio.sleep(.01)
        assert len(states) == count
    finally:
        await h.adapter.stop()
        await task
    assert all(x.disconnects==1 for x in h.instances)
    assert h.adapter._info is None


@pytest.mark.asyncio
async def test_sdk_recovery_waits_for_fresh_snapshot_despite_queued_l2(sdk_market):
    import threading
    h = sdk_market
    gate = threading.Event()
    h.plans.extend([{}, {'snapshot_gate':gate}])
    states = []
    task = asyncio.create_task(h.adapter.start(lambda snap:record_snapshot(states, snap)))
    try:
        await eventually(lambda:states and states[-1].connection_state=='CONNECTED')
        h.instances[0].ws_manager.ws.close()
        await eventually(lambda:len(h.instances)==2 and h.instances[1].snapshot_calls==1)
        h.instances[1].ws_manager.ws.emit('l2Book',h.book())
        await asyncio.sleep(.01)
        assert states[-1].connection_state == 'RECONNECTING'
        assert sum(s.connection_state=='CONNECTED' for s in states) == 1
        gate.set()
        await eventually(lambda:states[-1].connection_state=='CONNECTED')
    finally:
        gate.set()
        await h.adapter.stop()
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['missing','crossed','old','expired'])
async def test_sdk_invalid_recovery_snapshot_never_recovers(sdk_market, failure):
    h = sdk_market
    states = []
    task = asyncio.create_task(h.adapter.start(lambda snap:record_snapshot(states, snap)))
    try:
        await eventually(lambda:states and states[-1].connection_state=='CONNECTED')
        bad = h.book()
        if failure=='missing': bad['levels'][0]=[]
        elif failure=='crossed': bad['levels'][0][0]['px']='3002'
        elif failure=='old': bad['time']=h.adapter._latest_exchange_ms-1
        else: bad['time']-=60000
        h.plans.extend([{}, {'book':bad}])
        async def paused(seconds):
            if len(h.instances)>=2 and h.instances[1].disconnects==1:
                await h.adapter._stop_event.wait()
            else:
                await asyncio.sleep(seconds)
        h.adapter._pause = paused
        h.instances[0].ws_manager.ws.close()
        await eventually(lambda:len(h.instances)==2 and h.instances[1].disconnects==1 and states[-1].connection_state=='RECONNECTING')
        assert sum(s.connection_state=='CONNECTED' for s in states)==1
        assert states[-1].connection_state=='RECONNECTING'
    finally:
        await h.adapter.stop()
        await task


@pytest.mark.asyncio
async def test_sdk_repeated_failures_have_bounded_backoff_without_duplicate_resources(sdk_market):
    h = sdk_market
    h.plans.extend([{'snapshot_error':True} for _ in range(6)])
    states = []
    delays = []
    pause = h.adapter._pause
    async def record(seconds):
        delays.append(seconds)
        if len(h.instances)>=6:
            await h.adapter._stop_event.wait()
        else:
            await pause(seconds)
    h.adapter._pause = record
    task = asyncio.create_task(h.adapter.start(lambda snap:record_snapshot(states, snap)))
    try:
        await eventually(lambda:len(h.instances)==6 and h.instances[-1].disconnects==1 and len(delays)==6)
        assert delays == [.002,.004,.008,.008,.008,.008]
        assert all(s.connection_state!='CONNECTED' for s in states)
        for info in h.instances:
            assert info.disconnects==1
            assert sum(x['method']=='subscribe' for x in info.ws_manager.ws.sent)==1
            assert not info.ws_manager.is_alive() and not info.ws_manager.ping_sender.is_alive()
        await asyncio.wait_for(h.adapter.stop(),1)
        await task
        assert len(h.instances)==6 and h.adapter._info is None
    finally:
        await h.adapter.stop()
        await task


@pytest.mark.asyncio
async def test_sdk_partial_constructor_failure_closes_owned_threads(sdk_market):
    h = sdk_market
    h.plans.append({'init_error':True})
    states = []
    task = asyncio.create_task(h.adapter.start(lambda snap:record_snapshot(states, snap)))
    try:
        await eventually(lambda:len(h.instances)==2 and states[-1].connection_state=='CONNECTED')
        assert h.instances[0].disconnects==1
        assert not h.instances[0].ws_manager.is_alive()
        assert not h.instances[0].ws_manager.ping_sender.is_alive()
    finally:
        await h.adapter.stop()
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize('phase',['init','snapshot'])
@pytest.mark.parametrize('worker_failure',[False,True])
async def test_sdk_cancel_during_blocking_call_drains_worker_then_disconnects(sdk_market, phase, worker_failure):
    import threading
    h = sdk_market
    gate = threading.Event()
    h.plans.append({f'{phase}_gate':gate,f'{phase}_error':worker_failure})
    states = []
    task = asyncio.create_task(h.adapter.start(lambda snap:record_snapshot(states, snap)))
    try:
        await eventually(lambda:h.instances and (phase=='init' or h.instances[0].snapshot_calls==1))
        task.cancel()
        await asyncio.sleep(.01)
        assert not task.done()
        task.cancel()  # Repeated cancellation must not abandon the SDK worker.
        await asyncio.sleep(.001)
        assert not task.done()
        gate.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert h.instances[0].disconnects==1
        assert not h.instances[0].ws_manager.is_alive()
        assert not h.instances[0].ws_manager.ping_sender.is_alive()
        assert not states
    finally:
        gate.set()
        if not task.done():
            await h.adapter.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['identical','formatting','price','depth','deep_level','order_count'])
async def test_same_exchange_time_material_identity(change):
    from app.market_data.hyperliquid import HyperliquidMarketDataAdapter
    from app.market_data.history import MarketPriceHistory
    service = MarketDataService('ETH',MarketDataMode.LIVE)
    adapter = HyperliquidMarketDataAdapter('ETH')
    history = MarketPriceHistory()
    service.add_listener(history.add_snapshot)
    payload = {'coin':'ETH','time':int(utcnow().timestamp()*1000),
               'levels':[[{'px':'2999','sz':'1','n':1},{'px':'2998','sz':'2','n':2}],
                         [{'px':'3001','sz':'1','n':1}]]}
    assert await adapter._deliver_book(payload,service._accept)
    before = await service.snapshot()
    version = history.version
    import copy
    replay = copy.deepcopy(payload)
    if change=='formatting':
        replay['levels'][0][0].update(px='2999.000',sz='1.00')
    elif change=='price': replay['levels'][0][0]['px']='2999.5'
    elif change=='depth': replay['levels'][0][0]['sz']='100'
    elif change=='deep_level': replay['levels'][0][1]['sz']='100'
    elif change=='order_count': replay['levels'][0][0]['n']=3
    assert await adapter._deliver_book({'data':replay},service._accept)
    after = await service.snapshot()
    changed = change not in {'identical','formatting'}
    assert after.latest_valid_update == before.latest_valid_update
    assert after.book.sequence == before.book.sequence + int(changed)
    assert history.version == version + int(changed)
    assert len(history)==1  # Same-time updates do not create volatility samples.
    if change in {'depth','deep_level','order_count'}:
        assert after.mid_price==before.mid_price
    # Even after a feed failure, the source watermark must reject older books.
    await service._accept(MarketSnapshot.unavailable('ETH',MarketDataMode.LIVE,'failure'))
    old = before.model_copy(deep=True)
    old.latest_valid_update -= timedelta(milliseconds=1)
    old.book.sequence = after.book.sequence + 100
    await service._accept(old)
    assert (await service.snapshot()).book is None
    replay['time']-=1
    assert not await adapter._deliver_book(replay,service._accept)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['ping','silent_l2','silent_perp'])
async def test_sdk_socket_and_feed_health_failure_reconnects(sdk_market, failure):
    h = sdk_market
    if failure=='silent_perp':
        h.adapter.add_perp_listener(lambda ctx:None)
    h.adapter.stale_after_seconds=.03
    states=[]
    task=asyncio.create_task(h.adapter.start(lambda snap:record_snapshot(states,snap)))
    try:
        await eventually(lambda:states and states[-1].connection_state=='CONNECTED')
        if failure=='ping':
            # End the SDK ping sender while the socket/manager still runs.
            h.instances[0].ws_manager.stop_event.set()
        elif failure=='silent_perp':
            async def feed_l2():
                while len(h.instances)==1:
                    h.instances[0].ws_manager.ws.emit('l2Book',h.book())
                    await asyncio.sleep(.003)
            feeder=asyncio.create_task(feed_l2())
        await eventually(lambda:len(h.instances)==2 and states[-1].connection_state=='CONNECTED')
        assert h.instances[0].disconnects==1
        assert any(s.connection_state=='DEGRADED' for s in states)
        assert any(s.connection_state=='RECONNECTING' for s in states)
        if failure=='silent_perp': await feeder
    finally:
        await h.adapter.stop()
        await task


@pytest.mark.asyncio
async def test_reconfiguration_disconnects_previous_sdk_socket_before_new_instance(sdk_market):
    from app.market_data.models import MarketConnectionState
    h=sdk_market
    rt=HyperAmmRuntime(Settings(_env_file=None,redstone_public_http_fallback_enabled=False))
    await rt.start_services()
    try:
        for i in range(3):
            live=rt.config.model_copy(update={'market_data_mode':MarketDataMode.LIVE})
            await rt.update_config(live)
            async def connected():
                while (await rt.market.snapshot()).connection_state!=MarketConnectionState.CONNECTED:
                    await asyncio.sleep(.001)
            await asyncio.wait_for(connected(),2)
            assert len(h.instances)==i+1
            old_service=rt.market
            demo=rt.config.model_copy(update={'market_data_mode':MarketDataMode.DEMO})
            await rt.update_config(demo)
            assert old_service._adapter._info is None
            assert h.instances[-1].disconnects==1
            assert not h.instances[-1].ws_manager.is_alive()
            assert not h.instances[-1].ws_manager.ping_sender.is_alive()
        assert all(x.disconnects==1 for x in h.instances)
    finally:
        await rt.stop_services()


@pytest.mark.asyncio
async def test_service_repeated_start_stop_restores_single_sdk_subscription(sdk_market):
    h=sdk_market
    service=MarketDataService('ETH',MarketDataMode.LIVE)
    service._adapter=h.adapter
    for i in range(3):
        await asyncio.gather(service.start(),service.start())
        async def connected():
            while (await service.snapshot()).connection_state!='CONNECTED':
                await asyncio.sleep(.001)
        await asyncio.wait_for(connected(),2)
        assert len(h.instances)==i+1
        await asyncio.gather(service.stop(),service.stop())
        assert (await service.snapshot()).stale
        assert h.instances[-1].disconnects==1
        assert sum(x['method']=='subscribe' for x in h.instances[-1].ws_manager.ws.sent)==1


@pytest.mark.asyncio
async def test_shutdown_timeout_retains_info_and_prevents_duplicate_socket(sdk_market):
    import threading
    h=sdk_market
    states=[]
    task=asyncio.create_task(h.adapter.start(lambda snap:record_snapshot(states,snap)))
    gate=threading.Event()
    try:
        await eventually(lambda:states and states[-1].connection_state=='CONNECTED')
        old=h.instances[0]
        disconnect=old.disconnect_websocket
        def blocked_disconnect():
            assert gate.wait(2)
            disconnect()
        old.disconnect_websocket=blocked_disconnect
        h.adapter._shutdown_timeout=.02
        old.ws_manager.ws.close()
        with pytest.raises(TimeoutError):
            await task
        assert h.adapter._info is old
        assert len(h.instances)==1
        assert not h.adapter._shutdown_task.done()
        gate.set()
        await h.adapter.stop()
        assert old.disconnects==1 and h.adapter._info is None
        assert not old.ws_manager.is_alive() and not old.ws_manager.ping_sender.is_alive()
    finally:
        gate.set()
        if not task.done():
            await h.adapter.stop()
        elif h.adapter._info is not None:
            await h.adapter.stop()
