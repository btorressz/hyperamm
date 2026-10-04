from __future__ import annotations

from decimal import Decimal, InvalidOperation
from .models import VirtualPool


def _positive(value: Decimal, name: str) -> Decimal:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return value


def invariant(base: Decimal, quote: Decimal) -> Decimal:
    return _positive(base, "base reserve") * _positive(quote, "quote reserve")


def marginal_price(pool: VirtualPool) -> Decimal:
    return pool.reserve_quote / pool.reserve_base


def price_at_base_reserve(k: Decimal, base_reserve: Decimal) -> Decimal:
    _positive(k, "k"); _positive(base_reserve, "base reserve")
    quote = k / base_reserve
    return quote / base_reserve


def simulate_base_to_quote(pool: VirtualPool, base_in: Decimal) -> tuple[VirtualPool, Decimal]:
    _positive(base_in, "base trade quantity")
    new_base = pool.reserve_base + base_in
    new_quote = pool.k / new_base
    quote_out = pool.reserve_quote - new_quote
    return VirtualPool(reserve_base=new_base, reserve_quote=new_quote, k=pool.k, reference_price=pool.reference_price), quote_out


def simulate_quote_to_base(pool: VirtualPool, quote_in: Decimal) -> tuple[VirtualPool, Decimal]:
    _positive(quote_in, "quote trade quantity")
    new_quote = pool.reserve_quote + quote_in
    new_base = pool.k / new_quote
    base_out = pool.reserve_base - new_base
    return VirtualPool(reserve_base=new_base, reserve_quote=new_quote, k=pool.k, reference_price=pool.reference_price), base_out
