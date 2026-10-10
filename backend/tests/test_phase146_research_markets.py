"""Native SDK metadata, precision, deterministic scenarios and exact runtime isolation."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal as D
from threading import Event

import pytest
from pydantic import ValidationError

from app.main import app
from app.market_data.hyperliquid_metadata import HyperliquidMetadataCatalog, validate_native_metadata, load_sdk_metadata
from app.simulation.market_profiles import (MARKETS, ResearchPerpMarketMetadata, profile,
    normalize_price, validate_price, normalize_quotes, research_strategy)
from app.simulation.scenarios import ScenarioName, generate_scenario
from app.simulation.models import stable_fingerprint
from app.api.simulation import SimulationRunRequest, OptimizationRequest
from app.api.research_vault import ResearchComparisonRequest
from app.amm.models import QuoteLevel
from app.strategy.models import StrategyConfig
from test_phase14_research_vault import research_client, authority, proposal

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def native():
    # Deliberately nonstandard positions: indices must come from this universe.
    return {'universe': [{'name':'OTHER','szDecimals':3}, {'name':'SOL','szDecimals':2},
        {'name':'BTC','szDecimals':5}, {'name':'ETH','szDecimals':4}]}


def demo(market):
    precision = {'BTC':5, 'ETH':4, 'SOL':2}[market]
    return profile(ResearchPerpMarketMetadata(market=market, sz_decimals=precision,
        metadata_status='DEMO_PROFILE', metadata_source='PINNED_RESEARCH_FIXTURE'))


def test_native_whitelist_indices_and_immutable_snapshot():
    values = validate_native_metadata(native(), NOW)
    assert [p.market for p in values] == list(MARKETS)
    assert [p.asset_index for p in values] == [2,3,1]
    assert all(p.metadata_status == 'EXCHANGE_VERIFIED' for p in values)
    with pytest.raises(ValidationError): values[0].sz_decimals = 6


@pytest.mark.parametrize('raw', [None, [], {}, {'universe':[]}, {'dex':'hip3','universe':[]},
    {'universe':[{'name':'BTC'}]}, {'universe':[{'name':'BTC','szDecimals':True}]},
    {'universe':[{'name':'BTC','szDecimals':'5'}]}, {'universe':[{'name':'BTC','szDecimals':-1}]},
    {'universe':[{'name':'BTC','szDecimals':7}]}, {'universe':[{'name':'BTC','szDecimals':5,'isDelisted':'false'}]},
    {'universe':[{'name':'foo:BTC','szDecimals':5}]}, {'universe':[{'name':'BTC/USDC','szDecimals':5}]},
    {'universe':[{'name':'@1','szDecimals':5}]}, {'universe':[{'name':'BTC','szDecimals':5}]*2}])
def test_malformed_metadata_rejected(raw):
    with pytest.raises(ValueError): validate_native_metadata(raw, NOW)


@pytest.mark.parametrize('market', MARKETS)
def test_valid_missing_or_delisted_never_demo_fallback(market):
    raw = native()
    next(p for p in raw['universe'] if p['name'] == market)['isDelisted'] = True
    p = profile(next(p for p in validate_native_metadata(raw,NOW) if p.market == market))
    assert not p.research_supported and p.listed is False
    raw['universe'] = [p for p in raw['universe'] if p['name'] != market]
    p = profile(next(p for p in validate_native_metadata(raw,NOW) if p.market == market))
    assert not p.research_supported and p.asset_index is None


@pytest.mark.parametrize('market', ['DOGE','HYPE','BTC/USDC','SOL/USDC','BTC-PERP','@1','xyz:BTC','btc','Eth',' BTC','SOL ',None,[],['BTC','ETH']])
def test_exact_optional_request_symbol(market):
    if market is None:
        assert SimulationRunRequest(research_market=None).research_market is None
    else:
        with pytest.raises(ValidationError): SimulationRunRequest(research_market=market)


def test_no_client_profile_or_precision_or_index_authority():
    for patch in ({'market_profile':demo('BTC').model_dump()}, {'asset_index':2}, {'tick_size':'1'}, {'sz_decimals':5}):
        with pytest.raises(ValidationError): SimulationRunRequest(research_market='BTC', **patch)


@pytest.mark.parametrize('price,precision,expected', [('123456',5,'123456'),('60000.1',5,'60000'),
    ('9999.99',4,'9999.9'),('3000.123',4,'3000.1'),('150.123',2,'150.12'),
    ('0.123456',2,'0.1234'),('0.000123456',6,'0')])
def test_price_rule_integer_exception_significance_and_decimals(price,precision,expected):
    if D(expected) == 0:
        with pytest.raises(ValueError): normalize_price(D(price),precision)
    else:
        assert normalize_price(D(price),precision) == D(expected)
        assert validate_price(D(expected),precision)


@pytest.mark.parametrize('market',MARKETS)
def test_outward_quote_rounding_never_increases_size_or_notional(market):
    p=demo(market)
    for side in ('BID','ASK'):
        q=QuoteLevel(side=side,price=p.simulated_reference_price+D('.123456'),size=D('.123456789'),
            level_index=0,distance_bps=0,source_model='CONSTANT_PRODUCT')
        for n in normalize_quotes([q],p):
            assert validate_price(n.price,p.sz_decimals)
            assert n.size <= q.size and n.price*n.size <= q.price*q.size
            assert (n.price <= q.price) if side=='BID' else (n.price >= q.price)


@pytest.mark.parametrize('market',MARKETS)
def test_strategy_notional_scaling_does_not_relax_limits(market):
    source=StrategyConfig(execution_mode='TESTNET',market_data_mode='LIVE')
    before=source.model_dump()
    result=research_strategy(source,demo(market))
    assert result.market==market and result.execution_mode=='PAPER' and result.market_data_mode=='DEMO'
    assert result.virtual_quote_reserve/result.virtual_base_reserve==demo(market).simulated_reference_price
    assert result.virtual_quote_reserve==source.virtual_quote_reserve
    assert result.total_liquidity*demo(market).simulated_reference_price <= source.total_liquidity*D('3000')
    assert result.hard_inventory_limit_base==source.hard_inventory_limit_base
    assert result.soft_inventory_limit_base==source.soft_inventory_limit_base
    assert source.model_dump()==before


def test_infeasible_lot_size_fails_closed():
    with pytest.raises(ValidationError):
        research_strategy(StrategyConfig(base_order_size=D('.0001'),total_liquidity=D('.001')),demo('BTC'))


@pytest.mark.parametrize('market',MARKETS)
@pytest.mark.parametrize('scenario',list(ScenarioName))
def test_all_asset_scenarios_deterministic_consistent_and_precise(market,scenario):
    p=demo(market)
    a=generate_scenario(scenario,frames=30,market=market,market_profile=p)
    b=generate_scenario(scenario,frames=30,market=market,market_profile=p)
    assert a.fingerprint==b.fingerprint
    for i,f in enumerate(a.frames):
        assert f.market.market==f.market.book.market==f.perp_context.market==market
        assert f.sequence==i+1 and f.market.best_bid<f.market.best_ask
        assert all(validate_price(level.price,p.sz_decimals) and level.size>0
            and level.size==level.size.quantize(D(1).scaleb(-p.sz_decimals))
            for level in f.market.book.bids+f.market.book.asks)
        assert validate_price(f.perp_context.mark_price,p.sz_decimals)
        assert validate_price(f.perp_context.oracle_price,p.sz_decimals)
    assert a.fingerprint != generate_scenario(scenario,frames=30).fingerprint


def test_legacy_scenario_path_unchanged_and_profile_identity_changes_dataset():
    legacy=generate_scenario('QUIET',frames=4)
    assert [f.market.mid_price for f in legacy.frames]==[D('3000'),D('3000.2'),D('3000'),D('2999.8')]
    p=demo('ETH'); a=generate_scenario('QUIET',frames=4,market_profile=p)
    changed=profile(ResearchPerpMarketMetadata(market='ETH',sz_decimals=3,
        metadata_status='DEMO_PROFILE',metadata_source='PINNED_RESEARCH_FIXTURE'))
    assert a.fingerprint!=generate_scenario('QUIET',frames=4,market_profile=changed).fingerprint
    with pytest.raises(ValueError): generate_scenario('QUIET',market='BTC',market_profile=p)


@pytest.mark.asyncio
async def test_catalog_singleflight_cancel_cache_and_cleanup():
    started,release=Event(),Event();calls=[]
    def loader():
        calls.append(1);started.set();assert release.wait(5);return native()
    c=HyperliquidMetadataCatalog(loader=loader)
    a=asyncio.create_task(c.catalog())
    try:
        assert await asyncio.to_thread(started.wait,3)
        b=asyncio.create_task(c.catalog());a.cancel()
        with pytest.raises(asyncio.CancelledError): await a
        release.set(); result=await b
        assert len(calls)==1 and len(result.markets)==3
        again=await c.catalog()
        assert len(calls)==1 and again.markets[0].profile_fingerprint==result.markets[0].profile_fingerprint
        assert again.markets[0].metadata_age_seconds>=result.markets[0].metadata_age_seconds
    finally:
        release.set();await c.close()
    with pytest.raises(ValueError): await c.catalog()


@pytest.mark.asyncio
@pytest.mark.parametrize('allow_demo',[True,False])
async def test_outage_eligibility_and_expired_verified_cache(allow_demo):
    calls=[]
    def loader():
        calls.append(1)
        if len(calls)>1: raise ConnectionError('unavailable')
        return native()
    c=HyperliquidMetadataCatalog(loader=loader,allow_demo=allow_demo,ttl_seconds=0)
    try:
        first=await c.catalog();second=await c.catalog()
        assert first.markets[0].metadata_status=='EXCHANGE_VERIFIED'
        assert second.markets[0].metadata_status==('DEMO_PROFILE' if allow_demo else 'UNAVAILABLE')
        assert second.markets[0].asset_index is None and second.markets[0].listed is None
        assert second.markets[0].metadata_observed_at is None
        assert second.markets[0].research_supported is allow_demo
    finally: await c.close()


def test_sdk_readonly_native_no_ws_timeout_and_close(monkeypatch):
    import hyperliquid.info
    calls=[]
    class Session:
        def close(self):calls.append('close')
    class Info:
        def __init__(self,url,**kwargs):
            calls.append(kwargs);self.session=Session()
        def meta(self,**kwargs):calls.append(kwargs);return native()
    monkeypatch.setattr(hyperliquid.info,'Info',Info)
    assert load_sdk_metadata()==native()
    assert calls[0]['skip_ws'] is True and calls[0]['timeout']==5
    assert 'perp_dexs' not in calls[0] and calls[1]=={'dex':''} and calls[2]=='close'


@pytest.fixture
def market_client(research_client,monkeypatch):
    client,rt=research_client
    catalog=HyperliquidMetadataCatalog(allow_demo=True,loader=native)
    # Preloaded verified fixture has provenance only inside this test, not live acceptance.
    catalog._snapshot=validate_native_metadata(native(),NOW);catalog._expires=float('inf')
    monkeypatch.setattr(app.state,'research_market_catalog',catalog,raising=False)
    yield client,rt
    asyncio.run(catalog.close())


@pytest.mark.parametrize('market',MARKETS)
def test_run_compare_optimizer_provenance_and_exact_runtime_isolation(market_client,market):
    client,rt=market_client;before=authority(rt)
    catalog=client.get('/api/v1/research-markets').json()
    assert [p['market'] for p in catalog['markets']]==list(MARKETS)
    body={'research_market':market,'scenario':'FLASH_MOVE','frames':30,'research':proposal().model_dump(mode='json')}
    a=client.post('/api/v1/simulation/run',json=body);assert a.status_code==200,a.text
    r=a.json();assert r['research_market']==market and r['vault']['market']==market
    assert r['market_profile_fingerprint']==next(p for p in catalog['markets'] if p['market']==market)['profile_fingerprint']
    assert all(x['market']==market for x in r['orders']+r['fills'])
    assert all(validate_price(D(x['price']),demo(market).sz_decimals) for x in r['orders']+r['fills'])
    b=client.post('/api/v1/simulation/run',json=body);assert b.status_code==200
    assert r['run_fingerprint']==b.json()['run_fingerprint']
    custom=proposal().model_dump(mode='json');custom['config']['paper_taker_fee_bps']='20'
    cmp=client.post('/api/v1/research-vault/compare',json={'research_market':market,'frames':30,'scenario':'FLASH_MOVE',
        'baseline':body['research'],'custom':custom});assert cmp.status_code==200,cmp.text
    old,new=cmp.json()['baseline_result'],cmp.json()['custom_result']
    assert old['research_market']==new['research_market']==market
    assert old['dataset_fingerprint']==new['dataset_fingerprint'] and old['strategy_fingerprint']==new['strategy_fingerprint']
    assert old['run_fingerprint']!=new['run_fingerprint']
    opt=client.post('/api/v1/simulation/optimize',json={'research_market':market,'frames':3,
        'strategy_grid':{'levels_per_side':[6]},'agent_grid':{},'training_scenarios':['QUIET'],
        'validation_scenarios':['FLASH_MOVE']});assert opt.status_code==200,opt.text
    assert opt.json()['research_market']==market and opt.json()['candidate_count']==1
    assert authority(rt)==before


def test_bad_symbols_protected_grid_low_capital_and_unavailable_fail_closed(market_client):
    client,rt=market_client;before=authority(rt)
    assert client.post('/api/v1/simulation/run',json={'research_market':'BTC-PERP'}).status_code==422
    assert client.post('/api/v1/simulation/optimize',json={'research_market':'BTC','strategy_grid':{'market':['SOL']},
        'agent_grid':{},'training_scenarios':['QUIET'],'validation_scenarios':['FLASH_MOVE']}).status_code==422
    low=proposal().model_dump(mode='json');low['config']['initial_equity_quote']='1'
    result=client.post('/api/v1/simulation/run',json={'research_market':'BTC','frames':3,'research':low})
    assert result.status_code==200 and result.json()['metrics']['risk_halt_fraction']=='1' and not result.json()['orders']
    raw=native();raw['universe'][2]['isDelisted']=True
    app.state.research_market_catalog._snapshot=validate_native_metadata(raw,NOW)
    assert client.post('/api/v1/simulation/run',json={'research_market':'BTC','frames':3}).status_code==422
    assert authority(rt)==before
