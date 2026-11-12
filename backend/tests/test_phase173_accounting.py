from decimal import Decimal, localcontext

import pytest

from app.accounting.config import AccountingConfig
from app.portfolio_research.accounting import reconcile_accounting, validate_native_accounting
from app.portfolio_research.models import PortfolioResearchConfig
from app.portfolio_research.aggregation import assemble_analysis
from phase173_fixtures import native173, native, reseal
from phase172_fixtures import portfolio, AMOUNTS


def test_exact_shared_capital_reserve_equity_pnl_and_original_fees(native173):
    p, receipts, _, result = native173
    a = result.accounting
    assert (a.initial_capital_quote, a.allocated_capital_quote, a.reserve_quote) == (100000, 95000, 5000)
    assert a.capital_allocation_utilization == Decimal(".95")
    with localcontext() as ctx:
        ctx.prec = 80
        assert a.equity_quote == sum(r.vault.equity_quote for r in receipts) + 5000
        assert a.pnl_quote == a.equity_quote - 100000
        assert a.pnl_quote == sum(r.vault.net_pnl_quote for r in receipts) + a.native_rounding_residual_quote
    assert a.session_loss_quote == -a.pnl_quote > 0
    for c, r in zip(a.contributions, receipts):
        assert (c.fees_quote, c.funding_quote, c.realized_pnl_quote, c.unrealized_pnl_quote) == (
            r.vault.fees_quote, r.vault.funding_quote, r.vault.realized_pnl_quote, r.vault.unrealized_pnl_quote)


@pytest.mark.parametrize("markets", [("BTC",), ("ETH", "SOL"), ("BTC", "ETH", "SOL")])
async def test_partial_and_fully_allocated_budget(markets):
    p = portfolio(markets)
    raw = p.model_dump()
    raw["budget"]["total_equity_quote"] = p.allocated_equity_quote
    full = PortfolioResearchConfig.model_validate(raw)
    for c in (p, full):
        _, _, _, r = await native(c)
        assert r.accounting.allocated_capital_quote + r.accounting.reserve_quote == c.budget.total_equity_quote
    assert r.accounting.reserve_quote == 0


async def test_native_nonzero_fees_funding_never_deducted_twice():
    overrides = {m: {"simulation": {"accounting": AccountingConfig(
        paper_initial_equity_quote=amount, paper_fee_model_enabled=True,
        paper_funding_accounting_enabled=True, paper_funding_interval_seconds=1).model_dump(mode="json")}}
        for m, amount in AMOUNTS.items()}
    _, receipts, _, r = await native(portfolio(frames=40, scenario="FLASH_MOVE", overrides=overrides))
    assert any(c.fees_quote > 0 for c in r.accounting.contributions)
    assert any(c.funding_quote != 0 for c in r.accounting.contributions)
    assert any(c.unrealized_pnl_quote != 0 for c in r.accounting.contributions)
    assert r.accounting.equity_quote == sum(c.vault.equity_quote for c in receipts) + 5000


async def test_no_fill_is_actual_zero_evidence():
    _, receipts, _, r = await native(portfolio(frames=2))
    assert all(m.metrics.fill_count == 0 for m in receipts)
    assert r.accounting.pnl_quote == 0
    assert all(c.fees_quote == 0 and c.funding_quote == 0 for c in r.accounting.contributions)


@pytest.mark.parametrize("field,value", [("net_pnl_quote", None), ("fees_quote", None),
    ("equity_quote", Decimal("1")), ("mark_price", Decimal("0")), ("position_value_quote", Decimal("42")),
    ("reserved_capital_quote", Decimal("-1")), ("source", "FOREIGN"), ("stale", True)])
def test_incomplete_or_inconsistent_native_economics_rejected(native173, field, value):
    _, receipts, _, _ = native173
    r = receipts[0]
    bad = r.model_copy(update={"vault": r.vault.model_copy(update={field: value})})
    with pytest.raises(ValueError): validate_native_accounting(bad)


def test_missing_duplicate_or_foreign_market_contributions_rejected(native173):
    p, receipts, _, r = native173
    for items in (receipts[:-1], (receipts[0], receipts[0], receipts[2]), receipts[::-1]):
        with pytest.raises(ValueError):
            reconcile_accounting(p, items, r.temporal, drawdown_evidence=r.accounting.drawdown)


def test_aggregate_arithmetic_independent_of_ambient_precision(native173):
    p, receipts, evidence, r = native173
    with localcontext() as ctx:
        ctx.prec = 8
        assert assemble_analysis(p, receipts, evidence, r.risk.policy) == r


async def test_fractional_capital_retains_native_rounding_residual():
    from phase171a_fixtures import config
    p = config(markets=("BTC",), amounts=("12345.123456789123456789",),
               total="12346.123456789123456788")
    _, _, _, r = await native(p)
    assert r.accounting.reserve_quote == Decimal(".999999999999999999")
    assert r.accounting.equity_quote - r.accounting.initial_capital_quote == r.accounting.pnl_quote
