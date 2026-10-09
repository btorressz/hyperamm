from __future__ import annotations

from decimal import Decimal
from .models import AmmModel, CurvePoint, VirtualPool
from .concentrated import concentrated_weights
from .numeric import numeric_guard

BPS=Decimal("10000")


@numeric_guard
def sample_curve(pool: VirtualPool, fair_value: Decimal, levels_per_side: int, max_distance_bps: Decimal,
                 model: AmmModel = AmmModel.CONSTANT_PRODUCT, concentration_factor: Decimal = Decimal("0"),
                 lower_bound_bps: Decimal = Decimal("10"), upper_bound_bps: Decimal = Decimal("200")) -> list[CurvePoint]:
    if levels_per_side <= 0 or not max_distance_bps.is_finite() or max_distance_bps <= 0:
        raise ValueError("levels and max distance must be positive")
    distances=[max_distance_bps * Decimal(i+1) / Decimal(levels_per_side) for i in range(levels_per_side)]
    if not fair_value.is_finite() or fair_value <= 0:
        raise ValueError("fair value must be finite and positive")
    weights=[Decimal("1")]*levels_per_side
    if model == AmmModel.CONCENTRATED:
        weights=concentrated_weights(distances, concentration_factor, lower_bound_bps, upper_bound_bps)
    points=[]
    fair_base=(pool.k/fair_value).sqrt()
    for side in ("BID","ASK"):
        previous_base=fair_base
        previous_cumulative=Decimal("0")
        side_points=[]
        for d,w in zip(distances,weights):
            factor = Decimal("1") - d/BPS if side=="BID" else Decimal("1") + d/BPS
            target_price=fair_value*factor
            if target_price <= 0:
                raise ValueError("curve would produce non-positive price")
            target_base=(pool.k/target_price).sqrt()
            cumulative=abs(target_base-fair_base)
            incremental=cumulative-previous_cumulative
            if not incremental.is_finite() or incremental <= 0 or incremental != abs(target_base-previous_base):
                raise ValueError("curve reserve movement is not representable: must be finite, positive and monotonic")
            side_points.append(CurvePoint(side=side,distance_bps=d,price=target_price,
                                          target_base=target_base,cumulative_base=cumulative,
                                          incremental_base=incremental,weight=incremental*w))
            previous_base=target_base
            previous_cumulative=cumulative
        total=sum((p.weight for p in side_points),Decimal("0"))
        for point in side_points:
            point.weight /= total
        points.extend(side_points)
    return points
