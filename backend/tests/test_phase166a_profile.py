"""Instrumentation must see real worker calls, including retained imports."""
import hashlib
from pathlib import Path

import pytest

from app.research_replay import comparison, quantitative, runner
from app.simulation import executor
from app.simulation.engine import SimulationEngine
from app.simulation.service import SimulationService
from phase166a_profile import StageProbe, measured_stages, profile


def originals():
    return (SimulationService.replay_history, SimulationService.run_scenario,
        SimulationEngine.run, quantitative.compare_quantitative_paper,
        comparison.capture_comparison_foundation, quantitative.capture_comparison_foundation,
        runner.archive_wire_and_fingerprint, executor._run)


def test_missing_stage_measurements_are_unavailable():
    with pytest.raises(ValueError, match='unavailable'):
        StageProbe().validate(1, False)


def test_profile_restores_definitions_and_retained_aliases_on_exception():
    before = originals()
    with pytest.raises(RuntimeError, match='controlled'):
        with measured_stages(cpu_profile=True) as probe:
            assert quantitative.capture_comparison_foundation is comparison.capture_comparison_foundation
            assert 'app.research_replay.quantitative.capture_comparison_foundation' in probe.callsites['comparison_foundation']
            raise RuntimeError('controlled')
    assert originals() == before


async def test_real_modeled_multisegment_worker_is_observed_and_cleaned(tmp_path):
    before = originals()
    app = Path(__file__).resolve().parents[1] / 'app'
    sources = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in app.rglob('*.py')}
    report = await profile(frames=8, segments=2, modeled=True, runs=1,
        cpu_profile=True, output=tmp_path / 'profile.json', artifacts=tmp_path / 'artifacts')
    assert report['status'] == 'MEASURED'
    assert report['temporary_data_cleaned'] and report['worker_shutdown_complete']
    assert not Path(report['temporary_root']).exists()
    run = report['runs'][0]
    assert run['stages']['engine']['calls'] == 5
    assert run['stages']['archive_serialization']['calls'] == 4
    assert run['stages']['comparison_foundation']['calls'] == 1
    assert run['cpu_profile']['total_calls'] > 0
    assert all(stage['seconds'] and stage['status'] == 'MEASURED' for stage in run['stages'].values())
    assert len(run['evidence']['archives']) == 2
    assert originals() == before
    assert sources == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in app.rglob('*.py')}


@pytest.mark.parametrize('cancel_stage', ['historical-replay', 'QUIET'])
async def test_cancellation_inside_native_engine_keeps_capacity_until_shutdown(tmp_path, monkeypatch, cancel_stage):
    import asyncio
    from threading import Event
    from app.simulation import engine
    from app.simulation.executor import ResearchBusyError, SimulationExecutor
    from app.research_replay.storage import HistoricalStorage
    from app.research_replay.transport import ScenarioHistoricalRequest
    from app.agents.config import AgentConfig
    from app.risk.firewall import RiskFirewallConfig
    from app.strategy.models import StrategyConfig
    from phase1641_fixtures import admit
    from phase165d_fixtures import bounded_dataset
    from test_phase146_research_markets import demo

    (tmp_path / 'vault').mkdir(mode=0o700)
    vault = HistoricalStorage(tmp_path / 'vault')
    admitted = admit(vault, tmp_path / 'incoming', bounded_dataset(8))
    before_files = {p: p.read_bytes() for p in tmp_path.rglob('*.json')}
    request = ScenarioHistoricalRequest(research_market='BTC', frames=8,
        simulation={'max_frames': 8}, historical=dict(dataset_id=admitted.dataset_id,
            dataset_fingerprint=admitted.dataset_fingerprint, market='BTC', max_frames=8,
            execution={'size_decimals': 5}, policy={'max_component_age_ms': 1000}))
    loop, entered, release = asyncio.get_running_loop(), asyncio.Event(), Event()
    current, counts = [], {}
    original_run, original_refs = SimulationEngine.run, engine.build_simulated_references
    async def run(self, **kwargs):
        current[:] = [kwargs['scenario']]
        return await original_run(self, **kwargs)
    def frame(*args, **kwargs):
        stage = current[0]
        counts[stage] = counts.get(stage, 0) + 1
        if stage == cancel_stage and counts[stage] == 3:
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(10)
        return original_refs(*args, **kwargs)
    monkeypatch.setattr(SimulationEngine, 'run', run)
    monkeypatch.setattr(engine, 'build_simulated_references', frame)
    worker = SimulationExecutor()
    task = asyncio.create_task(worker.execute('compare_scenario_historical', storage_root=vault.root,
        request=request, strategy=StrategyConfig(), agents=AgentConfig(), risk=RiskFirewallConfig(), market_profile=demo('BTC')))
    shutdown = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ResearchBusyError):
            await worker.execute('historical_catalog', storage_root=vault.root)
        shutdown = asyncio.create_task(worker.shutdown())
        await asyncio.sleep(.02)
        assert not shutdown.done() and worker._busy
    finally:
        release.set()
        await (shutdown if shutdown is not None else worker.shutdown())
    assert not worker._busy and counts[cancel_stage] == 8
    assert before_files == {p: p.read_bytes() for p in tmp_path.rglob('*.json')}
