"""Narrow, stateless PAPER research assumptions; no runtime authority references."""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from app.accounting.config import AccountingConfig
from .config import SimulationConfig
from .models import SimulationResult, stable_fingerprint

RESEARCH_CONFIG_VERSION = "phase14-v1"
LIMITATIONS = (
    "Hypothetical PAPER accounting assumptions; no live trading authority or runtime mutation.",
    "Preview is validation and configuration arithmetic, not trades or a PnL forecast.",
    "Utilization ceiling is a hypothetical full-notional limit, not venue margin or guaranteed allocation.",
    "Funding uses scenario rates per sampled research interval, not venue payments or predicted income.",
    "Fingerprints identify canonical in-memory research inputs, not blockchain proofs or durable records.",
)


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return (text.rstrip("0").rstrip(".") if "." in text else text) if value else "0"


def accounting_field(name: str):
    """Reuse the accounting domain's type and financial bounds."""
    field = AccountingConfig.model_fields[name]
    return Annotated[field.annotation, *field.metadata]


class ResearchVaultConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    initial_equity_quote: accounting_field("paper_initial_equity_quote") = Decimal("100000")
    paper_fee_model_enabled: StrictBool = False
    paper_maker_fee_bps: accounting_field("paper_maker_fee_bps") = Decimal("1")
    paper_taker_fee_bps: accounting_field("paper_taker_fee_bps") = Decimal("3")
    paper_funding_accounting_enabled: StrictBool = False
    paper_funding_interval_seconds: Literal[1, 60, 300, 3600, 28800, 86400] = 3600
    max_capital_utilization: accounting_field("max_capital_utilization") = Decimal("1")

    @field_validator("initial_equity_quote", "paper_maker_fee_bps", "paper_taker_fee_bps", "max_capital_utilization", mode="before")
    @classmethod
    def bounded_decimal_input(cls, value):
        if isinstance(value, bool) or isinstance(value, (dict, list)):
            raise ValueError("expected a finite Decimal value")
        if len(str(value)) > 80:
            raise ValueError("Decimal input exceeds 80 characters")
        return value

    @field_validator("paper_funding_interval_seconds", mode="before")
    @classmethod
    def whole_interval(cls, value):
        if type(value) is not int:
            raise ValueError("funding interval must be an integer number of seconds")
        return value

    @model_validator(mode="after")
    def research_bounds(self):
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, Decimal):
                if not value.is_finite() or value.as_tuple().exponent < -18:
                    raise ValueError(f"{name} must be finite with at most 18 fractional places")
        if self.initial_equity_quote > Decimal("1000000000000"):
            raise ValueError("starting capital exceeds research bound 1000000000000")
        if max(self.paper_maker_fee_bps, self.paper_taker_fee_bps) > 100:
            raise ValueError("research fee rates must not exceed 100 bps")
        return self

    def canonical(self) -> dict:
        payload = self.model_dump()
        for key, value in payload.items():
            if isinstance(value, Decimal):
                payload[key] = decimal_text(value)
        return payload

    def fingerprint(self) -> str:
        return stable_fingerprint({"research_config_version": RESEARCH_CONFIG_VERSION, "config": self.canonical()})

    def to_simulation(self, controls: SimulationConfig | None = None) -> SimulationConfig:
        controls = controls or SimulationConfig()
        # Administrative fields always come from code-owned accounting defaults.
        payload = self.model_dump(exclude={"initial_equity_quote"})
        accounting = AccountingConfig(**payload, paper_initial_equity_quote=self.initial_equity_quote)
        return SimulationConfig(initial_equity_quote=self.initial_equity_quote,
            max_frames=controls.max_frames, record_trace=controls.record_trace,
            trace_max_points=controls.trace_max_points, accounting=accounting)


class ResearchProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: ResearchVaultConfig
    selected_preset_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def known_preset(self):
        from .presets import get_preset
        if self.selected_preset_id is not None:
            get_preset(self.selected_preset_id)
        return self

    def provenance(self) -> dict:
        from .presets import get_preset
        preset = get_preset(self.selected_preset_id) if self.selected_preset_id else None
        return {"research_config_version": RESEARCH_CONFIG_VERSION,
                "selected_preset_id": self.selected_preset_id,
                "selected_preset_version": preset.version if preset else None,
                "normalized_config": self.config.canonical(),
                "config_fingerprint": self.config.fingerprint(),
                "customized": preset is None or preset.config != self.config}


UNITS = {"initial_equity_quote": "quote", "paper_maker_fee_bps": "bps", "paper_taker_fee_bps": "bps",
         "paper_funding_interval_seconds": "seconds", "max_capital_utilization": "fraction"}


def config_differences(baseline: ResearchVaultConfig, custom: ResearchVaultConfig) -> list[dict]:
    old, new = baseline.canonical(), custom.canonical()
    with localcontext() as ctx:
        ctx.prec = 80
        return [{"field": key, "old_value": old[key], "new_value": new[key],
                 "difference": (str(Decimal(str(new[key])) - Decimal(str(old[key])))
                                if key in UNITS else None), "units": UNITS.get(key, "boolean")}
                for key in old if old[key] != new[key]]


def preview(proposal: ResearchProposal) -> dict:
    from .presets import get_preset
    baseline = get_preset(proposal.selected_preset_id or "balanced-research").config
    with localcontext() as ctx:
        ctx.prec = 80
        ceiling = proposal.config.initial_equity_quote * proposal.config.max_capital_utilization
    return {**proposal.provenance(), "validation_status": "VALID", "simulated": True,
            "changed_fields": config_differences(baseline, proposal.config),
            "baseline_values": baseline.canonical(), "custom_values": proposal.config.canonical(),
            "baseline_preset_id": proposal.selected_preset_id or "balanced-research",
            "illustrative_utilization_ceiling_quote": decimal_text(ceiling),
            "warnings": ["Funding enabled does not guarantee a funding event within the selected dataset."]
                        if proposal.config.paper_funding_accounting_enabled else [],
            "limitations": list(LIMITATIONS)}


class ResearchComparisonResult(BaseModel):
    research_config_version: str = RESEARCH_CONFIG_VERSION
    baseline_config_fingerprint: str
    custom_config_fingerprint: str
    baseline_provenance: dict
    custom_provenance: dict
    scenario: str
    frame_count: int
    baseline_result: SimulationResult
    custom_result: SimulationResult
    comparison_deltas: dict[str, Decimal | int | None]
    risk_state_counts: dict[str, dict[str, int]]
    limitations: list[str]
    simulated: bool = True


def result_deltas(baseline: SimulationResult, custom: SimulationResult) -> dict:
    with localcontext() as ctx:
        ctx.prec = 80
        result = {name: getattr(custom.metrics, name) - getattr(baseline.metrics, name)
                  for name in ("starting_equity", "ending_equity", "session_pnl", "return_pct",
                               "max_drawdown_pct", "fill_count", "max_inventory_utilization", "risk_halt_fraction")}
        for name in ("fees_quote", "funding_quote", "capital_utilization"):
            old = getattr(baseline.vault, name, None)
            new = getattr(custom.vault, name, None)
            result[name] = new - old if old is not None and new is not None else None
        return result
