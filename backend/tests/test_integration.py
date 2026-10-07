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


@pytest.fixture
def lifecycle_transports(monkeypatch):
    """Delay/fail real service lifecycle methods without opening sockets."""
    from app.references.service import ReferenceService
    calls = []
    created_markets = []
    created_references = []
    market_init = MarketDataService.__init__
    reference_init = ReferenceService.__init__

    def init_market(service, *args, **kwargs):
        market_init(service, *args, **kwargs)
        created_markets.append(service)

    def init_reference(service, *args, **kwargs):
        reference_init(service, *args, **kwargs)
        created_references.append(service)

    async def start(service):
        calls.append(("start", service))
        if getattr(service, "start_entered", None):
            service.start_entered.set()
            await service.start_release.wait()
        if getattr(service, "start_error", None):
            raise RuntimeError(service.start_error)

    async def stop(service):
        calls.append(("stop", service))
        if getattr(service, "stop_entered", None):
            service.stop_entered.set()
            await service.stop_release.wait()
        if getattr(service, "stop_error", None):
            raise RuntimeError(service.stop_error)

    monkeypatch.setattr(MarketDataService, "__init__", init_market)
    monkeypatch.setattr(ReferenceService, "__init__", init_reference)
    for cls in (MarketDataService, ReferenceService):
        monkeypatch.setattr(cls, "start", start)
        monkeypatch.setattr(cls, "stop", stop)
    return calls, created_markets, created_references


@pytest.mark.asyncio
async def test_config_lifecycles_serialize_captured_identities_and_publication(lifecycle_transports):
    calls, markets, refs = lifecycle_transports
    rt = HyperAmmRuntime(Settings(_env_file=None))
    original = rt.config
    old_market, old_ref = rt.market, rt.reference_service
    old_market.stop_entered = asyncio.Event()
    old_market.stop_release = asyncio.Event()
    first_config = original.model_copy(update={"market": "BTC"})
    second_config = original.model_copy(update={"market": "SOL"})
    first = asyncio.create_task(rt.update_config(first_config))
    await asyncio.wait_for(old_market.stop_entered.wait(), 1)
    first_market, first_ref = markets[-1], refs[-1]
    first_ref.start_entered = asyncio.Event()
    first_ref.start_release = asyncio.Event()
    second_entered = asyncio.Event()

    async def second_request():
        second_entered.set()
        await rt.update_config(second_config)

    second = asyncio.create_task(second_request())
    await asyncio.wait_for(second_entered.wait(), 1)
    assert len(markets) == len(refs) == 2
    assert calls == [("stop", old_market)]
    assert rt.config is original and rt.market is old_market and rt.reference_service is old_ref
    old_market.stop_release.set()
    await asyncio.wait_for(first_ref.start_entered.wait(), 1)
    assert rt.market is old_market and rt.config is original
    await rt.refresh_once()
    assert rt.authorization is None and not rt.quotes
    with pytest.raises(RuntimeError, match="in progress"):
        await rt._execution_authority()
    assert len(markets) == 2  # Second request has still not constructed a graph.
    first_ref.start_release.set()
    await asyncio.wait_for(asyncio.gather(first, second), 1)
    second_market, second_ref = markets[-1], refs[-1]
    assert calls == [("stop", old_market), ("stop", old_ref),
                     ("start", first_market), ("start", first_ref),
                     ("stop", first_market), ("stop", first_ref),
                     ("start", second_market), ("start", second_ref)]
    assert rt.market is second_market and rt.reference_service is second_ref
    assert rt.config is second_config and rt.lifecycle_state == "READY"
    assert ("stop", second_market) not in calls and ("stop", second_ref) not in calls


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["market_constructor", "perp_constructor", "reference_constructor",
                                      "accounting_constructor", "market_stop", "reference_stop",
                                      "market_start", "reference_start", "cleanup", "cancel_request"])
async def test_config_failure_is_latched_unpublished_and_cancellable(failure, lifecycle_transports, monkeypatch):
    import app.runtime as runtime_module
    calls, markets, refs = lifecycle_transports
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(2))
    await rt.refresh_once()
    rt.strategy.running = True
    old_config, old_market, old_ref = rt.config, rt.market, rt.reference_service
    old_paper, old_accounting = rt.paper, rt.accounting_service
    assert rt.authorization is not None
    if failure.endswith("constructor"):
        names = {"market_constructor": "MarketDataService", "perp_constructor": "PerpContextService",
                 "reference_constructor": "ReferenceService", "accounting_constructor": "AccountingService"}
        def broken(*args, **kwargs):
            raise RuntimeError("constructor failed")
        monkeypatch.setattr(runtime_module, names[failure], broken)
    if failure.endswith("stop"):
        setattr(old_market if failure == "market_stop" else old_ref, "stop_error", "old stop failed")
    old_market.stop_entered = asyncio.Event()
    old_market.stop_release = asyncio.Event()
    transition = asyncio.create_task(rt.update_config(old_config.model_copy(update={"market": "BTC"})))
    if not failure.endswith("constructor"):
        await asyncio.wait_for(old_market.stop_entered.wait(), 1)
        if failure in ("market_start", "reference_start", "cleanup"):
            target = markets[-1] if failure == "market_start" else refs[-1]
            target.start_error = "replacement start failed"
        if failure == "cleanup":
            markets[-1].stop_error = "replacement stop failed"
        if failure == "cancel_request":
            transition.cancel()
        old_market.stop_release.set()
    with pytest.raises((RuntimeError, asyncio.CancelledError)):
        await transition
    assert rt.lifecycle_state == "FAILED"
    assert rt.config is old_config and rt.strategy.config is old_config
    assert rt.market is old_market and rt.reference_service is old_ref
    assert rt.paper is old_paper and rt.accounting_service is old_accounting
    assert not rt.quotes and not rt.strategy_quotes and not rt.agent_quotes and rt.authorization is None
    assert "configuration lifecycle failed" in rt.strategy.last_error
    if failure == "reference_start":
        assert ("start", markets[-1]) in calls
    for service in markets[1:] + refs[1:]:
        assert ("stop", service) in calls
    if failure == "cleanup":
        assert "cleanup unconfirmed" in rt.lifecycle_error
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(3))
    await rt.refresh_once()
    assert not rt.quotes and rt.authorization is None
    with pytest.raises(RuntimeError, match="lifecycle failed"):
        await rt._execution_authority()
    with pytest.raises(RuntimeError, match="lifecycle failed"):
        await rt.start_strategy()
    with pytest.raises(RuntimeError, match="lifecycle failed"):
        await rt.update_config(old_config)
    await rt.orders.cancel_all()
    await rt.activate_kill()
    assert rt.risk.kill_switch_active and not rt.strategy.running
    await rt.resume()
    assert rt.lifecycle_state == "FAILED" and "lifecycle failed" in rt.strategy.last_error
    assert not rt.strategy.running


@pytest.mark.asyncio
@pytest.mark.parametrize("emergency", [False, True])
async def test_config_blocks_running_strategy_then_recovers_only_on_normal_evidence(emergency, lifecycle_transports, monkeypatch):
    from app.market_data.perp_context import demo_perp_context
    calls, markets, refs = lifecycle_transports
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(2))
    rt.strategy.running = True
    await rt.refresh_once()
    old_market, old_ref = rt.market, rt.reference_service
    old_market.stop_entered = asyncio.Event()
    old_market.stop_release = asyncio.Event()
    transition = asyncio.create_task(rt.update_config(rt.config.model_copy(update={"market": "BTC"})))
    await asyncio.wait_for(old_market.stop_entered.wait(), 1)
    before = rt.paper.fills.version
    async def no_reconcile(*args, **kwargs):
        pytest.fail("reconciled during lifecycle transition")
    with monkeypatch.context() as patch:
        patch.setattr(rt.orders, "reconcile", no_reconcile)
        # Run the actual enabled loop while transport shutdown is deliberately held.
        rt._strategy_task = asyncio.create_task(rt._loop())
        rt._strategy_wakeup.set()
        await asyncio.sleep(.02)
        await rt.refresh_once()
        await markets[-1]._accept(MockMarketDataAdapter("BTC").snapshot_for(2))
        await rt._on_perp_context(demo_perp_context(MockMarketDataAdapter().snapshot_for(2)), source=old_market)
        assert rt.perp_context is None or rt.perp_context.market == "ETH"
        assert rt.authorization is None and not rt.quotes and rt.paper.fills.version == before
        with pytest.raises(RuntimeError, match="in progress"):
            await rt.start_strategy()
        await asyncio.wait_for(rt.orders.cancel_all(), 1)
        if emergency:
            await asyncio.wait_for(rt.activate_kill(), 1)
        rt._strategy_task.cancel()
        try:
            await rt._strategy_task
        except asyncio.CancelledError:
            pass
        rt._strategy_task = None
        await markets[-1]._accept(MarketSnapshot.unavailable("BTC", MarketDataMode.DEMO, "no current evidence"))
    old_market.stop_release.set()
    await asyncio.wait_for(transition, 1)
    assert rt.authorization is None and not rt.quotes
    # Retired identities cannot add market history, perp/accounting evidence or wake.
    history_version = rt.market_history.version
    accounting_version = rt.accounting_service.version
    rt._strategy_wakeup.clear()
    old_snapshot = MockMarketDataAdapter().snapshot_for(4)
    await old_market._accept(old_snapshot)
    for listener in old_market._perp_listeners:
        await listener(demo_perp_context(old_snapshot))
    old_ref.redstone.on_update()
    assert not rt._strategy_wakeup.is_set()
    assert rt.market_history.version == history_version
    assert rt.accounting_service.version == accounting_version and rt.perp_context is None
    # Startup alone supplied no authority. Explicit replacement evidence can recover.
    await rt.market._accept(MockMarketDataAdapter("BTC").snapshot_for(3))
    await rt.refresh_once()
    if emergency:
        assert rt.risk.kill_switch_active and not rt.strategy.running
        assert rt.authorization is None and not await rt.paper.get_open_orders()
    else:
        assert rt.authorization.authorized and rt.strategy.quote_health == "HEALTHY"
        assert await rt.paper.get_open_orders()
        await rt._execution_authority()
    await rt.stop_strategy()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["execution", "feed", "market"])
async def test_config_context_rebind_preserves_session_isolation(change, lifecycle_transports):
    from app.strategy.models import ExecutionMode
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(2))
    await rt.refresh_once()
    original_paper = rt.paper
    original_accounting = rt.accounting_service
    original_telemetry = rt.agent_telemetry
    original_supervisor = rt.agent_supervisor
    changes = {"execution": {"execution_mode": ExecutionMode.TESTNET},
               "feed": {"market_data_mode": MarketDataMode.LIVE},
               "market": {"market": "BTC"}}
    await rt.update_config(rt.config.model_copy(update=changes[change]))
    assert rt.paper is not original_paper and rt.paper.fills.all() == []
    assert rt.accounting_service is not original_accounting
    assert rt.accounting_service.ledger.version == 0
    assert rt.accounting_service.market == rt.config.market
    assert rt.accounting_service.mode == rt.config.execution_mode.value
    assert rt.agent_telemetry is not original_telemetry
    assert rt.agent_supervisor is not original_supervisor
    assert rt.authorization is None
    assert rt._expected_accounting_version is None and rt._expected_accounting_fingerprint is None
    assert rt.orders.execution is rt.execution
    # Retired PAPER fills cannot contaminate the new accounting session.
    original_paper.on_fill(None)
    assert rt.accounting_service.ledger.version == 0
    if change == "execution":
        assert rt.accounting_service.snapshot().equity_quote is None
        await rt.update_config(rt.config.model_copy(update={"execution_mode": ExecutionMode.PAPER}))
        assert rt.paper.fills.all() == [] and rt.accounting_service.position.position_base == 0
        assert rt.accounting_service.mode == "PAPER"


@pytest.mark.asyncio
async def test_config_cancellation_failure_halts_before_staging(lifecycle_transports, monkeypatch):
    calls, markets, refs = lifecycle_transports
    rt = HyperAmmRuntime(Settings(_env_file=None))
    old_config = rt.config
    async def unconfirmed():
        raise RuntimeError("venue cancellation failed")
    monkeypatch.setattr(rt.execution, "cancel_all", unconfirmed)
    with pytest.raises(RuntimeError, match="venue cancellation failed"):
        await rt.update_config(old_config.model_copy(update={"market": "BTC"}))
    assert len(markets) == len(refs) == 1 and not calls
    assert rt.config is old_config and rt.lifecycle_state == "FAILED"
    assert rt.risk.kill_switch_active and rt.strategy.quote_health == "HALTED"
    assert not rt.quotes and rt.authorization is None


@pytest.mark.asyncio
async def test_failed_replacement_cleanup_is_retried_at_runtime_shutdown(lifecycle_transports):
    calls, markets, refs = lifecycle_transports
    rt = HyperAmmRuntime(Settings(_env_file=None))
    old_market = rt.market
    old_market.stop_entered = asyncio.Event()
    old_market.stop_release = asyncio.Event()
    transition = asyncio.create_task(rt.update_config(rt.config.model_copy(update={"market": "BTC"})))
    await asyncio.wait_for(old_market.stop_entered.wait(), 1)
    markets[-1].stop_error = "cleanup failed"
    refs[-1].start_error = "reference start failed"
    old_market.stop_release.set()
    with pytest.raises(RuntimeError, match="reference start failed"):
        await transition
    assert rt.lifecycle_state == "FAILED"
    markets[-1].stop_error = None
    await rt.stop_services()
    assert calls.count(("stop", markets[-1])) == 2
    assert calls.count(("stop", refs[-1])) == 2


@pytest.mark.asyncio
async def test_initial_service_start_failure_also_blocks_authority(lifecycle_transports):
    rt = HyperAmmRuntime(Settings(_env_file=None))
    rt.reference_service.start_error = "initial reference startup failed"
    with pytest.raises(RuntimeError, match="initial reference startup failed"):
        await rt.start_services()
    assert rt.lifecycle_state == "FAILED" and rt.authorization is None
    assert "runtime service startup failed" in rt.strategy.last_error
    with pytest.raises(RuntimeError, match="runtime service startup failed"):
        await rt.start_strategy()
    await rt.stop_services()
