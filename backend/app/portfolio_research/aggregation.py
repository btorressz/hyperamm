"""Bounded 17.2 execution bundles and versioned native portfolio analysis."""
from app.simulation.models import stable_fingerprint
from app.execution.research import PaperExecutionAssumptions
from .config import MAX_RESPONSE_BYTES, PortfolioResponseTooLarge
from .models import (
    PortfolioMarketExecution, PortfolioMarketReceipt, PortfolioExecutedResult,
    fingerprinted,
)


def project_market(execution: PortfolioMarketExecution) -> PortfolioMarketReceipt:
    execution = PortfolioMarketExecution.model_validate(execution)
    result = execution.captured_result.result
    return fingerprinted(PortfolioMarketReceipt,
        config_fingerprint=execution.config_fingerprint, market=execution.scenario.market,
        provenance=execution.captured_result.provenance, metrics=result.metrics,
        vault=result.vault, market_assumptions=result.research_assumptions,
        execution_assumptions=PaperExecutionAssumptions.model_validate(result.execution_assumptions),
        accounting_fingerprint=result.accounting_fingerprint,
        retained_ledger_fingerprint=stable_fingerprint(result.accounting_ledger),
        retained_ledger_entries=len(result.accounting_ledger), original_trace_points=len(result.trace))


def assemble_bundle(config, markets) -> PortfolioExecutedResult:
    bundle = fingerprinted(PortfolioExecutedResult,
        config=config, config_fingerprint=config.fingerprint(),
        selected_markets=tuple(r.market for r in markets), markets=tuple(markets),
        unallocated_reserve_quote=config.unallocated_reserve_quote)
    # Serialize in the worker too: failures/oversize cannot escape as a successful
    # admitted computation or be mirrored as completed by Redis coordination.
    bounded_json(bundle)
    return bundle


def bounded_json(bundle) -> str:
    wire = bundle.model_dump_json()
    if len(wire.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise PortfolioResponseTooLarge("portfolio response exceeds transport budget")
    return wire


def assemble_analysis(config, markets, evidence, policy):
    from decimal import localcontext
    # Native nested contracts contain arithmetic checks at engine precision.
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = "ROUND_HALF_EVEN"
        return _assemble_analysis(config, markets, evidence, policy)


def _assemble_analysis(config, markets, evidence, policy):
    from .accounting import reconcile_accounting, portfolio_drawdown
    from .exposure import calculate_exposure
    from .risk import evaluate_risk
    from .temporal import evaluate_temporal
    from .models import PortfolioAnalysisResult, sealed
    execution = assemble_bundle(config, markets)
    temporal = evaluate_temporal(markets, evidence)
    drawdown = portfolio_drawdown(config, temporal, evidence)
    accounting = reconcile_accounting(config, markets, temporal, drawdown_evidence=drawdown)
    exposure = calculate_exposure(markets, accounting, temporal)
    risk = evaluate_risk(config, accounting, exposure, temporal, policy)
    result = sealed(PortfolioAnalysisResult, execution=execution, temporal=temporal,
        accounting=accounting, exposure=exposure, risk=risk)
    bounded_json(result)
    return result


def verify_analysis(result):
    """Revalidate wire projections and recomputable economics/risk decisions.

    The native curve is deliberately omitted. Its digest/count and drawdown
    summary remain same-job bindings, as do 17.2's omitted full-result hashes.
    """
    from datetime import timedelta
    from app.simulation.scenarios import DEFAULT_START
    from app.accounting.pnl import drawdown
    from decimal import localcontext
    from .accounting import reconcile_accounting
    from .exposure import calculate_exposure
    from .risk import evaluate_risk
    from .temporal import classify_clocks
    from .models import ANALYSIS_LIMITATIONS
    from .config import portfolio_ratio
    e, t, a, x, r = result.execution, result.temporal, result.accounting, result.exposure, result.risk
    if result.limitations != ANALYSIS_LIMITATIONS or len(t.clocks) != len(e.markets):
        raise ValueError("portfolio analysis limitations or market set mismatch")
    for clock, market in zip(t.clocks, e.markets):
        sim = market.provenance.captured.inputs().simulation
        n = market.metrics.frame_count
        expected = min(n, sim.trace_max_points) if sim.record_trace else 0
        if (clock.market != market.market or clock.market_receipt_fingerprint != market.receipt_fingerprint or
                clock.frames != n or clock.scenario != market.provenance.requested_scenario or
                clock.engine_version != market.provenance.engine_version or
                clock.expected_retained != expected or clock.start_at != DEFAULT_START or
                clock.final_at != market.market_assumptions.representative_frame_timestamp or
                clock.complete != (clock.valid and clock.retained == n) or
                (clock.valid and (clock.retained != expected or clock.final_at != DEFAULT_START + timedelta(seconds=n - 1)))):
            raise ValueError("portfolio analysis clock binding mismatch")
    if classify_clocks(t.clocks) != t:
        raise ValueError("portfolio temporal classification mismatch")
    expected_accounting = reconcile_accounting(e.config, e.markets, t, drawdown_evidence=a.drawdown)
    if a != expected_accounting:
        raise ValueError("portfolio accounting projection mismatch")
    if a.drawdown is not None:
        with localcontext() as ctx:
            ctx.prec = 50
            peak = a.drawdown.peak_equity_quote
            if peak < max(a.initial_capital_quote, a.equity_quote) or portfolio_ratio(drawdown(a.equity_quote, peak)[0], peak) != a.drawdown.ending_drawdown_fraction:
                raise ValueError("portfolio drawdown ending state mismatch")
    if calculate_exposure(e.markets, a, t) != x or evaluate_risk(e.config, a, x, t, r.policy) != r:
        raise ValueError("portfolio exposure or risk projection mismatch")


def assemble_stress(request, baseline, stressed, selection):
    from .models import PortfolioStressResult, sealed
    from .stress import market_bindings
    from .metrics import compare_metrics, compare_risk
    result = sealed(PortfolioStressResult, request=request,
        request_fingerprint=stable_fingerprint(request), scenario_fingerprint=request.scenario.fingerprint(),
        baseline=baseline, stressed=stressed, markets=market_bindings(baseline, stressed),
        concentration_selection=selection, metrics=compare_metrics(baseline, stressed),
        risk_transition=compare_risk(baseline, stressed))
    bounded_json(result)
    return result
