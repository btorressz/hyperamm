"""Deterministic native evidence, SDK ownership and real runtime isolation."""
import asyncio
import copy
import inspect
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError
from requests.exceptions import Timeout

from app.config import Settings
from app.main import app
from app.market_data.live_models import LiveBookLevel, LiveMarketMetadata, LiveMarketSnapshot
from app.market_data.live_observations import LiveMarketObservationService, normalize_book, normalize_context
from app.runtime import HyperAmmRuntime
from app.simulation.market_profiles import MARKETS, DEMO_PROFILES
from test_phase14_research_vault import authority

NOW = datetime(2026, 10, 10, 20, tzinfo=timezone.utc)


class Clock:
    def __init__(self): self.now, self.elapsed = NOW, 0
    def __call__(self): return self.now
    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.elapsed += seconds


def native():
    return {'universe': [{'name':'OTHER','szDecimals':3}, {'name':'SOL','szDecimals':2},
                         {'name':'BTC','szDecimals':5}, {'name':'ETH','szDecimals':4}]}


def book(market):
    bid,ask = {'BTC':('60000','60010'),'ETH':('3000','3001'),'SOL':('150','151')}[market]
    return {'coin':market,'time':int(NOW.timestamp()*1000),
        'levels':[[{'px':bid,'sz':'1','n':2}],[{'px':ask,'sz':'2','n':3}]]}


def contexts():
    prices = {'BTC':'60000','ETH':'3000','SOL':'150','OTHER':'1'}
    return [native(), [{'markPx':prices[item['name']],'oraclePx':prices[item['name']],
        'funding':'-0.0001','openInterest':'100','midPx':prices[item['name']],'premium':'0.001'}
        for item in native()['universe']]]


class FakeSDK:
    def __init__(self):
        self.metadata, self.context = native(), contexts()
        self.books = {market:book(market) for market in MARKETS}
        self.clients, self.calls = [], []
        self.metadata_error, self.started, self.release, self.context_hook = None,None,None,None
        self.book_errors, self.context_errors = {},{}
        self.cleanup_error = False

    def factory(self, meta, timeout):
        owner, initialized = self, copy.deepcopy(meta)
        class Info:
            def __init__(self):
                self.name_to_coin = {item['name']:item['name'] for item in initialized['universe']}
                self.coin_to_asset = {item['name']:i for i,item in enumerate(initialized['universe'])}
                self.asset_to_sz_decimals = {i:item['szDecimals'] for i,item in enumerate(initialized['universe'])}
                self.timeout, self.closed, self.market, self.session = timeout,False,None,self
            def meta(self,dex=''):
                owner.calls.append(('meta',dex))
                if owner.metadata_error: raise owner.metadata_error
                return copy.deepcopy(owner.metadata)
            def l2_snapshot(self,market):
                assert not self.closed
                self.market = market; owner.calls.append(('l2',market))
                if owner.started:
                    owner.started.set()
                    if not owner.release.wait(3): raise Timeout('fixture gate timeout')
                if market in owner.book_errors: raise owner.book_errors[market]
                return copy.deepcopy(owner.books[market])
            def meta_and_asset_ctxs(self):
                assert not self.closed
                owner.calls.append(('ctx',self.market))
                if owner.context_hook: owner.context_hook()
                if self.market in owner.context_errors: raise owner.context_errors[self.market]
                return copy.deepcopy(owner.context)
            def close(self):
                self.closed = True
                if owner.cleanup_error: raise RuntimeError('secret-fixture cleanup')
        info = Info(); self.clients.append(info); return info


def observer(sdk=None,clock=None,**options):
    sdk,clock = sdk or FakeSDK(),clock or Clock()
    service = LiveMarketObservationService(Settings(_env_file=None,live_observations_enabled=True,**options),
        info_factory=sdk.factory,clock=clock,timer=lambda:clock.elapsed)
    return service,sdk,clock


@pytest.fixture
async def live():
    service,sdk,clock = observer()
    yield service,sdk,clock
    await service.close()


def verified(market='BTC'):
    i = next(i for i,item in enumerate(native()['universe']) if item['name']==market)
    return LiveMarketMetadata(market=market,metadata_status='EXCHANGE_VERIFIED',source='OFFICIAL_SDK_NATIVE_META',
        listed=True,asset_index=i,sz_decimals=native()['universe'][i]['szDecimals'],observed_at=NOW)


@pytest.mark.parametrize('market',MARKETS)
async def test_complete_immutable_native_evidence(live,market):
    service,sdk,_ = live; result = await service.snapshot(market)
    assert result.observation_status=='AVAILABLE',result.errors
    assert result.market==result.metadata.market==result.order_book.market==result.perp_context.market==market
    assert result.metadata.asset_index=={'BTC':2,'ETH':3,'SOL':1}[market]
    assert result.read_only and not result.simulated and result.dex==''
    assert result.perp_context.source_timestamp is None and result.perp_context.observed_at==NOW
    assert result.freshness.perp_event_time=='UNKNOWN' and result.last_successful_observed_at==NOW
    assert all(info.closed for info in sdk.clients)
    assert isinstance(result.model_dump(mode='json')['order_book']['midpoint'],str)
    with pytest.raises(ValidationError): result.order_book.bids[0].size=D(5)


@pytest.mark.parametrize('market',['DOGE','HYPE','BTC-PERP','BTC/USDC','SOL/USDC','@1','btc','Eth','xyz:BTC',' BTC','SOL ',None,[],['BTC','ETH']])
async def test_invalid_symbols_never_call_sdk(live,market):
    service,sdk,_ = live
    with pytest.raises(ValueError): await service.snapshot(market)
    assert not sdk.clients


@pytest.mark.parametrize('raw',[None,{}, {'dex':'other','universe':[]},
    {'universe':[{'name':'BTC','szDecimals':True}]}, {'universe':[{'name':'BTC','szDecimals':7}]},
    {'universe':[{'name':'BTC','szDecimals':5}]*2}, {'universe':[{'name':'BTC','szDecimals':'5'}]},
    {'universe':[{'name':'BTC','szDecimals':5,'isDelisted':1}]},
    {'universe':[{'name':'hip3:BTC','szDecimals':5}]}, {'universe':[{'name':'@1','szDecimals':5}]}])
async def test_invalid_metadata_cannot_create_live_or_demo_evidence(live,raw):
    service,sdk,_ = live; sdk.metadata=raw; result=await service.snapshot('BTC')
    assert result.metadata.metadata_status=='ERROR'
    assert result.order_book is result.perp_context is None
    assert 'DEMO_PROFILE' not in result.model_dump_json()
    assert all(info.closed for info in sdk.clients) and sdk.calls==[('meta','')]


@pytest.mark.parametrize('market',MARKETS)
@pytest.mark.parametrize('missing',[True,False])
async def test_missing_or_delisted_unavailable(live,market,missing):
    service,sdk,_ = live; entry=next(item for item in sdk.metadata['universe'] if item['name']==market)
    if missing: sdk.metadata['universe'].remove(entry)
    else: entry['isDelisted']=True
    result=await service.snapshot(market)
    assert result.observation_status=='UNAVAILABLE' and result.metadata.metadata_status=='UNAVAILABLE'
    assert result.errors[0].code=='NOT_LISTED' and not result.order_book and not result.perp_context
    assert sdk.calls==[('meta','')]


@pytest.mark.parametrize('value',['NaN','Infinity','-Infinity','bad','1e100000',' 1 ','1_000',True,1.1,{},'-1','0'])
def test_invalid_prices(value):
    raw=book('BTC'); raw['levels'][0][0]['px']=value
    with pytest.raises((ValueError,ArithmeticError)): normalize_book(raw,verified(),NOW,future_tolerance=1,max_levels=20)


@pytest.mark.parametrize('change',['missing_bid','missing_ask','cross','duplicate','unsorted_bid','unsorted_ask',
    'wrong_coin','no_coin','no_time','bool_time','float_time','future','structure','negative_size',
    'size_precision','price_precision','count_bool','oversized'])
def test_book_identity_structure_precision_order_and_times(change):
    raw=book('BTC')
    if change=='missing_bid': raw['levels'][0]=[]
    elif change=='missing_ask': raw['levels'][1]=[]
    elif change=='cross': raw['levels'][1][0]['px']='59999'
    elif change=='duplicate': raw['levels'][0]*=2
    elif change=='unsorted_bid': raw['levels'][0].append({'px':'60001','sz':'1'})
    elif change=='unsorted_ask': raw['levels'][1].append({'px':'60009','sz':'1'})
    elif change=='wrong_coin': raw['coin']='ETH'
    elif change=='no_coin': raw.pop('coin')
    elif change=='no_time': raw.pop('time')
    elif change=='bool_time': raw['time']=True
    elif change=='float_time': raw['time']=float(raw['time'])
    elif change=='future': raw['time']+=2000
    elif change=='structure': raw['levels']={}
    elif change=='negative_size': raw['levels'][0][0]['sz']='-1'
    elif change=='size_precision': raw['levels'][0][0]['sz']='0.000001'
    elif change=='price_precision': raw['levels'][0][0]['px']='60000.1'
    elif change=='count_bool': raw['levels'][0][0]['n']=True
    elif change=='oversized': raw['levels'][0]*=101
    with pytest.raises((ValueError,ArithmeticError)): normalize_book(raw,verified(),NOW,future_tolerance=1,max_levels=20)


def test_zero_sizes_depth_bound_and_integer_price_exception():
    raw=book('BTC'); raw['levels'][0]=[{'px':str(123456-i),'sz':'0','n':0} for i in range(25)]
    raw['levels'][1]=[{'px':'123457','sz':'1'}]
    result=normalize_book(raw,verified(),NOW,future_tolerance=1,max_levels=20)
    assert len(result.bids)==20 and result.truncated and result.bids[0].size==0
    raw['levels'][0][-1]['px']='123456'
    with pytest.raises(ValueError): normalize_book(raw,verified(),NOW,future_tolerance=1,max_levels=20)


@pytest.mark.parametrize('name,value',[('markPx','0'),('oraclePx','-1'),('funding','NaN'),('funding',0.1),
    ('openInterest','-1'),('openInterest','Infinity'),('midPx','0'),('premium','NaN'),('markPx',True),
    ('markPx',None),('midPx',''),('funding','garbage')])
def test_invalid_context_numbers(name,value):
    raw=contexts();raw[1][2][name]=value
    with pytest.raises(ValueError):normalize_context(raw,verified(),NOW)


@pytest.mark.parametrize('change',['cardinality','missing','duplicate','reordered','precision','delisted','wrong_coin','hip3'])
def test_context_universe_mapping(change):
    raw=contexts()
    if change=='cardinality':raw[1].append(raw[1][0])
    elif change=='missing':raw[1][2]=None
    elif change=='duplicate':raw[0]['universe'][0]['name']='BTC'
    elif change=='reordered':raw[0]['universe'].reverse();raw[1].reverse()
    elif change=='precision':raw[0]['universe'][2]['szDecimals']=4
    elif change=='delisted':raw[0]['universe'][2]['isDelisted']=True
    elif change=='wrong_coin':raw[1][2]['coin']='ETH'
    elif change=='hip3':raw[0]['dex']='hip3'
    with pytest.raises(ValueError):normalize_context(raw,verified(),NOW)


def test_basis_is_reused_with_only_actual_provider_mid():
    raw=contexts();raw[1][2].update(markPx='101',oraclePx='100',midPx='102',openInterest='3')
    result=normalize_context(raw,verified(),NOW)
    assert result.open_interest_notional==D('303') and result.mark_oracle_basis_bps==D('100')
    assert result.mark_mid_basis_bps==(D(101)-D(102))/D(102)*D(10000)
    raw[1][2].pop('midPx');result=normalize_context(raw,verified(),NOW)
    assert result.provider_mid_price is result.mark_mid_basis_bps is result.oracle_mid_basis_bps is None
    assert result.source_timestamp is None


async def test_old_exchange_timestamp_is_not_renewed_by_receipt(live):
    service,sdk,_=live;sdk.books['BTC']['time']-=11000;result=await service.snapshot('BTC')
    assert result.observation_status=='STALE' and result.freshness.l2_source_age_seconds==11
    assert result.order_book.observed_at==NOW and result.order_book.source_timestamp==NOW-timedelta(seconds=11)
    assert result.last_successful_observed_at is None


async def test_cache_expiry_replay_failed_refresh_and_recovery(live):
    service,sdk,clock=live;first=await service.snapshot('BTC');clock.advance(1)
    cached=await service.snapshot('BTC')
    assert len(sdk.clients)==2 and cached.cache_age_seconds==1 and cached.observed_at==first.observed_at
    clock.advance(2);repeated=await service.snapshot('BTC')
    assert repeated.order_book.source_timestamp==first.order_book.source_timestamp
    assert repeated.freshness.l2_source_age_seconds==3
    sdk.books['BTC']['time']-=1;clock.advance(3);regression=await service.snapshot('BTC')
    assert regression.order_book is None and regression.observation_status=='PARTIAL'
    assert regression.last_successful_observed_at==repeated.observed_at
    sdk.metadata_error=Timeout('secret-fixture');clock.advance(6);failed=await service.snapshot('BTC')
    assert failed.order_book is failed.perp_context is None and failed.observation_status=='UNAVAILABLE'
    assert failed.last_successful_observed_at==repeated.observed_at and 'secret-fixture' not in failed.model_dump_json()
    count=len(sdk.clients);await service.snapshot('BTC');assert len(sdk.clients)==count
    sdk.metadata_error=None;clock.advance(6);sdk.books['BTC']['time']=int(clock.now.timestamp()*1000)
    assert (await service.snapshot('BTC')).observation_status=='AVAILABLE'


async def test_conflicting_same_source_timestamp_rejected(live):
    service,sdk,clock=live;await service.snapshot('BTC');clock.advance(3)
    sdk.books['BTC']['levels'][0][0]['sz']='2';result=await service.snapshot('BTC')
    assert result.order_book is None and result.errors[0].code=='INVALID_DATA'


@pytest.mark.parametrize('options,seconds,expected',[({'live_observation_cache_ttl_seconds':60},11,'STALE'),
    ({'live_observation_metadata_stale_after_seconds':1},1.5,'STALE')])
async def test_cached_freshness_independent_of_cache_ttl(options,seconds,expected):
    service,sdk,clock=observer(**options)
    try:
        await service.snapshot('BTC');clock.advance(seconds);result=await service.snapshot('BTC')
        assert len(sdk.clients)==2 and result.observation_status==expected and result.last_successful_observed_at==NOW
        if seconds==11:assert result.freshness.order_book==result.freshness.perp_context=='STALE'
        else:assert result.metadata.metadata_status=='STALE'
    finally:await service.close()


async def test_temporal_discrepancy_and_overview_ages(live):
    service,sdk,clock=live;sdk.context_hook=lambda:clock.advance(3);result=await service.snapshot('BTC')
    assert result.observation_status=='DEGRADED' and result.freshness.acquisition_gap_seconds==3
    assert result.perp_context.source_timestamp is None
    sdk.context_hook=lambda:clock.advance(10);overview=await service.overview()
    assert overview.markets[0].observation_status=='STALE' and overview.markets[0].generated_at==overview.generated_at


async def test_one_market_failure_isolated(live):
    service,sdk,_=live;sdk.book_errors['BTC']=ValueError('secret-fixture');result=await service.overview()
    assert [item.observation_status for item in result.markets]==['PARTIAL','AVAILABLE','AVAILABLE']
    assert result.markets[0].order_book is None and result.markets[1].order_book.market=='ETH'


async def test_disabled_makes_no_sdk_request():
    service=LiveMarketObservationService(Settings(_env_file=None),info_factory=lambda *_:pytest.fail('SDK constructed'))
    try:assert all(item.observation_status=='DISABLED' for item in (await service.overview()).markets)
    finally:await service.close()


@pytest.mark.parametrize('status,code',[(403,'FORBIDDEN'),(429,'RATE_LIMITED'),(500,'UPSTREAM_ERROR'),
    ('timeout','TIMEOUT'),('import','SDK_UNAVAILABLE'),('invalid','INVALID_DATA')])
async def test_fixed_failure_codes_sanitization_and_cooldown(live,status,code):
    from hyperliquid.utils.error import ClientError,ServerError
    service,sdk,clock=live
    if status=='timeout':exc=Timeout('secret-fixture')
    elif status=='import':exc=ImportError('secret-fixture')
    elif status=='invalid':exc=ValueError('secret-fixture')
    elif status==500:exc=ServerError(status,'secret-fixture')
    else:exc=ClientError(status,'fixture','secret-fixture',{},None)
    sdk.metadata_error=exc;result=await service.snapshot('BTC')
    assert result.errors[0].code==code and 'secret-fixture' not in result.model_dump_json()
    clock.advance(4);await service.snapshot('BTC');assert len(sdk.clients)==1


async def test_singleflight_cancel_and_shutdown_keep_worker_owned(live):
    service,sdk,_=live;sdk.started,sdk.release=threading.Event(),threading.Event()
    one=asyncio.create_task(service.snapshot('BTC'));assert await asyncio.to_thread(sdk.started.wait,1)
    two=asyncio.create_task(service.snapshot('BTC'));one.cancel()
    with pytest.raises(asyncio.CancelledError):await one
    closing=asyncio.create_task(service.close());await asyncio.sleep(0)
    assert not closing.done() and not sdk.clients[-1].closed
    assert (await service.snapshot('ETH')).errors[0].code=='CLOSED'
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):await closing
    sdk.release.set();assert (await two).observation_status=='AVAILABLE'
    await service.close()
    assert len(sdk.clients)==2 and all(info.closed for info in sdk.clients)
    assert not service._tasks and all(not worker.is_alive() for worker in service._pool._threads)


async def test_finite_admission_has_no_executor_queue(live):
    service,sdk,_=live;sdk.started,sdk.release=threading.Event(),threading.Event()
    one=asyncio.create_task(service.snapshot('BTC'));assert await asyncio.to_thread(sdk.started.wait,1)
    sdk.started.clear();two=asyncio.create_task(service.snapshot('ETH'));assert await asyncio.to_thread(sdk.started.wait,1)
    assert (await service.snapshot('SOL')).errors[0].code=='CAPACITY'
    assert len(service._tasks)==2 and len(service._pool._threads)<=2
    sdk.release.set();a,b=await asyncio.gather(one,two)
    assert a.market=='BTC' and b.market=='ETH' and (await service.snapshot('SOL')).observation_status=='AVAILABLE'


async def test_cleanup_failure_never_healthy(live):
    service,sdk,_=live;sdk.cleanup_error=True;result=await service.snapshot('BTC')
    assert result.observation_status!='AVAILABLE' and any(item.code=='CLEANUP_ERROR' for item in result.errors)
    assert 'secret-fixture' not in result.model_dump_json()
    assert (await service.snapshot('ETH')).errors[0].code=='CLEANUP_ERROR'
    sdk.cleanup_error=False  # Retained failed session is retried by close.


@pytest.mark.parametrize('field,value',[('live_observation_http_timeout_seconds',0),
    ('live_observation_http_timeout_seconds',float('inf')),('live_observation_cache_ttl_seconds',-1),
    ('live_observation_stale_after_seconds',float('nan')),('live_observation_max_concurrent_requests',0),
    ('live_observation_max_concurrent_requests',4),('live_observation_max_concurrent_requests',True),
    ('live_observation_book_levels',21),('live_observation_coherence_seconds',0)])
def test_settings_resource_bounds(field,value):
    with pytest.raises(ValidationError):Settings(_env_file=None,**{field:value})


def test_settings_parse_environment(monkeypatch):
    monkeypatch.setenv('LIVE_OBSERVATION_MAX_CONCURRENT_REQUESTS','3');monkeypatch.setenv('LIVE_OBSERVATION_BOOK_LEVELS','10')
    settings=Settings(_env_file=None)
    assert settings.live_observation_max_concurrent_requests==3 and settings.live_observation_book_levels==10


def test_strict_contract_and_verification():
    for patch in ({'price':1.1,'size':'1'},{'price':'1','size':'1','wallet':'secret-fixture'}):
        with pytest.raises(ValidationError):LiveBookLevel(**patch)
    with pytest.raises(ValidationError):LiveMarketMetadata(market='BTC',metadata_status='EXCHANGE_VERIFIED',source='NONE')
    with pytest.raises(ValidationError):LiveMarketMetadata.model_validate({**verified().model_dump(),'observed_at':datetime(2026,10,10)})


@pytest.mark.parametrize('kill',[False,True])
async def test_real_runtime_authority_isolation_and_api_contract(live,monkeypatch,kill):
    service,sdk,_=live;rt=HyperAmmRuntime(Settings(_env_file=None,market_data_mode='DEMO',execution_mode='PAPER'))
    monkeypatch.setattr(app.state,'runtime',rt,raising=False);monkeypatch.setattr(app.state,'live_market_observer',service,raising=False)
    from app.market_data.mock import MockMarketDataAdapter
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(4))
    await rt.refresh_once()
    assert rt.authorization is not None and rt.quotes
    rt.strategy.running=True  # Controlled fixture; no background strategy loop.
    await rt._execution_authority()
    async with rt.execution_lock:
        await rt.orders.reconcile_locked(rt.config.market,rt.quotes,rt.config.replace_tolerance_bps,rt.config.size_tolerance)
    assert rt.paper.all_orders()
    rt.accounting_service.reserve(rt.quotes,await rt.execution.get_open_orders())
    if kill:
        await rt.activate_kill()
        await rt.refresh_once()
        assert rt.risk.kill_switch_active and rt.authorization is None
    before=authority(rt);identities=(id(rt.market),id(rt.perp_context_service),id(rt.reference_service));anchors=copy.deepcopy(DEMO_PROFILES)
    paths={path:value for path,value in app.openapi()['paths'].items() if '/live-markets/' in path}
    assert set(paths)=={'/api/v1/live-markets/overview','/api/v1/live-markets/{market}/snapshot'}
    assert all(set(methods)=={'get'} for methods in paths.values())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
        overview=await client.get('/api/v1/live-markets/overview');assert overview.status_code==200
        assert [item['market'] for item in overview.json()['markets']]==list(MARKETS)
        for market in MARKETS:
            response=await client.get(f'/api/v1/live-markets/{market}/snapshot')
            assert response.status_code==200 and response.json()['market']==market
            assert response.json()['perp_context']['source_timestamp'] is None
            LiveMarketSnapshot.model_validate(response.json())
            assert (await client.post(f'/api/v1/live-markets/{market}/snapshot')).status_code==405
        assert (await client.get('/api/v1/markets/BTC')).status_code==404
        assert (await client.get('/api/v1/markets/ETH')).status_code==200
        for market in ('DOGE','btc','BTC-PERP','xyz:BTC','secret-fixture'):
            response=await client.get(f'/api/v1/live-markets/{market}/snapshot')
            assert response.status_code==422 and 'secret-fixture' not in response.text
    assert authority(rt)==before and identities==(id(rt.market),id(rt.perp_context_service),id(rt.reference_service)) and DEMO_PROFILES==anchors


@pytest.mark.parametrize('failure,status',[('disabled',503),('timeout',504),('invalid',503),('rate',429),('partial',200),('stale',503)])
async def test_http_availability_and_sanitization(live,monkeypatch,failure,status):
    service,sdk,_=live;monkeypatch.setattr(app.state,'live_market_observer',service,raising=False)
    if failure=='disabled':service.enabled=False
    elif failure=='timeout':sdk.metadata_error=Timeout('secret-fixture')
    elif failure=='invalid':sdk.metadata={}
    elif failure=='rate':
        from hyperliquid.utils.error import ClientError
        sdk.metadata_error=ClientError(429,'fixture','secret-fixture',{},None)
    elif failure=='partial':sdk.context_errors['BTC']=ValueError('secret-fixture')
    elif failure=='stale':sdk.books['BTC']['time']-=11000
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
        response=await client.get('/api/v1/live-markets/BTC/snapshot')
        assert response.status_code==status and 'secret-fixture' not in response.text and response.headers['cache-control']=='no-store'
        if status==429:assert response.headers['retry-after']=='30'


async def test_real_sdk_mapping_timeout_and_session_cleanup(monkeypatch):
    import requests
    from hyperliquid.info import Info
    sessions,payloads=[],[]
    class Session:
        def __init__(self):self.headers={};self.closed=False;sessions.append(self)
        def post(self,url,json,timeout):
            payloads.append((json,timeout));kind=json['type']
            raw=native() if kind=='meta' else book(json['coin']) if kind=='l2Book' else contexts()
            return SimpleNamespace(status_code=200,json=lambda:raw)
        def close(self):self.closed=True
    monkeypatch.setattr(requests,'Session',Session)
    service=LiveMarketObservationService(Settings(_env_file=None,live_observations_enabled=True),clock=lambda:NOW)
    try:
        for market in MARKETS:assert (await service.snapshot(market)).observation_status=='AVAILABLE'
        assert all(session.closed for session in sessions) and len(sessions)==6
        assert all(timeout==5 for _,timeout in payloads)
        assert [payload['coin'] for payload,_ in payloads if payload['type']=='l2Book']==list(MARKETS)
        assert {payload['type'] for payload,_ in payloads}=={'meta','l2Book','metaAndAssetCtxs'}
        assert 'self.name_to_coin[name]' in inspect.getsource(Info.l2_snapshot)
    finally:await service.close()


def test_call_graph_excludes_trading_authority():
    import ast
    from pathlib import Path
    forbidden={'Exchange','HyperAmmRuntime','MarketDataService','ReferenceService','RiskFirewall',
        'FinalQuoteAuthorization','OrderManager','AccountingService','signing'}
    for path in ('app/market_data/live_observations.py','app/market_data/live_models.py','app/api/live_markets.py'):
        for node in ast.walk(ast.parse(Path(path).read_text())):
            if isinstance(node,ast.ImportFrom):assert not forbidden.intersection(alias.name for alias in node.names)
            if isinstance(node,ast.Attribute):assert node.attr not in {'update_config','start_strategy','stop_strategy',
                'order','cancel','cancel_by_cloid','update_leverage','update_isolated_margin','withdraw','transfer','hyperliquid_private_key'}


async def test_response_and_shutdown_deadlines_retain_owned_operation(live):
    service,sdk,_=live
    sdk.started,sdk.release=threading.Event(),threading.Event()
    service.request_deadline=.02
    reader=asyncio.create_task(service.snapshot('BTC'))
    assert await asyncio.to_thread(sdk.started.wait,1)
    result=await reader
    assert result.errors[0].code=='TIMEOUT' and len(service._tasks)==1
    assert not sdk.clients[-1].closed
    service.shutdown_deadline=.02
    with pytest.raises(RuntimeError,match='still draining'):await service.close()
    assert not sdk.clients[-1].closed and not service._close_task.done()
    sdk.release.set();service.shutdown_deadline=2
    await service.close()
    assert all(info.closed for info in sdk.clients) and not service._tasks


async def test_incomplete_cleanup_is_reported_at_shutdown():
    service,sdk,_=observer();sdk.cleanup_error=True
    await service.snapshot('BTC')
    with pytest.raises(RuntimeError,match='session cleanup incomplete'):await service.close()
    assert all(not worker.is_alive() for worker in service._pool._threads)


@pytest.mark.parametrize('enabled',[False,True])
async def test_lifespan_is_lazy_and_owns_shutdown(monkeypatch,enabled):
    import app.main as main
    sdk=FakeSDK();created=[]
    settings=Settings(_env_file=None,live_observations_enabled=enabled)
    monkeypatch.setattr(main,'settings',settings)
    def factory(settings):
        instance=LiveMarketObservationService(settings,info_factory=sdk.factory,clock=lambda:NOW)
        created.append(instance);return instance
    monkeypatch.setattr(main,'LiveMarketObservationService',factory)
    async with main.lifespan(app):
        assert not sdk.clients and app.state.runtime.config.market=='ETH'
        result=await app.state.live_market_observer.snapshot('BTC')
        assert result.observation_status==('AVAILABLE' if enabled else 'DISABLED')
        assert app.state.runtime.config.market=='ETH'
    assert created[0]._closed and all(info.closed for info in sdk.clients)
    assert all(not worker.is_alive() for worker in created[0]._pool._threads)


async def test_api_capacity_and_partial_overview(live,monkeypatch):
    service,sdk,_=live;monkeypatch.setattr(app.state,'live_market_observer',service,raising=False)
    sdk.started,sdk.release=threading.Event(),threading.Event()
    one=asyncio.create_task(service.snapshot('BTC'));assert await asyncio.to_thread(sdk.started.wait,1)
    sdk.started.clear();two=asyncio.create_task(service.snapshot('ETH'));assert await asyncio.to_thread(sdk.started.wait,1)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
        result=await client.get('/api/v1/live-markets/SOL/snapshot')
        assert result.status_code==429 and result.headers['retry-after']=='1'
        sdk.release.set();await asyncio.gather(one,two)
        sdk.context_errors['SOL']=ValueError('secret-fixture')
        result=await client.get('/api/v1/live-markets/overview')
        assert result.status_code==200 and result.json()['markets'][2]['observation_status']=='PARTIAL'
        assert 'secret-fixture' not in result.text


@pytest.mark.parametrize('value',[D('0e-1000000'),D('0e1000000'),D('1e-61'),D('1e31')])
def test_decimal_exponent_bounds_include_zero_before_serialization(value):
    with pytest.raises(ValidationError):LiveBookLevel(price='1',size=value)
