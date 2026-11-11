"""Phase 16.6A optional native profile: one real admitted PAPER comparison job.

No new production hooks, worker or dependency. Runs generated local fixtures.
Results are observations, not guaranteed latency or exchange authenticity.

From repo root (Python 3.12, backend test extras installed):
 PYTHONPATH=backend:backend/tests backend/.venv/bin/python \
   backend/tests/phase166a_profile.py --frames 128 --output work/phase166a-profile.json
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from contextlib import contextmanager
import json
import os
from pathlib import Path
import resource
from statistics import median
import tempfile
import time

from app.agents.config import AgentConfig
from app.research_replay import quantitative, runner
from app.research_replay.runner import archive_wire_and_fingerprint, canonical_json
from app.research_replay.storage import HistoricalStorage
from app.research_replay.transport import ScenarioHistoricalRequest
from app.risk.firewall import RiskFirewallConfig
from app.simulation.executor import SimulationExecutor
from app.simulation import models as simulation_models
from app.simulation.service import SimulationService
from app.strategy.models import StrategyConfig
from phase1641_fixtures import admit
from phase165d_fixtures import bounded_dataset
from test_phase146_research_markets import demo

@contextmanager
def measured_stages():
    """Instrument only the profiling process; restore every original method."""
    original_replay = SimulationService.replay_history
    original_scenario = SimulationService.run_scenario
    original_compare = quantitative.compare_quantitative_paper
    original_archive = runner.archive_wire_and_fingerprint
    totals: dict[str, list[float]] = defaultdict(list)
    sampled_results: list = []

    async def replay(self, **kwargs):
        started = time.perf_counter()
        try:
            return await original_replay(self, **kwargs)
        finally:
            totals["replay"].append(time.perf_counter() - started)

    async def scenario(self, **kwargs):
        started = time.perf_counter()
        try:
            return await original_scenario(self, **kwargs)
        finally:
            totals["scenario"].append(time.perf_counter() - started)

    def compare(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original_compare(*args, **kwargs)
        finally:
            totals["quantitative_receipt"].append(time.perf_counter() - started)

    def archive(result):
        started = time.perf_counter()
        try:
            if len(sampled_results) < 1:
                sampled_results.append(result)
            return original_archive(result)
        finally:
            totals["archive_serialization"].append(time.perf_counter() - started)

    SimulationService.replay_history = replay
    SimulationService.run_scenario = scenario
    quantitative.compare_quantitative_paper = compare
    runner.archive_wire_and_fingerprint = archive
    try:
        yield totals, sampled_results
    finally:
        SimulationService.replay_history = original_replay
        SimulationService.run_scenario = original_scenario
        quantitative.compare_quantitative_paper = original_compare
        runner.archive_wire_and_fingerprint = original_archive


def archive_microbenchmark(result, iterations=20):
    """Match archive bytes/hashes every run, report time without speed claims."""
    original_json = canonical_json(result)
    original_hash = simulation_models.stable_fingerprint(json.loads(original_json))
    assert archive_wire_and_fingerprint(result) == (original_json, original_hash)
    times = {"existing_roundtrip_ms": [], "single_payload_ms": []}
    for _ in range(iterations):
        start = time.perf_counter_ns()
        old_json = canonical_json(result)
        old_hash = simulation_models.stable_fingerprint(json.loads(old_json))
        times["existing_roundtrip_ms"].append((time.perf_counter_ns() - start) / 1e6)
        start = time.perf_counter_ns()
        new_json, new_hash = archive_wire_and_fingerprint(result)
        times["single_payload_ms"].append((time.perf_counter_ns() - start) / 1e6)
        assert old_json == new_json and old_hash == new_hash
    return {key: {"median_ms": round(median(values), 6),
                  "min_ms": round(min(values), 6),
                  "max_ms": round(max(values), 6)}
            for key, values in times.items()}


async def profile(*, frames: int, output: str):
    if not 2 <= frames <= 1000:
        raise ValueError("profile frames must be between 2 and 1000; 5000-bound stress belongs to 16.6D")
    with tempfile.TemporaryDirectory(prefix="phase166a-profile-") as temp:
        root = Path(temp)
        vault_dir = root / "vault"
        vault_dir.mkdir(mode=0o700)
        vault = HistoricalStorage(vault_dir)
        admitted = admit(vault, root / "incoming", bounded_dataset(frames))
        request = ScenarioHistoricalRequest(
            research_market="BTC",
            frames=frames,
            simulation={"max_frames": frames, "record_trace": True, "trace_max_points": 120},
            historical={
                "dataset_id": admitted.dataset_id,
                "dataset_fingerprint": admitted.dataset_fingerprint,
                "market": "BTC",
                "execution": {"size_decimals": 5},
                "policy": {"max_component_age_ms": 1000},
                "max_frames": frames,
                "record_trace": True,
                "trace_max_points": 120,
            },
            trace_point_limit=120,
        )
        worker = SimulationExecutor()
        try:
            with measured_stages() as (timings, archive_samples):
                started = time.perf_counter()
                response = await worker.execute(
                    "compare_scenario_historical",
                    storage_root=vault.root,
                    request=request,
                    strategy=StrategyConfig(),
                    agents=AgentConfig(),
                    risk=RiskFirewallConfig(),
                    market_profile=demo("BTC"),
                )
                worker_seconds = time.perf_counter() - started
            assert not worker._busy
            assert response.segment_count == 1
            assert response.receipt.foundation.classification == "CONTEXT_ONLY"
            assert response.receipt.authority == "NONE"
            assert not response.receipt.cross_segment_aggregation_allowed
            wire = response.model_dump_json().encode("utf-8")
            assert len(wire) <= 1_000_000
            # Use the original, validated single segment archive. No trusted
            # source bytes are persisted or exposed by this profile report.
            archive = response.receipt.foundation.historical
            summary = {
                "phase": "16.6A",
                "status": "MEASURED",
                "fixture_notice": "Synthetic deterministic PAPER evidence; no exchange/source licensing claim",
                "environment": {"python": os.sys.version.split()[0],
                                "platform": os.sys.platform, "cpus": os.cpu_count()},
                "frames": frames,
                "worker_seconds": round(worker_seconds, 6),
                "stages_seconds": {key: [round(v, 6) for v in values]
                                   for key, values in timings.items()},
                "response_bytes": len(wire),
                "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "receipt_fingerprint": response.receipt.receipt_fingerprint,
                "segment_run_fingerprint": archive.run_fingerprint,
                "single_worker_released": True,
                "archive_microbenchmark": archive_microbenchmark(archive_samples[0]) if archive_samples else None,
            }
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary, indent=2))
        finally:
            await worker.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=128)
    parser.add_argument("--output", required=True)
    options = parser.parse_args()
    asyncio.run(profile(frames=options.frames, output=options.output))
