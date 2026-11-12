from types import SimpleNamespace as NS
from decimal import localcontext

import pytest

from app.portfolio_research.metrics import compare_metrics,compare_risk
from phase174_fixtures import selloff174
from phase173_fixtures import reseal


def test_signed_comparisons_are_native_differences(selloff174):
    with localcontext() as ctx:
        ctx.prec = 80
        for c in selloff174.metrics.comparisons:
            assert c.status=="COMPARABLE"
            assert c.difference==c.stressed-c.baseline
    equity=next(c for c in selloff174.metrics.comparisons if c.metric=="equity_quote")
    pnl=next(c for c in selloff174.metrics.comparisons if c.metric=="pnl_quote")
    assert equity.difference==pnl.difference

@pytest.mark.parametrize("pair",[("NORMAL","WARN"),("WARN","REDUCE"),("REDUCE","HALT"),("NORMAL","HALT"),("HALT","NORMAL")])
def test_transition_semantics_use_native_reports(selloff174,pair):
    b,s=selloff174.baseline,selloff174.stressed
    # The comparator consumes reports; risk thresholds remain owned by risk.py.
    b=NS(execution=b.execution,temporal=b.temporal,risk=NS(policy=b.risk.policy,outcome="ASSESSED",decision=pair[0]))
    s=NS(execution=s.execution,temporal=s.temporal,risk=NS(policy=s.risk.policy,outcome="ASSESSED",decision=pair[1]))
    transition=compare_risk(b,s)
    assert transition.transition==f"{pair[0]} -> {pair[1]}"
    assert transition.operational_authority=="NONE" and not transition.historical_orders_prevented

@pytest.mark.parametrize("classification",["UNAVAILABLE","INCOMPARABLE"])
def test_ineligible_temporal_comparisons_have_no_deltas(selloff174,classification):
    b,s=selloff174.baseline,selloff174.stressed
    s=NS(execution=s.execution,temporal=NS(classification=classification),risk=s.risk,accounting=s.accounting,exposure=s.exposure)
    result=compare_metrics(b,s)
    assert result.temporal_classification==classification
    assert all(c.difference is None and c.status=="UNAVAILABLE" for c in result.comparisons)
    assert compare_risk(b,s).status=="BLOCKED"


def test_risk_changes_recomputed_from_native_accounting(selloff174):
    from app.portfolio_research.risk import evaluate_risk
    for leg in (selloff174.baseline,selloff174.stressed):
        assert evaluate_risk(leg.execution.config,leg.accounting,leg.exposure,leg.temporal,leg.risk.policy)==leg.risk
    assert selloff174.baseline.risk.decision != selloff174.stressed.risk.decision
