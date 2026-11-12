"""Native boundary cases and adversaries for the Phase 17.3 research layer."""
from copy import deepcopy
import asyncio
from decimal import Decimal, localcontext

import pytest

from app.portfolio_research.aggregation import assemble_analysis
from app.portfolio_research.models import (
    PortfolioAnalysisResult,
    PortfolioResearchConfig, PortfolioRiskPolicy,
)
from app.portfolio_research.provenance import capture_portfolio_provenance
from app.portfolio_research.risk import evaluate_risk
from app.portfolio_research.temporal import evaluate_temporal
from app.simulation.models import stable_fingerprint
from phase172_fixtures import portfolio
from phase173_fixtures import native173, native, request_for, reseal
from test_phase173_risk import inputs
from test_phase14_research_vault import authority, research_client


@pytest.mark.parametrize("frames,retained,levels,classification", [
    (500, 500, 8, "MODELED_ALIGNED"),
    (501, 500, 8, "FINAL_ONLY"),
    (1000, 500, 8, "FINAL_ONLY"),
    (160, 160, 50, "MODELED_ALIGNED"),
])
async def test_native_history_and_quote_work_boundaries(frames, retained, levels, classification):
    overrides = {m: {"simulation": {"trace_max_points": retained},
        "strategy": {"levels_per_side": levels, "total_liquidity": str(size)}}
        for m, size in (("BTC", 1), ("ETH", 20), ("SOL", 400))}
    p, receipts, evidence, result = await native(portfolio(
        frames=frames, scenario="FLASH_MOVE", overrides=overrides))
    assert sum(len(e.observations) for e in evidence) == retained * 3 <= 1500
    assert result.temporal.classification == classification
    assert all(c.valid and c.complete == (retained == frames) for c in result.temporal.clocks)
    if classification == "MODELED_ALIGNED":
        # Independent oracle: reserve once per frame, initial capital in the
        # running peak, maximum over the entire native curve (not endpoints).
        with localcontext() as ctx:
            ctx.prec = 80
            peak, maximum = p.budget.total_equity_quote, Decimal(0)
            for points in zip(*(e.observations for e in evidence), strict=True):
                equity = p.unallocated_reserve_quote + sum(x.equity_quote for x in points)
                peak = max(peak, equity)
                with localcontext() as ratio_ctx:
                    ratio_ctx.prec = 50
                    fraction = (peak - equity) / peak
                    if fraction.as_tuple().exponent < -60:
                        fraction = fraction.quantize(Decimal("1e-60"))
                maximum = max(maximum, fraction)
        assert result.accounting.drawdown.observation_count == frames
        assert result.accounting.drawdown.peak_equity_quote == peak
        assert result.accounting.drawdown.max_drawdown_fraction == maximum
        assert result.accounting.drawdown.ending_drawdown_fraction == fraction
        assert result.risk.outcome == "ASSESSED"
    else:
        assert result.accounting.equity_quote is not None
        assert result.accounting.drawdown is None
        assert result.risk.outcome == "BLOCKED" and not result.risk.risk_compliant
        assert result.risk.decision in {None, "HALT"}
    assert PortfolioAnalysisResult.model_validate_json(result.model_dump_json()) == result
    assert len(result.model_dump_json().encode()) <= 200000
    # Reusing precisely the same native evidence must reproduce the receipt.
    assert assemble_analysis(p, receipts, evidence, result.risk.policy) == result


@pytest.mark.parametrize("frames,retained,levels", [
    (501, 501, 8),  # 1,503 retained observations, even with complete histories.
    (1001, 500, 8),  # Total executed frames over 3,000.
    (1000, 500, 9),  # Quote work over 24,000.
    (161, 161, 50),  # Wide ladder just beyond the quote-work boundary.
])
def test_excess_work_is_rejected_before_worker_admission(research_client, monkeypatch, frames, retained, levels):
    from app.main import app
    client, _ = research_client
    p = portfolio(frames=frames, overrides={m: {"simulation": {"trace_max_points": retained},
        "strategy": {"levels_per_side": levels, "total_liquidity": str(size)}}
        for m, size in (("BTC", 1), ("ETH", 20), ("SOL", 400))})
    async def forbidden(*args, **kwargs):
        pytest.fail("over-budget request reached research admission")
    monkeypatch.setattr(app.state.simulation_executor, "execute", forbidden)
    response = client.post("/api/v1/portfolio-research/analyze", json={
        "config": p.model_dump(mode="json"), "config_fingerprint": p.fingerprint()})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert not app.state.simulation_executor._busy


@pytest.mark.parametrize("kind", ["foreign_market", "foreign_receipt", "relabeled_observations",
    "interior_equity", "terminal_position", "terminal_mark", "copied_unsealed"])
def test_substituted_observations_cannot_establish_modeled_alignment(native173, kind):
    _, receipts, evidence, _ = native173
    original = evidence[0]
    if kind == "foreign_market":
        bad = evidence[1]
    elif kind == "foreign_receipt":
        bad = reseal(original, market_receipt_fingerprint=evidence[1].market_receipt_fingerprint)
    elif kind == "relabeled_observations":
        # Same synthetic clock; different native financial history.
        bad = reseal(original, observations=evidence[1].observations)
    else:
        points = list(original.observations)
        index, field = (3, "equity_quote") if kind in {"interior_equity", "copied_unsealed"} else (
            -1, "position_base" if kind == "terminal_position" else "mark_price_quote")
        points[index] = points[index].model_copy(update={field: getattr(points[index], field) + 1})
        bad = (original.model_copy(update={"observations": tuple(points)}) if kind == "copied_unsealed"
               else reseal(original, observations=tuple(points)))
    with pytest.raises(ValueError):
        evaluate_temporal(receipts, (bad, *evidence[1:]))


@pytest.mark.parametrize("changes", [
    {"retained": 11}, {"complete": False}, {"expected_retained": 11},
    {"valid": False}, {"expected_retained": 13},
])
def test_rehashed_clock_cannot_lie_about_completeness(native173, changes):
    clock = native173[3].temporal.clocks[0]
    with pytest.raises(ValueError, match="retention/completeness"):
        reseal(clock, **changes)


def bound_reports(p, a, x, t):
    """Keep source links correct when constructing adversarial metric fixtures."""
    a = reseal(a, config_fingerprint=p.fingerprint(), temporal_fingerprint=t.evidence_fingerprint)
    x = reseal(x, accounting_fingerprint=a.evidence_fingerprint, temporal_fingerprint=t.evidence_fingerprint)
    return a, x


@pytest.mark.parametrize("missing", ["gross_exposure_quote", "net_exposure_quote",
    "max_inventory_concentration", "reserved_capital_utilization", "modeled_leverage",
    "session_loss_quote", "drawdown"])
@pytest.mark.parametrize("known,expected", [("0", None), ("80000", None), ("95000", None), ("100000", "HALT")])
def test_every_missing_metric_blocks_without_hiding_known_breaches(native173, missing, known, expected):
    p, a, x, t = inputs(native173)
    # Use session loss as the independent breach when gross itself is missing.
    if missing == "gross_exposure_quote":
        a = reseal(a, session_loss_quote=Decimal(known) / 10)
    else:
        x = reseal(x, gross_exposure_quote=Decimal(known))
    if missing in {"drawdown", "session_loss_quote"}:
        a = reseal(a, **{missing: None})
    else:
        x = reseal(x, **{missing: None})
    a, x = bound_reports(p, a, x, t)
    result = evaluate_risk(p, a, x, t, PortfolioRiskPolicy())
    assert result.outcome == "BLOCKED" and result.decision == expected
    assert not result.risk_compliant and any(c.state == "UNAVAILABLE" for c in result.checks)
    if known != "0":
        assert any(c.state == {"80000": "WARN", "95000": "REDUCE", "100000": "HALT"}[known]
                   for c in result.checks)
    assert evaluate_risk(p, a, x, t, PortfolioRiskPolicy()) == result


@pytest.mark.parametrize("field", ["equity_quote", "pnl_quote"])
@pytest.mark.parametrize("breach", [False, True])
def test_critical_accounting_missing_even_if_risk_metrics_are_present(native173, field, breach):
    p, a, x, t = inputs(native173)
    a = reseal(a, **{field: None})
    x = reseal(x, gross_exposure_quote=Decimal("100000" if breach else "0"))
    a, x = bound_reports(p, a, x, t)
    result = evaluate_risk(p, a, x, t, PortfolioRiskPolicy())
    assert result.outcome == "BLOCKED" and not result.risk_compliant
    assert result.decision == ("HALT" if breach else None)


@pytest.mark.parametrize("classification", ["FINAL_ONLY", "INCOMPARABLE", "UNAVAILABLE"])
@pytest.mark.parametrize("breach", [False, True])
def test_ineligible_temporal_report_cannot_be_overridden_by_complete_metrics(native173, classification, breach):
    p, a, x, t = inputs(native173)
    t = reseal(t, classification=classification)
    x = reseal(x, gross_exposure_quote=Decimal("100000" if breach else "0"))
    a, x = bound_reports(p, a, x, t)
    result = evaluate_risk(p, a, x, t, PortfolioRiskPolicy())
    assert result.outcome == "BLOCKED" and not result.risk_compliant
    assert result.decision == ("HALT" if breach else None)


@pytest.mark.parametrize("target,field", [
    ("accounting", "config_fingerprint"), ("accounting", "temporal_fingerprint"),
    ("exposure", "accounting_fingerprint"), ("exposure", "temporal_fingerprint"),
])
def test_risk_rejects_cross_report_source_substitution(native173, target, field):
    p, a, x, t = inputs(native173)
    if target == "accounting": a = reseal(a, **{field: "0" * 64})
    else: x = reseal(x, **{field: "0" * 64})
    with pytest.raises(ValueError, match="source identity"):
        evaluate_risk(p, a, x, t, PortfolioRiskPolicy())


@pytest.mark.parametrize("value,state", [
    ("-79999.999999999999999999", "NORMAL"),
    ("-94999.999999999999999999", "WARN"),
    ("-99999.999999999999999999", "REDUCE"), ("-100000", "HALT"),
])
def test_absolute_net_risk_thresholds_independent_of_ambient_decimal_context(native173, value, state):
    p, a, x, t = inputs(native173)
    x = reseal(x, net_exposure_quote=Decimal(value))
    expected = evaluate_risk(p, a, x, t, PortfolioRiskPolicy())
    assert expected.decision == state
    with localcontext() as ctx:
        ctx.prec = 8
        assert evaluate_risk(p, a, x, t, PortfolioRiskPolicy()) == expected


@pytest.mark.parametrize("target,field,value", [
    ("temporal", "historical_market_synchronization_verified", True),
    ("temporal", "empirical_correlation_verified", True),
    ("temporal", "cross_market_correlation", "0.99"),
    ("temporal", "source_authenticated", True),
    ("analysis", "historical_market_synchronization_verified", True),
    ("provenance", "source_authenticated", True),
    ("provenance", "synchronized_market_windows_verified", True),
    ("provenance", "results_engine_attested", True),
])
def test_rehashed_forged_authentication_synchronization_or_correlation_rejected(native173, target, field, value):
    p, _, _, result = native173
    if target == "provenance":
        receipt = capture_portfolio_provenance(p)
        with pytest.raises(ValueError):
            type(receipt).model_validate(receipt.model_copy(update={field: value}))
    else:
        receipt = result if target == "analysis" else result.temporal
        payload = receipt.model_dump(mode="json", exclude={"evidence_fingerprint"})
        payload[field] = value
        payload["evidence_fingerprint"] = stable_fingerprint(payload)
        with pytest.raises(ValueError): type(receipt).model_validate(payload)


def test_synthetic_alignment_never_establishes_empirical_correlation(native173):
    *_, result = native173
    t = result.temporal
    assert t.classification == "MODELED_ALIGNED"
    assert len({(c.start_at, c.final_at) for c in t.clocks}) == 1
    assert t.cross_market_correlation is None
    assert t.empirical_correlation_verified is False
    assert t.historical_market_synchronization_verified is False
    assert result.historical_market_synchronization_verified is False
    assert all(not s.source_authenticated for s in result.execution.config.scenarios)


@pytest.mark.parametrize("decision,concentration", [("HALT", "0.75"), ("REDUCE", "0.78")])
def test_native_risk_assessment_has_no_operational_or_signing_authority(research_client, monkeypatch, decision, concentration):
    client, rt = research_client
    # Preserve an existing operational order as well as accounting and switches.
    from app.execution.models import OrderRequest
    asyncio.run(rt.paper.submit_orders([OrderRequest(client_order_id="phase173h-existing", market="BTC", side="BID",
        price=Decimal("1"), size=Decimal(".001"))]))
    rt.risk.kill_switch_active = True
    before, history = authority(rt), deepcopy(rt.market_history.__dict__)
    listeners = tuple(rt.market._listeners)
    signing = (id(rt.testnet), id(rt.testnet.authority), rt.testnet.enabled,
        id(rt.settings), rt.settings.enable_hyperliquid_testnet_orders)
    def forbidden(*args, **kwargs):
        pytest.fail("research assessment accessed an operational adapter")
    for adapter in (rt.paper, rt.testnet):
        for name in ("submit_orders", "cancel_orders", "replace_orders", "get_account_state"):
            if hasattr(adapter, name): monkeypatch.setattr(adapter, name, forbidden)
    raw = portfolio(frames=12, scenario="FLASH_MOVE").model_dump()
    raw["risk_limits"]["max_inventory_concentration"] = concentration
    response = client.post("/api/v1/portfolio-research/analyze",
        json=request_for(PortfolioResearchConfig.model_validate(raw)).model_dump(mode="json"))
    assert response.status_code == 200, response.text
    result = PortfolioAnalysisResult.model_validate_json(response.content)
    assert result.risk.decision == decision
    assert result.risk.operational_authority == "NONE"
    assert result.risk.historical_orders_prevented is False
    assert authority(rt) == before and rt.market_history.__dict__ == history
    assert tuple(rt.market._listeners) == listeners
    assert signing == (id(rt.testnet), id(rt.testnet.authority), rt.testnet.enabled,
        id(rt.settings), rt.settings.enable_hyperliquid_testnet_orders)
