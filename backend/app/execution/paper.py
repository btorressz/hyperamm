from __future__ import annotations

from decimal import Decimal
from app.market_data.models import MarketSnapshot, utcnow
from .models import Fill, OrderRequest, OrderStatus, StrategyOrder
from .fills import FillStore, OrderHistory, ACTIVE_STATUSES


class PaperExecutionAdapter:
    def __init__(self, clock=utcnow):
        self.clock = clock
        self.fills = FillStore()
        self.orders = OrderHistory(pinned=self.fills.pins_order)
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

    def _fill(self, order: StrategyOrder, *, liquidity="MAKER"):
        fill_size = order.size - order.filled_size
        if fill_size <= 0:
            return
        order.filled_size = order.size
        order.status = OrderStatus.FILLED
        order.updated_at = self.clock()
        order.fill_source = "SIMULATED PAPER FILL"
        fill = Fill(
            client_order_id=order.client_order_id, market=order.market, side=order.side,
            price=order.price, size=fill_size, timestamp=self.clock(),
            liquidity=liquidity,
        )
        self.fills.add(fill)
        if self.on_fill is not None:
            self.on_fill(fill)
        self.orders.record(order)

    def _evaluate_open_orders(self):
        for order in list(self.orders.values()):
            if order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED} and self._crosses(order):
                self._fill(order)

    def position_base(self, market: str) -> Decimal:
        return self.fills.positions.get(market, Decimal("0"))

    @property
    def inventory_version(self) -> int:
        return self.fills.version

    @property
    def last_fill_at(self):
        return self.fills.last_fill_at

    async def submit_orders(self, orders: list[OrderRequest]) -> list[StrategyOrder]:
        result = []
        for req in orders:
            if req.client_order_id in self.orders:
                raise ValueError("execution client order identity already retained")
            self.fills.require_capacity()
            if any(o.status == OrderStatus.UNKNOWN for o in self.orders.values()):
                raise RuntimeError("unresolved PAPER execution exposure prevents submission")
            now=self.clock()
            order = StrategyOrder(**req.model_dump(),created_at=now,updated_at=now)
            self.orders[order.client_order_id] = order
            if self._crosses(order):
                self._fill(order, liquidity="TAKER")
            result.append(order)
        return result

    async def cancel_orders(self, client_order_ids: list[str]) -> list[StrategyOrder]:
        changed = []
        for cid in client_order_ids:
            order = self.orders.get(cid)
            if order and order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
                order.status = OrderStatus.CANCELLED
                order.updated_at = self.clock()
                self.orders.record(order)
                changed.append(order)
        return changed

    async def replace_orders(self, replacements: list[tuple[str, OrderRequest]]) -> list[StrategyOrder]:
        result = []
        for old_id, new_req in replacements:
            old = self.orders.get(old_id)
            if old and old.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
                old.status = OrderStatus.REPLACED
                old.updated_at = self.clock()
                self.orders.record(old)
            result.extend(await self.submit_orders([new_req]))
        return result

    async def get_open_orders(self) -> list[StrategyOrder]:
        return [o for o in self.orders.values() if o.status in ACTIVE_STATUSES]

    async def cancel_all(self):
        return await self.cancel_orders([o.client_order_id for o in await self.get_open_orders()])

    def all_orders(self):
        return list(self.orders.values())

    def recent_orders(self, limit=100):
        return self.orders.recent(limit)
