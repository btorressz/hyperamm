from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any

from .history import material_identity
from .models import MarketConnectionState, MarketDataMode, MarketLevel, MarketSnapshot, OrderBookSnapshot, utcnow
from .perp_context import normalize_active_asset_ctx, normalize_meta_and_asset_ctxs

log = logging.getLogger(__name__)


class HyperliquidMarketDataAdapter:
    """Own the official SDK 0.24 WebSocket lifecycle; it does not reconnect itself."""

    def __init__(self, market: str, *, stale_after_seconds: float = 5.0):
        self.market = market
        self.stale_after_seconds = stale_after_seconds
        self._running = False
        self._runner = None
        self._stop_event = asyncio.Event()
        self._shutdown_lock = asyncio.Lock()
        self._shutdown_task = None
        self._info = None
        self._subscription_id = None
        self._perp_subscription_id = None
        self._sequence = 0
        self._material_identity = None
        self._latest_exchange_ms = -1
        self._perp_listeners: list = []
        self._health_interval = 0.25
        self._connect_timeout = 10.0
        self._shutdown_timeout = 5.0
        self._retry_initial = 1.0
        self._retry_max = 10.0

    def add_perp_listener(self, listener):
        self._perp_listeners.append(listener)

    async def _emit_perp(self, context):
        for listener in list(self._perp_listeners):
            result = listener(context)
            if asyncio.iscoroutine(result):
                await result

    @staticmethod
    def _normalize_book(market: str, payload: dict[str, Any], fallback_sequence: int) -> OrderBookSnapshot:
        data = payload.get("data", payload)
        if data.get("coin", market) != market:
            raise ValueError("wrong market in L2 update")
        levels = data.get("levels") or [[], []]
        bids = [
            MarketLevel(price=Decimal(str(x["px"])), size=Decimal(str(x["sz"])), order_count=int(x.get("n", 0)))
            for x in levels[0]
        ]
        asks = [
            MarketLevel(price=Decimal(str(x["px"])), size=Decimal(str(x["sz"])), order_count=int(x.get("n", 0)))
            for x in levels[1]
        ]
        return OrderBookSnapshot(market=market, bids=bids, asks=asks, timestamp=utcnow(), sequence=fallback_sequence)

    async def _deliver_book(self, raw, callback) -> bool:
        data = raw.get("data", raw)
        exchange_ms = int(data.get("time") or 0)
        if exchange_ms < self._latest_exchange_ms:
            return False
        source_time = datetime.fromtimestamp(exchange_ms / 1000, timezone.utc)
        age = (utcnow() - source_time).total_seconds()
        if exchange_ms <= 0 or age < 0 or age > self.stale_after_seconds:
            raise ValueError("fresh exchange timestamp required")
        book = self._normalize_book(self.market, raw, self._sequence)
        if not book.bids or not book.asks:
            raise ValueError("missing bid or ask")
        bid, ask = book.bids[0].price, book.asks[0].price
        snapshot = MarketSnapshot(
            market=self.market, best_bid=bid, best_ask=ask, mid_price=(bid + ask) / 2,
            book=book, latest_valid_update=source_time,
            connection_state=MarketConnectionState.CONNECTED, mode=MarketDataMode.LIVE,
            simulated=False, stale=False,
        )
        identity = material_identity(snapshot)
        if identity != self._material_identity:
            self._sequence += 1
            self._material_identity = identity
        book.sequence = self._sequence
        self._latest_exchange_ms = exchange_ms
        await callback(snapshot)
        return True

    @staticmethod
    async def _sdk_call(method, *args, **kwargs):
        # Cancelling an asyncio.to_thread await does not stop the worker. Drain it
        # before teardown so an initializing Info cannot start an orphan socket.
        task = asyncio.create_task(asyncio.to_thread(method, *args, **kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not task.cancelled():
                task.exception()  # Retrieve worker failure; cancellation still wins.
            raise

    async def _pause(self, seconds):
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except TimeoutError:
            pass

    @staticmethod
    def _socket_ready(info):
        manager = info.ws_manager
        if not manager.is_alive() or manager.stop_event.is_set():
            raise ConnectionError("SDK WebSocket manager terminated")
        if not manager.ping_sender.is_alive():
            if not manager.ws_ready and manager.ping_sender.ident is None:
                return False
            raise ConnectionError("SDK WebSocket ping sender terminated")
        if manager.ws_ready:
            sock = manager.ws.sock
            if not manager.ws.keep_running or sock is None or not sock.connected:
                raise ConnectionError("SDK WebSocket disconnected")
            return True
        return False

    async def _state(self, callback, state, message):
        snapshot = MarketSnapshot.unavailable(self.market, MarketDataMode.LIVE, message)
        snapshot.connection_state = state
        await callback(snapshot)

    async def start(self, callback):
        if self._runner is not None:
            raise RuntimeError("market adapter already started")
        self._runner = asyncio.current_task()
        self._running = True
        self._stop_event.clear()
        retry_seconds = self._retry_initial
        try:
            # Never replace an Info whose shutdown has not been verified.
            await self._unsubscribe_current()
            while self._running:
                try:
                    from hyperliquid.info import Info
                    from hyperliquid.utils.constants import MAINNET_API_URL

                    # SDK starts WebsocketManager before HTTP metadata loading.
                    # Own even the partially initialized instance if __init__ fails.
                    info = Info.__new__(Info)
                    self._info = info
                    await self._sdk_call(Info.__init__, info, MAINNET_API_URL, False, timeout=10)
                    if not self._running:
                        break
                    loop = asyncio.get_running_loop()
                    queue = asyncio.Queue()

                    def enqueue(kind, raw, *, owner=info, inbox=queue):
                        def put():
                            if self._running and self._info is owner:
                                inbox.put_nowait((kind, raw))
                        loop.call_soon_threadsafe(put)

                    deadline = loop.time() + self._connect_timeout
                    while self._running and not self._socket_ready(info):
                        if loop.time() >= deadline:
                            raise TimeoutError("SDK WebSocket connection timeout")
                        await self._pause(self._health_interval)
                    if not self._running:
                        break
                    self._subscription_id = await self._sdk_call(
                        info.subscribe, {"type": "l2Book", "coin": self.market},
                        lambda raw, send=enqueue: send("l2", raw),
                    )
                    if self._perp_listeners:
                        self._perp_subscription_id = await self._sdk_call(
                            info.subscribe, {"type": "activeAssetCtx", "coin": self.market},
                            lambda raw, send=enqueue: send("perp", raw),
                        )
                        bootstrap = await self._sdk_call(info.meta_and_asset_ctxs)
                        if not self._running:
                            break
                        await self._emit_perp(normalize_meta_and_asset_ctxs(bootstrap, self.market, updated_at=utcnow()))

                    # A fresh valid REST L2 snapshot is the recovery barrier. Queued
                    # pre-bootstrap messages cannot publish CONNECTED ahead of it.
                    raw = await self._sdk_call(info.l2_snapshot, self.market)
                    if not self._running:
                        break
                    self._socket_ready(info)
                    if not await self._deliver_book(raw, callback):
                        raise ValueError("post-reconnect snapshot predates accepted exchange state")
                    last_l2 = loop.time()
                    last_perp = last_l2
                    connected_at = last_l2
                    while self._running:
                        self._socket_ready(info)
                        if loop.time() - last_l2 > self.stale_after_seconds:
                            raise TimeoutError("Hyperliquid L2 feed stalled")
                        if self._perp_listeners and loop.time() - last_perp > self.stale_after_seconds:
                            raise TimeoutError("Hyperliquid perp context feed stalled")
                        # Reset backoff only after sustained healthy delivery, not a
                        # bootstrap immediately followed by another socket failure.
                        if loop.time() - connected_at > self.stale_after_seconds:
                            retry_seconds = self._retry_initial
                        try:
                            kind, raw = await asyncio.wait_for(queue.get(), timeout=self._health_interval)
                        except TimeoutError:
                            continue
                        if not self._running:
                            break
                        self._socket_ready(info)
                        if kind == "l2":
                            if await self._deliver_book(raw, callback):
                                last_l2 = loop.time()
                        else:
                            context = normalize_active_asset_ctx(raw, self.market, updated_at=utcnow())
                            await self._emit_perp(context)
                            last_perp = loop.time()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("Hyperliquid market-data attempt failed: %s", exc)
                    if self._running:
                        await self._state(callback, MarketConnectionState.DEGRADED, f"Hyperliquid unavailable: {exc}")
                finally:
                    # Disconnect and verify both SDK threads before another Info.
                    await self._unsubscribe_current()
                if self._running:
                    await self._state(callback, MarketConnectionState.RECONNECTING, "Reconnecting to Hyperliquid public market data")
                    await self._pause(retry_seconds)
                    retry_seconds = min(retry_seconds * 2, self._retry_max)
        finally:
            self._running = False
            self._stop_event.set()
            try:
                await self._unsubscribe_current()
            finally:
                self._runner = None

    def _shutdown_sdk(self, info, subscriptions):
        try:
            for subscription, subscription_id in subscriptions:
                if subscription_id is None:
                    continue
                try:
                    info.unsubscribe(subscription, subscription_id)
                except Exception:
                    log.warning("Hyperliquid unsubscribe failed", exc_info=True)
        finally:
            manager = getattr(info, "ws_manager", None)
            if manager is not None:
                info.disconnect_websocket()
                # SDK stop() joins ping_sender, but does not join the manager.
                for thread in (manager, manager.ping_sender):
                    if thread.ident is not None:
                        thread.join(timeout=self._shutdown_timeout)
                    if thread.is_alive():
                        raise RuntimeError("SDK WebSocket thread did not terminate")

    async def _unsubscribe_current(self):
        async with self._shutdown_lock:
            if self._info is None:
                return
            if self._shutdown_task is None:
                subscriptions = [
                    ({"type": "l2Book", "coin": self.market}, self._subscription_id),
                    ({"type": "activeAssetCtx", "coin": self.market}, self._perp_subscription_id),
                ]
                self._shutdown_task = asyncio.create_task(asyncio.to_thread(self._shutdown_sdk, self._info, subscriptions))
            # Shield timeout/cancellation: retain ownership while SDK shutdown runs.
            await asyncio.wait_for(asyncio.shield(self._shutdown_task), timeout=self._shutdown_timeout * 3)
            self._subscription_id = None
            self._perp_subscription_id = None
            self._info = None
            self._shutdown_task = None

    async def stop(self):
        self._running = False
        self._stop_event.set()
        runner = self._runner
        if runner is not None and runner is not asyncio.current_task():
            await asyncio.shield(runner)
        else:
            await self._unsubscribe_current()
