from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from .research import PaperExecutionAssumptions
from app.market_data.models import MarketSnapshot, utcnow
from .models import Fill, OrderRequest, OrderStatus, StrategyOrder
from .fills import FillStore, OrderHistory, ACTIVE_STATUSES


class PaperExecutionAdapter:
    def __init__(self, clock=utcnow, *, assumptions=None):
        self.assumptions = PaperExecutionAssumptions.model_validate_json(
            (assumptions or PaperExecutionAssumptions()).model_dump_json())
        self._pending_cancels = {}
        self._depth_key = None
        self._evidence_at = None
        self._depth_remaining = {}
        self._attempted = set()
        self.clock = clock
        self.fills = FillStore()
        self.orders = OrderHistory(pinned=self.fills.pins_order)
        self._market: MarketSnapshot | None = None
        self.on_fill = None

    def update_market(self, snapshot: MarketSnapshot, *, evidence_key=None, evidence_at=None):
        self._market = snapshot
        if self.assumptions.modeled:
            self._evidence_at = evidence_at if evidence_at is not None else (snapshot.book.timestamp if snapshot.book else None)
            # Replay supplies original book identity, so as-of context frames do
            # not replenish the same observed liquidity. Other simulations use
            # the complete snapshot identity. This never changes source values.
            from app.simulation.models import stable_fingerprint
            key = evidence_key if evidence_key is not None else stable_fingerprint(snapshot)
            if key != self._depth_key:
                self._depth_key = key
                self._depth_remaining = {}
                self._attempted.clear()
                if self._valid_depth(snapshot):
                    for side, levels in (("BID", snapshot.book.asks), ("ASK", snapshot.book.bids)):
                        for index, level in enumerate(levels if self.assumptions.depth_sensitive else levels[:1]):
                            self._depth_remaining[side, index] = level.size * self.assumptions.participation_rate
            self._settle_cancels()
        self._evaluate_open_orders()

    @staticmethod
    def _valid_depth(snapshot):
        book = snapshot.book
        if not book or book.market != snapshot.market or not book.bids or not book.asks:
            return False
        if (book.bids[0].price, book.asks[0].price) != (snapshot.best_bid, snapshot.best_ask):
            return False
        if any(not x.price.is_finite() or not x.size.is_finite() or x.price <= 0 or x.size <= 0
               for x in (*book.bids, *book.asks)):
            return False
        return (book.bids[0].price < book.asks[0].price
                and all(a.price > b.price for a, b in zip(book.bids, book.bids[1:]))
                and all(a.price < b.price for a, b in zip(book.asks, book.asks[1:])))

    @property
    def pending_cancellation_deadlines(self):
        return dict(self._pending_cancels)

    def cancellation_pending(self, cid):
        return cid in self._pending_cancels

    def _settle_cancels(self):
        for cid, deadline in list(self._pending_cancels.items()):
            order = self.orders.get(cid)
            if order is None or order.status not in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
                self._pending_cancels.pop(cid, None)
            elif self.clock() >= deadline:
                order.status = OrderStatus.CANCELLED
                order.updated_at = self.clock()
                self._pending_cancels.pop(cid, None)
                self.orders.record(order)

    def _modeled_fill(self, order):
        a = self.assumptions
        if (order.client_order_id in self._attempted or not self._market
                or order.market != self._market.market or not self._valid_depth(self._market)
                or self._evidence_at is None or self._evidence_at > self.clock()
                or self._evidence_at < order.created_at + timedelta(milliseconds=a.order_latency_ms)
                or self.clock() < order.created_at + timedelta(milliseconds=a.order_latency_ms)):
            return
        self._attempted.add(order.client_order_id)
        remaining = order.size - order.filled_size
        budget = remaining * a.max_fill_fraction
        levels = self._market.book.asks if order.side == "BID" else self._market.book.bids
        plan = []
        for index, level in enumerate(levels if a.depth_sensitive else levels[:1]):
            # Adverse modeled price must still respect the authorized limit.
            sign = Decimal(1) if order.side == "BID" else Decimal(-1)
            price = level.price * (Decimal(1) + sign * a.slippage_bps / Decimal(10000))
            if (order.side == "BID" and price > order.price) or (order.side == "ASK" and price < order.price):
                break
            size = min(budget, self._depth_remaining.get((order.side, index), Decimal(0)))
            if size > 0:
                plan.append((index, price, size))
                budget -= size
            if budget <= 0:
                break
        quantity = sum((size for _, _, size in plan), Decimal(0))
        if not quantity or (not a.allow_partial_fills and quantity < remaining):
            return
        # Per-level fills preserve exact price*size trade economics, avoiding a
        # rounded VWAP division. They share the existing accounting callback.
        for index, price, size in plan:
            self._depth_remaining[order.side, index] -= size
            self._fill(order, liquidity="TAKER", price=price, size=size,
                       source=f"HYPOTHETICAL MODELED PAPER FILL:{self._depth_key}:{index}")


    def _crosses(self, order: StrategyOrder) -> bool:
        if not self._market or self._market.stale:
            return False
        if self.assumptions.modeled and (order.market != self._market.market or not self._valid_depth(self._market)):
            return False
        if order.side == "BID" and self._market.best_ask is not None:
            return order.price >= self._market.best_ask
        if order.side == "ASK" and self._market.best_bid is not None:
            return order.price <= self._market.best_bid
        return False

    def _fill(self, order: StrategyOrder, *, liquidity="MAKER", price=None, size=None, source=None):
        fill_size = order.size - order.filled_size if size is None else size
        if fill_size <= 0:
            return
        order.filled_size += fill_size
        order.status = OrderStatus.FILLED if order.filled_size == order.size else OrderStatus.PARTIALLY_FILLED
        if order.status == OrderStatus.FILLED:
            self._pending_cancels.pop(order.client_order_id, None)
        order.updated_at = self.clock()
        order.fill_source = "HYPOTHETICAL MODELED PAPER FILL" if self.assumptions.modeled else "SIMULATED PAPER FILL"
        fill = Fill(
            client_order_id=order.client_order_id, market=order.market, side=order.side,
            price=order.price if price is None else price, size=fill_size, timestamp=self.clock(),
            source=source or order.fill_source,
            liquidity=liquidity,
        )
        self.fills.add(fill)
        if self.on_fill is not None:
            self.on_fill(fill)
        self.orders.record(order)

    def _evaluate_open_orders(self):
        for order in list(self.orders.values()):
            if order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED} and self._crosses(order):
                if self.assumptions.modeled:
                    self._modeled_fill(order)
                else:
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
            if self.assumptions.modeled and (req.side not in {"BID", "ASK"} or not req.price.is_finite()
                    or not req.size.is_finite() or req.price <= 0 or req.size <= 0):
                raise ValueError("invalid modeled PAPER order economics")
            if req.client_order_id in self.orders:
                raise ValueError("execution client order identity already retained")
            self.fills.require_capacity()
            if any(o.status == OrderStatus.UNKNOWN for o in self.orders.values()):
                raise RuntimeError("unresolved PAPER execution exposure prevents submission")
            now=self.clock()
            order = StrategyOrder(**req.model_dump(),created_at=now,updated_at=now)
            self.orders[order.client_order_id] = order
            if self._crosses(order):
                if self.assumptions.modeled:
                    self._modeled_fill(order)
                else:
                    self._fill(order, liquidity="TAKER")
            result.append(order)
        return result

    async def cancel_orders(self, client_order_ids: list[str]) -> list[StrategyOrder]:
        changed = []
        for cid in client_order_ids:
            order = self.orders.get(cid)
            if order and order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
                if self.assumptions.modeled and self.assumptions.cancel_latency_ms:
                    self._pending_cancels.setdefault(cid, self.clock() + timedelta(milliseconds=self.assumptions.cancel_latency_ms))
                    changed.append(order)
                    continue
                order.status = OrderStatus.CANCELLED
                order.updated_at = self.clock()
                self.orders.record(order)
                changed.append(order)
        return changed

    async def replace_orders(self, replacements: list[tuple[str, OrderRequest]]) -> list[StrategyOrder]:
        result = []
        for old_id, new_req in replacements:
            if self.assumptions.modeled:
                await self.cancel_orders([old_id])
                if self.cancellation_pending(old_id):
                    continue
                result.extend(await self.submit_orders([new_req]))
                continue
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
