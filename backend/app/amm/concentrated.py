from __future__ import annotations

from decimal import Decimal


def concentrated_weights(distances_bps: list[Decimal], concentration_factor: Decimal, lower_bound_bps: Decimal, upper_bound_bps: Decimal) -> list[Decimal]:
    if concentration_factor < 0 or not concentration_factor.is_finite():
        raise ValueError("concentration_factor must be finite and >= 0")
    if lower_bound_bps < 0 or upper_bound_bps <= lower_bound_bps:
        raise ValueError("invalid concentration bounds")
    raw=[]
    width = upper_bound_bps - lower_bound_bps
    for distance in distances_bps:
        if distance <= lower_bound_bps:
            normalized = Decimal("0")
        else:
            normalized = min(Decimal("1"), (distance-lower_bound_bps)/width)
        raw.append(Decimal("1") / (Decimal("1") + concentration_factor * normalized * normalized))
    total=sum(raw, Decimal("0"))
    if total <= 0:
        raise ValueError("invalid concentrated-liquidity weights")
    return [x/total for x in raw]
