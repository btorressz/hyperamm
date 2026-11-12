"""Bound exact monetary inputs before Pydantic coercion; never accept binary floats."""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Annotated
from pydantic import BeforeValidator, PlainSerializer

from app.accounting.config import bounded_exact_decimal

MAX_PORTFOLIO_CAPITAL = Decimal("1000000000000")

# One sequential job, bounded across all selected markets. Quote work also
# bounds expensive 50-level configurations; captures are rejected, never edited.
MAX_TOTAL_FRAMES = 3000
MAX_QUOTE_LEVEL_FRAMES = 24000
MAX_TOTAL_TRACE_POINTS = 1500
MAX_TOTAL_LEDGER_ENTRIES = 30000
MAX_TOTAL_EVENT_ENTRIES = 750
MAX_RESPONSE_BYTES = 200000


class PortfolioResponseTooLarge(ValueError):
    pass


def exact_portfolio_decimal(value: object) -> Decimal:
    number = bounded_exact_decimal(value)
    if number.as_tuple().exponent < -18:
        raise ValueError("portfolio decimals may have no more than 18 fractional places")
    if number.copy_abs() > MAX_PORTFOLIO_CAPITAL:
        raise ValueError("portfolio amount exceeds local PAPER research bound")
    # Canonical equivalents (1, 1.0, 1.00) must hash identically.
    if not number:
        return Decimal("0")
    with localcontext() as ctx:
        ctx.prec = 80
        return number.normalize()


ExactPortfolioDecimal = Annotated[
    Decimal,
    BeforeValidator(exact_portfolio_decimal),
    PlainSerializer(lambda n: format(n, "f"), return_type=str, when_used="json"),
]
