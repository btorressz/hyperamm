"""Canonical, bounded normalized features shared by offline training and inference."""
from datetime import datetime, timedelta
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

# Fixed shared as-of policy: match the normal 5s book / 10s perp conventions;
# 30s admits the existing public-HTTP reference fallback. Provider stale flags
# still apply when their configured limit is stricter. No wall clock is used.
FEATURE_MAX_AGE = {"book": timedelta(seconds=5), "perpetual": timedelta(seconds=10),
                   "reference": timedelta(seconds=30)}


class FeatureUnavailableError(ValueError):
    """Only fixed public diagnostics, safe to expose in SHADOW output."""


def _require_fresh(timestamp, *, name, as_of):
    if timestamp is None or timestamp.tzinfo is None:
        raise FeatureUnavailableError(f"required {name} timestamp unavailable")
    age = as_of - timestamp
    if age < timedelta(0):
        raise FeatureUnavailableError(f"required {name} observation is future-dated")
    if age > FEATURE_MAX_AGE[name]:
        raise FeatureUnavailableError(f"required {name} observation is stale")


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


def build_feature_vector(evidence: AgentEvidenceSnapshot, side: Literal["BID", "ASK"], *,
                         as_of: datetime | None = None) -> FeatureVector:
    # Revalidate copied models at the boundary, including NaN/null fields.
    evidence = AgentEvidenceSnapshot.model_validate(evidence.model_dump())
    as_of = evidence.updated_at if as_of is None else as_of
    if as_of.tzinfo is None or as_of < evidence.updated_at:
        raise FeatureUnavailableError("feature observation exceeds as-of time")
    required = (evidence.momentum_bps, evidence.spread_bps, evidence.top_n_bid_depth_base,
                evidence.top_n_ask_depth_base, evidence.max_reference_deviation_bps)
    if any(v is None for v in required):
        raise FeatureUnavailableError("required normalized feature unavailable")
    if evidence.perp_stale:
        raise FeatureUnavailableError("required perpetual context explicitly stale")
    if evidence.perp_window_end is not None and (evidence.perp_window_end.tzinfo is None
            or evidence.perp_window_end > evidence.updated_at):
        raise FeatureUnavailableError("perpetual observation window exceeds feature time")
    # Sources must already exist at the feature observation, then remain fresh
    # at use time (offline fill selection may be later than that observation).
    for name, timestamp in (("book", evidence.book_timestamp), ("perpetual", evidence.perp_timestamp)):
        _require_fresh(timestamp, name=name, as_of=evidence.updated_at)
        _require_fresh(timestamp, name=name, as_of=as_of)
    if (evidence.reference_confidence not in {"VERIFIED", "DEGRADED"}
            or len(evidence.reference_provenance) < 2
            or not evidence.reference_provenance.keys() <= {"REDSTONE", "HYPERLIQUID_ORACLE", "KRAKEN"}):
        raise FeatureUnavailableError("required reference consensus unavailable")
    for provider, item in evidence.reference_provenance.items():
        if (item.provider.value != provider or item.market != evidence.market or not item.healthy
                or item.stale or item.status.value != "HEALTHY" or item.price is None):
            raise FeatureUnavailableError("required reference evidence unavailable or explicitly stale")
        # Validate both receipt and source time; a new envelope cannot refresh an old price.
        for timestamp in (item.observed_at, item.source_timestamp):
            _require_fresh(timestamp, name="reference", as_of=evidence.updated_at)
            _require_fresh(timestamp, name="reference", as_of=as_of)
    values = (
        evidence.volatility_score, evidence.book_imbalance, evidence.momentum_bps/100,
        evidence.spread_bps/100, evidence.top_n_bid_depth_base/100, evidence.top_n_ask_depth_base/100,
        evidence.mark_oracle_basis_bps/100, evidence.mark_mid_basis_bps/100,
        evidence.funding_rate/Decimal(".001"), evidence.inventory_ratio,
        evidence.max_reference_deviation_bps/100, Decimal(1 if side == "BID" else -1),
    )
    return FeatureVector(values=tuple(clamp(v, Decimal(-1), Decimal(1)) for v in values), side=side)
