"""Shared Decimal failure and executable-size semantics; no global precision change."""
from decimal import Decimal, DecimalException, ROUND_DOWN, ROUND_UP
from functools import wraps


def numeric_guard(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except DecimalException as exc:
            raise ValueError("AMM configuration is not representable at the supported Decimal precision") from exc
    return guarded


@numeric_guard
def quantize_size(size: Decimal, size_precision: int, *, minimum=False) -> Decimal:
    if not size.is_finite() or size < 0:
        raise ValueError("size must be finite and nonnegative")
    if not 0 <= size_precision <= 8:
        raise ValueError("size_precision must be between 0 and 8")
    quantum = Decimal(1).scaleb(-size_precision)
    return size.quantize(quantum, rounding=ROUND_UP if minimum else ROUND_DOWN)


@numeric_guard
def executable_distance(price: Decimal, reference: Decimal) -> Decimal:
    if any(not v.is_finite() or v <= 0 for v in (price, reference)):
        raise ValueError("quote price and reference must be finite and positive")
    return abs(price - reference) / reference * Decimal("10000")
