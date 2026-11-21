"""Exercise the existing provider limits and lifecycle with bounded fixtures."""
import asyncio
from collections import Counter
import json
import resource
from threading import Event, Lock, enumerate as threads
from time import perf_counter

import pytest
from httpx import ASGITransport, AsyncClient
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, Timeout
from urllib3.exceptions import ProtocolError

from app.market_data import market_summaries
from app.market_data.market_summaries import CACHE_CAPACITY, MAX_ACTIVE, MAX_REQUESTS_PER_MINUTE, REQUEST_SECONDS
from app.market_data.market_universe_discovery import (
    MAX_NAMESPACES, DiscoveryFailure, MarketUniverseDiscovery, OfficialMetadataClient,
)
from test_phase181_market_discovery import clock, meta, row, wire, WireResponse  # noqa: F401
from test_phase186h_market_summaries import Route, URL, route  # noqa: F401


async def refresh_fixture(route):
    route.clock.advance(61)
    route.catalog = await route.discovery.catalog()
    assert route.catalog.availability == "AVAILABLE"


@pytest.mark.parametrize("failure,code", [
    (ConnectionError("local-path diagnostic"), "NETWORK_ERROR"),
    (Timeout("local-path diagnostic"), "TIMEOUT"),
    ((500, b"local-path diagnostic", {}), "UPSTREAM_ERROR"),
    ((503, b"local-path diagnostic", {}), "UPSTREAM_ERROR"),
    ((200, b"[null", {}), "INVALID_DATA"),
    ((200, b"[null]", {"Content-Length": "9"}), "INVALID_DATA"),
])
async def test_provider_wire_failure_is_sanitized_and_recoverable(route, wire, monkeypatch, failure, code):
    requests, responses, sessions = wire
    route.owner._client = OfficialMetadataClient("MAINNET")
    monkeypatch.setattr(market_summaries, "monotonic", lambda: route.clock.seconds)
    recovery = WireResponse(body=json.dumps(route.provider.context("")).encode())
    if isinstance(failure, Exception):
        send = HTTPAdapter.send

        def fail_once(adapter, request, **kwargs):
            if not requests:
                requests.append((request, kwargs))
                raise failure
            return send(adapter, request, **kwargs)

        monkeypatch.setattr(HTTPAdapter, "send", fail_once)
        responses[:] = [recovery]
    else:
        responses[:] = [WireResponse(*failure), recovery]
    failed = await route.client.post(URL, json=route.body("BTC"))
    assert failed.status_code == 200 and "local-path diagnostic" not in failed.text
    item, = failed.json()["results"]
    assert (item["status"], item["error"], item["observed_at"]) == ("ERROR", code, None)
    assert (await route.request("BTC"))["results"] == [item]
    assert len(requests) == len(sessions) == 1
    route.clock.advance(5)
    recovered, = (await route.request("BTC", refresh=True))["results"]
    assert recovered["status"] == "CURRENT"
    assert len(requests) == len(sessions) == 2


async def test_provider_disconnect_during_body_closes_transport(route, wire, monkeypatch):
    requests, responses, sessions = wire
    route.owner._client = OfficialMetadataClient("MAINNET")
    monkeypatch.setattr(market_summaries, "monotonic", lambda: route.clock.seconds)
    response = responses[0]

    def interrupted(_size):
        raise ProtocolError("local-path diagnostic")

    response.raw.read1 = interrupted
    failed = await route.client.post(URL, json=route.body("BTC"))
    assert failed.status_code == 200 and "local-path diagnostic" not in failed.text
    item, = failed.json()["results"]
    assert item["error"] == "NETWORK_ERROR" and item["mark_price"] is None
    assert len(sessions) == len(requests) == 1 and response.raw.closed


async def test_real_rolling_budget_cache_capacity_and_recovery(route, record_property):
    dexes = tuple(f"d{i:02d}" for i in range(26))
    route.provider.inventory.extend({"name": dex} for dex in dexes)
    route.provider.markets.update({dex: meta(row(f"{dex}:BTC")) for dex in dexes})
    await refresh_fixture(route)

    for start in range(0, 24, 3):
        result = await route.request(*(f"{dex}:BTC" for dex in dexes[start:start + 3]))
        assert {row["status"] for row in result["results"]} == {"CURRENT"}
    assert sum(route.acquisitions.values()) == MAX_REQUESTS_PER_MINUTE == 24
    assert len(route.owner._cache) == CACHE_CAPACITY == 24

    blocked, = (await route.request("d24:BTC"))["results"]
    assert blocked["error"] == "RATE_LIMITED"
    route.clock.advance(59.9)
    blocked, = (await route.request("d24:BTC", refresh=True))["results"]
    assert blocked["error"] == "RATE_LIMITED"
    assert sum(route.acquisitions.values()) == 24

    route.clock.advance(0.2)
    route.catalog = await route.discovery.catalog()
    acquired = await route.request("d24:BTC", "d25:BTC")
    assert {row["status"] for row in acquired["results"]} == {"CURRENT"}
    assert sum(route.acquisitions.values()) == 26 and len(route.owner._cache) == 24
    assert all(dex not in {key[1] for key in route.owner._cache} for dex in ("d00", "d01"))
    record_property("rolling_budget", "24 starts, 2 blocked calls, 2 recovered starts, 24 retained entries")


async def test_same_namespace_single_flight_and_three_active_calls(route):
    active = peak = 0
    lock = Lock()
    three_active, release = Event(), Event()

    def held():
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 3:
                three_active.set()
        try:
            assert release.wait(10)
        finally:
            with lock:
                active -= 1

    # Eight independent callers wait on the Core acquisition. Two HIP-3 DEXs
    # can acquire simultaneously, and the fourth distinct namespace is bounded.
    route.provider.wait = held
    clients = [asyncio.create_task(route.request("BTC", "Z")) for _ in range(8)]
    clients.extend(asyncio.create_task(route.request(coin)) for coin in ("xyz:BTC", "abc:BTC"))
    try:
        assert await asyncio.to_thread(three_active.wait, 5)
        blocked, = (await route.request("def:BTC"))["results"]
        assert blocked["error"] == "CAPACITY" and route.acquisitions["def"] == 0
        assert peak == len(route.owner._tasks) == MAX_ACTIVE == 3
    finally:
        release.set()
        responses = await asyncio.gather(*clients)
    assert all(row["status"] == "CURRENT" for data in responses for row in data["results"])
    assert route.acquisitions == {"": 1, "xyz": 1, "abc": 1}
    assert active == 0 and not route.owner._tasks


async def test_provider_wait_ceiling_leaves_single_flight_to_drain(route, record_property):
    started, release = Event(), Event()

    def delayed():
        started.set()
        assert release.wait(12)

    route.provider.wait = delayed
    start = perf_counter()
    request = asyncio.create_task(route.request("BTC"))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        row, = (await request)["results"]
        elapsed = perf_counter() - start
        assert row["error"] == "TIMEOUT" and row["mark_price"] is None
        assert REQUEST_SECONDS <= elapsed < REQUEST_SECONDS + 3
        assert len(route.owner._tasks) == 1 and route.acquisitions == {"": 1}
        record_property("request_timeout_seconds", round(elapsed, 3))
    finally:
        release.set()
        await route.owner.close()
    assert not route.owner._tasks and not route.owner._cache


async def test_http_429_keeps_other_success_in_same_batch_and_recovers(route):
    route.provider.contexts["xyz"] = DiscoveryFailure("RATE_LIMITED")
    results = (await route.request("xyz:BTC", "BTC"))["results"]
    assert results[0]["error"] == "RATE_LIMITED" and results[1]["status"] == "CURRENT"
    for _ in range(4):
        route.clock.advance(5)
        out, = (await route.request("abc:BTC", refresh=True))["results"]
        assert out["error"] == "RATE_LIMITED"
    assert route.acquisitions == {"": 1, "xyz": 1}

    route.clock.advance(10)
    route.provider.contexts.pop("xyz")
    out = await route.request("xyz:BTC", "abc:BTC", refresh=True)
    assert {row["status"] for row in out["results"]} == {"CURRENT"}
    assert route.acquisitions == {"": 1, "xyz": 2, "abc": 1}
    await route.owner.close()
    assert not route.owner._cache and not route.owner._tasks


async def test_testnet_capacity_rejected_before_fetching_namespace_metadata(route):
    calls = []

    def inventory(method, dex, deadline):
        calls.append((method, dex))
        assert method == "perpDexs"
        return [None] + [{"name": f"d{i}"} for i in range(MAX_NAMESPACES)]

    discovery = MarketUniverseDiscovery(enabled=True, network="TESTNET", client=inventory)
    app = route.app
    app.state.market_universe_discovery = discovery
    try:
        catalog = await route.client.get("/market-universe")
        assert catalog.status_code == 503
        assert catalog.json()["inventory"]["error"] == "CATALOG_CAPACITY"
        assert catalog.json()["catalog"] is catalog.json()["catalog_fingerprint"] is None
        assert not catalog.json()["eligibility"] and not catalog.json()["namespaces"]
        assert calls == [("perpDexs", "")]
        body = route.body("BTC", network="TESTNET")
        assert (await route.client.post(URL, json=body)).status_code == 409
        assert calls == [("perpDexs", "")] and not route.acquisitions
    finally:
        await discovery.close()


async def test_disconnected_http_client_releases_waiter_and_shared_call_survives(route):
    entered, release = Event(), Event()
    disconnected = asyncio.Event()

    def delayed():
        entered.set()
        assert release.wait(10)

    async def asgi(scope, receive, send):
        body_finished = False

        async def receive_with_disconnect():
            nonlocal body_finished
            if body_finished:
                await disconnected.wait()
                return {"type": "http.disconnect"}
            event = await receive()
            body_finished = not event.get("more_body", False)
            return event

        await route.app(scope, receive_with_disconnect, send)

    route.provider.wait = delayed
    async with AsyncClient(transport=ASGITransport(app=asgi), base_url="http://test") as http:
        cancelled = asyncio.create_task(http.post(URL, json=route.body("BTC")))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            survivor = asyncio.create_task(route.request("Z"))
            disconnected.set()
            response = await asyncio.wait_for(cancelled, 3)
            assert response.status_code == 499
            assert len(route.owner._tasks) == 1 and not survivor.done()
        finally:
            release.set()
        assert (await survivor)["results"][0]["status"] == "CURRENT"
    assert route.acquisitions == {"": 1} and not route.owner._tasks


async def test_bounded_refresh_soak_and_restart(route, record_property):
    provider = route.provider
    symbols = tuple(f"xyz:T{i:02d}" for i in range(24))
    provider.markets["xyz"] = meta(*(row(coin) for coin in symbols))
    await refresh_fixture(route)
    start = perf_counter()
    baseline_threads = len(threads())
    response_bytes = []
    errors = Counter()
    for cycle in range(80):
        route.clock.advance(5)
        route.catalog = await route.discovery.catalog()
        page = symbols[12:] if cycle % 2 else symbols[:12]
        before = sum(route.acquisitions.values())
        response = await route.client.post(URL, json=route.body(*page, refresh=cycle % 4 == 0))
        response_bytes.append(len(response.content))
        errors.update(row["error"] for row in response.json()["results"] if row["error"])
        assert response.status_code == 200 and len(response.json()["results"]) == 12
        assert len(route.owner._cache) <= CACHE_CAPACITY and not route.owner._tasks
        assert sum(route.acquisitions.values()) - before <= 1
    misses = sum(route.acquisitions.values())
    retained = len(route.owner._cache)
    assert 1 < misses < 80 and not errors and set(route.acquisitions) == {"xyz"}
    assert max(response_bytes) < 32 * 1024
    started_threads = len(threads())

    await route.close()
    assert not route.owner._tasks and not route.owner._cache
    assert all(not thread.is_alive() for thread in route.discovery._pool._threads)

    restarted = await Route().start(route.clock, "MAINNET")
    try:
        row_result, = (await restarted.request("BTC"))["results"]
        assert row_result["status"] == "CURRENT" and restarted.acquisitions == {"": 1}
    finally:
        await restarted.close()
    record_property("provider_soak", json.dumps({
        "virtual_seconds": 400, "elapsed_seconds": round(perf_counter() - start, 3), "requests": 80,
        "cache_hits": 80 - misses, "cache_misses": misses, "peak_response_bytes": max(response_bytes),
        "errors": dict(errors), "retained_before_close": retained, "retained_after_close": len(route.owner._cache),
        "threads_before": baseline_threads, "threads_at_end": started_threads, "threads_after_close": len(threads()),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }, sort_keys=True))
