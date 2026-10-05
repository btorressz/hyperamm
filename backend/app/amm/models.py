from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from pydantic import BaseModel, Field, model_validator


class AmmModel(StrEnum):
    CONSTANT_PRODUCT = "CONSTANT_PRODUCT"
    CONCENTRATED = "CONCENTRATED"


class VirtualPool(BaseModel):
    reserve_base: Decimal = Field(gt=0)
    reserve_quote: Decimal = Field(gt=0)
    k: Decimal = Field(gt=0)
    reference_price: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def invariant_matches(self):
        if abs((self.reserve_base * self.reserve_quote) - self.k) > Decimal("1e-18") * max(self.k, Decimal("1")):
            raise ValueError("k must equal reserve_base * reserve_quote")
        return self


class CurvePoint(BaseModel):
    side: str
    distance_bps: Decimal = Field(ge=0)
    price: Decimal = Field(gt=0)
    target_base: Decimal = Field(gt=0)
    incremental_base: Decimal = Field(gt=0)
    cumulative_base: Decimal = Field(gt=0)
    weight: Decimal = Field(gt=0)


class QuoteLevel(BaseModel):
    side: str
    price: Decimal = Field(gt=0)
    size: Decimal = Field(gt=0)
    level_index: int = Field(ge=0)
    distance_bps: Decimal = Field(ge=0)
    source_model: AmmModel
    state: str = "DESIRED"
    neutral_price: Decimal | None = None
    neutral_size: Decimal | None = None
    inventory_intent: str | None = None
    inventory_effect: str | None = None
    pre_market_adaptation_price: Decimal | None = None
    pre_market_adaptation_size: Decimal | None = None
    market_spread_multiplier: Decimal | None = None
    market_size_multiplier: Decimal | None = None
    volatility_effect: str | None = None
    imbalance_effect: str | None = None
    market_fair_value: Decimal | None = None
    perp_reference_price: Decimal | None = None
    inventory_adjusted_price: Decimal | None = None
    pre_risk_price: Decimal | None = None
    pre_risk_size: Decimal | None = None
    risk_spread_multiplier: Decimal | None = None
    risk_size_multiplier: Decimal | None = None
    risk_state: str | None = None
    authorization_fingerprint: str | None = None
