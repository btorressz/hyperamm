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
    desired_map={(q.side,q.level_index):q for q in desired}
    existing_map={(o.side,o.level_index):o for o in existing if o.level_index is not None}
    actions=[]
    for key,q in desired_map.items():
        old=existing_map.get(key)
        if old is None:
            actions.append(ReconcileAction(action=ReconcileActionType.CREATE,desired=q)); continue
        price_diff=abs(q.price-old.price)/q.price*Decimal("10000")
        size_diff=abs(q.size-(old.size-old.filled_size))
        if price_diff <= price_tolerance_bps and size_diff <= size_tolerance:
            actions.append(ReconcileAction(action=ReconcileActionType.KEEP,desired=q,existing=old))
        else:
            actions.append(ReconcileAction(action=ReconcileActionType.REPLACE,desired=q,existing=old))
    for key,old in existing_map.items():
        if key not in desired_map:
            actions.append(ReconcileAction(action=ReconcileActionType.CANCEL,existing=old))
    return sorted(actions,key=lambda a:(a.desired.side if a.desired else a.existing.side, a.desired.level_index if a.desired else (a.existing.level_index or 0), a.action))
