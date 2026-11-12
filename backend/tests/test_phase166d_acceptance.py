"""Final acceptance gaps: public failures, mixed admission and retention edges."""
import asyncio
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from threading import Event

import httpx
import pytest

from app.execution.fills import OrderHistory
from app.execution.models import StrategyOrder
from app.main import app
from app.simulation.service import SimulationService
from app.simulation.executor import SimulationExecutor
from app.simulation.models import SimulationResult
from app.simulation.research_vault import ResearchProposal, ResearchVaultConfig
from app.research_replay.contracts import HistoricalReplayRequest
from app.research_replay.quantitative import compare_quantitative_paper
from app.research_replay.runner import canonical_json
from app.risk.firewall import RiskFirewallConfig
from app.simulation.config import SimulationConfig
from phase1641_fixtures import admit, dataset
from test_phase162_replay import inputs
from test_phase146_research_markets import demo
from test_phase10_api import OPTIMIZE_PAYLOAD
from test_phase14_research_vault import authority, proposal, research_client
from test_phase165c2_integration import body, comparison_client, replay_client, vault, URL
from test_phase166a_retention import OriginalOrderHistory


async def custom_accounting_case(vault, tmp_path, market, kind):
    """Complete evidence digest reused by the independent revision comparison."""
    config = ResearchVaultConfig(initial_equity_quote='12345.123456789123456789',
        paper_fee_model_enabled=True, paper_maker_fee_bps='2', paper_taker_fee_bps='7',
        paper_funding_accounting_enabled=True, paper_funding_interval_seconds=1,
        max_capital_utilization='0.75')
    research = ResearchProposal(config=config)
    admitted = admit(vault, tmp_path / 'incoming', dataset(kind, market))
    args = inputs(vault, admitted, max_frames=4, trace_max_points=4)
    raw = args['request'].model_dump(mode='json')
    raw['execution']['accounting'] = config.model_dump(mode='json')
    raw['execution']['paper'] = dict(mode='MODELED_CROSSING', order_latency_ms=1,
        slippage_bps='1', depth_sensitive=True, max_fill_fraction='0.5', participation_rate='0.5')
    args.update(request=HistoricalReplayRequest.model_validate(raw), risk=RiskFirewallConfig(enabled=False))
    before = {p.name: p.read_bytes() for p in tmp_path.rglob('*.json')}
    worker = SimulationExecutor()
    try:
        historical = await worker.execute('replay_history', **args)
        scenario = await worker.execute('run_scenario', scenario='QUIET', frames=4,
            **{k: args[k] for k in ('strategy', 'agents', 'risk')},
            simulation=SimulationConfig(max_frames=4, trace_max_points=4),
            market_profile=demo(market), research=research, include_comparison_provenance=True)
        receipts = []
        for i, segment in enumerate(historical.segments):
            archive = SimulationResult.model_validate_json(segment.simulation_result_json)
            assert archive.metrics.starting_equity == config.initial_equity_quote
            assert archive.vault.execution_accounting.execution_accounting_consistent
            assert canonical_json(archive) == segment.simulation_result_json
            receipt = compare_quantitative_paper(scenario=scenario, historical=historical, segment_index=i)
            for row in receipt.rows:
                owner = 'metrics' if row.scenario.origin == 'SIMULATION_METRICS' else 'vault'
                assert row.scenario.value == getattr(getattr(scenario.result, owner), row.name, None)
                assert row.historical_segment.value == getattr(getattr(archive, owner), row.name, None)
            receipts.append(receipt.model_dump(mode='json'))
        assert len(historical.segments) == (2 if kind == 'gap' else 1)
        if kind == 'crossing':
            assert sum(s.fill_count for s in historical.segments) > 0
        assert not worker._busy
        assert before == {p.name: p.read_bytes() for p in tmp_path.rglob('*.json')}
        complete = dict(scenario=scenario.model_dump(mode='json'),
                        historical=historical.model_dump(mode='json'), receipts=receipts)
        return hashlib.sha256(json.dumps(complete, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    finally:
        await worker.shutdown()


@pytest.mark.parametrize('market', ['BTC', 'ETH', 'SOL'])
@pytest.mark.parametrize('kind', ['gap', 'crossing'])
async def test_custom_vault_accounting_complete_evidence_is_repeatable(vault, tmp_path, market, kind):
    first = await custom_accounting_case(vault, tmp_path, market, kind)
    # Repeat against the same admitted bytes; storage admission is append-only.
    # A separate private root admits the identical source for a fresh worker.
    from app.research_replay.storage import HistoricalStorage
    root = tmp_path / 'repeat'
    (root / 'vault').mkdir(parents=True, mode=0o700)
    second = await custom_accounting_case(HistoricalStorage(root / 'vault'), root, market, kind)
    assert first == second


@pytest.mark.parametrize('operation,path,payload', [
    ('run_scenario', '/api/v1/simulation/run', {'frames': 3}),
    ('optimize', '/api/v1/simulation/optimize', OPTIMIZE_PAYLOAD),
    ('compare_research_configs', '/api/v1/research-vault/compare', None),
])
@pytest.mark.parametrize('failure,status', [(ValueError, 422), (RuntimeError, 500)])
def test_worker_errors_are_private_and_recover_without_operational_changes(
    research_client, monkeypatch, operation, path, payload, failure, status,
):
    client, rt = research_client
    before = deepcopy(authority(rt))
    if payload is None:
        payload = dict(baseline=proposal().model_dump(mode='json'),
                       custom=proposal().model_dump(mode='json'), frames=3)
    original = getattr(SimulationService, operation)
    async def broken(self, **kwargs):
        raise failure('Traceback /private/acceptance-path API_KEY=synthetic-secret')
    monkeypatch.setattr(SimulationService, operation, broken)
    response = client.post(path, json=payload)
    assert response.status_code == status
    if status == 422:
        assert response.headers['cache-control'] == 'no-store'
    for private in ('Traceback', '/private/', 'API_KEY', 'synthetic-secret'):
        assert private not in response.text
    assert not app.state.simulation_executor._busy
    assert authority(rt) == before
    monkeypatch.setattr(SimulationService, operation, original)
    assert client.post(path, json=payload).status_code == 200
    assert authority(rt) == before


@pytest.mark.parametrize('owner', ['run_scenario', 'replay_history', 'compare_scenario_historical'])
async def test_mixed_http_contenders_and_cancelled_waiter_share_one_native_worker(
    comparison_client, vault, tmp_path, monkeypatch, owner,
):
    _, rt = comparison_client
    comparison = body(vault, tmp_path)
    requests = {
        'run_scenario': ('/api/v1/simulation/run', {'frames': 4}),
        'replay_history': ('/api/v1/historical-replay/run', comparison['historical']),
        'compare_scenario_historical': (URL, comparison),
    }
    before = deepcopy(authority(rt))
    stored = {p.name: p.read_bytes() for p in tmp_path.rglob('*.json')}
    worker = app.state.simulation_executor
    original = getattr(SimulationService, owner)
    loop, entered, release = asyncio.get_running_loop(), asyncio.Event(), Event()
    completed = []
    async def held(self, **kwargs):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10)
        result = await original(self, **kwargs)
        completed.append(result)
        return result
    monkeypatch.setattr(SimulationService, owner, held)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        path, payload = requests[owner]
        task = asyncio.create_task(client.post(path, json=payload))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            replies = await asyncio.gather(*(client.post(p, json=b)
                for _ in range(4) for p, b in requests.values()))
            assert [r.status_code for r in replies] == [429] * 12
            assert worker._busy and not completed
        finally:
            release.set()
            await worker.shutdown()
    assert len(completed) == 1 and not worker._busy
    assert all(not t.is_alive() for t in worker._pool._threads)
    assert authority(rt) == before
    assert stored == {p.name: p.read_bytes() for p in tmp_path.rglob('*.json')}


@pytest.mark.parametrize('limit', [1, 2, 1000])
@pytest.mark.parametrize('protected', [False, True])
def test_exact_retention_boundary_keeps_pins_partial_fills_and_observation_order(limit, protected):
    pins = {'closed-0'} if protected else set()
    observations = [[], []]
    histories = [kind(limit=limit, pinned=pins.__contains__,
        observer=lambda rows, i=i: observations[i].extend(deepcopy(rows)))
        for i, kind in enumerate((OrderHistory, OriginalOrderHistory))]
    clock = datetime(2026, 11, 11, tzinfo=timezone.utc)
    def record(cid, status, filled='0'):
        for history in histories:
            history[cid] = StrategyOrder(client_order_id=cid, market='BTC', side='BID',
                price='60000', size='1', filled_size=filled, status=status,
                created_at=clock, updated_at=clock)
        assert list(histories[0].items()) == list(histories[1].items())
        assert list(histories[0]._closed) == list(histories[1]._closed)
        assert histories[0].recent() == histories[1].recent()
        assert observations[0] == observations[1]
    record('active', 'OPEN')
    record('active', 'PARTIALLY_FILLED', '0.25')
    record('active', 'PARTIALLY_FILLED', '0.5')
    record('unknown', 'UNKNOWN')
    for index in range(limit):
        record(f'closed-{index}', 'CANCELLED')
    assert len(histories[0]._closed) == limit
    record('boundary', 'FILLED', '1')
    assert len(histories[0]._closed) == limit + int(protected)
    assert ('closed-0' in histories[0]) == protected
    assert histories[0]['active'].filled_size == Decimal('0.5')
    # Repeated transitions refresh closed ordering identically to the old code.
    record('boundary', 'FILLED', '1')
    record('active', 'FILLED', '1')
    pins.clear()
    for history in histories:
        history.prune()
    assert list(histories[0].items()) == list(histories[1].items())
    assert len(histories[0]._closed) == limit
    assert histories[0]['unknown'].status == 'UNKNOWN'
