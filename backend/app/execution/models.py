from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pydantic import BaseModel, Field
from app.market_data.models import utcnow


class OrderStatus(StrEnum):
    UNKNOWN="UNKNOWN"; OPEN="OPEN"; PARTIALLY_FILLED="PARTIALLY_FILLED"; FILLED="FILLED"; CANCELLED="CANCELLED"; REPLACED="REPLACED"; REJECTED="REJECTED"


class OrderRequest(BaseModel):
    client_order_id: str
    market: str
    side: str
    price: Decimal = Field(gt=0)
    size: Decimal = Field(gt=0)
    level_index: int | None = None


class StrategyOrder(OrderRequest):
    status: OrderStatus = OrderStatus.OPEN
    filled_size: Decimal = Decimal("0")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    venue_order_id: str | None = None
    fill_source: str | None = None


class Fill(BaseModel):
    client_order_id: str
    market: str
    side: str
    price: Decimal
    size: Decimal
    timestamp: datetime = Field(default_factory=utcnow)
    source: str = "SIMULATED PAPER FILL"
