"""Phase 8.3.1 source-time, security and real PAPER authority boundaries."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import json
import httpx
import pytest
from app.config import Settings
from app.market_data.mock import MockMarketDataAdapter
from app.references.consensus import MATERIAL_PROVIDERS
from app.references.models import ProviderId, ProviderStatus, SourceType, utcnow
from app.references.providers import EvidenceState
from app.risk.authorization import fingerprint
from app.runtime import HyperAmmRuntime
from test_phase8_provider_observations import frame, gecko, yahoo


def test_yahoo_source_time_price_version_and_recovery_contract():
    t=utcnow().replace(microsecond=0); p=yahoo()
    assert p.ingest(frame(t),t)
    version=p.state.version
    for offset,price in [(0,'3000'),(0,'3001'),(-1,'3002')]:
        assert p.ingest(frame(t,price,offset),t+timedelta(seconds=1)) is False
        assert p.state.version==version
        assert p.state.latest.price==D('3000') and p.state.latest.source_timestamp==t
    newer=t+timedelta(seconds=1)
    assert p.ingest(frame(newer),newer) is False
    assert p.state.version==version and p.state.latest.source_timestamp==newer
    assert p.state.snapshot(newer).age_ms==0
    # Zero deadband accepts every actual change, without fake movement for freshness.
    assert p.ingest(frame(t,'3000.000001',2),t+timedelta(seconds=2))
    assert p.state.version==version+1 and p.state.latest.price==D('3000.000001')
    stale_at=t+timedelta(seconds=33)
    assert p.state.snapshot(stale_at).status==ProviderStatus.STALE
    with pytest.raises(ValueError):p.ingest(frame(t,'3000.000001',2),stale_at)
    assert p.state.latest.source_timestamp==t+timedelta(seconds=2)
    p.state.set_status(ProviderStatus.DEGRADED,'disconnected')
    degraded_version=p.state.version
    assert not p.ingest(frame(t,'3000.000001',2),t+timedelta(seconds=3))
    assert p.state.snapshot(t+timedelta(seconds=3)).status==ProviderStatus.DEGRADED
    assert p.state.version==degraded_version
    assert not p.ingest(frame(stale_at,'3000.000001'),stale_at)
    assert p.state.latest.source_timestamp==stale_at and p.state.snapshot(stale_at).healthy
    assert p.state.version==degraded_version+1  # health recovery, not price movement
    next_at=stale_at+timedelta(seconds=31)
    assert p.state.snapshot(next_at).stale
    recovered_version=p.state.version
    assert not p.ingest(frame(next_at,'3000.000001'),next_at)
    assert p.state.snapshot(next_at).healthy and p.state.version==recovered_version


@pytest.mark.parametrize('provider,threshold',[(ProviderId.REDSTONE,D('.25')),(ProviderId.KRAKEN,D('.25')),(ProviderId.COINGECKO,D('1'))])
def test_shared_material_deadband_and_timestamp_behavior_remains(provider,threshold):
    t=utcnow()
    state=EvidenceState('ETH',provider,SourceType.ORACLE,'fixture',30,True,material_change_bps=threshold)
    state.accept(D('3000'),t,t); version=state.version
    assert not state.accept(D('3000'),t+timedelta(seconds=1),t+timedelta(seconds=1))
    assert state.version==version and state.latest.source_timestamp==t+timedelta(seconds=1)
    assert not state.accept(D('3000.001'),t+timedelta(seconds=2),t+timedelta(seconds=2))
    assert state.latest.price==D('3000') and state.latest.source_timestamp==t+timedelta(seconds=1)
    assert state.accept(D('3001'),t+timedelta(seconds=3),t+timedelta(seconds=3))
    assert state.version==version+1


@pytest.mark.asyncio
@pytest.mark.parametrize('pro',[False,True])
async def test_coingecko_real_httpx_query_redirect_and_redaction(pro,caplog):
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(302,headers={'location':'https://untrusted.example/steal'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond),follow_redirects=False) as client:
        p=gecko(client=client,api_base_url='https://pro-api.coingecko.com/api/v3' if pro else 'https://api.coingecko.com/api/v3')
        await p.poll_once()
        assert len(calls)==1
        request=calls[0]
        assert request.url.path=='/api/v3/simple/price'
        assert dict(request.url.params)==dict(ids='ethereum',vs_currencies='usd',include_last_updated_at='true',precision='full')
        assert request.headers['x-cg-pro-api-key' if pro else 'x-cg-demo-api-key']=='demo-secret'
        assert p.snapshot().status==ProviderStatus.DEGRADED
        assert 'demo-secret' not in p.snapshot().model_dump_json()+caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['network','decode','stale'])
async def test_coingecko_transient_errors_and_source_staleness(failure):
    def respond(request):
        if failure=='network':raise httpx.ConnectError('demo-secret',request=request)
        if failure=='decode':return httpx.Response(200,text='demo-secret invalid JSON')
        return httpx.Response(200,json={'ethereum':{'usd':3000,'last_updated_at':int((utcnow()-timedelta(seconds=91)).timestamp())}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        p=gecko(client=client)
        assert await p.poll_once()
        assert p.snapshot().status==(ProviderStatus.STALE if failure=='stale' else ProviderStatus.DEGRADED)
        assert 'demo-secret' not in p.snapshot().model_dump_json()


def freeze_clock(monkeypatch):
    # Freeze shared clocks, including Pydantic factories and PAPER/accounting defaults.
    import app.market_data.models as market_models
    import app.references.models as reference_models
    import app.market_data.service as market_service
    import app.market_data.perp_context as perp_service
    at=datetime(2026,10,9,1,tzinfo=timezone.utc)
    class FixedDatetime(datetime):
        @classmethod
        def now(cls,tz=None):return at if tz else at.replace(tzinfo=None)
    monkeypatch.setattr(market_models,'datetime',FixedDatetime)
    monkeypatch.setattr(reference_models,'datetime',FixedDatetime)
    monkeypatch.setattr(market_service,'datetime',FixedDatetime)
    monkeypatch.setattr(perp_service,'datetime',FixedDatetime)
    return at


CONDITIONS=['DISABLED','HEALTHY','DEGRADED','STALE','ERROR','UNAVAILABLE','OUTLIER +50%','OUTLIER -50%','REPLAYED TIMESTAMP','RECOVERED CONNECTION']


def vary_yahoo(p,condition,at):
    if condition=='DISABLED':p.state.enabled=False
    elif condition=='UNAVAILABLE':pass  # enabled without accepted data
    else:
        price='4500' if condition=='OUTLIER +50%' else '1500' if condition=='OUTLIER -50%' else '3000'
        source=at-timedelta(seconds=31) if condition=='STALE' else at-timedelta(seconds=1) if condition=='RECOVERED CONNECTION' else at
        p.ingest(frame(source,price),source)
        if condition in ('DEGRADED','ERROR'):p.state.set_status(ProviderStatus(condition),'fixture connection failure')
        elif condition=='REPLAYED TIMESTAMP':
            version=p.state.version
            assert not p.ingest(frame(source,'9000'),at)
            assert p.state.version==version and p.state.latest.price==D(price)
        elif condition=='RECOVERED CONNECTION':
            p.state.set_status(ProviderStatus.DEGRADED,'reconnecting')
            assert not p.ingest(frame(at,price),at)
            assert p.snapshot().healthy
    return p


@pytest.mark.asyncio
@pytest.mark.parametrize('condition',CONDITIONS)
@pytest.mark.parametrize('kill',[False,True])
async def test_yahoo_variation_cannot_change_real_runtime_authority(monkeypatch,condition,kill):
    at=freeze_clock(monkeypatch)
    baseline=HyperAmmRuntime(Settings(_env_file=None))
    variant=HyperAmmRuntime(Settings(_env_file=None,yfinance_reference_enabled=True,coingecko_api_key='fixture-secret'))
    vary_yahoo(variant.reference_service.yahoo,condition,at)
    for rt in (baseline,variant):
        # Material market/perp/reference inputs and clocks are identical.
        await rt.market._accept(MockMarketDataAdapter().snapshot_for(4))
        await rt.refresh_once()
        assert rt.references is not None, rt.strategy.last_error
    observation=variant.reference_service.observations(variant.references)
    assert observation['authority']=='NONE'
    obs=observation['observations'][0]
    expected='HEALTHY' if condition in ('HEALTHY','OUTLIER +50%','OUTLIER -50%','REPLAYED TIMESTAMP','RECOVERED CONNECTION') else 'DEGRADED' if condition=='UNAVAILABLE' else condition
    assert obs['status']==expected and obs['authority']=='NONE'
    assert variant.references.model_dump()==baseline.references.model_dump()
    assert set(variant.references.evidence)=={p.value for p in MATERIAL_PROVIDERS}
    assert fingerprint(variant.references)==fingerprint(baseline.references)
    assert variant.agent_decision.model_dump()==baseline.agent_decision.model_dump()
    assert variant.risk_decision.model_dump()==baseline.risk_decision.model_dump()
    assert variant.authorization.model_dump()==baseline.authorization.model_dump()
    assert variant.quotes==baseline.quotes and variant.fair_value==baseline.fair_value
    assert variant.vault_snapshot==baseline.vault_snapshot
    # Real pre-transmission authority and OrderManager/PAPER, not mocked results.
    for rt in (baseline,variant):
        if kill:
            await rt.activate_kill(); await rt.refresh_once()
            assert rt.risk.kill_switch_active and not rt.quotes
            with pytest.raises(PermissionError):await rt._execution_authority()
        else:
            rt.strategy.running=True
            await rt._execution_authority()
            async with rt.execution_lock:
                rt.last_actions=await rt.orders.reconcile_locked(rt.config.market,rt.quotes,rt.config.replace_tolerance_bps,rt.config.size_tolerance)
            assert rt.paper.all_orders()  # CREATE, then KEEP
            async with rt.execution_lock:
                rt.last_actions=await rt.orders.reconcile_locked(rt.config.market,rt.quotes,rt.config.replace_tolerance_bps,rt.config.size_tolerance)
            assert all(a.action.value=='KEEP' for a in rt.last_actions)
            # Identical resting-price drift exercises REPLACE in both runtimes.
            bid=next(o for o in rt.paper.all_orders() if o.side=='BID')
            bid.price-=D('10')
            async with rt.execution_lock:
                rt.last_actions=await rt.orders.reconcile_locked(rt.config.market,rt.quotes,rt.config.replace_tolerance_bps,rt.config.size_tolerance)
            assert any(a.action.value=='REPLACE' for a in rt.last_actions)
            async with rt.execution_lock:
                rt.last_actions=await rt.orders.reconcile_locked(rt.config.market,rt.quotes[1:],rt.config.replace_tolerance_bps,rt.config.size_tolerance)
            assert any(a.action.value=='CANCEL' for a in rt.last_actions)
            rt.paper._fill(next(o for o in rt.paper.all_orders() if o.side=='BID' and o.status.value=='OPEN'))
    assert variant.last_actions==baseline.last_actions
    assert variant.paper.all_orders()==baseline.paper.all_orders()
    assert variant.paper.fills.all()==baseline.paper.fills.all()
    assert variant.accounting_service.snapshot()==baseline.accounting_service.snapshot()
    assert variant.risk.kill_switch_active==baseline.risk.kill_switch_active
    await variant._publish_terminal_snapshot()
    terminal=await variant.terminal_state()
    assert terminal['references'] is not None
    public=json.dumps(terminal,default=str)
    assert 'fixture-secret' not in public and 'YAHOO_FINANCE' not in public


@pytest.mark.asyncio
async def test_yahoo_reconnect_resubscribe_and_shutdown_drains_children(monkeypatch):
    import asyncio
    import app.references.yahoo as module
    at=utcnow().replace(microsecond=0)
    connected=asyncio.Event(); sockets=[]; listeners=[]; watchers=[]
    class Socket:
        def __init__(self):self.subscriptions=[]; self.closed=False; sockets.append(self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):self.closed=True
        async def subscribe(self,symbols):self.subscriptions.append(symbols)
        async def listen(self,handler):
            listeners.append(asyncio.current_task())
            handler(frame(at-timedelta(seconds=1) if len(sockets)==1 else at))
            if len(sockets)==1:return
            connected.set()
            await asyncio.Event().wait()
    p=yahoo(websocket_factory=Socket)
    original_watch=p._watch
    async def watch():
        watchers.append(asyncio.current_task())
        await original_watch()
    monkeypatch.setattr(p,'_watch',watch)
    monkeypatch.setattr(module,'backoff',lambda *args,**kwargs:0)
    await p.start()
    try:
        await asyncio.wait_for(connected.wait(),2)
        assert p.snapshot().healthy
        assert len(sockets)==2 and sockets[0].closed
        assert all(s.subscriptions==[['ETH-USD']] for s in sockets)
    finally:await p.stop()
    assert p.task is None and all(s.closed for s in sockets)
    assert all(task.done() for task in listeners+watchers)


@pytest.mark.asyncio
async def test_coingecko_retry_schedule_is_bounded_and_owned_client_closed(monkeypatch):
    import asyncio
    import app.references.providers as module
    delays=[]; calls=[]
    real_sleep=asyncio.sleep
    def respond(request):
        calls.append(request)
        return httpx.Response(429)
    async def sleep(delay):
        delays.append(delay)
        if len(delays)==10:raise asyncio.CancelledError
        await real_sleep(0)
    real_client=httpx.AsyncClient
    def factory(**kwargs):
        assert kwargs['follow_redirects'] is False and kwargs['timeout']==10
        return real_client(transport=httpx.MockTransport(respond),**kwargs)
    monkeypatch.setattr(module.httpx,'AsyncClient',factory)
    monkeypatch.setattr(module.asyncio,'sleep',sleep)
    p=gecko()
    await p._run()
    assert len(calls)==10 and all(20<=delay<=300 for delay in delays)
    client=p.client
    await p.stop()
    assert client.is_closed and p.client is None


@pytest.mark.asyncio
async def test_invalid_coingecko_configuration_keeps_paper_safe():
    from app.market_data.models import MarketDataMode
    rt=HyperAmmRuntime(Settings(_env_file=None,coingecko_reference_enabled=True,coingecko_api_key=None))
    # Enable real reference mode with deterministic local market data; no provider network.
    rt.reference_service.mode=MarketDataMode.LIVE
    rt.reference_service.coingecko.state.enabled=True
    await rt.reference_service.coingecko.start()
    assert rt.reference_service.coingecko.snapshot().status==ProviderStatus.ERROR
    assert rt.reference_service.coingecko.client is rt.reference_service.coingecko.task is None
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(4))
    rt.strategy.running=True
    await rt.refresh_once()
    assert rt.references is not None and rt.risk_decision.state.value=='HALT'
    assert not rt.authorization.authorized and not rt.quotes
    assert rt.paper.all_orders()==[] and not rt.risk.kill_switch_active


@pytest.mark.asyncio
async def test_observations_rest_exposes_yahoo_separately_without_secrets():
    from fastapi import FastAPI
    from app.api.risk import router
    from app.dependencies import runtime
    rt=HyperAmmRuntime(Settings(_env_file=None,yfinance_reference_enabled=True,coingecko_api_key='fixture-secret'))
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(4)); await rt.refresh_once()
    at=utcnow().replace(microsecond=0); rt.reference_service.yahoo.ingest(frame(at),at)
    app=FastAPI(); app.include_router(router,prefix='/api/v1'); app.dependency_overrides[runtime]=lambda:rt
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        observations=await client.get('/api/v1/references/observations')
        material=await client.get('/api/v1/references')
        assert observations.status_code==material.status_code==200
        assert observations.json()['observations'][0]['provider']=='YAHOO_FINANCE'
        assert observations.json()['authority']=='NONE'
        assert 'YAHOO_FINANCE' not in material.text
        assert 'fixture-secret' not in material.text+observations.text
