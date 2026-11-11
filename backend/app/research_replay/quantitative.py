"""Phase 16.5B — provenance-gated, descriptive PAPER metric extraction.

This module never runs a simulation, joins historical segments, calculates
cross-source financial deltas, scores strategies, or authorizes execution.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, StrictInt, field_validator, model_validator

from app.market_data.live_models import Evidence
from app.research_replay.comparison import (
    CapturedScenarioResult, ComparisonFoundation, capture_comparison_foundation,
)
from app.research_replay.contracts import HistoricalReplayResult
from app.research_replay.models import Fingerprint
from app.simulation.models import SimulationResult, stable_fingerprint

VERSION = "phase165b-v1"
MetricName = Literal[
    "frame_count", "starting_equity", "ending_equity", "session_pnl",
    "return_pct", "realized_pnl", "unrealized_pnl", "max_drawdown_pct",
    "fill_count", "buy_fill_count", "sell_fill_count",
    "quoted_notional", "filled_notional", "fill_activity_ratio",
    "ending_inventory_base", "max_abs_inventory_base",
    "max_inventory_utilization", "risk_halt_fraction",
    "fees_quote", "funding_quote", "capital_utilization",
    "reserved_capital_quote", "gross_exposure_quote",
]
MetricUnit = Literal["frames", "quote", "percent", "fills", "base", "ratio"]
MetricOrigin = Literal["SIMULATION_METRICS", "PAPER_VAULT"]
Availability = Literal["AVAILABLE", "NOT_REPORTED"]
DisplayPolicy = Literal["DESCRIPTIVE_ONLY", "BLOCKED"]

# (Existing field, unit, source). Never derive a metric from another metric.
# In particular, inventory utilization is NOT capital utilization.
METRICS: tuple[tuple[MetricName, MetricUnit, MetricOrigin], ...] = (
    ("frame_count", "frames", "SIMULATION_METRICS"),
    ("starting_equity", "quote", "SIMULATION_METRICS"),
    ("ending_equity", "quote", "SIMULATION_METRICS"),
    ("session_pnl", "quote", "SIMULATION_METRICS"),
    ("return_pct", "percent", "SIMULATION_METRICS"),
    ("realized_pnl", "quote", "SIMULATION_METRICS"),
    ("unrealized_pnl", "quote", "SIMULATION_METRICS"),
    ("max_drawdown_pct", "percent", "SIMULATION_METRICS"),
    ("fill_count", "fills", "SIMULATION_METRICS"),
    ("buy_fill_count", "fills", "SIMULATION_METRICS"),
    ("sell_fill_count", "fills", "SIMULATION_METRICS"),
    ("quoted_notional", "quote", "SIMULATION_METRICS"),
    ("filled_notional", "quote", "SIMULATION_METRICS"),
    ("fill_activity_ratio", "ratio", "SIMULATION_METRICS"),
    ("ending_inventory_base", "base", "SIMULATION_METRICS"),
    ("max_abs_inventory_base", "base", "SIMULATION_METRICS"),
    ("max_inventory_utilization", "ratio", "SIMULATION_METRICS"),
    ("risk_halt_fraction", "ratio", "SIMULATION_METRICS"),
    ("fees_quote", "quote", "PAPER_VAULT"),
    ("funding_quote", "quote", "PAPER_VAULT"),
    ("capital_utilization", "ratio", "PAPER_VAULT"),
    ("reserved_capital_quote", "quote", "PAPER_VAULT"),
    ("gross_exposure_quote", "quote", "PAPER_VAULT"),
)
_SPEC = {name: (unit, source) for name, unit, source in METRICS}
_COUNT_NAMES = frozenset({"frame_count", "fill_count", "buy_fill_count", "sell_fill_count"})
LIMITATIONS = (
    "Metrics are existing backend PAPER outputs, not a matched experimental performance comparison.",
    "Displayed scenario and historical segment values must never be subtracted, ranked, annualized or pooled.",
    "Historical receipt gaps reset capital, risk, orders and inventory; no multi-segment PnL or return is defined.",
    "Simulation frame count is not wall-clock duration, trading volume or proof of equivalent source coverage.",
    "Capital utilization is sourced only from the PAPER Vault, not inferred from inventory exposure.",
    "A missing backend value remains unavailable, never imputed as zero.",
    "Source labels and scenario service receipts do not prove exchange authenticity, licensed history or real fills.",
)


class MetricObservation(Evidence):
    """An exact value directly copied from the current engine result or Vault."""
    origin: MetricOrigin
    availability: Availability
    value: Decimal | None = None

    @field_validator("value", mode="before")
    @classmethod
    def no_float_or_nonfinite(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("floating-point or boolean financial evidence is forbidden")
        if isinstance(value, str) and len(value) > 120:
            raise ValueError("metric decimal exceeds wire bound")
        return value

    @model_validator(mode="after")
    def consistent_availability(self):
        if (self.availability == "AVAILABLE") != (self.value is not None):
            raise ValueError("metric availability and value disagree")
        if self.value is not None and not self.value.is_finite():
            raise ValueError("non-finite metric value")
        if self.value is not None and (len(str(self.value)) > 120 or
                not -999 <= self.value.as_tuple().exponent <= 999):
            raise ValueError("metric decimal exceeds wire bound")
        return self


class MetricRow(Evidence):
    name: MetricName
    unit: MetricUnit
    scenario: MetricObservation
    historical_segment: MetricObservation

    @model_validator(mode="after")
    def exact_source(self):
        unit, origin = _SPEC[self.name]
        if self.unit != unit or self.scenario.origin != origin or self.historical_segment.origin != origin:
            raise ValueError("metric unit/source does not match existing backend field")
        if self.name in _COUNT_NAMES:
            for observed in (self.scenario, self.historical_segment):
                if observed.value is not None and (observed.value < 0 or
                        observed.value != observed.value.to_integral_value()):
                    raise ValueError("count metric must be a non-negative integer")
        return self


class RiskStateEvidence(Evidence):
    """Original per-run counts, without cross-run subtraction or aggregation."""
    scenario: dict[str, StrictInt]
    historical_segment: dict[str, StrictInt]

    @model_validator(mode="after")
    def bounded_counts(self):
        for counts in (self.scenario, self.historical_segment):
            if len(counts) > 20 or any(not name or len(name) > 80 or count < 0
                                      for name, count in counts.items()):
                raise ValueError("invalid risk-state counts")
        return self


class QuantitativeComparison(Evidence):
    """One selected replay segment, never a replay-wide financial calculation."""
    version: Literal["phase165b-v1"] = VERSION
    foundation: ComparisonFoundation
    scenario_receipt_fingerprint: Fingerprint
    selected_segment_index: StrictInt = Field(ge=0, le=31)
    display_policy: DisplayPolicy
    rows: tuple[MetricRow, ...] = Field(max_length=len(METRICS))
    risk_states: RiskStateEvidence | None = None
    differences_available: Literal[False] = False
    cross_segment_aggregation_allowed: Literal[False] = False
    strategy_ranking_allowed: Literal[False] = False
    matched_market_evidence_verified: Literal[False] = False
    authority: Literal["NONE"] = "NONE"
    read_only: Literal[True] = True
    limitations: tuple[str, ...] = LIMITATIONS
    receipt_fingerprint: Fingerprint

    @model_validator(mode="after")
    def evidence_integrity(self):
        if self.selected_segment_index != self.foundation.historical.segment_index:
            raise ValueError("quantitative receipt selected the wrong replay segment")
        if self.foundation.classification == "CONTEXT_ONLY":
            if (self.display_policy != "DESCRIPTIVE_ONLY" or
                tuple(row.name for row in self.rows) != tuple(spec[0] for spec in METRICS) or
                self.risk_states is None):
                raise ValueError("contextual metrics must include exact known fields and risk counts")
            for name, counts in (
                ("scenario", self.risk_states.scenario),
                ("historical_segment", self.risk_states.historical_segment),
            ):
                count = next(row for row in self.rows if row.name == "frame_count")
                value = getattr(count, name).value
                side = self.foundation.scenario if name == "scenario" else self.foundation.historical
                if value != side.frame_count or sum(counts.values()) != int(value):
                    raise ValueError("risk-state counts do not cover the engine frames")
        elif (self.display_policy != "BLOCKED" or self.rows or self.risk_states is not None):
            raise ValueError("incomparable sources must not emit paired financial metrics")
        if self.foundation.classification == "ALIGNED":
            raise ValueError("Phase 16.5B cannot emit aligned evidence")
        if self.limitations != LIMITATIONS:
            raise ValueError("comparison limitations were altered")
        if self.receipt_fingerprint != stable_fingerprint(
            self.model_dump(exclude={"receipt_fingerprint"})
        ):
            raise ValueError("quantitative receipt fingerprint mismatch")
        return self


def _observation(result: SimulationResult, name: MetricName,
                 origin: MetricOrigin) -> MetricObservation:
    # Values must come from existing authoritative backend output; never
    # derive hypothetical capital utilization from inventory, PnL or equity.
    owner = result.metrics if origin == "SIMULATION_METRICS" else result.vault
    if owner is not None and origin == "PAPER_VAULT" and (
        owner.mode != "PAPER" or owner.simulated is not True
    ):
        raise ValueError("only simulated PAPER Vault evidence may be compared")
    value = getattr(owner, name, None) if owner is not None else None
    if value is not None and not isinstance(value, (int, Decimal)):
        raise ValueError("backend metric is not an exact Decimal or integer")
    return MetricObservation(
        origin=origin,
        availability="AVAILABLE" if value is not None else "NOT_REPORTED",
        value=value,
    )


def _risk_counts(result: SimulationResult) -> dict[str, int]:
    # Retain actual risk-state labels. The engine reports one state per frame;
    # do not infer or generate a missing risk sequence.
    return dict(sorted(result.metrics.risk_state_counts.items()))


def compare_quantitative_paper(
    *, scenario: CapturedScenarioResult,
    historical: HistoricalReplayResult,
    segment_index: int,
) -> QuantitativeComparison:
    """Validate both actual source receipts and project existing per-side metrics.

    This function has no worker, API side effects, scenario generator, engine,
    performance scoring or financial delta math. It requires the A.2 bound
    scenario receipt: a bare caller-supplied scenario is not sufficient.
    """
    scenario = CapturedScenarioResult.model_validate_json(scenario.model_dump_json())
    historical = HistoricalReplayResult.model_validate_json(historical.model_dump_json())
    foundation = capture_comparison_foundation(
        scenario=scenario.result, scenario_provenance=scenario.provenance,
        historical=historical, segment_index=segment_index,
    )
    if foundation.classification == "CONTEXT_ONLY":
        segment = historical.segments[segment_index]
        replay_result = SimulationResult.model_validate_json(segment.simulation_result_json)
        # Already verified by HistoricalReplayResult; assert the exact selected
        # run is being displayed rather than any other segment or baseline.
        if (replay_result.run_fingerprint != foundation.historical.run_fingerprint
                or replay_result.dataset_fingerprint != foundation.historical.engine_dataset_fingerprint
                or stable_fingerprint(replay_result.model_dump(mode="json"))
                != foundation.historical.simulation_result_fingerprint):
            raise ValueError("selected replay archive identity mismatch")
        rows = tuple(MetricRow(
            name=name, unit=unit,
            scenario=_observation(scenario.result, name, origin),
            historical_segment=_observation(replay_result, name, origin),
        ) for name, unit, origin in METRICS)
        risk_states = RiskStateEvidence(
            scenario=_risk_counts(scenario.result),
            historical_segment=_risk_counts(replay_result),
        )
        policy: DisplayPolicy = "DESCRIPTIVE_ONLY"
    else:
        rows = ()
        risk_states = None
        policy = "BLOCKED"
    values = dict(
        foundation=foundation, scenario_receipt_fingerprint=scenario.provenance.receipt_fingerprint,
        selected_segment_index=segment_index, display_policy=policy,
        rows=rows, risk_states=risk_states,
    )
    defaults = {key: field.default for key, field in QuantitativeComparison.model_fields.items()
                if key not in values and key != "receipt_fingerprint" and not field.is_required()}
    return QuantitativeComparison(
        **values, receipt_fingerprint=stable_fingerprint({**defaults, **values})
    )
