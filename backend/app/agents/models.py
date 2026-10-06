from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum, StrEnum

from pydantic import BaseModel, Field, model_validator

from app.market_data.models import utcnow


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


class AgentRecommendation(BaseModel):
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


class ToxicFlowMetrics(BaseModel):
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


class ToxicFlowAgentOutput(AgentRecommendation):
    state: ToxicFlowState
    metrics: ToxicFlowMetrics


class ExecutionQualityMetrics(BaseModel):
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


class ExecutionQualityAgentOutput(AgentRecommendation):
    state: ExecutionQualityState
    metrics: ExecutionQualityMetrics


class AgentEvidenceSnapshot(BaseModel):
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
    simulated: bool
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = Field(ge=0)

    @model_validator(mode="after")
    def finite_evidence(self):
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


class AgentEvent(BaseModel):
    timestamp: datetime = Field(default_factory=utcnow)
    agent: str
    previous_state: str | None = None
    new_state: str
    reasons: list[str] = Field(default_factory=list)
    version: int = Field(ge=0)


class AgentSupervisorDecision(BaseModel):
    market: str
    enabled: bool
    regime: RegimeAgentOutput
    toxic_flow: ToxicFlowAgentOutput
    execution_quality: ExecutionQualityAgentOutput
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
    return data
