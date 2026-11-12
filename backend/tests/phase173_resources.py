"""Cold native worker measurements; raw observations belong in ignored work/."""
import argparse
import asyncio
import json
import resource
import time

from app.execution.research import PaperExecutionAssumptions
from app.portfolio_research import exposure, risk
from app.portfolio_research.models import PortfolioAnalysisResult
from app.simulation.executor import SimulationExecutor
from phase172_fixtures import portfolio
from phase173_fixtures import request_for


async def measure(case):
    markets, frames, retained = {
        "one": (("BTC",), 3000, 1500),
        "two": (("BTC", "ETH"), 1500, 750),
        "three": (("BTC", "ETH", "SOL"), 1000, 500),
        "aligned": (("BTC", "ETH", "SOL"), 500, 500),
        "modeled": (("BTC", "ETH", "SOL"), 1000, 500),
    }[case]
    overrides = {m: {"simulation": {"trace_max_points": retained}} for m in markets}
    if case == "modeled":
        controls = PaperExecutionAssumptions(mode="MODELED_CROSSING", order_latency_ms=1000,
            cancel_latency_ms=2000, slippage_bps="1", depth_sensitive=True, participation_rate="0.25")
        for m in markets:
            overrides[m]["simulation"]["execution"] = controls.model_dump(mode="json")
    p = portfolio(markets, frames=frames, scenario="FLASH_MOVE", overrides=overrides)
    costs = {"exposure": 0.0, "risk": 0.0}
    originals = []
    for module, name, label in ((exposure, "calculate_exposure", "exposure"), (risk, "evaluate_risk", "risk")):
        original = getattr(module, name)
        originals.append((module, name, original))
        def timed(*args, _original=original, _label=label, **kwargs):
            start = time.perf_counter()
            try: return _original(*args, **kwargs)
            finally: costs[_label] += time.perf_counter() - start
        setattr(module, name, timed)
    worker = SimulationExecutor()
    start = time.perf_counter()
    try:
        result = await worker.execute("analyze_portfolio_research", request=request_for(p))
        elapsed = time.perf_counter() - start
        worker_costs = costs.copy()
        wire = result.model_dump_json()
        PortfolioAnalysisResult.model_validate_json(wire)
        assert not worker._busy
    finally:
        await worker.shutdown()
        for module, name, original in originals: setattr(module, name, original)
    return dict(case=case, total_frames=sum(m.metrics.frame_count for m in result.execution.markets),
        native_accounting_observations=sum(c.retained for c in result.temporal.clocks),
        portfolio_equity_observations=result.accounting.drawdown.observation_count if result.accounting.drawdown else 0,
        temporal=result.temporal.classification, risk_outcome=result.risk.outcome,
        worker_seconds=round(elapsed, 4), response_bytes=len(wire.encode()),
        peak_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
        exposure_seconds=round(worker_costs["exposure"], 6), risk_seconds=round(worker_costs["risk"], 6),
        analysis_fingerprint=result.evidence_fingerprint, worker_released=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("one", "two", "three", "aligned", "modeled"), required=True)
    print(json.dumps(asyncio.run(measure(parser.parse_args().case))))
