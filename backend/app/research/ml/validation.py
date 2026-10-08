"""Bounded Decimal probability calibration; classification is not profitability."""
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict, Field

from app.agents.models import AgentModel
from app.agents.common import ZERO, mean


class PredictionOutcome(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    side: Literal["BID", "ASK"]
    probability: Decimal = Field(ge=0, le=1)
    markout_bps: Decimal | None = None


class CalibrationBucket(AgentModel):
    lower_bound: Decimal = Field(ge=0, le=1)
    upper_bound: Decimal = Field(ge=0, le=1)
    sample_count: int = Field(ge=0)
    mean_probability: Decimal | None = Field(default=None, ge=0, le=1)
    observed_adverse_frequency: Decimal | None = Field(default=None, ge=0, le=1)
    sufficient_samples: bool


class ClassificationReport(AgentModel):
    partition: Literal["training", "validation", "holdout", "simulation"]
    horizon_seconds: Decimal = Field(gt=0, le=3600)
    prediction_count: int = Field(ge=0, le=100000)
    matured_label_count: int = Field(ge=0, le=100000)
    minimum_bucket_samples: int = Field(ge=1, le=100000)
    metrics: dict[str, Decimal | None]
    buckets: tuple[CalibrationBucket, ...]
    bid_metrics: dict[str, Decimal | None]
    ask_metrics: dict[str, Decimal | None]
    simulated: bool


def classification_metrics(rows):
    labeled = [r for r in rows if r.markout_bps is not None]
    if not labeled:
        return {k:None for k in ("accuracy", "precision", "recall", "roc_auc", "brier_score", "calibration_error")}
    labels = [(r.probability, int(r.markout_bps < 0)) for r in labeled]
    positives = sum(y for _,y in labels)
    predicted = sum(p >= Decimal(".5") for p,_ in labels)
    true_positive = sum(p >= Decimal(".5") and y for p,y in labels)
    accuracy = mean(Decimal((p >= Decimal(".5")) == bool(y)) for p,y in labels)
    brier = mean((p-y)**2 for p,y in labels)
    # Pair-order AUC in O(n log n), awarding half credit for ties.
    negatives = len(labels)-positives
    auc = None
    if positives and negatives:
        concordant = ZERO
        below = 0
        groups = {}
        for p,y in labels:
            count = groups.setdefault(p, [0,0])
            count[y] += 1
        for p in sorted(groups):
            neg, pos = groups[p]
            concordant += Decimal(pos)*(below+Decimal(neg)/2)
            below += neg
        auc = concordant/(positives*negatives)
    calibration = ZERO
    for bucket in range(10):
        group = [(p,y) for p,y in labels if min(9,int(p*10)) == bucket]
        if group:
            calibration += abs(mean(p for p,_ in group)-mean(Decimal(y) for _,y in group))*len(group)/len(labels)
    return dict(accuracy=accuracy, precision=Decimal(true_positive)/predicted if predicted else None,
        recall=Decimal(true_positive)/positives if positives else None, roc_auc=auc,
        brier_score=brier, calibration_error=calibration)


def evaluate_predictions(rows, *, partition, horizon_seconds, simulated, minimum_bucket_samples=10):
    if len(rows) > 100000:
        raise ValueError("prediction evaluation exceeds bound")
    rows = [PredictionOutcome.model_validate(r.model_dump()) for r in rows]
    buckets = []
    for i in range(10):
        group = [r for r in rows if r.markout_bps is not None and min(9,int(r.probability*10)) == i]
        buckets.append(CalibrationBucket(lower_bound=Decimal(i)/10,upper_bound=Decimal(i+1)/10,
            sample_count=len(group),mean_probability=mean(r.probability for r in group),
            observed_adverse_frequency=mean(Decimal(r.markout_bps < 0) for r in group),
            sufficient_samples=len(group) >= minimum_bucket_samples))
    return ClassificationReport(partition=partition,horizon_seconds=horizon_seconds,prediction_count=len(rows),
        matured_label_count=sum(r.markout_bps is not None for r in rows),minimum_bucket_samples=minimum_bucket_samples,
        metrics=classification_metrics(rows),buckets=tuple(buckets),
        bid_metrics=classification_metrics([r for r in rows if r.side == "BID"]),
        ask_metrics=classification_metrics([r for r in rows if r.side == "ASK"]),simulated=simulated)
