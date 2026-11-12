"""Pure capital reconciliation. This does not place, reserve or authorize orders."""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Iterable

from app.simulation.market_profiles import MARKETS


def allocation_totals(total_equity: Decimal, amounts: Iterable[tuple[str, Decimal]]) -> tuple[Decimal, Decimal]:
    with localcontext() as ctx:
        ctx.prec = 80
        return _reconcile(total_equity, amounts)


def _reconcile(total_equity: Decimal, amounts: Iterable[tuple[str, Decimal]]) -> tuple[Decimal, Decimal]:
    seen: set[str] = set()
    allocated = Decimal("0")
    for market, amount in amounts:
        if market not in MARKETS or market in seen:
            raise ValueError("portfolio allocation contains an unsupported or repeated market")
        seen.add(market)
        if not amount.is_finite() or amount <= 0:
            raise ValueError("portfolio allocation must be strictly positive")
        allocated += amount
        if allocated > total_equity:
            raise ValueError("portfolio allocations exceed the shared hypothetical capital budget")
    if not seen:
        raise ValueError("portfolio allocation requires at least one supported market")
    return allocated, total_equity - allocated
