"""Explicit native worker resource observations; raw output stays in work/."""
import argparse
import asyncio
import json
import resource
import time

from app.execution.research import PaperExecutionAssumptions
from app.portfolio_research.models import PortfolioExecutedResult
from app.simulation.executor import SimulationExecutor
from phase172_fixtures import portfolio, request_for, AMOUNTS


async def measure(case):
    frames = {"three": 1000, "single": 3000, "wide": 160, "modeled": 1000}[case]
    markets = ("BTC",) if case == "single" else tuple(AMOUNTS)
    overrides = {}
    if case == "wide":
        overrides = {m: {"strategy": {"levels_per_side": 50, "total_liquidity": str(size)}}
                     for m, size in (("BTC", 1), ("ETH", 20), ("SOL", 400))}
    if case == "modeled":
        controls = PaperExecutionAssumptions(mode="MODELED_CROSSING", order_latency_ms=1000,
            cancel_latency_ms=2000, slippage_bps="1", depth_sensitive=True, participation_rate="0.25")
        overrides = {m: {"simulation": {"execution": controls.model_dump(mode="json")}} for m in markets}
    p = portfolio(markets, frames=frames, scenario="FLASH_MOVE", overrides=overrides)
    worker = SimulationExecutor()
    start = time.perf_counter()
    try:
        result = await worker.execute("run_portfolio_research", request=request_for(p))
        elapsed = time.perf_counter() - start
        wire = result.model_dump_json()
        PortfolioExecutedResult.model_validate_json(wire)
        assert not worker._busy
    finally:
        await worker.shutdown()
    return dict(case=case, total_frames=frames * len(markets),
        quote_level_frames=sum(s.frames * s.captured.inputs().strategy.levels_per_side for s in p.scenarios),
        elapsed_seconds=round(elapsed, 4), response_bytes=len(wire.encode()),
        peak_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
        config_fingerprint=result.config_fingerprint, bundle_fingerprint=result.bundle_fingerprint,
        result_fingerprints=[r.provenance.result_fingerprint for r in result.markets],
        ledger_versions=[r.vault.ledger_version for r in result.markets],
        fills=[r.metrics.fill_count for r in result.markets], worker_released=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("three", "single", "wide", "modeled"), required=True)
    print(json.dumps(asyncio.run(measure(parser.parse_args().case)), indent=2))
