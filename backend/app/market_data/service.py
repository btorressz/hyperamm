from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from .models import MarketDataMode, MarketSnapshot
from .mock import MockMarketDataAdapter
from .hyperliquid import HyperliquidMarketDataAdapter


log=logging.getLogger(__name__)


class MarketDataService:
    def __init__(self, market: str, mode: MarketDataMode, stale_after_seconds: float = 5.0, demo_interval: float = 1.0):
        self.market = market
        self.mode = mode
        self.stale_after_seconds = stale_after_seconds
        self._snapshot = MarketSnapshot.unavailable(market, mode, "feed not started")
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._adapter = MockMarketDataAdapter(market, interval=demo_interval) if mode == MarketDataMode.DEMO else HyperliquidMarketDataAdapter(market)
        self._listeners: list = []

    async def _accept(self, snapshot: MarketSnapshot):
        async with self._lock:
            old_seq = self._snapshot.book.sequence if self._snapshot.book else -1
            new_seq = snapshot.book.sequence if snapshot.book else old_seq
            if self._snapshot.book and snapshot.book and new_seq < old_seq:
                return
            self._snapshot = snapshot
        for listener in list(self._listeners):
            try:
                result = listener(snapshot)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                log.warning("market-data listener failed", exc_info=True)

    def add_listener(self, listener):
        self._listeners.append(listener)

    async def start(self):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._adapter.start(self._accept), name="market-data")

    async def stop(self):
        await self._adapter.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def snapshot(self) -> MarketSnapshot:
        async with self._lock:
            snap = self._snapshot.model_copy(deep=True)
        if snap.latest_valid_update:
            age = (datetime.now(timezone.utc) - snap.latest_valid_update).total_seconds()
            snap.stale = age > self.stale_after_seconds
        else:
            snap.stale = True
        return snap
