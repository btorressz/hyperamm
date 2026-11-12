"""Post-execution research assessment with no operational authority."""
from decimal import localcontext

from app.simulation.models import stable_fingerprint
from .models import (PortfolioRiskPolicy, PortfolioRiskCheck, PortfolioRiskReport,
    PortfolioResearchConfig, PortfolioAccountingReport, PortfolioExposureReport, PortfolioTemporalReport, sealed)

STATES = ("NORMAL", "WARN", "REDUCE", "HALT")


def evaluate_risk(config, accounting, exposure, temporal, policy):
    config = PortfolioResearchConfig.model_validate(config)
    accounting = PortfolioAccountingReport.model_validate(accounting)
    exposure = PortfolioExposureReport.model_validate(exposure)
    temporal = PortfolioTemporalReport.model_validate(temporal)
    policy = PortfolioRiskPolicy.model_validate(policy)
    limits = config.risk_limits
    observations = (
        ("max_gross_exposure_quote", exposure.gross_exposure_quote),
        ("max_abs_net_exposure_quote", abs(exposure.net_exposure_quote) if exposure.net_exposure_quote is not None else None),
        ("max_inventory_concentration", exposure.max_inventory_concentration),
        ("max_capital_utilization", exposure.reserved_capital_utilization),
        ("modeled_leverage_ceiling", exposure.modeled_leverage),
        ("max_session_loss_quote", accounting.session_loss_quote),
        ("max_drawdown_fraction", accounting.drawdown.max_drawdown_fraction if accounting.drawdown else None),
    )
    checks = []
    with localcontext() as ctx:
        ctx.prec = 80
        for name, observed in observations:
            ceiling = getattr(limits, name)
            if observed is None:
                state = "UNAVAILABLE"
            elif observed > ceiling:
                state = "HALT"
            elif ceiling == 0:
                state = "NORMAL"  # A zero loss/drawdown is not a positive breach.
            elif observed >= ceiling * policy.reduction_ratio:
                state = "REDUCE"
            elif observed >= ceiling * policy.warning_ratio:
                state = "WARN"
            else:
                state = "NORMAL"
            # The hard boundary itself is inclusive for positive limits.
            if observed is not None and ceiling > 0 and observed >= ceiling:
                state = "HALT"
            checks.append(PortfolioRiskCheck(limit=name, observed=observed, ceiling=ceiling, state=state))
    blocked = (accounting.status != "SUPPORTED" or temporal.classification != "MODELED_ALIGNED" or
               any(c.state == "UNAVAILABLE" for c in checks))
    known = max((c.state for c in checks if c.state != "UNAVAILABLE"), key=STATES.index, default="NORMAL")
    # A known hard breach remains visible even when another critical metric is
    # missing. Incomplete evidence can never produce an unconditional NORMAL.
    decision = "HALT" if known == "HALT" else None if blocked else known
    reasons = tuple(f"{c.limit}:{c.state}" for c in checks if c.state != "NORMAL")
    if blocked:
        reasons += ("CRITICAL_EVIDENCE_OR_TEMPORAL_ELIGIBILITY_UNAVAILABLE",)
    return sealed(PortfolioRiskReport, config_fingerprint=config.fingerprint(),
        risk_configuration_fingerprint=stable_fingerprint({"limits": limits, "policy": policy}),
        accounting_fingerprint=accounting.evidence_fingerprint,
        exposure_fingerprint=exposure.evidence_fingerprint, temporal_fingerprint=temporal.evidence_fingerprint,
        policy=policy, outcome="BLOCKED" if blocked else "ASSESSED", decision=decision,
        checks=tuple(checks), reasons=reasons or ("ALL_REQUIRED_LIMITS_BELOW_WARNING",),
        risk_compliant=not blocked and decision in {"NORMAL", "WARN"})
