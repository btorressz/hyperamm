"""Native HTTP, persisted wire contracts, lifecycle and bounded replay acceptance."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.research_replay.contracts import HistoricalReplayResult, ReplaySegmentResult
from app.research_replay.summary import HistoricalDatasetSummary
from app.research_replay.provenance import describe_provenance
from app.simulation.models import stable_fingerprint
from app.simulation.service import SimulationService
from test_phase162_replay import vault, replay_client, request_for, capture, inputs
from phase1641_fixtures import dataset, admit
from test_phase152_live_streams import streams

FIXTURE = Path(__file__).resolve().parents[2] / 'frontend/tests/fixtures/phase1641-native.json'

@pytest.mark.parametrize('case', json.loads(FIXTURE.read_text())['cases'])
async def test_serialized_native_frontend_fixture_reproduces_from_existing_engine(vault, tmp_path, case):
    market = case['summary']['market']
    kind = {'BTC':'gap','ETH':'complete','SOL':'generation'}[market]
    d = admit(vault, tmp_path/'incoming', dataset(kind,market))
    args = inputs(vault,d)
    args['request'] = type(args['request']).model_validate(case['result']['request'])
    actual = await SimulationService().replay_history(**args)
    assert actual.model_dump(mode='json') == case['result']
    assert HistoricalDatasetSummary.from_dataset(d).model_dump(mode='json') == case['summary']
    assert describe_provenance(d).model_dump(mode='json') == case['provenance']

@pytest.mark.parametrize('change', ['dataset','run','metrics','trace','baseline'])
def test_self_consistent_archive_hash_does_not_allow_segment_substitution(change):
    raw = deepcopy(json.loads(FIXTURE.read_text())['cases'][0]['result']['segments'][0])
    field = 'baseline_result_json' if change == 'baseline' else 'simulation_result_json'
    archive = json.loads(raw[field])
    if change == 'dataset': archive['dataset_fingerprint'] = 'b'*64
    if change == 'run': archive['run_fingerprint'] = 'b'*64
    if change == 'metrics': archive['metrics']['session_pnl'] = '1'
    if change == 'trace': archive['trace'][0]['sequence'] = 999
    if change == 'baseline': archive = json.loads(raw['simulation_result_json'])
    raw[field] = json.dumps(archive)
    raw['baseline_result_fingerprint' if change == 'baseline' else 'simulation_result_fingerprint'] = stable_fingerprint(archive)
    with pytest.raises(ValidationError): ReplaySegmentResult.model_validate(raw)


def test_summary_http_empty_safe_errors_and_no_mutation(vault, replay_client, monkeypatch, tmp_path):
    from app.main import app
    from app.infrastructure.research import ResearchUnavailableError
    from app.simulation.executor import ResearchBusyError
    client, rt = replay_client
    from test_phase14_research_vault import authority
    before=deepcopy(authority(rt))
    path = '/api/v1/historical-replay/'
    assert client.get(path+'dataset-summaries').json() == []
    assert client.get(path+'dataset-summaries',headers={'Host':'attacker.example'}).status_code == 403
    assert client.get(path+'dataset-summaries',headers={'Origin':'https://attacker.example'}).status_code == 403
    assert client.post(path+'run',content=b' '*65537,headers={'Content-Type':'application/json'}).status_code == 413
    for market in ('BTC','ETH','SOL'):
        admit(vault,tmp_path/'incoming',dataset('complete',market))
    response = client.get(path+'dataset-summaries')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert len(response.json()) == 3
    assert not {'observations','order_book','perp_context','source_id'} & set(response.json()[0])
    row = response.json()[0]
    assert client.get(path+'provenance',params={'dataset_id':row['dataset_id']}).status_code == 200
    d = vault.read(row['dataset_id']); body=request_for(d).model_dump(mode='json')
    assert client.post(path+'run',json=body).status_code == 200
    rejected = client.post(path+'run',json={**body,'dataset_fingerprint':'0'*64})
    assert rejected.status_code == 422 and rejected.json()['detail']['issues'][0]['code'] == 'IDENTITY_MISMATCH'
    assert client.get(path+'provenance',params={'dataset_id':'?private'}).status_code == 422
    missing = admit(vault,tmp_path/'incoming',dataset('missing'))
    rejection=client.post(path+'run',json=request_for(missing).model_dump(mode='json'))
    assert rejection.status_code == 422 and rejection.json()['detail']['issues'][-1]['code'] == 'NO_VIABLE_FRAMES'
    for exc,code in [(ResearchBusyError('busy'),429),(ResearchUnavailableError(),503),
                     (RuntimeError('/private/provider/credentials'),500)]:
        class Failed:
            async def execute(self,*args,**kwargs): raise exc
        with monkeypatch.context() as m:
            m.setattr(app.state,'simulation_executor',Failed())
            r=client.get(path+'dataset-summaries');assert r.status_code == code
            assert '/private' not in r.text and 'secret' not in r.text and 'credentials' not in r.text
            assert r.headers['cache-control'] == 'no-store'
    root=Path(vault.root);root.chmod(0o755)
    try: assert client.get(path+'dataset-summaries').status_code == 422
    finally: root.chmod(0o700)
    next(root.glob('*.json')).write_text('{}')
    r=client.get(path+'dataset-summaries');assert r.status_code == 422 and str(root) not in r.text
    assert authority(rt) == before
    monkeypatch.setattr(app.state,'historical_replay_root',None)
    assert client.get(path+'dataset-summaries').status_code == 503


@pytest.mark.parametrize('frames,segments', [(4999,1),(64,32)])
async def test_bounded_retained_evidence_and_maximum_segments(vault, frames, segments, record_property):
    # Storage admits at most 5,000 observations, normally two per viable frame.
    times=tuple(i/10 for i in range(2500)) if segments == 1 else tuple(t for i in range(segments) for t in (i*3,i*3+.1))
    raw=capture(times=times,native=False).model_dump(mode='json')
    if segments == 1:
        from test_phase161a_contracts import T
        # First complete batch plus one new component per receipt: 4,999
        # viable frames is the reachable maximum under the 5,000-event vault cap.
        raw['dataset_fingerprint']=None
        for i,p in enumerate(raw['observations']):
            p['received_at']=(T+timedelta(milliseconds=max(0,i-1))).isoformat()
            p['source_timestamp']=None
        raw['coverage_end']=raw['observations'][-1]['received_at']
    from app.research_replay.validation import validate_bytes
    d=vault.save(validate_bytes(json.dumps(raw).encode()))
    args=inputs(vault,d,max_frames=5000,trace_max_points=500,policy={'max_component_age_ms':1000})
    payload=args['request'].model_dump(mode='json')
    payload['execution']['paper']={'mode':'MODELED_CROSSING','order_latency_ms':1,'depth_sensitive':True}
    args['request']=type(args['request']).model_validate(payload)
    result=await SimulationService().replay_history(**args)
    assert result.frame_count == frames and len(result.segments) == segments
    assert HistoricalReplayResult.model_validate_json(result.model_dump_json()) == result
    wire_bytes=len(result.model_dump_json().encode())
    record_property('replay_bytes',wire_bytes)
    record_property('viable_frames',result.frame_count)
    assert wire_bytes < 64_000_000


def test_actual_http_crossing_fills_and_decimal_comparison_preserve_preconfigured_risk(vault, replay_client, monkeypatch, tmp_path):
    from test_phase14_research_vault import authority
    client,rt=replay_client
    # This explicit test-only setup is separate from default HALT/no-fill
    # acceptance. Accounting and FinalQuoteAuthorization remain enforced.
    monkeypatch.setattr(rt,'risk_config',rt.risk_config.model_copy(update={'enabled':False}))
    before=deepcopy(authority(rt))
    d=admit(vault,tmp_path/'incoming',dataset('crossing'))
    body=request_for(d).model_dump(mode='json')
    body['execution']['paper']=dict(mode='MODELED_CROSSING',order_latency_ms=1,cancel_latency_ms=1,
        slippage_bps='1',depth_sensitive=True,participation_rate='0.5',max_fill_fraction='0.5')
    response=client.post('/api/v1/historical-replay/run',json=body)
    assert response.status_code == 200,response.text
    result=HistoricalReplayResult.model_validate(response.json());s=result.segments[0]
    assert s.fill_count > 0
    archive=json.loads(s.simulation_result_json);base=json.loads(s.baseline_result_json)
    assert archive['vault']['execution_accounting']['execution_accounting_consistent']
    assert all('HYPOTHETICAL' in f['source'] for f in archive['fills'])
    assert s.session_pnl_delta == s.session_pnl - Decimal(base['metrics']['session_pnl'])
    assert s.fill_count_delta == s.fill_count - base['metrics']['fill_count']
    assert authority(rt) == before


async def test_http_replay_leaves_active_phase15_sdk_subscriptions_and_consumers_intact(vault, replay_client, streams, monkeypatch):
    from app.main import app
    from test_phase152_live_streams import eventually
    service,sdk,clock=streams
    monkeypatch.setattr(app.state,'live_market_streams',service,raising=False)
    client,rt=replay_client
    queues={m:service.subscribe(m) for m in ('BTC','ETH','SOL')}
    connection=sdk.clients[-1]
    handles=tuple(connection.handles)
    generation=service._generation
    snapshots={m:service.snapshot(m).model_dump(mode='json') for m in queues}
    try:
        for market in queues:
            d=vault.save(capture(market=market))
            body=request_for(d).model_dump(mode='json')
            body['execution']['paper']={'mode':'MODELED_CROSSING','depth_sensitive':True}
            response=client.post('/api/v1/historical-replay/run',json=body)
            assert response.status_code == 200,response.text
        assert app.state.live_market_streams is service
        assert service._generation == generation and sdk.clients == [connection]
        assert tuple(connection.handles) == handles and not connection.closed
        assert service._subscribers == {q:m for m,q in queues.items()}
        assert {m:service.snapshot(m).model_dump(mode='json') for m in queues} == snapshots
        for market,q in queues.items():
            assert q.qsize() == 1
            q.get_nowait()
            sdk.emit(market,'l2Book');sdk.emit(market,'activeAssetCtx')
        await eventually(lambda:all(service.snapshot(m).observation_status=='AVAILABLE' for m in queues))
        assert all(not q.empty() for q in queues.values())
    finally:
        for q in queues.values():service.unsubscribe(q)
