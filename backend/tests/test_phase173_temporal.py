from datetime import timedelta
from decimal import Decimal

import pytest

from app.portfolio_research.temporal import evaluate_temporal
from app.portfolio_research.accounting import portfolio_drawdown
from app.portfolio_research.aggregation import assemble_analysis
from phase173_fixtures import native173, native, reseal
from phase172_fixtures import portfolio


def test_complete_common_clock_is_only_modeled_alignment(native173):
    p, receipts, evidence, r = native173
    assert r.temporal.classification == "MODELED_ALIGNED"
    assert r.temporal.historical_market_synchronization_verified is False
    assert all(c.complete and c.frames == 12 for c in r.temporal.clocks)
    assert r.accounting.drawdown.observation_count == 12
    # Portfolio peak includes initial shared capital and reserve at each frame.
    equities = [sum(ps.equity_quote for ps in points) + p.unallocated_reserve_quote
                for points in zip(*(e.observations for e in evidence))]
    peak, expected = p.budget.total_equity_quote, Decimal("0")
    from decimal import localcontext
    from app.accounting.pnl import drawdown
    with localcontext() as ctx:
        ctx.prec = 50
        for equity in equities:
            peak = max(peak, equity)
            expected = max(expected, drawdown(equity, peak)[1])
    assert r.accounting.drawdown.max_drawdown_fraction == expected


@pytest.mark.parametrize("kind", ["missing", "duplicate", "ordering", "timestamp", "gap", "reset"])
def test_invalid_retained_history_is_unavailable(native173, kind):
    p, receipts, evidence, r = native173
    points = list(evidence[0].observations)
    if kind == "missing": points.pop(3)
    elif kind == "duplicate": points[3] = points[2]
    elif kind == "ordering": points[1], points[2] = points[2], points[1]
    elif kind == "timestamp": points[3] = points[3].model_copy(update={"timestamp": points[3].timestamp + timedelta(microseconds=1)})
    elif kind == "gap": points[3] = points[3].model_copy(update={"sequence": 9})
    else: points[3] = points[3].model_copy(update={"sequence": 1})
    modified = (reseal(evidence[0], observations=tuple(points)), *evidence[1:])
    t = evaluate_temporal(receipts, modified)
    assert t.classification == "UNAVAILABLE"
    result = assemble_analysis(p, receipts, modified, r.risk.policy)
    assert result.accounting.equity_quote is None and result.accounting.drawdown is None
    assert result.exposure.modeled_leverage is None
    assert result.risk.outcome == "BLOCKED" and not result.risk.risk_compliant


@pytest.mark.parametrize("kind", ["suffix", "disabled", "zero_retention"])
async def test_valid_partial_or_disabled_trace_supports_only_terminal_accounting(kind):
    changes = {"trace_max_points": 2} if kind == "suffix" else (
        {"record_trace": False} if kind == "disabled" else {"trace_max_points": 0})
    p = portfolio(frames=6, overrides={m: {"simulation": changes} for m in ("BTC", "ETH", "SOL")})
    _, _, _, r = await native(p)
    assert r.temporal.classification == "FINAL_ONLY"
    assert r.accounting.equity_quote is not None and r.accounting.drawdown is None
    assert r.risk.outcome == "BLOCKED" and r.risk.decision != "NORMAL"
    assert r.risk.checks[-1].state == "UNAVAILABLE"


@pytest.mark.parametrize("kind", ["scenario", "frame_count"])
async def test_different_scenarios_or_reference_windows_incomparable(kind):
    p = portfolio(scenario={"BTC": "QUIET", "ETH": "FLASH_MOVE", "SOL": "QUIET"}) if kind == "scenario" else portfolio(frames={"BTC": 4, "ETH": 5, "SOL": 4})
    _, _, _, r = await native(p)
    assert r.temporal.classification == "INCOMPARABLE"
    assert r.accounting.equity_quote is None and r.accounting.pnl_quote is None
    assert r.exposure.net_exposure_quote is None and r.risk.outcome == "BLOCKED"
    assert all(p.gross_concentration is None for p in r.exposure.positions)


def test_engine_clock_sources_must_be_compatible(native173):
    from app.portfolio_research.temporal import classify_clocks
    *_, r = native173
    clocks = list(r.temporal.clocks)
    clocks[0] = reseal(clocks[0], engine_version="different-engine")
    assert classify_clocks(clocks).classification == "INCOMPARABLE"


def test_foreign_or_empty_native_evidence_rejected(native173):
    p, receipts, evidence, r = native173
    with pytest.raises(ValueError): evaluate_temporal(receipts, evidence[::-1])
    with pytest.raises(ValueError): evaluate_temporal(receipts, evidence[:-1])
    with pytest.raises(ValueError):
        portfolio_drawdown(p, r.temporal, (reseal(evidence[0], observations=()), *evidence[1:]))
