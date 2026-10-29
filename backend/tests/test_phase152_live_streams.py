"""Deterministic callbacks, SDK compatibility and owned recovery/cleanup."""
import asyncio
import copy
import json
import threading
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.config import Settings
from app.market_data.live_streams import LiveMarketStreamService, SDKObservationClient, MAX_WIRE_BYTES, SUBSCRIBER_QUEUE_CAPACITY
from app.market_data.live_stream_models import LiveMarketStreamEnvelope
from test_phase151_live_markets import NOW, Clock, native, book, contexts
from app.simulation.market_profiles import MARKETS

async def eventually(condition, timeout=2):
    async with asyncio.timeout(timeout):
        while not condition(): await asyncio.sleep(.005)

class FakeClients:
    def __init__(self, clock):
        self.clock=clock; self.clients=[]; self.metadata=native()
        self.books={m:book(m) for m in MARKETS}; self.contexts=contexts()
        self.error=self.context_error=self.subscription_error=None
        self.open_gate=self.close_gate=None; self.started=threading.Event(); self.close_error=False
    def factory(self, timeout, shutdown_timeout):
        owner=self
        class Client:
            def __init__(self):
                self.callbacks={}; self.handles=[]; self.closed=self.broken=False; self.book_calls=[]
            def open(self):
                owner.started.set()
                if owner.open_gate: owner.open_gate.wait(2)
                if owner.error: raise owner.error
                return copy.deepcopy(owner.metadata),owner.clock()
            def ready(self):
                if self.broken: raise ConnectionError('private-fixture-value')
                return not self.closed
            def subscribe(self, market, kind, callback):
                if owner.subscription_error: raise owner.subscription_error
                self.callbacks[(market,kind)]=callback; self.handles.append((market,kind)); return len(self.handles)
            def book(self,market):
                self.book_calls.append(market); return copy.deepcopy(owner.books[market]),owner.clock()
            def context(self):
                if owner.context_error: raise owner.context_error
                return copy.deepcopy(owner.contexts),owner.clock()
            def close(self):
                if owner.close_gate: owner.close_gate.wait(2)
                if owner.close_error: raise RuntimeError('secret-cleanup')
                self.closed=True
        client=Client();self.clients.append(client);return client
    def ctx(self,market):
        index=next(i for i,x in enumerate(native()['universe']) if x['name']==market)
        return {'channel':'activeAssetCtx','data':{'coin':market,'ctx':copy.deepcopy(self.contexts[1][index])}}
    def emit(self,market,kind,raw=None,client=None):
        (client or self.clients[-1]).callbacks[(market,kind)](raw if raw is not None else self.ctx(market)
            if kind=='activeAssetCtx' else {'channel':'l2Book','data':copy.deepcopy(self.books[market])})

def create(**options):
    clock=Clock();sdk=FakeClients(clock)
    service=LiveMarketStreamService(Settings(_env_file=None,live_observations_enabled=True,live_streams_enabled=True,
        live_stream_reconnect_initial_seconds=.01,live_stream_reconnect_max_seconds=.04,**options),
        client_factory=sdk.factory,clock=clock)
    return service,sdk,clock

@pytest.fixture
async def streams():
    service,sdk,clock=create(); await service.start()
    await eventually(lambda:all(x.barrier and x.context for x in service.states.values()))
    yield service,sdk,clock
    await service.close()

@pytest.mark.parametrize('market',MARKETS)
async def test_independent_bootstrap_and_native_channels(streams,market):
    service,sdk,_=streams
    assert len(sdk.clients)==1 and set(sdk.clients[0].handles)=={(m,k) for m in MARKETS for k in ('l2Book','activeAssetCtx')}
    initial=service.snapshot(market)
    assert initial.status.connection_state=='BOOTSTRAPPING' and initial.observation_status!='AVAILABLE'
    assert initial.order_book.source==initial.perp_context.source=='OFFICIAL_SDK_REST'
    others={m:service.snapshot(m) for m in MARKETS if m!=market}
    sdk.emit(market,'l2Book');sdk.emit(market,'activeAssetCtx')
    await eventually(lambda:service.snapshot(market).observation_status=='AVAILABLE')
    result=service.snapshot(market)
    assert result.perp_context.source_timestamp is None and result.status.perp_event_time=='UNKNOWN'
    assert result.status.subscription_state=='OBSERVED' and result.metadata.asset_index=={'BTC':2,'ETH':3,'SOL':1}[market]
    assert all(service.snapshot(m)==v for m,v in others.items())
    assert result.order_book.source=='OFFICIAL_SDK_REST' and result.perp_context.source=='OFFICIAL_SDK_WEBSOCKET'

async def test_acknowledgement_never_establishes_data(streams):
    service,sdk,_=streams;sdk.emit('BTC','activeAssetCtx',{'channel':'subscriptionResponse','data':{}})
    await asyncio.sleep(.02)
    assert service.snapshot('BTC').observation_status!='AVAILABLE' and service.states['BTC'].rejected==0

@pytest.mark.parametrize('change',['older','conflict','wrong_coin','missing_time','future','crossed','unordered',
    'duplicate','precision','negative_size','float','bool_time','depth','same'])
async def test_l2_integrity_replay_and_duplicate_history(streams,change):
    service,sdk,clock=streams;raw=copy.deepcopy(sdk.books['BTC']);before=service.history.query('BTC')
    if change=='older':raw['time']-=1
    elif change=='conflict':raw['levels'][0][0]['sz']='2'
    elif change=='wrong_coin':raw['coin']='ETH'
    elif change=='missing_time':raw.pop('time')
    elif change=='future':raw['time']+=2000
    elif change=='crossed':raw['levels'][1][0]['px']='59999'
    elif change=='unordered':raw['levels'][0].append({'px':'60001','sz':'1'})
    elif change=='duplicate':raw['levels'][0]*=2
    elif change=='precision':raw['levels'][0][0]['sz']='.000001'
    elif change=='negative_size':raw['levels'][0][0]['sz']='-1'
    elif change=='float':raw['levels'][0][0]['px']=60000.0
    elif change=='bool_time':raw['time']=True
    elif change=='depth':raw['levels'][0]*=101
    other=service.snapshot('ETH')
    assert not service.accept('BTC','l2Book',raw,service.states['BTC'].generation,clock())
    assert service.history.query('BTC').retained_point_count==before.retained_point_count
    assert service.snapshot('ETH')==other
    assert service.states['BTC'].rejected==(0 if change=='same' else 1)

async def test_conflicting_full_depth_beyond_returned_levels(streams):
    service,_,clock=streams;raw=book('BTC');raw['time']+=1
    raw['levels'][0]=[{'px':str(60000-i),'sz':'1'} for i in range(25)]
    assert service.accept('BTC','l2Book',raw,1,clock())
    raw['levels'][0][-1]['sz']='2'
    assert not service.accept('BTC','l2Book',raw,1,clock()) and service.states['BTC'].error=='CONFLICT'

@pytest.mark.parametrize('market',MARKETS)
@pytest.mark.parametrize('field,value',[('markPx','0'),('oraclePx','NaN'),('funding',True),('openInterest','-1'),('midPx',''),('premium',.1)])
async def test_context_validation_and_no_cross_market_writes(streams,market,field,value):
    service,sdk,clock=streams;raw=sdk.ctx(market);raw['data']['ctx'][field]=value
    others={m:service.snapshot(m) for m in MARKETS if m!=market}
    retained=service.snapshot(market).perp_context
    assert not service.accept(market,'activeAssetCtx',raw,1,clock())
    assert service.snapshot(market).perp_context == retained
    assert service.snapshot(market).observation_status == 'DEGRADED'
    assert service.states[market].rejected == 1 and 'activeAssetCtx' not in service.states[market].seen
    assert all(service.snapshot(m)==v for m,v in others.items())

async def test_context_wrong_symbol_and_reused_basis(streams):
    service,sdk,clock=streams;raw=sdk.ctx('BTC');raw['data']['coin']='ETH'
    assert not service.accept('BTC','activeAssetCtx',raw,1,clock())
    raw=sdk.ctx('BTC');raw['data']['ctx'].update(markPx='101',oraclePx='100',openInterest='3');raw['data']['ctx'].pop('midPx')
    assert service.accept('BTC','activeAssetCtx',raw,1,clock())
    ctx=service.snapshot('BTC').perp_context
    assert ctx.open_interest_notional==303 and ctx.mark_oracle_basis_bps==100
    assert ctx.provider_mid_price is ctx.mark_mid_basis_bps is ctx.oracle_mid_basis_bps is ctx.source_timestamp is None

@pytest.mark.parametrize('component',['l2','perp'])
async def test_independent_freshness_and_no_poll_samples(streams,component):
    service,sdk,clock=streams;sdk.emit('BTC','l2Book');sdk.emit('BTC','activeAssetCtx')
    await eventually(lambda:service.snapshot('BTC').observation_status=='AVAILABLE');clock.advance(31)
    if component=='l2':
        raw=book('BTC');raw['time']=int(clock().timestamp()*1000);service.accept('BTC','l2Book',raw,1,clock())
    else:service.accept('BTC','activeAssetCtx',sdk.ctx('BTC'),1,clock())
    status=service.snapshot('BTC').status
    assert (status.l2_freshness,status.perp_freshness)==(('FRESH','STALE') if component=='l2' else ('STALE','FRESH'))
    count=service.history.query('BTC').retained_point_count
    for _ in range(10):service.snapshot('BTC');service.publish('BTC')
    assert service.history.query('BTC').retained_point_count==count

async def test_bounded_history_eviction_nullable_components_and_restart(streams):
    service,_,clock=streams
    for i in range(1010):
        clock.advance(.001);raw=book('SOL');raw['time']=int(clock().timestamp()*1000)
        service.accept('SOL','l2Book',raw,1,clock())
    history=service.history.query('SOL',1000)
    assert history.retained_point_count==1000 and history.evicted_point_count>0 and len(history.points)==1000
    assert not history.continuous_history_verified and all(p.mark is p.oracle is p.funding is None for p in history.points)
    other,_,_=create()
    try:assert other.history.query('SOL').retained_point_count==0 and other.instance_id!=service.instance_id
    finally:await other.close()

async def test_thread_ingress_bound_and_snapshot_recovery(streams):
    service,sdk,_=streams;inbox=service._inbox
    def burst():
        for _ in range(service.queue_capacity+10):sdk.emit('BTC','l2Book')
    thread=threading.Thread(target=burst);thread.start();thread.join()
    assert len(inbox.queues['BTC'])==service.queue_capacity and inbox.scheduled and inbox.dropped['BTC']==10
    assert not inbox.queues['ETH'] and not inbox.queues['SOL']
    await eventually(lambda:service.states['BTC'].dropped>=10)
    assert service.history.query('BTC').gap_count>0 and sdk.clients[0].book_calls.count('BTC')>=2

async def test_oversized_callback_is_accounted_as_loss(streams):
    service,sdk,_=streams;sdk.emit('BTC','l2Book',{'data':'x'*MAX_WIRE_BYTES})
    await eventually(lambda:service.states['BTC'].dropped==1)
    assert service.history.query('BTC').gap_count>0

async def test_reconnect_retirement_and_old_callback_ignored(streams):
    service,sdk,_=streams;old=sdk.clients[0];old.broken=True
    await eventually(lambda:len(sdk.clients)>=2 and all(x.barrier and x.context for x in service.states.values()))
    assert old.closed and all(x.generation==2 for x in service.states.values())
    before=service.snapshot('BTC');sdk.emit('BTC','activeAssetCtx',client=old)
    assert service.snapshot('BTC')==before and service.states['BTC'].reconnects==1
    assert sdk.clients[1].book_calls==list(MARKETS)

async def test_subscriber_capacity_overflow_sequence_and_shutdown(streams):
    service,_,_=streams;queues=[service.subscribe('BTC') for _ in range(service.max_subscribers)]
    with pytest.raises(RuntimeError):service.subscribe('ETH')
    initial=LiveMarketStreamEnvelope.model_validate_json(queues[0].get_nowait())
    assert initial.market=='BTC' and initial.observation_status!='AVAILABLE'
    for _ in range(SUBSCRIBER_QUEUE_CAPACITY+1):service.publish('BTC')
    assert queues[0].get_nowait() is None and len(service._subscribers)==service.max_subscribers
    with pytest.raises(RuntimeError):service.subscribe('ETH')
    for q in queues:service.unsubscribe(q)
    assert not service._subscribers
    queue=service.subscribe('BTC');latest=LiveMarketStreamEnvelope.model_validate_json(queue.get_nowait())
    assert latest.sequence>initial.sequence and latest.observer_instance_id==service.instance_id
    closing=asyncio.create_task(service.close())
    await eventually(lambda:service._closed)
    assert queue.get_nowait() is None
    service.unsubscribe(queue);await closing
    assert service.snapshot('BTC').status.connection_state=='STOPPED'
    assert all(not t.is_alive() for t in service._pool._threads)

@pytest.mark.parametrize('market',['btc','BTC-PERP','DOGE','xyz:BTC','@1',None,[],['BTC','ETH']])
async def test_unsupported_selection_never_allocates_sdk(market):
    service,sdk,_=create()
    try:
        with pytest.raises(ValueError):service.snapshot(market)
        with pytest.raises(ValueError):service.subscribe(market)
        assert not sdk.clients
    finally:await service.close()

@pytest.mark.parametrize('option,value',[('live_stream_max_subscribers',True),('live_stream_queue_capacity',0),
    ('live_stream_queue_capacity',1025),('live_stream_history_max_points',3601),('live_stream_perp_stale_after_seconds',float('nan')),
    ('live_stream_connect_timeout_seconds',0),('live_stream_reconnect_initial_seconds',40),('live_stream_shutdown_timeout_seconds',121)])
def test_invalid_stream_settings(option,value):
    with pytest.raises(ValidationError):Settings(_env_file=None,**{option:value})

def test_stream_settings_dependency_and_environment_numbers():
    with pytest.raises(ValidationError):Settings(_env_file=None,live_streams_enabled=True)
    assert Settings(_env_file=None,live_stream_queue_capacity='1024').live_stream_queue_capacity==1024

async def test_disabled_lifecycle_opens_no_client():
    service=LiveMarketStreamService(Settings(_env_file=None),client_factory=lambda *_:pytest.fail('network'))
    await service.start();assert all(service.snapshot(m).status.connection_state=='DISABLED' for m in MARKETS)
    with pytest.raises(RuntimeError):service.subscribe('BTC')
    await service.close()

async def test_shutdown_during_initialization_retains_worker():
    service,sdk,_=create(live_stream_shutdown_timeout_seconds=.02);sdk.open_gate=threading.Event()
    await service.start();assert await asyncio.to_thread(sdk.started.wait,1)
    with pytest.raises(RuntimeError,match='still draining'):await service.close()
    assert not service._close_task.done() and not sdk.clients[0].closed
    closing=asyncio.create_task(service.close());closing.cancel()
    with pytest.raises(asyncio.CancelledError):await closing
    sdk.open_gate.set();service.shutdown_timeout=2;await service.close()
    assert sdk.clients[0].closed and not sdk.clients[0].handles and all(not t.is_alive() for t in service._pool._threads)

@pytest.mark.parametrize('failure',['open','subscribe','context'])
async def test_partial_failure_fixed_errors_and_recovery(failure):
    service,sdk,_=create()
    if failure=='open':sdk.error=ValueError('private-fixture-value')
    elif failure=='subscribe':sdk.subscription_error=ValueError('private-fixture-value')
    else:sdk.context_error=ValueError('private-fixture-value')
    await service.start()
    if failure=='context':
        await eventually(lambda:all(x.book for x in service.states.values()))
        for m in MARKETS:sdk.emit(m,'l2Book');sdk.emit(m,'activeAssetCtx')
        await eventually(lambda:all(service.snapshot(m).observation_status=='AVAILABLE' for m in MARKETS))
    else:
        await eventually(lambda:any(c.closed for c in sdk.clients));sdk.error=sdk.subscription_error=None
        await eventually(lambda:all(x.barrier and x.context for x in service.states.values()))
    assert 'private-fixture-value' not in service.snapshot('BTC').model_dump_json()
    await service.close();assert all(c.closed for c in sdk.clients)

async def test_cleanup_failure_stops_replacement_and_shutdown_retries():
    service,sdk,_=create();await service.start();await eventually(lambda:all(x.barrier for x in service.states.values()))
    sdk.close_error=True;sdk.clients[0].broken=True
    await eventually(lambda:service.states['BTC'].error=='CLEANUP_ERROR');assert len(sdk.clients)==1
    with pytest.raises(RuntimeError):await service.close()
    sdk.close_error=False;await service.close()
    assert sdk.clients[0].closed and all(not t.is_alive() for t in service._pool._threads)

@pytest.mark.parametrize('market',MARKETS)
async def test_missing_native_listing_never_subscribes(market):
    service,sdk,_=create();sdk.metadata['universe']=[x for x in sdk.metadata['universe'] if x['name']!=market]
    await service.start();await eventually(lambda:service.states[market].error=='NOT_LISTED')
    assert all(m!=market for m,_ in sdk.clients[0].handles) and service.snapshot(market).order_book is None
    await service.close()

async def test_actual_official_sdk_delivery_and_thread_cleanup(monkeypatch):
    import requests
    import hyperliquid.websocket_manager as wsmod
    import app.market_data.live_streams as mod
    sessions,sockets,owners=[],[],[]
    class Session:
        def __init__(self):self.headers={};self.closed=False;sessions.append(self)
        def post(self,url,json,timeout):
            raw=native() if json['type']=='meta' else book(json['coin']) if json['type']=='l2Book' else contexts()
            return SimpleNamespace(status_code=200,json=lambda:raw)
        def close(self):self.closed=True
    class Socket:
        def __init__(self,url,on_message,on_open):
            self.on_open=on_open;self.keep_running=True;self.sock=SimpleNamespace(connected=False)
            self.closed=threading.Event();self.sent=[];sockets.append(self)
        def run_forever(self):self.sock.connected=True;self.on_open(self);self.closed.wait(2)
        def send(self,wire):self.sent.append(json.loads(wire))
        def close(self):self.keep_running=False;self.sock.connected=False;self.closed.set()
    monkeypatch.setattr(requests,'Session',Session);monkeypatch.setattr(wsmod.websocket,'WebSocketApp',Socket)
    monkeypatch.setattr(mod,'utcnow',lambda:NOW)
    def factory(*args):client=SDKObservationClient(*args);owners.append(client);return client
    service=LiveMarketStreamService(Settings(_env_file=None,live_observations_enabled=True,live_streams_enabled=True),client_factory=factory,clock=lambda:NOW)
    await service.start();await eventually(lambda:all(x.barrier and x.context for x in service.states.values()))
    manager=owners[0].info.ws_manager;assert manager.is_alive() and manager.ping_sender.is_alive()
    for market in MARKETS:
        manager.on_message(None,json.dumps({'channel':'l2Book','data':book(market)}))
        i=next(i for i,x in enumerate(native()['universe']) if x['name']==market)
        manager.on_message(None,json.dumps({'channel':'activeAssetCtx','data':{'coin':market,'ctx':contexts()[1][i]}}))
    await eventually(lambda:all(service.snapshot(m).observation_status=='AVAILABLE' for m in MARKETS));await service.close()
    methods=[x['method'] for x in sockets[0].sent]
    assert methods.count('subscribe')==methods.count('unsubscribe')==6
    assert all(s.closed for s in sessions) and not manager.is_alive() and not manager.ping_sender.is_alive()

@pytest.mark.parametrize('failure',['metadata','sdk_constructor','socket_connect','rate_limit'])
async def test_bounded_failure_reconnect_and_shutdown(failure):
    from hyperliquid.utils.error import ClientError
    service,sdk,_=create(live_stream_connect_timeout_seconds=.02)
    if failure=='metadata':sdk.metadata={'universe':[{'name':'BTC','szDecimals':True}]}
    elif failure=='sdk_constructor':sdk.error=RuntimeError('sensitive-initialization')
    elif failure=='rate_limit':sdk.error=ClientError(429,'fixture','sensitive-rate',{},None)
    else:
        original=sdk.factory
        def factory(*args):
            client=original(*args);client.ready=lambda:False;return client
        service._factory=factory
    await service.start();await eventually(lambda:any(c.closed for c in sdk.clients))
    assert 'sensitive' not in service.snapshot('BTC').model_dump_json()
    if failure=='rate_limit':
        await asyncio.sleep(.03);assert len(sdk.clients)==1  # 30s cooldown, interrupted by shutdown.
    await service.close();assert all(c.closed for c in sdk.clients)

async def test_buffered_context_older_receipt_cannot_overwrite_later_context(streams):
    from datetime import timedelta
    service,sdk,clock=streams;before=service.snapshot('BTC').perp_context
    raw=sdk.ctx('BTC');raw['data']['ctx']['markPx']='61000'
    assert not service.accept('BTC','activeAssetCtx',raw,1,clock()-timedelta(seconds=1))
    assert service.snapshot('BTC').perp_context==before

async def test_stale_recovery_snapshot_does_not_restore_watermark(streams):
    service,_,clock=streams;clock.advance(11)
    service.states['BTC'].book=None;service.states['BTC'].barrier=False
    with pytest.raises(ValueError):await service._bootstrap_book('BTC')
    assert service.states['BTC'].book is None and not service.states['BTC'].barrier

async def test_retired_generation_does_not_change_counters_or_history(streams):
    service,sdk,clock=streams;before=service.snapshot('BTC');history=service.history.query('BTC')
    assert not service.accept('BTC','activeAssetCtx',sdk.ctx('BTC'),0,clock())
    assert service.snapshot('BTC')==before and service.history.query('BTC')==history

async def test_sdk_partial_constructor_owns_both_threads_and_session(monkeypatch):
    import requests
    import hyperliquid.websocket_manager as wsmod
    from hyperliquid.info import Info
    import app.market_data.live_streams as mod
    sessions=[]
    class Session:
        def __init__(self):self.headers={};self.closed=False;sessions.append(self)
        def post(self,*args,**kwargs):return SimpleNamespace(status_code=200,json=native)
        def close(self):self.closed=True
    class Socket:
        def __init__(self,*args,**kwargs):self.keep_running=True;self.closed=threading.Event()
        def run_forever(self):self.closed.wait(2)
        def close(self):self.keep_running=False;self.closed.set()
    original=Info.set_perp_meta
    def fail(self,meta,*args):
        if meta['universe']:raise ValueError('sensitive-after-thread-start')
        return original(self,meta,*args)
    monkeypatch.setattr(requests,'Session',Session);monkeypatch.setattr(wsmod.websocket,'WebSocketApp',Socket)
    monkeypatch.setattr(Info,'set_perp_meta',fail);monkeypatch.setattr(mod,'utcnow',lambda:NOW)
    client=SDKObservationClient(1,1)
    with pytest.raises(ValueError):await asyncio.to_thread(client.open)
    manager=client.info.ws_manager
    await asyncio.to_thread(client.close)
    assert not manager.is_alive() and not manager.ping_sender.is_alive() and all(s.closed for s in sessions)

async def test_bounded_burst_preserves_history_without_flooding_fast_browser(streams):
    service,sdk,_=streams
    queue=service.subscribe('BTC');queue.get_nowait()
    before=service.history.query('BTC').retained_point_count
    for i in range(service.queue_capacity):
        raw=book('BTC');raw['time']+=i+1;sdk.emit('BTC','l2Book',{'data':raw})
    await eventually(lambda:service.history.query('BTC').retained_point_count==before+service.queue_capacity)
    assert service.states['BTC'].dropped==0 and queue not in service._slow_subscribers
    frames=[]
    while not queue.empty():frames.append(LiveMarketStreamEnvelope.model_validate_json(queue.get_nowait()))
    assert frames and frames[-1].payload.order_book.source=='OFFICIAL_SDK_WEBSOCKET'
    service.unsubscribe(queue)

async def test_context_loss_requires_new_context_before_available(streams):
    service,sdk,_=streams;sdk.emit('BTC','l2Book');sdk.emit('BTC','activeAssetCtx')
    await eventually(lambda:service.snapshot('BTC').observation_status=='AVAILABLE')
    for _ in range(service.queue_capacity+1):sdk.emit('BTC','l2Book')
    await eventually(lambda:service.states['BTC'].dropped==1 and service.states['BTC'].book is not None)
    assert service.snapshot('BTC').perp_context is None and service.snapshot('BTC').observation_status!='AVAILABLE'
    sdk.emit('BTC','activeAssetCtx');sdk.emit('BTC','l2Book')
    await eventually(lambda:service.snapshot('BTC').observation_status=='AVAILABLE')
