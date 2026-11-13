"""Serial cold-process native measurements; run from backend with PYTHONPATH=tests."""
import argparse
import asyncio
import json
import resource
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from app.portfolio_research.preview import prepare
from app.portfolio_research.terminal_models import TerminalRequest, TerminalResult
from app.simulation.executor import SimulationExecutor
from app.simulation.service import SimulationService
from test_phase175_terminal import draft, profiles
from phase174_fixtures import request_for

CASES = [('BTC',3000,False), ('BTC,ETH',1500,False), ('BTC,ETH,SOL',1000,False),
         ('BTC,ETH,SOL',500,False), ('BTC,ETH,SOL',250,True),
         ('BTC,ETH,SOL',300,True), ('BTC,ETH,SOL',500,True)]


async def measure(index):
    markets, frames, stress = CASES[index]
    scenario = request_for(frames=frames,onset=30,duration=60).scenario if stress else None
    d = draft(tuple(markets.split(',')), stress=scenario).model_copy(update={'frames': frames})
    p = prepare(d, profiles())
    q = TerminalRequest(mode='STRESS' if stress else 'ANALYZE', config=p.config,
                        config_fingerprint=p.config_fingerprint, risk_policy=p.risk_policy, scenario=p.stress)
    observations = []
    original = SimulationService.run_scenario
    original_dataset = SimulationService._run_portfolio_dataset
    async def counted(self, **kw):
        result = await original(self, **kw)
        observations.append(len(result.result.trace))
        return result
    async def dataset_counted(self, **kw):
        result = await original_dataset(self, **kw)
        observations.append(len(result.result.trace))
        return result
    SimulationService.run_scenario = counted
    SimulationService._run_portfolio_dataset = dataset_counted
    worker = SimulationExecutor()
    start = perf_counter()
    try:
        result = await worker.execute('terminal_portfolio_research', request=q)
        seconds = perf_counter()-start
        assert TerminalResult.model_validate_json(result.model_dump_json()) == result
        assert not worker._busy
    finally:
        await worker.shutdown()
        SimulationService.run_scenario = original
        SimulationService._run_portfolio_dataset = original_dataset
    row = dict(markets=markets.split(','), frames_per_market_per_leg=frames, legs=2 if stress else 1,
        seconds=round(seconds,4),peak_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),
        request_bytes=len(q.model_dump_json().encode()),response_bytes=len(result.model_dump_json().encode()),
        retained_native_observations=sum(observations), native_runs=len(observations),workload=p.workload,
        baseline_chart_points=len(result.baseline.charts.points),
        stressed_chart_points=len(result.stressed.charts.points) if result.stressed else 0,
        temporal=result.baseline.temporal.classification, risk_outcome=result.baseline.risk.outcome,
        worker_released=not worker._busy, worker_threads_stopped=all(not t.is_alive() for t in worker._pool._threads))
    assert row['request_bytes']<=65536 and row['response_bytes']<=200000
    assert row['retained_native_observations']<=1500
    assert row['native_runs']==len(row['markets'])*row['legs']
    print(json.dumps(row),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',type=int);args=parser.parse_args()
    if args.case is not None: asyncio.run(measure(args.case))
    else:
        report=[]
        for index in range(len(CASES)):
            run=subprocess.run([sys.executable,__file__,'--case',str(index)],text=True,capture_output=True)
            if run.returncode:
                raise RuntimeError(run.stderr)
            row=json.loads(run.stdout);report.append(row);print(json.dumps(row),flush=True)
        target=Path('../work/phase176-resources.json');target.write_text(json.dumps(report,indent=2)+'\n')
