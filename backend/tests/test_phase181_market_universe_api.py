"""Exercise the real GET route and lifespan without operational side effects."""
import asyncio
from collections import Counter
from threading import Event
from typing import get_args

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.config import Settings
from app.market_data.market_universe_contracts import MAX_CATALOG_RECORDS
from app.market_data.market_universe_discovery import (
    DiscoveryFailure, MarketUniverseDiscovery, MarketUniverseResponse,
)
from app.simulation.market_profiles import ResearchPerpMarketId
from test_phase14_research_vault import authority, research_client
from test_phase181_market_discovery import NOW, Provider, meta, row

URL = "/api/v1/market-universe"


@pytest.fixture
async def route(monkeypatch):
    provider = Provider()
    service = MarketUniverseDiscovery(enabled=True, network="TESTNET", client=provider, clock=lambda: NOW)
    monkeypatch.setattr(main.app.state, "market_universe_discovery", service, raising=False)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                    base_url="http://127.0.0.1") as client:
            yield client, provider
    finally:
        await service.close()


async def test_schema_fingerprints_and_fixed_network(route):
    client, provider = route
    response = await client.get(URL, params={"network": "MAINNET", "url": "https://untrusted.invalid", "dex": "fake"})
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    body = MarketUniverseResponse.model_validate_json(response.content)
    assert body.network == "TESTNET" and body.availability == "AVAILABLE"
    assert body.catalog_fingerprint == body.catalog.fingerprint()
    assert body.schema_version == "phase181-v1" and body.contract_version == "phase180b-v2"
    assert body.authority == "NONE" and body.read_only and not body.paper_research_eligible and not body.execution_eligible
    assert body.evaluated_at == NOW
    assert body.limitations == ("METADATA_ONLY", "NO_PAPER_RESEARCH", "NO_EXECUTION")
    assert all(x.identity.network == "TESTNET" for x in body.catalog.records)
    assert set(provider.calls) == {("perpDexs", ""), ("meta", ""), ("meta", "abc"), ("meta", "xyz")}
    assert "untrusted.invalid" not in response.text and "fake" not in response.text
    assert body == MarketUniverseResponse.model_validate_json((await client.get(URL)).content)
    endpoint = (await client.get("/openapi.json")).json()["paths"][URL]
    assert set(endpoint) == {"get"}
    assert set(endpoint["get"]["responses"]) == {"200", "429", "503", "504"}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD"])
async def test_unsupported_http_methods_never_collect(route, method):
    client, provider = route
    assert (await client.request(method, URL)).status_code == 405
    assert not provider.calls


@pytest.mark.parametrize(("failure", "expected"), [
    ("RATE_LIMITED", 429), ("TIMEOUT", 504), ("FORBIDDEN", 503), ("NETWORK_MISMATCH", 503),
    ("CATALOG_CAPACITY", 503), ("SDK_UNAVAILABLE", 503), ("CLEANUP_ERROR", 503),
])
async def test_unavailable_typed_statuses_and_headers(route, failure, expected):
    client, provider = route
    provider.inventory = DiscoveryFailure(failure)
    response = await client.get(URL)
    assert response.status_code == expected and response.headers["Cache-Control"] == "no-store"
    assert response.headers.get("Retry-After") == ("30" if expected == 429 else None)
    result = MarketUniverseResponse.model_validate_json(response.content)
    assert result.availability == "UNAVAILABLE" and result.inventory.error == failure
    assert result.catalog is result.catalog_fingerprint is None and not result.eligibility


async def test_partial_failure_safe_and_bounded(route):
    client, provider = route
    provider.markets["abc"] = RuntimeError("PRIVATE_TRACE " + "x" * 5000)
    provider.markets["xyz"] = meta(row("untrusted_dex-token:sol"))
    response = await client.get(URL)
    result = MarketUniverseResponse.model_validate_json(response.content)
    assert response.status_code == 200 and result.availability == "PARTIAL"
    assert [ns.error for ns in result.namespaces] == [None, "INVALID_DATA", "NAMESPACE_CONFLICT"]
    assert result.catalog is result.catalog_fingerprint is None and len(response.content) < 1500
    assert "PRIVATE_TRACE" not in response.text and "untrusted_dex-token" not in response.text


async def test_maximum_catalog_fits_browser_response_budget(route):
    client, provider = route
    dex = "d" * 32
    provider.inventory = [None, {"name": dex}]
    provider.markets[""] = meta(row("X" * 64))
    provider.markets[dex] = meta(*(row(f"{dex}:" + "x" * 60 + f"{i:04d}", 6)
                                   for i in range(MAX_CATALOG_RECORDS - 1)))
    response = await client.get(URL)
    assert response.status_code == 200 and len(response.content) < 5_000_000
    data = MarketUniverseResponse.model_validate_json(response.content)
    assert len(data.catalog.records) == len(data.eligibility) == MAX_CATALOG_RECORDS


async def test_http_concurrency_shares_one_refresh(monkeypatch):
    entered, release = Event(), Event()
    provider = Provider()

    def blocked(method, dex, deadline):
        if method == "perpDexs":
            entered.set()
            assert release.wait(4)
        return provider(method, dex, deadline)

    service = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=blocked)
    monkeypatch.setattr(main.app.state, "market_universe_discovery", service, raising=False)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                    base_url="http://127.0.0.1") as client:
            requests = asyncio.gather(*(client.get(URL) for _ in range(20)))
            assert await asyncio.to_thread(entered.wait, 2) and not requests.done()
            release.set()
            responses = await requests
        assert all(response.status_code == 200 for response in responses)
        assert len({response.json()["catalog_fingerprint"] for response in responses}) == 1
        assert Counter(provider.calls) == {("perpDexs", ""): 1, ("meta", ""): 1, ("meta", "abc"): 1, ("meta", "xyz"): 1}
    finally:
        release.set()
        await service.close()


@pytest.mark.parametrize("enabled", [False, True])
def test_application_lifespan_owns_discovery(monkeypatch, enabled):
    settings = Settings(market_universe_enabled=enabled, market_universe_network="TESTNET")
    provider = Provider()
    instances = []

    def create(*, budget, **options):
        assert options == {"enabled": enabled, "network": "TESTNET"}
        assert budget is main.app.state.hyperliquid_budget
        instance = MarketUniverseDiscovery(**options, client=provider, budget=budget)
        instances.append(instance)
        return instance

    async def no_runtime_work(*args):
        pass

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "MarketUniverseDiscovery", create)
    monkeypatch.setattr(main.HyperAmmRuntime, "start_services", no_runtime_work)
    monkeypatch.setattr(main.HyperAmmRuntime, "stop_services", no_runtime_work)
    with TestClient(main.app, base_url="http://127.0.0.1") as client:
        assert len(instances) == 1 and not provider.calls
        result = client.get(URL)
        assert result.status_code == (200 if enabled else 503)
        assert result.headers["Cache-Control"] == "no-store"
        assert result.json()["availability"] == ("AVAILABLE" if enabled else "DISABLED")
        assert len(provider.calls) == (4 if enabled else 0)
    assert asyncio.run(instances[0].catalog()).error == "CLOSED"


def test_catalog_authority_cannot_change_native_state_or_market_admission(research_client, monkeypatch):
    client, runtime = research_client
    service = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=Provider())
    monkeypatch.setattr(main.app.state, "market_universe_discovery", service, raising=False)
    try:
        before = authority(runtime)
        result = MarketUniverseResponse.model_validate_json(client.get(URL).content)
        assert any(x.identity.instrument_name == "DOGE" for x in result.catalog.records)
        assert any(x.identity.dex == "xyz" for x in result.catalog.records)
        assert get_args(ResearchPerpMarketId) == ("BTC", "ETH", "SOL")
        assert authority(runtime) == before
        assert result.authority == "NONE" and all(d.authority == "NONE" for d in result.eligibility)
        for field in ("execution_eligible", "paper_research_eligible"):
            with pytest.raises(ValidationError):
                MarketUniverseResponse.model_validate(result.model_copy(update={field: True}))
    finally:
        asyncio.run(service.close())
