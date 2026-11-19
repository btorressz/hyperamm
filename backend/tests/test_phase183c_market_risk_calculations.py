from datetime import timedelta
from decimal import Decimal, ROUND_DOWN, localcontext
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.risk.market_risk_engine import (
    ResearchRiskError, ResearchRiskSettings, bind_research_model, evaluate_research_risk, opening_feasible,
)
from test_phase183b_market_risk_metadata import NOW, market_wire, observation, tier

D = Decimal


def hypothetical(**overrides):
    return ResearchRiskSettings(**{
        "mode": "HYPOTHETICAL", "margin_mode": "ISOLATED", "capital_paper_quote": "1000",
        "initial_margin_fraction": "0.2", "maintenance_margin_fraction": "0.1", **overrides,
    })


def sourced(source, **overrides):
    return ResearchRiskSettings(**{
        "mode": "SOURCE_CONSTRAINED", "margin_mode": "ISOLATED", "capital_paper_quote": "1000",
        "leverage": "5", "valuation": {"collateral_unit": source.collateral.financial_unit(),
                                     "collateral_per_paper_quote": "1"}, **overrides,
    })


def bind(settings=None, source=None, **overrides):
    record = source.metadata if source else observation().metadata
    return bind_research_model(settings or hypothetical(), record, **{
        "source": source, "evaluated_at": NOW, "max_age_seconds": 60, **overrides,
    })


def evaluate(model=None, **overrides):
    return evaluate_research_risk(model or bind(), **{
        "mark": D("100"), "position": D("0"), "position_limit": D("10"), "valuation_time": NOW, **overrides,
    })


def quote(side, quantity, level=0, price="100", *, filled="0", status="OPEN"):
    return SimpleNamespace(side=side, size=D(quantity), price=D(price), level_index=level,
                           filled_size=D(filled), status=status)


@pytest.mark.parametrize("position", ["-2", "0", "2"])
def test_signed_quantity_notional_margin_headroom_and_utilization(position):
    result = evaluate(position=D(position))
    exposure, margin = result.exposure, result.margin
    size = abs(D(position))
    assert exposure.signed_base == D(position) and exposure.absolute_notional == size * 100
    assert exposure.gross_long_notional - exposure.gross_short_notional == D(position) * 100
    assert exposure.inventory_utilization == size / 10 and exposure.capital_concentration == size / 10
    assert margin.current.initial == size * 20 and margin.current.maintenance == size * 10
    assert margin.projected_headroom == 1000 - size * 20
    assert exposure.quote_unit == margin.unit and exposure.quote_unit.symbol == "HYPOTHETICAL_QUOTE"


def test_existing_orders_overlap_desired_ladder_once_with_duplicate_resting_and_partial_fills():
    result = evaluate(position=D("-1"), quotes=(quote("BID", "2", price="99"), quote("ASK", "1")),
                      existing=(quote("BID", "3", filled="1", price="98", status="PARTIALLY_FILLED"),
                                quote("BID", "0.5", price="103"), quote("ASK", "2", 1),
                                quote("ASK", "100", 2, status="CANCELLED")))
    e = result.exposure
    assert (e.proposed_bid_notional, e.resting_bid_notional, e.effective_bid_notional) == (198, D("247.5"), D("247.5"))
    assert (e.proposed_ask_notional, e.resting_ask_notional, e.effective_ask_notional) == (100, 200, 300)
    assert (e.projected_long_base, e.projected_short_base) == (D("1.5"), D("-4"))
    assert (e.gross_long_notional, e.gross_short_notional) == (D("247.5"), 400)
    assert result.margin.projected_initial == 80 and result.margin.projected_headroom == 920


def test_explicit_source_conversion_tier_boundary_and_continuous_maintenance():
    source = observation(raw=market_wire(table=56, tiers=[tier("0", 10), tier("1000", 5)]))
    unit = source.collateral.financial_unit()
    model = bind(sourced(source, leverage="10", valuation={"collateral_unit": unit, "collateral_per_paper_quote": "2"}), source)
    below, boundary, above = [evaluate(model, position=D(size)).margin for size in ("4.99995", "5", "5.00005")]
    assert [x.current.initial for x in (below, boundary, above)] == [D("99.999"), D("200"), D("200.002")]
    assert [x.current.maintenance for x in (below, boundary, above)] == [D("49.9995"), D("50"), D("50.001")]
    assert [x.current.tier_lower_bound for x in (below, boundary, above)] == [0, 1000, 1000]
    assert opening_feasible(below) and not opening_feasible(boundary)
    assert boundary.unit == unit and boundary.capital == 2000
    assert model.readiness.status == "BLOCKED" and not model.readiness.exchange_margin_verified


def test_stress_covers_both_directions_collateral_funding_fees_and_projected_exposure():
    model = bind(hypothetical(stresses=[
        {"name": "fall", "price_shock_bps": "-1000", "collateral_loss_bps": "1000",
         "capital_reduction_bps": "1000", "funding_cost_bps": "20", "fees_bps": "10"},
        {"name": "rally", "price_shock_bps": "1000"},
    ]))
    result = evaluate(model, position=D("2"), quotes=(quote("BID", "1"), quote("ASK", "6")))
    fall, rally = result.stresses
    assert fall.adverse_pnl_paper_quote == -30 and fall.costs_paper_quote == D("1.08")
    assert fall.margin.capital == D("778.92") and fall.headroom_deterioration > 0
    assert rally.adverse_pnl_paper_quote == -40 and rally.mark_paper_quote_per_base == 110
    assert result.margin.capital == 1000
    assert result.model_dump_json() == evaluate(model, position=D("2"), quotes=(quote("BID", "1"), quote("ASK", "6"))).model_dump_json()


def test_stress_can_cross_tier_and_report_leverage_infeasibility():
    source = observation(raw=market_wire(table=56, tiers=[tier("0", 10), tier("1000", 5)]))
    model = bind(sourced(source, leverage="10", stresses=[{"name": "rally", "price_shock_bps": "3000"}]), source)
    stress, = evaluate(model, position=D("8")).stresses
    assert stress.tier_changed and not stress.feasible and stress.margin.current.source_max_leverage == 5


def test_rounds_up_and_is_independent_of_ambient_decimal_context():
    model = bind(hypothetical(initial_margin_fraction="0.333333333333", maintenance_margin_fraction="0.1"))
    with localcontext(prec=5, rounding=ROUND_DOWN):
        low = evaluate(model, mark=D("0.000000001"), position=D(1))
    assert low.margin.current.initial == low.margin.current.maintenance == D("0.00000001")
    high = evaluate(model, mark=D("1e30"), position=D("1e30"))
    assert high.margin.current.initial == D("3.33333333333e59")


@pytest.mark.parametrize(("change", "reason"), [
    ({"valuation": None}, "RISK_UNIT_MISMATCH"),
    ({"margin_mode": "CROSS"}, "RISK_MARGIN_MODE_UNSUPPORTED"),
    ({"margin_mode": "NO_CROSS"}, "RISK_MARGIN_MODE_UNSUPPORTED"),
])
def test_unsupported_units_and_modes_fail_closed(change, reason):
    source = observation()
    with pytest.raises(ResearchRiskError, match=reason):
        bind(sourced(source, **change), source)


def test_same_symbol_other_asset_and_future_or_stale_source_fail_closed():
    core, hip = observation(), observation(dex="xyz", raw=market_wire("xyz", index=268))
    with pytest.raises(ResearchRiskError, match="RISK_UNIT_MISMATCH"):
        bind(sourced(hip), core)
    for at in (NOW - timedelta(seconds=1), NOW + timedelta(seconds=60)):
        with pytest.raises(ResearchRiskError, match="RISK_SOURCE_STALE"):
            bind(sourced(core), core, evaluated_at=at)
    with pytest.raises(ResearchRiskError, match="RISK_SOURCE_UNAVAILABLE"):
        bind(sourced(core))


@pytest.mark.parametrize("value", [1.0, True, "NaN", "Infinity", "1e99", "0", "-1"])
def test_exact_financial_inputs_fail_closed(value):
    with pytest.raises(ResearchRiskError, match="RISK_EXPOSURE_INVALID"):
        evaluate(mark=value)


@pytest.mark.parametrize("change", [
    {"leverage": "6", "max_leverage": "5"},
    {"leverage": "4", "max_leverage": "5"},
    {"leverage": "5", "max_leverage": None},
    {"maintenance_margin_fraction": 0.1},
    {"maintenance_margin_fraction": "0.3"},
])
def test_hypothetical_leverage_and_fractions_need_consistent_assumptions(change):
    with pytest.raises(ValidationError):
        hypothetical(**change)


def test_hypothetical_leverage_is_constrained_by_observed_market_and_fingerprint_changes():
    source = observation(raw=market_wire(table=3, leverage=3))
    normal = bind(hypothetical(leverage="5", max_leverage="5"), source)
    changed = bind(hypothetical(leverage="5", max_leverage="5", capital_paper_quote="1001"), source)
    assert normal.fingerprint() != changed.fingerprint()
    assert not opening_feasible(evaluate(normal, position=D("1")).margin)


def test_unknown_hip3_tier_denomination_fails_closed():
    source = observation(dex="xyz", raw=market_wire("xyz", table=56, tiers=[tier("0", 10), tier("1000", 5)]))
    with pytest.raises(ResearchRiskError, match="RISK_SOURCE_UNSUPPORTED"):
        bind(sourced(source), source)
