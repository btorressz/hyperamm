from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from pydantic import BaseModel
from app.amm.models import QuoteLevel
from .models import StrategyOrder


class ReconcileActionType(StrEnum): KEEP="KEEP"; CREATE="CREATE"; REPLACE="REPLACE"; CANCEL="CANCEL"


class ReconcileAction(BaseModel):
    action: ReconcileActionType
    desired: QuoteLevel | None = None
    existing: StrategyOrder | None = None


def reconcile_quotes(desired: list[QuoteLevel], existing: list[StrategyOrder], price_tolerance_bps: Decimal, size_tolerance: Decimal) -> list[ReconcileAction]:
    desired_map = {(q.side, q.level_index): q for q in desired}
    slots = {}
    unmanaged = []
    for order in existing:
        if order.status not in {"OPEN", "PARTIALLY_FILLED", "UNKNOWN"}:
            continue
        if order.side not in {"BID", "ASK"} or not isinstance(order.level_index, int) or order.level_index < 0:
            unmanaged.append(order)
        else:
            slots.setdefault((order.side, order.level_index), []).append(order)
    actions = [ReconcileAction(action=ReconcileActionType.CANCEL, existing=o) for o in unmanaged]

    def matches(q, order):
        return (order.status != "UNKNOWN"
                and abs(q.price-order.price)/q.price*Decimal("10000") <= price_tolerance_bps
                and abs(q.size-max(Decimal("0"), order.size-order.filled_size)) <= size_tolerance)

    for key, q in desired_map.items():
        orders = sorted(slots.pop(key, []), key=lambda o: (o.created_at, o.client_order_id))
        # Prefer a matching verified keeper, independent of insertion order.
        keeper = next((o for o in orders if matches(q, o)), None)
        if keeper is None:
            keeper = next((o for o in orders if o.status != "UNKNOWN"), None)
        for order in orders:
            if order is not keeper:
                actions.append(ReconcileAction(action=ReconcileActionType.CANCEL, existing=order))
        if keeper is None:
            actions.append(ReconcileAction(action=ReconcileActionType.CREATE, desired=q))
        else:
            actions.append(ReconcileAction(action=ReconcileActionType.KEEP if matches(q, keeper)
                                           else ReconcileActionType.REPLACE, desired=q, existing=keeper))
    for orders in slots.values():
        actions.extend(ReconcileAction(action=ReconcileActionType.CANCEL, existing=o) for o in orders)
    # Clear surplus/unmanaged exposure before any new order is considered.
    return sorted(actions, key=lambda a: (a.action != ReconcileActionType.CANCEL,
                   a.desired.side if a.desired else a.existing.side,
                   a.desired.level_index if a.desired else (a.existing.level_index or 0)))
