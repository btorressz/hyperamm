from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from .models import MarketDataMode, MarketSnapshot
from .mock import MockMarketDataAdapter
from .hyperliquid import HyperliquidMarketDataAdapter
from .history import material_identity


log=logging.getLogger(__name__)


class MarketDataService:
    def __init__(self, market: str, mode: MarketDataMode, stale_after_seconds: float = 5.0, demo_interval: float = 1.0):
        self.market = market
        self.mode = mode
        self.stale_after_seconds = stale_after_seconds
        self._snapshot = MarketSnapshot.unavailable(market, mode, "feed not started")
        self._lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._adapter = MockMarketDataAdapter(market, interval=demo_interval) if mode == MarketDataMode.DEMO else HyperliquidMarketDataAdapter(market, stale_after_seconds=stale_after_seconds)
        self._listeners: list = []
        self._perp_listeners: list = []
        self._source_sequence = -1
        self._source_timestamp = None
        self._material_sequence = 0
        self._material_identity = None

    async def _accept(self, snapshot: MarketSnapshot):
        async with self._lock:
            snapshot = snapshot.model_copy(deep=True)
            if snapshot.book:
                source_time = snapshot.latest_valid_update
                # LIVE ordering is exchange time, never the local material sequence.
                # Retain the watermark even across unavailable/reconnecting states.
                if self.mode == MarketDataMode.LIVE and source_time and self._source_timestamp and source_time < self._source_timestamp:
                    return
                if self.mode == MarketDataMode.DEMO and snapshot.book.sequence < self._source_sequence:
                    return
                self._source_sequence = snapshot.book.sequence
                if source_time:
                    self._source_timestamp = source_time
                identity = material_identity(snapshot)
                if identity != self._material_identity:
                    self._material_sequence = max(self._material_sequence + 1, snapshot.book.sequence)
                    self._material_identity = identity
                snapshot.book.sequence = self._material_sequence
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

    def add_perp_listener(self, listener):
        self._perp_listeners.append(listener)
        if hasattr(self._adapter, "add_perp_listener"):
            self._adapter.add_perp_listener(listener)

    async def start(self):
        async with self._lifecycle_lock:
            if self._task and not self._task.done():
                return
            self._task = asyncio.create_task(self._adapter.start(self._accept), name="market-data")

    async def stop(self):
        async with self._lifecycle_lock:
            await self._adapter.stop()
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
            async with self._lock:
                self._snapshot = MarketSnapshot.unavailable(self.market, self.mode, "feed stopped")

    async def snapshot(self) -> MarketSnapshot:
        async with self._lock:
            snap = self._snapshot.model_copy(deep=True)
        if snap.latest_valid_update:
            age = (datetime.now(timezone.utc) - snap.latest_valid_update).total_seconds()
            snap.stale = snap.stale or age < 0 or age > self.stale_after_seconds
        else:
            snap.stale = True
        return snap
