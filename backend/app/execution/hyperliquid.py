from __future__ import annotations

import asyncio
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING, ROUND_DOWN, localcontext
from datetime import datetime, timezone
from enum import StrEnum
from app.market_data.models import utcnow
from app.market_data.perp_context import PerpPositionContext, normalize_user_position_context
from .fills import OrderHistory
from .models import OrderRequest, StrategyOrder, OrderStatus
from .venue_inventory import ACCOUNT, TESTNET_URL, InventoryError, VenueOrder, order_id, read_open_orders


class VenueReadiness(StrEnum):
    NOT_CHECKED = "NOT_CHECKED"
    CHECKING = "CHECKING"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"


class HyperliquidTestnetExecutionAdapter:
    """Guarded testnet-only adapter. Mainnet execution is deliberately absent."""

    _sdk_timeout = 15.0
    _inventory_max_age = 10.0
    _max_order_status_checks = 16

    def __init__(self, *, enabled: bool, private_key: str | None, account_address: str | None, base_url: str, venue_info=None, exchange=None):
        self.enabled=enabled
        self.private_key=private_key
        self.account_address=account_address
        self._configured_account = account_address
        self.base_url=base_url
        self.authority=None
        self._exchange=exchange
        self._info=venue_info
        self._owns_exchange = exchange is None
        self._owns_info = venue_info is None
        self._subscriptions = []
        self._sdk_lock = asyncio.Lock()
        self._sdk_worker = None
        self._cleanup_task = None
        self._closing = False
        self._subscription_generation = 0
        self._venue_revision = 0
        self._bound_account = None
        self._inventory_binding = None
        self._readiness = VenueReadiness.NOT_CHECKED
        self.unmanaged_order_count = None
        self._needs_verification=set()
        self._pending_accounting = set()
        self.venue_changed=asyncio.Event()
        self.last_reconciled_at=None
        self.reconciliation_error=None
        self._orders = OrderHistory(pinned=lambda cid: cid in self._needs_verification or cid in self._pending_accounting)
        self._positions: dict[str, Decimal]={}
        self._position_updated_at=None
        self._position_error=None
        self._position_version=0
        self._perp_position: PerpPositionContext | None = None
        self._account_value: Decimal | None = None
        self._total_margin_used: Decimal | None = None
        self._withdrawable: Decimal | None = None

    def _require_enabled(self):
        if not self.enabled:
            raise PermissionError("Hyperliquid TESTNET execution is disabled")
        if self.base_url.rstrip("/") != TESTNET_URL:
            raise PermissionError("TESTNET adapter refuses non-testnet base URL")

    @staticmethod
    def _require_submission_provenance():
        # There is no trusted source implementation in this release. Neither
        # an authority callback nor injected snapshot metadata is a source.
        raise PermissionError("TESTNET submission requires a qualified Testnet Core source")

    def _require_account(self):
        if (self.account_address != self._configured_account or not isinstance(self.account_address, str)
                or not ACCOUNT.fullmatch(self.account_address)):
            raise PermissionError("TESTNET requires an explicit venue account")
        return self.account_address

    def _exchange_client(self):
        if self._exchange is None:
            from eth_account import Account
            from hyperliquid.api import API
            from hyperliquid.exchange import Exchange

            if not self.private_key:
                raise PermissionError("TESTNET cancellation credentials unavailable")
            if not self._owns_info:
                raise PermissionError("owned TESTNET exchange requires owned account Info")
            wallet = Account.from_key(self.private_key)
            # SDK 0.24 Exchange.__init__ constructs a second Info inside an
            # assignment. Reuse the owned Info and initialize the fields used
            # by Exchange's native order/cancel methods and API transport.
            self._exchange = Exchange.__new__(Exchange)
            API.__init__(self._exchange, TESTNET_URL, timeout=10)
            self._exchange.wallet = wallet
            self._exchange.vault_address = None
            self._exchange.account_address = self._require_account()
            self._exchange.info = self._info
            self._exchange.expires_after = None
        if getattr(self._exchange, "base_url", None) != TESTNET_URL:
            raise PermissionError("TESTNET exchange endpoint mismatch")
        if getattr(self._exchange, "account_address", self.account_address) != self.account_address:
            raise PermissionError("TESTNET exchange account mismatch")
        return self._exchange

    @staticmethod
    def _cloid(client_order_id: str):
        import hashlib
        from hyperliquid.utils.types import Cloid
        raw="0x"+hashlib.md5(client_order_id.encode(), usedforsecurity=False).hexdigest()
        return Cloid.from_str(raw)

    @staticmethod
    def normalize_order_request(exchange, req: OrderRequest) -> OrderRequest:
        """Pure Decimal normalization; never move a quote toward the market.

        Hyperliquid: five significant figures for non-integer prices, at most
        (6 perps / 8 spot) - szDecimals fractional places; integer prices are
        permitted regardless of significant figures. Sizes use szDecimals.
        """
        if req.side not in {"BID", "ASK"}:
            raise ValueError("invalid Hyperliquid order side")
        if any(not v.is_finite() or v <= 0 for v in (req.price, req.size)):
            raise ValueError("Hyperliquid economics must be finite and positive")
        asset=exchange.info.name_to_asset(req.market)
        # This guarded adapter currently supports native perpetuals only.
        # Spot and HIP-3 asset IDs have distinct namespaces/precision rules;
        # rejecting them is safer than misclassifying builder perps as spot.
        if type(asset) is not int or not 0 <= asset < 10_000:
            raise ValueError("unsupported Hyperliquid instrument class: native perpetual only")
        sz_decimals=exchange.info.asset_to_sz_decimals[asset]
        max_decimals=6
        if type(sz_decimals) is not int or not 0 <= sz_decimals <= max_decimals:
            raise ValueError("unsupported Hyperliquid asset precision")
        with localcontext() as ctx:
            ctx.prec=max(28, *(len(v.as_tuple().digits) + max(0, v.adjusted()) + 10
                               for v in (req.price, req.size)))
            size=req.size.quantize(Decimal(1).scaleb(-sz_decimals), rounding=ROUND_DOWN)
            price=req.price
            if price != price.to_integral_value():
                exponent=max(-(max_decimals-sz_decimals), min(0, price.adjusted()-4))
                price=price.quantize(Decimal(1).scaleb(exponent),
                                     rounding=ROUND_FLOOR if req.side == "BID" else ROUND_CEILING)
        if size <= 0:
            raise ValueError("size normalizes to zero for Hyperliquid asset precision")
        if price <= 0:
            raise ValueError("price normalizes to non-positive value")
        return req.model_copy(update={"price":req.price if price == req.price else price,
                                      "size":req.size if size == req.size else size})

    async def normalize_quotes(self, market, quotes, *, center):
        self._require_submission_provenance()
        async with self._sdk_lock:
            exchange = await self._venue_exchange()
        out=[]
        for quote in quotes:
            req=OrderRequest(client_order_id="normalization-only", market=market,
                             side=quote.side, level_index=quote.level_index,
                             price=quote.price, size=quote.size)
            normalized=self.normalize_order_request(exchange, req)
            fair=quote.market_fair_value or center
            out.append(quote.model_copy(update={"price":normalized.price, "size":normalized.size,
                "distance_bps":abs(normalized.price-fair)/fair*Decimal("10000")}))
        return out

    @staticmethod
    def _normalize_for_sdk(exchange, req: OrderRequest) -> tuple[float, float]:
        """Conversion only: an unauthorized normalization is an error."""
        from hyperliquid.utils.signing import float_to_wire
        normalized=HyperliquidTestnetExecutionAdapter.normalize_order_request(exchange, req)
        if (normalized.price, normalized.size) != (req.price, req.size):
            raise ValueError("request is not already venue-normalized")
        price, size=float(req.price), float(req.size)
        if (Decimal(str(price)) != req.price or Decimal(str(size)) != req.size
                or Decimal(float_to_wire(price)) != req.price
                or Decimal(float_to_wire(size)) != req.size):
            raise ValueError("SDK serialization changes authorized economics")
        return price, size

    @staticmethod
    def _parse_order_response(response) -> tuple[OrderStatus, str | None]:
        if not isinstance(response, dict) or response.get("status") != "ok":
            return OrderStatus.UNKNOWN, None
        statuses = response.get("response", {}).get("data", {}).get("statuses", [])
        if not statuses or not isinstance(statuses[0], dict):
            return OrderStatus.UNKNOWN, None
        status = statuses[0]
        if "error" in status:
            return OrderStatus.REJECTED, None
        if "resting" in status and status["resting"].get("oid") is not None:
            return OrderStatus.OPEN, order_id(status["resting"]["oid"])
        if "filled" in status:
            return OrderStatus.FILLED, order_id(status["filled"]["oid"]) if status["filled"].get("oid") is not None else None
        return OrderStatus.UNKNOWN, None

    @staticmethod
    def normalize_user_position(user_state, market: str) -> Decimal:
        if not isinstance(user_state, dict):
            raise ValueError("invalid Hyperliquid user state")
        positions=user_state.get("assetPositions")
        if not isinstance(positions,list):
            raise ValueError("Hyperliquid user state missing assetPositions")
        return normalize_user_position_context(user_state, market).signed_position_base

    async def refresh_position(self, market: str) -> Decimal:
        async with self._sdk_lock:
            return await self._refresh_position(market)

    async def _refresh_position(self, market: str) -> Decimal:
        try:
            info=await self._venue_client()
            address = self._require_account()
            state = await self._sdk_call(info.user_state, address)
            self._check_binding(info, address)
            updated_at=utcnow()
            parsed=normalize_user_position_context(
                state, market, updated_at=updated_at, version=self._position_version
            )
            position=parsed.signed_position_base
            summary=state.get("marginSummary") or state.get("crossMarginSummary")
            if summary is not None and not isinstance(summary,dict):
                raise ValueError("invalid Hyperliquid margin summary")
            def optional_decimal(value,name):
                if value is None:return None
                result=Decimal(str(value))
                if not result.is_finite():raise ValueError(f"non-finite Hyperliquid {name}")
                return result
            self._account_value=optional_decimal(summary.get("accountValue") if summary else None,"account value")
            self._total_margin_used=optional_decimal(summary.get("totalMarginUsed") if summary else None,"total margin used")
            self._withdrawable=optional_decimal(state.get("withdrawable"),"withdrawable")
            previous=self._perp_position
            material_changed = (
                market not in self._positions
                or self._positions[market] != position
                or previous is None
                or previous.model_dump(exclude={"updated_at","version","stale"}) != parsed.model_dump(exclude={"updated_at","version","stale"})
            )
            if material_changed:
                self._position_version += 1
            self._positions[market]=position
            self._position_updated_at=updated_at
            self._perp_position=parsed.model_copy(update={"version":self._position_version})
            self._position_error=None
            return position
        except BaseException as exc:
            self._position_error = "TESTNET account position unavailable"
            self._retire_sdk()
            if isinstance(exc, asyncio.CancelledError):
                raise
            await self._wait_for_cleanup()
            raise RuntimeError(self._position_error) from None

    def perp_position_snapshot(self, market: str):
        if self._perp_position is None or self._perp_position.market != market:
            return None
        return self._perp_position.model_copy(deep=True)

    def account_risk_snapshot(self):
        if self._position_updated_at is None:
            return None
        return {
            "account_value":self._account_value,
            "total_margin_used":self._total_margin_used,
            "withdrawable":self._withdrawable,
            "updated_at":self._position_updated_at,
            "version":self._position_version,
        }

    def position_snapshot(self, market: str):
        if market not in self._positions or self._position_updated_at is None:
            return None
        return self._positions[market],self._position_updated_at,self._position_version,self._position_error

    @property
    def reconciliation_readiness(self):
        if self._readiness == VenueReadiness.VERIFIED:
            age = (utcnow() - self.last_reconciled_at).total_seconds()
            if (not 0 <= age <= self._inventory_max_age
                    or self._inventory_binding != self._current_binding()):
                return VenueReadiness.NOT_CHECKED
        return self._readiness

    def has_unknown_exposure(self) -> bool:
        return (self.reconciliation_readiness != VenueReadiness.VERIFIED
                or bool(self._needs_verification)
                or any(order.status == OrderStatus.UNKNOWN for order in self._orders.values()))

    def _current_binding(self):
        return (self.enabled, self.base_url, self.account_address, id(self._info),
                getattr(self._info, "base_url", None), self._subscription_generation, self._venue_revision)

    def _check_binding(self, info, address):
        if (self._closing or info is not self._info or address != self.account_address
                or self._bound_account != address):
            raise InventoryError("TESTNET account session changed")
        self._require_enabled()
        if getattr(info, "base_url", None) != TESTNET_URL:
            raise InventoryError("TESTNET inventory endpoint mismatch")

    async def _sdk_call(self, method, *args):
        if self._closing:
            raise RuntimeError("TESTNET SDK session is closed")
        # Keep the real worker reachable across cancellation or timeout.
        self._sdk_worker = asyncio.create_task(asyncio.to_thread(method, *args))
        try:
            return await asyncio.wait_for(asyncio.shield(self._sdk_worker), self._sdk_timeout)
        finally:
            if self._sdk_worker.done():
                if not self._sdk_worker.cancelled():
                    self._sdk_worker.exception()
                self._sdk_worker = None

    def _retire_sdk(self):
        self._subscription_generation += 1
        self.venue_changed.clear()
        self._readiness = VenueReadiness.BLOCKED
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._drain_sdk(), name="testnet-sdk-cleanup")
            # Retrieve failures even when the initiating caller was cancelled.
            self._cleanup_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())

    async def _drain_sdk(self):
        if self._sdk_worker is not None:
            await asyncio.gather(self._sdk_worker, return_exceptions=True)
            self._sdk_worker = None
        await asyncio.to_thread(self._release_sdk)

    def _release_sdk(self):
        incomplete = False
        for subscription, handle in self._subscriptions[:]:
            try:
                if self._info.unsubscribe(subscription.copy(), handle) is not False:
                    self._subscriptions.remove((subscription, handle))
            except Exception:
                # Closing an owned manager also retires handles that were
                # queued when the socket was disconnected.
                pass
        if self._owns_info and self._info is not None:
            manager = getattr(self._info, "ws_manager", None)
            if manager is not None:
                try:
                    # SDK stop() joins the ping sender without a deadline.
                    manager.stop_event.set()
                    manager.ws.close()
                except Exception:
                    incomplete = True
                # Join the manager first so it cannot launch ping after its join.
                for thread in (manager, getattr(manager, "ping_sender", None)):
                    if thread is not None:
                        try:
                            if thread.ident is not None:
                                thread.join(timeout=self._sdk_timeout / 4)
                            incomplete |= thread.is_alive()
                        except Exception:
                            incomplete = True
            if not incomplete:
                self._info.ws_manager = None
                self._subscriptions.clear()
        for client in (self._exchange if self._owns_exchange else None,
                       self._info if self._owns_info else None):
            session = getattr(client, "session", None)
            if session is not None:
                try:
                    session.close()
                    client.session = None
                except Exception:
                    incomplete = True
        if incomplete or self._subscriptions:
            raise RuntimeError("TESTNET SDK cleanup unconfirmed")
        if self._owns_info:
            self._info = None
        if self._owns_exchange:
            self._exchange = None
        self._bound_account = None

    async def _wait_for_cleanup(self):
        if self._cleanup_task is not None:
            await asyncio.wait_for(asyncio.shield(self._cleanup_task), self._sdk_timeout)
            self._cleanup_task = None

    def _initialize_venue(self, address, callback):
        if self._info is None:
            from hyperliquid.info import Info

            self._info = Info.__new__(Info)
            Info.__init__(self._info, TESTNET_URL, skip_ws=False, timeout=10)
        self._check_binding(self._info, address)
        for kind in ("orderUpdates", "userFills"):
            subscription = {"type": kind, "user": address}
            handle = self._info.subscribe(subscription.copy(), callback)
            self._subscriptions.append((subscription, handle))
        return self._info

    async def _venue_client(self):
        self._require_enabled()
        address = self._require_account()
        if self._closing:
            raise RuntimeError("TESTNET SDK session is closed")
        await self._wait_for_cleanup()
        if self._subscriptions:
            self._check_binding(self._info, address)
            return self._info
        self._bound_account = address
        self._subscription_generation += 1
        generation = self._subscription_generation
        loop = asyncio.get_running_loop()

        def notify():
            if generation == self._subscription_generation and not self._closing:
                self._venue_revision += 1
                self.venue_changed.set()

        def changed(_message):
            if generation == self._subscription_generation and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(notify)
                except RuntimeError:
                    pass

        try:
            return await self._sdk_call(self._initialize_venue, address, changed)
        except BaseException as exc:
            self._retire_sdk()
            if isinstance(exc, asyncio.CancelledError):
                raise
            await self._wait_for_cleanup()
            raise RuntimeError("TESTNET SDK initialization failed") from None

    async def _venue_exchange(self):
        await self._venue_client()
        try:
            return await self._sdk_call(self._exchange_client)
        except BaseException as exc:
            self._retire_sdk()
            if isinstance(exc, asyncio.CancelledError):
                raise
            await self._wait_for_cleanup()
            raise RuntimeError("TESTNET exchange initialization failed") from None

    @staticmethod
    def _active(order):
        return order.status in {OrderStatus.OPEN,OrderStatus.PARTIALLY_FILLED,OrderStatus.UNKNOWN}

    def _venue_order_update(self, order, row, status, timestamp=None):
        if (row.coin != order.market or row.side != order.side or row.price != order.price
                or row.original != order.size or (order.venue_order_id is not None and row.oid != order.venue_order_id)
                or (row.cloid is not None and row.cloid != self._cloid(order.client_order_id).to_raw())):
            raise InventoryError("venue order conflicts with retained ownership or economics")
        filled = row.original - row.remaining
        if filled < order.filled_size:
            raise InventoryError("venue fill evidence regressed")
        if status == "open":
            mapped = OrderStatus.PARTIALLY_FILLED if filled else OrderStatus.OPEN
        elif status == "filled" and not row.remaining:
            mapped = OrderStatus.FILLED
        elif status in {
            "canceled", "marginCanceled", "vaultWithdrawalCanceled", "openInterestCapCanceled",
            "selfTradeCanceled", "reduceOnlyCanceled", "siblingFilledCanceled", "delistedCanceled",
            "liquidatedCanceled", "scheduledCancel", "expired",
        }:
            mapped = OrderStatus.CANCELLED
        elif status in {
            "rejected", "tickRejected", "minTradeNtlRejected", "perpMarginRejected",
            "reduceOnlyRejected", "badAloPxRejected", "iocCancelRejected", "badTriggerPxRejected",
            "marketOrderNoLiquidityRejected", "positionIncreaseAtOpenInterestCapRejected",
            "positionFlipAtOpenInterestCapRejected", "tooAggressiveAtOpenInterestCapRejected",
            "openInterestIncreaseRejected", "insufficientSpotBalanceRejected", "oracleRejected",
            "perpMaxPositionRejected", "postOnlyRejected",
        }:
            mapped = OrderStatus.REJECTED
        else:
            raise InventoryError("unknown or contradictory venue order status")
        if (order.status, order.filled_size, order.venue_order_id) == (mapped, filled, row.oid):
            return {}
        return {"status": mapped, "filled_size": filled, "venue_order_id": row.oid,
                "updated_at": timestamp or utcnow()}

    def _apply_venue_update(self, order, update):
        if update.get("filled_size", order.filled_size) > order.filled_size:
            self._pending_accounting.add(order.client_order_id)
        for field, value in update.items():
            setattr(order, field, value)
        self._orders.record(order)

    async def reconcile_venue(self):
        async with self._sdk_lock:
            await self._reconcile_venue()

    async def _reconcile_venue(self):
        self._readiness = VenueReadiness.CHECKING
        self.unmanaged_order_count = None
        try:
            info = await self._venue_client()
            address = self._require_account()
            binding = self._current_binding()
            opened = await self._sdk_call(read_open_orders, info, address)
            self._check_binding(info, address)
            by_cloid = {row.cloid: row for row in opened.values() if row.cloid is not None}
            claimed = set()
            updates = []
            unresolved = None
            status_checks = 0
            terminal_oids = set()
            for order in list(self._orders.values()):
                cid = order.client_order_id
                if not self._active(order) and cid not in self._needs_verification:
                    continue
                try:
                    row = opened.get(order.venue_order_id) or by_cloid.get(self._cloid(cid).to_raw())
                    if row is not None:
                        if row.oid in claimed:
                            raise InventoryError("venue order has conflicting local owners")
                        update = self._venue_order_update(order, row, "open")
                        claimed.add(row.oid)
                        updates.append((order, update, False))
                        if cid in self._needs_verification:
                            unresolved = unresolved or InventoryError("venue cancellation still open")
                    else:
                        if status_checks >= self._max_order_status_checks:
                            raise InventoryError("venue order status check limit reached")
                        status_checks += 1
                        update = await self._resolve_missing_order(info, address, order)
                        oid = update.get("venue_order_id", order.venue_order_id)
                        if oid in opened or oid in terminal_oids:
                            raise InventoryError("venue terminal evidence conflicts with account inventory")
                        terminal_oids.add(oid)
                        updates.append((order, update, True))
                except InventoryError as exc:
                    if order.status != OrderStatus.UNKNOWN and cid not in self._needs_verification:
                        updates.append((order, {"status": OrderStatus.UNKNOWN, "updated_at": utcnow()}, False))
                    unresolved = unresolved or exc
            self._check_binding(info, address)
            if binding != self._current_binding():
                raise InventoryError("venue account inventory changed during reconciliation")
            for order, update, terminal in updates:
                self._apply_venue_update(order, update)
                if terminal:
                    self._needs_verification.discard(order.client_order_id)
            self.unmanaged_order_count = len(opened) - len(claimed)
            if self.unmanaged_order_count:
                raise InventoryError("unknown active orders in TESTNET account inventory")
            if unresolved is not None:
                raise unresolved
            self._orders.prune()
            self.last_reconciled_at = utcnow()
            self.reconciliation_error = None
            self._inventory_binding = binding
            self._readiness = VenueReadiness.VERIFIED
        except BaseException as exc:
            self._readiness = VenueReadiness.BLOCKED
            if not isinstance(exc, InventoryError):
                self.unmanaged_order_count = None
                if self._sdk_worker is not None:
                    self._retire_sdk()
            self.reconciliation_error = str(exc) if isinstance(exc, InventoryError) else "TESTNET account inventory unavailable"
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise RuntimeError(self.reconciliation_error) from None

    async def _resolve_missing_order(self, info, address, order):
        if order.venue_order_id is not None:
            result = await self._sdk_call(info.query_order_by_oid, address, int(order.venue_order_id))
        else:
            result = await self._sdk_call(info.query_order_by_cloid, address, self._cloid(order.client_order_id))
        if not isinstance(result, dict) or result.get("status") != "order" or not isinstance(result.get("order"), dict):
            raise InventoryError("venue order status unknown")
        update = result["order"]
        status = update.get("status")
        if not isinstance(status, str) or status == "open":
            raise InventoryError("venue status conflicts with missing open order")
        raw_time = update.get("statusTimestamp")
        if type(raw_time) is not int or not 0 < raw_time <= int(utcnow().timestamp() * 1000):
            raise InventoryError("invalid venue status timestamp")
        row = VenueOrder.parse(update.get("order"), address, active=False)
        if order.venue_order_id is None and row.cloid != self._cloid(order.client_order_id).to_raw():
            raise InventoryError("venue status lacks matching client order identity")
        return self._venue_order_update(order, row, status, datetime.fromtimestamp(raw_time / 1000, timezone.utc))

    async def submit_orders(self, orders: list[OrderRequest]) -> list[StrategyOrder]:
        self._require_enabled()
        self._require_submission_provenance()
        async with self._sdk_lock:
            return await self._submit_orders(orders)

    async def _submit_orders(self, orders):
        if self.authority is None:
            raise PermissionError("concrete request authority is required for TESTNET submission")
        if self._pending_accounting:
            raise RuntimeError("unconsumed venue accounting evidence prevents submission")
        result = []
        for req in orders:
            if self.reconciliation_readiness != VenueReadiness.VERIFIED:
                await self._reconcile_venue()
            if self.has_unknown_exposure() or self._pending_accounting:
                raise RuntimeError("unresolved venue/accounting exposure prevents submission")
            if req.client_order_id in self._orders:
                raise ValueError("execution client order identity already retained")
            req = req.model_copy(deep=True)
            exchange = await self._venue_exchange()
            price, size = self._normalize_for_sdk(exchange, req)
            checked = req.model_copy(deep=True)
            await self.authority(checked)
            if checked != req:
                raise ValueError("request changed during final authority check")
            self._require_submission_provenance()
            if (self._closing or exchange is not self._exchange or self.has_unknown_exposure()
                    or getattr(exchange, "base_url", None) != TESTNET_URL
                    or getattr(exchange, "account_address", None) != self.account_address):
                raise RuntimeError("TESTNET venue session or exposure changed during final authority")
            cloid = self._cloid(req.client_order_id)
            order = StrategyOrder(**req.model_dump(), status=OrderStatus.UNKNOWN)
            self._orders[req.client_order_id] = order
            self._readiness = VenueReadiness.NOT_CHECKED
            try:
                response = await self._sdk_call(exchange.order, req.market, req.side == "BID", size, price,
                                                {"limit": {"tif": "Alo"}}, False, cloid)
                status, venue_order_id = self._parse_order_response(response)
            except BaseException as exc:
                if self._sdk_worker is not None:
                    self._retire_sdk()
                if isinstance(exc, asyncio.CancelledError):
                    raise
                if isinstance(exc, TimeoutError):
                    raise TimeoutError("TESTNET submission unconfirmed") from None
                raise RuntimeError("TESTNET submission unconfirmed") from None
            order.status = status
            order.venue_order_id = venue_order_id
            order.updated_at = utcnow()
            if status == OrderStatus.FILLED:
                order.filled_size = order.size
                self._pending_accounting.add(order.client_order_id)
                self.venue_changed.set()
            self._orders.record(order)
            if status in {OrderStatus.REJECTED, OrderStatus.UNKNOWN}:
                raise RuntimeError(f"Hyperliquid strategy order status: {status}")
            result.append(order)
        return result

    async def cancel_orders(self, client_order_ids: list[str]):
        async with self._sdk_lock:
            return await self._cancel_orders(client_order_ids)

    async def _cancel_orders(self, client_order_ids):
        targets = [self._orders[cid] for cid in dict.fromkeys(client_order_ids)
                   if cid in self._orders and self._active(self._orders[cid])
                   and cid not in self._needs_verification]
        if not targets:
            return []
        exchange = await self._venue_exchange()
        result = []
        failures = False
        for order in targets:
            self._needs_verification.add(order.client_order_id)
            self._readiness = VenueReadiness.BLOCKED
            try:
                response = await self._sdk_call(exchange.cancel_by_cloid, order.market, self._cloid(order.client_order_id))
                statuses = response.get("response", {}).get("data", {}).get("statuses", [])
                if response.get("status") != "ok" or statuses != ["success"]:
                    await self._reconcile_venue()
                    if self._active(order):
                        raise RuntimeError("venue did not confirm cancellation")
                else:
                    order.status = OrderStatus.CANCELLED
                    order.updated_at = utcnow()
                self._orders.record(order)
                result.append(order)
            except asyncio.CancelledError:
                if self._sdk_worker is not None:
                    self._retire_sdk()
                raise
            except Exception:
                if self._sdk_worker is not None:
                    self._retire_sdk()
                    raise RuntimeError("venue did not confirm cancellation") from None
                failures = True
        if failures:
            raise RuntimeError("venue did not confirm cancellation")
        return result

    async def replace_orders(self, replacements):
        self._require_submission_provenance()
        out=[]
        for cid, req in replacements:
            await self.cancel_orders([cid])
            await self.reconcile_venue()
            if any(o.client_order_id == cid for o in await self.get_open_orders()):
                raise RuntimeError("replacement cancellation unconfirmed")
            out.extend(await self.submit_orders([req]))
        return out

    async def get_open_orders(self):
        return [o if self._active(o) else o.model_copy(update={"status": OrderStatus.UNKNOWN})
                for o in self._orders.values() if self._active(o) or o.client_order_id in self._needs_verification]

    async def cancel_all(self):
        return await self.cancel_orders([o.client_order_id for o in await self.get_open_orders()])

    def all_orders(self):
        return list(self._orders.values())

    def acknowledge_accounting(self, position, account):
        """Release only after Phase 11 consumed fresh authoritative account state.

        TESTNET has partial accounting, not a normalized trade ledger. Closed
        fill/order evidence therefore waits for independent position/account
        observation; active and verification state remains independently pinned.
        """
        if position is None or account is None or position.stale:
            return
        if account.get("account_value") is None or account.get("updated_at") is None:
            return
        for cid in tuple(self._pending_accounting):
            order = self._orders[cid]
            if (order.market == position.market and position.updated_at >= order.updated_at
                    and account["updated_at"] >= order.updated_at):
                self._pending_accounting.discard(cid)
        self._orders.prune()

    def recent_orders(self, limit=100):
        return [o if self._active(o) or o.client_order_id not in self._needs_verification
                else o.model_copy(update={"status": OrderStatus.UNKNOWN})
                for o in self._orders.recent(limit)]

    async def close(self):
        self._closing = True
        self._subscription_generation += 1
        self._readiness = VenueReadiness.BLOCKED
        self.venue_changed.clear()
        try:
            async with asyncio.timeout(self._sdk_timeout):
                async with self._sdk_lock:
                    self._retire_sdk()
                    await self._wait_for_cleanup()
        except TimeoutError:
            raise RuntimeError("TESTNET SDK cleanup unconfirmed") from None
