from __future__ import annotations

from decimal import Decimal
from app.market_data.models import MarketSnapshot, utcnow
from .models import Fill, OrderRequest, OrderStatus, StrategyOrder
from .fills import FillStore


class PaperExecutionAdapter:
    def __init__(self):
        self.orders: dict[str, StrategyOrder] = {}
        self.fills = FillStore()
        self._market: MarketSnapshot | None = None
        self.on_fill = None

    def update_market(self, snapshot: MarketSnapshot):
        self._market = snapshot
        self._evaluate_open_orders()

    def _crosses(self, order: StrategyOrder) -> bool:
        if not self._market or self._market.stale:
            return False
        if order.side == "BID" and self._market.best_ask is not None:
            return order.price >= self._market.best_ask
        if order.side == "ASK" and self._market.best_bid is not None:
            return order.price <= self._market.best_bid
        return False

    def _fill(self, order: StrategyOrder):
        fill_size = order.size - order.filled_size
        if fill_size <= 0:
            return
        order.filled_size = order.size
        order.status = OrderStatus.FILLED
        order.updated_at = utcnow()
        order.fill_source = "SIMULATED PAPER FILL"
        fill = Fill(
            client_order_id=order.client_order_id, market=order.market, side=order.side,
            price=order.price, size=fill_size,
        )
        self.fills.add(fill)
        if self.on_fill is not None:
            self.on_fill(fill)

    def _evaluate_open_orders(self):
        for order in self.orders.values():
            if order.status == OrderStatus.OPEN and self._crosses(order):
                self._fill(order)

    def position_base(self, market: str) -> Decimal:
        position = Decimal("0")
        for fill in self.fills.all():
            if fill.market != market:
                continue
            position += fill.size if fill.side == "BID" else -fill.size
        return position

    @property
    def inventory_version(self) -> int:
        return len(self.fills.all())

    @property
    def last_fill_at(self):
        fills = self.fills.all()
        return fills[-1].timestamp if fills else None

    async def submit_orders(self, orders: list[OrderRequest]) -> list[StrategyOrder]:
        result = []
        for req in orders:
            order = StrategyOrder(**req.model_dump())
            self.orders[order.client_order_id] = order
            if self._crosses(order):
                self._fill(order)
            result.append(order)
        return result

    async def cancel_orders(self, client_order_ids: list[str]) -> list[StrategyOrder]:
        changed = []
        for cid in client_order_ids:
            order = self.orders.get(cid)
            if order and order.status == OrderStatus.OPEN:
                order.status = OrderStatus.CANCELLED
                order.updated_at = utcnow()
                changed.append(order)
        return changed

    async def replace_orders(self, replacements: list[tuple[str, OrderRequest]]) -> list[StrategyOrder]:
        result = []
        for old_id, new_req in replacements:
            old = self.orders.get(old_id)
            if old and old.status == OrderStatus.OPEN:
                old.status = OrderStatus.REPLACED
                old.updated_at = utcnow()
            result.extend(await self.submit_orders([new_req]))
        return result

    async def get_open_orders(self) -> list[StrategyOrder]:
        return [o for o in self.orders.values() if o.status == OrderStatus.OPEN]

    async def cancel_all(self):
        return await self.cancel_orders([o.client_order_id for o in await self.get_open_orders()])

    def all_orders(self):
        return list(self.orders.values())
