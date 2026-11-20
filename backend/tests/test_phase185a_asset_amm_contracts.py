"""Phase 18.5A: policy declarations cannot acquire AMM quote/trading authority."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.amm.asset_policy_contracts import (
    CONTRACT_VERSION, AssetAmmPolicyAssessment, AssetAmmResearchControls,
    AssetAmmResearchPolicy, AssetResearchClassification, assess_asset_amm_policy,
)
from app.amm.models import AmmModel
from app.market_data.market_universe_contracts import MarketInstrumentIdentity, MarketUniverseMetadata
from app.risk.market_risk_contracts import RiskFinancialUnit
from app.strategy.models import StrategyConfig

NOW = datetime(2026, 11, 19, 20, tzinfo=timezone.utc)


def metadata(*, network="MAINNET", dex="", name="BTC", listed=True, status="EXCHANGE_VERIFIED",
             observed_at=None):
    identity = MarketInstrumentIdentity(
        network=network, instrument_type="HIP3_PERP" if dex else "CORE_PERP",
        dex=dex, instrument_name=name,
    )
    if status == "UNAVAILABLE":
        return MarketUniverseMetadata(identity=identity, metadata_status="UNAVAILABLE",
                                      metadata_source="NONE")
    return MarketUniverseMetadata(
        identity=identity, source_coin=identity.exchange_coin, universe_index=0,
        sz_decimals=5, listed=listed, metadata_status=status,
        metadata_source="OFFICIAL_SDK_HIP3_META" if dex else "OFFICIAL_SDK_CORE_META",
        observed_at=observed_at or NOW - timedelta(seconds=5),
    )


def controls(**changes):
    base = StrategyConfig()
    fields = {name: getattr(base, name) for name in AssetAmmResearchControls.model_fields
              if hasattr(base, name)}
    return AssetAmmResearchControls(**(fields | changes))


def policy(m=None, **changes):
    m = m or metadata()
    fields = {
        "metadata": m,
        "metadata_fingerprint": m.fingerprint(),
        "classification": AssetResearchClassification(family="UNKNOWN"),
        "controls": controls(),
        "hypothetical_accounting_unit": RiskFinancialUnit(
            network=m.identity.network, kind="HYPOTHETICAL_QUOTE",
            symbol="HYPOTHETICAL_QUOTE", provenance="RESEARCH_ASSUMPTION",
        ),
        "simulated_reference_price": "50000",
        "declared_at": NOW,
    }
    return AssetAmmResearchPolicy(**(fields | changes))


def test_existing_constant_product_and_concentrated_controls_are_reused():
    base = controls()
    assert base.amm_model == AmmModel.CONSTANT_PRODUCT
    assert base.total_liquidity == StrategyConfig().total_liquidity
    assert controls(amm_model=AmmModel.CONCENTRATED).amm_model == AmmModel.CONCENTRATED
    assert base.price_precision_policy == "REUSE_GENERALIZED_PRECISION"
    assert base.size_precision_policy == "REUSE_DISCOVERED_SZ_DECIMALS"
    assert CONTRACT_VERSION == "phase185a-v1"


def test_canonical_identity_includes_core_hip3_and_network():
    items = [policy(metadata()), policy(metadata(dex="xyz")), policy(metadata(network="TESTNET"))]
    assert len({item.identity.stable_key for item in items}) == 3
    assert len({item.fingerprint() for item in items}) == 3
    assert all(item.authority == "NONE" and not item.affects_quotes for item in items)


def test_asset_family_is_operator_declared_never_verified():
    for family in ("CRYPTO", "EQUITY", "INDEX", "COMMODITY", "ENERGY", "FX",
                   "RATES", "OTHER", "UNKNOWN"):
        item = policy(classification=AssetResearchClassification(family=family))
        assert item.classification.provenance == "OPERATOR_DECLARED_RESEARCH"
        assert not item.classification.exchange_class_verified
    for changes in [
        {"exchange_class_verified": True},
        {"tradability_verified": 1},
        {"provenance": "EXCHANGE_OBSERVED"},
        {"family": "HIP3_PERP"},
    ]:
        with pytest.raises(ValidationError):
            AssetResearchClassification(family="CRYPTO", **changes) if "family" not in changes else AssetResearchClassification(**changes)


@pytest.mark.parametrize("changes", [
    {"virtual_base_reserve": "0"}, {"virtual_quote_reserve": "NaN"},
    {"levels_per_side": True}, {"max_distance_bps": "2501"},
    {"base_order_size": 0.5}, {"total_liquidity": "0.1"},
    {"concentration_factor": "-1"}, {"concentration_upper_bps": "10",
                                      "concentration_lower_bps": "10"},
    {"hard_inventory_limit_base": "5", "soft_inventory_limit_base": "5"},
    {"max_inventory_price_skew_bps": "501"},
    {"volatility_size_strength": "1.1"},
    {"max_funding_reference_shift_bps": "101"},
    {"provenance": "EXCHANGE_VERIFIED"},
    {"price_precision_policy": "FORCE_TICK"},
    {"size_precision_policy": "UNVERIFIED_TICK"},
])
def test_invalid_numeric_or_unverified_controls_rejected(changes):
    with pytest.raises(ValidationError):
        controls(**changes)


@pytest.mark.parametrize("changes", [
    {"metadata_fingerprint": "b" * 64},
    {"hypothetical_accounting_unit": RiskFinancialUnit(
        network="TESTNET", kind="HYPOTHETICAL_QUOTE",
        symbol="HYPOTHETICAL_QUOTE", provenance="RESEARCH_ASSUMPTION")},
    {"hypothetical_accounting_unit": RiskFinancialUnit(
        network="MAINNET", kind="EXCHANGE_ASSET",
        symbol="USDC", asset_reference="exchange:USDC", provenance="DECLARED_UNVERIFIED")},
    {"simulated_reference_price": "0"},
    {"simulated_reference_price": float("inf")},
    {"reference_provenance": "HYPERLIQUID_LIVE_MARK"},
    {"execution_mode": "TESTNET"},
    {"risk_ready": True},
    {"affects_quotes": True},
    {"can_authorize_paper": True},
    {"can_override_risk": True},
    {"execution_eligible": True},
    {"read_only": 1},
    {"authority": "MAINNET"},
    {"research_scope": "CROSS_MARKET_LIVE"},
    {"source_provenance": "EXCHANGE_VERIFIED"},
])
def test_policy_cannot_be_promoted_to_live_trading_or_assumed_price_source(changes):
    with pytest.raises(ValidationError):
        AssetAmmResearchPolicy(**(policy().model_dump() | changes))


def test_metadata_from_future_is_rejected_for_past_declaration():
    m = metadata(observed_at=NOW + timedelta(seconds=1))
    with pytest.raises(ValidationError):
        policy(m)


def test_research_assessment_is_not_paper_admission():
    item = policy()
    result = assess_asset_amm_policy(item, evaluated_at=NOW, max_age_seconds=60)
    assert result.status == "RESEARCH_DRAFT"
    assert result.reason == "DISCOVERABLE"
    assert result.policy_fingerprint == item.fingerprint()
    assert not result.eligible_for_paper and not result.eligible_for_live
    assert result.authority == "NONE"
    assert result == AssetAmmPolicyAssessment.model_validate_json(result.model_dump_json())


def test_stale_delisted_and_unavailable_metadata_fail_closed():
    examples = [
        (metadata(observed_at=NOW - timedelta(seconds=61)), "STALE_METADATA"),
        (metadata(listed=False), "NOT_LISTED"),
        (metadata(status="UNAVAILABLE"), "MISSING_METADATA"),
        (metadata(status="STALE"), "STALE_METADATA"),
    ]
    for m, expected in examples:
        item = policy(m)
        result = assess_asset_amm_policy(item, evaluated_at=NOW, max_age_seconds=60)
        assert result.status == "BLOCKED" and result.reason == expected
        assert not result.eligible_for_paper


def test_policy_fingerprints_bind_parameters_family_and_evidence():
    a = policy()
    b = policy()
    c = policy(controls=controls(max_distance_bps="120"))
    d = policy(classification=AssetResearchClassification(family="ENERGY"))
    e = policy(catalog_fingerprint="c" * 64)
    f = policy(research_risk_fingerprint="d" * 64)
    g = policy(advisory_snapshot_fingerprint="e" * 64)
    assert a.fingerprint() == b.fingerprint()
    assert len({a.fingerprint(), c.fingerprint(), d.fingerprint(), e.fingerprint(),
                f.fingerprint(), g.fingerprint()}) == 6
    assert a.fingerprint() == AssetAmmResearchPolicy.model_validate_json(
        a.model_dump_json()).fingerprint()


def test_policy_mutated_copy_cannot_bypass_full_revalidation():
    forged_controls = controls().model_copy(update={"base_order_size": Decimal("-1")})
    forged = policy().model_copy(update={"controls": forged_controls})
    with pytest.raises(ValidationError):
        assess_asset_amm_policy(forged, evaluated_at=NOW, max_age_seconds=60)
    with pytest.raises(ValidationError):
        forged.fingerprint()


def test_assessment_clock_and_authority_rejected():
    with pytest.raises(ValueError):
        assess_asset_amm_policy(policy(), evaluated_at=NOW - timedelta(seconds=1),
                                max_age_seconds=60)
    result = assess_asset_amm_policy(policy(), evaluated_at=NOW, max_age_seconds=60)
    for changes in (
        {"eligible_for_paper": True}, {"eligible_for_testnet": True},
        {"eligible_for_live": True}, {"execution_eligible": True},
        {"read_only": 0}, {"affects_quotes": True},
        {"risk_ready": True}, {"can_override_risk": True},
        {"authority": "NONE", "status": "BLOCKED"},
    ):
        with pytest.raises(ValidationError):
            AssetAmmPolicyAssessment(**(result.model_dump() | changes))


def test_existing_strategy_and_amm_policy_do_not_gain_new_runtime_fields():
    assert "asset_amm_policy" not in StrategyConfig.model_fields
    assert "asset_class" not in StrategyConfig.model_fields
    assert "asset_research_policy" not in StrategyConfig.model_fields
    assert policy().controls.amm_model == StrategyConfig().amm_model
