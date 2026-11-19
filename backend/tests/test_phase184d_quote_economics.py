from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, localcontext

import pytest
from pydantic import ValidationError

from app.agents.advisory_contracts import AdvisorySnapshot
from app.agents.advisory_evidence import AdvisoryBindingError, capture_context
from app.agents.funding_basis import FundingBasisAgent, PaperFundingObservation
from app.agents.market_eligibility import MarketEligibilityAgent, PaperEligibilityCapture
from app.agents.models import AgentRecommendation
from app.agents.quote_economics import QuoteCostAssumptions, QuoteEconomicsAgent, QuoteEconomicsObservation
from app.execution.models import Fill, StrategyOrder
from app.risk.authorization import FinalQuoteAuthorization
from app.risk.market_risk_engine import RISK_CONTEXT
from app.simulation.generalized_market_profiles import _result_fingerprint
from app.simulation.references import build_simulated_references
from test_phase182_generalized_paper import admit, evidence, proposal_for
from test_phase183c_market_risk_calculations import hypothetical
from test_phase183d_paper_risk_integration import offline_boundaries, run_local  # noqa: F401

D = Decimal


def options(**kwargs):
    return QuoteCostAssumptions(**{
        "holding_seconds": 6, "closing_liquidity": "MAKER", "exit_slippage_bps": "0",
        "inventory_rate_bps": "0", **kwargs,
    })


def wrap(paper, *, options=options(), sequence=1):
    now = datetime.now(timezone.utc)
    return QuoteEconomicsObservation(paper, sequence, options, now, now + timedelta(seconds=15))


def bound(observation, *, extra_sources=()):
    paper = observation.paper
    binding = paper.admission.binding
    return capture_context(
        paper.admission.profile.metadata, evaluated_at=observation.captured_at, valid_until=observation.valid_until,
        sources=(*observation.source_evidence(), *extra_sources),
        catalog_fingerprint=binding.catalog_fingerprint, paper_binding_fingerprint=binding.configuration_fingerprint,
        risk_model_fingerprint=binding.research_risk_fingerprint,
    )


def fingerprinted(paper, *, research_risk=None, **changes):
    if research_risk is None:
        research_risk = paper.research_risk
    result = paper.result.model_copy(update=changes)
    run = paper.model_copy(update={
        "result": result, "research_risk": research_risk,
        "result_fingerprint": _result_fingerprint(paper.admission.binding, paper.proposal, result, research_risk),
    })
    return run


async def scenario_run(scenario, *, dex="xyz", fees=("0", "0"), interval=3, risk=None):
    metadata = evidence(dex=dex, name="GOLD" if dex else "BTC", precision=3)
    proposal = proposal_for(metadata, price="3000", frames=30, scenario=scenario, research_risk=risk, economics={
        "model": "HYPOTHETICAL_LINEAR", "funding_interval_seconds": interval,
        "maker_fee_bps": fees[0], "taker_fee_bps": fees[1],
    })
    return await run_local(proposal, metadata)


def modeled_cohort(paper, *, quantities=(D(1), D(1)), target=None, statuses=("MAKER", "MAKER"),
                   millis_offset=0):
    """A labeled synthetic fill fixture on an existing scenario and reference clock."""
    metadata = paper.admission.profile.metadata
    _, prepared = admit(metadata, paper.proposal, evaluated_at=paper.admission.evaluated_at)
    frame = prepared.dataset.frames[0]
    ref = build_simulated_references(
        frame, agreement_bps=prepared.risk.source_agreement_bps,
        outlier_bps=prepared.risk.source_outlier_bps, version=frame.sequence,
    ).consensus.consensus_price
    future = next(item for item in prepared.dataset.frames if item.timestamp >= frame.timestamp + timedelta(seconds=5))
    with localcontext(RISK_CONTEXT):
        adverse = abs(ref - future.market.mid_price)
        if target is None:
            gap = D(10)
        else:
            quantum = D("0.00000001")
            cost = (adverse / (ref * 2) * 10000).quantize(quantum, rounding=ROUND_CEILING)
            gap = (cost + target + D("0.000000004")) * 2 * ref / 10000
        prices = (ref - gap / 2, ref + gap / 2)
    orders = []
    fills = []
    for side, price, filled, liquidity in zip(("BID", "ASK"), prices, quantities, statuses, strict=True):
        orders.append(StrategyOrder(
            client_order_id=side, market=metadata.identity.stable_key, side=side, price=price, size=D(2),
            filled_size=filled, created_at=frame.timestamp, updated_at=frame.timestamp,
        ).model_dump(mode="json"))
        if filled:
            fills.append(Fill(
                client_order_id=side, market=metadata.identity.stable_key, side=side, price=price,
                size=filled, timestamp=frame.timestamp + timedelta(milliseconds=millis_offset), liquidity=liquidity,
            ).model_dump(mode="json"))
    trace = [point.model_copy(update={"inventory_base": quantities[0] - quantities[1]})
             if point.sequence == frame.sequence else point for point in paper.result.trace]
    return fingerprinted(paper, orders=orders, fills=fills, trace=trace)


def evaluate(observation, context=None, **kwargs):
    context = context or bound(observation)
    return QuoteEconomicsAgent().evaluate(context, observation, **{"as_of": context.evaluated_at, **kwargs})


@pytest.mark.parametrize(("target", "state"), [
    (D(1), "MODELED_POSITIVE"), (D(0), "MODELED_BREAKEVEN"), (D("-0.1"), "MODELED_NEGATIVE"),
])
async def test_complete_two_sided_partial_cohort_reconciles(target, state, offline_boundaries):
    paper = modeled_cohort(await scenario_run("HIGH_VOLATILITY"), target=target)
    observation = wrap(paper)
    context = bound(observation)
    result = evaluate(observation, context)
    assert result.status == "READY" and result.state == state
    assert result.fill_coverage == "BOTH_SIDES"
    assert result.filled_base == 2 and result.residual_base == 0
    assert result.captured_spread_bps - result.break_even_capture_bps == result.modeled_edge_bps
    assert result.break_even_capture_bps == sum((
        result.fee_cost_bps, result.funding_cost_bps, result.adverse_selection_cost_bps,
        result.inventory_cost_bps, result.slippage_cost_bps,
    ))
    assert result.bid_capture_bps is not None and result.ask_capture_bps is not None
    assert result.adverse_selection_cost_bps > 0
    assert result.funding_cost_bps == result.fee_cost_bps == 0
    assert result.accounting_unit.kind == "HYPOTHETICAL_QUOTE" and result.provenance == "MIXED"
    assert result == evaluate(observation, context)
    with localcontext() as modified:
        modified.prec = 8
        assert evaluate(observation, context) == result
    assert AdvisorySnapshot(context=context, quote_economics=result).fingerprint()
    with pytest.raises(ValidationError, match="reconcile"):
        AdvisorySnapshot(context=context, quote_economics=result.model_copy(update={
            "fee_cost_bps": result.fee_cost_bps + 1,
        }))


@pytest.mark.parametrize(("scenario", "quantities", "sign"), [
    ("POSITIVE_FUNDING_STRESS", (D(1), D(0)), 1),
    ("POSITIVE_FUNDING_STRESS", (D(0), D(1)), -1),
    ("NEGATIVE_FUNDING_STRESS", (D(1), D(0)), -1),
    ("NEGATIVE_FUNDING_STRESS", (D(0), D(1)), 1),
])
async def test_directional_funding_fees_inventory_and_slippage(scenario, quantities, sign):
    paper = modeled_cohort(await scenario_run(scenario, fees=("2", "100")), quantities=quantities)
    metrics = paper.result.metrics.model_copy(update={"max_inventory_utilization": D("0.8")})
    paper = fingerprinted(paper, metrics=metrics)
    maker = evaluate(wrap(paper))
    taker = evaluate(wrap(paper, options=options(
        closing_liquidity="TAKER", holding_seconds=300, exit_slippage_bps="5", inventory_rate_bps="25",
    )))
    assert maker.status == taker.status == "READY"
    assert taker.fill_coverage == "ONE_SIDED"
    assert taker.residual_base == quantities[0] - quantities[1]
    assert taker.fee_cost_bps > maker.fee_cost_bps
    assert taker.inventory_cost_bps > 0 and taker.slippage_cost_bps > 0
    assert taker.funding_cost_bps.compare(0) == sign
    assert abs(taker.funding_cost_bps) > abs(maker.funding_cost_bps)


async def test_real_cohort_binds_all_three_agents_and_preserves_authority(offline_boundaries):
    paper = await scenario_run("HIGH_VOLATILITY", risk=hypothetical(capital_paper_quote="10000"))
    before = paper.result_fingerprint, paper.result.accounting_fingerprint, paper.result.run_fingerprint
    capture = next((item for item in (wrap(paper, sequence=trace.sequence) for trace in paper.result.trace)
                    if evaluate(item).status == "READY"), None)
    assert capture is not None
    funding = PaperFundingObservation(paper, capture.captured_at, capture.valid_until)
    metadata = paper.admission.profile.metadata
    assessment = PaperEligibilityCapture.from_assessment(
        paper.proposal, metadata, network=metadata.identity.network,
        evaluated_at=paper.admission.evaluated_at, max_age_seconds=60,
    )
    context = bound(capture, extra_sources=(*funding.source_evidence(), *assessment.source_evidence()))
    quote = evaluate(capture, context)
    eligibility = MarketEligibilityAgent().evaluate(
        context, "HYPOTHETICAL_RISK", as_of=context.evaluated_at, paper=assessment,
    )
    funds = FundingBasisAgent().evaluate(context, funding, as_of=context.evaluated_at)
    validation = AdvisorySnapshot(
        context=context, market_eligibility=eligibility, quote_economics=quote, funding_basis=funds,
    )
    assert validation.fingerprint() == AdvisorySnapshot.model_validate_json(validation.model_dump_json()).fingerprint()
    assert quote.status == eligibility.status == funds.status == "READY"
    assert quote.projected_margin_headroom > 0
    assert quote.margin_headroom_unit == quote.accounting_unit
    assert (paper.result_fingerprint, paper.result.accounting_fingerprint, paper.result.run_fingerprint) == before
    for advice in (quote, eligibility, funds):
        assert not isinstance(advice, AgentRecommendation)
        assert advice.authority == "NONE"
        assert not any((advice.affects_quotes, advice.can_override_risk, advice.can_authorize_paper, advice.execution_eligible))
        with pytest.raises(ValidationError):
            FinalQuoteAuthorization.model_validate(advice.model_dump())


async def test_missing_fills_and_maturity_return_indeterminate():
    quiet = await scenario_run("QUIET")
    missing = evaluate(wrap(quiet))
    assert missing.state == "INDETERMINATE" and missing.confidence == 0
    assert missing.missing_requirements == ("PAPER_FILLS",)
    assert missing.modeled_edge_bps is None
    volatile = await scenario_run("HIGH_VOLATILITY")
    outcomes = [evaluate(wrap(volatile, sequence=point.sequence)) for point in volatile.result.trace[-7:]]
    pending = [outcome for outcome in outcomes if outcome.missing_requirements == ("MATURE_MARKOUTS",)]
    assert pending and all(result.state == "INDETERMINATE" and result.confidence == 0 for result in pending)


async def test_retired_halted_invalid_and_unbound_quote_inputs():
    paper = modeled_cohort(await scenario_run("HIGH_VOLATILITY"))
    point, *later = paper.result.trace
    for updated in ({"risk_state": "HALT"}, {"authorized_quote_count": 0}):
        risk = fingerprinted(paper, trace=[point.model_copy(update=updated), *later])
        refused = evaluate(wrap(risk))
        assert refused.status == "UNSUPPORTED" and refused.modeled_edge_bps is None
    other = await scenario_run("HIGH_VOLATILITY", dex="")
    with pytest.raises(AdvisoryBindingError, match="context bindings"):
        evaluate(wrap(other), bound(wrap(paper)))
    float_fill = fingerprinted(paper, fills=[dict(paper.result.fills[0], price=1.0), paper.result.fills[1]])
    with pytest.raises(ValueError, match="exact bounded financial input"):
        evaluate(wrap(float_fill))
    with pytest.raises(ValidationError):
        options(inventory_rate_bps="NaN")
    observation = wrap(paper)
    expired_at = observation.valid_until
    assert evaluate(observation, as_of=expired_at).status == "STALE"
    forged = replace(observation, assumptions=options(holding_seconds=19))
    with pytest.raises(AdvisoryBindingError, match="context evidence"):
        evaluate(forged, bound(observation))


async def test_missing_schedule_reference_and_incompatible_risk_unit(monkeypatch):
    paper = modeled_cohort(await scenario_run("HIGH_VOLATILITY", interval=None))
    assert evaluate(wrap(paper)).missing_requirements == ("PAPER_FUNDING_INTERVAL",)
    from app.agents import quote_economics

    original = quote_economics.build_simulated_references

    def missing_ref(*args, **kwargs):
        result = original(*args, **kwargs)
        return result.model_copy(update={
            "consensus": result.consensus.model_copy(update={"consensus_price": None}),
        })

    modeled = modeled_cohort(await scenario_run("HIGH_VOLATILITY", risk=hypothetical(capital_paper_quote="10000")))
    snap = modeled.research_risk.final_snapshot
    other_unit = snap.exposure.quote_unit.model_copy(update={"network": "TESTNET"})
    adjusted = snap.model_copy(update={"exposure": snap.exposure.model_copy(update={"quote_unit": other_unit})})
    risk = modeled.research_risk.model_copy(update={"final_snapshot": adjusted})
    with pytest.raises(AdvisoryBindingError, match="financial units"):
        evaluate(wrap(fingerprinted(modeled, research_risk=risk)))
    monkeypatch.setattr(quote_economics, "build_simulated_references", missing_ref)
    assert evaluate(wrap(modeled)).missing_requirements == ("QUOTE_REFERENCE",)
