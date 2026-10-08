from __future__ import annotations

from decimal import Decimal

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import PredictiveAgentMode


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    agents_enabled: bool = True
    regime_agent_enabled: bool = True
    toxic_flow_agent_enabled: bool = True
    execution_quality_agent_enabled: bool = True
    liquidity_quality_agent_enabled: bool = True
    perp_crowding_agent_enabled: bool = True
    predictive_agent_enabled: bool = True
    predictive_agent_mode: PredictiveAgentMode = PredictiveAgentMode.SHADOW
    # Artifacts are injected from a trusted operator boundary, never loaded by GET/config.
    predictive_min_confidence: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)

    agent_max_spread_multiplier: Decimal = Field(default=Decimal("1.75"), ge=1, le=10)
    agent_min_size_multiplier: Decimal = Decimal("0.35")
    agent_min_confidence: Decimal = Decimal("0.20")

    regime_momentum_window_samples: int = Field(default=20, ge=2, le=500)
    regime_min_samples: int = Field(default=8, ge=2, le=500)
    regime_trend_threshold_bps: Decimal = Decimal("15")
    regime_dislocation_bps: Decimal = Decimal("50")
    regime_spread_strength: Decimal = Decimal("0.40")
    regime_size_strength: Decimal = Decimal("0.30")
    regime_funding_stress_threshold: Decimal = Field(default=Decimal("0.0005"), gt=0, le=1)
    regime_basis_stress_threshold_bps: Decimal = Field(default=Decimal("30"), gt=0, le=10000)

    toxic_flow_window_fills: int = Field(default=100, ge=1, le=1000)
    toxic_flow_min_matured_fills: int = Field(default=5, ge=1, le=1000)
    toxic_flow_markout_horizon_seconds: float = Field(default=5.0, gt=0, le=3600)
    toxic_flow_markout_horizons_seconds: tuple[Annotated[float, Field(gt=0, le=3600)], ...] = Field(default=(1.0, 5.0, 15.0), min_length=1, max_length=3)
    toxic_flow_recency_half_life_seconds: Decimal = Field(default=Decimal("60"), gt=0, le=86400)
    toxic_flow_adverse_markout_bps: Decimal = Decimal("3")
    toxic_flow_spread_strength: Decimal = Decimal("0.50")
    toxic_flow_size_strength: Decimal = Decimal("0.60")

    execution_quality_window: int = Field(default=50, ge=1, le=1000)
    execution_quality_min_fills: int = Field(default=5, ge=1, le=1000)
    execution_quality_poor_markout_bps: Decimal = Decimal("3")
    execution_quality_max_churn_ratio: Decimal = Decimal("0.65")
    execution_quality_spread_strength: Decimal = Decimal("0.40")
    execution_quality_size_strength: Decimal = Decimal("0.40")

    liquidity_depth_levels: int = Field(default=5, ge=1, le=50)
    liquidity_thin_depth_base: Decimal = Field(default=Decimal("1"), gt=0, le=1000000000)
    liquidity_imbalance_threshold: Decimal = Field(default=Decimal("0.65"), gt=0, le=1)
    liquidity_instability_threshold_bps: Decimal = Field(default=Decimal("20"), gt=0, le=10000)
    liquidity_wide_spread_threshold_bps: Decimal = Field(default=Decimal("25"), gt=0, le=10000)
    liquidity_concentration_threshold: Decimal = Field(default=Decimal("0.85"), gt=0, le=1)
    liquidity_reduced_max_levels: int = Field(default=2, ge=1, le=100)
    liquidity_spread_strength: Decimal = Field(default=Decimal("0.35"), ge=0, le=1)
    liquidity_size_strength: Decimal = Field(default=Decimal("0.40"), ge=0, le=1)

    perp_observation_window: int = Field(default=30, ge=2, le=120)
    perp_min_observation_span_seconds: Decimal = Field(default=Decimal("5"), gt=0, le=86400)
    perp_max_observation_span_seconds: Decimal = Field(default=Decimal("900"), gt=0, le=86400)
    crowding_funding_threshold: Decimal = Field(default=Decimal("0.0003"), gt=0, le=1)
    crowding_basis_threshold_bps: Decimal = Field(default=Decimal("15"), gt=0, le=10000)
    crowding_oi_change_threshold: Decimal = Field(default=Decimal("0.02"), gt=0, le=10)
    crowding_spread_strength: Decimal = Field(default=Decimal("0.30"), ge=0, le=1)
    crowding_size_strength: Decimal = Field(default=Decimal("0.40"), ge=0, le=1)

    @model_validator(mode="after")
    def validate_agent_config(self):
        horizons = self.toxic_flow_markout_horizons_seconds
        if tuple(sorted(set(horizons))) != horizons:
            raise ValueError("markout horizons must be unique and increasing")
        if self.perp_min_observation_span_seconds > self.perp_max_observation_span_seconds:
            raise ValueError("perp observation span bounds are reversed")
        decimals = {
            "agent_max_spread_multiplier": self.agent_max_spread_multiplier,
            "agent_min_size_multiplier": self.agent_min_size_multiplier,
            "agent_min_confidence": self.agent_min_confidence,
            "regime_trend_threshold_bps": self.regime_trend_threshold_bps,
            "regime_dislocation_bps": self.regime_dislocation_bps,
            "regime_spread_strength": self.regime_spread_strength,
            "regime_size_strength": self.regime_size_strength,
            "toxic_flow_adverse_markout_bps": self.toxic_flow_adverse_markout_bps,
            "toxic_flow_spread_strength": self.toxic_flow_spread_strength,
            "toxic_flow_size_strength": self.toxic_flow_size_strength,
            "execution_quality_poor_markout_bps": self.execution_quality_poor_markout_bps,
            "execution_quality_max_churn_ratio": self.execution_quality_max_churn_ratio,
            "execution_quality_spread_strength": self.execution_quality_spread_strength,
            "execution_quality_size_strength": self.execution_quality_size_strength,
        }
        for name, value in decimals.items():
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")

        if self.agent_max_spread_multiplier < 1:
            raise ValueError("agent_max_spread_multiplier must be >= 1")
        if not Decimal("0") < self.agent_min_size_multiplier <= 1:
            raise ValueError("agent_min_size_multiplier must be in (0, 1]")
        if not Decimal("0") <= self.agent_min_confidence <= 1:
            raise ValueError("agent_min_confidence must be in [0, 1]")
        if self.regime_min_samples > self.regime_momentum_window_samples:
            raise ValueError("regime_min_samples cannot exceed regime_momentum_window_samples")
        if self.toxic_flow_min_matured_fills > self.toxic_flow_window_fills:
            raise ValueError("toxic_flow_min_matured_fills cannot exceed toxic_flow_window_fills")
        if self.execution_quality_min_fills > self.execution_quality_window:
            raise ValueError("execution_quality_min_fills cannot exceed execution_quality_window")
        for name in (
            "regime_trend_threshold_bps",
            "regime_dislocation_bps",
            "toxic_flow_adverse_markout_bps",
            "execution_quality_poor_markout_bps",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        for name in (
            "regime_spread_strength",
            "regime_size_strength",
            "toxic_flow_spread_strength",
            "toxic_flow_size_strength",
            "execution_quality_spread_strength",
            "execution_quality_size_strength",
        ):
            if not Decimal("0") <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if not Decimal("0") < self.execution_quality_max_churn_ratio <= 1:
            raise ValueError("execution_quality_max_churn_ratio must be in (0, 1]")
        return self
