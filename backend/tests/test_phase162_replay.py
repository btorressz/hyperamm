"""Native deterministic replay acceptance through secure admission and PAPER."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
from threading import Event

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.agents.config import AgentConfig
from app.research_replay.adapter import prepare_replay, segment_dataset
from app.research_replay.contracts import (
    HistoricalReplayRequest, HistoricalReplayResult, ReplayRejected,
)
from app.research_replay.storage import HistoricalStorage
from app.research_replay.validation import validate_bytes
from app.risk.firewall import RiskFirewallConfig
from app.simulation.engine import SimulationEngine
from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.models import stable_fingerprint
from app.simulation.service import SimulationService
from app.strategy.models import StrategyConfig
from test_phase161a_contracts import T, sample
from test_redis_infrastructure import infrastructure  # shared native fake-Redis fixture


def capture(*, market="BTC", native=True, times=(0, 1, 2, 3), partial=None,
            gaps=(), generations=None, context_offset_ms=0, reverse_ties=False):
    value = sample(native=native).model_dump(mode="json")
    value.update(dataset_fingerprint=None, market=market, dataset_id=f"{market}-capture")
    value["source"]["market"] = market
    value["observations"] = []
    for index, seconds in enumerate(times):
        context = dict(mark_price="60000", oracle_price="60000", funding_rate="0.0001", open_interest_base="10")
        if partial and index in partial:
            context = partial[index]
        common = dict(market=market, observer_instance_id="observer-1",
            connection_generation=generations[index] if generations else 1)
        context_point = dict(**common, kind="PERP_CONTEXT", received_at=(T + timedelta(seconds=seconds,
            milliseconds=context_offset_ms)).isoformat(), perp_context=context)
        book_point = dict(**common, kind="L2", received_at=(T + timedelta(seconds=seconds)).isoformat(),
            source_timestamp=(T + timedelta(seconds=seconds, milliseconds=-10)).isoformat(),
            source_event_time_verified=native, order_book=sample().observations[0].order_book.model_dump(mode="json"))
        pair = [book_point, context_point] if reverse_ties or context_offset_ms > 0 else [context_point, book_point]
        for point in pair:
            point["sequence"] = len(value["observations"]) + 1
            value["observations"].append(point)
    value["coverage_start"] = value["observations"][0]["received_at"]
    value["coverage_end"] = value["observations"][-1]["received_at"]
    value["gaps"] = [dict(start_at=(T + timedelta(seconds=a)).isoformat(),
        end_at=(T + timedelta(seconds=b)).isoformat(), reason=reason) for a, b, reason in gaps]
    return validate_bytes(json.dumps(value).encode())


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    root.mkdir(mode=0o700)
    return HistoricalStorage(root)


def request_for(dataset, **overrides):
    return HistoricalReplayRequest(dataset_id=dataset.dataset_id, dataset_fingerprint=dataset.dataset_fingerprint,
        market=dataset.market, execution={"size_decimals": 5}, **overrides)


def inputs(vault, dataset, **overrides):
    return dict(storage_root=vault.root, request=request_for(dataset, **overrides),
        strategy=StrategyConfig(), agents=AgentConfig(), risk=RiskFirewallConfig())


@pytest.mark.parametrize("market", ["BTC", "ETH", "SOL"])
@pytest.mark.parametrize("native", [True, False])
async def test_deterministic_complete_reproduction_and_provenance(vault, market, native):
    dataset = vault.save(capture(market=market, native=native))
    service = SimulationService()
    first = await service.replay_history(**inputs(vault, dataset))
    second = await service.replay_history(**inputs(vault, dataset))
    assert first == second
    assert first.result_fingerprint == stable_fingerprint(first.model_dump(exclude={"result_fingerprint"}))
    assert HistoricalReplayResult.model_validate_json(first.model_dump_json()) == first
    assert first.provenance.dataset_fingerprint == dataset.dataset_fingerprint
    assert first.provenance.source_kind == dataset.source.source_kind
    assert first.frame_count == 4 and len(first.segments) == 1 and not first.issues
    segment = first.segments[0]
    for frame in segment.frames:
        assert frame.economics == ("RECORDED_VALUES" if native else "SYNTHETIC_FIXTURE_VALUES")
        assert frame.context_observation.source_timestamp is None
        assert frame.context_observation.source_event_time_verified is False
    archive = json.loads(segment.simulation_result_json)
    assert archive["simulated"] is True and archive["scenario"] == "historical-replay"
    assert archive["research_assumptions"] is None
    assert first.read_only and first.authority == "NONE"
    with pytest.raises(ValidationError):
        first.segments[0].frames[0].book_observation.order_book.bids[0].size = Decimal(8)
    with pytest.raises(ValidationError):
        first.request.execution.accounting.initial_equity_quote = Decimal(8)


@pytest.mark.parametrize("kind", ["gap", "generation", "observer", "interval"])
async def test_discontinuities_reset_all_engine_states(vault, kind, monkeypatch):
    dataset = capture(times=(0, 1, 4, 5), gaps=((1, 4, "DISCONNECT"),) if kind != "interval" else (),
                      generations=(1, 1, 2, 2) if kind == "generation" else None)
    if kind == "observer":
        value = dataset.model_dump(mode="json")
        value["dataset_fingerprint"] = None
        for point in value["observations"][4:]:
            point["observer_instance_id"] = "observer-2"
        dataset = validate_bytes(json.dumps(value).encode())
    vault.save(dataset)
    calls = []
    original = SimulationEngine.run
    async def observed(self, **kwargs):
        result = await original(self, **kwargs)
        calls.append((kwargs["dataset"], result))
        return result
    monkeypatch.setattr(SimulationEngine, "run", observed)
    result = await SimulationService().replay_history(**inputs(vault, dataset))
    assert [x.frame_count for x in result.segments] == [2, 2]
    assert result.segments[1].reset_reason == {"gap": "DECLARED_GAP", "generation": "OBSERVER_CHANGE",
        "observer": "OBSERVER_CHANGE", "interval": "RECEIPT_INTERVAL"}[kind]
    assert len(calls) == 2
    for _, output in calls:
        assert output.metrics.starting_equity == Decimal("100000")
        assert output.trace[0].inventory_base == 0
    assert result.declared_gaps == dataset.gaps


@pytest.mark.parametrize("missing", ["mark_price", "oracle_price", "funding_rate", "open_interest_base"])
async def test_partial_context_rejects_without_economic_imputation(vault, missing):
    complete = dict(mark_price="60000", oracle_price="60000", funding_rate="0", open_interest_base="10")
    del complete[missing]
    dataset = vault.save(capture(partial={i: complete for i in range(4)}))
    with pytest.raises(ReplayRejected) as caught:
        await SimulationService().replay_history(**inputs(vault, dataset))
    issues = caught.value.rejection.issues
    assert issues[-1].code == "NO_VIABLE_FRAMES"
    assert all(issue.missing_fields == (missing,) for issue in issues[:-1])


async def test_partial_new_context_invalidates_old_context_and_breaks_orders(vault):
    dataset = vault.save(capture(times=(0, 1, 2, 3, 4), partial={2: {"mark_price": "60000"}}))
    result = await SimulationService().replay_history(**inputs(vault, dataset))
    assert [x.frame_count for x in result.segments] == [2, 2]
    assert result.segments[1].reset_reason == "UNAVAILABLE_FRAME"
    assert result.issues[0].missing_fields == ("oracle_price", "funding_rate", "open_interest_base")


@pytest.mark.parametrize("component", ["L2", "PERP_CONTEXT"])
async def test_missing_component_zero_viable_frames(vault, component):
    value = capture().model_dump(mode="json")
    value["dataset_fingerprint"] = None
    value["observations"] = [p for p in value["observations"] if p["kind"] != component]
    for index, point in enumerate(value["observations"]):
        point["sequence"] = index
    dataset = vault.save(validate_bytes(json.dumps(value).encode()))
    with pytest.raises(ReplayRejected) as caught:
        await SimulationService().replay_history(**inputs(vault, dataset))
    assert caught.value.rejection.issues[-1].code == "NO_VIABLE_FRAMES"
    assert caught.value.rejection.issues[0].missing_fields == (("order_book",) if component == "L2" else ("perp_context",))


@pytest.mark.parametrize("reverse", [False, True])
def test_timestamp_ties_are_receipt_batches_without_invented_time(reverse):
    dataset = capture(reverse_ties=reverse)
    plan, issues, examined = prepare_replay(dataset, request_for(dataset))
    assert not issues and examined == 8
    assert [x.sequence for x in plan[0].frames] == [2, 4, 6, 8]
    assert [x.timestamp for x in plan[0].frames] == [T + timedelta(seconds=i) for i in range(4)]
    assert plan[0].evidence[0].receipt_batch_sequences == (1, 2)
    assert segment_dataset(plan[0], request_for(dataset)).fingerprint


def test_unverified_source_time_never_changes_receipt_order():
    value = capture().model_dump(mode="json")
    value["dataset_fingerprint"] = None
    for point in value["observations"]:
        if point["kind"] == "L2":
            point["source_timestamp"] = None
            point["source_event_time_verified"] = False
    dataset = validate_bytes(json.dumps(value).encode())
    plan, _, _ = prepare_replay(dataset, request_for(dataset))
    assert all(not p.book_observation.source_event_time_verified for p in plan[0].evidence)
    assert all(p.book_observation.source_timestamp is None for p in plan[0].evidence)


async def test_explicit_temporal_model_is_separately_fingerprinted(vault):
    dataset = vault.save(capture(context_offset_ms=20))
    with pytest.raises(ReplayRejected):
        await SimulationService().replay_history(**inputs(vault, dataset))
    result = await SimulationService().replay_history(**inputs(vault, dataset,
        policy={"max_component_age_ms": 1000}))
    assert result.modeling_fingerprint != stable_fingerprint((request_for(dataset).policy, request_for(dataset).execution))
    assert result.provenance.dataset_fingerprint == dataset.dataset_fingerprint
    assert all(x.evaluated_at >= x.book_observation.received_at for x in result.segments[0].frames)
    assert result.issues[0].missing_fields == ("perp_context",)


def test_zero_l2_size_is_unavailable_instead_of_filtered_or_fabricated():
    value = capture().model_dump(mode="json")
    value["dataset_fingerprint"] = None
    for point in value["observations"]:
        if point["kind"] == "L2":
            point["order_book"]["bids"][0]["size"] = "0"
    dataset = validate_bytes(json.dumps(value).encode())
    with pytest.raises(ReplayRejected) as caught:
        prepare_replay(dataset, request_for(dataset))
    assert caught.value.rejection.issues[0].missing_fields == ("positive_l2_sizes",)


def test_segment_bound_and_short_segments_never_fabricate_a_second_frame():
    dataset = capture(times=tuple(i * 3 for i in range(4)))
    with pytest.raises(ReplayRejected) as caught:
        prepare_replay(dataset, request_for(dataset))
    assert sum(x.code == "SHORT_SEGMENT" for x in caught.value.rejection.issues) == 4
    assert caught.value.rejection.issues[-1].code == "NO_VIABLE_FRAMES"
    times = tuple(second for i in range(33) for second in (i * 4, i * 4 + 1))
    dataset = capture(times=times)
    with pytest.raises(ReplayRejected) as caught:
        prepare_replay(dataset, request_for(dataset))
    assert caught.value.rejection.issues[-1].code == "SEGMENT_LIMIT"


async def test_corrupt_storage_and_forged_request_never_reach_engine(vault, monkeypatch):
    from pathlib import Path
    dataset = vault.save(capture())
    async def forbidden(*args, **kwargs):
        pytest.fail("unsupported evidence reached the simulation engine")
    monkeypatch.setattr(SimulationEngine, "run", forbidden)
    args = inputs(vault, dataset)
    args["request"] = args["request"].model_copy(update={"max_frames": True})
    with pytest.raises(ValidationError):
        await SimulationService().replay_history(**args)
    path = next(Path(vault.root).glob("*.json"))
    path.write_text(path.read_text().replace('"mark_price":"60000"', '"mark_price":"60001"'))
    with pytest.raises(ValueError, match="corrupt"):
        await SimulationService().replay_history(**inputs(vault, dataset))


async def test_window_and_output_controls_preserve_evidence_and_change_identity(vault):
    dataset = vault.save(capture())
    service = SimulationService()
    full = await service.replay_history(**inputs(vault, dataset))
    window = await service.replay_history(**inputs(vault, dataset,
        start_at=T + timedelta(seconds=1), end_at=T + timedelta(seconds=2), record_trace=False))
    assert window.frame_count == 2 and window.examined_observation_count == 4
    assert window.segments[0].frames[0].evaluated_at == T + timedelta(seconds=1)
    assert window.provenance == full.provenance
    assert window.result_fingerprint != full.result_fingerprint
    assert json.loads(window.segments[0].simulation_result_json)["trace"] == []
    bad = window.model_dump(mode="json")
    bad["segments"][0]["simulation_result_json"] = "{}"
    with pytest.raises(ValidationError, match="fingerprint"):
        HistoricalReplayResult.model_validate(bad)


@pytest.mark.parametrize("change,code", [({"dataset_fingerprint": "0" * 64}, "IDENTITY_MISMATCH"),
    ({"market": "SOL"}, "IDENTITY_MISMATCH"), ({"max_frames": 2}, "FRAME_LIMIT"),
    ({"start_at": T + timedelta(seconds=8)}, "NO_VIABLE_FRAMES"),
    ({"end_at": T}, "NO_VIABLE_FRAMES")])
async def test_replay_rejections_are_structured(vault, change, code):
    dataset = vault.save(capture())
    args = inputs(vault, dataset)
    args["request"] = HistoricalReplayRequest.model_validate({**args["request"].model_dump(), **change})
    with pytest.raises(ReplayRejected) as caught:
        await SimulationService().replay_history(**args)
    assert caught.value.rejection.issues[-1].code == code


@pytest.mark.parametrize("change", [{"max_frames": True}, {"market": "DOGE"}, {"execution": {}},
    {"policy": {"max_component_age_ms": 30001}}, {"policy": {"missing_economics": "IMPUTE"}},
    {"execution": {"size_decimals": 3, "external_references": "FABRICATE"}}, {"storage_root": "/tmp"}])
def test_request_fail_closed(change):
    value = request_for(capture()).model_dump(mode="json")
    with pytest.raises(ValidationError):
        HistoricalReplayRequest.model_validate({**value, **change})


@pytest.mark.parametrize("cancel", [False, True])
async def test_shared_slot_concurrency_cancellation_and_shutdown(vault, monkeypatch, cancel):
    dataset = vault.save(capture())
    loop, started, release = asyncio.get_running_loop(), asyncio.Event(), Event()
    original = SimulationEngine.run
    async def held(self, **kwargs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        return await original(self, **kwargs)
    monkeypatch.setattr(SimulationEngine, "run", held)
    executor = SimulationExecutor()
    first = asyncio.create_task(executor.execute("replay_history", **inputs(vault, dataset)))
    shutdown = None
    try:
        await asyncio.wait_for(started.wait(), 5)
        if cancel:
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
        for operation in ("replay_history", "run_scenario", "optimize", "historical_catalog"):
            with pytest.raises(ResearchBusyError):
                await executor.execute(operation)
        shutdown = asyncio.create_task(executor.shutdown())
        await asyncio.sleep(0)
        assert not shutdown.done()
        with pytest.raises(ResearchBusyError):
            await executor.execute("replay_history")
    finally:
        release.set()
        if not cancel:
            assert (await first).frame_count == 4
        await (shutdown if shutdown else executor.shutdown())
    assert not executor._busy
    assert all(not thread.is_alive() for thread in executor._pool._threads)


async def test_existing_coordinated_executor_admits_and_mirrors_replay(vault, infrastructure):
    from app.infrastructure.research import CoordinatedSimulationExecutor
    infra, _ = infrastructure
    dataset = vault.save(capture())
    executor = CoordinatedSimulationExecutor(SimulationExecutor(), infra, lambda: ("p162", "s162"))
    try:
        result = await executor.execute("replay_history", **inputs(vault, dataset))
        keys = await infra.call("keys", infra.key("research-job", "p162", "s162", "*"))
        status = json.loads(await infra.call("get", keys[0]))
        assert status["operation"] == "replay_history" and status["status"] == "COMPLETED"
        mirrored = json.loads(await infra.call("get", status["result_key"]))
        assert mirrored["result"] == result.model_dump(mode="json")
        assert result.result_fingerprint in json.dumps(mirrored)
        assert 0 < await infra.call("ttl", status["result_key"]) <= 30
    finally:
        await executor.shutdown()


@pytest.fixture
def replay_client(vault, monkeypatch):
    from app.config import Settings
    from app.main import app
    from app.runtime import HyperAmmRuntime
    rt = HyperAmmRuntime(Settings(_env_file=None))
    executor = SimulationExecutor()
    monkeypatch.setattr(app.state, "runtime", rt, raising=False)
    monkeypatch.setattr(app.state, "simulation_executor", executor, raising=False)
    monkeypatch.setattr(app.state, "historical_replay_root", vault.root, raising=False)
    # No lifespan: live runtime authority remains frozen for isolation assertions.
    client = TestClient(app)
    yield client, rt
    client.close()
    asyncio.run(executor.shutdown())


def test_read_only_apis_and_safe_errors(vault, replay_client, monkeypatch):
    from app.main import app
    dataset = vault.save(capture())
    client, rt = replay_client
    assert client.get("/api/v1/historical-replay/datasets").json() == [dataset.dataset_id]
    response = client.get("/api/v1/historical-replay/provenance", params={"dataset_id": dataset.dataset_id})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    body = request_for(dataset).model_dump(mode="json")
    response = client.post("/api/v1/historical-replay/run", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["provenance"]["dataset_fingerprint"] == dataset.dataset_fingerprint
    body["dataset_fingerprint"] = "0" * 64
    rejection = client.post("/api/v1/historical-replay/run", json=body)
    assert rejection.status_code == 422 and rejection.json()["detail"]["issues"][0]["code"] == "IDENTITY_MISMATCH"
    assert client.post("/api/v1/historical-replay/datasets", json={}).status_code == 405
    assert client.post("/api/v1/historical-replay/run", json={**body, "storage_root": "private-path"}).status_code == 422
    assert "private-path" not in client.post("/api/v1/historical-replay/run", json={**body, "storage_root": "private-path"}).text
    monkeypatch.setattr(app.state, "historical_replay_root", None)
    assert client.get("/api/v1/historical-replay/datasets").status_code == 503


async def test_concurrent_http_requests_and_cancelled_waiter_share_existing_worker(vault, monkeypatch):
    from app.config import Settings
    from app.main import app
    from app.runtime import HyperAmmRuntime
    dataset = vault.save(capture())
    rt, worker = HyperAmmRuntime(Settings(_env_file=None)), SimulationExecutor()
    monkeypatch.setattr(app.state, "runtime", rt, raising=False)
    monkeypatch.setattr(app.state, "simulation_executor", worker, raising=False)
    monkeypatch.setattr(app.state, "historical_replay_root", vault.root, raising=False)
    loop, started, release = asyncio.get_running_loop(), asyncio.Event(), Event()
    original = SimulationEngine.run
    async def held(self, **kwargs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        return await original(self, **kwargs)
    monkeypatch.setattr(SimulationEngine, "run", held)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        first = asyncio.create_task(client.post("/api/v1/historical-replay/run",
            json=request_for(dataset).model_dump(mode="json")))
        try:
            await asyncio.wait_for(started.wait(), 5)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            for path, body in (("/historical-replay/run", request_for(dataset).model_dump(mode="json")),
                               ("/simulation/run", {"frames": 3})):
                response = await client.post("/api/v1" + path, json=body)
                assert response.status_code == 429
            assert (await client.get("/api/v1/historical-replay/datasets")).status_code == 429
            assert worker._busy
        finally:
            release.set()
            await worker.shutdown()


@pytest.mark.parametrize("kill", [False, True])
async def test_replay_preserves_seeded_paper_and_authority(vault, kill):
    from app.config import Settings
    from app.runtime import HyperAmmRuntime
    from app.execution.models import OrderRequest
    from app.market_data.mock import MockMarketDataAdapter
    from test_phase14_research_vault import authority
    rt = HyperAmmRuntime(Settings(_env_file=None))
    frame = MockMarketDataAdapter().snapshot_for(4)
    await rt.market._accept(frame)
    await rt.refresh_once()
    await rt.paper.submit_orders([OrderRequest(client_order_id="162-seed", market="ETH", side="BID",
        price=frame.best_ask, size=Decimal(".1"))])
    await rt.refresh_once()
    rt.strategy.running = True
    await rt._execution_authority()
    async with rt.execution_lock:
        await rt.orders.reconcile_locked(rt.config.market, rt.quotes,
            rt.config.replace_tolerance_bps, rt.config.size_tolerance)
    rt.accounting_service.reserve(rt.quotes, await rt.execution.get_open_orders())
    if kill:
        await rt.activate_kill()
        await rt.refresh_once()
    before = deepcopy(authority(rt))
    services = tuple(id(x) for x in (rt.market, rt.perp_context_service, rt.reference_service, rt.testnet))
    executor = SimulationExecutor()
    try:
        for market in ("BTC", "ETH", "SOL"):
            dataset = vault.save(capture(market=market))
            args = inputs(vault, dataset)
            args.update(strategy=rt.config.model_copy(deep=True), agents=rt.agent_config.model_copy(deep=True),
                        risk=rt.risk_config.model_copy(deep=True))
            assert (await executor.execute("replay_history", **args)).frame_count == 4
            args["request"] = args["request"].model_copy(update={"dataset_fingerprint": "0" * 64})
            with pytest.raises(ReplayRejected):
                await executor.execute("replay_history", **args)
    finally:
        await executor.shutdown()
    assert authority(rt) == before
    assert services == tuple(id(x) for x in (rt.market, rt.perp_context_service, rt.reference_service, rt.testnet))
