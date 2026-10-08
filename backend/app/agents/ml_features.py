"""Canonical, bounded normalized features shared by offline training and inference."""
from decimal import Decimal
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from .common import clamp
from .models import AgentModel, AgentEvidenceSnapshot

FEATURE_SCHEMA_VERSION = "passive-adverse-v1"
FEATURE_NAMES = (
    "volatility_score", "book_imbalance", "momentum_100bps", "spread_100bps",
    "bid_depth_100base", "ask_depth_100base", "mark_oracle_basis_100bps",
    "mark_mid_basis_100bps", "funding_001rate", "inventory_ratio",
    "reference_deviation_100bps", "side_sign",
)


class FeatureSchema(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    feature_schema_version: Literal["passive-adverse-v1"] = FEATURE_SCHEMA_VERSION
    feature_names: tuple[str, ...] = FEATURE_NAMES
    missing_policy: Literal["REJECT_REQUIRED"] = "REJECT_REQUIRED"
    normalization: Literal["CLIP_MINUS_ONE_PLUS_ONE"] = "CLIP_MINUS_ONE_PLUS_ONE"

    @model_validator(mode="after")
    def canonical_order(self):
        if self.feature_names != FEATURE_NAMES:
            raise ValueError("feature ordering differs from canonical schema")
        return self


FEATURE_SCHEMA = FeatureSchema()


class FeatureVector(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    feature_schema_version: Literal["passive-adverse-v1"] = FEATURE_SCHEMA_VERSION
    values: tuple[Decimal, ...] = Field(min_length=len(FEATURE_NAMES), max_length=len(FEATURE_NAMES))
    side: Literal["BID", "ASK"]

    @model_validator(mode="after")
    def bounded_vector(self):
        if any(not v.is_finite() or not -1 <= v <= 1 for v in self.values):
            raise ValueError("features must be finite normalized values in [-1,1]")
        if self.values[-1] != (1 if self.side == "BID" else -1):
            raise ValueError("feature side sign mismatch")
        return self


def build_feature_vector(evidence: AgentEvidenceSnapshot, side: Literal["BID", "ASK"]) -> FeatureVector:
    # Revalidate copied models at the boundary, including NaN/null fields.
    evidence = AgentEvidenceSnapshot.model_validate(evidence.model_dump())
    required = (evidence.momentum_bps, evidence.spread_bps, evidence.top_n_bid_depth_base,
                evidence.top_n_ask_depth_base, evidence.max_reference_deviation_bps)
    if any(v is None for v in required):
        raise ValueError("required normalized feature unavailable")
    if evidence.updated_at.tzinfo is None or any(t is not None and (t.tzinfo is None or t > evidence.updated_at)
            for t in (evidence.book_timestamp, evidence.perp_window_end)):
        raise ValueError("feature source evidence exceeds observation time")
    values = (
        evidence.volatility_score, evidence.book_imbalance, evidence.momentum_bps/100,
        evidence.spread_bps/100, evidence.top_n_bid_depth_base/100, evidence.top_n_ask_depth_base/100,
        evidence.mark_oracle_basis_bps/100, evidence.mark_mid_basis_bps/100,
        evidence.funding_rate/Decimal(".001"), evidence.inventory_ratio,
        evidence.max_reference_deviation_bps/100, Decimal(1 if side == "BID" else -1),
    )
    return FeatureVector(values=tuple(clamp(v, Decimal(-1), Decimal(1)) for v in values), side=side)
