"""Eligibility-gated comparisons of existing native portfolio projections."""
from decimal import Decimal, localcontext

from .models import (PortfolioStressMetrics, PortfolioStressRiskTransition, StressMetricComparison)


def comparison_classification(baseline, stressed):
    if "UNAVAILABLE" in {baseline.temporal.classification, stressed.temporal.classification}:
        return "UNAVAILABLE"
    if "INCOMPARABLE" in {baseline.temporal.classification, stressed.temporal.classification}:
        return "INCOMPARABLE"
    def clocks(result):
        return tuple((c.market, c.clock, c.engine_version, c.scenario, c.frames, c.start_at, c.final_at)
                     for c in result.temporal.clocks)
    if (baseline.execution.config_fingerprint != stressed.execution.config_fingerprint or
            baseline.risk.policy != stressed.risk.policy or clocks(baseline) != clocks(stressed)):
        return "INCOMPARABLE"
    return "MODELED_ALIGNED" if all(r.temporal.classification == "MODELED_ALIGNED" for r in (baseline, stressed)) else "FINAL_ONLY"


def compare_metrics(baseline, stressed):
    classification = comparison_classification(baseline, stressed)
    supported = classification in {"MODELED_ALIGNED", "FINAL_ONLY"}
    with localcontext() as ctx:
        ctx.prec = 80
        values = []
        fields = (("accounting", ("equity_quote", "pnl_quote", "capital_allocation_utilization")),
                  ("exposure", ("gross_exposure_quote", "net_exposure_quote", "max_inventory_concentration",
                                "reserved_capital_utilization", "modeled_leverage", "gross_notional_utilization")))
        for domain, names in fields:
            for name in names:
                values.append((name, getattr(getattr(baseline, domain), name), getattr(getattr(stressed, domain), name)))
        values.append(("funding_quote", *(sum((c.funding_quote for c in r.accounting.contributions), Decimal(0))
                                            if r.accounting.status == "SUPPORTED" else None for r in (baseline, stressed))))
        values.append(("max_drawdown_fraction", *(r.accounting.drawdown.max_drawdown_fraction
                      if classification == "MODELED_ALIGNED" and r.accounting.drawdown else None for r in (baseline, stressed))))
        return PortfolioStressMetrics(temporal_classification=classification, comparisons=tuple(
            StressMetricComparison(metric=name, baseline=b, stressed=s,
                difference=s-b if supported and b is not None and s is not None else None,
                status="COMPARABLE" if supported and b is not None and s is not None else "UNAVAILABLE")
            for name, b, s in values))


def compare_risk(baseline, stressed):
    b, s = baseline.risk, stressed.risk
    assessed = (comparison_classification(baseline, stressed) in {"MODELED_ALIGNED", "FINAL_ONLY"}
                and b.outcome == s.outcome == "ASSESSED" and b.decision is not None and s.decision is not None)
    return PortfolioStressRiskTransition(baseline_outcome=b.outcome, stressed_outcome=s.outcome,
        baseline_decision=b.decision, stressed_decision=s.decision,
        status="ASSESSED" if assessed else "BLOCKED",
        transition=f"{b.decision} -> {s.decision}" if assessed else None)
