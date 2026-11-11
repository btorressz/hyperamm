"""Independent bounded-input, receipt consistency and worker regression gates."""
import asyncio
from copy import deepcopy
from decimal import Decimal
from threading import Event

import httpx
import pytest
from pydantic import ValidationError

from app.research_replay.quantitative import MetricObservation, QuantitativeComparison
from app.research_replay.transport import ScenarioHistoricalRequest, ScenarioHistoricalResponse
from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.models import stable_fingerprint
from app.simulation.service import SimulationService
from test_phase165c2_integration import comparison_client, body, vault, replay_client, URL


@pytest.mark.parametrize('field', ['initial_equity_quote', 'paper_initial_equity_quote',
    'paper_maker_fee_bps', 'paper_taker_fee_bps', 'max_capital_utilization'])
@pytest.mark.parametrize('value', [1.25, True, '1E+1000000', '1E-1000000', 'NaN', 'Infinity'])
def test_untrusted_simulation_decimals_rejected_before_admission(comparison_client, vault, tmp_path, field, value, monkeypatch):
    from app.main import app
    client, _ = comparison_client
    request = body(vault, tmp_path)
    target = request['simulation'] if field == 'initial_equity_quote' else request['simulation'].setdefault('accounting', {})
    target[field] = value
    calls = []
    async def unexpected(*args, **kwargs):
        calls.append(args)
        raise AssertionError('invalid decimal reached worker')
    monkeypatch.setattr(app.state.simulation_executor, 'execute', unexpected)
    response = client.post(URL, json=request)
    assert response.status_code == 422, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert not calls


@pytest.mark.parametrize('value', ['0', '-0', '0E+5', '1E-18', '0.123456789123456789'])
def test_bounded_exact_accounting_spelling_survives_request_roundtrip(vault, tmp_path, value):
    request = body(vault, tmp_path)
    request['simulation']['accounting'] = {'paper_maker_fee_bps': value}
    # Negative zero is valid for a nonnegative fee; capital remains positive.
    first = ScenarioHistoricalRequest.model_validate(request)
    second = ScenarioHistoricalRequest.model_validate_json(first.model_dump_json())
    assert first == second
    assert first.simulation.accounting.paper_maker_fee_bps == Decimal(value)


@pytest.fixture
def native_response(comparison_client, vault, tmp_path):
    client, _ = comparison_client
    result = client.post(URL, json=body(vault, tmp_path))
    assert result.status_code == 200, result.text
    return ScenarioHistoricalResponse.model_validate_json(result.content)


@pytest.mark.parametrize('side', ['scenario', 'historical_segment'])
def test_rehashed_frame_counts_cannot_disagree_with_bound_source(native_response, side):
    receipt = native_response.receipt
    row = receipt.rows[0]
    row = row.model_copy(update={side: getattr(row, side).model_copy(update={'value': Decimal(5)})})
    changed = receipt.model_copy(update={'rows': (row, *receipt.rows[1:]),
        'risk_states': receipt.risk_states.model_copy(update={side: {'HALT': 5}})})
    changed = changed.model_copy(update={'receipt_fingerprint': stable_fingerprint(changed.model_dump(exclude={'receipt_fingerprint'}))})
    with pytest.raises(ValidationError):
        QuantitativeComparison.model_validate_json(changed.model_dump_json())


@pytest.mark.parametrize('value', ['1E+1000000', '1E-1000000', '9' * 121])
def test_metric_receipts_cannot_expand_unbounded_decimal_strings(value):
    with pytest.raises(ValidationError):
        MetricObservation(origin='SIMULATION_METRICS', availability='AVAILABLE', value=value)


@pytest.mark.parametrize('field,value', [('frame_count', 3), ('window_start', '2025-01-01T00:00:00Z')])
def test_selected_segment_metadata_must_match_receipt(native_response, field, value):
    raw = native_response.model_dump(mode='json')
    raw['segments'][0][field] = value
    with pytest.raises(ValidationError):
        ScenarioHistoricalResponse.model_validate(raw)


def test_original_source_receipt_times_cannot_be_relabelled(native_response):
    raw = native_response.model_dump(mode='json')
    raw['historical_trace']['source_times'][0]['book_received_at'] = '2025-01-01T00:00:00Z'
    raw['historical_trace']['source_times'][0]['context_received_at'] = '2025-01-01T00:00:00Z'
    with pytest.raises(ValidationError):
        ScenarioHistoricalResponse.model_validate(raw)


@pytest.mark.parametrize('raw', [b'{', b'{"x":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}'])
def test_malformed_json_remains_bounded_public_422(comparison_client, raw):
    client, _ = comparison_client
    response = client.post(URL, content=raw, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert response.headers['cache-control'] == 'no-store'
    assert len(response.content) < 16000


async def test_chunked_body_rejected_before_json_or_worker(comparison_client, monkeypatch):
    from app.main import app
    calls = []
    async def unexpected(*args, **kwargs):
        calls.append(args)
        raise AssertionError('oversize request reached worker')
    monkeypatch.setattr(app.state.simulation_executor, 'execute', unexpected)
    async def chunks():
        yield b'{"unexpected": "' + b'x' * 32768
        yield b'x' * 32768
        raise AssertionError('body continued after exceeding byte budget')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        response = await client.post(URL, content=chunks(), headers={'Content-Type': 'application/json'})
    assert response.status_code == 413 and response.headers['cache-control'] == 'no-store'
    assert not calls


@pytest.mark.parametrize('header', [{'Host': 'attacker.example'}, {'Origin': 'https://attacker.example'}])
def test_comparison_keeps_local_host_origin_boundary(comparison_client, header):
    client, _ = comparison_client
    assert client.post(URL, content=b'{' * 65537, headers=header).status_code == 403


def test_budget_is_actual_serialized_http_bytes(comparison_client, vault, tmp_path, monkeypatch):
    import app.research_replay.transport as transport
    client, _ = comparison_client
    request = body(vault, tmp_path)
    original = client.post(URL, json=request)
    assert original.status_code == 200
    actual = len(original.content)
    monkeypatch.setattr(transport, 'MAX_RESPONSE_BYTES', actual)
    assert client.post(URL, json=request).content == original.content
    monkeypatch.setattr(transport, 'MAX_RESPONSE_BYTES', actual - 1)
    rejected = client.post(URL, json=request)
    assert rejected.status_code == 422 and rejected.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('operation', ['compare_scenario_historical', 'historical_catalog'])
async def test_failed_cancelled_worker_retains_admission_until_shutdown_completes(monkeypatch, operation):
    worker = SimulationExecutor()
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = Event()
    async def held(self, **kwargs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        raise ValueError('controlled worker failure')
    monkeypatch.setattr(SimulationService, operation, held)
    task = asyncio.create_task(worker.execute(operation))
    shutdown = None
    try:
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Concurrent computational and metadata contenders share one owner.
        contenders = await asyncio.gather(*(worker.execute(operation) for _ in range(20)), return_exceptions=True)
        assert all(isinstance(result, ResearchBusyError) for result in contenders)
        shutdown = asyncio.create_task(worker.shutdown())
        await asyncio.sleep(.02)
        assert not shutdown.done() and worker._busy
        with pytest.raises(ResearchBusyError):
            await worker.execute(operation)
    finally:
        release.set()
        await (shutdown if shutdown is not None else worker.shutdown())
    assert not worker._busy


from test_redis_infrastructure import infrastructure


async def test_redis_comparison_cancellation_keeps_native_worker_ownership(infrastructure, vault, tmp_path, monkeypatch):
    import json
    from app.agents.config import AgentConfig
    from app.infrastructure.research import CoordinatedSimulationExecutor
    from app.risk.firewall import RiskFirewallConfig
    from app.strategy.models import StrategyConfig
    from test_phase146_research_markets import demo
    infra, _ = infrastructure
    worker = CoordinatedSimulationExecutor(SimulationExecutor(), infra, lambda: ('165d', 'session'))
    loop, started, release = asyncio.get_running_loop(), asyncio.Event(), Event()
    original = SimulationService.compare_scenario_historical
    completed = []
    async def held(self, **kwargs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        result = await original(self, **kwargs)
        completed.append(result)
        return result
    monkeypatch.setattr(SimulationService, 'compare_scenario_historical', held)
    request = ScenarioHistoricalRequest.model_validate(body(vault, tmp_path))
    job = asyncio.create_task(worker.execute('compare_scenario_historical', storage_root=vault.root,
        request=request, strategy=StrategyConfig(), agents=AgentConfig(), risk=RiskFirewallConfig(), market_profile=demo('BTC')))
    try:
        await asyncio.wait_for(started.wait(), 5)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):await job
        with pytest.raises(ResearchBusyError):await worker.execute('historical_catalog', storage_root=vault.root)
        assert worker.local._busy
    finally:
        release.set()
        await worker.shutdown()
    keys = await infra.call('keys', infra.key('research-job', '165d', 'session', '*'))
    status = json.loads(await infra.call('get', keys[0]))
    mirrored = json.loads(await infra.call('get', status['result_key']))
    assert status['status'] == 'COMPLETED'
    assert ScenarioHistoricalResponse.model_validate(mirrored['result']) == completed[0]
    assert not worker.local._busy


@pytest.mark.parametrize('latency,cancel_latency', [(0, 0), (1, 2)])
async def test_partial_fills_defer_stale_quotes_then_reauthorize_next_frame(vault, tmp_path, monkeypatch, latency, cancel_latency):
    from app.agents.config import AgentConfig
    from app.execution.order_manager import OrderManager
    from app.risk.firewall import RiskFirewallConfig
    from app.strategy.models import StrategyConfig
    from phase1641_fixtures import admit
    from phase165d_fixtures import bounded_dataset
    from test_phase146_research_markets import demo
    d = admit(vault, tmp_path/'incoming', bounded_dataset(128, crossing=True))
    request = ScenarioHistoricalRequest(research_market='BTC', frames=4,
        historical=dict(dataset_id=d.dataset_id, dataset_fingerprint=d.dataset_fingerprint, market='BTC',
            max_frames=128, policy=dict(max_component_age_ms=1000),
            execution=dict(size_decimals=5, paper=dict(mode='MODELED_CROSSING', order_latency_ms=latency,
                cancel_latency_ms=cancel_latency, depth_sensitive=True, participation_rate='0.5', max_fill_fraction='0.5'))))
    original = OrderManager.reconcile_locked
    deferred = []
    async def observe(self, *args, **kwargs):
        authority = self.authority
        async def inspect_authority():
            allowed = await authority()
            if allowed is False:deferred.append(True)
            return allowed
        self.authority = inspect_authority
        try:return await original(self, *args, **kwargs)
        finally:self.authority = authority
    monkeypatch.setattr(OrderManager, 'reconcile_locked', observe)
    result = await SimulationService().compare_scenario_historical(storage_root=vault.root, request=request,
        strategy=StrategyConfig(), agents=AgentConfig(), risk=RiskFirewallConfig(enabled=False), market_profile=demo('BTC'))
    assert next(r for r in result.receipt.rows if r.name == 'fill_count').historical_segment.value > 0
    assert deferred  # exercises the formerly aborting path, including baseline sensitivity
    assert result.receipt.foundation.classification == 'CONTEXT_ONLY'
    assert not result.receipt.differences_available


@pytest.mark.parametrize('value', ['0', '-0', '0E+5', '1E-60', '-1E-60',
    '12345.123456789123456789', '-12345.123456789123456789'])
def test_metric_wire_values_roundtrip_exactly_without_imputation(value):
    import json
    observed = MetricObservation(origin='SIMULATION_METRICS', availability='AVAILABLE', value=value)
    assert observed.value.as_tuple() == Decimal(value).as_tuple()
    assert json.loads(observed.model_dump_json())['value'] == str(Decimal(value))
    assert MetricObservation.model_validate_json(observed.model_dump_json()) == observed
    missing = MetricObservation(origin='PAPER_VAULT', availability='NOT_REPORTED')
    assert missing.value is None


@pytest.mark.parametrize('existing', [False, True])
async def test_explicit_authority_deferral_never_submits_or_counts_a_create(existing):
    from app.execution.models import OrderRequest
    from app.execution.order_manager import OrderManager
    from app.execution.paper import PaperExecutionAdapter
    from test_execution import q
    paper = PaperExecutionAdapter()
    if existing:
        await paper.submit_orders([OrderRequest(client_order_id='old', market='ETH', side='BID', price='2900', size='1', level_index=0)])
    manager = OrderManager(paper, authority=lambda: False)
    actions = await manager.reconcile('ETH', [q()], Decimal(1), Decimal('.01'))
    assert [a.action.value for a in actions] == (['CANCEL'] if existing else [])
    assert not await paper.get_open_orders()
    async def denied():raise PermissionError('controlled stale authorization')
    manager.authority = denied
    with pytest.raises(PermissionError):
        await manager.reconcile('ETH', [q()], Decimal(1), Decimal('.01'))
    assert not await paper.get_open_orders()


@pytest.mark.parametrize('kill', [False, True])
async def test_seeded_state_survives_invalid_busy_and_cancelled_comparison(comparison_client, vault, tmp_path, monkeypatch, kill):
    from pathlib import Path
    from app.execution.models import OrderRequest
    from app.main import app
    from app.market_data.mock import MockMarketDataAdapter
    from test_phase14_research_vault import authority
    _, rt = comparison_client
    request = body(vault, tmp_path, kind='gap')
    frame = MockMarketDataAdapter().snapshot_for(4)
    await rt.market._accept(frame)
    await rt.refresh_once()
    await rt.paper.submit_orders([OrderRequest(client_order_id='165d-seed', market='ETH', side='BID', price=frame.best_ask, size='0.1')])
    await rt.refresh_once()
    rt.strategy.running = True
    rt.accounting_service.reserve(rt.quotes, await rt.execution.get_open_orders())
    if kill:await rt.activate_kill()
    before = deepcopy(authority(rt))
    signer = (id(rt.testnet), rt.testnet.private_key, rt.testnet.account_address, rt.testnet.enabled)
    stored = {p.name:p.read_bytes() for p in Path(vault.root).glob('*.json')}
    worker = app.state.simulation_executor
    original = SimulationService.compare_scenario_historical
    loop, started, release = asyncio.get_running_loop(), asyncio.Event(), Event()
    completed = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        invalid = deepcopy(request)
        invalid['historical']['dataset_fingerprint'] = '0'*64
        assert (await client.post(URL, json=invalid)).status_code == 422
        async def held(self, **kwargs):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(10)
            completed.append(await original(self, **kwargs))
            return completed[-1]
        monkeypatch.setattr(SimulationService, 'compare_scenario_historical', held)
        task = asyncio.create_task(client.post(URL, json=request))
        try:
            await asyncio.wait_for(started.wait(), 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert (await client.post(URL, json=request)).status_code == 429
            assert worker._busy
        finally:
            release.set()
            await worker.shutdown()
    assert completed[0].segment_count == 2
    assert authority(rt) == before
    assert signer == (id(rt.testnet), rt.testnet.private_key, rt.testnet.account_address, rt.testnet.enabled)
    assert stored == {p.name:p.read_bytes() for p in Path(vault.root).glob('*.json')}


@pytest.mark.parametrize('source', ['another_scenario', 'another_dataset', 'another_segment'])
async def test_valid_evidence_cannot_substitute_for_original_bound_identity(vault, tmp_path, source):
    from app.research_replay.comparison import CapturedScenarioResult
    from app.research_replay.contracts import HistoricalReplayResult
    from test_phase165a2_integration import pair
    original, replay = await pair(vault, tmp_path/'first')
    other, other_replay = await pair(vault, tmp_path/'second', 'ETH', kind='gap')
    if source == 'another_scenario':
        forged = original.model_copy(update={'result':other.result})
        with pytest.raises(ValidationError):CapturedScenarioResult.model_validate_json(forged.model_dump_json())
    else:
        replacement = other_replay.segments[-1 if source == 'another_segment' else 0]
        forged = replay.model_copy(update={'segments':(replacement,)})
        with pytest.raises(ValidationError):HistoricalReplayResult.model_validate_json(forged.model_dump_json())


@pytest.mark.parametrize('value', [1.25, '1E+1000000', '1E-1000000'])
def test_existing_scenario_route_shares_exact_capital_boundary(comparison_client, value, monkeypatch):
    from app.main import app
    calls = []
    async def unexpected(*args, **kwargs):calls.append(args)
    monkeypatch.setattr(app.state.simulation_executor, 'execute', unexpected)
    client, _ = comparison_client
    response = client.post('/api/v1/simulation/run', json=dict(frames=4, include_comparison_provenance=True,
        simulation=dict(initial_equity_quote=value)))
    assert response.status_code == 422 and not calls
