from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from app.accounting import AccountingConfig, AccountingService
from app.accounting.pnl import to_pnl_drawdown
from app.execution.models import Fill, StrategyOrder
from app.amm.models import QuoteLevel


T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def fill(side="BID", price="3000", size="1", identity="a", seconds=0, **kwargs):
    return Fill(client_order_id=identity, market="ETH", side=side, price=D(price), size=D(size),
                timestamp=T + timedelta(seconds=seconds), **kwargs)


def service(**kwargs):
    return AccountingService("ETH", config=AccountingConfig(**kwargs), clock=lambda: T)


@pytest.mark.parametrize("trades,qty,avg,realized", [
    ([("BID", "3000", "1")], "1", "3000", "0"),
    ([("ASK", "3000", "1")], "-1", "3000", "0"),
    ([("BID", "3000", "1"), ("BID", "3100", "1")], "2", "3050", "0"),
    ([("ASK", "3000", "1"), ("ASK", "3100", "1")], "-2", "3050", "0"),
    ([("BID", "3000", "1"), ("BID", "3100", "1"), ("ASK", "3200", "1")], "1", "3050", "150"),
    ([("ASK", "3000", "1"), ("ASK", "3100", "1"), ("BID", "2900", "1")], "-1", "3050", "150"),
    ([("BID", "3000", "1"), ("ASK", "3100", "1")], "0", "0", "100"),
    ([("ASK", "3000", "1"), ("BID", "2900", "1")], "0", "0", "100"),
    ([("BID", "3000", "1"), ("ASK", "3100", "2")], "-1", "3100", "100"),
    ([("ASK", "3000", "1"), ("BID", "2900", "2")], "1", "2900", "100"),
    ([("BID", "3000", "1"), ("ASK", "2900", "1")], "0", "0", "-100"),
    ([("ASK", "3000", "1"), ("BID", "3100", "1")], "0", "0", "-100"),
    ([("BID", "3000", "1"), ("BID", "3100", "3")], "4", "3075", "0"),
])
def test_exact_average_cost_transitions(trades, qty, avg, realized):
    accounting = service()
    for index, (side, price, size) in enumerate(trades):
        accounting.ingest_fill(fill(side, price, size, identity=str(index), seconds=index))
    position = accounting.position
    assert position.position_base == D(qty)
    assert position.average_entry_price == D(avg)
    assert position.realized_pnl_quote == D(realized)
    assert position.cost_basis_quote == D(qty) * D(avg)


@pytest.mark.parametrize("side,mark,expected", [("BID", "3100", "100"), ("BID", "2900", "-100"),
                                               ("ASK", "3100", "-100"), ("ASK", "2900", "100")])
def test_unrealized_sign(side, mark, expected):
    accounting = service()
    accounting.ingest_fill(fill(side))
    accounting.mark(D(mark))
    assert accounting.pnl().unrealized_trading_pnl == D(expected)


@pytest.mark.parametrize("field,value", [("paper_initial_equity_quote", "0"), ("paper_initial_equity_quote", "NaN"),
    ("paper_taker_fee_bps", "Infinity"), ("paper_maker_fee_bps", "-1"), ("max_capital_utilization", "1.1"),
    ("paper_funding_interval_seconds", 0), ("ledger_max_entries", 1), ("event_max_entries", 0)])
def test_config_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        AccountingConfig(**{field: value})


@pytest.mark.parametrize("side,price,size", [("BUY", "3000", "1"), ("BID", "0", "1"),
                                         ("ASK", "3000", "-1"), ("BID", "NaN", "1")])
def test_invalid_economics_fail_without_partial_ledger(side, price, size):
    accounting = service()
    with pytest.raises(ValueError):
        accounting.ingest_fill(fill().model_copy(update={"side": side, "price": D(price), "size": D(size)}))
    assert accounting.ledger.version == 0
    assert accounting.position.position_base == 0
    assert accounting.snapshot().error


def test_exact_perpetual_equity_fees_funding_peak_drawdown():
    accounting = service(paper_initial_equity_quote=D("100000"), paper_fee_model_enabled=True,
                         paper_taker_fee_bps=D("10"), paper_funding_accounting_enabled=True)
    accounting.ingest_fill(fill(price="1000"))
    accounting.mark(D("1100"))
    assert accounting.snapshot().settled_capital_quote == D("99999")
    assert accounting.snapshot().equity_quote == D("100099")
    assert accounting.snapshot().peak_equity_quote == D("100099")
    accounting.accrue_funding(effective_at=T, mark=D("1100"), rate=D(".01"))
    accounting.ingest_fill(fill("ASK", "1050", identity="b", seconds=1))
    accounting.mark(D("1050"))
    accounting.reserve()
    vault = accounting.snapshot()
    assert vault.realized_pnl_quote == D("50")
    assert vault.unrealized_pnl_quote == 0
    assert vault.fees_quote == D("2.05")
    assert vault.funding_quote == D("-11")
    assert vault.net_pnl_quote == D("36.95")
    assert vault.equity_quote == vault.settled_capital_quote == D("100036.95")
    assert vault.drawdown_quote == D("62.05")
    assert vault.drawdown_pct == D("62.05") / D("100099")
    assert vault.reserved_capital_quote == 0
    assert vault.available_capital_quote == vault.equity_quote
    pnl = accounting.pnl()
    assert pnl.net_realized_pnl == D("36.95")
    assert pnl.fee_pnl == D("-2.05")
    assert pnl.session_pnl == pnl.net_pnl == vault.net_pnl_quote
    assert to_pnl_drawdown(vault).current_equity == vault.equity_quote


def quote(size="1", price="3000", side="BID", level=0):
    return QuoteLevel(side=side, price=D(price), size=D(size), level_index=level, distance_bps=D("1"), source_model="CONSTANT_PRODUCT")


def order(size="1", price="3000", side="BID", level=0, **kwargs):
    return StrategyOrder(client_order_id="rest", market="ETH", side=side, price=D(price), size=D(size),
                         level_index=level, **kwargs)


def test_capital_keep_replace_cancel_and_filled_position():
    accounting = service(paper_initial_equity_quote=D("10000"))
    accounting.mark(D("3000"))
    assert accounting.reserve() == 0
    assert accounting.reserve([quote()]) == D("3000")
    assert accounting.reserve([quote()], [order()]) == D("3000")
    assert accounting.reserve([quote(price="3100")], [order()]) == D("3100")
    assert accounting.reserve([quote(size=".5")], [order()]) == D("3000")
    assert accounting.reserve([], [order(filled_size=D(".25"), status="PARTIALLY_FILLED")]) == D("2250")
    assert accounting.reserve([], [order(status="CANCELLED")]) == 0
    accounting.ingest_fill(fill())
    accounting.mark(D("3000"))
    assert accounting.reserve([], [order(status="FILLED")]) == D("3000")
    vault = accounting.snapshot()
    assert vault.available_capital_quote == D("7000")
    assert vault.capital_utilization == D(".3")
    assert vault.gross_exposure_quote == vault.net_exposure_quote == D("3000")


def test_multiple_resting_same_slot_are_not_hidden():
    accounting = service()
    accounting.mark(D("3000"))
    assert accounting.reserve([quote()], [order(), order()]) == D("6000")


def test_material_versions_and_preview_reservations_do_not_churn():
    accounting = service()
    accounting.mark(D("3000"))
    accounting.reserve([quote()])
    state = accounting.snapshot()
    for _ in range(3):
        accounting.mark(D("3000"))
        accounting.reservation_snapshot([quote(size="2")])
        accounting.reserve([quote()])
    assert accounting.snapshot() == state
    accounting.mark(D("3100"))
    assert accounting.version > state.accounting_version


def test_staleness_and_errors_do_not_fabricate_fresh_authority():
    accounting = service()
    assert accounting.snapshot().accounting_complete == "UNAVAILABLE"
    accounting.mark(D("3000"))
    assert accounting.snapshot().accounting_complete == "COMPLETE"
    assert accounting.snapshot(now=T + timedelta(seconds=31)).stale
    accounting.clock = lambda: T + timedelta(seconds=31)
    with pytest.raises(RuntimeError, match="accounting stale"):
        accounting.require_fresh()
    accounting.fail("fixture invalid")
    assert accounting.snapshot().error == "fixture invalid"


def test_nonpositive_equity_has_no_utilization_or_fabricated_available_capital():
    accounting = service(paper_initial_equity_quote=D("100"))
    accounting.ingest_fill(fill())
    accounting.mark(D("2800"))
    accounting.reserve()
    assert accounting.snapshot().equity_quote == D("-100")
    assert accounting.snapshot().available_capital_quote == 0
    assert accounting.snapshot().capital_utilization is None
