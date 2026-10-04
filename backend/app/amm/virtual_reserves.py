from decimal import Decimal
from .models import VirtualPool
from .constant_product import invariant


def initialize_virtual_pool(base_reserve: Decimal, quote_reserve: Decimal, reference_price: Decimal | None = None) -> VirtualPool:
    k = invariant(base_reserve, quote_reserve)
    ref = reference_price or (quote_reserve / base_reserve)
    if not ref.is_finite() or ref <= 0:
        raise ValueError("reference price must be finite and > 0")
    return VirtualPool(reserve_base=base_reserve, reserve_quote=quote_reserve, k=k, reference_price=ref)


def recenter_pool(pool: VirtualPool, reference_price: Decimal) -> VirtualPool:
    if not reference_price.is_finite() or reference_price <= 0:
        raise ValueError("reference price must be finite and > 0")
    # Preserve k while moving the marginal price y/x to the new reference.
    base = (pool.k / reference_price).sqrt()
    quote = (pool.k * reference_price).sqrt()
    return VirtualPool(reserve_base=base, reserve_quote=quote, k=pool.k, reference_price=reference_price)
