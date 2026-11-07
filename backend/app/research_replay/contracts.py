"""Immutable Phase 16.2 requests and receipts; no historical-value imputation."""
from __future__ import annotations

import json
from typing import Literal
from decimal import Decimal

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, field_validator, model_serializer, model_validator

from app.market_data.live_models import Evidence, FinancialDecimal
from app.execution.research import PaperExecutionAssumptions
from app.simulation.market_profiles import ResearchPerpMarketId
from app.simulation.models import SimulationResult, stable_fingerprint
from app.simulation.research_vault import ResearchVaultConfig
from .models import Fingerprint, HistoricalGap, HistoricalObservation, Identifier
from .provenance import HistoricalDatasetProvenance

REPLAY_VERSION = "phase162-v1"
MAX_SEGMENTS = 32


class ReplayPolicy(Evidence):
    """Explicit temporal modeling, independently fingerprinted from evidence."""

    pairing: Literal["RECEIPT_BATCH_LAST_COMPONENT"] = "RECEIPT_BATCH_LAST_COMPONENT"
    max_component_age_ms: StrictInt = Field(default=0, ge=0, le=30000)
    max_frame_interval_ms: StrictInt = Field(default=1000, ge=1, le=60000)
    missing_economics: Literal["REJECT_FRAME"] = "REJECT_FRAME"
    discontinuity: Literal["RESET_ALL_SIMULATION_STATE"] = "RESET_ALL_SIMULATION_STATE"


class ReplayExecutionAssumptions(Evidence):
    # Historical contracts contain no execution precision or venue metadata.
    size_decimals: StrictInt = Field(ge=0, le=6)
    metadata: Literal["USER_ASSERTED_RESEARCH_PRECISION"] = "USER_ASSERTED_RESEARCH_PRECISION"
    strategy_scaling: Literal["EXISTING_DEMO_MARKET_PROFILE"] = "EXISTING_DEMO_MARKET_PROFILE"
    fill_model: Literal["PAPER_CROSSING_ONLY"] = "PAPER_CROSSING_ONLY"
    external_references: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    paper: PaperExecutionAssumptions = Field(default_factory=PaperExecutionAssumptions)
    accounting: ResearchVaultConfig = Field(default_factory=ResearchVaultConfig)

    @model_serializer(mode="wrap")
    def retain_legacy_shape(self, handler):
        values = handler(self)
        if "paper" not in self.model_fields_set and not self.paper.modeled:
            values.pop("paper", None)
        return values

    @field_validator("accounting", mode="before")
    @classmethod
    def exact_accounting(cls, value):
        if isinstance(value, dict):
            for name in ("initial_equity_quote", "paper_maker_fee_bps", "paper_taker_fee_bps", "max_capital_utilization"):
                if name in value:
                    PaperExecutionAssumptions.exact_decimal(value[name])
        return value


class HistoricalReplayRequest(Evidence):
    replay_version: Literal["phase162-v1"] = REPLAY_VERSION
    dataset_id: Identifier
    dataset_fingerprint: Fingerprint
    market: ResearchPerpMarketId
    execution: ReplayExecutionAssumptions
    policy: ReplayPolicy = Field(default_factory=ReplayPolicy)
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    max_frames: StrictInt = Field(default=250, ge=2, le=5000)
    record_trace: StrictBool = True
    trace_max_points: StrictInt = Field(default=500, ge=0, le=5000)

    @model_validator(mode="after")
    def ordered_window(self):
        if self.start_at is not None and self.end_at is not None and self.start_at > self.end_at:
            raise ValueError("replay receipt window is reversed")
        return self


MissingField = Literal["order_book", "perp_context", "mark_price", "oracle_price",
                       "funding_rate", "open_interest_base", "positive_l2_sizes"]


class ReplayIssue(Evidence):
    code: Literal["INCOMPLETE_FRAME", "COMPONENT_TOO_OLD", "SHORT_SEGMENT",
                  "NO_VIABLE_FRAMES", "FRAME_LIMIT", "SEGMENT_LIMIT", "IDENTITY_MISMATCH"]
    sequence: StrictInt | None = None
    received_at: AwareDatetime | None = None
    missing_fields: tuple[MissingField, ...] = ()
    frame_count: StrictInt | None = Field(default=None, ge=0)


class ReplayRejection(Evidence):
    status: Literal["REJECTED"] = "REJECTED"
    request_fingerprint: Fingerprint
    dataset_fingerprint: Fingerprint
    issues: tuple[ReplayIssue, ...]


class ReplayRejected(ValueError):
    def __init__(self, rejection: ReplayRejection):
        super().__init__("historical replay rejected")
        self.rejection = rejection


class ReplayFrameEvidence(Evidence):
    sequence: StrictInt
    evaluated_at: AwareDatetime
    receipt_batch_sequences: tuple[StrictInt, ...]
    book_observation: HistoricalObservation
    context_observation: HistoricalObservation
    economics: Literal["RECORDED_VALUES", "SYNTHETIC_FIXTURE_VALUES"]
    derived_fields: tuple[str, ...] = (
        "BBO midpoint", "basis ratios", "open interest notional",
        "simulation evaluation time (not context source time)",
    )


class ReplaySegmentResult(Evidence):
    segment_index: StrictInt
    reset_reason: Literal["WINDOW_START", "DECLARED_GAP", "OBSERVER_CHANGE",
                          "RECEIPT_INTERVAL", "UNAVAILABLE_FRAME"]
    dataset_fingerprint: Fingerprint
    run_fingerprint: Fingerprint
    frames: tuple[ReplayFrameEvidence, ...]
    frame_count: StrictInt
    starting_equity: FinancialDecimal
    ending_equity: FinancialDecimal
    session_pnl: FinancialDecimal
    fill_count: StrictInt
    simulation_result_fingerprint: Fingerprint
    # A canonical JSON archive preserves the existing engine's complete output
    # without embedding mutable SimulationResult/list/dict objects in a receipt.
    simulation_result_json: str = Field(max_length=16_000_000)
    baseline_result_json: str | None = Field(default=None, max_length=16_000_000)
    baseline_result_fingerprint: Fingerprint | None = None
    session_pnl_delta: FinancialDecimal | None = None
    fill_count_delta: StrictInt | None = None

    @model_serializer(mode="wrap")
    def retain_legacy_shape(self, handler):
        values = handler(self)
        for name in ("baseline_result_json", "baseline_result_fingerprint", "session_pnl_delta", "fill_count_delta"):
            if name not in self.model_fields_set and getattr(self, name) is None:
                values.pop(name, None)
        return values

    @model_validator(mode="after")
    def archive_identity(self):
        if stable_fingerprint(json.loads(self.simulation_result_json)) != self.simulation_result_fingerprint:
            raise ValueError("simulation result archive fingerprint mismatch")
        modeled = SimulationResult.model_validate_json(self.simulation_result_json)
        self._check_archive(modeled)
        if (modeled.run_fingerprint != self.run_fingerprint
                or modeled.metrics.fill_count != self.fill_count
                or any(getattr(modeled.metrics, name) != getattr(self, name)
                       for name in ("starting_equity", "ending_equity", "session_pnl"))):
            raise ValueError("segment simulation identity or metrics mismatch")
        comparison = (self.baseline_result_json, self.baseline_result_fingerprint,
                      self.session_pnl_delta, self.fill_count_delta)
        if any(x is not None for x in comparison):
            if any(x is None for x in comparison):
                raise ValueError("incomplete baseline comparison")
            baseline = json.loads(self.baseline_result_json)
            if stable_fingerprint(baseline) != self.baseline_result_fingerprint:
                raise ValueError("baseline archive fingerprint mismatch")
            parsed_baseline = SimulationResult.model_validate_json(self.baseline_result_json)
            self._check_archive(parsed_baseline)
            if (parsed_baseline.strategy_fingerprint != modeled.strategy_fingerprint
                    or parsed_baseline.engine_version != modeled.engine_version
                    or parsed_baseline.run_fingerprint == modeled.run_fingerprint
                    or (parsed_baseline.execution_assumptions or {}).get("mode") == "MODELED_CROSSING"):
                raise ValueError("baseline comparison inputs differ")
            if (self.session_pnl_delta != self.session_pnl - Decimal(baseline["metrics"]["session_pnl"])
                    or self.fill_count_delta != self.fill_count - baseline["metrics"]["fill_count"]):
                raise ValueError("baseline comparison delta mismatch")
        return self

    def _check_archive(self, archive):
        # Source dataset identity and engine segment identity are intentionally
        # different. Bind only to this segment, using existing result contracts.
        if (not archive.simulated or archive.scenario != "historical-replay"
                or archive.dataset_fingerprint != self.dataset_fingerprint
                or archive.metrics.frame_count != self.frame_count
                or len(self.frames) != self.frame_count):
            raise ValueError("archive does not belong to replay segment")
        frames = {f.sequence: f.evaluated_at for f in self.frames}
        previous = -1
        for point in archive.trace:
            if point.sequence <= previous or frames.get(point.sequence) != point.timestamp:
                raise ValueError("archive trace does not belong to replay segment")
            previous = point.sequence


class HistoricalReplayResult(Evidence):
    replay_version: Literal["phase162-v1"] = REPLAY_VERSION
    status: Literal["COMPLETED_PARTIAL"] = "COMPLETED_PARTIAL"
    simulated: Literal[True] = True
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"
    request: HistoricalReplayRequest
    request_fingerprint: Fingerprint
    modeling_fingerprint: Fingerprint
    execution_assumptions_fingerprint: Fingerprint | None = None
    provenance: HistoricalDatasetProvenance
    declared_gaps: tuple[HistoricalGap, ...]
    examined_observation_count: StrictInt
    frame_count: StrictInt
    issues: tuple[ReplayIssue, ...]
    segments: tuple[ReplaySegmentResult, ...]
    captured_configuration_json: str
    captured_configuration_fingerprint: Fingerprint
    result_fingerprint: Fingerprint
    limitations: tuple[str, ...] = (
        "Receipt batches preserve sequence order; source times never order the replay.",
        "Context evaluation timestamps are simulation clocks, not exchange event times.",
        "Temporal pairing and execution/accounting assumptions are separately fingerprinted modeling inputs.",
        "Missing economics and L2 are never imputed; unavailable frames and short segments are excluded explicitly.",
        "Each segment starts with fresh PAPER orders, inventory, history, risk and accounting; no combined return is claimed.",
        "Recorded labels are user assertions; snapshots never establish continuous coverage, queue position or actual passive fills.",
        "Crossing-only baseline and optional bounded execution sensitivities produce hypothetical PAPER fills; no real passive fills are claimed.",
        "External provider references remain unavailable; existing risk authorization can suppress all quotes.",
        "Virtual reserves and size scaling use the existing fixed demo market profile, not historical venue metadata.",
    )

    @model_serializer(mode="wrap")
    def retain_legacy_shape(self, handler):
        values = handler(self)
        if "execution_assumptions_fingerprint" not in self.model_fields_set and self.execution_assumptions_fingerprint is None:
            values.pop("execution_assumptions_fingerprint", None)
        return values

    @model_validator(mode="after")
    def receipt_identity(self):
        if (self.execution_assumptions_fingerprint is not None
                and self.execution_assumptions_fingerprint != self.request.execution.paper.fingerprint):
            raise ValueError("execution assumptions fingerprint mismatch")
        if self.request_fingerprint != stable_fingerprint(self.request):
            raise ValueError("replay request fingerprint mismatch")
        if self.modeling_fingerprint != stable_fingerprint((self.request.policy, self.request.execution)):
            raise ValueError("replay modeling fingerprint mismatch")
        if stable_fingerprint(json.loads(self.captured_configuration_json)) != self.captured_configuration_fingerprint:
            raise ValueError("captured configuration fingerprint mismatch")
        if self.result_fingerprint != stable_fingerprint(self.model_dump(exclude={"result_fingerprint"})):
            raise ValueError("replay result fingerprint mismatch")
        return self
