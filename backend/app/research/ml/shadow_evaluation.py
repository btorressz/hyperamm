"""Bounded simulation cohort: predictions bound at order creation, labels frozen per fill."""
from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.agents.models import AgentModel, PredictiveAdverseSelectionState
from .validation import ClassificationReport, PredictionOutcome, evaluate_predictions


class ShadowPredictionRecord(AgentModel):
    fill_identity: str
    prediction_time: datetime
    fill_time: datetime
    side: Literal["BID", "ASK"]
    probability: Decimal = Field(ge=0, le=1)
    horizon_seconds: Decimal = Field(gt=0, le=3600)
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    actual_markout_bps: Decimal | None = None
    label_time: datetime | None = None
    label_state: Literal["PENDING", "MATURED", "UNAVAILABLE"] = "PENDING"


class ShadowEvaluationResult(AgentModel):
    affects_quotes: Literal[False] = False
    simulated: Literal[True] = True
    total_fill_predictions: int = Field(ge=0)
    evicted_fill_predictions: int = Field(ge=0)
    reports: tuple[ClassificationReport, ...]
    records: tuple[ShadowPredictionRecord, ...] = Field(max_length=1000)
    cohort: Literal["bounded retained fill predictions"] = "bounded retained fill predictions"


class ShadowEvaluationAccumulator:
    def __init__(self, max_records=1000, max_orders=1000):
        if not 1 <= max_records <= 1000 or not 1 <= max_orders <= 1000:
            raise ValueError("shadow cohort bounds exceeded")
        self.max_records, self.max_orders = max_records, max_orders
        self.orders = OrderedDict()
        self.records = OrderedDict()
        self.total = self.evicted = 0

    def observe_orders(self, orders, prediction):
        if prediction is None or prediction.state != PredictiveAdverseSelectionState.PREDICTED:
            return
        for order in orders:
            if order.client_order_id not in self.orders and order.created_at == prediction.metrics.last_inference_time:
                if len(self.orders) >= self.max_orders:
                    self.orders.popitem(last=False)
                self.orders[order.client_order_id] = prediction.model_copy(deep=True)

    def observe_fill(self, fill, fill_identity):
        prediction = self.orders.get(fill.client_order_id)
        if prediction is None or prediction.metrics.last_inference_time > fill.timestamp or fill_identity in self.records:
            return
        if len(self.records) >= self.max_records:
            self.records.popitem(last=False)
            self.evicted += 1
        self.total += 1
        p = prediction.metrics.bid_adverse_probability if fill.side == "BID" else prediction.metrics.ask_adverse_probability
        self.records[fill_identity] = ShadowPredictionRecord(fill_identity=fill_identity,side=fill.side,
            prediction_time=prediction.metrics.last_inference_time,fill_time=fill.timestamp,probability=p,
            horizon_seconds=prediction.metrics.markout_horizon_seconds,model_sha256=prediction.model_provenance.model_sha256)

    def mature(self, telemetry, history):
        for horizon in {r.horizon_seconds for r in self.records.values()}:
            markouts,_ = telemetry.markouts(history,horizon_seconds=float(horizon),window=1000)
            selected = {m.fill_identity:m for m in markouts}
            retained = {f.identity for f in telemetry.fills(1000)}
            for key,record in self.records.items():
                if record.horizon_seconds != horizon or record.label_state != "PENDING":
                    continue
                if key in selected:
                    markout = selected[key]
                    self.records[key] = record.model_copy(update=dict(actual_markout_bps=markout.signed_markout_bps,
                        label_time=markout.selected_observation_timestamp,label_state="MATURED"))
                elif key not in retained or telemetry.markout_terminally_unavailable(key, record.fill_time+timedelta(seconds=float(horizon))):
                    self.records[key] = record.model_copy(update={"label_state":"UNAVAILABLE"})

    def result(self):
        records = tuple(self.records.values())
        reports = tuple(evaluate_predictions([PredictionOutcome(side=r.side,probability=r.probability,markout_bps=r.actual_markout_bps)
            for r in records if r.horizon_seconds == horizon],partition="simulation",horizon_seconds=horizon,simulated=True)
            for horizon in sorted({r.horizon_seconds for r in records}))
        return ShadowEvaluationResult(total_fill_predictions=self.total,evicted_fill_predictions=self.evicted,
            records=records,reports=reports)
