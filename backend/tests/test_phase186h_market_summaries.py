"""Exercise the public summary route, transport, binding and lifecycle."""
import asyncio
from collections import Counter
from copy import deepcopy
from datetime import timedelta
import json
from threading import Event
from time import monotonic

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from hyperliquid.utils.constants import MAINNET_API_URL, TESTNET_API_URL

from app.api.market_universe import router
from app.agents.supervisor import AgentSupervisor
from app.market_data import market_summaries as summaries
from app.market_data.market_universe_discovery import (
    MAX_PROVIDER_BYTES, DiscoveryFailure, MarketUniverseDiscovery, OfficialMetadataClient,
)
from app.risk.firewall import RiskFirewall
from app.simulation import engine
from test_phase181_market_discovery import Provider, WireResponse, clock, meta, row, wire  # noqa: F401
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401

URL = "/market-universe/market-summaries"


class SummaryProvider(Provider):
    def __init__(self):
        super().__init__()
        self.markets[""] = meta(row("Z"), row("BTC", 5), *(row(f"T{i:02d}") for i in range(10)),
                                row("OLD", isDelisted=True))
        self.markets["xyz"]["collateralToken"] = 1
        self.inventory.extend({"name": dex} for dex in ("def", "ghi", "jkl"))
        self.markets.update({dex: meta(row(f"{dex}:BTC")) for dex in ("def", "ghi", "jkl")})
        self.contexts = {}
        self.wait = None

    def __call__(self, method, dex, deadline):
        if method == "spotMeta":
            return {"tokens": []}
        if method != "metaAndAssetCtxs":
            return super().__call__(method, dex, deadline)
        self.calls.append((method, dex))
        if self.wait:
            self.wait()
        if dex in self.contexts:
            result = self.contexts[dex]
            if isinstance(result, Exception):
                raise result
            return result
        return self.context(dex)

    def context(self, dex):
        metadata = deepcopy(self.markets[dex])
        rows = [{
            "markPx": str(101 + index + (100 if dex == "xyz" else 0)),
            "oraclePx": "100.2", "funding": "-0.0000125", "prevDayPx": "100",
            "dayNtlVlm": "2012345.75", "openInterest": "31.17",
        } for index, _ in enumerate(metadata["universe"])]
        return [metadata, rows]


class Route:
    async def start(self, clock, network):
        self.clock = clock
        self.provider = SummaryProvider()
        self.discovery = MarketUniverseDiscovery(enabled=True, network=network, clock=lambda: clock.now,
                                                 client=self.provider)
        self.owner = summaries.MarketSummaryObservations(
            network, client=self.provider, clock=lambda: clock.now, timer=lambda: clock.seconds)
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.market_universe_discovery = self.discovery
        self.app.state.market_summary_observations = self.owner
        self.client = AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test")
        self.catalog = await self.discovery.catalog()
        assert self.catalog.availability == "AVAILABLE", (self.catalog, self.provider.calls)
        return self

    def body(self, *coins, **extra):
        by_coin = {record.source_coin: record.identity.stable_key for record in self.catalog.catalog.records}
        return {"market_keys": [by_coin[coin] for coin in coins], "network": self.catalog.network,
                "catalog_fingerprint": self.catalog.catalog_fingerprint, **extra}

    async def request(self, *coins, **extra):
        response = await self.client.post(URL, json=self.body(*coins, **extra))
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"
        return response.json()

    @property
    def acquisitions(self):
        return Counter(dex for method, dex in self.provider.calls if method == "metaAndAssetCtxs")

    async def close(self):
        await self.client.aclose()
        await self.owner.close()
        await self.discovery.close()


@pytest.fixture
async def route(clock):
    instance = await Route().start(clock, "MAINNET")
    try:
        yield instance
    finally:
        await instance.close()


async def test_twelve_cards_share_authority_free_context_and_page_cache(route, offline_boundaries, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Summary reached a trading, quoting or operational agent path")

    monkeypatch.setattr(AgentSupervisor, "evaluate", forbidden)
    monkeypatch.setattr(RiskFirewall, "evaluate", forbidden)
    monkeypatch.setattr(engine, "authorize", forbidden)
    page = await route.request("Z", "BTC", *(f"T{i:02d}" for i in range(10)))
    assert page["read_only"] and not page["execution_eligible"] and page["authority"] == "NONE"
    mark = page["results"][1]
    assert mark["status"] == "CURRENT"
    assert mark["universe_index"] == 1 and mark["identity"]["instrument_name"] == "BTC"
    assert mark["mark_price"] == "102" and mark["oracle_price"] == "100.2"
    assert mark["day_notional_volume"] == "2012345.75" and mark["open_interest_base"] == "31.17"
    assert mark["funding_interval_seconds"] == 3600 and mark["funding_rate"] == "-0.0000125"
    assert mark["mark_change_vs_previous_day_percent"] == "2.00000000"
    assert mark["provider_event_at"] is None and mark["observation_clock"] == "LOCAL_RECEIPT"
    assert mark["observed_at"] == route.clock.now.isoformat().replace("+00:00", "Z")
    assert mark["observation_fingerprint"] != mark["metadata_fingerprint"]
    assert not mark["execution_eligible"] and mark["authority"] == "NONE"
    other = await route.request("BTC", "OLD")
    assert other["results"][0] == mark
    assert other["results"][1]["status"] == "UNSUPPORTED"
    assert route.acquisitions == {"": 1}
    await route.request("BTC", refresh=True)
    assert route.acquisitions == {"": 1}
    route.clock.advance(5)
    refreshed = await route.request("BTC", refresh=True)
    assert route.acquisitions == {"": 2}
    assert refreshed["results"][0]["observation_fingerprint"] != mark["observation_fingerprint"]


async def test_mixed_namespaces_same_symbol_and_capacity(route):
    result = await route.request("BTC", "xyz:BTC", "abc:BTC", "def:BTC", "ghi:BTC", "jkl:BTC")
    rows = result["results"]
    assert sum(item["status"] == "CURRENT" for item in rows) == summaries.MAX_ACTIVE
    assert {item["error"] for item in rows if item["status"] == "UNAVAILABLE"} == {"CAPACITY"}
    assert sum(route.acquisitions.values()) == summaries.MAX_ACTIVE
    accepted = await route.request("BTC", "xyz:BTC")
    core, hip3 = accepted["results"]
    assert core["identity"]["dex"] == "" and hip3["identity"]["dex"] == "xyz"
    assert core["mark_price"] == "102" and hip3["mark_price"] == "201"
    assert core["observation_fingerprint"] != hip3["observation_fingerprint"]
    route.clock.advance(summaries.CACHE_SECONDS)
    followup = await route.request("BTC", "xyz:BTC", "abc:BTC", "def:BTC", "ghi:BTC", "jkl:BTC")
    assert {item["status"] for item in followup["results"]} == {"CURRENT"}
    assert route.acquisitions["ghi"] == route.acquisitions["jkl"] == 1


async def test_generation_and_network_replacement(route, clock):
    first = await route.request("BTC")
    old = route.body("BTC")
    clock.advance(61)
    route.catalog = await route.discovery.catalog()
    assert (await route.client.post(URL, json=old)).status_code == 409
    current = await route.request("BTC")
    assert first["catalog_fingerprint"] != current["catalog_fingerprint"]
    assert route.acquisitions == {"": 2}
    testnet = await Route().start(clock, "TESTNET")
    try:
        assert (await testnet.client.post(URL, json=route.body("BTC"))).status_code == 409
        foreign = {**testnet.body("BTC"), "market_keys": old["market_keys"]}
        assert (await testnet.client.post(URL, json=foreign)).status_code == 404
        answer = await testnet.request("BTC", "xyz:BTC")
        assert {r["identity"]["network"] for r in answer["results"]} == {"TESTNET"}
        assert testnet.acquisitions == {"": 1, "xyz": 1}
        with pytest.raises(DiscoveryFailure, match="NETWORK_MISMATCH"):
            await route.owner.summarize(
                summaries.MarketSummaryRequest(**testnet.body("BTC")), testnet.catalog, testnet.discovery,
                testnet.discovery.paper_generation(testnet.catalog.catalog_fingerprint),
            )
        assert route.acquisitions == {"": 2}
    finally:
        await testnet.close()


@pytest.mark.parametrize("mutation,error", [
    ("reorder", "CATALOG_CHANGED"),
    ("delist", "CATALOG_CHANGED"),
    ("remove", "CATALOG_CHANGED"),
    ("collateral", "QUOTE_UNIT_MISMATCH"),
    ("truncated", "INVALID_DATA"),
    ("namespace", "NAMESPACE_CONFLICT"),
    ("network", "NETWORK_MISMATCH"),
    ("context_quote", "QUOTE_UNIT_MISMATCH"),
])
async def test_incompatible_namespace_context_is_rejected(route, mutation, error):
    raw = route.provider.context("xyz")
    metadata, rows = raw
    if mutation == "reorder":
        metadata["universe"].reverse()
    elif mutation == "delist":
        metadata["universe"][0]["isDelisted"] = True
    elif mutation == "remove":
        metadata["universe"].pop()
    elif mutation == "collateral":
        metadata["collateralToken"] = 2
    elif mutation == "truncated":
        rows.pop()
    elif mutation == "namespace":
        rows[0]["coin"] = "abc:BTC"
    elif mutation == "network":
        rows[0]["network"] = "TESTNET"
    else:
        rows[0].update(markQuoteUnit="A", prevDayQuoteUnit="B")
    route.provider.contexts["xyz"] = raw
    answer = await route.request("xyz:BTC", "BTC")
    assert answer["results"][0]["error"] == error
    assert answer["results"][0]["mark_price"] is None
    assert answer["results"][1]["status"] == "CURRENT"


@pytest.mark.parametrize("changes,missing", [
    ({"markPx": None}, ("mark_price", "mark_change_vs_previous_day_percent")),
    ({"oraclePx": None}, ("oracle_price",)),
    ({"funding": None}, ("funding_rate",)),
    ({"dayNtlVlm": None}, ("day_notional_volume",)),
    ({"prevDayPx": "0"}, ("previous_day_price", "mark_change_vs_previous_day_percent")),
    ({"prevDayPx": "1e-60"}, ("mark_change_vs_previous_day_percent",)),
    ({"dayNtlVlm": "-1", "openInterest": "-1"}, ("day_notional_volume", "open_interest_base")),
    ({"markPx": "NaN", "oraclePx": "Infinity"}, ("mark_price", "oracle_price")),
    ({"markPx": 101.1, "funding": "0.005001"}, ("mark_price", "funding_rate")),
    ({"markPx": "-1", "oraclePx": "0"}, ("mark_price", "oracle_price")),
    ({"markPx": "abc", "oraclePx": " 8"}, ("mark_price", "oracle_price")),
])
async def test_invalid_fields_are_suppressed_independently(route, changes, missing):
    raw = route.provider.context("")
    raw[1][1].update(changes)
    route.provider.contexts[""] = raw
    result = (await route.request("BTC"))["results"][0]
    assert result["status"] == "CURRENT"
    assert all(result[field] is None for field in missing)
    assert result["limitations"]


async def test_partial_null_row_and_stale_local_receipt(route):
    raw = route.provider.context("")
    raw[1][1] = None
    route.provider.contexts[""] = raw
    first = (await route.request("BTC", "Z"))["results"]
    assert first[0]["status"] == "UNAVAILABLE" and first[1]["status"] == "CURRENT"
    # Advance the UTC clock without advancing the monotonic cache clock.
    route.clock.now += timedelta(seconds=31)
    stale = (await route.request("Z"))["results"][0]
    assert stale["status"] == "STALE" and stale["mark_price"] is None
    assert route.acquisitions == {"": 1}


async def test_rate_limit_backoff_and_timeout(route):
    route.provider.contexts[""] = DiscoveryFailure("RATE_LIMITED")
    first = (await route.request("BTC"))["results"][0]
    assert first["error"] == "RATE_LIMITED"
    route.clock.advance(5)
    limited = (await route.request("xyz:BTC"))["results"][0]
    assert limited["error"] == "RATE_LIMITED"
    assert route.acquisitions == {"": 1}
    route.clock.advance(summaries.RATE_LIMIT_BACKOFF)
    route.provider.contexts["xyz"] = TimeoutError()
    timed_out = (await route.request("xyz:BTC"))["results"][0]
    assert timed_out["error"] == "TIMEOUT"
    assert route.acquisitions == {"": 1, "xyz": 1}


async def test_global_budget_and_cache_entry_cap(route, monkeypatch):
    monkeypatch.setattr(summaries, "MAX_REQUESTS_PER_MINUTE", 2)
    monkeypatch.setattr(summaries, "CACHE_CAPACITY", 1)
    await route.request("BTC")
    await route.request("xyz:BTC")
    assert len(route.owner._cache) == 1
    assert (await route.request("abc:BTC"))["results"][0]["error"] == "RATE_LIMITED"
    assert route.acquisitions == {"": 1, "xyz": 1}


async def test_cancellation_and_shutdown_drain_shared_call(route):
    started, release = Event(), Event()

    def wait():
        started.set()
        assert release.wait(5)

    route.provider.wait = wait
    cancelled = asyncio.create_task(route.request("BTC"))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        survivor = asyncio.create_task(route.request("Z"))
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert len(route.owner._tasks) == 1
    finally:
        release.set()
    assert (await survivor)["results"][0]["status"] == "CURRENT"
    assert route.acquisitions == {"": 1}

    started.clear()
    release.clear()
    active = asyncio.create_task(route.request("xyz:BTC"))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        shutdown = asyncio.create_task(route.owner.close())
        await asyncio.sleep(0)
        assert not shutdown.done()
    finally:
        release.set()
    row, = (await active)["results"]
    assert (row["status"], row["error"], row["mark_price"]) == ("ERROR", "CLOSED", None)
    assert row["observation_fingerprint"] is None
    await shutdown
    assert not route.owner._tasks and not route.owner._cache


async def test_generation_retired_midflight(route):
    started, release = Event(), Event()

    def wait():
        started.set()
        assert release.wait(5)

    route.provider.wait = wait
    active = asyncio.create_task(route.client.post(URL, json=route.body("BTC")))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        route.clock.advance(61)
        new_catalog = await route.discovery.catalog()
        assert new_catalog.catalog_fingerprint != route.catalog.catalog_fingerprint
    finally:
        release.set()
    assert (await active).status_code == 409


async def test_bounded_selector_and_json_response(route):
    assert (await route.client.post(URL, json=route.body(*(["BTC"] * 14)))).status_code == 422
    assert (await route.client.post(URL, json=route.body("BTC", "BTC"))).status_code == 422
    assert (await route.client.post(URL, json=route.body("BTC", refresh="true"))).status_code == 422
    assert not route.acquisitions
    response = await route.client.post(URL, json=route.body("Z", "BTC", "OLD", *(f"T{i:02d}" for i in range(10))))
    assert response.status_code == 200 and len(response.content) < 32768


@pytest.mark.parametrize("network,dex,host", [
    ("MAINNET", "", MAINNET_API_URL), ("TESTNET", "xyz", TESTNET_API_URL),
])
def test_sdk_scope_size_and_session_cleanup(wire, network, dex, host):
    requests, responses, sessions = wire
    oversized = WireResponse(body=b"x" * (MAX_PROVIDER_BYTES + 1))
    responses.append(oversized)
    client = OfficialMetadataClient(network)
    assert client("metaAndAssetCtxs", dex, monotonic() + 6) == [None]
    with pytest.raises(DiscoveryFailure, match="RESPONSE_TOO_LARGE"):
        client("metaAndAssetCtxs", dex, monotonic() + 6)
    assert [json.loads(req.body) for req, _ in requests] == [{"type": "metaAndAssetCtxs", "dex": dex}] * 2
    assert all(req.url == f"{host}/info" for req, _ in requests)
    assert len(sessions) == 2 and oversized.raw.closed
