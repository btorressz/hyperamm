from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any

from .models import MarketConnectionState, MarketDataMode, MarketLevel, MarketSnapshot, OrderBookSnapshot, utcnow

log = logging.getLogger(__name__)


class HyperliquidMarketDataAdapter:
    """Official hyperliquid-python-sdk adapter. Raw SDK payloads terminate here."""

    def __init__(self, market: str):
        self.market = market
        self._running = False
        self._info = None
        self._subscription_id = None
        self._sequence = 0
        self._latest_exchange_ms = -1

    @staticmethod
    def _normalize_book(market: str, payload: dict[str, Any], fallback_sequence: int) -> OrderBookSnapshot:
        data = payload.get("data", payload)
        levels = data.get("levels") or [[], []]
        exchange_ms = int(data.get("time") or 0)
        sequence = exchange_ms if exchange_ms > 0 else fallback_sequence
        bids = [
            MarketLevel(price=Decimal(str(x["px"])), size=Decimal(str(x["sz"])), order_count=int(x.get("n", 0)))
            for x in levels[0]
        ]
        asks = [
            MarketLevel(price=Decimal(str(x["px"])), size=Decimal(str(x["sz"])), order_count=int(x.get("n", 0)))
            for x in levels[1]
        ]
        return OrderBookSnapshot(market=market, bids=bids, asks=asks, timestamp=utcnow(), sequence=sequence)

    async def start(self, callback):
        self._running = True
        retry_seconds = 1.0
        while self._running:
            try:
                from hyperliquid.info import Info
                from hyperliquid.utils.constants import MAINNET_API_URL

                if retry_seconds > 1.0:
                    reconnecting = MarketSnapshot.unavailable(
                        self.market, MarketDataMode.LIVE, "Reconnecting to Hyperliquid public market data"
                    )
                    reconnecting.connection_state = MarketConnectionState.RECONNECTING
                    await callback(reconnecting)

                self._info = await asyncio.to_thread(Info, MAINNET_API_URL, False)
                loop = asyncio.get_running_loop()

                async def deliver(raw):
                    try:
                        data = raw.get("data", raw)
                        exchange_ms = int(data.get("time") or 0)
                        if exchange_ms and exchange_ms < self._latest_exchange_ms:
                            return
                        if exchange_ms:
                            self._latest_exchange_ms = exchange_ms
                        self._sequence += 1
                        book = self._normalize_book(self.market, raw, self._sequence)
                        if not book.bids or not book.asks:
                            return
                        bid, ask = book.bids[0].price, book.asks[0].price
                        await callback(
                            MarketSnapshot(
                                market=self.market,
                                best_bid=bid,
                                best_ask=ask,
                                mid_price=(bid + ask) / 2,
                                book=book,
                                latest_valid_update=utcnow(),
                                connection_state=MarketConnectionState.CONNECTED,
                                mode=MarketDataMode.LIVE,
                                simulated=False,
                                stale=False,
                            )
                        )
                    except Exception:
                        log.exception("failed to normalize Hyperliquid market update")

                def sdk_callback(raw):
                    asyncio.run_coroutine_threadsafe(deliver(raw), loop)

                self._subscription_id = self._info.subscribe({"type": "l2Book", "coin": self.market}, sdk_callback)
                raw = await asyncio.to_thread(self._info.l2_snapshot, self.market)
                await deliver(raw)
                retry_seconds = 1.0

                # The official SDK's WebsocketManager handles ordinary socket reconnects.
                # This outer loop handles adapter/client initialization failures.
                while self._running:
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Hyperliquid market-data attempt failed; retrying", exc_info=True)
                degraded = MarketSnapshot.unavailable(
                    self.market, MarketDataMode.LIVE, f"Hyperliquid unavailable: {exc}"
                )
                degraded.connection_state = MarketConnectionState.DEGRADED
                await callback(degraded)
                await self._unsubscribe_current()
                if self._running:
                    await asyncio.sleep(retry_seconds)
                    retry_seconds = min(retry_seconds * 2, 10.0)

    async def _unsubscribe_current(self):
        if self._info is not None and self._subscription_id is not None:
            try:
                await asyncio.to_thread(
                    self._info.unsubscribe, {"type": "l2Book", "coin": self.market}, self._subscription_id
                )
            except Exception:
                log.warning("Hyperliquid unsubscribe failed", exc_info=True)
        self._subscription_id = None
        self._info = None

    async def stop(self):
        self._running = False
        await self._unsubscribe_current()
