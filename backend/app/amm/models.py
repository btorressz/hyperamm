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
    cumulative_base: Decimal = Field(ge=0)
    weight: Decimal = Field(gt=0)


class QuoteLevel(BaseModel):
    side: str
    price: Decimal = Field(gt=0)
    size: Decimal = Field(gt=0)
    level_index: int = Field(ge=0)
    distance_bps: Decimal = Field(ge=0)
    source_model: AmmModel
    state: str = "DESIRED"
