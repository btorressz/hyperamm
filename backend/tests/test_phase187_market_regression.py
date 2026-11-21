"""Deterministic cross-market checks across the public route and PAPER worker."""
import asyncio
from datetime import datetime, timezone
from threading import Event

import pytest

from app.simulation.executor import SimulationExecutor
from app.simulation.models import stable_fingerprint
from test_phase181_market_discovery import clock, meta, row  # noqa: F401
from test_phase182_generalized_paper import proposal_for
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401
from test_phase186h_market_summaries import URL, route  # noqa: F401


async def test_qualified_catalog_and_observations_across_market_matrix(route):
    provider = route.provider
    provider.markets[""] = meta(row("ETH", 4), row("BTC", 5), row("SOL", 2), row("DOGE", 0),
                                row("OLD", isDelisted=True))
    provider.markets["xyz"] = meta(row("xyz:GOLD", 4), row("xyz:XYZ100", 4), row("xyz:BTC", 5))
    route.clock.advance(61)
    route.catalog = await route.discovery.catalog()

    raw = provider.context("")
    raw[1][3].update(markPx="0.000019", oraclePx="0.000018", prevDayPx="0.00002",
                     dayNtlVlm="0", openInterest="0", funding="0")
    provider.contexts[""] = raw
    selection = ("xyz:XYZ100", "SOL", "BTC", "xyz:BTC", "abc:BTC", "ETH", "DOGE", "xyz:GOLD", "OLD")
    response = await route.request(*selection)
    assert response["schema_version"] == "phase186h-v1"
    assert response["network"] == "MAINNET" and response["catalog_fingerprint"] == route.catalog.catalog_fingerprint
    records = {record.source_coin: record for record in route.catalog.catalog.records}
    for coin, result in zip(selection, response["results"], strict=True):
        record = records[coin]
        assert result["identity"] == record.identity.model_dump(mode="json")
        assert (result["universe_index"], result["metadata_fingerprint"]) == (record.universe_index, record.fingerprint())
        assert result["source"] == "HYPERLIQUID_INFO_META_AND_ASSET_CTXS"
        assert result["read_only"] and result["authority"] == "NONE" and not result["execution_eligible"]
        if coin == "OLD":
            assert result["status"] == "UNSUPPORTED" and result["observed_at"] is None
            continue
        assert result["status"] == "CURRENT" and result["provider_event_at"] is None
        assert result["observation_clock"] == "LOCAL_RECEIPT"
        assert result["observed_at"] <= response["evaluated_at"] < result["valid_until"]
        assert result["funding_interval_seconds"] == 3600
        assert result["price_unit"] == "PROVIDER_QUOTE_PER_BASE" and result["open_interest_unit"] == "BASE"
        fields = {name: value for name, value in result.items() if name != "observation_fingerprint"}
        assert result["observation_fingerprint"] == stable_fingerprint({
            "catalog_fingerprint": response["catalog_fingerprint"], **fields,
        })

    by_coin = dict(zip(selection, response["results"], strict=True))
    assert [records[coin].sz_decimals for coin in ("BTC", "ETH", "SOL", "DOGE", "xyz:GOLD", "xyz:XYZ100")] == [
        5, 4, 2, 0, 4, 4,
    ]
    assert [by_coin[coin]["mark_price"] for coin in ("BTC", "xyz:BTC", "abc:BTC")] == ["102", "203", "101"]
    doge = by_coin["DOGE"]
    assert doge["mark_price"] == "0.000019" and doge["mark_change_vs_previous_day_percent"] == "-5.00000000"
    assert (doge["day_notional_volume"], doge["open_interest_base"], doge["funding_rate"]) == ("0", "0", "0")
    assert route.acquisitions == {"": 1, "xyz": 1, "abc": 1}


@pytest.mark.parametrize("mutation,expected", [
    ("precision", "CATALOG_CHANGED"), ("ordinal", "INVALID_DATA"),
    ("source_coin", "NAMESPACE_CONFLICT"), ("empty", "CATALOG_CHANGED"),
])
async def test_changed_source_metadata_does_not_cross_market(route, mutation, expected):
    metadata, rows = raw = route.provider.context("xyz")
    first = metadata["universe"][0]
    if mutation == "precision":
        first["szDecimals"] += 1
    elif mutation == "ordinal":
        first["universeIndex"] = 5
    elif mutation == "source_coin":
        first["name"] = "abc:BTC"
    else:
        metadata["universe"].clear()
        rows.clear()
    route.provider.contexts["xyz"] = raw
    hip3, core = (await route.request("xyz:BTC", "BTC"))["results"]
    assert (hip3["error"], hip3["mark_price"], hip3["observation_fingerprint"]) == (expected, None, None)
    assert core["status"] == "CURRENT"


async def test_unknown_unlisted_and_future_receipt(route):
    body = route.body("BTC")
    body["market_keys"][0] = body["market_keys"][0].replace("BTC", "NO_SUCH_MARKET")
    assert (await route.client.post(URL, json=body)).status_code == 404
    assert not route.acquisitions
    old, = (await route.request("OLD"))["results"]
    assert old["status"] == "UNSUPPORTED" and old["limitations"] == ["NOT_LISTED"]
    assert not route.acquisitions

    catalog_time = route.clock.now
    route.clock.advance(1)
    await route.request("BTC")
    route.clock.now = catalog_time
    future, = (await route.request("BTC"))["results"]
    assert future["status"] == "STALE" and future["mark_price"] is None
    assert future["observation_fingerprint"] is None and route.acquisitions == {"": 1}


async def test_public_acquisition_leaves_real_paper_worker_available(route, offline_boundaries):
    executor = SimulationExecutor()
    app = route.app
    app.state.simulation_executor = executor
    started, release = Event(), Event()

    def wait():
        started.set()
        assert release.wait(10)

    route.provider.wait = wait
    route.clock.advance(61)
    route.clock.now = datetime.now(timezone.utc)
    route.catalog = await route.discovery.catalog()
    record = next(record for record in route.catalog.catalog.records if record.source_coin == "BTC")
    acquisition = asyncio.create_task(route.request("BTC"))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        proposal = proposal_for(record, price="64000", scenario="QUIET")
        body = proposal.model_dump(mode="json")
        check = await route.client.post("/generalized-paper/eligibility", json=body)
        assert check.status_code == 200, check.text
        assert not executor._busy
        body["expected"] = check.json()["binding"]
        run = await route.client.post("/generalized-paper/run", json=body)
        assert run.status_code == 200, run.text
        paper = run.json()
        assert paper["execution_mode"] == "PAPER" and paper["proposal"]["simulated_reference_price"] == "64000"
        assert paper["admission"]["binding"]["metadata_fingerprint"] == record.fingerprint()
        assert not acquisition.done() and route.acquisitions == {"": 1}
        assert not hasattr(app.state, "runtime") and not hasattr(app.state, "live_market_streams")
    finally:
        release.set()
        try:
            observed, = (await acquisition)["results"]
            assert observed["mark_price"] == "102"
        finally:
            await executor.shutdown()
