from decimal import Decimal

import pytest

from app.portfolio_research.models import PortfolioRiskPolicy
from app.portfolio_research.risk import evaluate_risk
from phase173_fixtures import native173, reseal


def inputs(native173):
    p, _, _, r = native173
    dd = reseal(r.accounting.drawdown, peak_equity_quote=Decimal("100000"),
                ending_drawdown_fraction=Decimal("0"), max_drawdown_fraction=Decimal("0"))
    a = reseal(r.accounting, equity_quote=Decimal("100000"), pnl_quote=Decimal("0"),
               session_loss_quote=Decimal("0"), drawdown=dd)
    x = reseal(r.exposure, accounting_fingerprint=a.evidence_fingerprint,
        gross_exposure_quote=Decimal("0"), net_exposure_quote=Decimal("0"),
        max_inventory_concentration=Decimal("0"), modeled_leverage=Decimal("0"),
        reserved_capital_utilization=Decimal("0"), gross_notional_utilization=Decimal("0"))
    return p, a, x, r.temporal


@pytest.mark.parametrize("observed,expected", [("0", "NORMAL"), ("79999.999999999999999999", "NORMAL"),
    ("80000", "WARN"), ("94999.999999999999999999", "WARN"), ("95000", "REDUCE"),
    ("99999.999999999999999999", "REDUCE"), ("100000", "HALT"), ("100001", "HALT")])
def test_threshold_ordering_and_inclusive_boundaries(native173, observed, expected):
    p, a, x, t = inputs(native173)
    x = reseal(x, gross_exposure_quote=Decimal(observed))
    r = evaluate_risk(p, a, x, t, PortfolioRiskPolicy())
    assert r.outcome == "ASSESSED" and r.decision == expected
    assert r.checks[0].observed == Decimal(observed)
    assert r.risk_compliant == (expected in {"NORMAL", "WARN"})


@pytest.mark.parametrize("limit,field,value", [
    ("max_gross_exposure_quote", "gross_exposure_quote", "100001"),
    ("max_abs_net_exposure_quote", "net_exposure_quote", "-100001"),
    ("max_inventory_concentration", "max_inventory_concentration", ".76"),
    ("max_capital_utilization", "reserved_capital_utilization", "1.01"),
    ("modeled_leverage_ceiling", "modeled_leverage", "3.01"),
    ("max_session_loss_quote", "session_loss_quote", "10001"),
    ("max_drawdown_fraction", "max_drawdown_fraction", ".21")])
def test_every_limit_has_a_deterministic_hard_breach(native173, limit, field, value):
    p, a, x, t = inputs(native173)
    if field == "session_loss_quote": a = reseal(a, **{field: Decimal(value)})
    elif field == "max_drawdown_fraction": a = reseal(a, drawdown=reseal(a.drawdown, **{field: Decimal(value)}))
    else: x = reseal(x, **{field: Decimal(value)})
    x = reseal(x, accounting_fingerprint=a.evidence_fingerprint)
    r = evaluate_risk(p, a, x, t, PortfolioRiskPolicy())
    assert r.decision == "HALT"
    assert f"{limit}:HALT" in r.reasons
    assert not r.risk_compliant and r.operational_authority == "NONE"
    assert r.historical_orders_prevented is False


def test_multiple_breaches_have_stable_priority_and_order(native173):
    p, a, x, t = inputs(native173)
    x = reseal(x, gross_exposure_quote=Decimal("100001"), net_exposure_quote=Decimal("-100001"), modeled_leverage=Decimal("4"))
    a = reseal(a, session_loss_quote=Decimal("10001"))
    x = reseal(x, accounting_fingerprint=a.evidence_fingerprint)
    r = evaluate_risk(p, a, x, t, PortfolioRiskPolicy())
    assert r.reasons == ("max_gross_exposure_quote:HALT", "max_abs_net_exposure_quote:HALT",
                         "modeled_leverage_ceiling:HALT", "max_session_loss_quote:HALT")
    assert evaluate_risk(p, a, x, t, PortfolioRiskPolicy()) == r


@pytest.mark.parametrize("field", ["modeled_leverage", "reserved_capital_utilization", "gross_exposure_quote"])
def test_missing_metric_never_maps_to_normal(native173, field):
    p, a, x, t = inputs(native173)
    x = reseal(x, **{field: None})
    r = evaluate_risk(p, a, x, t, PortfolioRiskPolicy())
    assert r.outcome == "BLOCKED" and r.decision is None and not r.risk_compliant


def test_missing_drawdown_never_overrides_known_halt_or_produces_normal(native173):
    p, a, x, t = inputs(native173)
    a = reseal(a, drawdown=None)
    x = reseal(x, accounting_fingerprint=a.evidence_fingerprint)
    assert evaluate_risk(p, a, x, t, PortfolioRiskPolicy()).decision is None
    x = reseal(x, gross_exposure_quote=Decimal("100001"))
    r = evaluate_risk(p, a, x, t, PortfolioRiskPolicy())
    assert r.outcome == "BLOCKED" and r.decision == "HALT" and not r.risk_compliant


@pytest.mark.parametrize("warning,reduction", [(".95", ".8"), (".8", ".8"), ("0", ".95"),
    (".8", "1"), ("NaN", ".95"), (0.8, ".95"), (True, ".95")])
def test_invalid_threshold_policy_rejected(warning, reduction):
    with pytest.raises(ValueError): PortfolioRiskPolicy(warning_ratio=warning, reduction_ratio=reduction)


def test_policy_changes_risk_identity_without_changing_old_config(native173):
    p, a, x, t = inputs(native173)
    before = p.fingerprint()
    r = evaluate_risk(p, a, x, t, PortfolioRiskPolicy())
    changed = evaluate_risk(p, a, x, t, PortfolioRiskPolicy(warning_ratio="0.7"))
    assert changed.evidence_fingerprint != r.evidence_fingerprint
    assert changed.risk_configuration_fingerprint != r.risk_configuration_fingerprint
    assert p.fingerprint() == before


def test_zero_drawdown_ceiling_treats_only_positive_loss_as_breach(native173):
    p, a, x, t = inputs(native173)
    from app.portfolio_research.models import PortfolioResearchConfig
    raw = p.model_dump()
    raw["risk_limits"]["max_drawdown_fraction"] = "0"
    p = PortfolioResearchConfig.model_validate(raw)
    a = reseal(a, config_fingerprint=p.fingerprint())
    x = reseal(x, accounting_fingerprint=a.evidence_fingerprint)
    assert evaluate_risk(p, a, x, t, PortfolioRiskPolicy()).decision == "NORMAL"
    a = reseal(a, drawdown=reseal(a.drawdown, max_drawdown_fraction=Decimal(".000001")))
    x = reseal(x, accounting_fingerprint=a.evidence_fingerprint)
    assert evaluate_risk(p, a, x, t, PortfolioRiskPolicy()).decision == "HALT"
