from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.agents.advisory_contracts import AdvisoryContext, AdvisorySnapshot
from app.agents.advisory_evidence import AdvisoryBindingError, capture_context
from app.agents.market_eligibility import MarketEligibilityAgent, PaperEligibilityCapture
from app.agents.models import AgentRecommendation
from test_phase182_generalized_paper import proposal_for
from test_phase183b_market_risk_metadata import market_wire, observation
from test_phase183c_market_risk_calculations import hypothetical, sourced
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401
from test_phase184a_advisory_contracts import NOW, market


def context(metadata, paper=None, **kwargs):
    binding = paper.admission.binding if paper else None
    return capture_context(metadata, **{
        "evaluated_at": NOW, "valid_until": NOW + timedelta(seconds=35),
        "sources": paper.source_evidence() if paper else (),
        "paper_binding_fingerprint": binding.configuration_fingerprint if binding else None,
        "risk_model_fingerprint": binding.research_risk_fingerprint if binding else None,
        **kwargs,
    })


def assess(metadata, proposal=None, **kwargs):
    return PaperEligibilityCapture.from_assessment(
        proposal or proposal_for(metadata, price="100"), metadata,
        network=metadata.identity.network, evaluated_at=NOW, max_age_seconds=60, **kwargs,
    )


@pytest.mark.parametrize(("network", "dex"), [("MAINNET", ""), ("MAINNET", "xyz"), ("TESTNET", "alpha")])
def test_discovery_and_standard_are_source_bound(network, dex, offline_boundaries):
    metadata = market(network=network, dex=dex)
    evaluator = MarketEligibilityAgent()
    for operation, capture in (("DISCOVERY", None), ("STANDARD_PAPER", assess(metadata))):
        captured = context(metadata, capture)
        recommendation = evaluator.evaluate(captured, operation, as_of=NOW, paper=capture)
        assert recommendation.status == "READY"
        assert recommendation.suitability == "SUITABLE"
        assert recommendation == evaluator.evaluate(captured, operation, as_of=NOW, paper=capture)
        assert not isinstance(recommendation, AgentRecommendation)
        assert not any((recommendation.affects_quotes, recommendation.execution_eligible,
                        recommendation.can_authorize_paper, recommendation.can_override_risk))
        assert recommendation.authority == "NONE"
        assert AdvisorySnapshot(context=captured, market_eligibility=recommendation).fingerprint()


def test_same_market_name_cannot_cross_namespaces_or_networks():
    metadata = market(dex="xyz")
    capture = assess(metadata)
    for other in (market(dex="other"), market(dex="xyz", network="TESTNET"), market()):
        with pytest.raises(AdvisoryBindingError, match="generation"):
            MarketEligibilityAgent().evaluate(context(other), "STANDARD_PAPER", as_of=NOW, paper=capture)
        with pytest.raises(AdvisoryBindingError, match="network"):
            assess(other, capture.proposal)


@pytest.mark.parametrize(("changes", "status", "suitability"), [
    ({"listed": False}, "UNSUPPORTED", "NOT_SUITABLE"),
    ({"status": "STALE"}, "STALE", "UNKNOWN"),
    ({"status": "UNAVAILABLE"}, "INSUFFICIENT_DATA", "UNKNOWN"),
])
def test_unlisted_stale_and_missing_precision_are_neutral(changes, status, suitability):
    metadata = market(**changes)
    result = MarketEligibilityAgent().evaluate(context(metadata), "DISCOVERY", as_of=NOW)
    assert (result.status, result.suitability, result.confidence) == (status, suitability, 0)
    assert result.missing_requirements


def test_standard_paper_and_hypothetical_risk_have_independent_evidence_requirements():
    metadata = market(dex="xyz")
    plain = assess(metadata)
    modeled = assess(metadata, proposal_for(metadata, price="100", research_risk=hypothetical()))
    agent = MarketEligibilityAgent()
    assert agent.evaluate(context(metadata, plain), "STANDARD_PAPER", as_of=NOW, paper=plain).status == "READY"
    assert agent.evaluate(context(metadata, modeled), "HYPOTHETICAL_RISK", as_of=NOW, paper=modeled).status == "READY"
    wrong = agent.evaluate(context(metadata, modeled), "SOURCE_CONSTRAINED_RISK", as_of=NOW, paper=modeled)
    assert wrong.status == "INSUFFICIENT_DATA"
    assert wrong.missing_requirements == ("MATCHING_RESEARCH_SCENARIO",)
    no_margin = agent.evaluate(context(metadata, plain), "HYPOTHETICAL_RISK", as_of=NOW, paper=plain)
    assert no_margin.status == "INSUFFICIENT_DATA"


@pytest.mark.parametrize("mode", ["strictIsolated", None])
def test_documented_source_constrained_risk_requires_matched_collateral_and_supported_margin(mode):
    source = observation(dex="xyz", raw=market_wire("xyz", mode=mode))
    metadata = source.metadata
    proposal = proposal_for(metadata, price="100", research_risk=sourced(source))
    now = metadata.observed_at
    agent = MarketEligibilityAgent()
    missing = PaperEligibilityCapture.from_assessment(
        proposal, metadata, network="MAINNET", evaluated_at=now, max_age_seconds=60,
    )
    deadline = now + timedelta(seconds=30)
    absent = agent.evaluate(context(metadata, missing, evaluated_at=now, valid_until=deadline),
                            "SOURCE_CONSTRAINED_RISK", as_of=now, paper=missing)
    assert absent.status == "INSUFFICIENT_DATA"
    captured = PaperEligibilityCapture.from_assessment(
        proposal, metadata, network="MAINNET", evaluated_at=now, max_age_seconds=60, risk_source=source,
    )
    result = agent.evaluate(context(metadata, captured, evaluated_at=now, valid_until=deadline),
                            "SOURCE_CONSTRAINED_RISK", as_of=now, paper=captured)
    assert result.status == ("READY" if mode else "UNSUPPORTED")
    assert result.suitability == ("SUITABLE" if mode else "NOT_SUITABLE")
    assert not result.can_authorize_paper


def test_infeasible_profile_cannot_override_paper_rejection():
    metadata = market()
    paper = assess(metadata, proposal_for(metadata, price="0.01"))
    assert paper.admission.reason == "PRICE_UNREPRESENTABLE"
    result = MarketEligibilityAgent().evaluate(context(metadata, paper), "STANDARD_PAPER", as_of=NOW, paper=paper)
    assert result.status == "UNSUPPORTED" and result.suitability == "NOT_SUITABLE"
    assert result.confidence == 0 and result.missing_requirements == paper.admission.checks


def test_reject_detached_or_changed_admission_and_conflicting_source():
    metadata = market()
    eligibility = assess(metadata)
    captured = context(metadata, eligibility)
    agent = MarketEligibilityAgent()
    with pytest.raises(AdvisoryBindingError, match="server assessor"):
        agent.evaluate(captured, "STANDARD_PAPER", as_of=NOW, paper=eligibility.admission)
    wrong = captured.sources[0].model_copy(update={"source_fingerprint": "f" * 64})
    forged = captured.model_copy(update={"sources": (wrong, *captured.sources[1:])})
    with pytest.raises(AdvisoryBindingError, match="context evidence"):
        agent.evaluate(forged, "STANDARD_PAPER", as_of=NOW, paper=eligibility)
    corrupt = captured.model_copy(update={"sources": (*captured.sources, captured.sources[0])})
    with pytest.raises(ValidationError, match="duplicate advisory source"):
        agent.evaluate(corrupt, "DISCOVERY", as_of=NOW)
    with pytest.raises(ValidationError, match="fingerprint mismatch"):
        AdvisoryContext.model_validate(captured.model_copy(update={"metadata_fingerprint": "b" * 64}))


def test_expired_context_missing_funding_and_missing_economics():
    metadata = market()
    captured = context(metadata)
    agent = MarketEligibilityAgent()
    stale = agent.evaluate(captured, "DISCOVERY", as_of=captured.valid_until)
    assert stale.status == "STALE" and stale.confidence == 0
    for operation in ("FUNDING_BASIS", "QUOTE_ECONOMICS"):
        missing = agent.evaluate(captured, operation, as_of=NOW)
        assert missing.status == "INSUFFICIENT_DATA"
        assert missing.suitability == "UNKNOWN"
        assert missing.missing_requirements
