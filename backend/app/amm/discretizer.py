from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_UP
from .models import AmmModel, QuoteLevel, VirtualPool
from .liquidity_curve import sample_curve


def normalize_price(price: Decimal, tick_size: Decimal, side: str) -> Decimal:
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    units=price/tick_size
    rounding=ROUND_DOWN if side=="BID" else ROUND_UP
    return units.to_integral_value(rounding=rounding)*tick_size


def normalize_size(size: Decimal, size_precision: int) -> Decimal:
    if size_precision < 0:
        raise ValueError("size_precision must be >= 0")
    quantum=Decimal(1).scaleb(-size_precision)
    result=size.quantize(quantum, rounding=ROUND_DOWN)
    if result <= 0:
        raise ValueError("normalized size is zero")
    return result


def compile_quotes(pool: VirtualPool, fair_value: Decimal, model: AmmModel, levels_per_side: int,
                   max_distance_bps: Decimal, total_liquidity: Decimal, tick_size: Decimal,
                   size_precision: int, concentration_factor: Decimal = Decimal("0"),
                   lower_bound_bps: Decimal = Decimal("10"), upper_bound_bps: Decimal = Decimal("200"),
                   base_order_size: Decimal = Decimal("0")) -> list[QuoteLevel]:
    if total_liquidity <= 0:
        raise ValueError("total_liquidity must be > 0")
    if base_order_size < 0:
        raise ValueError("base_order_size must be >= 0")
    quantum=Decimal(1).scaleb(-size_precision)
    # Round the minimum up first, then allocate only the remaining budget.
    base_order_size=base_order_size.quantize(quantum,rounding=ROUND_UP)
    baseline_total=base_order_size*Decimal(levels_per_side)
    if total_liquidity < baseline_total:
        raise ValueError("total_liquidity must cover base_order_size across all levels")
    variable_liquidity=total_liquidity-baseline_total
    points=sample_curve(pool,fair_value,levels_per_side,max_distance_bps,model,concentration_factor,lower_bound_bps,upper_bound_bps)
    quotes=[]
    by_side={"BID":[],"ASK":[]}
    for p in points: by_side[p.side].append(p)
    for side in ("BID","ASK"):
        for i,p in enumerate(by_side[side]):
            price=normalize_price(p.price,tick_size,side)
            # Each level receives a configured base size plus a curve-shaped share of remaining side liquidity.
            size=normalize_size(base_order_size + variable_liquidity*p.weight,size_precision)
            quotes.append(QuoteLevel(side=side,price=price,size=size,level_index=i,distance_bps=p.distance_bps,source_model=model))
    bids=sorted((q for q in quotes if q.side=="BID"), key=lambda q:q.price, reverse=True)
    asks=sorted((q for q in quotes if q.side=="ASK"), key=lambda q:q.price)
    if bids and asks and bids[0].price >= asks[0].price:
        raise ValueError("compiled quote market is crossed")
    return bids+asks
