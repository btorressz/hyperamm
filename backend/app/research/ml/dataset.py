"""Leakage-aware offline fill-label construction from normalized domain evidence."""
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from app.agents.evidence import FillObservation
from app.agents.ml_features import FEATURE_SCHEMA_VERSION, FeatureVector, build_feature_vector
from app.agents.models import AgentModel, AgentEvidenceSnapshot, semantic_fingerprint
from app.market_data.history import MarketObservation

TARGET = "signed_markout_bps < 0, conditional on observed fill"
MAX_SAMPLES = 100000


class DatasetSample(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    sample_id: str = Field(min_length=1, max_length=500)
    feature_timestamp: datetime
    fill_timestamp: datetime
    label_timestamp: datetime
    label_observation_sequence: int = Field(ge=0)
    features: FeatureVector
    signed_markout_bps: Decimal
    adverse: bool
    fill_notional_quote: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def temporal_contract(self):
        if any(t.tzinfo is None for t in (self.feature_timestamp, self.fill_timestamp, self.label_timestamp)):
            raise ValueError("dataset timestamps must be timezone-aware")
        if not self.feature_timestamp <= self.fill_timestamp < self.label_timestamp:
            raise ValueError("features must precede fill and future label")
        if self.adverse != (self.signed_markout_bps < 0):
            raise ValueError("dataset target sign mismatch")
        return self


class OfflineDataset(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    market: str = Field(pattern=r"^[A-Z0-9-]{1,20}$")
    feature_schema_version: Literal["passive-adverse-v1"] = FEATURE_SCHEMA_VERSION
    target_definition: Literal["signed_markout_bps < 0, conditional on observed fill"] = TARGET
    markout_horizon_seconds: Decimal = Field(gt=0, le=3600)
    samples: tuple[DatasetSample, ...] = Field(min_length=1, max_length=MAX_SAMPLES)
    sample_count: int = Field(ge=1, le=MAX_SAMPLES)
    simulated: bool
    source_provenance: tuple[str, ...] = Field(min_length=1, max_length=10)
    time_start: datetime
    time_end: datetime
    fingerprint: str = ""

    @model_validator(mode="after")
    def identity(self):
        if self.sample_count != len(self.samples):
            raise ValueError("dataset sample count mismatch")
        if len({s.sample_id for s in self.samples}) != len(self.samples):
            raise ValueError("duplicate dataset samples")
        if any(len(p) != 64 or any(c not in "0123456789abcdef" for c in p) for p in self.source_provenance):
            raise ValueError("source provenance must contain content fingerprints")
        if self.time_start != min(s.feature_timestamp for s in self.samples) or self.time_end != max(s.label_timestamp for s in self.samples):
            raise ValueError("dataset time bounds must include features and labels")
        if any(s.label_timestamp < s.fill_timestamp+timedelta(seconds=float(self.markout_horizon_seconds)) for s in self.samples):
            raise ValueError("label not matured at configured horizon")
        expected = semantic_fingerprint(self.model_dump(exclude={"fingerprint"}))
        if self.fingerprint and self.fingerprint != expected:
            raise ValueError("dataset fingerprint mismatch")
        object.__setattr__(self, "fingerprint", expected)
        return self


def build_dataset(*, market, evidence: list[AgentEvidenceSnapshot], fills: list[FillObservation],
                  observations: list[MarketObservation], horizon_seconds=Decimal(5), source_fingerprint,
                  simulated=True) -> OfflineDataset:
    if any(len(items) > MAX_SAMPLES for items in (evidence, fills, observations)):
        raise ValueError("offline dataset input exceeds bound")
    horizon_seconds = Decimal(str(horizon_seconds))
    if not horizon_seconds.is_finite() or not 0 < horizon_seconds <= 3600:
        raise ValueError("invalid target horizon")
    retained = {}
    for ev in evidence:
        if ev.market != market or ev.simulated != simulated:
            raise ValueError("feature market mismatch")
        # Canonical vectors validate required fields and prohibit future source evidence.
        vectors = (build_feature_vector(ev, "BID"), build_feature_vector(ev, "ASK"))
        if ev.updated_at in retained and retained[ev.updated_at] != vectors:
            raise ValueError("conflicting features for one observation timestamp")
        retained[ev.updated_at] = vectors
    times = sorted(retained)
    normalized = {}
    for obs in observations:
        if obs.timestamp.tzinfo is None or not obs.mid_price.is_finite() or obs.mid_price <= 0:
            raise ValueError("invalid normalized target observation")
        key = obs.timestamp
        if key in normalized and normalized[key] != obs:
            raise ValueError("conflicting target observations")
        normalized[key] = obs
    future_times = sorted(normalized)
    if any(normalized[a].sequence >= normalized[b].sequence for a,b in zip(future_times,future_times[1:])):
        raise ValueError("target observations must have strictly increasing sequences")
    unique_fills = {}
    identities = {}
    for fill in fills:
        fill = FillObservation.model_validate(fill.model_dump())
        if fill.market != market or fill.simulated != simulated:
            raise ValueError("fill market/classification mismatch")
        if fill.side not in {"BID", "ASK"}:
            raise ValueError("invalid fill side")
        if fill.identity in identities and identities[fill.identity] != fill:
            raise ValueError("conflicting duplicate fill identity")
        identities[fill.identity] = fill
        # Stable normalized economics deduplicate even relabeled duplicate records.
        key = (fill.market,fill.client_order_id,fill.timestamp,fill.side,fill.price,fill.size)
        unique_fills.setdefault(key,fill)
    rows = []
    for fill in sorted(unique_fills.values(), key=lambda f:(f.timestamp, f.identity)):
        feature_index = bisect_right(times, fill.timestamp)-1
        target_index = bisect_left(future_times, fill.timestamp+timedelta(seconds=float(horizon_seconds)))
        if feature_index < 0 or target_index == len(future_times):
            continue  # Unavailable features/labels are omitted, never synthesized.
        feature_time = times[feature_index]
        target = normalized[future_times[target_index]]
        sign = Decimal(1 if fill.side == "BID" else -1)
        markout = sign*(target.mid_price-fill.price)/fill.price*10000
        rows.append(DatasetSample(sample_id=semantic_fingerprint((fill.market,fill.client_order_id,fill.timestamp,fill.side,fill.price,fill.size)), feature_timestamp=feature_time,
            fill_timestamp=fill.timestamp, label_timestamp=target.timestamp, label_observation_sequence=target.sequence,
            features=retained[feature_time][0 if fill.side == "BID" else 1], signed_markout_bps=markout,
            adverse=markout < 0, fill_notional_quote=fill.price*fill.size))
    if not rows:
        raise ValueError("no honest matured dataset samples")
    return OfflineDataset(market=market, markout_horizon_seconds=horizon_seconds, samples=tuple(rows),
        sample_count=len(rows), simulated=simulated, source_provenance=(source_fingerprint,),
        time_start=min(s.feature_timestamp for s in rows), time_end=max(s.label_timestamp for s in rows))


def validate_independent_windows(training: OfflineDataset, validation: OfflineDataset):
    for dataset in (training, validation):
        OfflineDataset.model_validate(dataset.model_dump())
    if training.fingerprint == validation.fingerprint or training.time_end >= validation.time_start:
        raise ValueError("training/validation windows overlap or identity is reused")
    if {s.sample_id for s in training.samples} & {s.sample_id for s in validation.samples}:
        raise ValueError("training/validation sample identity overlap")
    if (training.market,training.markout_horizon_seconds,training.feature_schema_version,training.simulated) != (validation.market,validation.markout_horizon_seconds,validation.feature_schema_version,validation.simulated):
        raise ValueError("training/validation contracts differ")
