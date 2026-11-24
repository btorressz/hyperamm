from __future__ import annotations

import asyncio
import logging
import json
from decimal import Decimal
from datetime import datetime, timezone
from threading import Event
from typing import Any

from .history import BoundedIngress, material_identity
from .models import MarketConnectionState, MarketDataMode, MarketLevel, MarketSnapshot, OrderBookSnapshot, utcnow
from .provider_budget import ProviderAdmissionError
from .perp_context import normalize_active_asset_ctx, normalize_meta_and_asset_ctxs

log = logging.getLogger(__name__)


class HyperliquidMarketDataAdapter:
    """Own the official SDK 0.24 WebSocket lifecycle; it does not reconnect itself."""

    INGRESS_CAPACITY = 8

    def __init__(self, market: str, *, stale_after_seconds: float = 5.0, budget=None):
        self.market = market
        self.stale_after_seconds = stale_after_seconds
        self._running = False
        self._runner = None
        self._stop_event = asyncio.Event()
        self._shutdown_lock = asyncio.Lock()
        self._shutdown_task = None
        self._info = None
        self._ingress = None
        self._budget = budget
        self._cancel_http = Event()
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

    @property
    def ingress_gap(self):
        inbox = self._ingress
        return inbox is not None and inbox.metrics()[2] > 0

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
        if data.get("coin") != market:
            raise ValueError("wrong market in L2 update")
        levels = data.get("levels")
        if (not isinstance(levels, list) or len(levels) != 2
                or any(not isinstance(side, list) or not 1 <= len(side) <= 100 for side in levels)):
            raise ValueError("invalid bounded L2 depth")
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
        exchange_ms = data.get("time")
        if type(exchange_ms) is not int or exchange_ms <= 0:
            raise ValueError("valid exchange milliseconds required")
        if exchange_ms < self._latest_exchange_ms:
            return False
        source_time = datetime.fromtimestamp(exchange_ms / 1000, timezone.utc)
        age = (utcnow() - source_time).total_seconds()
        if age < 0 or age > self.stale_after_seconds:
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

    def _initialize_sdk(self, info, sdk_class, url):
        if self._budget is None:
            sdk_class.__init__(info, url, skip_ws=False, timeout=10)
            return
        from hyperliquid.websocket_manager import WebsocketManager

        # Finish admitted SDK metadata before opening a WebSocket. A budget
        # denial during initialization leaves only an owned HTTP session to close.
        sdk_class.__init__(info, url, skip_ws=True, timeout=10)
        if not self._cancel_http.is_set():
            info.ws_manager = WebsocketManager(info.base_url)
            info.ws_manager.start()

    async def start(self, callback):
        if self._runner is not None:
            raise RuntimeError("market adapter already started")
        self._runner = asyncio.current_task()
        self._running = True
        self._stop_event.clear()
        self._cancel_http.clear()
        retry_seconds = self._retry_initial
        gap_watermark = -1
        try:
            # Never replace an Info whose shutdown has not been verified.
            await self._unsubscribe_current()
            while self._running:
                inbox = None
                cooldown = 0
                try:
                    from hyperliquid.info import Info
                    from hyperliquid.utils.constants import MAINNET_API_URL

                    # Own even the partially initialized instance if __init__ fails.
                    info = Info.__new__(Info)
                    self._info = info
                    if self._budget is not None:
                        self._budget.bind_sdk(info, "operational", 10, cancel=self._cancel_http)
                    await self._sdk_call(self._initialize_sdk, info, Info, MAINNET_API_URL)
                    if not self._running:
                        break
                    loop = asyncio.get_running_loop()
                    inbox = self._ingress = BoundedIngress(loop, self.INGRESS_CAPACITY, utcnow, (self.market,))

                    def enqueue(kind, raw, *, owner=inbox):
                        if isinstance(raw, dict) and raw.get("channel") == "subscriptionResponse":
                            return
                        # The SDK dispatches by channel and coin. Verify both at
                        # this boundary before retaining a callback.
                        channel = "l2Book" if kind == "l2" else "activeAssetCtx"
                        if isinstance(raw, dict) and raw.get("channel", channel) == channel:
                            data = raw.get("data", raw)
                            if isinstance(data, dict) and data.get("coin") == self.market:
                                owner.offer(self.market, kind, 0, raw)
                                return
                        owner.offer(self.market, kind, 0, None)

                    def require_continuity():
                        nonlocal gap_watermark
                        if inbox.metrics()[2]:
                            gap_watermark = self._latest_exchange_ms
                            raise ValueError("callback gap requires a fresh recovery snapshot")

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
                    bootstrap_context = None
                    if self._perp_listeners:
                        self._perp_subscription_id = await self._sdk_call(
                            info.subscribe, {"type": "activeAssetCtx", "coin": self.market},
                            lambda raw, send=enqueue: send("perp", raw),
                        )
                        bootstrap = await self._sdk_call(info.meta_and_asset_ctxs)
                        if not self._running:
                            break
                        bootstrap_context = normalize_meta_and_asset_ctxs(bootstrap, self.market, updated_at=utcnow())

                    # A fresh valid REST L2 snapshot is the recovery barrier. Queued
                    # pre-bootstrap messages cannot publish CONNECTED ahead of it.
                    raw = await self._sdk_call(info.l2_snapshot, self.market)
                    if not self._running:
                        break
                    self._socket_ready(info)
                    require_continuity()
                    payload = raw.get("data", raw)
                    if gap_watermark >= 0 and (type(payload.get("time")) is not int or payload["time"] <= gap_watermark):
                        raise ValueError("recovery snapshot does not advance the gap watermark")
                    if bootstrap_context is not None:
                        if (utcnow() - bootstrap_context.updated_at).total_seconds() > self.stale_after_seconds:
                            raise TimeoutError("Hyperliquid bootstrap context stalled")
                        await self._emit_perp(bootstrap_context)
                    if not self._running:
                        break
                    require_continuity()
                    if not await self._deliver_book(raw, callback):
                        raise ValueError("post-reconnect snapshot predates accepted exchange state")
                    connected_at = loop.time()
                    last_l2 = datetime.fromtimestamp(self._latest_exchange_ms / 1000, timezone.utc)
                    last_perp = bootstrap_context.updated_at if bootstrap_context is not None else utcnow()
                    while self._running:
                        require_continuity()
                        self._socket_ready(info)
                        now = utcnow()
                        if (now - last_l2).total_seconds() > self.stale_after_seconds:
                            raise TimeoutError("Hyperliquid L2 feed stalled")
                        if self._perp_listeners and (now - last_perp).total_seconds() > self.stale_after_seconds:
                            raise TimeoutError("Hyperliquid perp context feed stalled")
                        if loop.time() - connected_at > self.stale_after_seconds:
                            retry_seconds = self._retry_initial
                        try:
                            await asyncio.wait_for(inbox.event.wait(), timeout=self._health_interval)
                        except TimeoutError:
                            continue
                        batches, _ = inbox.take()
                        # A loss in the drained batch also latches the generation gap.
                        require_continuity()
                        for kind, _, wire, received in batches[self.market]:
                            if not self._running:
                                break
                            require_continuity()
                            self._socket_ready(info)
                            if not 0 <= (utcnow() - received).total_seconds() <= self.stale_after_seconds:
                                raise TimeoutError("Hyperliquid callback receipt expired")
                            raw = json.loads(wire)
                            if kind == "l2":
                                if await self._deliver_book(raw, callback):
                                    last_l2 = datetime.fromtimestamp(self._latest_exchange_ms / 1000, timezone.utc)
                            elif received >= last_perp:
                                context = normalize_active_asset_ctx(raw, self.market, updated_at=received)
                                await self._emit_perp(context)
                                last_perp = received
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if getattr(exc, "status_code", None) == 429 or (
                        isinstance(exc, ProviderAdmissionError) and exc.code == "RATE_LIMITED"
                    ):
                        cooldown = 30
                    # Provider payloads and exceptions from the SDK can contain wire data.
                    log.warning("Hyperliquid market-data attempt failed (%s)", type(exc).__name__)
                    if self.ingress_gap:
                        gap_watermark = max(gap_watermark, self._latest_exchange_ms)
                    if self._running:
                        reason = "Hyperliquid callback gap" if self.ingress_gap else "Hyperliquid public data unavailable"
                        await self._state(callback, MarketConnectionState.DEGRADED, reason)
                finally:
                    if inbox is not None:
                        inbox.close()
                    # Disconnect and verify both SDK threads before another Info.
                    await self._unsubscribe_current()
                if self._running:
                    await self._state(callback, MarketConnectionState.RECONNECTING, "Reconnecting to Hyperliquid public market data")
                    await self._pause(max(retry_seconds, cooldown))
                    retry_seconds = min(retry_seconds * 2, self._retry_max)
        except asyncio.CancelledError:
            if self._running:
                raise
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
            try:
                manager = getattr(info, "ws_manager", None)
                if manager is not None:
                    # Signal and bound the ping join before SDK stop(), which
                    # otherwise joins without a timeout.
                    manager.stop_event.set()
                    ping = manager.ping_sender
                    if ping.ident is not None:
                        ping.join(timeout=self._shutdown_timeout)
                    if ping.is_alive():
                        raise RuntimeError("SDK WebSocket ping thread did not terminate")
                    info.disconnect_websocket()
                    if manager.ident is not None:
                        manager.join(timeout=self._shutdown_timeout)
                    if manager.is_alive():
                        raise RuntimeError("SDK WebSocket thread did not terminate")
            finally:
                session = getattr(info, "session", None)
                if session is not None:
                    session.close()

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
        self._cancel_http.set()
        if self._budget is not None:
            self._budget.wake()
        if self._ingress is not None:
            self._ingress.close()
        runner = self._runner
        if runner is not None and runner is not asyncio.current_task():
            runner.cancel()
            await asyncio.shield(runner)
        else:
            await self._unsubscribe_current()
