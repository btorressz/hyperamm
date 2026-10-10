"""Immutable REST evidence for native public perpetual observations, without authority."""
from __future__ import annotations

import re
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field,
                      PlainSerializer, StrictBool, StrictInt, model_validator)

from app.simulation.market_profiles import ResearchPerpMarketId

LiveMarketId = ResearchPerpMarketId


def financial_decimal(value):
    # Official wire values are decimal strings. Reject float rounding, booleans,
    # exponent bombs and nonfinite inputs before existing financial arithmetic.
    if isinstance(value, str):
        if len(value) > 80 or not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
            raise ValueError("invalid financial decimal string")
        value = Decimal(value)
    elif type(value) is int:
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("finite Decimal required; binary floats are not accepted")
    if abs(value) > Decimal("1e30") or not -60 <= value.as_tuple().exponent <= 30:
        raise ValueError("financial decimal outside observation bounds")
    return value


FinancialDecimal = Annotated[Decimal, BeforeValidator(financial_decimal),
    PlainSerializer(lambda value: format(value, "f"), return_type=str, when_used="json")]
PositiveDecimal = Annotated[FinancialDecimal, Field(gt=0)]
NonnegativeDecimal = Annotated[FinancialDecimal, Field(ge=0)]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class LiveObservationStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


class LiveObservationError(Evidence):
    component: Literal["metadata", "order_book", "perp_context", "service", "snapshot"]
    code: Literal["DISABLED", "CLOSED", "CAPACITY", "TIMEOUT", "FORBIDDEN", "RATE_LIMITED",
                  "UPSTREAM_ERROR", "SDK_UNAVAILABLE", "NETWORK_ERROR", "INVALID_DATA",
                  "NOT_LISTED", "TEMPORAL_DISCREPANCY", "CLEANUP_ERROR"]
    message: str


class LiveMarketMetadata(Evidence):
    market: LiveMarketId
    dex: Literal[""] = ""
    metadata_status: Literal["EXCHANGE_VERIFIED", "UNAVAILABLE", "STALE", "ERROR"]
    source: Literal["OFFICIAL_SDK_NATIVE_META", "NONE"]
    sz_decimals: StrictInt | None = Field(default=None, ge=0, le=6)
    asset_index: StrictInt | None = Field(default=None, ge=0)
    listed: StrictBool | None = None
    observed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def verified_evidence(self):
        if self.metadata_status == "EXCHANGE_VERIFIED" and (
            self.source != "OFFICIAL_SDK_NATIVE_META" or self.listed is not True or
            self.observed_at is None or self.asset_index is None or self.sz_decimals is None
        ):
            raise ValueError("verified native metadata requires actual listing evidence")
        return self


class LiveBookLevel(Evidence):
    price: PositiveDecimal
    size: NonnegativeDecimal
    order_count: StrictInt = Field(default=0, ge=0)


class LiveBookObservation(Evidence):
    market: LiveMarketId
    bids: tuple[LiveBookLevel, ...] = Field(min_length=1, max_length=20)
    asks: tuple[LiveBookLevel, ...] = Field(min_length=1, max_length=20)
    source_timestamp: AwareDatetime
    observed_at: AwareDatetime
    source: Literal["OFFICIAL_SDK_L2_SNAPSHOT"] = "OFFICIAL_SDK_L2_SNAPSHOT"
    best_bid: PositiveDecimal
    best_ask: PositiveDecimal
    midpoint: PositiveDecimal
    spread: PositiveDecimal
    spread_bps: PositiveDecimal
    truncated: StrictBool = False

    @model_validator(mode="after")
    def consistent_book(self):
        if any(a.price <= b.price for a, b in zip(self.bids, self.bids[1:])):
            raise ValueError("bids must be strictly descending")
        if any(a.price >= b.price for a, b in zip(self.asks, self.asks[1:])):
            raise ValueError("asks must be strictly ascending")
        bid, ask = self.bids[0].price, self.asks[0].price
        if bid >= ask or (self.best_bid, self.best_ask) != (bid, ask):
            raise ValueError("crossed or inconsistent top of book")
        if self.midpoint != (bid + ask) / 2 or self.spread != ask - bid:
            raise ValueError("inconsistent midpoint/spread")
        if self.spread_bps != self.spread / self.midpoint * Decimal("10000"):
            raise ValueError("inconsistent spread basis")
        return self


class LivePerpObservation(Evidence):
    market: LiveMarketId
    source: Literal["OFFICIAL_SDK_META_AND_ASSET_CTXS"] = "OFFICIAL_SDK_META_AND_ASSET_CTXS"
    source_timestamp: Literal[None] = None
    observed_at: AwareDatetime
    mark_price: PositiveDecimal
    oracle_price: PositiveDecimal
    funding_rate: FinancialDecimal
    open_interest_base: NonnegativeDecimal
    open_interest_notional: NonnegativeDecimal
    provider_mid_price: PositiveDecimal | None = None
    premium: FinancialDecimal | None = None
    mark_oracle_basis_bps: FinancialDecimal
    mark_mid_basis_bps: FinancialDecimal | None = None
    oracle_mid_basis_bps: FinancialDecimal | None = None


class LiveFreshness(Evidence):
    metadata_age_seconds: float | None = None
    l2_source_age_seconds: float | None = None
    perp_observation_age_seconds: float | None = None
    metadata: Literal["FRESH", "STALE", "UNAVAILABLE"] = "UNAVAILABLE"
    order_book: Literal["FRESH", "STALE", "UNAVAILABLE"] = "UNAVAILABLE"
    perp_context: Literal["FRESH", "STALE", "UNAVAILABLE"] = "UNAVAILABLE"
    perp_event_time: Literal["UNKNOWN"] = "UNKNOWN"
    acquisition_gap_seconds: float | None = None
    acquisition_coherent: StrictBool | None = None


class LiveMarketSnapshot(Evidence):
    contract_version: Literal["phase151-v1"] = "phase151-v1"
    market: LiveMarketId
    display_name: str
    exchange: Literal["HYPERLIQUID"] = "HYPERLIQUID"
    dex: Literal[""] = ""
    market_type: Literal["PERPETUAL"] = "PERPETUAL"
    read_only: Literal[True] = True
    simulated: Literal[False] = False
    observation_status: LiveObservationStatus
    metadata: LiveMarketMetadata
    order_book: LiveBookObservation | None = None
    perp_context: LivePerpObservation | None = None
    observed_at: AwareDatetime | None = None
    generated_at: AwareDatetime
    cache_stored_at: AwareDatetime | None = None
    cache_age_seconds: float | None = None
    last_successful_observed_at: AwareDatetime | None = None
    freshness: LiveFreshness = Field(default_factory=LiveFreshness)
    errors: tuple[LiveObservationError, ...] = ()
    limitations: tuple[str, ...] = (
        "Read-only describes this API's authority; observations grant no trading permission.",
        "One Hyperliquid source, no independent oracle quorum.",
        "REST perpetual context has no exchange event timestamp; retrieval freshness is not event-time proof.",
        "Separate REST acquisitions do not prove book/context synchronization.",
        "Bounded snapshot only; no continuous stream or market history.")

    @model_validator(mode="after")
    def identities(self):
        if self.display_name != f"{self.market}-PERP":
            raise ValueError("invalid display identity")
        if any(item is not None and item.market != self.market
               for item in (self.metadata, self.order_book, self.perp_context)):
            raise ValueError("mixed observation identities")
        if (self.order_book or self.perp_context) and self.metadata.source != "OFFICIAL_SDK_NATIVE_META":
            raise ValueError("live values require exchange metadata")
        if self.observation_status == LiveObservationStatus.AVAILABLE and (
            self.errors or self.order_book is None or self.perp_context is None or
            self.metadata.metadata_status != "EXCHANGE_VERIFIED" or
            any(value != "FRESH" for value in (self.freshness.metadata, self.freshness.order_book,
                                               self.freshness.perp_context)) or
            self.freshness.acquisition_coherent is not True
        ):
            raise ValueError("available observation requires fresh complete evidence")
        return self


class LiveMarketOverview(Evidence):
    contract_version: Literal["phase151-v1"] = "phase151-v1"
    read_only: Literal[True] = True
    simulated: Literal[False] = False
    generated_at: AwareDatetime
    markets: tuple[LiveMarketSnapshot, LiveMarketSnapshot, LiveMarketSnapshot]

    @model_validator(mode="after")
    def fixed_markets(self):
        from app.simulation.market_profiles import MARKETS
        if tuple(item.market for item in self.markets) != MARKETS:
            raise ValueError("overview must contain BTC, ETH, SOL exactly once in catalog order")
        return self
