"""Run measured comparison acceptance through the existing single-slot worker.

Standalone acceptance command, kept outside routine pytest collection because
near-limit jobs are deliberately expensive. No additional application worker.
"""
import argparse
import asyncio
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import tempfile
import time

from app.agents.config import AgentConfig
from app.research_replay.storage import HistoricalStorage
from app.research_replay.transport import ScenarioHistoricalRequest
from app.risk.firewall import RiskFirewallConfig
from app.simulation.executor import SimulationExecutor
from app.strategy.models import StrategyConfig
from phase1641_fixtures import admit
from phase165d_fixtures import bounded_dataset
from test_phase146_research_markets import demo


async def main(output, selected_case='all'):
    report = dict(status='FAIL', fixture_notice='Generated synthetic PAPER evidence, no exchange authentication',
        environment=dict(platform=platform.platform(), python=platform.python_version(), logical_cpus=os.cpu_count()), cases=[])
    cases = [(1000,1,0,False,False), (4999,1,0,False,False), (64,32,0,False,False),
             (4,1,1000,False,False), (128,1,0,True,False), (64,32,0,False,True)]
    if selected_case=='high-gaps':cases=cases[-1:]
    try:
        for frames, segments, missing, modeled, high_gaps in cases:
            with tempfile.TemporaryDirectory(prefix='phase165d-') as temp:
                root=Path(temp);(root/'vault').mkdir(mode=0o700)
                vault=HistoricalStorage(root/'vault')
                generated=bounded_dataset(frames,segments,missing,modeled)
                if high_gaps:
                    from app.research_replay.validation import validate_bytes
                    raw=generated.model_dump(mode='json');raw['dataset_fingerprint']=None
                    anchor=generated.gaps[0].start_at
                    # Many disjoint declared outages in one unobserved interval
                    # remain one reset; no fabricated market observations.
                    raw['gaps']=[dict(start_at=(anchor+timedelta(microseconds=2*i)).isoformat(),
                        end_at=(anchor+timedelta(microseconds=2*i+1)).isoformat(),reason='DISCONNECT')
                        for i in range(994)]+raw['gaps'][1:]
                    generated=validate_bytes(json.dumps(raw).encode())
                d=admit(vault,root/'incoming',generated)
                original={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'vault').glob('*.json')}
                historical=dict(dataset_id=d.dataset_id,dataset_fingerprint=d.dataset_fingerprint,market='BTC',
                    execution=dict(size_decimals=5),max_frames=5000,trace_max_points=250,
                    policy=dict(max_component_age_ms=1000))
                if modeled:
                    historical['execution']['paper']=dict(mode='MODELED_CROSSING',order_latency_ms=1,
                        cancel_latency_ms=2,slippage_bps='1',depth_sensitive=True,participation_rate='0.5',max_fill_fraction='0.5')
                request=ScenarioHistoricalRequest(research_market='BTC',frames=min(5000,frames+1),
                    simulation=dict(max_frames=5000,trace_max_points=250),historical=historical,trace_point_limit=250)
                worker=SimulationExecutor()
                inputs=dict(storage_root=vault.root,request=request,strategy=StrategyConfig(),agents=AgentConfig(),
                    risk=RiskFirewallConfig(enabled=not modeled),market_profile=demo('BTC'))
                before_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                started=time.perf_counter()
                try:
                    result=await worker.execute('compare_scenario_historical',**inputs)
                    elapsed=time.perf_counter()-started
                    serialized=time.perf_counter();wire=result.model_dump_json().encode();serialization=time.perf_counter()-serialized
                    assert not worker._busy
                    assert result.segment_count==segments
                    assert sum(s.frame_count for s in result.segments)==frames
                    assert len(wire)<=1_000_000
                    assert len(result.historical_trace.points)==min(250,result.segments[0].frame_count)
                    fills=next(r for r in result.receipt.rows if r.name=='fill_count').historical_segment.value
                    if modeled:assert fills>0
                    measured=dict(historical_frames=frames,scenario_frames=request.frames,source_observations=len(d.observations),
                        segments=segments,declared_gaps=len(result.declared_gaps),issues=len(result.issues)+result.omitted_issues,omitted_issues=result.omitted_issues,
                        modeled=modeled,worker_seconds=round(elapsed,6),serialization_seconds=round(serialization,6),response_bytes=len(wire),
                        scenario_trace_points=len(result.scenario_trace.points),historical_trace_points=len(result.historical_trace.points),
                        fills=str(fills),process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        previous_process_peak_rss_kib=before_rss,worker_released=True)
                    if segments==32:
                        original_receipt=result.receipt.receipt_fingerprint
                        reruns=[]
                        for index in (31,0):
                            request=request.model_copy(update={'segment_index':index})
                            started=time.perf_counter()
                            rerun=await worker.execute('compare_scenario_historical',**{**inputs,'request':request})
                            reruns.append(dict(segment_index=index,seconds=round(time.perf_counter()-started,6)))
                            assert rerun.receipt.selected_segment_index==index and not worker._busy
                        assert rerun.receipt.receipt_fingerprint==original_receipt
                        measured['selection_reruns']=reruns
                    assert original=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'vault').glob('*.json')}
                    measured['source_files_unchanged']=True
                    report['cases'].append(measured)
                    print(json.dumps(measured),flush=True)
                finally:await worker.shutdown()
        report['status']='PASS'
    finally:
        path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--case',choices=['all','high-gaps'],default='all')
    args=parser.parse_args()
    asyncio.run(main(args.output,args.case))
