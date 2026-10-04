from __future__ import annotations

from decimal import Decimal
from .models import AmmModel, CurvePoint, VirtualPool
from .concentrated import concentrated_weights

BPS=Decimal("10000")


def sample_curve(pool: VirtualPool, fair_value: Decimal, levels_per_side: int, max_distance_bps: Decimal,
                 model: AmmModel = AmmModel.CONSTANT_PRODUCT, concentration_factor: Decimal = Decimal("0"),
                 lower_bound_bps: Decimal = Decimal("10"), upper_bound_bps: Decimal = Decimal("200")) -> list[CurvePoint]:
    if levels_per_side <= 0 or max_distance_bps <= 0:
        raise ValueError("levels and max distance must be positive")
    distances=[max_distance_bps * Decimal(i+1) / Decimal(levels_per_side) for i in range(levels_per_side)]
    weights=[Decimal("1")/Decimal(levels_per_side)]*levels_per_side
    if model == AmmModel.CONCENTRATED:
        weights=concentrated_weights(distances, concentration_factor, lower_bound_bps, upper_bound_bps)
    points=[]
    for side in ("BID","ASK"):
        for d,w in zip(distances,weights):
            factor = Decimal("1") - d/BPS if side=="BID" else Decimal("1") + d/BPS
            target_price=fair_value*factor
            if target_price <= 0:
                raise ValueError("curve would produce non-positive price")
            target_base=(pool.k/target_price).sqrt()
            cumulative=abs(target_base-pool.reserve_base)
            points.append(CurvePoint(side=side,distance_bps=d,price=target_price,cumulative_base=cumulative,weight=w))
    return points
