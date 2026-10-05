from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.market_data.models import MarketSnapshot


@dataclass(frozen=True)
class MarketObservation:
    timestamp: datetime
    sequence: int
    mid_price: Decimal


class MarketPriceHistory:
    """Bounded, deterministic normalized mid-price history for Phase 6."""

    def __init__(self, max_samples: int = 1000):
        if max_samples < 2:
            raise ValueError("max_samples must be >= 2")
        self._items: deque[MarketObservation] = deque(maxlen=max_samples)
        self._seen_sequences: set[int] = set()
        self._seen_timestamps: set[datetime] = set()
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def clear(self) -> None:
        self._items.clear()
        self._seen_sequences.clear()
        self._seen_timestamps.clear()
        self._version += 1

    def add_snapshot(self, snapshot: MarketSnapshot) -> bool:
        if snapshot.stale or snapshot.book is None or snapshot.mid_price is None:
            return False
        price = snapshot.mid_price
        if not price.is_finite() or price <= 0:
            return False
        timestamp = snapshot.latest_valid_update or snapshot.book.timestamp
        sequence = snapshot.book.sequence
        if sequence in self._seen_sequences or timestamp in self._seen_timestamps:
            return False
        if self._items and (timestamp < self._items[-1].timestamp or sequence <= self._items[-1].sequence):
            return False
        if len(self._items) == self._items.maxlen:
            dropped = self._items[0]
            self._seen_sequences.discard(dropped.sequence)
            self._seen_timestamps.discard(dropped.timestamp)
        self._items.append(MarketObservation(timestamp=timestamp, sequence=sequence, mid_price=price))
        self._seen_sequences.add(sequence)
        self._seen_timestamps.add(timestamp)
        self._version += 1
        return True

    def prices(self, window: int) -> list[Decimal]:
        if window < 2:
            raise ValueError("window must be >= 2")
        return [item.mid_price for item in list(self._items)[-window:]]

    def observations(self, window: int) -> list[MarketObservation]:
        if window < 2:
            raise ValueError("window must be >= 2")
        return list(self._items)[-window:]

    def __len__(self) -> int:
        return len(self._items)
