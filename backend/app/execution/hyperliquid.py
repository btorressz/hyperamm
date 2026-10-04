from __future__ import annotations

import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from app.market_data.models import utcnow
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
        self.venue_changed=asyncio.Event()
        self.last_reconciled_at=None
        self.reconciliation_error=None
        self._orders: dict[str, StrategyOrder]={}

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
    def _normalize_for_sdk(exchange, req: OrderRequest) -> tuple[float, float]:
        asset=exchange.info.name_to_asset(req.market)
        sz_decimals=int(exchange.info.asset_to_sz_decimals[asset])
        size_quantum=Decimal(1).scaleb(-sz_decimals)
        size=req.size.quantize(size_quantum, rounding="ROUND_DOWN")
        if size <= 0:
            raise ValueError("size normalizes to zero for Hyperliquid asset precision")
        is_spot=asset >= 10_000
        max_px_decimals=(8 if is_spot else 6)-sz_decimals
        sig=float(f"{float(req.price):.5g}")
        price=round(sig, max_px_decimals)
        if price <= 0:
            raise ValueError("price normalizes to non-positive value")
        return price,float(size)


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

    async def _venue_client(self):
        self._require_enabled()
        if self._info is None:
            from hyperliquid.info import Info
            await asyncio.to_thread(self._exchange_client)
            self._info=await asyncio.to_thread(Info,self.base_url,False,timeout=10)
        if not self._subscriptions:
            loop=asyncio.get_running_loop()
            def changed(_message):
                # SDK callbacks run on its WS thread. Only wake the serialized
                # authoritative reader; never mutate orders from that thread.
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

    async def reconcile_venue(self):
        """Authoritative account snapshot, then status lookup for missing tracked IDs.

        Missing is not synonymous with cancelled. Unknown exposure remains
        cancellable and blocks new orders until resolved.
        """
        if not self._orders:
            return
        try:
            info=await self._venue_client()
            opened=await asyncio.to_thread(info.open_orders,self.account_address)
            if not isinstance(opened,list):
                raise ValueError("invalid venue open-order response")
            by_oid={str(item["oid"]):item for item in opened}
            for order in self._orders.values():
                if not self._active(order) and order.client_order_id not in self._needs_verification:
                    continue
                data=by_oid.get(order.venue_order_id)
                if data is not None:
                    self._apply_venue_order(order,data,"open")
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
            self.last_reconciled_at=utcnow()
            self.reconciliation_error=None
        except Exception as exc:
            self.reconciliation_error=str(exc)
            raise

    @staticmethod
    async def _transmit(method, *args):
        # Cancelling an asyncio waiter cannot stop a requests/SDK worker thread.
        # Keep the caller's execution lock held until the signed call finishes.
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
        exchange=await asyncio.to_thread(self._exchange_client)
        await self._venue_client()
        result=[]
        for req in orders:
            price,size=self._normalize_for_sdk(exchange,req)
            if self.authority is not None:
                await self.authority()
            # Record uncertain exposure BEFORE transmission, including timeouts.
            values=req.model_dump()
            values.update(price=Decimal(str(price)),size=Decimal(str(size)))
            order=StrategyOrder(**values,status=OrderStatus.UNKNOWN)
            self._orders[req.client_order_id]=order
            response=await self._transmit(
                exchange.order, req.market, req.side=="BID", size, price,
                {"limit":{"tif":"Alo"}}, False, self._cloid(req.client_order_id)
            )
            status,venue_order_id=self._parse_order_response(response)
            order.status=status; order.venue_order_id=venue_order_id; order.updated_at=utcnow()
            if status==OrderStatus.FILLED:
                order.filled_size=order.size
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
                    # A fill may win the cancellation race. Only venue terminal
                    # evidence makes that cancellation failure safe.
                    await self.reconcile_venue()
                    if self._active(order):
                        raise RuntimeError("venue did not confirm cancellation")
                else:
                    order.status=OrderStatus.CANCELLED; order.updated_at=utcnow()
                    self._needs_verification.add(order.client_order_id)
                result.append(order)
            except Exception as exc:
                failures.append(str(exc))
        if failures:
            raise RuntimeError("; ".join(failures))
        return result

    async def replace_orders(self, replacements):
        out=[]
        for cid, req in replacements:
            await self.cancel_orders([cid]); out.extend(await self.submit_orders([req]))
        return out

    async def get_open_orders(self):
        # Cache projection only: the manager reconciles before decisions and the
        # runtime also reconciles on WS events and on a five-second timer.
        return [o for o in self._orders.values() if self._active(o)]

    async def cancel_all(self):
        return await self.cancel_orders([o.client_order_id for o in await self.get_open_orders()])

    def all_orders(self):
        return list(self._orders.values())

    async def close(self):
        if self._info is not None and self._subscriptions:
            await asyncio.to_thread(self._info.disconnect_websocket)
            self._subscriptions=[]
            self._info=None
