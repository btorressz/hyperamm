import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Event

import pytest
from pydantic import ValidationError
from requests import Session

from app.agents.advisory_contracts import AdvisorySnapshot
from app.agents.advisory_evidence import AdvisoryBindingError, capture_context, captured_paper_scenario
from app.agents.funding_basis import FundingBasisAgent, PaperFundingObservation
from app.market_data.advisory_market_observations import AdvisoryMarketObservations, _OfficialPublicClient, _epoch_ms
from app.market_data.market_universe_discovery import DiscoveryFailure
from test_phase182_generalized_paper import evidence, proposal_for
from test_phase183d_paper_risk_integration import offline_boundaries, run_local  # noqa: F401
from test_phase184a_advisory_contracts import NOW, market, source

D = Decimal


def provider_wire(metadata, *, changes=None, book_changes=None, history=None):
    identity = metadata.identity
    coin = identity.exchange_coin
    ts = _epoch_ms(NOW)
    return {
        "metaAndAssetCtxs": [
            {"universe": [{"name": coin, "szDecimals": metadata.sz_decimals}, *(
                [{"name": f"{identity.dex}:OTHER", "szDecimals": 4}] if identity.dex else
                [{"name": "OTHER", "szDecimals": 4}]
            )]},
            [{"funding": "0.0002", "markPx": "100.13", "oraclePx": "100", "openInterest": "22",
              "midPx": "999", **(changes or {})}, {}],
        ],
        "l2Book": {"coin": coin, "time": ts - 10, "levels": [
            [{"px": "100.10", "sz": "1"}], [{"px": "100.14", "sz": "2"}],
        ], **(book_changes or {})},
        "fundingHistory": history if history is not None else [
            {"coin": coin, "time": ts - 100, "fundingRate": "0.0002", "premium": "0.0001"},
            {"coin": coin, "time": ts - 3_600_100, "fundingRate": "-0.0001"},
        ],
    }


def install_provider(monkeypatch, fixtures, *, closed=None):
    calls = []

    def send(self, session, path, payload, deadline):
        assert path == "/info"
        operation = payload["type"]
        calls.append((self.endpoint, payload))
        answer = fixtures[operation]
        if isinstance(answer, Exception):
            raise answer
        return answer() if callable(answer) else answer

    monkeypatch.setattr(_OfficialPublicClient, "_post", send)
    if closed is not None:
        original = Session.close

        def close(self):
            closed.append(self)
            original(self)

        monkeypatch.setattr(Session, "close", close)
    return calls


def ctx(metadata, observation, **kwargs):
    return capture_context(metadata, **{
        "evaluated_at": NOW, "valid_until": NOW + timedelta(seconds=45),
        "sources": observation.source_evidence(), **kwargs,
    })


@pytest.mark.parametrize(("network", "dex", "endpoint"), [
    ("MAINNET", "", "https://api.hyperliquid.xyz"), ("MAINNET", "xyz", "https://api.hyperliquid.xyz"),
    ("TESTNET", "alpha", "https://api.hyperliquid-testnet.xyz"),
])
async def test_sdk_public_acquisition_market_and_clocks(monkeypatch, network, dex, endpoint, offline_boundaries):
    metadata = market(network=network, dex=dex)
    closed = []
    calls = install_provider(monkeypatch, provider_wire(metadata), closed=closed)
    adapter = AdvisoryMarketObservations(network=network, clock=lambda: NOW)
    try:
        observed = await adapter.observe(metadata)
        captured = ctx(metadata, observed)
        result = FundingBasisAgent().evaluate(captured, observed, as_of=NOW)
        assert observed is await adapter.observe(metadata)
        assert [payload for _, payload in calls] == [
            {"type": "metaAndAssetCtxs", "dex": dex},
            {"type": "l2Book", "coin": metadata.source_coin},
            {"type": "fundingHistory", "coin": metadata.source_coin,
             "startTime": _epoch_ms(NOW) - 86_400_000, "endTime": _epoch_ms(NOW)},
        ]
        assert all(url == endpoint for url, _ in calls)
        assert len(set(closed)) == 3
        assert observed.point("MID_PRICE").value == D("100.12")
        points = {item.category: item for item in observed.source_evidence()}
        assert points["FUNDING"].observed_at is None
        assert points["FUNDING"].observation_clock == "LOCAL_RECEIPT"
        assert points["MID_PRICE"].observed_at == NOW - timedelta(milliseconds=10)
        assert points["MID_PRICE"].observation_clock == "PROVIDER_EVENT"
        assert result.status == "READY" and result.state == "FUNDING_POSITIVE"
        assert result.funding_direction == "LONGS_PAY" and result.funding_interval_seconds == 3600
        assert result.provenance == "EXCHANGE_OBSERVED"
        assert result.mark_oracle_basis_bps == D(13) and result.mark_mid_basis_bps > 0
        assert result.open_interest_base == D(22)
        assert result.history_count == 2 and result.recent_history_mean_rate == D("0.00005")
        assert not result.affects_quotes and result.authority == "NONE"
        assert AdvisorySnapshot(context=captured, funding_basis=result).fingerprint()
    finally:
        await adapter.close()


@pytest.mark.parametrize(("change", "status", "state"), [
    ({"funding": "-0.1"}, "READY", "FUNDING_NEGATIVE"),
    ({"funding": "0"}, "READY", "NEUTRAL"),
    ({"markPx": "10000"}, "READY", "BASIS_STRESSED"),
    ({"markPx": "1000000"}, "UNSUPPORTED", "UNKNOWN"),
    ({"markPx": None}, "INSUFFICIENT_DATA", "UNKNOWN"),
    ({"funding": None}, "INSUFFICIENT_DATA", "UNKNOWN"),
    ({"oraclePx": "Infinity"}, "INSUFFICIENT_DATA", "UNKNOWN"),
    ({"funding": False}, "INSUFFICIENT_DATA", "UNKNOWN"),
    ({"funding": 0.01}, "INSUFFICIENT_DATA", "UNKNOWN"),
    ({"coin": "else:BTC"}, "ERROR", "UNKNOWN"),
    ({"network": "TESTNET"}, "ERROR", "UNKNOWN"),
])
async def test_missing_invalid_and_directional_market_context(monkeypatch, change, status, state):
    metadata = market()
    install_provider(monkeypatch, provider_wire(metadata, changes=change))
    adapter = AdvisoryMarketObservations(network="MAINNET", clock=lambda: NOW)
    try:
        observed = await adapter.observe(metadata)
        captured = ctx(metadata, observed)
        result = FundingBasisAgent().evaluate(captured, observed, as_of=NOW)
        assert (result.status, result.state) == (status, state)
        assert (result.confidence > 0) is (status == "READY")
    finally:
        await adapter.close()


@pytest.mark.parametrize("book_changes", [
    {"time": _epoch_ms(NOW) + 1}, {"time": _epoch_ms(NOW) - 10001},
    {"levels": [[{"px": "100.13", "sz": "1"}], [{"px": "100.12", "sz": "1"}]]},
    {"levels": [[], []]},
])
async def test_invalid_or_misaligned_mid_is_unavailable_without_substitution(monkeypatch, book_changes):
    metadata = market()
    install_provider(monkeypatch, provider_wire(metadata, book_changes=book_changes))
    adapter = AdvisoryMarketObservations(network="MAINNET", clock=lambda: NOW)
    try:
        observed = await adapter.observe(metadata)
        result = FundingBasisAgent().evaluate(ctx(metadata, observed), observed, as_of=NOW)
        assert result.status == "READY"
        assert result.mark_mid_basis_bps is None and result.oracle_mid_basis_bps is None
        assert "MID_PRICE" in result.missing_requirements
    finally:
        await adapter.close()


async def test_history_normalizes_order_and_identical_duplicates_discards_conflicting_hours(monkeypatch):
    metadata = market(dex="xyz")
    wire = provider_wire(metadata)
    first, second = wire["fundingHistory"]
    original = None
    for rows in ([first, second], [second, first, first], [first, dict(first, fundingRate="0.1")], []):
        install_provider(monkeypatch, {**wire, "fundingHistory": rows})
        adapter = AdvisoryMarketObservations(network="MAINNET", clock=lambda: NOW)
        try:
            observed = await adapter.observe(metadata)
            result = FundingBasisAgent().evaluate(ctx(metadata, observed), observed, as_of=NOW)
            if original is None:
                original = result
            elif len(rows) == 3:
                assert original == result
            else:
                assert result.history_count == 0
                assert result.recent_history_mean_rate is None
                assert "FUNDING_HISTORY" in result.missing_requirements
        finally:
            await adapter.close()


@pytest.mark.parametrize("error", ["TIMEOUT", "RATE_LIMITED", "RESPONSE_TOO_LARGE"])
async def test_provider_failures_are_bounded_and_sessions_close(monkeypatch, error):
    metadata = market()
    closed = []
    calls = install_provider(monkeypatch, {"metaAndAssetCtxs": DiscoveryFailure(error)}, closed=closed)
    adapter = AdvisoryMarketObservations(network="MAINNET", clock=lambda: NOW)
    try:
        observed = await adapter.observe(metadata)
        assert observed.status == "ERROR" and len(closed) == 1
        assert FundingBasisAgent().evaluate(ctx(metadata, observed), observed, as_of=NOW).state == "UNKNOWN"
        if error == "RATE_LIMITED":
            assert "backoff" in (await adapter.observe(metadata)).limitations[0]
            assert len(calls) == 1
        with pytest.raises(DiscoveryFailure, match="NETWORK_MISMATCH"):
            await adapter.observe(market(network="TESTNET"))
    finally:
        await adapter.close()


async def test_single_flight_waiter_cancellation_cleans_up(monkeypatch):
    metadata = market()
    started, released = Event(), Event()
    wire = provider_wire(metadata)

    def wait():
        started.set()
        assert released.wait(3)
        return wire["metaAndAssetCtxs"]

    calls = install_provider(monkeypatch, {**wire, "metaAndAssetCtxs": wait})
    adapter = AdvisoryMarketObservations(network="MAINNET", clock=lambda: NOW)
    try:
        requester = asyncio.create_task(adapter.observe(metadata))
        assert await asyncio.to_thread(started.wait, 3)
        other = asyncio.create_task(adapter.observe(metadata))
        requester.cancel()
        with pytest.raises(asyncio.CancelledError):
            await requester
        released.set()
        assert (await other).status == "AVAILABLE"
        assert len(calls) == 3
    finally:
        released.set()
        await adapter.close()


async def test_expiry_detached_labels_and_observed_interval_tampering(monkeypatch):
    metadata = market()
    install_provider(monkeypatch, provider_wire(metadata))
    adapter = AdvisoryMarketObservations(network="MAINNET", clock=lambda: NOW)
    try:
        observed = await adapter.observe(metadata)
    finally:
        await adapter.close()
    agent = FundingBasisAgent()
    captured = ctx(metadata, observed)
    stale = agent.evaluate(captured, observed, as_of=NOW + timedelta(seconds=30))
    assert stale.status == "STALE" and stale.funding_rate is None
    after_book = agent.evaluate(captured, observed, as_of=NOW + timedelta(seconds=11))
    assert after_book.status == "READY" and after_book.mark_mid_basis_bps is None
    fake = source(metadata)
    with pytest.raises(AdvisoryBindingError, match="backend"):
        agent.evaluate(ctx(metadata, observed, sources=(fake,)), fake, as_of=NOW)
    with pytest.raises(AdvisoryBindingError, match="captured context"):
        agent.evaluate(ctx(metadata, observed, sources=(fake,)), observed, as_of=NOW)
    ready = agent.evaluate(captured, observed, as_of=NOW)
    snapshot = AdvisorySnapshot(context=captured, funding_basis=ready)
    assert snapshot.validate_at(as_of=NOW) == snapshot
    with pytest.raises(ValueError, match="expired READY"):
        snapshot.validate_at(as_of=NOW + timedelta(seconds=11))
    with pytest.raises(ValidationError, match="hourly"):
        AdvisorySnapshot(context=captured, funding_basis=ready.model_copy(update={"funding_interval_seconds": 60}))


@pytest.mark.parametrize(("scenario", "direction"), [
    ("POSITIVE_FUNDING_STRESS", "LONGS_PAY"), ("NEGATIVE_FUNDING_STRESS", "SHORTS_PAY"),
])
async def test_synthetic_funding_uses_existing_paper_frame_and_schedule(scenario, direction, offline_boundaries):
    metadata = evidence(dex="xyz", precision=3)
    proposal = proposal_for(metadata, price="3000", scenario=scenario,
                            economics={"model": "HYPOTHETICAL_LINEAR", "funding_interval_seconds": 3})
    paper = await run_local(proposal, metadata)
    now = datetime.now(timezone.utc)
    observation = PaperFundingObservation(paper, now, now + timedelta(seconds=20))
    captured = ctx(metadata, observation, evaluated_at=now, valid_until=observation.valid_until,
                   paper_binding_fingerprint=paper.admission.binding.configuration_fingerprint)
    result = FundingBasisAgent().evaluate(captured, observation, as_of=now)
    assert result.status == "READY" and result.provenance == "SCENARIO_SYNTHETIC"
    assert result.funding_interval_seconds == 3 and result.funding_direction == direction
    assert result.funding_rate == captured_paper_scenario(paper).dataset.frames[-1].perp_context.funding_rate
    assert all(s.observed_at is None for s in observation.source_evidence())
    assert AdvisorySnapshot(context=captured, funding_basis=result).fingerprint()
    with pytest.raises(ValidationError, match="PAPER result evidence mismatch"):
        FundingBasisAgent().evaluate(captured, replace(observation, paper=paper.model_copy(update={
            "admission": paper.admission.model_copy(update={"binding": paper.admission.binding.model_copy(update={
                "configuration_fingerprint": "c" * 64,
            })}),
        })), as_of=now)
