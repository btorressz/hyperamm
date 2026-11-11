"""Real HTTP -> one worker -> existing scenario/replay -> quantitative receipt."""
import asyncio
from copy import deepcopy
from pathlib import Path
from threading import Event

import httpx
import pytest
from pydantic import ValidationError

from app.research_replay.transport import ScenarioHistoricalRequest, ScenarioHistoricalResponse
from app.research_replay.quantitative import QuantitativeComparison
from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.service import SimulationService
from phase1641_fixtures import admit, dataset
from test_phase162_replay import vault, replay_client
from test_phase14_research_vault import authority, proposal
from test_phase146_research_markets import demo

URL='/api/v1/research-comparison/scenario-historical'


def body(vault,tmp_path,market='BTC',kind='complete',**overrides):
    stored=admit(vault,tmp_path/'incoming',dataset(kind,market))
    value=dict(scenario='QUIET',frames=4,research_market=market,
        simulation=dict(max_frames=4,record_trace=True,trace_max_points=4),
        historical=dict(dataset_id=stored.dataset_id,dataset_fingerprint=stored.dataset_fingerprint,
            market=market,execution=dict(size_decimals={'BTC':5,'ETH':4,'SOL':2}[market]),max_frames=4,trace_max_points=4),
        segment_index=0,include_traces=True,trace_point_limit=4)
    return {**value,**overrides}


@pytest.fixture
def comparison_client(replay_client,monkeypatch):
    from app.main import app
    class Catalog:
        async def resolve(self,market):return demo(market)
    monkeypatch.setattr(app.state,'research_market_catalog',Catalog(),raising=False)
    return replay_client


@pytest.mark.parametrize('market',['BTC','ETH','SOL'])
@pytest.mark.parametrize('modeled',[False,True])
def test_real_http_receipt_bounded_projection_and_exact_zero(comparison_client,vault,tmp_path,market,modeled):
    client,rt=comparison_client
    request=body(vault,tmp_path,market)
    if modeled:request['historical']['execution']['paper']=dict(mode='MODELED_CROSSING',order_latency_ms=1,depth_sensitive=True)
    before=deepcopy(authority(rt))
    response=client.post(URL,json=request)
    assert response.status_code==200,response.text
    report=ScenarioHistoricalResponse.model_validate(response.json())
    assert len(response.content)<1_000_000
    assert 'simulation_result_json' not in response.text and 'book_observation' not in response.text
    assert response.headers['cache-control']=='no-store'
    assert report.receipt.foundation.classification=='CONTEXT_ONLY'
    assert report.receipt.foundation.historical.original_dataset_fingerprint!=report.receipt.foundation.historical.engine_dataset_fingerprint
    assert len(report.scenario_trace.points)==len(report.historical_trace.points)==4
    assert len(report.historical_trace.source_times)==4
    assert not report.provenance.source_authenticated
    assert next(r for r in report.receipt.rows if r.name=='fill_count').historical_segment.value==0
    assert next(r for r in report.receipt.rows if r.name=='fill_activity_ratio').historical_segment.value is None
    assert QuantitativeComparison.model_validate_json(report.receipt.model_dump_json())==report.receipt
    assert authority(rt)==before


@pytest.mark.parametrize('kind',['gap','generation'])
def test_segment_selection_reruns_independently(comparison_client,vault,tmp_path,kind):
    client,_=comparison_client
    request=body(vault,tmp_path,kind=kind)
    first=client.post(URL,json=request)
    assert first.status_code==200,first.text
    request['segment_index']=1
    second=client.post(URL,json=request)
    assert second.status_code==200,second.text
    a,b=(ScenarioHistoricalResponse.model_validate(r.json()) for r in (first,second))
    assert a.segment_count==b.segment_count==2
    assert b.receipt.selected_segment_index==1
    assert b.historical_trace.run_fingerprint==b.segments[1].run_fingerprint
    assert a.historical_trace.run_fingerprint!=b.historical_trace.run_fingerprint
    assert not b.receipt.cross_segment_aggregation_allowed
    assert 'HISTORICAL_SEGMENT_RESETS' in b.receipt.foundation.reasons
    assert next(r for r in a.receipt.rows if r.name=='starting_equity').historical_segment.value==next(r for r in b.receipt.rows if r.name=='starting_equity').historical_segment.value
    request['segment_index']=2
    assert client.post(URL,json=request).status_code==422


def test_cross_market_blocks_metrics_and_traces(comparison_client,vault,tmp_path):
    client,_=comparison_client
    request=body(vault,tmp_path,research_market='ETH')
    response=client.post(URL,json=request)
    assert response.status_code==200,response.text
    report=ScenarioHistoricalResponse.model_validate(response.json())
    assert report.receipt.display_policy=='BLOCKED' and not report.receipt.rows
    assert not report.scenario_trace.points and not report.historical_trace.points
    assert report.scenario_trace.omission=='INCOMPARABLE'


@pytest.mark.parametrize('patch',[{'strategy':{}},{'risk':{}},{'scenario_result':{}},{'frames':True},{'frames':'4'},
    {'trace_point_limit':251},{'segment_index':32},{'include_traces':'true'},{'research_market':'DOGE'},
    {'simulation':{'max_frames':'4'}},{'simulation':{'accounting':{'signer':'private'}}}])
def test_forged_or_invalid_requests_fail_closed(comparison_client,vault,tmp_path,patch):
    client,_=comparison_client
    request=body(vault,tmp_path,**patch)
    assert client.post(URL,json=request).status_code==422


def test_storage_identity_and_bounds_errors(comparison_client,vault,tmp_path,monkeypatch):
    from app.main import app
    client,_=comparison_client
    request=body(vault,tmp_path)
    changed=deepcopy(request);changed['historical']['dataset_fingerprint']='f'*64
    assert client.post(URL,json=changed).status_code==422
    incomplete=body(vault,tmp_path,kind='missing')
    assert client.post(URL,json=incomplete).status_code==422
    assert client.post(URL,content=b' '*65537,headers={'Content-Type':'application/json'}).status_code==413
    monkeypatch.setattr(app.state,'historical_replay_root',None)
    assert client.post(URL,json=request).status_code==503
    bad=tmp_path/'public';bad.mkdir();bad.chmod(0o755)
    monkeypatch.setattr(app.state,'historical_replay_root',str(bad))
    response=client.post(URL,json=request)
    assert response.status_code==503 and str(tmp_path) not in response.text
    monkeypatch.setattr(app.state,'historical_replay_root',vault.root)
    import hashlib
    path=Path(vault.root)/(hashlib.sha256(request['historical']['dataset_id'].encode()).hexdigest()+'.json');path.write_text('{}')
    assert client.post(URL,json=request).status_code==422


@pytest.mark.parametrize('include,cap,omission',[(False,4,'NOT_REQUESTED'),(True,2,'POINT_LIMIT'),(True,0,'POINT_LIMIT')])
def test_trace_omissions_are_explicit(comparison_client,vault,tmp_path,include,cap,omission):
    client,_=comparison_client
    response=client.post(URL,json=body(vault,tmp_path,include_traces=include,trace_point_limit=cap))
    assert response.status_code==200,response.text
    r=ScenarioHistoricalResponse.model_validate(response.json())
    assert len(r.scenario_trace.points)==(cap if include else 0)
    assert r.scenario_trace.omission==omission
    assert r.scenario_trace.omitted_points==4-len(r.scenario_trace.points)


@pytest.mark.parametrize('modeled',[False,True])
@pytest.mark.parametrize('kill',[False,True])
async def test_operational_authority_storage_and_signer_isolation(comparison_client,vault,tmp_path,kill,modeled):
    from app.execution.models import OrderRequest
    from app.market_data.mock import MockMarketDataAdapter
    client,rt=comparison_client
    request=body(vault,tmp_path)
    request['research']=proposal().model_dump(mode='json')
    request['research']['config']['initial_equity_quote']='12345.123456789123456789'
    if modeled:request['historical']['execution']['paper']=dict(mode='MODELED_CROSSING',order_latency_ms=1)
    frame=MockMarketDataAdapter().snapshot_for(4)
    await rt.market._accept(frame);await rt.refresh_once()
    await rt.paper.submit_orders([OrderRequest(client_order_id='c2-seed',market='ETH',side='BID',price=frame.best_ask,size='0.1')])
    await rt.refresh_once()
    rt.strategy.running=True
    rt.accounting_service.reserve(rt.quotes,await rt.execution.get_open_orders())
    if kill:await rt.activate_kill();await rt.refresh_once()
    before=deepcopy(authority(rt))
    signer=(id(rt.testnet),rt.testnet.private_key,rt.testnet.account_address,rt.testnet.enabled)
    stored={p.name:p.read_bytes() for p in Path(vault.root).glob('*.json')}
    response=client.post(URL,json=request)
    assert response.status_code==200,response.text
    assert authority(rt)==before
    assert signer==(id(rt.testnet),rt.testnet.private_key,rt.testnet.account_address,rt.testnet.enabled)
    assert stored=={p.name:p.read_bytes() for p in Path(vault.root).glob('*.json')}


@pytest.mark.parametrize('cancel',[False,True])
async def test_combined_worker_cancellation_keeps_global_capacity(vault,tmp_path,monkeypatch,cancel):
    from app.main import app
    from app.config import Settings
    from app.runtime import HyperAmmRuntime
    worker=SimulationExecutor();rt=HyperAmmRuntime(Settings(_env_file=None))
    monkeypatch.setattr(app.state,'runtime',rt,raising=False)
    monkeypatch.setattr(app.state,'simulation_executor',worker,raising=False)
    monkeypatch.setattr(app.state,'historical_replay_root',vault.root,raising=False)
    class Catalog:
        async def resolve(self,market):return demo(market)
    monkeypatch.setattr(app.state,'research_market_catalog',Catalog(),raising=False)
    request=body(vault,tmp_path)
    original=SimulationService.replay_history
    loop=asyncio.get_running_loop();started=asyncio.Event();release=Event()
    async def held(self,**inputs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        return await original(self,**inputs)
    monkeypatch.setattr(SimulationService,'replay_history',held)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost') as client:
        job=asyncio.create_task(client.post(URL,json=request))
        try:
            await asyncio.wait_for(started.wait(),5)
            if cancel:
                job.cancel()
                with pytest.raises(asyncio.CancelledError):await job
            assert (await client.post(URL,json=request)).status_code==429
            assert (await client.get('/api/v1/health')).status_code==200
            for operation in ('run_scenario','optimize','replay_history','historical_catalog'):
                with pytest.raises(ResearchBusyError):await worker.execute(operation)
        finally:
            release.set()
            if not cancel:assert (await job).status_code==200
            await worker.shutdown()
    assert not worker._busy


def test_response_budget_and_sanitized_failure(comparison_client,vault,tmp_path,monkeypatch):
    import app.research_replay.transport as transport
    client,_=comparison_client;request=body(vault,tmp_path)
    monkeypatch.setattr(transport,'MAX_RESPONSE_BYTES',100)
    assert client.post(URL,json=request).status_code==422
    async def fail(self,**kwargs):raise RuntimeError('/private/signer secret')
    monkeypatch.setattr(SimulationService,'compare_scenario_historical',fail)
    response=client.post(URL,json=request)
    assert response.status_code==500 and 'private' not in response.text and 'secret' not in response.text


@pytest.mark.parametrize('tamper',['scenario','historical'])
def test_combined_service_rejects_tampered_engine_receipts(comparison_client,vault,tmp_path,monkeypatch,tamper):
    client,_=comparison_client
    if tamper=='scenario':
        original=SimulationService.run_scenario
        async def corrupt(self,**kwargs):
            result=await original(self,**kwargs)
            return result.model_copy(update={'result':result.result.model_copy(update={'run_fingerprint':'0'*64})})
        monkeypatch.setattr(SimulationService,'run_scenario',corrupt)
    else:
        original=SimulationService.replay_history
        async def corrupt(self,**kwargs):
            result=await original(self,**kwargs)
            return result.model_copy(update={'result_fingerprint':'0'*64})
        monkeypatch.setattr(SimulationService,'replay_history',corrupt)
    assert client.post(URL,json=body(vault,tmp_path)).status_code==422


from test_phase152_live_streams import streams, eventually


async def test_combined_operation_preserves_phase15_subscriptions(comparison_client,vault,tmp_path,streams,monkeypatch):
    from app.main import app
    service,sdk,_=streams
    monkeypatch.setattr(app.state,'live_market_streams',service,raising=False)
    client,_=comparison_client
    queues={m:service.subscribe(m) for m in ('BTC','ETH','SOL')}
    connection=sdk.clients[-1]
    before=(service._generation,tuple(connection.handles),{m:service.snapshot(m) for m in queues})
    try:
        for market in queues:
            response=client.post(URL,json=body(vault,tmp_path,market))
            assert response.status_code==200,response.text
        assert sdk.clients==[connection] and not connection.closed
        assert before==(service._generation,tuple(connection.handles),{m:service.snapshot(m) for m in queues})
        assert service._subscribers=={q:m for m,q in queues.items()}
        for m,q in queues.items():
            q.get_nowait();sdk.emit(m,'l2Book');sdk.emit(m,'activeAssetCtx')
        await eventually(lambda:all(service.snapshot(m).observation_status=='AVAILABLE' for m in queues))
        assert all(not q.empty() for q in queues.values())
    finally:
        for q in queues.values():service.unsubscribe(q)
