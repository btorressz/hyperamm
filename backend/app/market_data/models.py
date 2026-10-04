from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from pydantic import BaseModel, Field, model_validator


class MarketConnectionState(StrEnum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"
    DEGRADED = "DEGRADED"


class MarketDataMode(StrEnum):
    LIVE = "LIVE"
    DEMO = "DEMO"


class MarketLevel(BaseModel):
    price: Decimal = Field(gt=0)
    size: Decimal = Field(gt=0)
    order_count: int = Field(default=0, ge=0)


class OrderBookSnapshot(BaseModel):
    market: str
    bids: list[MarketLevel]
    asks: list[MarketLevel]
    timestamp: datetime
    sequence: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_book(self):
        if self.bids and self.asks and self.bids[0].price >= self.asks[0].price:
            raise ValueError("order book is crossed")
        return self


class MarketSnapshot(BaseModel):
    market: str
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    mid_price: Decimal | None = None
    book: OrderBookSnapshot | None = None
    latest_valid_update: datetime | None = None
    connection_state: MarketConnectionState = MarketConnectionState.DISCONNECTED
    mode: MarketDataMode = MarketDataMode.DEMO
    simulated: bool = False
    stale: bool = True
    message: str | None = None

    @classmethod
    def unavailable(cls, market: str, mode: MarketDataMode, message: str):
        return cls(market=market, mode=mode, simulated=(mode == MarketDataMode.DEMO), message=message)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
