from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum, StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.market_data.models import utcnow


class AgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)


class AgentHealth(StrEnum):
    DISABLED = "DISABLED"
    WARMING_UP = "WARMING_UP"
    READY = "READY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


class MarketRegime(StrEnum):
    WARMING_UP = "WARMING_UP"
    QUIET = "QUIET"
    NORMAL = "NORMAL"
    TRENDING = "TRENDING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    DISLOCATED = "DISLOCATED"


class RegimeDirection(StrEnum):
    NEUTRAL = "NEUTRAL"
    UP = "UP"
    DOWN = "DOWN"


class ToxicFlowState(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    TOXIC = "TOXIC"


class ExecutionQualityState(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    GOOD = "GOOD"
    NORMAL = "NORMAL"
    POOR = "POOR"


class AgentRecommendation(AgentModel):
    agent: str
    health: AgentHealth
    confidence: Decimal = Field(ge=0, le=1)
    spread_multiplier: Decimal = Field(ge=1)
    bid_size_multiplier: Decimal = Field(gt=0, le=1)
    ask_size_multiplier: Decimal = Field(gt=0, le=1)
    max_levels: int | None = Field(default=None, ge=1)
    reasons: list[str] = Field(default_factory=list)
    simulated: bool
    evidence_version: int = Field(ge=0)
    version: int = Field(ge=0)
    updated_at: datetime = Field(default_factory=utcnow)
    implementation_version: str = "v2"
    affects_quotes: bool = True

    @model_validator(mode="after")
    def finite_outputs(self):
        for name in ("confidence", "spread_multiplier", "bid_size_multiplier", "ask_size_multiplier"):
            if not getattr(self, name).is_finite():
                raise ValueError(f"{name} must be finite")
        return self


class RegimeAgentOutput(AgentRecommendation):
    state: MarketRegime
    direction: RegimeDirection
    momentum_bps: Decimal | None = None
    realized_volatility: Decimal | None = None
    volatility_score: Decimal = Field(ge=0, le=1)
    book_imbalance: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    trend_strength: Decimal = Field(default=0, ge=0, le=1)
    funding_stress_score: Decimal = Field(default=0, ge=0, le=1)
    basis_stress_score: Decimal = Field(default=0, ge=0, le=1)
    book_pressure_score: Decimal = Field(default=0, ge=0, le=1)
    inventory_stress_score: Decimal = Field(default=0, ge=0, le=1)


class HorizonMarkoutMetrics(AgentModel):
    horizon_seconds: Decimal = Field(gt=0, le=3600)
    matured_fills: int = Field(ge=0)
    pending_markouts: int = Field(ge=0)
    unavailable_markouts: int = Field(ge=0)
    mean_markout_bps: Decimal | None = None
    bid_adverse_rate: Decimal | None = Field(default=None, ge=0, le=1)
    ask_adverse_rate: Decimal | None = Field(default=None, ge=0, le=1)


class ToxicFlowMetrics(AgentModel):
    total_fills: int = Field(ge=0)
    matured_fills: int = Field(ge=0)
    pending_markouts: int = Field(ge=0)
    adverse_fill_count: int = Field(ge=0)
    adverse_fill_rate: Decimal = Field(ge=0, le=1)
    mean_signed_markout_bps: Decimal | None = None
    mean_adverse_markout_bps: Decimal | None = None
    bid_toxic_flow_score: Decimal = Field(ge=0, le=1)
    ask_toxic_flow_score: Decimal = Field(ge=0, le=1)
    overall_toxic_flow_score: Decimal = Field(ge=0, le=1)
    horizons: tuple[HorizonMarkoutMetrics, ...] = Field(default=(), max_length=4)
    markout_1s_bps: Decimal | None = None
    markout_5s_bps: Decimal | None = None
    markout_15s_bps: Decimal | None = None
    bid_adverse_rate: Decimal | None = Field(default=None, ge=0, le=1)
    ask_adverse_rate: Decimal | None = Field(default=None, ge=0, le=1)
    weighted_adverse_severity: Decimal = Field(default=0, ge=0, le=1)
    median_markout_bps: Decimal | None = None
    lower_quantile_markout_bps: Decimal | None = None
    upper_quantile_markout_bps: Decimal | None = None
    recency_weighted_toxicity: Decimal = Field(default=0, ge=0, le=1)
    notional_weighted_toxicity: Decimal | None = Field(default=None, ge=0, le=1)
    toxicity_persistence: Decimal = Field(default=0, ge=0, le=1)
    bid_confidence: Decimal = Field(default=0, ge=0, le=1)
    ask_confidence: Decimal = Field(default=0, ge=0, le=1)


class ToxicFlowAgentOutput(AgentRecommendation):
    state: ToxicFlowState
    metrics: ToxicFlowMetrics


class LevelExecutionMetrics(AgentModel):
    side: str = Field(pattern="^(BID|ASK)$")
    level_index: int = Field(ge=0)
    order_count: int = Field(ge=0)
    filled_order_count: int = Field(ge=0)
    fill_rate: Decimal | None = Field(default=None, ge=0, le=1)
    mean_markout_bps: Decimal | None = None


class ExecutionQualityMetrics(AgentModel):
    fill_count: int = Field(ge=0)
    filled_order_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    average_spread_capture_bps: Decimal | None = None
    average_mature_markout_bps: Decimal | None = None
    reject_count: int = Field(ge=0)
    unknown_order_count: int = Field(ge=0)
    keep_count: int = Field(ge=0)
    create_count: int = Field(ge=0)
    replace_count: int = Field(ge=0)
    cancel_count: int = Field(ge=0)
    reconciliation_churn_ratio: Decimal = Field(ge=0, le=1)
    mean_time_to_first_fill_seconds: Decimal | None = Field(default=None, ge=0)
    mean_time_to_fill_seconds: Decimal | None = Field(default=None, ge=0)
    mean_quote_lifetime_seconds: Decimal | None = Field(default=None, ge=0)
    partial_fill_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    cancel_to_fill_ratio: Decimal | None = Field(default=None, ge=0)
    replace_to_fill_ratio: Decimal | None = Field(default=None, ge=0)
    bid_mean_markout_bps: Decimal | None = None
    ask_mean_markout_bps: Decimal | None = None
    mean_fill_distance_bps: Decimal | None = Field(default=None, ge=0)
    level_quality: tuple[LevelExecutionMetrics, ...] = Field(default=(), max_length=200)
    reconciliation_latency_seconds: Decimal | None = Field(default=None, ge=0)
    venue_acknowledgment_latency_seconds: Decimal | None = Field(default=None, ge=0)


class ExecutionQualityAgentOutput(AgentRecommendation):
    state: ExecutionQualityState
    metrics: ExecutionQualityMetrics


class AgentEvidenceSnapshot(AgentModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    evidence_schema_version: str = "agents-evidence-v2"
    market: str
    market_version: int = Field(ge=0)
    inventory_version: int = Field(ge=0)
    perp_version: int = Field(ge=0)
    reference_version: int = Field(ge=0)
    market_adaptation_regime: str
    realized_volatility: Decimal | None = None
    volatility_score: Decimal = Field(ge=0, le=1)
    book_imbalance: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    history_sample_count: int = Field(ge=0)
    momentum_bps: Decimal | None = None
    inventory_position_base: Decimal
    inventory_ratio: Decimal
    mark_price: Decimal = Field(gt=0)
    oracle_price: Decimal = Field(gt=0)
    funding_rate: Decimal
    open_interest_base: Decimal = Field(ge=0)
    mark_oracle_basis_bps: Decimal
    mark_mid_basis_bps: Decimal
    reference_confidence: str
    max_reference_deviation_bps: Decimal | None = None
    spread_bps: Decimal | None = Field(default=None, ge=0)
    top_n_bid_depth_base: Decimal | None = Field(default=None, ge=0)
    top_n_ask_depth_base: Decimal | None = Field(default=None, ge=0)
    depth_imbalance: Decimal | None = Field(default=None, ge=-1, le=1)
    depth_concentration: Decimal | None = Field(default=None, ge=0, le=1)
    book_span_bps: Decimal | None = Field(default=None, ge=0)
    midpoint_instability_bps: Decimal | None = Field(default=None, ge=0)
    liquidity_depth_levels: int = Field(default=0, ge=0, le=50)
    upstream_available_levels: int | None = Field(default=None, ge=0, le=100)
    book_timestamp: datetime | None = None
    perp_observation_count: int = Field(default=0, ge=0, le=120)
    perp_window_start: datetime | None = None
    perp_window_end: datetime | None = None
    open_interest_change_ratio: Decimal | None = None
    funding_rate_delta: Decimal | None = None
    perp_stale: bool = False
    simulated: bool
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = Field(ge=0)

    @model_validator(mode="after")
    def finite_evidence(self):
        if self.updated_at.tzinfo is None:
            raise ValueError("agent observation timestamp must be timezone-aware")
        if self.open_interest_change_ratio is not None or self.funding_rate_delta is not None:
            if self.perp_observation_count < 2 or self.perp_window_start is None or self.perp_window_end is None:
                raise ValueError("perp changes require retained observation bounds")
            if not self.perp_window_start < self.perp_window_end <= self.updated_at:
                raise ValueError("perp observation bounds must precede evaluation")
        names = (
            "volatility_score", "book_imbalance", "inventory_position_base", "inventory_ratio",
            "mark_price", "oracle_price", "funding_rate", "open_interest_base",
            "mark_oracle_basis_bps", "mark_mid_basis_bps",
        )
        for name in names:
            if not getattr(self, name).is_finite():
                raise ValueError(f"{name} must be finite")
        for name in ("realized_volatility", "momentum_bps", "max_reference_deviation_bps"):
            value = getattr(self, name)
            if value is not None and not value.is_finite():
                raise ValueError(f"{name} must be finite when available")
        return self


class AgentEvent(AgentModel):
    timestamp: datetime = Field(default_factory=utcnow)
    agent: str
    previous_state: str | None = None
    new_state: str
    reasons: list[str] = Field(default_factory=list)
    version: int = Field(ge=0)


class LiquidityQualityState(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    HEALTHY = "HEALTHY"
    THIN = "THIN"
    IMBALANCED = "IMBALANCED"
    UNSTABLE = "UNSTABLE"
    DISLOCATED = "DISLOCATED"


class LiquidityQualityMetrics(AgentModel):
    thin_score: Decimal = Field(default=0, ge=0, le=1)
    imbalance_score: Decimal = Field(default=0, ge=0, le=1)
    instability_score: Decimal = Field(default=0, ge=0, le=1)
    concentration_score: Decimal = Field(default=0, ge=0, le=1)
    spread_bps: Decimal | None = Field(default=None, ge=0)
    bid_depth_base: Decimal | None = Field(default=None, ge=0)
    ask_depth_base: Decimal | None = Field(default=None, ge=0)
    book_span_bps: Decimal | None = Field(default=None, ge=0)


class LiquidityQualityAgentOutput(AgentRecommendation):
    state: LiquidityQualityState
    metrics: LiquidityQualityMetrics


class PerpCrowdingState(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NEUTRAL = "NEUTRAL"
    LONG_CROWDED = "LONG_CROWDED"
    SHORT_CROWDED = "SHORT_CROWDED"
    BASIS_STRESSED = "BASIS_STRESSED"
    OI_EXPANSION = "OI_EXPANSION"
    OI_UNWIND = "OI_UNWIND"


class PerpCrowdingMetrics(AgentModel):
    long_crowding_score: Decimal = Field(default=0, ge=0, le=1)
    short_crowding_score: Decimal = Field(default=0, ge=0, le=1)
    basis_stress_score: Decimal = Field(default=0, ge=0, le=1)
    oi_change_ratio: Decimal | None = None
    funding_rate_delta: Decimal | None = None
    observation_count: int = Field(default=0, ge=0, le=120)


class PerpCrowdingAgentOutput(AgentRecommendation):
    state: PerpCrowdingState
    metrics: PerpCrowdingMetrics


class PredictiveAgentMode(StrEnum):
    DISABLED = "DISABLED"
    SHADOW = "SHADOW"


class PredictiveAdverseSelectionState(StrEnum):
    DISABLED = "DISABLED"
    UNAVAILABLE = "UNAVAILABLE"
    PREDICTED = "PREDICTED"
    ERROR = "ERROR"


class ModelProvenance(AgentModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    model_name: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")
    model_version: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,40}$")
    model_type: str = Field(pattern="^LOGISTIC_REGRESSION$")
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    feature_schema_version: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,60}$")
    training_dataset_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    validation_dataset_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    training_config_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    trained_at: datetime
    training_window_start: datetime
    training_window_end: datetime
    validation_window_start: datetime
    validation_window_end: datetime
    training_sample_count: int = Field(ge=2, le=100000)
    validation_sample_count: int = Field(ge=1, le=100000)
    validation_metrics: dict[str, Decimal | None] = Field(max_length=10)
    library_version: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,40}$")
    market: str = Field(pattern=r"^[A-Z0-9-]{1,20}$")
    simulated: bool
    markout_horizon_seconds: Decimal = Field(gt=0, le=3600)
    target_definition: str = "signed_markout_bps < 0, conditional on observed fill"

    @model_validator(mode="after")
    def valid_windows(self):
        times = (self.trained_at, self.training_window_start, self.training_window_end,
                 self.validation_window_start, self.validation_window_end)
        if any(t.tzinfo is None for t in times):
            raise ValueError("model provenance timestamps must be timezone-aware")
        if not (self.training_window_start <= self.training_window_end <
                self.validation_window_start <= self.validation_window_end):
            raise ValueError("training and validation windows must be disjoint and ordered")
        if self.training_dataset_fingerprint == self.validation_dataset_fingerprint:
            raise ValueError("validation dataset must be independent")
        if self.trained_at < self.validation_window_end:
            raise ValueError("model cannot be trained before its validation labels exist")
        allowed = {"accuracy", "precision", "recall", "roc_auc", "brier_score", "calibration_error"}
        if set(self.validation_metrics) - allowed:
            raise ValueError("unknown validation metric")
        if any(v is not None and not 0 <= v <= 1 for v in self.validation_metrics.values()):
            raise ValueError("classification metrics must be bounded in [0,1]")
        if self.target_definition != "signed_markout_bps < 0, conditional on observed fill":
            raise ValueError("unsupported predictive target")
        return self


class PredictiveAdverseSelectionMetrics(AgentModel):
    bid_adverse_probability: Decimal | None = Field(default=None, ge=0, le=1)
    ask_adverse_probability: Decimal | None = Field(default=None, ge=0, le=1)
    inference_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    markout_horizon_seconds: Decimal | None = Field(default=None, gt=0, le=3600)
    last_inference_time: datetime | None = None


class PredictiveAdverseSelectionAgentOutput(AgentRecommendation):
    mode: PredictiveAgentMode
    state: PredictiveAdverseSelectionState
    affects_quotes: Literal[False] = False
    spread_multiplier: Decimal = Field(default=Decimal(1), ge=1, le=1)
    bid_size_multiplier: Decimal = Field(default=Decimal(1), ge=1, le=1)
    ask_size_multiplier: Decimal = Field(default=Decimal(1), ge=1, le=1)
    max_levels: None = None
    metrics: PredictiveAdverseSelectionMetrics = Field(default_factory=PredictiveAdverseSelectionMetrics)
    model_provenance: ModelProvenance | None = None
    feature_schema_version: str | None = None

    @model_validator(mode="after")
    def shadow_only(self):
        if self.affects_quotes or (self.spread_multiplier, self.bid_size_multiplier,
                                  self.ask_size_multiplier) != (1, 1, 1) or self.max_levels is not None:
            raise ValueError("predictive agent is observational SHADOW ONLY")
        return self


class AgentSupervisorDecision(AgentModel):
    market: str
    enabled: bool
    regime: RegimeAgentOutput
    toxic_flow: ToxicFlowAgentOutput
    execution_quality: ExecutionQualityAgentOutput
    liquidity_quality: LiquidityQualityAgentOutput | None = None
    perp_crowding: PerpCrowdingAgentOutput | None = None
    predictive_adverse_selection: PredictiveAdverseSelectionAgentOutput | None = None
    spread_multiplier: Decimal = Field(ge=1)
    bid_size_multiplier: Decimal = Field(gt=0, le=1)
    ask_size_multiplier: Decimal = Field(gt=0, le=1)
    max_levels: int | None = Field(default=None, ge=1)
    reasons: list[str] = Field(default_factory=list)
    market_version: int = Field(ge=0)
    inventory_version: int = Field(ge=0)
    perp_version: int = Field(ge=0)
    reference_version: int = Field(ge=0)
    simulated: bool
    version: int = Field(ge=0)
    fingerprint: str
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def finite_supervisor(self):
        for name in ("spread_multiplier", "bid_size_multiplier", "ask_size_multiplier"):
            if not getattr(self, name).is_finite():
                raise ValueError(f"{name} must be finite")
        return self


def _canonical(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):
        return _canonical(value.model_dump())
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def semantic_fingerprint(value) -> str:
    raw = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def recommendation_signature(output: AgentRecommendation) -> dict:
    data = {
        "agent": output.agent,
        "health": output.health,
        "confidence": output.confidence,
        "spread_multiplier": output.spread_multiplier,
        "bid_size_multiplier": output.bid_size_multiplier,
        "ask_size_multiplier": output.ask_size_multiplier,
        "max_levels": output.max_levels,
        "reasons": output.reasons,
        "simulated": output.simulated,
    }
    if isinstance(output, RegimeAgentOutput):
        data.update({"state": output.state, "direction": output.direction})
    elif isinstance(output, ToxicFlowAgentOutput):
        data.update({"state": output.state})
    elif isinstance(output, ExecutionQualityAgentOutput):
        data.update({"state": output.state})
    elif isinstance(output, (LiquidityQualityAgentOutput, PerpCrowdingAgentOutput)):
        data.update({"state": output.state})
    data["implementation_version"] = output.implementation_version
    return data
