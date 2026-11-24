"""Public Explorer and Funding/Basis use the same provider context fixtures."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.agents.advisory_evidence import AdvisoryBindingError, capture_context
from app.agents.funding_basis import FundingBasisAgent
from app.market_data.advisory_market_observations import AdvisoryMarketObservations, _epoch_ms
from test_phase181_market_discovery import clock, meta, row  # noqa: F401
from test_phase183b_market_risk_metadata import spot_wire
from test_phase184c_funding_basis import provider_wire
from test_phase186h_market_summaries import Route, SummaryProvider


class ParityProvider(SummaryProvider):
    def __init__(self):
        super().__init__()
        self.markets[""]["universe"].extend([row("ETH", 4), row("SOL")])
        self.markets[""]["collateralToken"] = 0
        self.markets["xyz"]["collateralToken"] = 268
        self.inventory.append({"name": "io"})
        self.markets["io"] = {**meta(row("io:AAPL"), row("io:BTC")), "collateralToken": 268}

    def __call__(self, method, dex, deadline):
        if method == "spotMeta":
            return spot_wire()
        return super().__call__(method, dex, deadline)

    def context(self, dex):
        metadata, rows = super().context(dex)
        for context, entry in zip(rows, metadata["universe"], strict=True):
            context["coin"] = entry["name"]
        return [metadata, rows]


@pytest.fixture
async def route(clock):
    instance = await Route().start(clock, "MAINNET", ParityProvider())
    try:
        yield instance
    finally:
        await instance.close()


async def evaluate_context(route, coin, raw, *, delay=timedelta(0), history=None, financial=True):
    records = route.catalog.catalog.records
    metadata = next(record for record in records if record.source_coin == coin)
    identity = metadata.identity
    fingerprint = route.catalog.catalog_fingerprint
    route.provider.contexts[identity.dex] = raw
    summary, = (await route.request(coin))["results"]
    receipt = route.clock.now
    at = _epoch_ms(receipt)
    wire = {**provider_wire(metadata), "metaAndAssetCtxs": raw}
    wire["l2Book"]["time"] = at - 10
    wire["fundingHistory"] = [{"coin": coin, "time": at - 100, "fundingRate": rate}
                              for rate in (history or [])]
    adapter = AdvisoryMarketObservations(network=identity.network, clock=lambda: route.clock.now)
    adapter._client.request = lambda operation, *_args, **_kwargs: wire[operation]
    try:
        observation = await adapter.observe(
            metadata, catalog_fingerprint=fingerprint,
            financial=route.discovery.financial_observation(fingerprint, identity) if financial else None,
            namespace_records=tuple(sorted((record for record in records if record.identity.dex == identity.dex),
                                           key=lambda record: record.universe_index)),
        )
        context = capture_context(metadata, evaluated_at=receipt, valid_until=receipt + timedelta(seconds=60),
                                  catalog_fingerprint=fingerprint, sources=observation.source_evidence())
        advice = FundingBasisAgent().evaluate(context, observation, as_of=receipt + delay)
        return summary, observation, advice
    finally:
        await adapter.close()


def assert_no_basis(advice, status):
    assert advice.status == status
    assert advice.confidence == Decimal(0) and advice.state == "UNKNOWN"
    assert advice.funding_rate is None
    assert advice.mark_oracle_basis_bps is advice.mark_mid_basis_bps is advice.oracle_mid_basis_bps is None
    assert advice.authority == "NONE" and not advice.affects_quotes


@pytest.mark.parametrize("quote_tag", [False, True])
async def test_audit_fixture_rejects_excess_current_funding(route, quote_tag):
    raw = route.provider.context("")
    raw[1][1]["funding"] = "0.006"
    if quote_tag:
        raw[1][1]["quoteUnit"] = "UNTRUSTED"
    summary, observation, advice = await evaluate_context(route, "BTC", raw)
    assert summary["funding_rate"] is None
    assert summary["error"] == ("QUOTE_UNIT_MISMATCH" if quote_tag else None)
    assert_no_basis(advice, "UNSUPPORTED" if quote_tag else "INSUFFICIENT_DATA")
    if quote_tag:
        assert not observation.points
    else:
        assert advice.mark_price == Decimal(summary["mark_price"])


@pytest.mark.parametrize(("rate", "valid"), [
    ("0", True), ("0.005", True), ("-0.005", True),
    ("0.005000000001", False), ("-0.005000000001", False), ("-0.006", False),
    (None, False), ("malformed", False), ("Infinity", False), ("NaN", False), (False, False),
    ("1E+31", False), ("1E-61", False), (0.0001, False),
])
async def test_current_hourly_fraction_parity(route, rate, valid):
    raw = route.provider.context("")
    raw[1][1]["funding"] = rate
    summary, observation, advice = await evaluate_context(route, "BTC", raw)
    if valid:
        assert Decimal(summary["funding_rate"]) == observation.point("FUNDING").value == Decimal(rate)
        assert advice.status == "READY" and advice.confidence == Decimal("0.90")
        assert advice.funding_rate == Decimal(rate) and advice.funding_interval_seconds == 3600
    else:
        assert summary["funding_rate"] is None and observation.point("FUNDING") is None
        assert_no_basis(advice, "INSUFFICIENT_DATA")


@pytest.mark.parametrize(("field", "category", "wire_field"), [
    ("markPx", "MARK_PRICE", "mark_price"), ("oraclePx", "ORACLE_PRICE", "oracle_price"),
])
@pytest.mark.parametrize("value", [None, "0", "-1", "NaN", "Infinity", "1E+31", "1E-61"])
async def test_invalid_or_missing_price_is_omitted_independently(route, field, category, wire_field, value):
    raw = route.provider.context("")
    raw[1][1][field] = value
    summary, observation, advice = await evaluate_context(route, "BTC", raw)
    assert summary[wire_field] is None and observation.point(category) is None
    assert summary["funding_rate"] == str(observation.point("FUNDING").value)
    assert summary["status"] == "CURRENT"
    assert_no_basis(advice, "INSUFFICIENT_DATA")
    assert category in advice.missing_requirements


@pytest.mark.parametrize("tag", ["quoteUnit", "markQuoteUnit", "prevDayQuoteUnit", "oracleQuoteUnit", "midQuoteUnit"])
async def test_unknown_denomination_invalidates_entire_row(route, tag):
    raw = route.provider.context("")
    raw[1][1][tag] = "USDC"
    summary, observation, advice = await evaluate_context(route, "BTC", raw)
    assert summary["error"] == "QUOTE_UNIT_MISMATCH" and summary["mark_price"] is None
    assert not observation.points
    assert_no_basis(advice, "UNSUPPORTED")
    assert "PRICE_UNIT_COMPATIBILITY" in advice.missing_requirements


@pytest.mark.parametrize("index", [268, None, True, "0"])
async def test_conflicting_collateral_invalidates_namespace(route, index):
    raw = route.provider.context("")
    raw[0]["collateralToken"] = index
    summary, observation, advice = await evaluate_context(route, "BTC", raw)
    assert summary["error"] == "QUOTE_UNIT_MISMATCH" and not observation.points
    assert_no_basis(advice, "UNSUPPORTED")


@pytest.mark.parametrize("snapshot_index", [None, 1000])
async def test_missing_or_unresolved_collateral_limits_price_use(clock, snapshot_index):
    provider = ParityProvider()
    if snapshot_index is None:
        del provider.markets[""]["collateralToken"]
    else:
        provider.markets[""]["collateralToken"] = snapshot_index
    route = await Route().start(clock, "MAINNET", provider)
    try:
        summary, observation, advice = await evaluate_context(route, "BTC", provider.context(""))
        assert summary["status"] == "CURRENT"
        assert advice.mark_price == Decimal(summary["mark_price"])
        assert advice.oracle_price == Decimal(summary["oracle_price"])
        assert observation.point("FUNDING").value == Decimal(summary["funding_rate"])
        assert_no_basis(advice, "INSUFFICIENT_DATA")
        assert advice.missing_requirements == ("PRICE_UNIT_COMPATIBILITY",)
        assert "collateral metadata" in advice.reasons[0]
    finally:
        await route.close()


@pytest.mark.parametrize("coin", ["BTC", "ETH", "SOL", "xyz:BTC", "io:BTC", "io:AAPL"])
async def test_qualified_core_and_hip3_have_compatible_provider_price_pairs(route, coin):
    dex = coin.partition(":")[0] if ":" in coin else ""
    summary, observation, advice = await evaluate_context(route, coin, route.provider.context(dex))
    assert summary["identity"]["dex"] == advice.identity.dex == dex
    assert summary["status"] == "CURRENT" and advice.status == "READY"
    assert Decimal(summary["mark_price"]) == advice.mark_price
    assert Decimal(summary["oracle_price"]) == advice.oracle_price
    assert Decimal(summary["funding_rate"]) == advice.funding_rate
    assert advice.mark_oracle_basis_bps is not None
    for point in observation.source_evidence():
        if point.observation_clock == "LOCAL_RECEIPT":
            assert point.observed_at is None
            assert point.captured_at == route.clock.now
        assert point.financial_unit is None


@pytest.mark.parametrize(("mutation", "summary_error"), [
    (lambda raw: raw[1][1].update(coin="io:BTC"), "NAMESPACE_CONFLICT"),
    (lambda raw: raw[1][1].update(network="TESTNET"), "NETWORK_MISMATCH"),
    (lambda raw: raw[1][1].update(universeIndex=2), "NAMESPACE_CONFLICT"),
    (lambda raw: raw[1].reverse(), "NAMESPACE_CONFLICT"),
    (lambda raw: raw[1].pop(), "INVALID_DATA"),
    (lambda raw: raw[0]["universe"].reverse(), "CATALOG_CHANGED"),
    (lambda raw: raw[0]["universe"][1].update(szDecimals=4), "CATALOG_CHANGED"),
    (lambda raw: raw[0]["universe"][1].update(isDelisted=True), "CATALOG_CHANGED"),
])
async def test_incompatible_wire_rows_cannot_cross_identity(route, mutation, summary_error):
    raw = route.provider.context("")
    mutation(raw)
    summary, observation, advice = await evaluate_context(route, "BTC", raw)
    assert summary["error"] == summary_error and not observation.points
    assert_no_basis(advice, "ERROR")


async def test_delisted_market_has_no_funding_or_price_evidence(route):
    summary, observation, advice = await evaluate_context(route, "OLD", route.provider.context(""))
    assert summary["status"] == "UNSUPPORTED" and not observation.points
    assert_no_basis(advice, "UNSUPPORTED")


@pytest.mark.parametrize(("delay", "status"), [
    (timedelta(seconds=30, microseconds=-1), "READY"), (timedelta(seconds=30), "STALE"),
])
async def test_receipt_expiry_and_catalog_binding(route, delay, status):
    summary, observation, advice = await evaluate_context(route, "BTC", route.provider.context(""), delay=delay)
    assert advice.status == status
    if status == "STALE":
        assert_no_basis(advice, "STALE")
    assert summary["valid_until"] == (route.clock.now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    metadata = observation.metadata
    context = capture_context(metadata, evaluated_at=route.clock.now,
                              valid_until=route.clock.now + timedelta(seconds=60),
                              catalog_fingerprint="f" * 64, sources=observation.source_evidence())
    with pytest.raises(AdvisoryBindingError, match="metadata or catalog"):
        FundingBasisAgent().evaluate(context, observation, as_of=route.clock.now)


@pytest.mark.parametrize(("rate", "valid"), [
    ("0.005", True), ("-0.005", True), ("0.006", False), ("-0.005000000001", False),
])
async def test_historical_realized_hourly_rate_is_optional_and_bounded(route, rate, valid):
    _, observation, advice = await evaluate_context(route, "BTC", route.provider.context(""), history=[rate])
    assert advice.status == "READY" and advice.history_count == int(valid)
    assert (advice.recent_history_mean_rate == Decimal(rate)) is valid
    history = observation.point("FUNDING_HISTORY")
    if valid:
        assert history.unit == "REALIZED_RATE_PER_HOUR"
        assert history.observed_at < history.captured_at
    else:
        assert history is None and "FUNDING_HISTORY" in advice.missing_requirements
