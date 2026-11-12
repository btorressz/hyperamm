from itertools import combinations
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.portfolio_research.models import PortfolioStressRequest, PortfolioStressScenario
from app.portfolio_research.scenarios import baseline_dataset, transform_dataset, validate_dataset
from app.simulation.models import SimulationDataset
from app.simulation.market_profiles import validate_price
from phase174_fixtures import request_for, KINDS

MARKETS = ("BTC", "ETH", "SOL")
SELECTIONS = [c for n in (1, 2, 3) for c in combinations(MARKETS, n)]

@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("markets", SELECTIONS)
def test_all_scenarios_and_market_selections_preserve_baseline_and_clock(kind, markets):
    r = request_for(kind, markets)
    for s in r.config.scenarios:
        base = baseline_dataset(s)
        wire = base.model_dump_json()
        stressed = transform_dataset(base, s, r.scenario, concentration_market=markets[0], concentration_position=Decimal("1"))
        assert base.model_dump_json() == wire
        assert stressed == transform_dataset(base, s, r.scenario, concentration_market=markets[0], concentration_position=Decimal("1"))
        assert tuple((f.sequence, f.timestamp) for f in base.frames) == tuple((f.sequence, f.timestamp) for f in stressed.frames)
        assert stressed.frames[:4] == base.frames[:4]
        p = s.captured.inputs().market_profile
        for f in stressed.frames:
            assert f.market.best_bid < f.market.best_ask
            assert validate_price(f.perp_context.mark_price, p.sz_decimals)
            assert validate_price(f.perp_context.oracle_price, p.sz_decimals)
        assert SimulationDataset.model_validate_json(stressed.model_dump_json()) == stressed

@pytest.mark.parametrize("value", [0.06, float("nan"), float("inf"), True, "NaN", "Infinity", "1e99", "0.81", "0", "-0.1", "0.0000000000000000001"])
def test_invalid_exact_shocks(value):
    with pytest.raises(ValueError):
        request_for(assumptions={"price_shocks": [{"market":m,"decline_fraction":value} for m in MARKETS]})

@pytest.mark.parametrize("changes", [
    {"selected_markets": ["BTC", "BTC"]}, {"selected_markets": ["DOGE"]}, {"scenario_type":"OTHER"},
    {"duration_frames":0}, {"duration_frames":1.5}, {"onset_frame":-1},
    {"assumptions":{"price_shocks":[{"market":"BTC","decline_fraction":"0.1"}]}},
    {"assumptions":{"price_shocks":[{"market":m,"decline_fraction":"0.1"} for m in MARKETS],"spread_multiplier":"2"}},
    {"assumptions":{"empirical_correlation_verified":True}},
])
def test_strict_scenario_contract(changes):
    raw = request_for().scenario.model_dump()
    raw.update(changes)
    with pytest.raises(ValueError): PortfolioStressScenario.model_validate(raw)

@pytest.mark.parametrize("assumptions", [
    {"btc_decline_fraction":"0.2","eth_transmission":"5","sol_transmission":"2"},
    {"btc_decline_fraction":"0.1","eth_transmission":"6","sol_transmission":"2"},
    {"btc_decline_fraction":"0.1","eth_transmission":"2","sol_transmission":"2","propagation_lag_frames":-1},
    {"btc_decline_fraction":"0.1","eth_transmission":"2","sol_transmission":"2","propagation_matrix":[]},
])
def test_invalid_transmission(assumptions):
    with pytest.raises(ValueError): request_for("BTC_LED_VOLATILITY",assumptions=assumptions)


def test_transmission_lag_and_linear_recovery():
    r = request_for("BTC_LED_VOLATILITY", duration=4, recovery="LINEAR_TO_BASELINE", assumptions={
        "btc_decline_fraction":"0.06","eth_transmission":"1.5","sol_transmission":"2","propagation_lag_frames":2})
    for s in r.config.scenarios:
        base = baseline_dataset(s)
        stressed = transform_dataset(base,s,r.scenario)
        onset = 4 if s.market == "BTC" else 6
        assert stressed.frames[:onset] == base.frames[:onset]
        expected = Decimal("0.94") if s.market == "BTC" else Decimal("0.91") if s.market == "ETH" else Decimal("0.88")
        assert abs(stressed.frames[onset].market.mid_price / base.frames[onset].market.mid_price - expected) < Decimal("0.0001")
        assert stressed.frames[onset+3] == base.frames[onset+3]

@pytest.mark.parametrize("mode", ["MISSING","DIVERGENT"])
def test_oracle_native_conventions(mode):
    assumptions = {"reference_mode":mode,"reference_source":"redstone"}
    if mode == "DIVERGENT": assumptions["reference_divergence_fraction"] = "0.015"
    r = request_for("ORACLE_DEGRADATION",assumptions=assumptions)
    s = r.config.scenarios[0]
    base = baseline_dataset(s)
    value = transform_dataset(base,s,r.scenario).frames[4].reference_prices.redstone
    assert (value is None) if mode == "MISSING" else value > base.frames[4].reference_prices.redstone


def test_stale_references_and_missing_divergence_rejected():
    with pytest.raises(ValueError): request_for("ORACLE_DEGRADATION",assumptions={"reference_mode":"STALE","reference_source":"redstone"})
    r = request_for("ORACLE_DEGRADATION",scenario="REFERENCE_DEGRADATION", assumptions={
        "reference_mode":"DIVERGENT","reference_source":"redstone","reference_divergence_fraction":"0.015"})
    s = r.config.scenarios[0]
    with pytest.raises(ValueError): transform_dataset(baseline_dataset(s),s,r.scenario)

@pytest.mark.parametrize("field", ["price","size"])
def test_forged_precision_is_revalidated(field):
    r=request_for();s=r.config.scenarios[0];base=baseline_dataset(s)
    forged=base.model_copy(deep=True)
    setattr(forged.frames[0].market.book.bids[0], field, Decimal("0.000000001"))
    with pytest.raises(ValueError): validate_dataset(forged,s)

@pytest.mark.parametrize("bound", ["frames","quotes","trace","ledger","events"])
def test_both_legs_count_toward_resource_limits(bound):
    kwargs = {"frames":501} if bound == "frames" else {}
    overrides={m:{"simulation":{}} for m in MARKETS}
    if bound == "quotes":
        kwargs["frames"]=100
        for m in MARKETS: overrides[m]["strategy"]={"levels_per_side":50}
    elif bound == "trace":
        kwargs["frames"]=251
        for m in MARKETS: overrides[m]["simulation"]["trace_max_points"]=251
    elif bound in {"ledger","events"}:
        for m in MARKETS: overrides[m]["simulation"]["accounting"]={"ledger_max_entries":5001 if bound=="ledger" else 5000,"event_max_entries":126 if bound=="events" else 125}
    with pytest.raises(ValueError): request_for(overrides=overrides,**kwargs)


def test_out_of_window_unselected_and_funding_disabled_rejected():
    with pytest.raises(ValueError): request_for(duration=20)
    with pytest.raises(ValueError): request_for(markets=("BTC",),selected=("ETH",))
    with pytest.raises(ValueError): request_for("FUNDING_STRESS",overrides={"BTC":{"simulation":{"accounting":{"paper_funding_accounting_enabled":False}}}})


def test_input_order_and_decimal_equivalence_canonical():
    a=request_for(markets=MARKETS)
    b=request_for(markets=tuple(reversed(MARKETS)))
    assert a==b and a.scenario.fingerprint()==b.scenario.fingerprint()
    raw=a.model_dump(); raw["scenario"]["assumptions"]["price_shocks"][0]["decline_fraction"]=Decimal(".06000")
    assert PortfolioStressRequest.model_validate(raw)==a


def test_transmission_bound_is_exact_at_decimal_edge():
    from decimal import localcontext
    raw=request_for("BTC_LED_VOLATILITY",markets=("ETH",)).scenario.model_dump()
    raw["assumptions"].update(btc_decline_fraction="0.4",eth_transmission="2.000000000000000001")
    # Exact bounds must survive a caller context that would round this to .8.
    with localcontext() as ctx:
        ctx.prec=10
        with pytest.raises(ValueError,match="transmitted decline"):
            PortfolioStressScenario.model_validate(raw)


def test_concentration_tie_selection_uses_canonical_market_order():
    from datetime import datetime,timezone
    from app.portfolio_research.models import ConcentrationSelection,NativeAccountingObservation
    from app.portfolio_research.stress import concentration_target
    point=NativeAccountingObservation(sequence=1,timestamp=datetime(2026,1,1,tzinfo=timezone.utc),
        equity_quote="1",session_pnl_quote="0",position_base="1",mark_price_quote="1")
    selection=ConcentrationSelection(market="BTC",sequence=1,candidates=(point,point,point),
        candidate_markets=("BTC","ETH","SOL"),native_evidence_fingerprints=("a"*64,)*3)
    assert concentration_target(selection)=="BTC"


@pytest.mark.parametrize("onset,duration,recovery",[(0,1,"STEP_WINDOW"),(4,2,"LINEAR_TO_BASELINE")])
def test_funding_requires_nonzero_stress_at_a_native_accrual_boundary(onset,duration,recovery):
    with pytest.raises(ValueError,match="observed funding boundary"):
        request_for("FUNDING_STRESS",markets=("BTC",),onset=onset,duration=duration,recovery=recovery,
            overrides={"BTC":{"simulation":{"accounting":{"paper_funding_interval_seconds":5}}}})
