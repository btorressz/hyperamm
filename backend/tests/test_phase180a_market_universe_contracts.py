"""Phase 18.0A market universe is additive and cannot authorize research or orders."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.market_data.market_universe_contracts import (
    CONTRACT_VERSION, DiscoveryEligibility, MarketInstrumentIdentity,
    MarketUniverseCatalog, MarketUniverseMetadata, evaluate_discovery,
)
from app.simulation.market_profiles import MARKETS, ResearchPerpMarketId

NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


def identity(kind="CORE_PERP", dex="", name="BTC"):
    return MarketInstrumentIdentity(instrument_type=kind, dex=dex, instrument_name=name)


def metadata(kind="CORE_PERP", dex="", name="BTC", **changes):
    fields = dict(identity=identity(kind, dex, name), asset_index=0, sz_decimals=5,
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
        MarketInstrumentIdentity(**payload)


def test_verified_metadata_requires_matching_source_listing_precision_and_timestamp():
    valid = metadata()
    assert valid.metadata_status == "EXCHANGE_VERIFIED"
    assert valid.fingerprint() == metadata().fingerprint()
    for changes in [
        dict(metadata_source="OFFICIAL_SDK_HIP3_META"),
        dict(metadata_source="PINNED_RESEARCH_FIXTURE"),
        dict(metadata_source="NONE"),
        dict(asset_index=None),
        dict(sz_decimals=None),
        dict(listed=None),
        dict(observed_at=None),
        dict(sz_decimals=True),
        dict(asset_index=True),
        dict(observed_at=NOW.replace(tzinfo=None)),
    ]:
        with pytest.raises(ValidationError):
            metadata(**changes)
    assert metadata("HIP3_PERP", "builder", "BTC").metadata_source == "OFFICIAL_SDK_HIP3_META"


def test_fixture_and_unknown_metadata_never_promote_to_discovery():
    fixture = metadata(metadata_status="DEMO_PROFILE", metadata_source="PINNED_RESEARCH_FIXTURE")
    missing = metadata(metadata_status="UNAVAILABLE", metadata_source="NONE", observed_at=None,
                       asset_index=None, sz_decimals=None, listed=None)
    for record in (fixture, missing):
        decision = evaluate_discovery(record, evaluated_at=NOW, max_age_seconds=60)
        assert decision.discovery_eligible is False
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
    with pytest.raises(ValidationError, match="duplicate verified asset index"):
        MarketUniverseCatalog(records=(core, metadata(name="ETH", asset_index=0)))
    assert MarketUniverseCatalog(records=(core, metadata(name="ETH", asset_index=1)))


def test_immutable_contracts_and_mutated_copies_fail_closed():
    original = metadata()
    with pytest.raises(ValidationError):
        original.asset_index = 12
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
