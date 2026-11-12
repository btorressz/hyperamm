"""Phase 17.3 real HTTP, lifecycle failures and bounded native integration."""
import asyncio

import pytest

from app.infrastructure.research import ResearchUnavailableError
from app.main import app
from app.portfolio_research.models import PortfolioAnalysisResult
from app.simulation.executor import ResearchBusyError
from app.simulation.service import SimulationService
from phase172_fixtures import portfolio
from phase173_fixtures import request_for
from test_phase14_research_vault import authority, research_client
from test_phase166c2_local_integration import local_server
from phase173_fixtures import native
from itertools import combinations

URL = "/api/v1/portfolio-research/analyze"


@pytest.mark.parametrize("markets", [c for n in (1, 2, 3) for c in combinations(("BTC", "ETH", "SOL"), n)])
async def test_all_seven_market_selections(markets):
    _, receipts, _, result = await native(portfolio(markets, frames=6))
    assert result.execution.selected_markets == markets
    assert len(result.accounting.contributions) == len(markets)
    assert result.temporal.classification == "MODELED_ALIGNED"
    assert PortfolioAnalysisResult.model_validate_json(result.model_dump_json()) == result


def test_remote_peer_is_rejected_before_computation():
    from fastapi.testclient import TestClient
    with TestClient(app, client=("203.0.113.10", 12345)) as client:
        response = client.post(URL, json=request_for().model_dump(mode="json"))
        assert response.status_code == 403


@pytest.mark.parametrize("corruption", ["missing_accounting", "missing_trace", "unknown_equity", "wrong_timestamp"])
def test_native_evidence_collection_before_discard(research_client, monkeypatch, corruption):
    from app.research_replay.comparison import ScenarioProvenanceReceipt
    client, _ = research_client
    original = SimulationService.run_scenario
    calls = []
    async def corrupt(self, **kwargs):
        value = await original(self, **kwargs)
        calls.append(kwargs["strategy"].market)
        if calls[-1] == "ETH":
            if corruption == "missing_accounting": value.result.vault = None
            elif corruption == "missing_trace": value.result.trace = []
            elif corruption == "unknown_equity": value.result.trace[0].equity = None
            else:
                from datetime import timedelta
                value.result.trace[0].timestamp += timedelta(seconds=10)
            return value.model_copy(update={"provenance": ScenarioProvenanceReceipt.bind(result=value.result,
                captured=value.provenance.captured, scenario=value.provenance.requested_scenario, frames=value.provenance.requested_frames)})
        return value
    monkeypatch.setattr(SimulationService, "run_scenario", corrupt)
    response = client.post(URL, json=request_for().model_dump(mode="json"))
    if corruption in {"missing_trace", "wrong_timestamp"}:
        assert response.status_code == 200, response.text
        result = PortfolioAnalysisResult.model_validate_json(response.content)
        assert result.temporal.classification == "UNAVAILABLE" and result.risk.outcome == "BLOCKED"
        assert result.accounting.equity_quote is None and result.accounting.drawdown is None
        assert calls == ["BTC", "ETH", "SOL"]
    else:
        assert response.status_code == 422
        assert calls == ["BTC", "ETH"]
    assert not app.state.simulation_executor._busy


def test_real_router_returns_exact_typed_validated_native_json(research_client):
    client, rt = research_client
    request = request_for()
    expected = asyncio.run(SimulationService().analyze_portfolio_research(request=request))
    before = authority(rt)
    response = client.post(URL, json=request.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == expected.model_dump(mode="json")
    assert PortfolioAnalysisResult.model_validate_json(response.content) == expected
    assert len(response.content) <= 200000
    assert authority(rt) == before


@pytest.mark.parametrize("kind", ["missing", "hash", "result", "extra", "budget", "profile"])
def test_invalid_request_is_sanitized_no_store_and_never_executes(research_client, monkeypatch, kind):
    client, rt = research_client
    body = request_for().model_dump(mode="json")
    if kind == "missing": body = {}
    elif kind == "hash": body["config_fingerprint"] = "f" * 64
    elif kind == "result": body["markets"] = [{"result_fingerprint": "a" * 64}]
    elif kind == "extra": body["/private/secret-fixture"] = "forbidden"
    elif kind == "budget": body = {"config": portfolio(frames=1001).model_dump(mode="json"), "config_fingerprint": "0" * 64}
    else: body["config"]["scenarios"][0]["captured"]["market_profile_fingerprint"] = "0" * 64
    async def forbidden(*args, **kwargs): pytest.fail("invalid input entered worker")
    monkeypatch.setattr(app.state.simulation_executor, "execute", forbidden)
    before = authority(rt)
    result = client.post(URL, json=body)
    assert result.status_code == 422 and result.headers["cache-control"] == "no-store"
    assert "/private/secret-fixture" not in result.text
    assert authority(rt) == before


@pytest.mark.parametrize("chunked", [False, True])
def test_request_body_enforced_before_json_parsing(research_client, chunked):
    client, _ = research_client
    body = iter([b"x" * 40000, b"x" * 40000]) if chunked else b"x" * 65537
    result = client.post(URL, content=body)
    assert result.status_code == 413 and result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("headers", [{"Host": "attacker.invalid"}, {"Origin": "https://attacker.invalid"},
    {"Origin": "http://127.0.0.1:5999"}, {"X-Forwarded-For": "127.0.0.1"}])
def test_local_only_boundary_applies_to_new_route(research_client, headers):
    client, _ = research_client
    assert client.post(URL, headers=headers, json=request_for().model_dump(mode="json")).status_code == 403


@pytest.mark.parametrize("exception,status", [(ResearchBusyError("/private/secret"), 429),
    (ResearchUnavailableError(), 503), (ValueError("/private/secret"), 422), (RuntimeError("/private/secret"), 500)])
def test_admission_and_internal_errors_are_sanitized(research_client, monkeypatch, exception, status):
    client, rt = research_client
    async def broken(*args, **kwargs): raise exception
    monkeypatch.setattr(app.state.simulation_executor, "execute", broken)
    before = authority(rt)
    response = client.post(URL, json=request_for().model_dump(mode="json"))
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "/private/secret" not in response.text and "Traceback" not in response.text
    assert authority(rt) == before


@pytest.mark.parametrize("stage", ["scenario", "engine", "dataset", "accounting", "result_hash", "bundle", "serialization"])
def test_execution_stage_failure_stops_at_eth_and_releases_worker(research_client, monkeypatch, stage):
    from app.simulation import service as sim_service
    from app.portfolio_research import service as portfolio_service, aggregation
    client, rt = research_client
    markets = []
    original = SimulationService.run_scenario
    async def observe(self, **kwargs):
        market = kwargs["strategy"].market
        markets.append(market)
        if market == "ETH" and stage == "scenario":
            monkeypatch.setattr(sim_service, "generate_scenario", lambda *a, **k: (_ for _ in ()).throw(ValueError("/private/secret")))
        if market == "ETH" and stage == "engine":
            async def broken(**kwargs): raise RuntimeError("/private/secret")
            monkeypatch.setattr(self.engine, "run", broken)
        if market == "ETH" and stage == "dataset":
            engine_run = self.engine.run
            async def wrong_dataset(**inputs):
                value = await engine_run(**inputs)
                value.dataset_fingerprint = "0" * 64
                return value
            monkeypatch.setattr(self.engine, "run", wrong_dataset)
        value = await original(self, **kwargs)
        if market == "ETH" and stage == "accounting":
            value.result.vault = value.result.vault.model_copy(update={"market": "SOL"})
            # Rebind native receipt to prove semantic accounting validation,
            # beyond merely detecting a stale full-result fingerprint.
            from app.research_replay.comparison import ScenarioProvenanceReceipt
            return value.model_copy(update={"provenance": ScenarioProvenanceReceipt.bind(
                result=value.result, captured=value.provenance.captured,
                scenario=value.provenance.requested_scenario, frames=value.provenance.requested_frames)})
        if market == "ETH" and stage == "result_hash":
            return value.model_copy(update={"provenance": value.provenance.model_copy(update={"result_fingerprint": "0" * 64})})
        return value
    monkeypatch.setattr(SimulationService, "run_scenario", observe)
    if stage == "bundle":
        monkeypatch.setattr(aggregation, "assemble_bundle", lambda *a: (_ for _ in ()).throw(ValueError("/private/secret")))
    if stage == "serialization":
        monkeypatch.setattr(aggregation, "bounded_json", lambda *a: (_ for _ in ()).throw(TypeError("/private/secret")))
    before = authority(rt)
    response = client.post(URL, json=request_for().model_dump(mode="json"))
    assert response.status_code == (500 if stage in {"engine", "serialization"} else 422), response.text
    assert markets == (["BTC", "ETH", "SOL"] if stage in {"bundle", "serialization"} else ["BTC", "ETH"])
    assert "/private/secret" not in response.text and response.headers["cache-control"] == "no-store"
    assert not app.state.simulation_executor._busy
    assert authority(rt) == before


def test_competing_native_http_request_returns_busy_while_portfolio_runs(research_client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    client, _ = research_client
    started, release = Event(), Event()
    original = SimulationService.run_scenario
    async def held(self, **kwargs):
        if kwargs["strategy"].market == "ETH":
            started.set()
            assert release.wait(10)
        return await original(self, **kwargs)
    monkeypatch.setattr(SimulationService, "run_scenario", held)
    with ThreadPoolExecutor(max_workers=1) as caller:
        first = caller.submit(client.post, URL, json=request_for().model_dump(mode="json"))
        try:
            assert started.wait(5)
            competing = client.post("/api/v1/simulation/run", json={"frames": 2})
            assert competing.status_code == 429
            duplicate = client.post(URL, json=request_for().model_dump(mode="json"))
            assert duplicate.status_code == 429 and duplicate.headers["cache-control"] == "no-store"
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200


def test_response_size_checks_exact_serialized_bytes(research_client, monkeypatch):
    from app.portfolio_research import aggregation
    client, _ = research_client
    request = request_for()
    result = asyncio.run(SimulationService().analyze_portfolio_research(request=request))
    size = len(result.model_dump_json().encode("utf-8"))
    monkeypatch.setattr(aggregation, "MAX_RESPONSE_BYTES", size)
    accepted = client.post(URL, json=request.model_dump(mode="json"))
    assert accepted.status_code == 200 and len(accepted.content) == size
    monkeypatch.setattr(aggregation, "MAX_RESPONSE_BYTES", size - 1)
    rejected = client.post(URL, json=request.model_dump(mode="json"))
    assert rejected.status_code == 413 and rejected.headers["cache-control"] == "no-store"
    assert not app.state.simulation_executor._busy


def test_production_uvicorn_actual_loopback_http(tmp_path):
    with local_server(tmp_path) as client:
        request = request_for()
        response = client.post(URL, json=request.model_dump(mode="json"))
        assert response.status_code == 200, response.text
        result = PortfolioAnalysisResult.model_validate_json(response.content)
        assert result.execution.selected_markets == ("BTC", "ETH", "SOL")
        assert result.execution.unallocated_reserve_quote == 5000
        assert response.headers["cache-control"] == "no-store"
        assert client.post(URL, json={}).status_code == 422
        assert client.post(URL, content=b" " * 65537).status_code == 413
        assert client.post(URL, json=request.model_dump(mode="json"), headers={"Host": "attacker.invalid"}).status_code == 403
        assert client.post(URL, json=request.model_dump(mode="json"), headers={"Origin": "https://attacker.invalid"}).status_code == 403


def test_production_uvicorn_redis_outage_returns_503(tmp_path):
    with local_server(tmp_path, redis=True, coordination=True) as client:
        response = client.post(URL, json=request_for().model_dump(mode="json"))
        assert response.status_code == 503 and response.headers["cache-control"] == "no-store"
