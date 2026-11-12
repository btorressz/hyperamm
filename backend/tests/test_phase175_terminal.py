"""Native presentation, preparation, transport and worker acceptance gates."""
import asyncio
from decimal import Decimal
from datetime import timedelta
from threading import Event
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.portfolio_research.preview import PortfolioDraft, prepare
from app.portfolio_research.terminal_models import TerminalRequest, TerminalResult, ChartPoint
from app.portfolio_research.charts import project_chart, sample_indices
from app.portfolio_research.models import sealed, MarketAccountingEvidence, NativeAccountingObservation
from app.portfolio_research.aggregation import assemble_analysis, bounded_json
from app.portfolio_research import aggregation
from app.portfolio_research.orchestration import execute_markets
from app.simulation.service import SimulationService
from app.simulation.executor import SimulationExecutor, ResearchBusyError
from app.infrastructure.research import ResearchUnavailableError
from app.simulation.scenarios import DEFAULT_START
from app.simulation.market_profiles import profile, ResearchPerpMarketMetadata, DEMO_PROFILES
from phase174_fixtures import request_for, KINDS
from test_phase14_research_vault import research_client, authority
from test_phase166c2_local_integration import local_server

URL='/api/v1/portfolio-research/'

def draft(markets=('BTC','ETH','SOL'), frames=12, stress=None):
    original=request_for(markets=markets,frames=frames,onset=4)
    return PortfolioDraft(budget=original.config.budget, allocations=original.config.allocations,
        risk_limits=original.config.risk_limits, frames=frames, stress=stress)


def profiles():
    return {m:profile(ResearchPerpMarketMetadata(market=m,sz_decimals=DEMO_PROFILES[m][1],
        metadata_status='DEMO_PROFILE',metadata_source='PINNED_RESEARCH_FIXTURE')) for m in DEMO_PROFILES}


def terminal_request(kind=None,markets=('BTC','ETH','SOL'),frames=12):
    r=request_for(kind or 'CORRELATED_SELLOFF',markets=markets,frames=frames,
        onset=7 if kind=='CONCENTRATION_STRESS' else 4)
    raw=r.model_dump()
    if not kind:raw.pop('scenario')
    return TerminalRequest(mode='STRESS' if kind else 'ANALYZE',**raw)

@pytest.fixture(autouse=True)
def offline_catalog(monkeypatch):
    from app.main import app
    class Catalog:
        async def resolve(self,market):return profiles()[market]
    monkeypatch.setattr(app.state,'research_market_catalog',Catalog(),raising=False)

@pytest.fixture(scope='module')
def native():
    async def run():
        q=terminal_request()
        receipts,evidence=await execute_markets(SimulationService(),q.config,collect_accounting=True)
        a=assemble_analysis(q.config,receipts,evidence,q.risk_policy)
        return q,a,evidence
    return asyncio.run(run())

@pytest.mark.parametrize('markets',[('BTC',),('ETH','SOL'),('BTC','ETH','SOL')])
def test_prepare_exact_authority_and_native_constructors(markets):
    p=prepare(draft(markets),profiles())
    assert p.config.fingerprint()==p.config_fingerprint
    assert p.config.budget.total_equity_quote==p.allocated_quote+p.reserve_quote
    assert p.authority=='NONE' and p.read_only and p.execution_mode=='PAPER'
    for s in p.config.scenarios:
        i=s.captured.inputs()
        assert i.strategy.market==s.market and i.strategy.execution_mode=='PAPER'
        assert i.market_profile==profiles()[s.market]
        assert i.simulation.initial_equity_quote==next(a.allocated_equity_quote for a in p.config.allocations if a.market==s.market)


def test_prepare_equivalent_decimal_spelling_and_market_order():
    d=draft();raw=d.model_dump(mode='json');raw['allocations'].reverse()
    raw['budget']['total_equity_quote']='100000.000'
    for a in raw['allocations']:a['allocated_equity_quote']+='.'+'0'*18
    assert prepare(d,profiles()).config_fingerprint==prepare(PortfolioDraft.model_validate(raw),profiles()).config_fingerprint

@pytest.mark.parametrize('case',['negative','float','duplicate','reserve','overbudget','unsupported','extra','risk','levels'])
def test_invalid_drafts_rejected(case):
    raw=draft().model_dump(mode='json')
    if case=='negative':raw['allocations'][0]['allocated_equity_quote']='-1'
    elif case=='float':raw['allocations'][0]['allocated_equity_quote']=40000.0
    elif case=='duplicate':raw['allocations'][1]=raw['allocations'][0]
    elif case=='reserve':raw['budget']['minimum_reserve_quote']='6000'
    elif case=='overbudget':raw['budget']['total_equity_quote']='1'
    elif case=='unsupported':raw['allocations'][0]['market']='DOGE'
    elif case=='extra':raw['native_receipt']={}
    elif case=='risk':raw['risk_limits']['max_abs_net_exposure_quote']='100001'
    else:raw['strategy']['levels_per_side']=51
    with pytest.raises(ValueError):prepare(PortfolioDraft.model_validate(raw),profiles())

@pytest.mark.parametrize('kind',KINDS)
def test_prepare_six_stress_models(kind):
    r=request_for(kind,onset=7 if kind=='CONCENTRATION_STRESS' else 4)
    p=prepare(draft(stress=r.scenario),profiles())
    assert p.stress==r.scenario
    assert p.workload['executed_frames']==72


def test_preview_combined_budget_and_trace_estimate():
    scenario=request_for(frames=300,onset=4).scenario
    p=prepare(draft(frames=300,stress=scenario),profiles())
    assert p.trace_eligibility=='FINAL_ONLY' and p.workload['native_observations']==1500
    with pytest.raises(ValueError):prepare(draft(frames=501,stress=scenario),profiles())


def test_chart_native_binding_before_disposal_and_determinism(native):
    q,a,e=native
    c=project_chart(q.config,a,e)
    assert c==project_chart(q.config,a,e)
    assert c.status=='AVAILABLE' and len(c.points)==12 and not c.sampled
    assert c.equity_series_fingerprint==a.accounting.drawdown.equity_series_fingerprint
    assert c.native_evidence_fingerprints==tuple(x.evidence_fingerprint for x in e)
    assert c.points[-1].equity_quote==a.accounting.equity_quote
    assert c.points[-1].pnl_quote==a.accounting.pnl_quote
    assert max(p.drawdown_fraction for p in c.points)==a.accounting.drawdown.max_drawdown_fraction


def test_deterministic_sampling_preserves_extrema_shock_and_original_clock():
    points=tuple(ChartPoint(sequence=i+1,timestamp=DEFAULT_START+timedelta(seconds=i),equity_quote=str(1000+(i%37)),
        pnl_quote=str(i%37),drawdown_fraction=str(Decimal(i%31)/100)) for i in range(500))
    indices=sample_indices(points,context=(199,200,201,249,250,251))
    assert indices==sample_indices(points,context=(199,200,201,249,250,251))
    assert len(indices)<=120 and set((0,499,199,200,201,249,250,251))<=set(indices)
    for f in ('equity_quote','pnl_quote','drawdown_fraction'):
        assert min(getattr(points[i],f) for i in indices)==min(getattr(p,f) for p in points)
        assert max(getattr(points[i],f) for i in indices)==max(getattr(p,f) for p in points)


def test_excess_material_risk_context_rejected():
    points=tuple(ChartPoint(sequence=i+1,timestamp=DEFAULT_START+timedelta(seconds=i),equity_quote='1',pnl_quote='0',
        drawdown_fraction='0.5' if i%2 else '0') for i in range(500))
    with pytest.raises(ValueError,match='MATERIAL_CONTEXT'):sample_indices(points,thresholds=(Decimal('.2'),))

@pytest.mark.parametrize('case',['sparse','clock','substitution','financial'])
def test_ineligible_native_evidence_never_charts(native,case):
    q,a,e=native;raw=e[0].model_dump(exclude={'evidence_fingerprint'})
    if case=='sparse':raw['observations']=raw['observations'][1:]
    elif case=='clock':raw['observations'][0]['timestamp']+=timedelta(seconds=1)
    elif case=='substitution':raw['market_receipt_fingerprint']='a'*64
    else:raw['observations'][0]['equity_quote']+=1
    raw['observations']=tuple(NativeAccountingObservation.model_validate(p) for p in raw['observations'])
    bad=sealed(MarketAccountingEvidence,**raw)
    with pytest.raises(ValueError):project_chart(q.config,a,(bad,*e[1:]))

@pytest.mark.parametrize('classification',['FINAL_ONLY','INCOMPARABLE'])
def test_unavailable_histories_are_empty(classification):
    async def run():
        q=terminal_request();raw=q.config.model_dump()
        from app.research_replay.comparison import ComparisonConfigSnapshot
        for i,s in enumerate(raw['scenarios']):
            p=ComparisonConfigSnapshot.model_validate(s['captured']).inputs().model_dump(mode='json')
            if classification=='FINAL_ONLY':p['simulation']['trace_max_points']=4
            elif i==0:s['scenario']='QUIET'
            s['captured']=ComparisonConfigSnapshot.from_payload(p)
        from app.portfolio_research.models import PortfolioResearchConfig
        config=PortfolioResearchConfig.model_validate(raw)
        return await SimulationService().terminal_portfolio_research(request=TerminalRequest(mode='ANALYZE',config=config,config_fingerprint=config.fingerprint()))
    r=asyncio.run(run());b=r.baseline
    assert b.temporal.classification==classification and b.charts.status=='UNAVAILABLE' and not b.charts.points
    assert b.accounting.drawdown is None and b.risk.outcome=='BLOCKED'
    if classification=='INCOMPARABLE':assert b.accounting.equity_quote is None

@pytest.mark.parametrize('kind',KINDS)
async def test_native_terminal_six_scenarios_and_original_compatibility(kind):
    q=terminal_request(kind);service=SimulationService()
    t=await service.terminal_portfolio_research(request=q)
    original=await service.stress_portfolio_research(request=q.stress_request())
    assert t.source_result_fingerprint==original.evidence_fingerprint
    assert t.metrics==original.metrics and t.risk_transition==original.risk_transition
    for leg,native_leg in ((t.baseline,original.baseline),(t.stressed,original.stressed)):
        assert leg.analysis_fingerprint==native_leg.evidence_fingerprint
        assert leg.accounting==native_leg.accounting and leg.risk==native_leg.risk
        assert leg.charts.status=='AVAILABLE' and len(leg.charts.points)==12
    assert len(bounded_json(t).encode())<200000
    assert TerminalResult.model_validate_json(t.model_dump_json())==t

@pytest.mark.parametrize('mode',['RUN','ANALYZE'])
async def test_nonstress_modes_share_native_analysis_and_run_contract(mode):
    q=terminal_request().model_copy(update={'mode':mode});service=SimulationService()
    t=await service.terminal_portfolio_research(request=q)
    a=await service.analyze_portfolio_research(request={k:v for k,v in q.model_dump().items() if k not in ('contract_version','mode','scenario')})
    r=await service.run_portfolio_research(request={'config':q.config,'config_fingerprint':q.config_fingerprint})
    assert t.baseline.analysis_fingerprint==a.evidence_fingerprint
    assert t.baseline.bundle_fingerprint==r.bundle_fingerprint
    assert t.stressed is None

async def test_one_admission_no_duplicate_engine_runs(monkeypatch):
    from app.simulation.engine import SimulationEngine
    calls=[];original=SimulationEngine.run
    async def counted(self,*,dataset,**kw):
        calls.append(dataset.market);return await original(self,dataset=dataset,**kw)
    monkeypatch.setattr(SimulationEngine,'run',counted)
    worker=SimulationExecutor();submissions=[];submit=worker._pool.submit
    def record(*args,**kw):submissions.append(args[1]);return submit(*args,**kw)
    monkeypatch.setattr(worker._pool,'submit',record)
    try:await worker.execute('terminal_portfolio_research',request=terminal_request('CORRELATED_SELLOFF'))
    finally:await worker.shutdown()
    assert submissions==['terminal_portfolio_research'] and calls==['BTC','ETH','SOL','BTC','ETH','SOL']

@pytest.mark.parametrize('path',['preview','terminal'])
def test_http_bounded_no_store_and_operational_isolation(research_client,path):
    client,rt=research_client;before=authority(rt)
    q=draft().model_dump(mode='json') if path=='preview' else terminal_request().model_dump(mode='json')
    r=client.post(URL+path,json=q)
    assert r.status_code==200,r.text
    assert r.headers['cache-control']=='no-store' and len(r.content)<=200000
    assert authority(rt)==before

@pytest.mark.parametrize('case',['receipt','result','fingerprint','authority','mode'])
def test_client_authoritative_evidence_rejected_before_admission(research_client,monkeypatch,case):
    from app.main import app
    client,_=research_client;q=terminal_request().model_dump(mode='json')
    if case in ('receipt','result'):q[case]={'authoritative':True}
    elif case=='fingerprint':q['config_fingerprint']='f'*64
    elif case=='authority':q['config']['authority']='LIVE'
    else:q['mode']='EXECUTE'
    async def forbidden(*args,**kw):pytest.fail('invalid request admitted')
    monkeypatch.setattr(app.state.simulation_executor,'execute',forbidden)
    r=client.post(URL+'terminal',json=q)
    assert r.status_code==422 and r.headers['cache-control']=='no-store'

@pytest.mark.parametrize('exception,status',[(ResearchBusyError(),429),(ResearchUnavailableError(),503),(RuntimeError('/private/secret'),500),(ValueError('/private/secret'),422)])
def test_sanitized_failure_states(research_client,monkeypatch,exception,status):
    from app.main import app
    client,_=research_client
    async def broken(*a,**kw):raise exception
    monkeypatch.setattr(app.state.simulation_executor,'execute',broken)
    r=client.post(URL+'terminal',json=terminal_request().model_dump(mode='json'))
    assert r.status_code==status and '/private/secret' not in r.text


def test_response_cap_checked_before_http_200(research_client,monkeypatch):
    client,_=research_client;q=terminal_request(markets=('BTC',)).model_dump(mode='json')
    result=asyncio.run(SimulationService().terminal_portfolio_research(request=q))
    size=len(result.model_dump_json().encode())
    async def computed(self,**kw):return result
    monkeypatch.setattr(SimulationService,'terminal_portfolio_research',computed)
    monkeypatch.setattr(aggregation,'MAX_RESPONSE_BYTES',size)
    assert len(client.post(URL+'terminal',json=q).content)==size
    monkeypatch.setattr(aggregation,'MAX_RESPONSE_BYTES',size-1)
    assert client.post(URL+'terminal',json=q).status_code==413

@pytest.mark.parametrize('path',['preview','terminal'])
@pytest.mark.parametrize('chunked',[True,False])
def test_request_cap_unchanged(research_client,path,chunked):
    client,_=research_client
    content=iter([b'x'*40000,b'x'*40000]) if chunked else b'x'*65537
    assert client.post(URL+path,content=content).status_code==413


def test_busy_stressed_worker_retains_one_slot(research_client,monkeypatch):
    client,_=research_client;started,release=Event(),Event();original=SimulationService._run_portfolio_dataset
    async def held(self,**kw):started.set();assert release.wait(15);return await original(self,**kw)
    monkeypatch.setattr(SimulationService,'_run_portfolio_dataset',held)
    with ThreadPoolExecutor(max_workers=1) as caller:
        future=caller.submit(client.post,URL+'terminal',json=terminal_request('CORRELATED_SELLOFF',markets=('BTC',)).model_dump(mode='json'))
        try:
            assert started.wait(10)
            assert client.post(URL+'terminal',json=terminal_request().model_dump(mode='json')).status_code==429
            assert client.post('/api/v1/simulation/run',json={'frames':2}).status_code==429
        finally:release.set()
        assert future.result(timeout=15).status_code==200


def test_local_http_integration(tmp_path):
    with local_server(tmp_path) as c:
        r=c.post(URL+'preview',json=draft(('BTC',)).model_dump(mode='json'))
        assert r.status_code==200,r.text
        p=r.json()
        r=c.post(URL+'terminal',json={'mode':'ANALYZE','config':p['config'],'config_fingerprint':p['config_fingerprint'],'risk_policy':p['risk_policy']})
        assert r.status_code==200 and r.json()['baseline']['charts']['status']=='AVAILABLE'
