"""Phase 18 market universe is additive and cannot authorize research or orders."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.market_data.market_universe_contracts import (
    CONTRACT_VERSION, MAX_CATALOG_RECORDS, DiscoveryEligibility, MarketInstrumentIdentity,
    MarketUniverseCatalog, MarketUniverseMetadata, evaluate_discovery,
)
from app.simulation.market_profiles import MARKETS, ResearchPerpMarketId

NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


def identity(kind="CORE_PERP", dex="", name="BTC", network="MAINNET"):
    return MarketInstrumentIdentity(network=network, instrument_type=kind, dex=dex, instrument_name=name)


def metadata(kind="CORE_PERP", dex="", name="BTC", network="MAINNET", **changes):
    market = identity(kind, dex, name, network)
    fields = dict(identity=market, source_coin=market.exchange_coin, universe_index=0, sz_decimals=5,
                  listed=True, metadata_status="EXCHANGE_VERIFIED",
                  metadata_source=("OFFICIAL_SDK_CORE_META" if kind == "CORE_PERP"
                                   else "OFFICIAL_SDK_HIP3_META"), observed_at=NOW)
    fields.update(changes)
    return MarketUniverseMetadata(**fields)


def test_canonical_identity_separates_core_hip3_and_dex_namespaces():
    core = identity()
    builder = identity("HIP3_PERP", "builder", "BTC")
    other = identity("HIP3_PERP", "other", "BTC")
    assert len({core.stable_key, builder.stable_key, other.stable_key}) == 3
    assert core.contract_version == CONTRACT_VERSION


@pytest.mark.parametrize("payload", [
    dict(instrument_type="CORE_PERP", dex="builder", instrument_name="BTC"),
    dict(instrument_type="HIP3_PERP", dex="", instrument_name="BTC"),
    dict(instrument_type="HIP3_PERP", dex="bad:namespace", instrument_name="BTC"),
    dict(instrument_type="HIP3_PERP", dex="builder", instrument_name="BTC:USD"),
    dict(instrument_type="CORE_PERP", dex="", instrument_name=""),
    dict(instrument_type="CORE_PERP", dex="", instrument_name="BTC/USD"),
    dict(instrument_type="SPOT", dex="", instrument_name="BTC"),
])
def test_rejects_invalid_or_ambiguous_instrument_identity(payload):
    with pytest.raises(ValidationError):
        MarketInstrumentIdentity(network="MAINNET", **payload)


def test_verified_metadata_requires_matching_source_listing_precision_and_timestamp():
    valid = metadata()
    assert valid.metadata_status == "EXCHANGE_VERIFIED"
    assert valid.fingerprint() == metadata().fingerprint()
    for changes in [
        dict(metadata_source="OFFICIAL_SDK_HIP3_META"),
        dict(metadata_source="PINNED_RESEARCH_FIXTURE"),
        dict(metadata_source="NONE"),
        dict(universe_index=None),
        dict(sz_decimals=None),
        dict(listed=None),
        dict(observed_at=None),
        dict(sz_decimals=True),
        dict(universe_index=True),
        dict(observed_at=NOW.replace(tzinfo=None)),
    ]:
        with pytest.raises(ValidationError):
            metadata(**changes)
    assert metadata("HIP3_PERP", "builder", "BTC").metadata_source == "OFFICIAL_SDK_HIP3_META"


def test_fixture_and_unknown_metadata_never_promote_to_discovery():
    fixture = MarketUniverseMetadata(identity=identity(), metadata_status="DEMO_PROFILE",
                                     metadata_source="PINNED_RESEARCH_FIXTURE", sz_decimals=5)
    missing = MarketUniverseMetadata(identity=identity(), metadata_status="UNAVAILABLE", metadata_source="NONE")
    for record, reason in ((fixture, "UNVERIFIED_METADATA"), (missing, "MISSING_METADATA")):
        decision = evaluate_discovery(record, evaluated_at=NOW, max_age_seconds=60)
        assert decision.discovery_eligible is False
        assert decision.reason == reason
        assert decision.paper_research_eligible is False
        assert decision.execution_eligible is False
        assert decision.authority == "NONE"
    with pytest.raises(ValidationError):
        metadata(metadata_status="DEMO_PROFILE", metadata_source="OFFICIAL_SDK_CORE_META")


def test_eligibility_fresh_boundary_stale_future_and_delisted():
    fresh = metadata()
    assert evaluate_discovery(fresh, evaluated_at=NOW + timedelta(seconds=60),
                              max_age_seconds=60).reason == "DISCOVERABLE"
    assert evaluate_discovery(fresh, evaluated_at=NOW + timedelta(seconds=61),
                              max_age_seconds=60).reason == "STALE_METADATA"
    assert evaluate_discovery(fresh, evaluated_at=NOW - timedelta(microseconds=1),
                              max_age_seconds=60).reason == "FUTURE_TIMESTAMP"
    assert evaluate_discovery(metadata(listed=False), evaluated_at=NOW,
                              max_age_seconds=60).reason == "NOT_LISTED"
    for budget in (0, -1, 86401, True, 1.5):
        with pytest.raises(ValueError):
            evaluate_discovery(fresh, evaluated_at=NOW, max_age_seconds=budget)
    with pytest.raises(ValueError):
        evaluate_discovery(fresh, evaluated_at=NOW.replace(tzinfo=None), max_age_seconds=60)


def test_discovery_decision_cannot_grant_paper_or_execution_authority():
    d = evaluate_discovery(metadata(), evaluated_at=NOW, max_age_seconds=60)
    assert d.discovery_eligible and d.reason == "DISCOVERABLE"
    assert d.paper_research_eligible is False and d.execution_eligible is False
    assert d.read_only is True and d.authority == "NONE"
    for changes in [
        dict(paper_research_eligible=True),
        dict(execution_eligible=True),
        dict(authority="TESTNET"),
        dict(read_only=False),
        dict(reason="STALE_METADATA"),
        dict(metadata_fingerprint="forged"),
    ]:
        with pytest.raises(ValidationError):
            DiscoveryEligibility(**(d.model_dump() | changes))


def test_catalog_canonical_order_namespaced_indices_and_duplicates():
    core = metadata()
    hip = metadata("HIP3_PERP", "builder", "BTC")
    other = metadata("HIP3_PERP", "other", "BTC")
    a = MarketUniverseCatalog(records=(core, hip, other))
    b = MarketUniverseCatalog(records=(other, core, hip))
    assert a.fingerprint() == b.fingerprint()
    assert a.authority == "NONE" and a.read_only is True
    with pytest.raises(ValidationError, match="duplicate canonical"):
        MarketUniverseCatalog(records=(core, core))
    with pytest.raises(ValidationError, match="duplicate universe index"):
        MarketUniverseCatalog(records=(core, metadata(name="ETH", universe_index=0)))
    assert MarketUniverseCatalog(records=(core, metadata(name="ETH", universe_index=1)))


def test_immutable_contracts_and_mutated_copies_fail_closed():
    original = metadata()
    with pytest.raises(ValidationError):
        original.universe_index = 12
    forged = original.model_copy(update={"metadata_status": "EXCHANGE_VERIFIED",
                                         "observed_at": None})
    with pytest.raises(ValidationError):
        evaluate_discovery(forged, evaluated_at=NOW, max_age_seconds=60)
    with pytest.raises(ValidationError):
        MarketUniverseCatalog(records=(original,), authority="TESTNET")


def test_existing_native_research_and_guarded_execution_are_unchanged():
    assert MARKETS == ("BTC", "ETH", "SOL")
    assert set(ResearchPerpMarketId.__args__) == set(MARKETS)
    root = Path(__file__).resolve().parents[1] / "app"
    execution = (root / "execution" / "hyperliquid.py").read_text()
    assert '0 <= asset < 10_000' in execution
    assert "native perpetual only" in execution
    from app.simulation.market_profiles import research_strategy
    assert callable(research_strategy)


def test_network_is_explicit_in_identity_and_index_scope():
    mainnet = metadata("HIP3_PERP", "xyz", "BTC")
    testnet = metadata("HIP3_PERP", "xyz", "BTC", network="TESTNET")
    assert mainnet.identity.stable_key == "HYPERLIQUID:MAINNET:HIP3_PERP:xyz:BTC"
    assert testnet.identity.stable_key == "HYPERLIQUID:TESTNET:HIP3_PERP:xyz:BTC"
    assert mainnet.fingerprint() != testnet.fingerprint()
    assert len(MarketUniverseCatalog(records=(mainnet, testnet)).records) == 2
    fields = dict(instrument_type="CORE_PERP", dex="", instrument_name="BTC")
    with pytest.raises(ValidationError, match="network"):
        MarketInstrumentIdentity(**fields)
    with pytest.raises(ValidationError, match="network"):
        MarketInstrumentIdentity(network="DEMO", **fields)
    with pytest.raises(ValidationError, match="contract_version"):
        MarketInstrumentIdentity(network="MAINNET", **fields, contract_version="phase180a-v1")


@pytest.mark.parametrize("kind,dex", [("CORE_PERP", ""), ("HIP3_PERP", "xyz")])
def test_dex_local_index_and_perpetual_precision_bounds(kind, dex):
    for edge in (0, 9999):
        assert metadata(kind, dex, universe_index=edge).universe_index == edge
    for edge in (0, 6):
        assert metadata(kind, dex, sz_decimals=edge).sz_decimals == edge
    for index in (-1, 10000, 110000, True, 1.0, "1"):
        with pytest.raises(ValidationError, match="universe_index"):
            metadata(kind, dex, universe_index=index)
    for precision in (-1, 7, 18, True, 1.0, "1"):
        with pytest.raises(ValidationError, match="sz_decimals"):
            metadata(kind, dex, sz_decimals=precision)
    for field in ("asset_index", "action_asset_id", "perp_dex_index"):
        with pytest.raises(ValidationError, match=field):
            metadata(kind, dex, **{field: 0})


def test_official_source_coin_is_bound_to_class_namespace_and_exact_name():
    assert metadata().source_coin == "BTC"
    hip = metadata("HIP3_PERP", "xyz", "BRK.B")
    assert hip.identity.instrument_name == "BRK.B"
    assert hip.identity.exchange_coin == hip.source_coin == "xyz:BRK.B"
    for coin in ("BRK.B", "other:BRK.B", "xyz:brk.b", "XYZ:BRK.B", "xyz:xyz:BRK.B", "xyz:BRK.B\n"):
        with pytest.raises(ValidationError, match="source coin"):
            metadata("HIP3_PERP", "xyz", "BRK.B", source_coin=coin)
    with pytest.raises(ValidationError, match="source coin"):
        metadata(source_coin="xyz:BTC")


@pytest.mark.parametrize("status,source,reason", [
    ("UNAVAILABLE", "NONE", "MISSING_METADATA"),
    ("UNAVAILABLE", "OFFICIAL_SDK_CORE_META", "MISSING_METADATA"),
    ("ERROR", "OFFICIAL_SDK_CORE_META", "METADATA_ERROR"),
    ("DEMO_PROFILE", "PINNED_RESEARCH_FIXTURE", "UNVERIFIED_METADATA"),
])
def test_non_exchange_observations_cannot_claim_upstream_fields(status, source, reason):
    fields = dict(identity=identity(), metadata_status=status, metadata_source=source)
    assert evaluate_discovery(MarketUniverseMetadata(**fields), evaluated_at=NOW,
                              max_age_seconds=60).reason == reason
    for change in (dict(source_coin="BTC"), dict(universe_index=0), dict(listed=False),
                   dict(observed_at=NOW)):
        with pytest.raises(ValidationError, match="cannot claim an exchange observation"):
            MarketUniverseMetadata(**fields, **change)
    if status != "DEMO_PROFILE":
        with pytest.raises(ValidationError):
            MarketUniverseMetadata(**fields, sz_decimals=5)
        with pytest.raises(ValidationError, match="fixture provenance"):
            MarketUniverseMetadata(**(fields | {"metadata_source": "PINNED_RESEARCH_FIXTURE"}))


def test_stale_delisted_observations_reserve_their_index():
    stale = metadata("HIP3_PERP", "xyz", metadata_status="STALE")
    assert evaluate_discovery(stale, evaluated_at=NOW, max_age_seconds=60).reason == "STALE_METADATA"
    with pytest.raises(ValidationError, match="complete matching official evidence"):
        metadata("HIP3_PERP", "xyz", metadata_status="STALE", observed_at=None)
    with pytest.raises(ValidationError, match="duplicate universe index"):
        MarketUniverseCatalog(records=(stale, metadata("HIP3_PERP", "xyz", "ETH", listed=False)))
    assert len(MarketUniverseCatalog(records=(stale, metadata("HIP3_PERP", "other", "ETH"))).records) == 2


def test_fingerprints_and_wire_order_are_canonical():
    offset = timezone(timedelta(hours=5, minutes=30))
    later = metadata(name="ETH", universe_index=1)
    original = metadata()
    equivalent = metadata(observed_at=NOW.astimezone(offset))
    assert equivalent.observed_at.tzinfo is timezone.utc
    assert original.fingerprint() == equivalent.fingerprint()
    assert original.fingerprint() != metadata(observed_at=NOW + timedelta(seconds=1)).fingerprint()
    catalog = MarketUniverseCatalog(records=(later, equivalent))
    reverse = MarketUniverseCatalog(records=(original, later))
    assert catalog.records == (original, later)
    assert catalog.model_dump_json() == reverse.model_dump_json()
    assert catalog.fingerprint() == reverse.fingerprint()
    assert MarketUniverseCatalog.model_validate_json(catalog.model_dump_json()) == catalog
    decision = evaluate_discovery(original, evaluated_at=NOW.astimezone(offset), max_age_seconds=60)
    assert decision.evaluated_at.tzinfo is timezone.utc
    assert DiscoveryEligibility.model_validate_json(decision.model_dump_json()) == decision


def test_catalog_rejects_oversized_inputs_and_limits_malformed_record_errors():
    original = metadata()
    with pytest.raises(ValidationError, match="at most 4096 items"):
        MarketUniverseCatalog(records=(original,) * (MAX_CATALOG_RECORDS + 1))
    with pytest.raises(ValidationError) as malformed:
        MarketUniverseCatalog.model_validate_json(json.dumps({"records": [None] * MAX_CATALOG_RECORDS}))
    assert malformed.value.error_count() == 1
    with pytest.raises(ValidationError, match="records"):
        MarketUniverseCatalog.model_validate_json('{"records":{}}')


@pytest.mark.parametrize("change", [
    dict(venue="OTHER"), dict(network="OTHER"), dict(contract_version="phase180a-v1"),
    dict(instrument_type="SPOT"), dict(dex="xyz"), dict(instrument_name="xyz:BTC"),
])
def test_nested_forged_identity_is_rejected(change):
    original = metadata()
    for unchecked in (original.identity.model_copy(update=change),
                      MarketInstrumentIdentity.model_construct(**(dict(original.identity) | change))):
        with pytest.raises(ValidationError):
            MarketUniverseMetadata(**(dict(original) | {"identity": unchecked}))
        forged = original.model_copy(update={"identity": unchecked})
        with pytest.raises(ValidationError):
            MarketUniverseCatalog(records=(forged,))
        with pytest.raises(ValidationError):
            forged.fingerprint()
        with pytest.raises(ValidationError):
            evaluate_discovery(forged, evaluated_at=NOW, max_age_seconds=60)


@pytest.mark.parametrize("change", [
    dict(metadata_status="FORGED"), dict(metadata_source="FORGED"), dict(universe_index=-1),
    dict(universe_index=110000), dict(sz_decimals=18), dict(listed=1), dict(listed="true"),
    dict(observed_at="2026-11-18T12:00:00Z"), dict(observed_at=None),
])
def test_forged_metadata_revalidates_before_catalog_and_evaluation(change):
    original = metadata()
    for unchecked in (original.model_copy(update=change),
                      MarketUniverseMetadata.model_construct(**(dict(original) | change))):
        with pytest.raises(ValidationError):
            MarketUniverseCatalog(records=(unchecked,))
        with pytest.raises(ValidationError):
            evaluate_discovery(unchecked, evaluated_at=NOW, max_age_seconds=60)


def test_forged_catalog_revalidation_rejects_duplicates_and_overflow():
    original = metadata()
    catalog = MarketUniverseCatalog(records=(original,))
    for unchecked in (
        catalog.model_copy(update={"records": (original, original)}),
        MarketUniverseCatalog.model_construct(records=(original, original)),
    ):
        with pytest.raises(ValidationError, match="duplicate canonical"):
            unchecked.fingerprint()
    with pytest.raises(ValidationError, match="at most 4096 items"):
        catalog.model_copy(update={"records": (original,) * (MAX_CATALOG_RECORDS + 1)}).fingerprint()
    with pytest.raises(ValidationError, match="duplicate canonical"):
        MarketUniverseCatalog(records=(original, MarketUniverseMetadata.model_construct(**dict(original))))


@pytest.mark.parametrize("updates", [
    dict(read_only=1), dict(read_only=False), dict(paper_research_eligible=0),
    dict(paper_research_eligible=True), dict(execution_eligible=0), dict(execution_eligible=True),
    dict(authority="PAPER"), dict(metadata_fingerprint="g" * 64), dict(metadata_fingerprint="a" * 64 + "\n"),
    dict(reason="NOT_LISTED"), dict(reason="FORGED"), dict(discovery_eligible=1),
])
def test_forged_decision_revalidation_rejects_invalid_literals_and_contradictions(updates):
    original = evaluate_discovery(metadata(), evaluated_at=NOW, max_age_seconds=60)
    for unchecked in (original.model_copy(update=updates),
                      DiscoveryEligibility.model_construct(**(dict(original) | updates))):
        with pytest.raises(ValidationError):
            DiscoveryEligibility.model_validate(unchecked)
    with pytest.raises(ValidationError):
        DiscoveryEligibility.model_validate_json(json.dumps(original.model_dump(mode="json") | updates))


def test_detached_decision_requires_bound_metadata_and_freshness_context():
    original = metadata()
    fresh = evaluate_discovery(original, evaluated_at=NOW, max_age_seconds=60)
    assert fresh.validate_against(original, evaluated_at=NOW, max_age_seconds=60) == fresh
    for decision, record, when in (
        (fresh.model_copy(update={"metadata_fingerprint": "f" * 64}), original, NOW),
        (fresh, metadata(listed=False), NOW),
        (fresh, metadata(network="TESTNET"), NOW),
        (fresh, original, NOW + timedelta(seconds=61)),
        (fresh.model_copy(update={"discovery_eligible": False, "reason": "STALE_METADATA"}), original, NOW),
    ):
        with pytest.raises(ValueError, match="decision does not match"):
            decision.validate_against(record, evaluated_at=when, max_age_seconds=60)


def test_wire_validation_rejects_coercion_and_unknown_fields():
    original = metadata()
    payload = original.model_dump(mode="json")
    assert MarketUniverseMetadata.model_validate_json(json.dumps(payload)) == original
    for changes in (dict(universe_index="0"), dict(sz_decimals=5.0), dict(listed="true"),
                    dict(observed_at=1795003200), dict(observed_at="2026-11-18T12:00:00"),
                    dict(fingerprint="a" * 64)):
        with pytest.raises(ValidationError):
            MarketUniverseMetadata.model_validate_json(json.dumps(payload | changes))
    with pytest.raises(ValidationError):
        MarketUniverseMetadata.model_validate_json('{"identity":')
    with pytest.raises(ValidationError, match="read_only"):
        MarketUniverseCatalog.model_validate_json('{"read_only":1}')
    forged = original.model_copy(update={"fingerprint": "a" * 64})
    with pytest.raises(ValidationError, match="fingerprint"):
        MarketUniverseCatalog(records=(forged,))
