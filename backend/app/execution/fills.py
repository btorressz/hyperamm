from collections import OrderedDict
from itertools import islice
from decimal import Decimal

from .models import Fill


ACTIVE_STATUSES = {"OPEN", "PARTIALLY_FILLED", "UNKNOWN"}
CLOSED_ORDER_LIMIT = 1000
FILL_HISTORY_LIMIT = 1000


class OrderHistory(dict):
    """Authoritative active/pinned state plus bounded closed observation rows.

    Adapters call record after each transition. A pin is independent of status:
    cancellation verification and unconsumed fill evidence cannot be evicted.
    """
    def __init__(self, *, limit=CLOSED_ORDER_LIMIT, pinned=None, observer=None):
        super().__init__()
        self.limit = limit
        self.pinned = pinned or (lambda cid: False)
        self.observer = observer
        self._closed = OrderedDict()

    def __setitem__(self, cid, order):
        super().__setitem__(cid, order)
        self.record(order)

    def record(self, order):
        cid = order.client_order_id
        if self.observer is not None:
            self.observer([order])
        self._closed.pop(cid, None)
        if order.status not in ACTIVE_STATUSES:
            self._closed[cid] = order
        self.prune()

    def prune(self):
        # Only closed, unpinned rows count toward the retention allowance.
        eligible = [cid for cid, order in self._closed.items()
                    if order.status not in ACTIVE_STATUSES and not self.pinned(cid)]
        for cid in eligible[:-self.limit]:
            self._closed.pop(cid, None)
            super().pop(cid, None)

    def active(self):
        return [o for o in self.values() if o.status in ACTIVE_STATUSES]

    def recent(self, limit=100):
        if not 1 <= limit <= CLOSED_ORDER_LIMIT:
            raise ValueError("order history limit must be between 1 and 1000")
        closed = list(reversed(list(islice(reversed(self._closed.values()), limit))))
        active = [o for o in self.values() if o.status in ACTIVE_STATUSES or self.pinned(o.client_order_id)]
        ids = {o.client_order_id for o in active}
        return active + [o for o in closed if o.client_order_id not in ids]


class FillStore:
    """Recent observability plus pinned evidence awaiting both consumers.

    Acknowledgement requires immutable accounting evidence and agent consumption.
    Capacity exhaustion blocks new submissions; pending fills are never dropped.
    Position/version/notional are cumulative, independent of recent UI retention.
    """
    def __init__(self, limit=FILL_HISTORY_LIMIT):
        self.limit = limit
        self._fills: list[Fill] = []
        self._pending = {}
        # Consumption receipts are bounded by the non-evicting ledger capacity.
        self._consumed_identities = set()
        self.version = 0
        self.retired_count = 0
        self.positions = {}
        self.last_fill_at = None
        self.filled_notional = Decimal("0")

    def add(self, fill: Fill):
        self._fills.append(fill)
        self._pending[id(fill)] = fill
        self.version += 1
        self.last_fill_at = fill.timestamp
        self.positions[fill.market] = self.positions.get(fill.market, Decimal("0")) + (fill.size if fill.side == "BID" else -fill.size)
        self.filled_notional += fill.price*fill.size
        self._prune()

    def _prune(self):
        acknowledged = [f for f in self._fills if id(f) not in self._pending]
        drops = {id(f) for f in acknowledged[:-self.limit]}
        if drops:
            self._fills[:] = [f for f in self._fills if id(f) not in drops]
            self.retired_count += len(drops)

    def acknowledge(self, fill, accounting, *, agent_consumed):
        identity, _, economics = accounting._fill_evidence(fill)
        if id(fill) not in self._pending:
            return False
        if agent_consumed and accounting.ledger.fill_evidence().get("fill:"+identity) == economics and not accounting.error:
            if identity in self._consumed_identities:
                accounting.observe_execution_fills(self.all(), retired_count=self.retired_count,
                                                   duplicate_fills=self.duplicate_pending(accounting))
                accounting.fail("duplicate execution fill identity after consumption")
                return False
            if len(self._consumed_identities) >= accounting.ledger.max_entries // 2:
                accounting.fail("execution consumption receipt capacity exhausted")
                return False
            self._consumed_identities.add(identity)
            self._pending.pop(id(fill), None)
            self._prune()
            return True
        return False

    def duplicate_pending(self, accounting):
        return [fill for fill in self._pending.values()
                if accounting.fill_identity(fill) in self._consumed_identities]

    def pending(self):
        return list(self._pending.values())

    def pins_order(self, cid):
        return any(f.client_order_id == cid for f in self._pending.values())

    def require_capacity(self):
        if len(self._pending) >= self.limit:
            raise RuntimeError("unconsumed execution fill capacity exhausted")

    def all(self) -> list[Fill]:
        rows = list(self._fills)
        present = {id(f) for f in rows}
        return rows + [f for key, f in self._pending.items() if key not in present]

    def recent(self, limit=100):
        if not 1 <= limit <= FILL_HISTORY_LIMIT:
            raise ValueError("fill history limit must be between 1 and 1000")
        return self._fills[-limit:]
