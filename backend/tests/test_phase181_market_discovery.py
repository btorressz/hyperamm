"""Official SDK wire, normalization, and single-owner refresh acceptance."""
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from threading import Event, Lock, enumerate as threads
from time import monotonic

import pytest
from hyperliquid.info import Info
from hyperliquid.utils.constants import MAINNET_API_URL, TESTNET_API_URL
from pydantic import ValidationError
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, Timeout
from requests.sessions import Session

from app.config import Settings
from app.market_data import market_universe_discovery as discovery
from app.market_data.market_universe_contracts import MarketUniverseCatalog, MAX_CATALOG_RECORDS
from app.market_data.market_universe_discovery import (
    DiscoveryFailure, MarketUniverseDiscovery, OfficialMetadataClient, normalize_inventory, normalize_metadata,
)

NOW = datetime(2026, 11, 18, 20, tzinfo=timezone.utc)


def row(name, precision=2, **extra):
    return {"name": name, "szDecimals": precision, **extra}


def meta(*entries):
    return {"universe": list(entries)}


class Clock:
    seconds = 1000.0
    now = NOW

    def advance(self, seconds):
        self.seconds += seconds
        self.now += timedelta(seconds=seconds)


class Provider:
    def __init__(self):
        self.calls = []
        self.inventory = [None, {"name": "xyz"}, {"name": "abc"}]
        self.markets = {
            "": meta(row("SOL"), row("OLD", isDelisted=True), row("BTC", 5), row("ETH", 4), row("DOGE", 0)),
            "abc": meta(row("abc:BTC", 6)),
            "xyz": meta(row("xyz:BTC"), row("xyz:Gold")),
        }

    def __call__(self, method, dex, deadline):
        self.calls.append((method, dex))
        result = self.inventory if method == "perpDexs" else self.markets[dex]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(discovery, "monotonic", lambda: clock.seconds)
    return clock


@pytest.fixture
async def service(clock):
    provider = Provider()
    service = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=provider,
                                      cache_seconds=10, clock=lambda: clock.now)
    try:
        yield service, provider
    finally:
        await service.close()


@pytest.mark.parametrize("network", ["MAINNET", "TESTNET"])
async def test_catalog_ordinals_provenance_and_inventory_order(network):
    provider = Provider()
    service = MarketUniverseDiscovery(enabled=True, network=network, client=provider, clock=lambda: NOW)
    shuffled = Provider()
    shuffled.inventory[1:] = reversed(shuffled.inventory[1:])
    second = MarketUniverseDiscovery(enabled=True, network=network, client=shuffled, clock=lambda: NOW)
    try:
        result, reordered = await asyncio.gather(service.catalog(), second.catalog())
        assert result.availability == "AVAILABLE"
        assert result.catalog == reordered.catalog
        assert result.catalog_fingerprint == reordered.catalog_fingerprint == result.catalog.fingerprint()
        assert [i.dex for i in result.namespaces] == ["", "abc", "xyz"]
        assert result.inventory.observed_at == NOW
        assert result.network == network and result.read_only and result.authority == "NONE"
        keys = [x.identity.stable_key for x in result.catalog.records]
        assert keys == sorted(keys) and len(keys) == len(set(keys)) == 8
        by_coin = {x.source_coin: (x, d) for x, d in zip(result.catalog.records, result.eligibility, strict=True)}
        assert by_coin["BTC"][0].universe_index == 2
        assert by_coin["OLD"][0].universe_index == 1
        assert by_coin["OLD"][1].reason == "NOT_LISTED"
        assert by_coin["DOGE"][1].reason == "DISCOVERABLE"
        assert by_coin["BTC"][0].metadata_source == "OFFICIAL_SDK_CORE_META"
        assert by_coin["abc:BTC"][0].metadata_source == "OFFICIAL_SDK_HIP3_META"
        assert by_coin["abc:BTC"][0].universe_index == by_coin["xyz:BTC"][0].universe_index == 0
        for record, decision in by_coin.values():
            assert record.identity.network == network and record.observed_at == NOW
            assert decision.validate_against(record, evaluated_at=NOW, max_age_seconds=result.max_age_seconds)
            assert not decision.paper_research_eligible and not decision.execution_eligible
            assert not hasattr(record, "asset_index")
    finally:
        await service.close()
        await second.close()


@pytest.mark.parametrize(("raw", "error"), [
    ([], "INVALID_DATA"), ([{"name": "xyz"}], "INVALID_DATA"),
    ([None, None], "INVALID_DATA"), ([None, {}], "INVALID_DATA"),
    ([None, {"name": ""}], "NAMESPACE_CONFLICT"),
    ([None, {"name": "xyz"}, {"name": "xyz"}], "NAMESPACE_CONFLICT"),
    ([None] + [{"name": str(i)} for i in range(discovery.MAX_NAMESPACES)], "CATALOG_CAPACITY"),
])
def test_invalid_inventory_fails_closed(raw, error):
    with pytest.raises(DiscoveryFailure, match=f"^{error}$"):
        normalize_inventory(raw, "MAINNET")


@pytest.mark.parametrize("name", ["x/y", "x:y", "ABC\n", "a" * 33, "ä"])
def test_namespace_uses_contract_grammar(name):
    with pytest.raises(ValidationError):
        normalize_inventory([None, {"name": name}], "MAINNET")


@pytest.mark.parametrize(("raw", "dex", "code"), [
    ({}, "", "MISSING_METADATA"),
    (meta(), "abc", "MISSING_METADATA"),
    ({"universe": {}}, "", "INVALID_DATA"),
    ({"network": "TESTNET", **meta(row("A"))}, "", "NETWORK_MISMATCH"),
    ({"dex": "xyz", **meta(row("abc:A"))}, "abc", "NAMESPACE_CONFLICT"),
    (meta(row("abc:A", network="TESTNET")), "abc", "NETWORK_MISMATCH"),
    (meta(row("abc:A", dex="xyz")), "abc", "NAMESPACE_CONFLICT"),
    (meta(row("xyz:A")), "abc", "NAMESPACE_CONFLICT"),
    (meta(row("abc:A")), "", "NAMESPACE_CONFLICT"),
    (meta(row("A")), "abc", "NAMESPACE_CONFLICT"),
    (meta(row("A"), row("A")), "", "NAMESPACE_CONFLICT"),
    (meta(row("A", universeIndex=0), row("B", universeIndex=0)), "", "INVALID_DATA"),
    (meta(row("A", universeIndex=10_000)), "", "INVALID_DATA"),
    (meta(row("A", universeIndex=False)), "", "INVALID_DATA"),
    (meta(row("A", isDelisted=None)), "", "INVALID_DATA"),
    (meta(row("A", isDelisted=1)), "", "INVALID_DATA"),
    (meta(row("A", instrumentType="SPOT")), "", "UNSUPPORTED_METADATA"),
    ({"instrumentType": "SPOT", **meta(row("A"))}, "", "UNSUPPORTED_METADATA"),
])
def test_invalid_meta_diagnostics(raw, dex, code):
    with pytest.raises(DiscoveryFailure, match=f"^{code}$"):
        normalize_metadata(raw, network="MAINNET", dex=dex, observed_at=NOW)


@pytest.mark.parametrize("entry", [
    row("@107"), row("BTC/USDC"), row("abc:BTC:USD"), row("abc:"),
    row("abc:BTC\n"), row("abc:" + "x" * 65), row("a" * 98),
    row("abc:A", -1), row("abc:A", 7), row("abc:A", True), row("abc:A", "2"),
    row("abc:A", 1.0), row("abc:A", None), {"name": "abc:A"},
])
async def test_bad_record_retires_namespace(service, entry):
    catalog, provider = service
    provider.markets["abc"] = meta(entry)
    result = await catalog.catalog()
    assert result.availability == "PARTIAL" and result.catalog is None
    assert result.namespaces[1].error in {"INVALID_DATA", "NAMESPACE_CONFLICT"}


@pytest.mark.parametrize("scope", ["namespace", "combined"])
async def test_catalog_overflow_is_explicit_and_atomic(service, scope):
    catalog, provider = service
    provider.markets[""] = meta(*(row(f"X{i}") for i in range(MAX_CATALOG_RECORDS + (scope == "namespace"))))
    result = await catalog.catalog()
    assert (result.availability, result.error) == ("UNAVAILABLE", "CATALOG_CAPACITY")
    assert result.catalog is None and not result.eligibility


def test_official_endpoints_are_exact():
    assert OfficialMetadataClient("MAINNET").endpoint == MAINNET_API_URL
    assert OfficialMetadataClient("TESTNET", endpoint=TESTNET_API_URL).endpoint == TESTNET_API_URL
    for network, endpoint in [
        ("TESTNET", MAINNET_API_URL), ("MAINNET", MAINNET_API_URL + "/"),
        ("MAINNET", "https://api.hyperliquid.xyz.attacker.invalid"), ("UNKNOWN", MAINNET_API_URL),
    ]:
        with pytest.raises(DiscoveryFailure, match="^NETWORK_MISMATCH$"):
            OfficialMetadataClient(network, endpoint=endpoint)
    with pytest.raises(ValidationError):
        Settings(market_universe_network="https://untrusted.invalid")


class WireResponse:
    def __init__(self, status=200, body=b"", headers=None):
        self.status_code = status
        self.raw = BytesIO(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.raw.close()


@pytest.fixture
def wire(monkeypatch):
    requests = []
    sessions = []
    responses = [WireResponse(body=b"[null]")]

    def send(adapter, request, **kwargs):
        requests.append((request, kwargs))
        return responses.pop(0)

    close = Session.close

    def closed(session):
        sessions.append(session)
        close(session)

    monkeypatch.setattr(HTTPAdapter, "send", send)
    monkeypatch.setattr(Session, "close", closed)
    return requests, responses, sessions


def test_real_sdk_methods_without_spot_wallet_or_redirects(wire):
    requests, responses, sessions = wire
    responses.append(WireResponse(body=b'{"universe":[{"name":"xyz:BTC","szDecimals":2}]}'))
    client = OfficialMetadataClient("TESTNET")
    assert client("perpDexs", "", monotonic() + 5) == [None]
    assert client("meta", "xyz", monotonic() + 5) == meta(row("xyz:BTC"))
    assert len(sessions) == 2 and sessions[0] is not sessions[1]
    assert [json.loads(r.body) for r, _ in requests] == [
        {"type": "perpDexs"}, {"type": "meta", "dex": "xyz"},
    ]
    for request, options in requests:
        assert request.url == TESTNET_API_URL + "/info" and request.method == "POST"
        assert not {"authorization", "cookie"}.intersection(key.lower() for key in request.headers)
        assert options["stream"] is True and 0 < options["timeout"] <= 5


@pytest.mark.parametrize(("status", "headers", "body", "code"), [
    (302, {"Location": "https://untrusted.invalid"}, b"", "UPSTREAM_ERROR"),
    (403, {}, b"provider-secret", "FORBIDDEN"),
    (429, {}, b"provider-secret", "RATE_LIMITED"),
    (503, {}, b"provider-secret", "UPSTREAM_ERROR"),
    (200, {"Content-Length": "2000000"}, b"x", "RESPONSE_TOO_LARGE"),
    (200, {}, b"x" * (discovery.MAX_PROVIDER_BYTES + 1), "RESPONSE_TOO_LARGE"),
    (200, {"Content-Encoding": "gzip"}, b"x", "UNSUPPORTED_METADATA"),
    (200, {"Content-Length": "1.2"}, b"x", "INVALID_DATA"),
    (200, {"Content-Length": "8"}, b"[null]", "INVALID_DATA"),
    (200, {}, b'{"name":"A","name":"B"}', "INVALID_DATA"),
    (200, {}, b"[NaN]", "INVALID_DATA"),
    (200, {}, b"\xff", "INVALID_DATA"),
    pytest.param(200, {}, b"[" * (discovery.MAX_JSON_DEPTH + 1) + b"]" * (discovery.MAX_JSON_DEPTH + 1),
                 "INVALID_DATA", id="too-deep-json"),
])
def test_http_bounds_and_diagnostics(wire, status, headers, body, code):
    requests, responses, sessions = wire
    response = WireResponse(status, body, headers)
    responses[0] = response
    with pytest.raises(DiscoveryFailure, match=f"^{code}$"):
        OfficialMetadataClient("MAINNET")("perpDexs", "", monotonic() + 5)
    assert len(requests) == len(sessions) == 1 and response.raw.closed
    if status != 200 or headers.get("Content-Length") == "2000000":
        assert requests[0][0].url == MAINNET_API_URL + "/info"


async def test_failed_sdk_initialization_closes_its_session(wire, monkeypatch):
    requests, _, sessions = wire

    def broken(info, *args, **kwargs):
        info.session = Session()
        raise ImportError("private stack text")

    monkeypatch.setattr(Info, "__init__", broken)
    client = MarketUniverseDiscovery(enabled=True, network="MAINNET")
    try:
        result = await client.catalog()
        assert result.inventory.error == "SDK_UNAVAILABLE"
        assert not requests and len(sessions) == 1
        assert "private stack text" not in result.model_dump_json()
    finally:
        await client.close()


def test_session_cleanup_failure_discards_observation(wire, monkeypatch, caplog):
    _, _, sessions = wire
    close = Session.close

    def broken(session):
        close(session)
        raise RuntimeError("private cleanup text")

    monkeypatch.setattr(Session, "close", broken)
    with pytest.raises(DiscoveryFailure, match="^CLEANUP_ERROR$"):
        OfficialMetadataClient("MAINNET")("perpDexs", "", monotonic() + 5)
    assert len(sessions) == 1 and "private cleanup text" not in caplog.text


async def test_ttl_boundary_stale_validation_and_refresh(service, clock):
    catalog, provider = service
    first = await catalog.catalog()
    clock.now += timedelta(seconds=10)
    boundary = await catalog.catalog()
    assert boundary.catalog_fingerprint == first.catalog_fingerprint
    assert boundary.eligibility[0].reason == "DISCOVERABLE"
    clock.now += timedelta(microseconds=1)
    stale = await catalog.catalog()
    assert stale.availability == "STALE" and not any(d.discovery_eligible for d in stale.eligibility)
    assert {row.metadata_status for row in stale.catalog.records} == {"STALE"}
    assert len(provider.calls) == 4
    clock.seconds += 10
    provider.markets[""] = meta(row("NEW"))
    refreshed = await catalog.catalog()
    assert refreshed.availability == "AVAILABLE" and len(provider.calls) == 8
    assert len(refreshed.catalog.records) == 4
    assert refreshed.catalog_fingerprint not in {first.catalog_fingerprint, stale.catalog_fingerprint}


async def test_partial_then_total_failure_retains_one_stale_generation_and_recovers(service, clock):
    catalog, provider = service
    first = await catalog.catalog()
    clock.advance(10)
    provider.markets[""] = meta(row("NEW"))
    provider.markets["abc"] = Timeout("private timeout")
    partial = await catalog.catalog()
    assert partial.availability == "PARTIAL"
    assert [e.error for e in partial.namespaces] == [None, "TIMEOUT", None]
    assert partial.namespaces[0].observed_at == clock.now
    assert [m.source_coin for m in partial.catalog.records] == [m.source_coin for m in first.catalog.records]
    assert all(m.metadata_status == "STALE" and m.observed_at == NOW for m in partial.catalog.records)
    assert all(not decision.discovery_eligible for decision in partial.eligibility)
    assert partial.catalog_fingerprint == partial.catalog.fingerprint() != first.catalog_fingerprint
    count = len(provider.calls)
    clock.advance(4)
    assert (await catalog.catalog()).catalog_fingerprint == partial.catalog_fingerprint
    assert len(provider.calls) == count
    clock.advance(1)
    provider.inventory = ConnectionError("private network error")
    failure = await catalog.catalog()
    assert failure.availability == "UNAVAILABLE" and failure.inventory.error == "NETWORK_ERROR"
    assert failure.catalog_fingerprint == partial.catalog_fingerprint and failure.namespaces == ()
    clock.advance(10)
    provider.inventory = [None, {"name": "abc"}]
    provider.markets["abc"] = meta(row("abc:NEW"))
    recovered = await catalog.catalog()
    assert recovered.availability == "AVAILABLE"
    assert [row.source_coin for row in recovered.catalog.records] == ["NEW", "abc:NEW"]
    assert all(row.observed_at == clock.now for row in recovered.catalog.records)
    assert all(item.discovery_eligible for item in recovered.eligibility)


async def test_core_failure_can_never_publish_builder_records(service):
    catalog, provider = service
    provider.markets[""] = meta()
    result = await catalog.catalog()
    assert (result.availability, result.catalog) == ("UNAVAILABLE", None)
    assert [e.status for e in result.namespaces] == ["FAILED", "REFRESHED", "REFRESHED"]


async def test_rate_limit_backs_off_and_skips_queued_requests(service, clock):
    catalog, provider = service
    provider.inventory.extend({"name": f"z{i}"} for i in range(10))
    provider.markets["abc"] = DiscoveryFailure("RATE_LIMITED")
    result = await catalog.catalog()
    assert result.availability == "PARTIAL"
    assert any(i.status == "SKIPPED" and i.error == "RATE_LIMITED" for i in result.namespaces)
    calls = len(provider.calls)
    assert calls <= len(provider.inventory)
    clock.advance(29)
    await catalog.catalog()
    assert len(provider.calls) == calls
    clock.advance(1)
    provider.inventory = [None]
    assert (await catalog.catalog()).availability == "AVAILABLE"


@pytest.mark.parametrize("shutdown", [False, True])
async def test_cancelled_waiters_do_not_abandon_sdk_owner(shutdown):
    started, release = Event(), Event()
    provider = Provider()

    def blocked(method, dex, deadline):
        if method == "perpDexs":
            started.set()
            assert release.wait(4)
        return provider(method, dex, deadline)

    catalog = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=blocked)
    try:
        reader = asyncio.create_task(catalog.catalog())
        assert await asyncio.to_thread(started.wait, 2)
        reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reader
        if shutdown:
            closer = asyncio.create_task(catalog.close())
            await asyncio.sleep(0)
            assert not closer.done()
            closer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await closer
            assert (await catalog.catalog()).error == "CLOSED"
            again = asyncio.create_task(catalog.close())
        else:
            again = asyncio.gather(*(catalog.catalog() for _ in range(15)))
        release.set()
        outcome = await again
        counts = Counter(provider.calls)
        assert counts[("perpDexs", "")] == 1
        if shutdown:
            assert sum(counts.values()) == 1
        else:
            assert all(response.availability == "AVAILABLE" for response in outcome)
            assert len({response.catalog_fingerprint for response in outcome}) == 1 and sum(counts.values()) == 4
    finally:
        release.set()
        await catalog.close()
    assert not any(thread.name.startswith("market-universe") for thread in threads())


async def test_deadline_returns_promptly_and_cannot_publish_late_worker():
    release = Event()
    provider = Provider()

    def blocked(method, dex, deadline):
        assert release.wait(4)
        return provider(method, dex, deadline)

    catalog = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=blocked, refresh_timeout=0.05)
    try:
        responses = await asyncio.wait_for(asyncio.gather(catalog.catalog(), catalog.catalog()), 1)
        assert all(result.error == "TIMEOUT" and result.catalog is None for result in responses)
        release.set()
        late = await catalog.catalog()
        assert late.availability == "UNAVAILABLE" and late.catalog is None
    finally:
        release.set()
        await catalog.close()
    assert provider.calls == [("perpDexs", "")]
    assert not any(thread.name.startswith("market-universe") for thread in threads())


async def test_executor_never_runs_more_than_three_provider_calls():
    provider = Provider()
    provider.inventory.extend({"name": f"z{i}"} for i in range(8))
    provider.markets.update({f"z{i}": meta(row(f"z{i}:BTC")) for i in range(8)})
    entered, release, lock = Event(), Event(), Lock()
    active = peak = 0

    def record(method, dex, deadline):
        nonlocal active, peak
        if method == "meta":
            with lock:
                active += 1
                peak = max(peak, active)
                if peak == 3:
                    entered.set()
            try:
                assert release.wait(4)
            finally:
                with lock:
                    active -= 1
        return provider(method, dex, deadline)

    catalog = MarketUniverseDiscovery(enabled=True, network="MAINNET", client=record)
    try:
        read = asyncio.create_task(catalog.catalog())
        assert await asyncio.to_thread(entered.wait, 2)
        assert not read.done() and peak == 3
        release.set()
        result = await read
        assert peak == 3 and result.availability == "AVAILABLE" and len(result.namespaces) == 11
    finally:
        release.set()
        await catalog.close()


def test_duplicate_local_index_rejected_across_direct_catalog_inputs():
    first, second = normalize_metadata(meta(row("A"), row("B")), network="MAINNET", dex="", observed_at=NOW)
    with pytest.raises(ValidationError, match="duplicate universe index"):
        MarketUniverseCatalog(records=(first, second.model_copy(update={"universe_index": 0})))
