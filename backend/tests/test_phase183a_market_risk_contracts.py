"""Phase 18.3A: risk foundation contracts cannot promote PAPER to exchange risk."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.market_data.market_universe_contracts import MarketInstrumentIdentity, MarketUniverseMetadata
from app.risk.market_risk_contracts import (
    CONTRACT_VERSION, MarketCollateralIdentity, MarketMarginPolicy, MarketRiskReadiness,
    RiskFinancialUnit, assess_market_risk_readiness,
)
from app.simulation.market_profiles import MARKETS, ResearchPerpMarketId

NOW = datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc)


def market(*, network="MAINNET", dex="", name="BTC", status="EXCHANGE_VERIFIED",
           listed=True, observed_at=NOW):
    identity = MarketInstrumentIdentity(
        network=network, instrument_type="HIP3_PERP" if dex else "CORE_PERP",
        dex=dex, instrument_name=name,
    )
    if status == "UNAVAILABLE":
        return MarketUniverseMetadata(identity=identity, metadata_status="UNAVAILABLE",
                                      metadata_source="NONE")
    return MarketUniverseMetadata(
        identity=identity, source_coin=identity.exchange_coin,
        universe_index=0, sz_decimals=5, listed=listed,
        metadata_status=status,
        metadata_source="OFFICIAL_SDK_HIP3_META" if dex else "OFFICIAL_SDK_CORE_META",
        observed_at=observed_at,
    )


def exchange_unit(network="MAINNET", symbol="USDC", asset_ref="exchange:USDC", namespace=""):
    return RiskFinancialUnit(
        network=network, kind="EXCHANGE_ASSET", symbol=symbol,
        asset_namespace=namespace, asset_reference=asset_ref,
        provenance="DECLARED_UNVERIFIED",
    )


def synthetic_unit(network="MAINNET"):
    return RiskFinancialUnit(network=network, kind="HYPOTHETICAL_QUOTE",
                             symbol="HYPOTHETICAL_QUOTE", provenance="RESEARCH_ASSUMPTION")


def units(metadata=None, *, collateral=None, price_quote=None, settlement=None):
    metadata = metadata if metadata is not None else market()
    network = metadata.identity.network
    return MarketCollateralIdentity(
        metadata=metadata, metadata_fingerprint=metadata.fingerprint(),
        collateral_unit=collateral, price_quote_unit=price_quote,
        settlement_unit=settlement, paper_accounting_unit=synthetic_unit(network),
    )


def policy(metadata=None, *, collateral=None, evidence="UNVERIFIED", margin_mode="UNSPECIFIED",
           initial=None, maintenance=None, leverage=None):
    return MarketMarginPolicy(
        financial_units=units(metadata, collateral=collateral),
        policy_evidence=evidence, margin_mode=margin_mode,
        initial_margin_fraction=initial, maintenance_margin_fraction=maintenance,
        modeled_max_leverage=leverage,
    )


def test_network_namespace_identity_and_hypothetical_accounting_cannot_collide():
    core = units(market(), collateral=exchange_unit())
    hip = units(market(dex="xyz", name="BTC"), collateral=exchange_unit())
    testnet = units(market(network="TESTNET"), collateral=exchange_unit("TESTNET"))
    assert len({x.instrument.stable_key for x in (core, hip, testnet)}) == 3
    assert len({x.fingerprint() for x in (core, hip, testnet)}) == 3
    assert core.paper_accounting_unit.kind == "HYPOTHETICAL_QUOTE"
    assert core.collateral_unit.provenance == "DECLARED_UNVERIFIED"
    assert core.contract_version == CONTRACT_VERSION


def test_price_collateral_settlement_are_distinct_roles_not_implicit_usdc():
    quoted = exchange_unit(symbol="USDC")
    collateral = exchange_unit(symbol="PURR", asset_ref="builder:PURR", namespace="builder")
    settled = exchange_unit(symbol="USDT", asset_ref="exchange:USDT")
    x = units(market(dex="builder", name="GOLD"), price_quote=quoted,
              collateral=collateral, settlement=settled)
    assert (x.price_quote_unit.symbol, x.collateral_unit.symbol,
            x.settlement_unit.symbol, x.paper_accounting_unit.symbol) == (
                "USDC", "PURR", "USDT", "HYPOTHETICAL_QUOTE")
    assert not x.verified_collateral and not x.verified_settlement and x.authority == "NONE"
    assert units(market(dex="builder", name="GOLD")).collateral_unit is None


@pytest.mark.parametrize("changes", [
    dict(kind="HYPOTHETICAL_QUOTE", symbol="USDC", asset_reference=None,
         provenance="RESEARCH_ASSUMPTION"),
    dict(kind="HYPOTHETICAL_QUOTE", symbol="HYPOTHETICAL_QUOTE",
         asset_reference="exchange:USDC", provenance="RESEARCH_ASSUMPTION"),
    dict(kind="EXCHANGE_ASSET", symbol="HYPOTHETICAL_QUOTE",
         asset_reference="exchange:USDC", provenance="DECLARED_UNVERIFIED"),
    dict(kind="EXCHANGE_ASSET", symbol="USDC", asset_reference=None,
         provenance="DECLARED_UNVERIFIED"),
    dict(kind="EXCHANGE_ASSET", symbol="USDC", asset_reference="exchange:USDC",
         provenance="RESEARCH_ASSUMPTION"),
    dict(kind="EXCHANGE_ASSET", symbol="bad:unit", asset_reference="exchange:USDC",
         provenance="DECLARED_UNVERIFIED"),
])
def test_invalid_or_privilege_promoted_units_rejected(changes):
    payload = dict(network="MAINNET", kind="EXCHANGE_ASSET", symbol="USDC",
                   asset_reference="exchange:USDC", provenance="DECLARED_UNVERIFIED")
    with pytest.raises(ValidationError):
        RiskFinancialUnit(**(payload | changes))


def test_cross_network_units_and_privilege_flags_fail_closed():
    record = market()
    for changes in (
        dict(collateral_unit=exchange_unit("TESTNET")),
        dict(price_quote_unit=synthetic_unit()),
        dict(settlement_unit=exchange_unit("TESTNET")),
        dict(paper_accounting_unit=exchange_unit()),
        dict(verified_collateral=True),
        dict(verified_settlement=1),
        dict(read_only=0),
        dict(authority="TESTNET"),
        dict(metadata_fingerprint="f" * 64),
    ):
        payload = units(record).model_dump()
        payload.update(changes)
        with pytest.raises(ValidationError):
            MarketCollateralIdentity(**payload)


def test_unverified_margin_cannot_claim_numbers_or_verified_authority():
    base = units()
    assert MarketMarginPolicy(financial_units=base).policy_evidence == "UNVERIFIED"
    for changes in (
        dict(initial_margin_fraction=Decimal("0.1")),
        dict(maintenance_margin_fraction=Decimal("0.05")),
        dict(modeled_max_leverage=Decimal("5")),
        dict(exchange_margin_verified=True),
        dict(shared_capital_eligible=True),
        dict(cross_market_netting_eligible=True),
        dict(execution_eligible=True),
        dict(authority="NONE", liquidation_price=Decimal("123")),
        dict(policy_evidence="EXCHANGE_VERIFIED"),
        dict(account_mode="INVALID"),
    ):
        with pytest.raises(ValidationError):
            MarketMarginPolicy(financial_units=base, **changes)


@pytest.mark.parametrize("invalid", [
    dict(initial_margin_fraction="0.01", maintenance_margin_fraction="0.02"),
    dict(initial_margin_fraction="0", maintenance_margin_fraction="0.01"),
    dict(initial_margin_fraction="1.01", maintenance_margin_fraction="0.1"),
    dict(initial_margin_fraction="NaN", maintenance_margin_fraction="0.01"),
    dict(initial_margin_fraction=0.1, maintenance_margin_fraction="0.01"),
    dict(initial_margin_fraction="0.1", maintenance_margin_fraction="0.05",
         modeled_max_leverage="101"),
    dict(initial_margin_fraction="0.1", maintenance_margin_fraction="0.05",
         modeled_max_leverage=True),
])
def test_hypothetical_margin_fraction_bounds_and_exact_decimals(invalid):
    with pytest.raises(ValidationError):
        MarketMarginPolicy(financial_units=units(), policy_evidence="HYPOTHETICAL",
                           margin_mode="ISOLATED", **invalid)


def test_hypothetical_margin_is_not_exchange_verified_or_risk_ready():
    original = policy(collateral=exchange_unit(), evidence="HYPOTHETICAL",
                      margin_mode="STRICT_ISOLATED", initial="0.1", maintenance="0.05",
                      leverage="10")
    decision = assess_market_risk_readiness(original, evaluated_at=NOW, max_age_seconds=60)
    assert original.initial_margin_fraction == Decimal("0.1")
    assert original.maintenance_margin_fraction == Decimal("0.05")
    assert decision.status == "BLOCKED"
    assert decision.reason == "COLLATERAL_UNVERIFIED"
    assert decision.scope == "SINGLE_MARKET_RESEARCH_ONLY"
    assert not (decision.risk_ready or decision.exchange_margin_verified
                or decision.shared_capital_eligible or decision.leverage_eligible
                or decision.cross_market_netting_eligible or decision.execution_eligible)
    assert decision.authority == "NONE"
    for changes in (
        dict(risk_ready=True),
        dict(exchange_margin_verified=True),
        dict(shared_capital_eligible=1),
        dict(leverage_eligible=True),
        dict(cross_market_netting_eligible=True),
        dict(execution_eligible=True),
        dict(authority="TESTNET"),
        dict(status="READY"),
        dict(scope="OPERATIONAL"),
    ):
        with pytest.raises(ValidationError):
            MarketRiskReadiness(**(decision.model_dump() | changes))


def test_stale_future_delisted_missing_collateral_and_metadata_are_blocked():
    examples = [
        (market(observed_at=NOW - timedelta(seconds=61)), "MARKET_METADATA_STALE"),
        (market(observed_at=NOW + timedelta(seconds=1)), "MARKET_METADATA_STALE"),
        (market(status="STALE"), "MARKET_METADATA_STALE"),
        (market(listed=False), "MARKET_DELISTED"),
        (market(status="UNAVAILABLE"), "MARKET_METADATA_UNAVAILABLE"),
        (market(), "COLLATERAL_NOT_ESTABLISHED"),
    ]
    for record, reason in examples:
        decision = assess_market_risk_readiness(policy(record),
                                                evaluated_at=NOW, max_age_seconds=60)
        assert decision.reason == reason and not decision.risk_ready


def test_fingerprints_bind_units_and_policy_without_claiming_exchange_support():
    a = policy(collateral=exchange_unit())
    b = policy(collateral=exchange_unit())
    alternative = policy(collateral=exchange_unit(
        symbol="USDT", asset_ref="exchange:USDT"))
    hyp = policy(collateral=exchange_unit(), evidence="HYPOTHETICAL",
                 margin_mode="CROSS", initial="0.2", maintenance="0.1")
    assert a.fingerprint() == b.fingerprint()
    assert a.financial_units.fingerprint() != alternative.financial_units.fingerprint()
    assert a.fingerprint() != alternative.fingerprint()
    assert a.fingerprint() != hyp.fingerprint()
    assert hyp.cross_market_netting_eligible is False


def test_mutated_copies_and_extra_margin_fx_fields_cannot_bypass_boundary():
    p = policy(collateral=exchange_unit())
    forged_unit = p.financial_units.model_copy(update={"verified_collateral": True})
    forged = p.model_copy(update={"financial_units": forged_unit})
    with pytest.raises(ValidationError):
        assess_market_risk_readiness(forged, evaluated_at=NOW, max_age_seconds=60)
    with pytest.raises(ValidationError):
        MarketMarginPolicy(financial_units=p.financial_units, fx_conversion_rate="1")
    with pytest.raises(ValidationError):
        MarketMarginPolicy(financial_units=p.financial_units, portfolio_margin_eligible=True)


def test_native_research_contracts_remain_three_market_and_unaffected():
    assert MARKETS == ("BTC", "ETH", "SOL")
    assert set(ResearchPerpMarketId.__args__) == set(MARKETS)
    assert policy().financial_units.paper_accounting_unit.symbol == "HYPOTHETICAL_QUOTE"
