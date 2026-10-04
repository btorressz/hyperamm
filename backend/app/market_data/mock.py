from __future__ import annotations

import asyncio
import math
from decimal import Decimal
from .models import MarketDataMode, MarketLevel, OrderBookSnapshot, MarketSnapshot, MarketConnectionState, utcnow


class MockMarketDataAdapter:
    """Deterministic demo feed. It never represents itself as live data."""

    def __init__(self, market: str = "ETH", start_price: Decimal = Decimal("3000"), interval: float = 1.0):
        self.market = market
        self.start_price = start_price
        self.interval = interval
        self._counter = 0
        self._running = False
        self._callback = None

    def snapshot_for(self, counter: int) -> MarketSnapshot:
        wave = Decimal(str(round(math.sin(counter / 6.0) * 4.0 + math.sin(counter / 17.0) * 2.0, 4)))
        mid = self.start_price + wave
        spread = Decimal("1.00")
        bid = mid - spread / 2
        ask = mid + spread / 2
        bids, asks = [], []
        for i in range(10):
            offset = Decimal(i) * Decimal("0.75")
            size = Decimal("0.25") + Decimal(i) * Decimal("0.08")
            bids.append(MarketLevel(price=bid-offset, size=size, order_count=i+1))
            asks.append(MarketLevel(price=ask+offset, size=size, order_count=i+1))
        now = utcnow()
        book = OrderBookSnapshot(market=self.market, bids=bids, asks=asks, timestamp=now, sequence=counter)
        return MarketSnapshot(
            market=self.market, best_bid=bid, best_ask=ask, mid_price=(bid+ask)/2,
            book=book, latest_valid_update=now, connection_state=MarketConnectionState.CONNECTED,
            mode=MarketDataMode.DEMO, simulated=True, stale=False,
            message="SIMULATED DEMO DATA",
        )

    async def start(self, callback):
        self._callback = callback
        self._running = True
        while self._running:
            self._counter += 1
            await callback(self.snapshot_for(self._counter))
            await asyncio.sleep(self.interval)

    async def stop(self):
        self._running = False
