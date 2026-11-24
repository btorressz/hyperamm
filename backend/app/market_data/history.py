from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from threading import Lock

from app.market_data.models import MarketSnapshot


def material_identity(snapshot: MarketSnapshot) -> tuple:
    """Economic normalized L2 identity; Decimal equality ignores wire formatting."""
    book = snapshot.book
    return (
        snapshot.market, snapshot.best_bid, snapshot.best_ask, snapshot.mid_price,
        tuple((x.price, x.size, x.order_count) for x in book.bids) if book else (),
        tuple((x.price, x.size, x.order_count) for x in book.asks) if book else (),
    )


@dataclass(frozen=True)
class MarketObservation:
    timestamp: datetime
    sequence: int
    mid_price: Decimal


class MarketPriceHistory:
    """Bounded accepted normalized observations for Phase 6's count-based RMS.

    Timestamp/sequence enforce ordering and deduplication, not time weighting.
    Distinct accepted observations with unchanged prices still count. There is
    no cadence resampling, interpolation, or expiry based on elapsed time.
    """

    def __init__(self, max_samples: int = 1000):
        if max_samples < 2:
            raise ValueError("max_samples must be >= 2")
        self._items: deque[MarketObservation] = deque(maxlen=max_samples)
        self._seen_sequences: set[int] = set()
        self._seen_timestamps: set[datetime] = set()
        self._version = 0
        self._material_identity = None
        self._latest_timestamp = None
        self._latest_sequence = -1
        self._evicted_through_timestamp: datetime | None = None

    @property
    def evicted_through_timestamp(self) -> datetime | None:
        """Latest discarded sample; horizons at/before it cannot be reconstructed."""
        return self._evicted_through_timestamp

    @property
    def version(self) -> int:
        return self._version

    def clear(self) -> None:
        if self._items:
            self._evicted_through_timestamp = max(
                self._evicted_through_timestamp or self._items[-1].timestamp,
                self._items[-1].timestamp,
            )
        self._items.clear()
        self._seen_sequences.clear()
        self._seen_timestamps.clear()
        self._material_identity = None
        self._latest_timestamp = None
        self._latest_sequence = -1
        self._version += 1

    def add_snapshot(self, snapshot: MarketSnapshot) -> bool:
        if snapshot.stale or snapshot.book is None or snapshot.mid_price is None:
            return False
        price = snapshot.mid_price
        if not price.is_finite() or price <= 0:
            return False
        timestamp = snapshot.latest_valid_update or snapshot.book.timestamp
        sequence = snapshot.book.sequence
        if self._latest_timestamp and timestamp < self._latest_timestamp:
            return False
        if sequence < self._latest_sequence:
            return False
        identity = material_identity(snapshot)
        changed = identity != self._material_identity
        self._material_identity = identity
        self._latest_timestamp = timestamp
        self._latest_sequence = sequence
        # Authority tracks the full book independently of midpoint sampling.
        if changed:
            self._version += 1
        if sequence in self._seen_sequences or timestamp in self._seen_timestamps:
            return False
        if self._items and (timestamp < self._items[-1].timestamp or sequence <= self._items[-1].sequence):
            return False
        if len(self._items) == self._items.maxlen:
            dropped = self._items[0]
            self._evicted_through_timestamp = max(
                self._evicted_through_timestamp or dropped.timestamp, dropped.timestamp,
            )
            self._seen_sequences.discard(dropped.sequence)
            self._seen_timestamps.discard(dropped.timestamp)
        self._items.append(MarketObservation(timestamp=timestamp, sequence=sequence, mid_price=price))
        self._seen_sequences.add(sequence)
        self._seen_timestamps.add(timestamp)
        if not changed:
            self._version += 1
        return True

    def prices(self, window: int) -> list[Decimal]:
        """Latest N accepted prices, irrespective of timestamp spacing."""
        if window < 2:
            raise ValueError("window must be >= 2")
        return [item.mid_price for item in list(self._items)[-window:]]

    def observations(self, window: int) -> list[MarketObservation]:
        if window < 2:
            raise ValueError("window must be >= 2")
        return list(self._items)[-window:]

    def __len__(self) -> int:
        return len(self._items)


MAX_WIRE_BYTES = 64 * 1024


def bounded_callback_wire(raw):
    """Bound traversal before serialization, including deeply nested/huge SDK values."""
    pending, nodes, text_size = [(raw, 0)], 0, 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > 8192 or depth > 16:
            raise ValueError('callback structure exceeds bound')
        if isinstance(value, str):
            text_size += len(value)
            if text_size > MAX_WIRE_BYTES:
                raise ValueError('callback text exceeds bound')
        elif type(value) in (dict, list):
            if len(value) > 8192 or len(pending) + len(value) * 2 > 16384:
                raise ValueError('callback container exceeds bound')
            if isinstance(value, dict):
                for key, child in value.items():
                    if not isinstance(key, str):
                        raise ValueError('callback keys must be strings')
                    pending.extend(((key, depth + 1), (child, depth + 1)))
            else:
                pending.extend((child, depth + 1) for child in value)
        elif type(value) is int and value.bit_length() > 256:
            raise ValueError('callback integer exceeds bound')
        elif value is not None and type(value) not in (bool, int, float):
            raise ValueError('unsupported callback value')
    wire = json.dumps(raw, separators=(',', ':'), allow_nan=False)
    if len(wire.encode('utf-8')) > MAX_WIRE_BYTES:
        raise ValueError('oversized callback')
    return wire


class BoundedIngress:
    """Bound retained wire data per market and coalesce pending loop wakeups."""

    def __init__(self, loop, capacity, clock, markets=None):
        if markets is None:
            from app.simulation.market_profiles import MARKETS

            markets = MARKETS
        self.loop, self.capacity, self.clock = loop, capacity, clock
        self.lock = Lock()
        self.queues = {market: deque() for market in markets}
        self.dropped = dict.fromkeys(self.queues, 0)
        self.event = asyncio.Event()
        self.scheduled = self.closed = self._wake_pending = False
        self._loss_count = self._peak = self._wakeups = 0

    def offer(self, market, kind, generation, raw):
        with self.lock:
            if self.closed:
                return
            full = len(self.queues[market]) >= self.capacity
        received = self.clock()
        try:
            wire = bounded_callback_wire(raw) if not full and type(raw) is dict else None
        except (ValueError, TypeError, RecursionError):
            wire = None
        with self.lock:
            if self.closed:
                return
            queue = self.queues[market]
            if wire is None or len(queue) >= self.capacity:
                self.dropped[market] += 1
                self._loss_count += 1
            else:
                queue.append((kind, generation, wire, received))
                self._peak = max(self._peak, len(queue))
            if not self.scheduled:
                self.scheduled = self._wake_pending = True
                self._wakeups += 1
                self.loop.call_soon_threadsafe(self._wake)

    def _wake(self):
        with self.lock:
            self._wake_pending = False
            if not self.closed and (any(self.queues.values()) or any(self.dropped.values())):
                self.event.set()
            else:
                self.scheduled = False

    def take(self):
        with self.lock:
            values = {market: tuple(queue) for market, queue in self.queues.items()}
            losses = self.dropped.copy()
            for queue in self.queues.values():
                queue.clear()
            self.dropped = dict.fromkeys(self.queues, 0)
            self.event.clear()
            self.scheduled = self._wake_pending
        return values, losses

    def has_loss(self, market):
        with self.lock:
            return self.dropped[market] > 0

    def metrics(self):
        with self.lock:
            return self._peak, self._wakeups, self._loss_count

    def close(self):
        with self.lock:
            self.closed = True
            for queue in self.queues.values():
                queue.clear()
