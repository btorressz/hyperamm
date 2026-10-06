from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class AgentConfig(BaseModel):
    agents_enabled: bool = True
    regime_agent_enabled: bool = True
    toxic_flow_agent_enabled: bool = True
    execution_quality_agent_enabled: bool = True

    agent_max_spread_multiplier: Decimal = Decimal("1.75")
    agent_min_size_multiplier: Decimal = Decimal("0.35")
    agent_min_confidence: Decimal = Decimal("0.20")

    regime_momentum_window_samples: int = Field(default=20, ge=2, le=500)
    regime_min_samples: int = Field(default=8, ge=2, le=500)
    regime_trend_threshold_bps: Decimal = Decimal("15")
    regime_dislocation_bps: Decimal = Decimal("50")
    regime_spread_strength: Decimal = Decimal("0.40")
    regime_size_strength: Decimal = Decimal("0.30")

    toxic_flow_window_fills: int = Field(default=100, ge=1, le=1000)
    toxic_flow_min_matured_fills: int = Field(default=5, ge=1, le=1000)
    toxic_flow_markout_horizon_seconds: float = Field(default=5.0, gt=0, le=3600)
    toxic_flow_adverse_markout_bps: Decimal = Decimal("3")
    toxic_flow_spread_strength: Decimal = Decimal("0.50")
    toxic_flow_size_strength: Decimal = Decimal("0.60")

    execution_quality_window: int = Field(default=50, ge=1, le=1000)
    execution_quality_min_fills: int = Field(default=5, ge=1, le=1000)
    execution_quality_poor_markout_bps: Decimal = Decimal("3")
    execution_quality_max_churn_ratio: Decimal = Decimal("0.65")
    execution_quality_spread_strength: Decimal = Decimal("0.40")
    execution_quality_size_strength: Decimal = Decimal("0.40")

    @model_validator(mode="after")
    def validate_agent_config(self):
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
