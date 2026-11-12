from decimal import Decimal, localcontext
from itertools import combinations

import pytest

from app.portfolio_research.models import PortfolioStressResult
from app.portfolio_research.orchestration import execute_markets
from app.portfolio_research.scenarios import baseline_dataset, transform_dataset
from app.simulation.service import SimulationService
from phase174_fixtures import request_for, native174, selloff174


def test_all_six_execute_native_accounting_and_roundtrip(native174):
    r = native174
    assert PortfolioStressResult.model_validate_json(r.model_dump_json()) == r
    assert r.metrics.temporal_classification == "MODELED_ALIGNED"
    assert r.baseline.accounting.drawdown and r.stressed.accounting.drawdown
    assert r.risk_transition.status == "ASSESSED"
    for leg in (r.baseline, r.stressed):
        with localcontext() as ctx:
            ctx.prec = 80
            assert leg.accounting.equity_quote == leg.execution.unallocated_reserve_quote + sum(c.equity_quote for c in leg.accounting.contributions)
            assert leg.accounting.pnl_quote == leg.accounting.equity_quote - leg.execution.config.budget.total_equity_quote
        for receipt in leg.execution.markets:
            assert receipt.market == receipt.vault.market == receipt.market_assumptions.market
            assert receipt.vault.net_pnl_quote == receipt.metrics.session_pnl
    assert any(m.baseline_dataset_fingerprint != m.stressed_dataset_fingerprint for m in r.markets)


async def test_actual_engine_consumes_transformed_dataset_and_same_baseline(monkeypatch,selloff174):
    service=SimulationService();original=service.engine.run;calls=[]
    async def observe(**kwargs):
        calls.append(kwargs["dataset"])
        return await original(**kwargs)
    monkeypatch.setattr(service.engine,"run",observe)
    r=await service.stress_portfolio_research(request=selloff174.request)
    assert len(calls)==6
    assert r==selloff174
    for index,s in enumerate(r.request.config.scenarios):
        base=baseline_dataset(s)
        stress=transform_dataset(base,s,r.request.scenario)
        assert calls[index]==base and calls[index+3]==stress
    standalone=await service.analyze_portfolio_research(request={
        "config":r.request.config,"config_fingerprint":r.request.config_fingerprint,"risk_policy":r.request.risk_policy})
    assert standalone==r.baseline

@pytest.mark.parametrize("markets",[c for n in (1,2,3) for c in combinations(("BTC","ETH","SOL"),n)])
async def test_native_each_portfolio_selection(markets):
    result=await SimulationService().stress_portfolio_research(request=request_for(markets=markets))
    assert tuple(m.market for m in result.markets)==markets
    assert result.metrics.temporal_classification=="MODELED_ALIGNED"

@pytest.mark.parametrize("direction",["0.001","-0.001"])
async def test_native_funding_and_fees_reconcile_without_double_deduction(direction):
    r=await SimulationService().stress_portfolio_research(request=request_for("FUNDING_STRESS",assumptions={
        "funding_shocks":[{"market":m,"adjustment":direction} for m in ("BTC","ETH","SOL")]},
        overrides={m:{"simulation":{"accounting":{"paper_fee_model_enabled":True}}} for m in ("BTC","ETH","SOL")}))
    for leg in (r.baseline,r.stressed):
        for c in leg.accounting.contributions:
            assert c.net_pnl_quote == (c.realized_pnl_quote-c.fees_quote+c.funding_quote)+c.unrealized_pnl_quote
    funding=next(c for c in r.metrics.comparisons if c.metric=="funding_quote")
    assert funding.stressed != funding.baseline
    pnl=next(c for c in r.metrics.comparisons if c.metric=="pnl_quote")
    # Funding can change later native quotes/fills through existing risk policy.
    # Aggregate the already-net native PnL; never subtract funding again.
    with localcontext() as ctx:
        ctx.prec = 80
        native_delta = sum(c.net_pnl_quote for c in r.stressed.accounting.contributions) - sum(c.net_pnl_quote for c in r.baseline.accounting.contributions)
        residual_delta = r.stressed.accounting.native_rounding_residual_quote - r.baseline.accounting.native_rounding_residual_quote
        assert pnl.difference == native_delta + residual_delta


async def test_concentration_prefix_existing_inventory_and_targeted_shock(monkeypatch):
    service=SimulationService();original=service.engine.run;native=[]
    async def observe(**kwargs):
        value=await original(**kwargs);native.append((kwargs["dataset"],value));return value
    monkeypatch.setattr(service.engine,"run",observe)
    r=await service.stress_portfolio_research(request=request_for("CONCENTRATION_STRESS",onset=7))
    sel=r.concentration_selection
    assert sel is not None
    expected=min(zip(sel.candidate_markets,sel.candidates),key=lambda v:(-abs(v[1].position_base*v[1].mark_price_quote),("BTC","ETH","SOL").index(v[0])))[0]
    assert sel.market==expected
    for (b,br),(s,sr) in zip(native[:3],native[3:]):
        assert br.trace[:7]==sr.trace[:7]
        assert b.frames[:7]==s.frames[:7]
        assert (b.fingerprint!=s.fingerprint)==(b.market==sel.market)
    assert r.baseline.execution.config==r.stressed.execution.config
    assert r.baseline.accounting.initial_capital_quote==r.stressed.accounting.initial_capital_quote


async def test_no_concentration_position_is_unavailable_instead_of_success():
    with pytest.raises(ValueError,match="no nonzero"):
        await SimulationService().stress_portfolio_research(request=request_for("CONCENTRATION_STRESS",onset=1))


async def test_incomplete_history_keeps_final_comparison_and_blocks_risk():
    r=await SimulationService().stress_portfolio_research(request=request_for(overrides={
        "ETH":{"simulation":{"trace_max_points":3}}}))
    assert r.metrics.temporal_classification=="FINAL_ONLY"
    assert r.risk_transition.status=="BLOCKED" and r.risk_transition.transition is None
    assert all(leg.accounting.drawdown is None for leg in (r.baseline,r.stressed))
    assert next(c for c in r.metrics.comparisons if c.metric=="equity_quote").status=="COMPARABLE"
    assert next(c for c in r.metrics.comparisons if c.metric=="max_drawdown_fraction").difference is None

@pytest.mark.parametrize("corruption",["missing","timestamp","sequence"])
async def test_native_substituted_frames_fail_closed(monkeypatch,corruption):
    from app.research_replay.comparison import ScenarioProvenanceReceipt
    original=SimulationService._run_portfolio_dataset
    async def corrupt(self,**kwargs):
        value=await original(self,**kwargs)
        if kwargs["scenario"].market=="ETH":
            if corruption=="missing": value.result.trace.pop(0)
            elif corruption=="sequence": value.result.trace[0].sequence+=1
            else:
                from datetime import timedelta
                value.result.trace[0].timestamp+=timedelta(seconds=1)
            value=value.model_copy(update={"provenance":ScenarioProvenanceReceipt.bind(result=value.result,
                captured=value.provenance.captured,scenario=value.provenance.requested_scenario,frames=value.provenance.requested_frames)})
        return value
    monkeypatch.setattr(SimulationService,"_run_portfolio_dataset",corrupt)
    r=await SimulationService().stress_portfolio_research(request=request_for())
    assert r.metrics.temporal_classification=="UNAVAILABLE"
    assert r.risk_transition.status=="BLOCKED"
    assert all(m.difference is None for m in r.metrics.comparisons)


async def test_ambient_precision_does_not_change_native_stress_identity():
    r=request_for(markets=("BTC",))
    first=await SimulationService().stress_portfolio_research(request=r)
    with localcontext() as ctx:
        ctx.prec=70
        ctx.rounding="ROUND_DOWN"
        second=await SimulationService().stress_portfolio_research(request=r)
        assert second==first
        assert PortfolioStressResult.model_validate_json(first.model_dump_json())==first


async def test_concentration_is_largest_in_whole_portfolio_not_arbitrary_selected_market():
    with pytest.raises(ValueError,match="outside the selected"):
        await SimulationService().stress_portfolio_research(request=request_for(
            "CONCENTRATION_STRESS",onset=7,selected=("BTC",)))


@pytest.mark.parametrize("mode",["MISSING","DIVERGENT"])
async def test_oracle_quality_and_risk_use_native_fallback(monkeypatch,mode):
    service=SimulationService();original=service.engine.run;outputs=[]
    async def observe(**kwargs):
        value=await original(**kwargs);outputs.append(value);return value
    monkeypatch.setattr(service.engine,"run",observe)
    a={"reference_mode":mode,"reference_source":"redstone"}
    if mode=="DIVERGENT":a["reference_divergence_fraction"]="0.015"
    r=await service.stress_portfolio_research(request=request_for("ORACLE_DEGRADATION",markets=("BTC",),assumptions=a))
    baseline,stressed=outputs
    assert baseline.trace[:4]==stressed.trace[:4]
    assert all(p.reference_confidence=="VERIFIED" for p in baseline.trace)
    assert all(p.reference_confidence=="DEGRADED" for p in stressed.trace[4:])
    assert r.stressed.execution.markets[0].metrics.risk_state_counts==stressed.metrics.risk_state_counts
    assert all(p.risk_state in {"WARN","REDUCE","HALT"} for p in stressed.trace[4:])


async def test_concentration_native_short_receives_adverse_price_rise():
    r=await SimulationService().stress_portfolio_research(request=request_for(
        "CONCENTRATION_STRESS",markets=("BTC",),scenario="HIGH_VOLATILITY",onset=2))
    selection=r.concentration_selection
    assert selection.candidates[0].position_base<0
    assert r.stressed.execution.markets[0].vault.mark_price>r.baseline.execution.markets[0].vault.mark_price


async def test_liquidity_shock_uses_captured_native_latency_depth_and_slippage():
    from app.execution.research import PaperExecutionAssumptions
    controls=PaperExecutionAssumptions(mode="MODELED_CROSSING",order_latency_ms=1000,cancel_latency_ms=2000,
        slippage_bps="1",depth_sensitive=True,participation_rate="0.25")
    r=await SimulationService().stress_portfolio_research(request=request_for("LIQUIDITY_SHOCK",markets=("BTC",),
        overrides={"BTC":{"simulation":{"execution":controls.model_dump(mode="json")}}}))
    b,s=r.baseline.execution.markets[0],r.stressed.execution.markets[0]
    assert b.execution_assumptions==s.execution_assumptions==controls
    assert s.market_assumptions.bid_depth_base<b.market_assumptions.bid_depth_base
    assert s.market_assumptions.spread_quote>b.market_assumptions.spread_quote
    assert s.metrics.filled_notional!=b.metrics.filled_notional
