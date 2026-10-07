from decimal import Decimal

from .models import PnlBreakdown, PositionAccounting


ZERO = Decimal("0")


def apply_trade(position: PositionAccounting, *, side: str, price: Decimal, size: Decimal):
    """Single average-cost authority. Positive base is long; negative is short."""
    if side not in {"BID", "ASK"}:
        raise ValueError("accounting fill side must be BID or ASK")
    if not price.is_finite() or price <= 0 or not size.is_finite() or size <= 0:
        raise ValueError("accounting fill price/size must be finite and positive")
    qty, avg = position.position_base, position.average_entry_price
    signed = size if side == "BID" else -size
    new = qty + signed
    realized = ZERO
    if qty == 0 or (qty > 0) == (signed > 0):
        avg = (avg * abs(qty) + price * size) / abs(new)
    else:
        closed = min(abs(qty), size)
        realized = (price - avg) * closed * (Decimal("1") if qty > 0 else Decimal("-1"))
        if new == 0:
            avg = ZERO
        elif (qty > 0) != (new > 0):
            avg = price
    updated = PositionAccounting(
        market=position.market, position_base=new, average_entry_price=avg,
        cost_basis_quote=new * avg, realized_pnl_quote=position.realized_pnl_quote + realized,
        version=position.version + 1,
    )
    if position.mark_price is not None:
        updated = mark_position(updated, position.mark_price)
    return updated, realized


def mark_position(position: PositionAccounting, mark: Decimal):
    if not mark.is_finite() or mark <= 0:
        raise ValueError("accounting mark must be finite and positive")
    return position.model_copy(update={
        "mark_price": mark,
        "unrealized_pnl_quote": (mark - position.average_entry_price) * position.position_base,
        "position_value_quote": mark * position.position_base,
    })


def pnl_breakdown(position: PositionAccounting, fees: Decimal, funding: Decimal):
    realized, unrealized = position.realized_pnl_quote, position.unrealized_pnl_quote
    net_realized = realized - fees + funding
    gross = realized + unrealized if unrealized is not None else None
    net = net_realized + unrealized if unrealized is not None else None
    return PnlBreakdown(
        realized_trading_pnl=realized, unrealized_trading_pnl=unrealized,
        fee_pnl=-fees, funding_pnl=funding, net_realized_pnl=net_realized,
        net_unrealized_pnl=unrealized, session_pnl=net,
        gross_trading_pnl=gross, net_pnl=net,
    )


def drawdown(equity: Decimal | None, peak: Decimal | None):
    if equity is None or peak is None:
        return None, None
    amount = max(ZERO, peak - equity)
    return amount, amount / peak if peak > 0 else None


def to_pnl_drawdown(vault):
    # Local import keeps the accounting domain independent of risk implementation.
    from app.risk.firewall import PnlDrawdown
    return PnlDrawdown(
        realized_pnl=vault.realized_pnl_quote, unrealized_pnl=vault.unrealized_pnl_quote,
        session_pnl=vault.session_pnl_quote, current_equity=vault.equity_quote,
        peak_equity=vault.peak_equity_quote, drawdown_pct=vault.drawdown_pct,
        source=vault.source, simulated=vault.simulated,
    )


def replay_position(fills, market, mark):
    """Legacy gross-PnL compatibility only; runtime/simulation use AccountingService."""
    position = PositionAccounting(market=market)
    for fill in fills:
        if fill.market == market:
            position, _ = apply_trade(position, side=fill.side, price=fill.price, size=fill.size)
    return mark_position(position, mark)
