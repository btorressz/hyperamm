from __future__ import annotations

from collections import deque
from bisect import bisect_left
from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.execution.models import Fill, OrderStatus
from app.execution.quote_reconciler import ReconcileActionType
from app.market_data.history import MarketPriceHistory
from app.market_data.models import utcnow
from app.references.models import PriceEvidence, ReferenceSnapshot
from .models import AgentEvidenceSnapshot, AgentModel, semantic_fingerprint
from .common import seconds


class FillObservation(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    identity: str
    client_order_id: str
    market: str
    side: str
    price: Decimal = Field(gt=0)
    size: Decimal = Field(gt=0)
    timestamp: datetime
    reference_price: Decimal | None = Field(default=None, gt=0)
    reference_timestamp: datetime | None = None
    reference_source: str | None = None
    reference_version: int | None = None
    reference_provenance: dict[str, PriceEvidence] = Field(default_factory=dict)
    source: str
    simulated: bool


class MarkoutObservation(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    fill_identity: str
    target_maturity_time: datetime
    selected_observation_sequence: int
    selected_observation_timestamp: datetime
    side: str
    fill_price: Decimal
    future_reference_price: Decimal
    signed_markout_bps: Decimal
    simulated: bool


class OrderObservation(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    client_order_id: str
    side: str = Field(pattern="^(BID|ASK)$")
    level_index: int | None = Field(default=None, ge=0, le=99)
    size: Decimal = Field(gt=0)
    filled_size: Decimal = Field(ge=0)
    status: OrderStatus
    created_at: datetime
    updated_at: datetime


class PerpObservation(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    market: str
    source: str
    timestamp: datetime
    open_interest_base: Decimal = Field(ge=0)
    funding_rate: Decimal


class ReconcileObservation(BaseModel):
    keep_count: int = 0
    create_count: int = 0
    replace_count: int = 0
    cancel_count: int = 0
    timestamp: datetime


class AgentTelemetryStore:
    def __init__(self, *, max_fills: int = 1000, max_reconcile_cycles: int = 1000, max_orders: int = 1000,
                 markout_horizons=(1.0, 5.0, 15.0), max_perp_observations: int = 120):
        if not (1 <= max_fills <= 1000 and 1 <= max_reconcile_cycles <= 1000 and
                1 <= max_orders <= 1000 and 2 <= max_perp_observations <= 120):
            raise ValueError("telemetry capacity outside bounded contract")
        self.max_fills=max_fills
        self._fills: deque[FillObservation]=deque()
        self._fill_ids:set[str]=set()
        # None is a terminal unavailable result, distinct from a pending horizon.
        self._markouts:dict[tuple[str,datetime],MarkoutObservation | None]={}
        self._reconcile:deque[ReconcileObservation]=deque(maxlen=max_reconcile_cycles)
        # KEEP cadence must not evict order-changing activity from the churn window.
        self._action_reconcile:deque[ReconcileObservation]=deque(maxlen=max_reconcile_cycles)
        self._order_statuses:dict[str,OrderStatus]={}
        self._orders:dict[str,OrderObservation]={}
        self._first_fill_times:dict[str,datetime]={}
        self._order_order:deque[str]=deque()
        self.max_orders=max_orders
        self._horizons: set[float] = set()
        self.register_horizons(markout_horizons)
        self.evicted_unavailable_markouts = 0
        self._perp: deque[PerpObservation] = deque(maxlen=max_perp_observations)
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

    def observe_fill_from_references(self, fill: Fill, refs: ReferenceSnapshot | None) -> bool:
        """Bind the accepted consensus retained at fill time; never substitute midpoint.

        The timestamp identifies consensus evaluation; provider evidence retains each
        accepted source timestamp/transport separately. Later updates cannot rebind a fill.
        """
        if refs is None or refs.consensus.consensus_price is None:
            return self.observe_fill(fill, None)
        return self.observe_fill(
            fill, refs.consensus.consensus_price,
            reference_timestamp=refs.consensus.updated_at,
            reference_source="CONSENSUS", reference_version=refs.version,
            reference_provenance={
                provider: refs.evidence[provider].model_copy(deep=True)
                for provider in refs.consensus.eligible_providers
            },
        )

    def observe_fill(self, fill: Fill, reference_price: Decimal | None, *,
                     reference_timestamp: datetime | None = None,
                     reference_source: str | None = None,
                     reference_version: int | None = None,
                     reference_provenance: dict[str, PriceEvidence] | None = None) -> bool:
        identity=self.fill_identity(fill)
        if identity in self._fill_ids:
            return False
        if len(self._fills)>=self.max_fills:
            dropped=self._fills.popleft()
            # Explicit terminal accounting before removing unresolved retained evidence.
            self.evicted_unavailable_markouts += sum(
                (dropped.identity, dropped.timestamp + timedelta(seconds=h)) not in self._markouts
                for h in self._horizons
            )
            self._fill_ids.discard(dropped.identity)
            self._markouts={key:value for key,value in self._markouts.items() if key[0]!=dropped.identity}
        simulated=fill.source.startswith("SIMULATED")
        self._fills.append(FillObservation(
            identity=identity,client_order_id=fill.client_order_id,market=fill.market,side=fill.side,
            price=fill.price,size=fill.size,timestamp=fill.timestamp,reference_price=reference_price,
            reference_timestamp=reference_timestamp,reference_source=reference_source,
            reference_version=reference_version,reference_provenance=reference_provenance or {},
            source=fill.source,simulated=simulated,
        ))
        self._fill_ids.add(identity)
        if fill.client_order_id in self._orders:
            self._first_fill_times.setdefault(fill.client_order_id, fill.timestamp)
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
                    self._orders.pop(old,None)
                    self._first_fill_times.pop(old,None)
                self._order_order.append(order.client_order_id)
            self._order_statuses[order.client_order_id]=order.status
            retained = OrderObservation(**{name: getattr(order, name) for name in OrderObservation.model_fields})
            changed=changed or previous!=order.status or self._orders.get(order.client_order_id)!=retained
            self._orders[order.client_order_id] = retained
        if changed:self.version+=1
        return changed

    def orders(self) -> list[OrderObservation]:
        return list(self._orders.values())

    def first_fill_times(self):
        return dict(self._first_fill_times)

    def register_horizons(self, horizons):
        values = {float(h) for h in horizons}
        if any(not Decimal(str(h)).is_finite() or not 0 < h <= 3600 for h in values):
            raise ValueError("invalid markout horizon")
        if len(self._horizons | values) > 8:
            raise ValueError("telemetry supports at most eight retained markout horizons")
        self._horizons.update(values)

    def observe_perp(self, context) -> bool:
        if context.stale or context.updated_at.tzinfo is None:
            return False
        observation = PerpObservation(market=context.market, source=context.source,
            timestamp=context.updated_at, open_interest_base=context.open_interest_base,
            funding_rate=context.funding_rate)
        if self._perp and (self._perp[-1].market, self._perp[-1].source) != (observation.market, observation.source):
            self._perp.clear()
        if self._perp and observation.timestamp <= self._perp[-1].timestamp:
            return False  # One source timestamp is one observation, regardless of polling cadence.
        self._perp.append(observation)
        self.version += 1
        return True

    def perp_changes(self, *, now, window, min_span_seconds, max_span_seconds):
        selected = [p for p in list(self._perp)[-window:]
                    if 0 <= seconds(now-p.timestamp) <= max_span_seconds]
        result = dict(perp_observation_count=len(selected), open_interest_change_ratio=None,
                      funding_rate_delta=None, perp_window_start=None, perp_window_end=None)
        if len(selected) < 2:
            return result
        first, last = selected[0], selected[-1]
        result.update(perp_window_start=first.timestamp, perp_window_end=last.timestamp)
        if seconds(last.timestamp-first.timestamp) < min_span_seconds:
            return result
        result["funding_rate_delta"] = last.funding_rate-first.funding_rate
        if first.open_interest_base > 0:
            result["open_interest_change_ratio"] = (last.open_interest_base-first.open_interest_base)/first.open_interest_base
        return result

    def observe_reconcile(self, actions, orders) -> None:
        counts={kind:0 for kind in ReconcileActionType}
        for action in actions:
            counts[action.action]+=1
        observation=ReconcileObservation(
            keep_count=counts[ReconcileActionType.KEEP],
            create_count=counts[ReconcileActionType.CREATE],
            replace_count=counts[ReconcileActionType.REPLACE],
            cancel_count=counts[ReconcileActionType.CANCEL],
            timestamp=utcnow(),
        )
        self._reconcile.append(observation)
        if observation.create_count or observation.replace_count or observation.cancel_count:
            self._action_reconcile.append(observation)
        self.observe_orders(orders)
        self.version+=1

    def fills(self, window: int) -> list[FillObservation]:
        return list(self._fills)[-window:]

    def reconcile(self, window: int) -> list[ReconcileObservation]:
        return list(self._reconcile)[-window:]

    def action_reconcile(self, window: int) -> list[ReconcileObservation]:
        return list(self._action_reconcile)[-window:]

    def order_status_counts(self) -> dict[str,int]:
        counts={status.value:0 for status in OrderStatus}
        for status in self._order_statuses.values():
            counts[status.value]+=1
        return counts

    def markouts(self, history: MarketPriceHistory, *, horizon_seconds: float, window: int) -> tuple[list[MarkoutObservation],int]:
        self.register_horizons((horizon_seconds,))
        fills=self.fills(window)
        observations=history.observations(max(2,len(history)))
        timestamps=[obs.timestamp for obs in observations]
        matured=[]
        pending=0
        # Resolve all retained fills even when a consumer asks for a smaller window.
        for fill in self._fills:
            target=fill.timestamp+timedelta(seconds=horizon_seconds)
            key=(fill.identity,target)
            if key in self._markouts:
                continue
            if history.evicted_through_timestamp is not None and history.evicted_through_timestamp>=target:
                self._markouts[key]=None
                continue
            index=bisect_left(timestamps,target)
            future=observations[index] if index<len(observations) else None
            if future is None:
                continue
            sign=Decimal("1") if fill.side=="BID" else Decimal("-1")
            markout=sign*(future.mid_price-fill.price)/fill.price*Decimal("10000")
            if not markout.is_finite():
                raise ValueError("non-finite toxic-flow markout")
            self._markouts[key]=MarkoutObservation(
                fill_identity=fill.identity,side=fill.side,fill_price=fill.price,
                target_maturity_time=target,selected_observation_sequence=future.sequence,
                selected_observation_timestamp=future.timestamp,
                future_reference_price=future.mid_price,signed_markout_bps=markout,
                simulated=fill.simulated,
            )
        for fill in fills:
            key=(fill.identity,fill.timestamp+timedelta(seconds=horizon_seconds))
            if key not in self._markouts:
                pending+=1
            elif self._markouts[key] is not None:
                matured.append(self._markouts[key])
        return matured,pending

    def markout_terminally_unavailable(self, fill_identity, target):
        return self._markouts.get((fill_identity,target), False) is None

    def unavailable_markouts(self, *, horizon_seconds, window):
        return sum(self._markouts.get((f.identity, f.timestamp+timedelta(seconds=horizon_seconds)), False) is None
                   for f in self.fills(window))

    def summary(self) -> dict:
        statuses=self.order_status_counts()
        return {
            "version":self.version,
            "fill_observations":len(self._fills),
            "unavailable_markouts":sum(value is None for value in self._markouts.values()),
            "evicted_unavailable_markouts": self.evicted_unavailable_markouts,
            "perp_observations": len(self._perp),
            "retained_markout_horizons": len(self._horizons),
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
    market_snapshot=None,
    config=None,
    telemetry=None,
    observed_at=None,
    upstream_quotes=None,
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
    observed_at = observed_at or (selected[-1].timestamp if selected else perp_context.updated_at)
    book_metrics = _book_metrics(market_snapshot, config.liquidity_depth_levels if config else 5)
    changes = {}
    if telemetry is not None and config is not None:
        telemetry.observe_perp(perp_context)
        if not perp_context.stale:
            changes = telemetry.perp_changes(now=observed_at, window=config.perp_observation_window,
                min_span_seconds=config.perp_min_observation_span_seconds,
                max_span_seconds=config.perp_max_observation_span_seconds)
    instability = None
    if len(selected) >= 2:
        instability = max(abs((b.mid_price-a.mid_price)/a.mid_price)*Decimal("10000")
                          for a,b in zip(selected,selected[1:]))
    versions=(market_decision.version,inventory.version,perp_context.version,refs.version,book_metrics,changes)
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
        **book_metrics, **changes,
        upstream_available_levels=(max((len({q.level_index for q in upstream_quotes if q.side==side})
            for side in ("BID","ASK")),default=0) if upstream_quotes is not None else None),
        midpoint_instability_bps=instability, perp_stale=perp_context.stale,
        updated_at=observed_at,
        version=_evidence_version(versions),
    )


def _book_metrics(snapshot, levels):
    """Top-N base quantities, BBO/span bps and maximum level share of total depth."""
    if snapshot is None or snapshot.stale or snapshot.book is None or snapshot.mid_price is None:
        return {}
    bids, asks = snapshot.book.bids[:levels], snapshot.book.asks[:levels]
    if not bids or not asks:
        return {}
    mid = snapshot.mid_price
    for side in (bids, asks):
        for level in side:
            if not level.price.is_finite() or not level.size.is_finite() or level.price <= 0 or level.size <= 0:
                raise ValueError("agent book evidence requires finite positive levels")
    if mid <= 0 or not mid.is_finite() or bids[0].price >= asks[0].price:
        raise ValueError("agent book evidence invalid midpoint or BBO")
    bid_depth = sum((x.size for x in bids), Decimal(0))
    ask_depth = sum((x.size for x in asks), Decimal(0))
    total = bid_depth + ask_depth
    return dict(spread_bps=(asks[0].price-bids[0].price)/mid*Decimal(10000),
        top_n_bid_depth_base=bid_depth, top_n_ask_depth_base=ask_depth,
        depth_imbalance=(bid_depth-ask_depth)/total,
        depth_concentration=max(x.size for x in bids+asks)/total,
        book_span_bps=(asks[-1].price-bids[-1].price)/mid*Decimal(10000),
        liquidity_depth_levels=levels, book_timestamp=snapshot.latest_valid_update or snapshot.book.timestamp)
