from __future__ import annotations
from decimal import Decimal
from pydantic import BaseModel


class RiskStatus(BaseModel):
    kill_switch_active: bool=False
    last_reason: str | None=None
    max_quote_levels: int=50
    max_order_size: Decimal=Decimal("25")
    max_aggregate_notional: Decimal=Decimal("1000000")
    min_valid_price: Decimal=Decimal("0.00000001")
    max_quote_distance_bps: Decimal=Decimal("2500")
