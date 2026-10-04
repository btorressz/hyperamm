from __future__ import annotations

import asyncio
from decimal import Decimal
from .models import OrderRequest, StrategyOrder, OrderStatus


class HyperliquidTestnetExecutionAdapter:
    """Guarded testnet-only adapter. Mainnet execution is deliberately absent."""

    def __init__(self, *, enabled: bool, private_key: str | None, account_address: str | None, base_url: str):
        self.enabled=enabled
        self.private_key=private_key
        self.account_address=account_address
        self.base_url=base_url
        self._exchange=None
        self._orders: dict[str, StrategyOrder]={}

    def _require_enabled(self):
        if not self.enabled:
            raise PermissionError("Hyperliquid testnet order submission is disabled; set ENABLE_HYPERLIQUID_TESTNET_ORDERS=true")
        if "testnet" not in self.base_url.lower():
            raise PermissionError("testnet adapter refuses non-testnet base URL")
        if not self.private_key:
            raise PermissionError("HYPERLIQUID_PRIVATE_KEY is required for testnet order submission")

    def _exchange_client(self):
        self._require_enabled()
        if self._exchange is None:
            from eth_account import Account
            from hyperliquid.exchange import Exchange
            wallet=Account.from_key(self.private_key)
            self._exchange=Exchange(wallet, self.base_url, account_address=self.account_address)
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
            return OrderStatus.REJECTED, None
        statuses = response.get("response", {}).get("data", {}).get("statuses", [])
        if not statuses or not isinstance(statuses[0], dict):
            return OrderStatus.REJECTED, None
        status = statuses[0]
        if "error" in status:
            return OrderStatus.REJECTED, None
        if "resting" in status:
            return OrderStatus.OPEN, str(status["resting"].get("oid"))
        if "filled" in status:
            return OrderStatus.FILLED, str(status["filled"].get("oid")) if status["filled"].get("oid") is not None else None
        return OrderStatus.REJECTED, None

    async def submit_orders(self, orders: list[OrderRequest]) -> list[StrategyOrder]:
        exchange=self._exchange_client()
        result=[]
        for req in orders:
            price,size=self._normalize_for_sdk(exchange,req)
            response=await asyncio.to_thread(
                exchange.order, req.market, req.side=="BID", size, price,
                {"limit":{"tif":"Alo"}}, False, self._cloid(req.client_order_id)
            )
            status,venue_order_id=self._parse_order_response(response)
            order=StrategyOrder(**req.model_dump(), status=status, venue_order_id=venue_order_id)
            self._orders[req.client_order_id]=order; result.append(order)
        return result

    async def cancel_orders(self, client_order_ids: list[str]):
        exchange=self._exchange_client(); result=[]
        for cid in client_order_ids:
            order=self._orders.get(cid)
            if order:
                await asyncio.to_thread(exchange.cancel_by_cloid, order.market, self._cloid(cid))
                order.status=OrderStatus.CANCELLED; result.append(order)
        return result

    async def replace_orders(self, replacements):
        # Conservative cancel/create semantics at this boundary; strategy reconciliation still avoids churn.
        out=[]
        for cid, req in replacements:
            await self.cancel_orders([cid]); out.extend(await self.submit_orders([req]))
        return out

    async def get_open_orders(self):
        return [o for o in self._orders.values() if o.status==OrderStatus.OPEN]

    async def cancel_all(self):
        return await self.cancel_orders([o.client_order_id for o in await self.get_open_orders()])
