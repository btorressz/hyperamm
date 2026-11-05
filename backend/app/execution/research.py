"""Bounded user assumptions for hypothetical PAPER execution, never venue facts."""
from decimal import Decimal
import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_serializer, field_validator, model_validator


class PaperExecutionAssumptions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    version: Literal["phase163-v1"] = "phase163-v1"
    mode: Literal["BASELINE", "MODELED_CROSSING"] = "BASELINE"
    order_latency_ms: StrictInt = Field(default=0, ge=0, le=60000)
    cancel_latency_ms: StrictInt = Field(default=0, ge=0, le=60000)
    slippage_bps: Decimal = Field(default=Decimal(0), ge=0, le=1000)
    depth_sensitive: StrictBool = False
    allow_partial_fills: StrictBool = True
    participation_rate: Decimal = Field(default=Decimal(1), ge=0, le=1)
    max_fill_fraction: Decimal = Field(default=Decimal(1), ge=0, le=1)

    @field_validator("slippage_bps", "participation_rate", "max_fill_fraction", mode="before")
    @classmethod
    def exact_decimal(cls, value):
        if isinstance(value, str):
            if len(value) > 40 or not re.fullmatch(r"\d+(?:\.\d+)?", value):
                raise ValueError("bounded decimal string required")
            value = Decimal(value)
        elif type(value) is int:
            value = Decimal(value)
        if not isinstance(value, Decimal) or not value.is_finite() or value.as_tuple().exponent < -18:
            raise ValueError("finite exact Decimal with at most 18 fractional places required")
        if not -18 <= value.as_tuple().exponent <= 30 or value.copy_abs() > Decimal("1e30"):
            raise ValueError("Decimal outside research input bounds")
        return value.normalize() if value else Decimal(0)

    @field_serializer("slippage_bps", "participation_rate", "max_fill_fraction", when_used="json")
    def decimal_json(self, value):
        return format(value, "f")

    @model_validator(mode="after")
    def baseline_controls(self):
        if self.mode == "BASELINE" and (self.order_latency_ms or self.cancel_latency_ms or self.slippage_bps
                or self.depth_sensitive or not self.allow_partial_fills
                or self.participation_rate != 1 or self.max_fill_fraction != 1):
            raise ValueError("model controls require MODELED_CROSSING")
        return self

    @property
    def modeled(self):
        return self.mode == "MODELED_CROSSING"

    @property
    def fingerprint(self):
        # Decimal spelling is semantic: 0.10 and 0.1 have the same identity.
        values = self.model_dump(mode="json")
        for name in ("slippage_bps", "participation_rate", "max_fill_fraction"):
            values[name] = format(getattr(self, name).normalize(), "f")
        return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


MODEL_LIMITATIONS = (
    "Execution controls are user-provided research assumptions; fills are hypothetical PAPER outputs.",
    "Submission order allocates shared snapshot depth deterministically; this is not venue queue evidence.",
    "Only crossing orders are eligible; no queue position, unobserved trades or real passive fills are inferred.",
    "Latency uses receipt-clock eligibility at the next available observation, never interpolated market evidence.",
    "Cancellation wins an equal-time race; pending cancellation remains exposed until its modeled deadline.",
    "Modeled fills consume observed L2 once per book observation, with no hidden or replenished liquidity.",
    "Depth disabled uses only observed BBO size; depth enabled walks retained levels, never beyond limit price.",
    "Sampled funding and configured fees are assumptions, not historical venue charges or settlement evidence.",
)
