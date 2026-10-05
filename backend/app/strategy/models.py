from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from app.amm.models import AmmModel
from app.market_data.models import MarketDataMode


class ExecutionMode(StrEnum):
    PAPER = "PAPER"
    TESTNET = "TESTNET"


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

    inventory_skew_enabled: bool = True
    target_inventory_base: Decimal = Decimal("0")
    soft_inventory_limit_base: Decimal = Field(default=Decimal("5"), gt=0)
    hard_inventory_limit_base: Decimal = Field(default=Decimal("10"), gt=0)
    max_inventory_price_skew_bps: Decimal = Field(default=Decimal("20"), ge=0, le=Decimal("500"))
    inventory_size_skew_strength: Decimal = Field(default=Decimal("0.75"), ge=0, le=Decimal("2"))
    min_inventory_size_multiplier: Decimal = Field(default=Decimal("0.25"), gt=0)
    max_inventory_size_multiplier: Decimal = Field(default=Decimal("1.75"), ge=Decimal("1"))
    inventory_stale_after_seconds: float = Field(default=10.0, gt=0, le=300)

    market_adaptation_enabled: bool = True
    volatility_window_samples: int = Field(default=60, ge=2, le=1000)
    volatility_min_samples: int = Field(default=10, ge=2, le=1000)
    volatility_low_threshold: Decimal = Field(default=Decimal("0.0002"), ge=0)
    volatility_high_threshold: Decimal = Field(default=Decimal("0.0020"), gt=0)
    volatility_spread_strength: Decimal = Field(default=Decimal("1.0"), ge=0)
    volatility_size_strength: Decimal = Field(default=Decimal("0.50"), ge=0, le=Decimal("1"))
    book_imbalance_levels: int = Field(default=5, ge=1, le=50)
    imbalance_spread_strength: Decimal = Field(default=Decimal("0.25"), ge=0)
    imbalance_size_strength: Decimal = Field(default=Decimal("0.25"), ge=0, le=Decimal("1"))
    min_spread_multiplier: Decimal = Field(default=Decimal("1.0"), gt=0)
    max_spread_multiplier: Decimal = Field(default=Decimal("2.5"), ge=Decimal("1"))
    min_market_size_multiplier: Decimal = Field(default=Decimal("0.35"), gt=0, le=Decimal("1"))

    perp_context_enabled: bool = True
    perp_context_stale_after_seconds: float = Field(default=10.0, gt=0, le=300)
    perp_mark_weight: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    perp_oracle_weight: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    funding_reference_abs_rate: Decimal = Field(default=Decimal("0.00025"), gt=0)
    max_funding_reference_shift_bps: Decimal = Field(default=Decimal("5"), ge=0, le=Decimal("100"))
    max_perp_reference_shift_bps: Decimal = Field(default=Decimal("50"), ge=0, le=Decimal("1000"))

    @model_validator(mode="after")
    def bounds(self):
        if self.concentration_upper_bps <= self.concentration_lower_bps:
            raise ValueError("concentration_upper_bps must exceed lower bound")
        if self.total_liquidity < self.base_order_size * Decimal(self.levels_per_side):
            raise ValueError("total_liquidity must be at least base_order_size * levels_per_side")
        decimal_fields = (
            "virtual_base_reserve", "virtual_quote_reserve", "max_distance_bps", "base_order_size",
            "total_liquidity", "concentration_factor", "concentration_lower_bps", "concentration_upper_bps",
            "replace_tolerance_bps", "size_tolerance", "tick_size", "target_inventory_base",
            "soft_inventory_limit_base", "hard_inventory_limit_base", "max_inventory_price_skew_bps",
            "inventory_size_skew_strength", "min_inventory_size_multiplier", "max_inventory_size_multiplier",
            "volatility_low_threshold", "volatility_high_threshold", "volatility_spread_strength",
            "volatility_size_strength", "imbalance_spread_strength", "imbalance_size_strength",
            "min_spread_multiplier", "max_spread_multiplier", "min_market_size_multiplier",
            "perp_mark_weight", "perp_oracle_weight", "funding_reference_abs_rate",
            "max_funding_reference_shift_bps", "max_perp_reference_shift_bps",
        )
        if any(not getattr(self, name).is_finite() for name in decimal_fields):
            raise ValueError("strategy decimal configuration must be finite")
        if self.hard_inventory_limit_base <= self.soft_inventory_limit_base:
            raise ValueError("hard_inventory_limit_base must exceed soft_inventory_limit_base")
        if self.min_inventory_size_multiplier > Decimal("1"):
            raise ValueError("min_inventory_size_multiplier must be <= 1")
        if self.min_inventory_size_multiplier > self.max_inventory_size_multiplier:
            raise ValueError("min_inventory_size_multiplier must not exceed max_inventory_size_multiplier")
        if self.volatility_window_samples < self.volatility_min_samples:
            raise ValueError("volatility_window_samples must be >= volatility_min_samples")
        if self.volatility_high_threshold <= self.volatility_low_threshold:
            raise ValueError("volatility_high_threshold must exceed volatility_low_threshold")
        if self.max_spread_multiplier < self.min_spread_multiplier:
            raise ValueError("max_spread_multiplier must be >= min_spread_multiplier")
        if self.min_spread_multiplier < Decimal("1"):
            raise ValueError("Phase 6 widening-only policy requires min_spread_multiplier >= 1")
        if self.perp_mark_weight + self.perp_oracle_weight > Decimal("1"):
            raise ValueError("perp mark + oracle weights must be <= 1")
        return self


class StrategyState(BaseModel):
    running: bool = False
    config: StrategyConfig
    last_error: str | None = None
    quote_health: Literal["NO_QUOTES", "HEALTHY", "DEGRADED", "HALTED"] = "NO_QUOTES"
