"""Native single-slot PAPER profiling/benchmarking; no production instrumentation.

Run the SAME file against clean checkouts via PYTHONPATH=checkout/backend:checkout/backend/tests.
Use --no-instrument for comparable wall times; --cprofile is a separate diagnostic.
Near-limit acceptance continues to use phase165d_performance.py unchanged.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager, ExitStack
import cProfile
from functools import wraps
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
import pstats
import resource
from statistics import median, pstdev
import sys
import tempfile
import time
from unittest.mock import patch

from app.agents.config import AgentConfig
from app.research_replay import comparison, quantitative, runner, transport
from app.research_replay.storage import HistoricalStorage
from app.research_replay.transport import ScenarioHistoricalRequest
from app.risk.firewall import RiskFirewallConfig
from app.simulation import executor
from app.simulation.engine import SimulationEngine
from app.simulation.executor import SimulationExecutor
from app.simulation.models import stable_fingerprint
from app.simulation.service import SimulationService
from app.strategy.models import StrategyConfig
from phase1641_fixtures import admit
from phase165d_fixtures import bounded_dataset
from test_phase146_research_markets import demo


class StageProbe:
    def __init__(self):
        self.timings = {}
        self.failures = {}
        self.callsites = {}
        self.archive_samples = []
        self.replay = self.scenario = None
        self.profiler = None

    def observe(self, stage, elapsed, result, failed):
        self.timings.setdefault(stage, []).append(elapsed)
        if failed:
            self.failures[stage] = self.failures.get(stage, 0) + 1
        elif stage == 'archive_serialization' and not self.archive_samples:
            self.archive_samples.append(result)
        elif stage in ('replay', 'scenario'):
            setattr(self, stage, result)

    def validate(self, segments, modeled):
        expected = dict(replay=1, scenario=1, quantitative_receipt=1,
            archive_serialization=segments * (2 if modeled else 1),
            engine=segments * (2 if modeled else 1) + 1,
            dataset_read=1, prepare_replay=1, comparison_foundation=1,
            segment_dataset=segments + 1, trace_projection=2, comparison_response=1)
        unavailable = {k: dict(expected=n, observed=len(self.timings.get(k, [])))
            for k, n in expected.items() if len(self.timings.get(k, [])) != n}
        if unavailable or self.failures:
            raise ValueError(f'profiling stages unavailable/failed: {unavailable}; {self.failures}')
        return {k: dict(status='MEASURED', calls=len(v), seconds=v, inclusive_seconds=sum(v))
            for k, v in self.timings.items()}


@contextmanager
def measured_stages(*, cpu_profile=False):
    """Patch actual call sites and already-retained app aliases; restore on failure.

    Durations are inclusive/nested and MUST NOT be summed across stages.
    cProfile runs on the admitted executor thread (not the waiting event loop).
    """
    probe = StageProbe()
    targets = [(SimulationService, 'replay_history', 'replay'),
        (SimulationService, 'run_scenario', 'scenario'),
        (SimulationService, 'compare_scenario_historical', 'comparison_response'),
        (SimulationEngine, 'run', 'engine'),
        (HistoricalStorage, 'read', 'dataset_read'),
        (quantitative, 'compare_quantitative_paper', 'quantitative_receipt'),
        (comparison, 'capture_comparison_foundation', 'comparison_foundation'),
        (runner, 'prepare_replay', 'prepare_replay'),
        (runner, 'segment_dataset', 'segment_dataset'),
        (transport, 'project_trace', 'trace_projection')]
    if hasattr(runner, 'archive_wire_and_fingerprint'):
        targets.append((runner, 'archive_wire_and_fingerprint', 'archive_serialization'))
    # Capture originals before applying any patch, including aliases imported
    # by quantitative.py at module import time.
    originals = [(owner, name, stage, getattr(owner, name)) for owner, name, stage in targets]
    with ExitStack() as stack:
        for owner, name, stage, original in originals:
            def wrap(original, stage):
                def record(start, result, failed):
                    # Retain the validated source result, not the archive tuple.
                    probe.observe(stage, time.perf_counter() - start, result, failed)
                if inspect.iscoroutinefunction(original):
                    @wraps(original)
                    async def observed(*args, **kwargs):
                        start, result, failed = time.perf_counter(), None, True
                        try:
                            result = await original(*args, **kwargs)
                            failed = False
                            return result
                        finally:
                            record(start, result, failed)
                else:
                    @wraps(original)
                    def observed(*args, **kwargs):
                        start, result, failed = time.perf_counter(), None, True
                        try:
                            result = original(*args, **kwargs)
                            failed = False
                            return result
                        finally:
                            record(start, args[0] if stage == 'archive_serialization' else result, failed)
                return observed
            observed = wrap(original, stage)
            sites = [(owner, name)]
            if inspect.ismodule(owner):
                for module_name, module in list(sys.modules.items()):
                    if module_name.startswith('app.') and module is not None:
                        sites.extend((module, key) for key, value in list(vars(module).items())
                            if value is original and (module, key) not in sites)
            probe.callsites[stage] = [f'{obj.__name__}.{attr}' for obj, attr in sites]
            for obj, attr in sites:
                stack.enter_context(patch.object(obj, attr, observed))
        if cpu_profile:
            probe.profiler = cProfile.Profile()
            original_run = executor._run
            def profiled(*args, **kwargs):
                return probe.profiler.runcall(original_run, *args, **kwargs)
            stack.enter_context(patch.object(executor, '_run', profiled))
        yield probe


def archive_microbenchmark(result, iterations=30):
    """Alternate order to avoid consistently favoring the second operation."""
    def legacy():
        wire = runner.canonical_json(result)
        return wire, stable_fingerprint(json.loads(wire))
    optimized = getattr(runner, 'archive_wire_and_fingerprint', None)
    if optimized is None:
        return dict(status='UNAVAILABLE', reason='Pre-optimization checkout')
    expected = legacy()
    times = dict(existing_roundtrip_ms=[], single_payload_ms=[])
    for i in range(iterations):
        choices = [('existing_roundtrip_ms', legacy), ('single_payload_ms', lambda: optimized(result))]
        for key, operation in choices[::1 if i % 2 else -1]:
            start = time.perf_counter_ns()
            actual = operation()
            times[key].append((time.perf_counter_ns() - start) / 1e6)
            assert actual == expected
    return {key: dict(samples_ms=v, median_ms=median(v), min_ms=min(v), max_ms=max(v))
        for key, v in times.items()}


def cpu_stats(profiler):
    stats = pstats.Stats(profiler)
    rows = []
    for (filename, line, function), (primitive, calls, own, cumulative, _) in stats.stats.items():
        if '/app/' in filename:
            rows.append(dict(file='app/' + filename.split('/app/', 1)[1], line=line,
                function=function, primitive_calls=primitive, calls=calls,
                self_seconds=own, cumulative_seconds=cumulative))
    return dict(total_seconds=stats.total_tt, total_calls=stats.total_calls,
        functions=sorted(rows, key=lambda r: r['cumulative_seconds'], reverse=True),
        note='cProfile overhead included; recursive/nested cumulative times overlap')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def evidence(response, probe=None):
    """Hash complete deterministic evidence, including all exact archive strings."""
    result = dict(response_sha256=digest(response.model_dump_json()),
        request_fingerprint=response.request_fingerprint,
        dataset_fingerprint=response.provenance.dataset_fingerprint,
        receipt_fingerprint=response.receipt.receipt_fingerprint,
        segments=[s.model_dump(mode='json') for s in response.segments],
        scenario=response.receipt.foundation.scenario.model_dump(mode='json'),
        rows=[r.model_dump(mode='json') for r in response.receipt.rows])
    if probe is not None:
        result.update(replay_sha256=digest(probe.replay.model_dump_json()),
            replay_fingerprint=probe.replay.result_fingerprint,
            scenario_sha256=digest(probe.scenario.model_dump_json()),
            archives=[dict(modeled_sha256=digest(s.simulation_result_json),
                baseline_sha256=digest(s.baseline_result_json) if s.baseline_result_json else None)
                for s in probe.replay.segments])
    return result


async def profile(*, frames, output, segments=1, modeled=False, runs=1,
                  instrument=True, cpu_profile=False, artifacts=None):
    if not 2 <= frames <= 1000 or not 1 <= runs <= 20:
        raise ValueError('Use 2..1000 frames, 1..20 runs; near-limit uses phase165d_performance.py')
    if cpu_profile and not instrument:
        raise ValueError('cProfile requires instrumentation')
    report = dict(phase='16.6A.2', status='FAIL', fixture_notice='Synthetic deterministic PAPER evidence',
        environment=dict(python=platform.python_version(), platform=platform.platform(), cpus=os.cpu_count()),
        instrumentation=dict(enabled=instrument, cprofile=cpu_profile,
            timing_note='Inclusive nested stages; do not add. Monkeypatch/timer overhead included when enabled.',
            rss_note='Linux process cumulative high-water KiB, includes imports/setup and earlier runs; not allocation delta.'),
        frames=frames, segments=segments, modeled=modeled, runs=[])
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='phase166a-profile-') as temp:
            root = Path(temp)
            (root / 'vault').mkdir(mode=0o700)
            vault = HistoricalStorage(root / 'vault')
            admitted = admit(vault, root / 'incoming', bounded_dataset(frames, segments, crossing=modeled))
            original_files = {str(p.relative_to(root)): digest(p.read_text()) for p in root.rglob('*.json')}
            historical = dict(dataset_id=admitted.dataset_id, dataset_fingerprint=admitted.dataset_fingerprint,
                market='BTC', execution=dict(size_decimals=5), policy=dict(max_component_age_ms=1000),
                max_frames=frames, record_trace=True, trace_max_points=120)
            if modeled:
                historical['execution']['paper'] = dict(mode='MODELED_CROSSING', order_latency_ms=1,
                    cancel_latency_ms=2, slippage_bps='1', depth_sensitive=True,
                    participation_rate='0.5', max_fill_fraction='0.5')
            request = ScenarioHistoricalRequest(research_market='BTC', frames=frames,
                simulation=dict(max_frames=frames, record_trace=True, trace_max_points=120),
                historical=historical, trace_point_limit=120)
            worker = SimulationExecutor()
            report['temporary_root'] = str(root)
            try:
                for index in range(runs):
                    inputs = dict(storage_root=vault.root, request=request, strategy=StrategyConfig(),
                        agents=AgentConfig(), risk=RiskFirewallConfig(enabled=not modeled), market_profile=demo('BTC'))
                    before_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    @contextmanager
                    def uninstrumented():
                        yield None
                    context = measured_stages(cpu_profile=cpu_profile) if instrument else uninstrumented()
                    with context as probe:
                        started = time.perf_counter()
                        response = await worker.execute('compare_scenario_historical', **inputs)
                        elapsed = time.perf_counter() - started
                    assert not worker._busy and response.segment_count == segments
                    assert sum(s.frame_count for s in response.segments) == frames
                    assert response.receipt.foundation.classification == 'CONTEXT_ONLY'
                    assert response.receipt.authority == 'NONE' and not response.receipt.cross_segment_aggregation_allowed
                    wire = response.model_dump_json().encode()
                    assert len(wire) <= transport.MAX_RESPONSE_BYTES
                    assert original_files == {str(p.relative_to(root)): digest(p.read_text()) for p in root.rglob('*.json')}
                    if modeled:
                        assert next(r for r in response.receipt.rows if r.name == 'fill_count').historical_segment.value > 0
                    measured = dict(index=index, temperature='process-cold/thread-cold' if index == 0 else 'process-warm/thread-warm',
                        worker_seconds=elapsed, response_bytes=len(wire),
                        previous_process_peak_rss_kib=before_rss,
                        process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        single_worker_released=True, source_files_unchanged=True, evidence=evidence(response, probe))
                    if probe is not None:
                        measured.update(stages=probe.validate(segments, modeled), callsites=probe.callsites,
                            archive_microbenchmark=archive_microbenchmark(probe.archive_samples[0]))
                        if cpu_profile:
                            measured['cpu_profile'] = cpu_stats(probe.profiler)
                        if artifacts:
                            dest = Path(artifacts)
                            dest.mkdir(parents=True, exist_ok=True)
                            for name, value in [('response', response), ('replay', probe.replay), ('scenario', probe.scenario)]:
                                (dest / f'{index}-{name}.json').write_text(value.model_dump_json())
                    report['runs'].append(measured)
                    print(json.dumps(dict(index=index, frames=frames, modeled=modeled, worker_seconds=elapsed)), flush=True)
            finally:
                await worker.shutdown()
                report['worker_shutdown_complete'] = all(not thread.is_alive() for thread in worker._pool._threads)
                assert report['worker_shutdown_complete'] and not worker._busy
        report['temporary_data_cleaned'] = not root.exists()
        values = [r['worker_seconds'] for r in report['runs']]
        report['summary'] = dict(median_seconds=median(values), min_seconds=min(values), max_seconds=max(values),
            population_stdev_seconds=pstdev(values), individual_seconds=values)
        assert report['temporary_data_cleaned']
        report['status'] = 'MEASURED'
    finally:
        path.write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--frames', type=int, default=128)
    parser.add_argument('--segments', type=int, default=1)
    parser.add_argument('--modeled', action='store_true')
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--no-instrument', action='store_true')
    parser.add_argument('--cprofile', action='store_true')
    parser.add_argument('--artifacts')
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    asyncio.run(profile(frames=options.frames, segments=options.segments, modeled=options.modeled,
        runs=options.runs, instrument=not options.no_instrument, cpu_profile=options.cprofile,
        artifacts=options.artifacts, output=options.output))
