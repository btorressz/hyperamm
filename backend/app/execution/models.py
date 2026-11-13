from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field, model_serializer, model_validator
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
    liquidity: Literal["MAKER", "TAKER"] | None = None
    # Legacy Fill was PAPER-only. Venue records must supply their mode explicitly.
    execution_mode: Literal["PAPER", "TESTNET"] = "PAPER"

    @model_validator(mode="after")
    def evidence_classification(self):
        paper_source = (self.source == "SIMULATED PAPER FILL"
            or self.source == "HYPOTHETICAL MODELED PAPER FILL"
            or self.source.startswith("HYPOTHETICAL MODELED PAPER FILL:"))
        if paper_source != (self.execution_mode == "PAPER"):
            raise ValueError("fill source/execution mode contradiction")
        return self

    @model_serializer(mode="wrap")
    def compatible_wire(self, handler):
        data = handler(self)
        # Preserve existing PAPER economics, ledger hashes and replay archives.
        # Omission always means PAPER; a venue mode is never omitted.
        if self.execution_mode == "PAPER":
            data.pop("execution_mode", None)
        return data
