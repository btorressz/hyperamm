"""Phase 18.4A: advisory contracts remain research-only and source-bound."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.advisory_contracts import (
    CONTRACT_VERSION, AdvisoryContext, AdvisorySnapshot, AdvisorySourceEvidence,
    FundingBasisAdvisory, MarketEligibilityAdvisory, QuoteEconomicsAdvisory,
)
from app.agents.models import AgentRecommendation, AgentSupervisorDecision
from app.market_data.market_universe_contracts import MarketInstrumentIdentity, MarketUniverseMetadata
from app.risk.market_risk_contracts import RiskFinancialUnit

NOW = datetime(2026, 11, 18, 23, 0, tzinfo=timezone.utc)
HASH = "a" * 64
HASH2 = "b" * 64


def market(network="MAINNET", dex="", name="BTC", *, listed=True, status="EXCHANGE_VERIFIED"):
    identity = MarketInstrumentIdentity(network=network, instrument_type="HIP3_PERP" if dex else "CORE_PERP",
                                        dex=dex, instrument_name=name)
    if status == "UNAVAILABLE":
        return MarketUniverseMetadata(identity=identity, metadata_status="UNAVAILABLE",
                                      metadata_source="NONE")
    return MarketUniverseMetadata(
        identity=identity, source_coin=identity.exchange_coin, universe_index=0,
        sz_decimals=5, listed=listed, metadata_status=status,
        metadata_source="OFFICIAL_SDK_HIP3_META" if dex else "OFFICIAL_SDK_CORE_META",
        observed_at=NOW - timedelta(seconds=5),
    )


def source(m=None, *, category="FUNDING", provenance="EXCHANGE_OBSERVED",
           source_id="HYPERLIQUID_INFO", fingerprint=HASH, **kw):
    m = m or market()
    fields = dict(identity=m.identity, category=category, provenance=provenance,
                  source_id=source_id, captured_at=NOW, source_fingerprint=fingerprint)
    if provenance == "EXCHANGE_OBSERVED":
        fields["observed_at"] = NOW - timedelta(seconds=3)
    elif provenance == "SCENARIO_SYNTHETIC":
        fields.update(source_id="SCENARIO_FRAME", scenario_at=NOW - timedelta(seconds=1))
    elif provenance == "HYPOTHETICAL_ASSUMPTION":
        fields.update(source_id="ASSUMPTION_INPUT")
    else:
        fields.update(source_id="NONE", source_fingerprint=None)
    return AdvisorySourceEvidence(**(fields | kw))


def context(m=None, sources=None, *, deadline=NOW + timedelta(seconds=25)):
    m = m or market()
    return AdvisoryContext(metadata=m, metadata_fingerprint=m.fingerprint(),
                           catalog_fingerprint=HASH2, evaluated_at=NOW, valid_until=deadline,
                           sources=tuple(sources or ()))


def eligibility(c, status="READY", provenance="EXCHANGE_OBSERVED", **kw):
    fields = dict(identity=c.identity, context_fingerprint=c.fingerprint(),
                  evaluated_at=NOW, operation="DISCOVERY", status=status,
                  suitability="SUITABLE" if status == "READY" else "UNKNOWN",
                  provenance=provenance, confidence="0.9" if status == "READY" else "0",
                  source_fingerprints=(HASH,) if status == "READY" else (),
                  reasons=("Evidence supports the scoped research assessment.",))
    return MarketEligibilityAdvisory(**(fields | kw))


def funding(c, *, source_fps=(HASH,), provenance="EXCHANGE_OBSERVED", **kw):
    fields = dict(identity=c.identity, context_fingerprint=c.fingerprint(),
                  evaluated_at=NOW, status="READY", confidence="0.5",
                  provenance=provenance, source_fingerprints=source_fps,
                  state="FUNDING_POSITIVE", funding_rate="0.0001", funding_interval_seconds=3600,
                  reasons=("Funding is observed, not a forecast.",))
    return FundingBasisAdvisory(**(fields | kw))


def paper_unit(m=None):
    m = m or market()
    return RiskFinancialUnit(network=m.identity.network, kind="HYPOTHETICAL_QUOTE",
                             symbol="HYPOTHETICAL_QUOTE", provenance="RESEARCH_ASSUMPTION")


def economics(c, **kw):
    fields = dict(identity=c.identity, context_fingerprint=c.fingerprint(), evaluated_at=NOW,
                  status="READY", confidence="0.7", provenance="SCENARIO_SYNTHETIC",
                  source_fingerprints=(HASH,), state="MODELED_POSITIVE",
                  accounting_unit=paper_unit(c.metadata), gross_spread_bps="12",
                  fee_cost_bps="4", funding_cost_bps="1", inventory_cost_bps="1",
                  adverse_selection_cost_bps="5", modeled_edge_bps="1",
                  reasons=("Only scenario economics; no guaranteed realized returns.",))
    return QuoteEconomicsAdvisory(**(fields | kw))


def test_strict_foundation_identity_separates_core_hip3_and_network():
    keys = [market().identity.stable_key, market(dex="xyz").identity.stable_key,
            market(network="TESTNET").identity.stable_key]
    assert len(set(keys)) == 3
    assert len({context(market()).fingerprint(), context(market(dex="xyz")).fingerprint(),
                context(market(network="TESTNET")).fingerprint()}) == 3
    assert CONTRACT_VERSION == "phase184a-v1"


def test_observed_synthetic_assumption_and_unavailable_have_distinct_clocks():
    observed = source()
    synthetic = source(category="FUNDING", provenance="SCENARIO_SYNTHETIC")
    assumed = source(category="FEES", provenance="HYPOTHETICAL_ASSUMPTION")
    missing = source(category="ORACLE_PRICE", provenance="UNAVAILABLE")
    assert observed.observed_at is not None and observed.scenario_at is None
    assert synthetic.scenario_at is not None and synthetic.observed_at is None
    assert assumed.observed_at is None and assumed.scenario_at is None
    assert missing.source_fingerprint is None and missing.source_id == "NONE"
    assert all(x.authority == "NONE" and not x.execution_eligible for x in (observed, synthetic, assumed, missing))


@pytest.mark.parametrize("edits", [
    dict(provenance="EXCHANGE_OBSERVED", observed_at=None),
    dict(provenance="EXCHANGE_OBSERVED", observed_at=NOW + timedelta(seconds=1)),
    dict(provenance="EXCHANGE_OBSERVED", scenario_at=NOW),
    dict(provenance="EXCHANGE_OBSERVED", source_fingerprint=None),
    dict(provenance="EXCHANGE_OBSERVED", source_id="SCENARIO_KRAKEN"),
    dict(provenance="SCENARIO_SYNTHETIC", source_id="KRAKEN", scenario_at=NOW),
    dict(provenance="SCENARIO_SYNTHETIC", category="COLLATERAL", scenario_at=NOW),
    dict(provenance="HYPOTHETICAL_ASSUMPTION", source_id="KRAKEN", observed_at=None),
    dict(provenance="UNAVAILABLE", source_id="NONE", source_fingerprint=HASH),
    dict(authority="TESTNET"), dict(execution_eligible=True), dict(read_only=1),
    dict(financial_unit=paper_unit(market(network="TESTNET"))),
])
def test_invalid_evidence_source_and_authority_rejected(edits):
    base = source().model_dump()
    with pytest.raises(ValidationError):
        AdvisorySourceEvidence(**(base | edits))


def test_context_rejects_wrong_market_duplicate_or_expired_source():
    valid = source()
    c = context(sources=(valid,))
    assert c.fingerprint() == AdvisoryContext.model_validate_json(c.model_dump_json()).fingerprint()
    examples = [
        dict(metadata_fingerprint=HASH2),
        dict(sources=(source(market(dex="xyz")),)),
        dict(sources=(source(captured_at=NOW + timedelta(seconds=1)),)),
        dict(sources=(valid, valid)),
        dict(sources=(valid, source(category="MARK_PRICE", source_id="DIFFERENT", fingerprint=HASH))),
        dict(valid_until=NOW),
    ]
    for edits in examples:
        with pytest.raises(ValidationError):
            AdvisoryContext(**(c.model_dump() | edits))


def test_observed_evidence_rejected_for_missing_discovery_provenance():
    m = market(status="UNAVAILABLE")
    with pytest.raises(ValidationError):
        context(m, (source(m),))


@pytest.mark.parametrize("edits", [
    dict(affects_quotes=True), dict(can_override_risk=True), dict(can_authorize_paper=True),
    dict(execution_eligible=True), dict(read_only=0), dict(authority="MAINNET"),
    dict(confidence="1.1"), dict(confidence="NaN"), dict(confidence=0.5),
    dict(status="READY", confidence="0"),
    dict(status="STALE", confidence="0.8", suitability="UNKNOWN"),
    dict(status="UNSUPPORTED", confidence="0.8", suitability="UNKNOWN"),
    dict(status="ERROR", confidence="0.8", suitability="UNKNOWN"),
    dict(status="INSUFFICIENT_DATA", confidence="0.8", suitability="UNKNOWN"),
    dict(status="STALE", suitability="SUITABLE", confidence="0"),
])
def test_advisory_never_mutates_quote_authority_or_invents_ready(edits):
    c = context(sources=(source(),))
    with pytest.raises(ValidationError):
        MarketEligibilityAdvisory(**(eligibility(c).model_dump() | edits))


def test_ready_requires_real_captured_source_and_context_linkage():
    c = context(sources=(source(),))
    answer = eligibility(c)
    snap = AdvisorySnapshot(context=c, market_eligibility=answer)
    assert snap.market_eligibility.suitability == "SUITABLE"
    assert snap.fingerprint() == AdvisorySnapshot.model_validate_json(snap.model_dump_json()).fingerprint()
    for edits in [
        dict(context_fingerprint=HASH2), dict(identity=market(dex="xyz").identity),
        dict(evaluated_at=NOW + timedelta(seconds=1)),
        dict(source_fingerprints=(HASH2,)),
        dict(provenance="SCENARIO_SYNTHETIC"),
    ]:
        with pytest.raises(ValidationError):
            AdvisorySnapshot(context=c, market_eligibility=MarketEligibilityAdvisory(
                **(answer.model_dump() | edits)))


def test_unavailable_and_stale_advice_has_no_signal_or_confidence():
    c = context()
    stale = eligibility(c, status="STALE", provenance="UNAVAILABLE")
    assert stale.confidence == 0
    assert AdvisorySnapshot(context=c, market_eligibility=stale).authority == "NONE"
    with pytest.raises(ValidationError):
        MarketEligibilityAdvisory(**(stale.model_dump() | dict(suitability="SUITABLE")))
    with pytest.raises(ValidationError):
        MarketEligibilityAdvisory(**(stale.model_dump() | dict(source_fingerprints=(HASH,))))


def test_funding_signal_requires_matching_funding_evidence():
    c = context(sources=(source(category="FUNDING"),))
    outcome = funding(c)
    assert AdvisorySnapshot(context=c, funding_basis=outcome).funding_basis.funding_rate == Decimal("0.0001")
    for changes in [dict(state="BASIS_STRESSED", mark_oracle_basis_bps=None),
                    dict(status="ERROR", confidence="0"),
                    dict(state="FUNDING_POSITIVE", funding_rate=None),
                    dict(funding_rate=float(0.0001)),
                    dict(authority="PAPER")]:
        with pytest.raises(ValidationError):
            FundingBasisAdvisory(**(outcome.model_dump() | changes))
    c2 = context(sources=(source(category="FEES"),))
    with pytest.raises(ValidationError):
        AdvisorySnapshot(context=c2, funding_basis=funding(c2))


def test_synthetic_funding_is_not_exchange_observed():
    s = source(provenance="SCENARIO_SYNTHETIC")
    c = context(sources=(s,))
    assert AdvisorySnapshot(context=c, funding_basis=funding(c, provenance="SCENARIO_SYNTHETIC")).funding_basis.provenance == "SCENARIO_SYNTHETIC"
    with pytest.raises(ValidationError):
        AdvisorySnapshot(context=c, funding_basis=funding(c, provenance="EXCHANGE_OBSERVED"))


def test_quote_edge_requires_model_inputs_and_is_never_profit_guarantee():
    c = context(sources=(source(category="QUOTE_LADDER", provenance="SCENARIO_SYNTHETIC"),))
    result = economics(c)
    assert AdvisorySnapshot(context=c, quote_economics=result).quote_economics.hypothetical_only is True
    for changes in [
        dict(guarantees_profit=True),
        dict(hypothetical_only=0),
        dict(provenance="EXCHANGE_OBSERVED"),
        dict(modeled_edge_bps="0"),
        dict(gross_spread_bps=None),
        dict(fee_cost_bps="-1"),
        dict(accounting_unit=RiskFinancialUnit(
            network="MAINNET", kind="EXCHANGE_ASSET", symbol="USDC",
            asset_reference="exchange:USDC", provenance="DECLARED_UNVERIFIED")),
    ]:
        with pytest.raises(ValidationError):
            QuoteEconomicsAdvisory(**(result.model_dump() | changes))


def test_no_advisory_fields_on_existing_six_agent_authorization_contract():
    for model in (AgentRecommendation, AgentSupervisorDecision):
        assert "market_eligibility" not in model.model_fields
        assert "funding_basis" not in model.model_fields
        assert "quote_economics" not in model.model_fields
    c = context(sources=(source(),))
    advisory = eligibility(c)
    assert "spread_multiplier" not in advisory.model_fields
    assert "bid_size_multiplier" not in advisory.model_fields
    assert "max_levels" not in advisory.model_fields
    assert advisory.affects_quotes is False and advisory.can_override_risk is False
