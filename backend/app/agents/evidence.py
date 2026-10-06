from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, Field

from app.execution.models import Fill, OrderStatus
from app.execution.quote_reconciler import ReconcileActionType
from app.market_data.history import MarketPriceHistory
from app.market_data.models import utcnow
from .models import AgentEvidenceSnapshot, semantic_fingerprint


class FillObservation(BaseModel):
    identity: str
    client_order_id: str
    market: str
    side: str
    price: Decimal = Field(gt=0)
    size: Decimal = Field(gt=0)
    timestamp: datetime
    reference_price: Decimal | None = Field(default=None, gt=0)
    source: str
    simulated: bool


class MarkoutObservation(BaseModel):
    fill_identity: str
    side: str
    fill_price: Decimal
    future_reference_price: Decimal
    signed_markout_bps: Decimal
    simulated: bool


class ReconcileObservation(BaseModel):
    keep_count: int = 0
    create_count: int = 0
    replace_count: int = 0
    cancel_count: int = 0
    timestamp: datetime


class AgentTelemetryStore:
    def __init__(self, *, max_fills: int = 500, max_reconcile_cycles: int = 250, max_orders: int = 1000):
        self.max_fills=max_fills
        self._fills: deque[FillObservation]=deque()
        self._fill_ids:set[str]=set()
        self._reconcile:deque[ReconcileObservation]=deque(maxlen=max_reconcile_cycles)
        self._order_statuses:dict[str,OrderStatus]={}
        self._order_order:deque[str]=deque()
        self.max_orders=max_orders
        self.version=0

    @staticmethod
    def fill_identity(fill: Fill) -> str:
        return "|".join([
            fill.client_order_id,
            fill.timestamp.isoformat(),
            fill.side,
            format(fill.size,"f"),
            format(fill.price,"f"),
        ])

    def observe_fill(self, fill: Fill, reference_price: Decimal | None) -> bool:
        identity=self.fill_identity(fill)
        if identity in self._fill_ids:
            return False
        if len(self._fills)>=self.max_fills:
            dropped=self._fills.popleft()
            self._fill_ids.discard(dropped.identity)
        simulated=fill.source.startswith("SIMULATED")
        self._fills.append(FillObservation(
            identity=identity,client_order_id=fill.client_order_id,market=fill.market,side=fill.side,
            price=fill.price,size=fill.size,timestamp=fill.timestamp,reference_price=reference_price,
            source=fill.source,simulated=simulated,
        ))
        self._fill_ids.add(identity)
        self.version+=1
        return True

    def observe_orders(self, orders) -> bool:
        changed=False
        for order in orders:
            previous=self._order_statuses.get(order.client_order_id)
            if order.client_order_id not in self._order_statuses:
                if len(self._order_order)>=self.max_orders:
                    old=self._order_order.popleft()
                    self._order_statuses.pop(old,None)
                self._order_order.append(order.client_order_id)
            self._order_statuses[order.client_order_id]=order.status
            changed=changed or previous!=order.status
        if changed:self.version+=1
        return changed

    def observe_reconcile(self, actions, orders) -> None:
        counts={kind:0 for kind in ReconcileActionType}
        for action in actions:
            counts[action.action]+=1
        self._reconcile.append(ReconcileObservation(
            keep_count=counts[ReconcileActionType.KEEP],
            create_count=counts[ReconcileActionType.CREATE],
            replace_count=counts[ReconcileActionType.REPLACE],
            cancel_count=counts[ReconcileActionType.CANCEL],
            timestamp=utcnow(),
        ))
        self.observe_orders(orders)
        self.version+=1

    def fills(self, window: int) -> list[FillObservation]:
        return list(self._fills)[-window:]

    def reconcile(self, window: int) -> list[ReconcileObservation]:
        return list(self._reconcile)[-window:]

    def order_status_counts(self) -> dict[str,int]:
        counts={status.value:0 for status in OrderStatus}
        for status in self._order_statuses.values():
            counts[status.value]+=1
        return counts

    def markouts(self, history: MarketPriceHistory, *, horizon_seconds: float, window: int) -> tuple[list[MarkoutObservation],int]:
        fills=self.fills(window)
        observations=history.observations(max(2,len(history)))
        matured=[]
        pending=0
        for fill in fills:
            target=fill.timestamp+timedelta(seconds=horizon_seconds)
            future=next((obs for obs in observations if obs.timestamp>=target),None)
            if future is None:
                pending+=1
                continue
            sign=Decimal("1") if fill.side=="BID" else Decimal("-1")
            markout=sign*(future.mid_price-fill.price)/fill.price*Decimal("10000")
            if not markout.is_finite():
                raise ValueError("non-finite toxic-flow markout")
            matured.append(MarkoutObservation(
                fill_identity=fill.identity,side=fill.side,fill_price=fill.price,
                future_reference_price=future.mid_price,signed_markout_bps=markout,
                simulated=fill.simulated,
            ))
        return matured,pending

    def summary(self) -> dict:
        statuses=self.order_status_counts()
        return {
            "version":self.version,
            "fill_observations":len(self._fills),
            "reconcile_cycles":len(self._reconcile),
            "tracked_orders":len(self._order_statuses),
            "unknown_orders":statuses.get(OrderStatus.UNKNOWN.value,0),
            "rejected_orders":statuses.get(OrderStatus.REJECTED.value,0),
        }


def _evidence_version(parts: tuple) -> int:
    return int(semantic_fingerprint(parts)[:12],16)


def build_agent_evidence(
    *,
    market_decision,
    inventory,
    perp_context,
    refs,
    history: MarketPriceHistory,
    momentum_window: int,
) -> AgentEvidenceSnapshot:
    observations=history.observations(max(2,momentum_window))
    selected=observations[-momentum_window:]
    momentum=None
    if len(selected)>=2:
        first=selected[0].mid_price
        last=selected[-1].mid_price
        if not first.is_finite() or not last.is_finite() or first<=0 or last<=0:
            raise ValueError("agent momentum history contains invalid prices")
        if any(a.timestamp>b.timestamp or a.sequence>=b.sequence for a,b in zip(selected,selected[1:])):
            raise ValueError("agent momentum history is not ordered")
        momentum=(last-first)/first*Decimal("10000")
    max_dev=refs.consensus.max_source_deviation_bps
    versions=(market_decision.version,inventory.version,perp_context.version,refs.version)
    return AgentEvidenceSnapshot(
        market=inventory.market,
        market_version=market_decision.version,
        inventory_version=inventory.version,
        perp_version=perp_context.version,
        reference_version=refs.version,
        market_adaptation_regime=market_decision.regime.value,
        realized_volatility=market_decision.realized_volatility,
        volatility_score=market_decision.volatility_score,
        book_imbalance=market_decision.book_imbalance,
        history_sample_count=len(selected),
        momentum_bps=momentum,
        inventory_position_base=inventory.position_base,
        inventory_ratio=inventory.inventory_ratio,
        mark_price=perp_context.mark_price,
        oracle_price=perp_context.oracle_price,
        funding_rate=perp_context.funding_rate,
        open_interest_base=perp_context.open_interest_base,
        mark_oracle_basis_bps=perp_context.mark_oracle_basis_bps,
        mark_mid_basis_bps=perp_context.mark_mid_basis_bps,
        reference_confidence=refs.consensus.confidence_state,
        max_reference_deviation_bps=max_dev,
        simulated=bool(perp_context.simulated or any(item.simulated for item in refs.evidence.values())),
        updated_at=utcnow(),
        version=_evidence_version(versions),
    )
