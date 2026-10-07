from __future__ import annotations

import asyncio
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING, ROUND_DOWN, localcontext
from datetime import datetime, timezone
from app.market_data.models import utcnow
from app.market_data.perp_context import PerpPositionContext, normalize_user_position_context
from .fills import OrderHistory
from .models import OrderRequest, StrategyOrder, OrderStatus


class HyperliquidTestnetExecutionAdapter:
    """Guarded testnet-only adapter. Mainnet execution is deliberately absent."""

    def __init__(self, *, enabled: bool, private_key: str | None, account_address: str | None, base_url: str, venue_info=None, exchange=None):
        self.enabled=enabled
        self.private_key=private_key
        self.account_address=account_address
        self.base_url=base_url
        self.authority=None
        self._exchange=exchange
        self._info=venue_info
        self._subscriptions=[]
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
            raise PermissionError("Hyperliquid testnet order submission is disabled; set ENABLE_HYPERLIQUID_TESTNET_ORDERS=true")
        if self.base_url.rstrip("/") != "https://api.hyperliquid-testnet.xyz":
            raise PermissionError("testnet adapter refuses non-testnet base URL")
        if not self.private_key:
            raise PermissionError("HYPERLIQUID_PRIVATE_KEY is required for testnet order submission")

    def _exchange_client(self):
        self._require_enabled()
        if self._exchange is None:
            from eth_account import Account
            from hyperliquid.exchange import Exchange
            wallet=Account.from_key(self.private_key)
            self._exchange=Exchange(wallet, self.base_url, account_address=self.account_address or None, timeout=10)
            if not self.account_address:
                self.account_address=wallet.address
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
        sz_decimals=exchange.info.asset_to_sz_decimals[asset]
        max_decimals=8 if asset >= 10_000 else 6
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
        exchange=await asyncio.to_thread(self._exchange_client)
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
            return OrderStatus.OPEN, str(status["resting"]["oid"])
        if "filled" in status:
            return OrderStatus.FILLED, str(status["filled"].get("oid")) if status["filled"].get("oid") is not None else None
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
        try:
            info=await self._venue_client()
            state=await asyncio.to_thread(info.user_state,self.account_address)
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
        except Exception as exc:
            self._position_error=str(exc)
            raise

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

    def has_unknown_exposure(self) -> bool:
        return bool(self._needs_verification) or any(order.status == OrderStatus.UNKNOWN for order in self._orders.values())

    async def _venue_client(self):
        self._require_enabled()
        if self._info is None:
            from hyperliquid.info import Info
            await asyncio.to_thread(self._exchange_client)
            self._info=await asyncio.to_thread(Info,self.base_url,False,timeout=10)
        if not self._subscriptions:
            loop=asyncio.get_running_loop()
            def changed(_message):
                if not loop.is_closed():
                    loop.call_soon_threadsafe(self.venue_changed.set)
            for kind in ("orderUpdates","userFills"):
                subscription={"type":kind,"user":self.account_address}
                sid=await asyncio.to_thread(self._info.subscribe,subscription,changed)
                self._subscriptions.append((subscription,sid))
        return self._info

    @staticmethod
    def _active(order):
        return order.status in {OrderStatus.OPEN,OrderStatus.PARTIALLY_FILLED,OrderStatus.UNKNOWN}

    def _apply_venue_order(self, order, data, status, timestamp=None):
        if data.get("coin") != order.market:
            raise ValueError("venue order market mismatch")
        oid=str(data["oid"])
        if order.venue_order_id is not None and oid != order.venue_order_id:
            raise ValueError("venue order id mismatch")
        remaining=Decimal(str(data["sz"]))
        original=Decimal(str(data.get("origSz",order.size)))
        if not remaining.is_finite() or not original.is_finite() or not 0 <= remaining <= original or original != order.size:
            raise ValueError("invalid venue order size")
        filled=max(order.filled_size,original-remaining)
        if status == "open":
            mapped=OrderStatus.PARTIALLY_FILLED if filled > 0 else OrderStatus.OPEN
        elif status == "filled":
            mapped=OrderStatus.FILLED
            filled=order.size
        elif status.lower().endswith("canceled") or status == "expired":
            mapped=OrderStatus.CANCELLED
        elif status.lower().endswith("rejected"):
            mapped=OrderStatus.REJECTED
        else:
            raise ValueError(f"unsupported venue order status: {status}")
        if (order.status,order.filled_size,order.venue_order_id) != (mapped,filled,oid):
            order.status=mapped
            order.filled_size=filled
            order.venue_order_id=oid
            order.updated_at=datetime.fromtimestamp(timestamp/1000,timezone.utc) if timestamp else utcnow()
            if filled > 0:
                self._pending_accounting.add(order.client_order_id)
                self.venue_changed.set()

    async def reconcile_venue(self):
        if not self._orders:
            return
        try:
            info=await self._venue_client()
            opened=await asyncio.to_thread(info.open_orders,self.account_address)
            if not isinstance(opened,list):
                raise ValueError("invalid venue open-order response")
            by_oid={str(item["oid"]):item for item in opened}
            for order in list(self._orders.values()):
                if not self._active(order) and order.client_order_id not in self._needs_verification:
                    continue
                data=by_oid.get(order.venue_order_id)
                if data is not None:
                    self._apply_venue_order(order,data,"open")
                    self._needs_verification.discard(order.client_order_id)
                    self._orders.record(order)
                    continue
                if order.venue_order_id:
                    result=await asyncio.to_thread(info.query_order_by_oid,self.account_address,int(order.venue_order_id))
                else:
                    result=await asyncio.to_thread(info.query_order_by_cloid,self.account_address,self._cloid(order.client_order_id))
                if result.get("status") != "order":
                    if order.status != OrderStatus.UNKNOWN:
                        order.status=OrderStatus.UNKNOWN
                        order.updated_at=utcnow()
                    raise RuntimeError(f"venue order state unknown: {order.client_order_id}")
                update=result["order"]
                self._apply_venue_order(order,update["order"],update["status"],update.get("statusTimestamp"))
                self._needs_verification.discard(order.client_order_id)
                self._orders.record(order)
            self._orders.prune()
            self.last_reconciled_at=utcnow()
            self.reconciliation_error=None
        except Exception as exc:
            self.reconciliation_error=str(exc)
            raise

    @staticmethod
    async def _transmit(method, *args):
        task=asyncio.create_task(asyncio.to_thread(method,*args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            except Exception:
                pass
            raise

    async def submit_orders(self, orders: list[OrderRequest]) -> list[StrategyOrder]:
        self._require_enabled()
        if self.has_unknown_exposure() or self._pending_accounting:
            raise RuntimeError("unresolved venue/accounting exposure prevents submission")
        if self.authority is None:
            raise PermissionError("concrete request authority is required for TESTNET submission")
        exchange=await asyncio.to_thread(self._exchange_client)
        await self._venue_client()
        result=[]
        for req in orders:
            if self._pending_accounting:
                raise RuntimeError("unconsumed venue accounting evidence prevents submission")
            if req.client_order_id in self._orders:
                raise ValueError("execution client order identity already retained")
            # Isolate caller mutation across the authority await. The callback
            # receives its own copy; only the checked snapshot is serialized.
            req=req.model_copy(deep=True)
            normalized=self.normalize_order_request(exchange, req)
            if (normalized.price, normalized.size) != (req.price, req.size):
                raise ValueError("request is not already venue-normalized")
            checked=req.model_copy(deep=True)
            await self.authority(checked)
            if checked != req:
                raise ValueError("request changed during final authority check")
            price,size=self._normalize_for_sdk(exchange,req)
            cloid=self._cloid(req.client_order_id)
            order=StrategyOrder(**req.model_dump(),status=OrderStatus.UNKNOWN)
            self._orders[req.client_order_id]=order
            response=await self._transmit(
                exchange.order, req.market, req.side=="BID", size, price,
                {"limit":{"tif":"Alo"}}, False, cloid
            )
            status,venue_order_id=self._parse_order_response(response)
            order.status=status
            order.venue_order_id=venue_order_id
            order.updated_at=utcnow()
            if status==OrderStatus.FILLED:
                order.filled_size=order.size
                self._pending_accounting.add(order.client_order_id)
                self.venue_changed.set()
            self._orders.record(order)
            if status in {OrderStatus.REJECTED,OrderStatus.UNKNOWN}:
                raise RuntimeError(f"Hyperliquid strategy order status: {status}")
            result.append(order)
        return result

    async def cancel_orders(self, client_order_ids: list[str]):
        targets=[self._orders[cid] for cid in client_order_ids if cid in self._orders and self._active(self._orders[cid])]
        if not targets:
            return []
        exchange=await asyncio.to_thread(self._exchange_client)
        result=[]
        failures=[]
        for order in targets:
            try:
                response=await self._transmit(exchange.cancel_by_cloid,order.market,self._cloid(order.client_order_id))
                statuses=response.get("response",{}).get("data",{}).get("statuses",[])
                if response.get("status") != "ok" or statuses != ["success"]:
                    await self.reconcile_venue()
                    if self._active(order):
                        raise RuntimeError("venue did not confirm cancellation")
                else:
                    order.status=OrderStatus.CANCELLED
                    order.updated_at=utcnow()
                    self._needs_verification.add(order.client_order_id)
                self._orders.record(order)
                result.append(order)
            except Exception as exc:
                failures.append(str(exc))
        if failures:
            raise RuntimeError("; ".join(failures))
        return result

    async def replace_orders(self, replacements):
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
        if self._info is not None and self._subscriptions:
            await asyncio.to_thread(self._info.disconnect_websocket)
            self._subscriptions=[]
            self._info=None
