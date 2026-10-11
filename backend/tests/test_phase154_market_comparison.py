from decimal import Decimal as D
import copy
import json
import httpx
import pytest
from pydantic import ValidationError
from app.main import app
from app.config import Settings
from app.market_data.live_streams import LiveMarketStreamService
from app.research_comparison.models import ResearchMarketComparisonRequest
from app.research_comparison.comparison import compare
from test_phase152_live_streams import streams
from phase154_helpers import request, summary

@pytest.mark.parametrize('market',['BTC','ETH','SOL'])
async def test_decimal_metrics_actual_capture(streams,market):
    service,_,_=streams
    r=compare(request(market,market=market),service.snapshot(market))
    a=r.research.assumptions;metrics={x.metric_name:x for x in r.metrics};b=r.observed.snapshot.order_book
    assert metrics['midpoint'].absolute_difference==b.midpoint-a.midpoint
    assert metrics['midpoint'].difference_bps==(b.midpoint-a.midpoint)/a.midpoint*D(10000)
    assert metrics['spread_bps'].difference_bps==b.spread_bps-a.spread_bps
    assert metrics['funding_rate'].absolute_difference==r.observed.snapshot.perp_context.funding_rate-a.funding_rate
    assert metrics['funding_rate'].comparison_status=='PARTIAL'
    if r.observed.depth_level_count==5:
        assert metrics['bid_depth_base'].absolute_difference==r.observed.bid_depth_base-a.bid_depth_base
    else:assert metrics['bid_depth_base'].comparison_status=='NOT_COMPARABLE'
    assert all(isinstance(x.observed_value,D) for x in r.metrics if x.observed_value is not None)
    assert isinstance(json.loads(r.model_dump_json())['metrics'][0]['absolute_difference'],str)

@pytest.mark.parametrize('component',['book','context','metadata','disconnected','depth','oi','legacy','mismatch'])
async def test_missing_partial_and_mismatched_evidence(streams,component):
    service,_,clock=streams;s=service.snapshot('BTC');data=s.model_dump()
    research=summary()
    if component=='book':data['order_book']=None;data['status']['l2_freshness']='UNAVAILABLE'
    if component=='context':data['perp_context']=None;data['status']['perp_freshness']='UNAVAILABLE'
    if component=='metadata':data['status']['metadata_freshness']='STALE'
    if component=='disconnected':data['status']['connection_state']='RECONNECTING'
    if component=='depth':
        data['order_book']['bids']=data['order_book']['bids'][:1]
        data['order_book']['asks']=data['order_book']['asks'][:1]
    if component=='legacy':research=summary(assumptions=False)
    if component=='mismatch':research=summary('ETH')
    if component=='oi':
        from app.simulation.models import stable_fingerprint,ResearchMarketAssumptions
        a=research.assumptions.model_dump(exclude={'assumption_fingerprint'});a['open_interest_base']=None
        research=research.model_copy(update={'assumptions':ResearchMarketAssumptions(**a,assumption_fingerprint=stable_fingerprint(a))})
    s=type(s).model_validate(data);r=compare(ResearchMarketComparisonRequest(market='BTC',research=research),s)
    metrics={m.metric_name:m for m in r.metrics}
    if component=='book':assert metrics['midpoint'].absolute_difference is None and metrics['mark_price'].absolute_difference is not None
    if component=='context':assert metrics['midpoint'].absolute_difference is not None and metrics['funding_rate'].absolute_difference is None
    if component in ('metadata','disconnected','legacy','mismatch'):assert all(m.absolute_difference is None for m in r.metrics)
    if component=='depth':assert metrics['bid_depth_base'].absolute_difference is None
    if component=='oi':assert metrics['open_interest_base'].absolute_difference is None
    if component=='mismatch':assert r.comparison_status=='NOT_COMPARABLE'

@pytest.mark.parametrize('stale',['l2','perp'])
async def test_independent_freshness_gates(streams,stale):
    service,_,_=streams;s=service.snapshot('BTC');data=s.model_dump()
    data['status'][stale+'_freshness']='STALE';data['observation_status']='STALE'
    r=compare(request(),type(s).model_validate(data));metrics={m.metric_name:m for m in r.metrics}
    assert (metrics['midpoint'].absolute_difference is None)==(stale=='l2')
    assert (metrics['mark_price'].absolute_difference is None)==(stale=='perp')

@pytest.mark.parametrize('value',['NaN','Infinity','-Infinity','1e10000',1.2,True,'9'*81,{},[]])
def test_bounded_financial_input(value):
    payload=request().model_dump(mode='json');payload['research']['assumptions']['funding_rate']=value
    with pytest.raises(ValidationError):ResearchMarketComparisonRequest.model_validate(payload)

@pytest.mark.parametrize('field',['midpoint','spread_quote','bid_depth_base','dataset_fingerprint','assumption_fingerprint'])
def test_inconsistent_assumptions_reject(field):
    payload=request().model_dump(mode='json');payload['research']['assumptions'][field]='123' if 'fingerprint' not in field else 'f'*64
    with pytest.raises(ValidationError):ResearchMarketComparisonRequest.model_validate(payload)

@pytest.mark.parametrize('symbol',['DOGE','btc','BTC-PERP',['BTC']])
def test_strict_market(symbol):
    payload=request().model_dump(mode='json');payload['market']=symbol
    with pytest.raises(ValidationError):ResearchMarketComparisonRequest.model_validate(payload)

async def test_api_bounds_sanitization_disabled_and_no_network(monkeypatch):
    service=LiveMarketStreamService(Settings(_env_file=None),client_factory=lambda *a:pytest.fail('comparison opened SDK'))
    monkeypatch.setattr(app.state,'live_market_streams',service,raising=False)
    payload=request().model_dump(mode='json')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as c:
        response=await c.post('/api/v1/research-market-comparison/compare',json=payload)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert response.json()['comparison_status']=='UNAVAILABLE'
        assert response.json()['research']==payload['research'] and not service.enabled
        assert (await c.get('/api/v1/research-market-comparison/compare')).status_code==405
        for mutate in ('extra','nested','levels','secret','nonfinite'):
            data=copy.deepcopy(payload)
            if mutate=='extra':data['module']='credential-sentinel'
            if mutate=='nested':data['research']['performance']['strategy']={}
            if mutate=='levels':data['research']['assumptions']['bid_levels']*=20
            if mutate=='secret':data['research']['run_fingerprint']='credential-sentinel'
            if mutate=='nonfinite':data['research']['performance']['session_pnl']='NaN'
            bad=await c.post('/api/v1/research-market-comparison/compare',json=data)
            assert bad.status_code==422 and 'credential-sentinel' not in bad.text and all('input' not in e and 'ctx' not in e for e in bad.json()['detail'])
        assert (await c.post('/api/v1/research-market-comparison/compare',content='x'*65537)).status_code==413
        def failure(m):raise RuntimeError('credential-sentinel SDK traceback')
        monkeypatch.setattr(service,'snapshot',failure)
        bad=await c.post('/api/v1/research-market-comparison/compare',json=payload)
        assert bad.status_code==500 and 'credential-sentinel' not in bad.text
    await service.close()

@pytest.mark.parametrize('market',['BTC','ETH','SOL'])
def test_actual_normalized_five_level_fixture_and_distinct_price_policy(market):
    from pathlib import Path
    from app.market_data.live_stream_models import LiveStreamSnapshot
    raw=json.loads((Path(__file__).resolve().parents[2]/'frontend/tests/phase154-fixtures.json').read_text())[market]
    snap=LiveStreamSnapshot.model_validate(raw['response']['observed']['snapshot'])
    r=compare(request(market,market=market),snap);metrics={m.metric_name:m for m in r.metrics}
    assert r.observed.depth_level_count==5
    assert r.observed.bid_depth_base==sum((x.size for x in snap.order_book.bids[:5]),D(0))
    if market=='SOL':
        assert len({x.price for x in r.research.assumptions.bid_levels})<5
        assert metrics['bid_depth_base'].absolute_difference is None
    else:
        assert metrics['bid_depth_base'].absolute_difference==r.observed.bid_depth_base-r.research.assumptions.bid_depth_base
        assert metrics['ask_depth_base'].absolute_difference==r.observed.ask_depth_base-r.research.assumptions.ask_depth_base

@pytest.mark.parametrize('location',['summary','assumptions'])
@pytest.mark.parametrize('value',[False,1,'true',None])
def test_simulated_requires_explicit_true_boolean(location,value):
    payload=request().model_dump(mode='json')
    evidence=payload['research'] if location=='summary' else payload['research']['assumptions']
    evidence['simulated']=value
    with pytest.raises(ValidationError):ResearchMarketComparisonRequest.model_validate(payload)


def test_accounting_provenance_rejects_binary_float_and_unknown_fields():
    from app.research_comparison.models import ResearchAccountingProvenance
    from app.simulation.research_vault import ResearchProposal, ResearchVaultConfig
    data=ResearchProposal(config=ResearchVaultConfig()).provenance()
    data['normalized_config']['initial_equity_quote']=100000.5
    with pytest.raises(ValidationError):ResearchAccountingProvenance.model_validate(data)
