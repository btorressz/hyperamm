from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel,ConfigDict,Field,model_validator
from app.accounting.config import AccountingConfig


class FillModel(StrEnum):
    CROSSING_ONLY="CROSSING_ONLY"


class SimulationConfig(BaseModel):
    model_config=ConfigDict(extra="forbid")
    initial_equity_quote:Decimal=Field(default=Decimal("100000"),gt=0)
    max_frames:int=Field(default=250,ge=2,le=5000)
    record_trace:bool=True
    trace_max_points:int=Field(default=500,ge=0,le=5000)
    fill_model:FillModel=FillModel.CROSSING_ONLY
    accounting:AccountingConfig=Field(default_factory=AccountingConfig)

    @model_validator(mode="after")
    def validate_values(self):
        if not self.initial_equity_quote.is_finite():
            raise ValueError("initial_equity_quote must be finite")
        return self


class OptimizationObjectiveConfig(BaseModel):
    model_config=ConfigDict(extra="forbid")
    drawdown_weight:Decimal=Decimal("1")
    inventory_weight:Decimal=Decimal("0.25")
    adverse_markout_weight:Decimal=Decimal("1")
    churn_weight:Decimal=Decimal("0.25")
    halt_weight:Decimal=Decimal("1")

    @model_validator(mode="after")
    def validate_weights(self):
        for name in (
            "drawdown_weight","inventory_weight","adverse_markout_weight","churn_weight","halt_weight"
        ):
            value=getattr(self,name)
            if not value.is_finite() or value<0:
                raise ValueError(f"{name} must be finite and non-negative")
        return self
