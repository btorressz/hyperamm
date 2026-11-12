"""Fresh-process native combined-workload measurements, no changed limits.

Run from backend: PYTHONPATH=.:tests python tests/phase174_resources.py --case aligned
"""
import argparse
import asyncio
import json
import resource
import time

from app.execution.research import PaperExecutionAssumptions
from app.portfolio_research.models import PortfolioStressResult
from app.portfolio_research.scenarios import workload
from app.simulation.executor import SimulationExecutor
from phase174_fixtures import request_for


async def measure(case):
    markets,frames,retained={
        "one":(("BTC",),1500,750),
        "two":(("BTC","ETH"),750,375),
        "three":(("BTC","ETH","SOL"),500,250),
        "aligned":(("BTC","ETH","SOL"),250,250),
        "modeled":(("BTC","ETH","SOL"),500,250),
        "quotes":(("BTC","ETH","SOL"),500,250),
    }[case]
    overrides={m:{"simulation":{"trace_max_points":retained}} for m in markets}
    if case=="modeled":
        execution=PaperExecutionAssumptions(mode="MODELED_CROSSING",order_latency_ms=1000,
            cancel_latency_ms=2000,slippage_bps="1",depth_sensitive=True,participation_rate="0.25")
        for m in markets:overrides[m]["simulation"]["execution"]=execution.model_dump(mode="json")
    if case=="quotes":
        for m in markets:overrides[m]["strategy"]={"levels_per_side":8}
    r=request_for("LIQUIDITY_SHOCK" if case=="modeled" else "CORRELATED_SELLOFF",markets,
                  frames=frames,onset=frames//2,overrides=overrides)
    worker=SimulationExecutor();started=time.perf_counter()
    try:
        result=await worker.execute("stress_portfolio_research",request=r)
        elapsed=time.perf_counter()-started
        wire=result.model_dump_json()
        PortfolioStressResult.model_validate_json(wire)
        retained_count=sum(c.retained for leg in (result.baseline,result.stressed) for c in leg.temporal.clocks)
        frames_count=sum(m.metrics.frame_count for leg in (result.baseline,result.stressed) for m in leg.execution.markets)
        assert retained_count==1500 and len(wire.encode())<=200000 and not worker._busy
        if case=="aligned":
            assert result.metrics.temporal_classification=="MODELED_ALIGNED"
            assert result.risk_transition.status=="ASSESSED"
        else:
            assert result.metrics.temporal_classification=="FINAL_ONLY"
            assert result.risk_transition.status=="BLOCKED"
        costs=workload(r.config)
        return dict(case=case,frames=frames_count,quote_level_frames=2*costs[1],retained=retained_count,
            configured_ledger=2*costs[3],configured_events=2*costs[4],request_bytes=len(r.model_dump_json().encode()),
            response_bytes=len(wire.encode()),worker_seconds=round(elapsed,3),
            peak_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),
            temporal=result.metrics.temporal_classification,worker_released=not worker._busy)
    finally:await worker.shutdown()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--case",choices=("one","two","three","aligned","modeled","quotes"),required=True)
    print(json.dumps(asyncio.run(measure(parser.parse_args().case))))
