from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.amm.models import AmmModel
from app.market_data.models import MarketDataMode


class ExecutionMode(StrEnum):
    PAPER="PAPER"
    TESTNET="TESTNET"


class StrategyConfig(BaseModel):
    market: str = "ETH"
    market_data_mode: MarketDataMode = MarketDataMode.DEMO
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    amm_model: AmmModel = AmmModel.CONSTANT_PRODUCT
    virtual_base_reserve: Decimal = Field(default=Decimal("100"), gt=0)
    virtual_quote_reserve: Decimal = Field(default=Decimal("300000"), gt=0)
    levels_per_side: int = Field(default=8, ge=1, le=50)
    max_distance_bps: Decimal = Field(default=Decimal("100"), gt=0, le=Decimal("2500"))
    base_order_size: Decimal = Field(default=Decimal("0.10"), gt=0)
    total_liquidity: Decimal = Field(default=Decimal("4.0"), gt=0)
    concentration_factor: Decimal = Field(default=Decimal("8"), ge=0, le=Decimal("1000"))
    concentration_lower_bps: Decimal = Field(default=Decimal("10"), ge=0)
    concentration_upper_bps: Decimal = Field(default=Decimal("200"), gt=0)
    quote_refresh_interval_ms: int = Field(default=1000, ge=100, le=60000)
    replace_tolerance_bps: Decimal = Field(default=Decimal("0.5"), ge=0, le=Decimal("100"))
    size_tolerance: Decimal = Field(default=Decimal("0.0001"), ge=0)
    tick_size: Decimal = Field(default=Decimal("0.1"), gt=0)
    size_precision: int = Field(default=4, ge=0, le=8)

    @model_validator(mode="after")
    def bounds(self):
        if self.concentration_upper_bps <= self.concentration_lower_bps:
            raise ValueError("concentration_upper_bps must exceed lower bound")
        if self.total_liquidity < self.base_order_size * Decimal(self.levels_per_side):
            raise ValueError("total_liquidity must be at least base_order_size * levels_per_side")
        return self


class StrategyState(BaseModel):
    running: bool = False
    config: StrategyConfig
    last_error: str | None = None
    quote_health: Literal["NO_QUOTES","HEALTHY","DEGRADED","HALTED"] = "NO_QUOTES"
