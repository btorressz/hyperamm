from decimal import Decimal


def reserved_capital(position, mark, desired=(), existing=()):
    """Full-notional research reservation. Same-side/level KEEP/REPLACE overlap
    reserves max(old remaining notional, desired notional), never their sum.
    """
    if not position.is_finite() or not mark.is_finite() or mark <= 0:
        raise ValueError("invalid capital reservation position/mark")
    effective = {}
    for quote in desired:
        if (not quote.size.is_finite() or not quote.price.is_finite()
                or quote.size <= 0 or quote.price <= 0):
            raise ValueError("invalid desired capital reservation economics")
        key = (quote.side, quote.level_index)
        if key in effective:
            raise ValueError("duplicate desired accounting order level")
        effective[key] = quote.size * quote.price
    resting = {}
    for order in existing:
        if order.status not in {"OPEN", "PARTIALLY_FILLED", "UNKNOWN"}:
            continue
        if (not order.price.is_finite() or not order.size.is_finite() or not order.filled_size.is_finite()
                or order.price <= 0 or order.size <= 0 or not Decimal("0") <= order.filled_size <= order.size):
            raise ValueError("invalid resting capital reservation economics")
        key = (order.side, order.level_index)
        remaining = max(Decimal("0"), order.size - order.filled_size)
        resting[key] = resting.get(key, Decimal("0")) + remaining * order.price
    for key, notional in resting.items():
        effective[key] = max(effective.get(key, Decimal("0")), notional)
    return abs(position) * mark + sum(effective.values(), Decimal("0"))
