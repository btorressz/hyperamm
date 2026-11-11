"""Bounded same-worker comparison transport, never client-supplied result evidence."""
from typing import Literal

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, field_validator, model_serializer, model_validator

from app.market_data.live_models import Evidence
from app.research_replay.contracts import HistoricalReplayRequest, ReplayIssue
from app.research_replay.models import Fingerprint, HistoricalGap
from app.research_replay.provenance import HistoricalDatasetProvenance
from app.research_replay.quantitative import QuantitativeComparison
from app.simulation.config import SimulationConfig
from app.simulation.market_profiles import ResearchPerpMarketId
from app.simulation.models import SimulationTracePoint
from app.simulation.research_vault import ResearchProposal
from app.simulation.scenarios import ScenarioName

MAX_RESPONSE_BYTES = 1_000_000
MAX_TRACE_POINTS = 250


class ScenarioHistoricalRequest(Evidence):
    scenario: ScenarioName = ScenarioName.QUIET
    frames: StrictInt = Field(default=120, ge=2, le=5000)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    research: ResearchProposal | None = None
    research_market: ResearchPerpMarketId
    historical: HistoricalReplayRequest
    segment_index: StrictInt = Field(default=0, ge=0, le=31)
    include_traces: StrictBool = True
    trace_point_limit: StrictInt = Field(default=120, ge=0, le=MAX_TRACE_POINTS)

    @model_serializer(mode="wrap")
    def preserve_research_controls(self, handler):
        values = handler(self)
        if self.research is not None:
            # Capital/accounting defaults must not become explicit conflicting
            # overrides when the admitted request is revalidated or transported.
            values["simulation"] = self.simulation.model_dump(mode="json", exclude_unset=True)
        return values

    @field_validator("simulation", mode="before")
    @classmethod
    def strict_simulation(cls, value):
        import json
        from app.accounting.config import AccountingConfig
        from app.execution.research import PaperExecutionAssumptions
        if isinstance(value, SimulationConfig):
            value = value.model_dump(mode="json")
        if isinstance(value, dict):
            for key, model in (("accounting", AccountingConfig), ("execution", PaperExecutionAssumptions)):
                nested = value.get(key, {})
                if not isinstance(nested, dict) or set(nested) - set(model.model_fields):
                    raise ValueError("unexpected simulation assumptions")
        return SimulationConfig.model_validate_json(json.dumps(value), strict=True)

    @model_validator(mode="after")
    def research_controls(self):
        from app.api.simulation import validate_research_controls
        validate_research_controls(self)
        if self.frames > self.simulation.max_frames:
            raise ValueError("scenario frames exceed simulation max_frames")
        return self


class SegmentIdentity(Evidence):
    segment_index: StrictInt = Field(ge=0, le=31)
    reset_reason: Literal["WINDOW_START", "DECLARED_GAP", "OBSERVER_CHANGE", "RECEIPT_INTERVAL", "UNAVAILABLE_FRAME"]
    frame_count: StrictInt = Field(ge=2, le=5000)
    window_start: AwareDatetime
    window_end: AwareDatetime
    dataset_fingerprint: Fingerprint
    run_fingerprint: Fingerprint
    simulation_result_fingerprint: Fingerprint


class TraceSourceTime(Evidence):
    sequence: StrictInt
    book_received_at: AwareDatetime
    book_source_timestamp: AwareDatetime | None
    book_source_event_time_verified: StrictBool
    context_received_at: AwareDatetime
    context_source_timestamp: AwareDatetime | None
    context_source_event_time_verified: StrictBool


class ComparisonTrace(Evidence):
    run_fingerprint: Fingerprint
    dataset_fingerprint: Fingerprint
    simulation_result_fingerprint: Fingerprint
    frame_count: StrictInt = Field(ge=2, le=5000)
    points: tuple[SimulationTracePoint, ...] = Field(max_length=MAX_TRACE_POINTS)
    source_times: tuple[TraceSourceTime, ...] = Field(max_length=MAX_TRACE_POINTS)
    omitted_points: StrictInt = Field(ge=0, le=5000)
    omission: Literal["NONE", "NOT_REQUESTED", "TRACE_UNAVAILABLE", "POINT_LIMIT", "INCOMPARABLE"]

    @model_validator(mode="after")
    def ordered_points(self):
        if len(self.points) + self.omitted_points != self.frame_count:
            raise ValueError("trace omission count mismatch")
        if any(a.sequence >= b.sequence or a.timestamp >= b.timestamp
               for a, b in zip(self.points, self.points[1:])):
            raise ValueError("trace points must be independent ordered original frames")
        if self.source_times and tuple(p.sequence for p in self.points) != tuple(p.sequence for p in self.source_times):
            raise ValueError("trace source time identity mismatch")
        if any(point.timestamp != max(source.book_received_at, source.context_received_at)
               for point, source in zip(self.points, self.source_times)):
            raise ValueError("trace evaluation must use original receipt clock")
        return self


class ScenarioHistoricalResponse(Evidence):
    version: Literal["phase165c2-v1"] = "phase165c2-v1"
    request: ScenarioHistoricalRequest
    request_fingerprint: Fingerprint
    receipt: QuantitativeComparison
    segment_count: StrictInt = Field(ge=1, le=32)
    segments: tuple[SegmentIdentity, ...] = Field(min_length=1, max_length=32)
    selection_policy: Literal["RERUN_SELECTED_SEGMENT"] = "RERUN_SELECTED_SEGMENT"
    provenance: HistoricalDatasetProvenance
    declared_gaps: tuple[HistoricalGap, ...] = Field(max_length=1024)
    issues: tuple[ReplayIssue, ...] = Field(max_length=100)
    omitted_issues: StrictInt = Field(ge=0)
    scenario_trace: ComparisonTrace
    historical_trace: ComparisonTrace
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def response_identity(self):
        from app.simulation.models import stable_fingerprint
        if self.request_fingerprint != stable_fingerprint(self.request):
            raise ValueError("comparison request identity mismatch")
        if self.segment_count != len(self.segments) or tuple(s.segment_index for s in self.segments) != tuple(range(self.segment_count)):
            raise ValueError("comparison segment identities mismatch")
        f = self.receipt.foundation
        if (self.receipt.selected_segment_index != self.request.segment_index or
                f.historical.original_dataset_fingerprint != self.request.historical.dataset_fingerprint or
                self.provenance.dataset_fingerprint != self.request.historical.dataset_fingerprint or
                f.scenario.market != self.request.research_market or
                f.scenario.frame_count != self.request.frames or
                f.historical.market != self.request.historical.market or
                f.historical.replay_segment_count != self.segment_count):
            raise ValueError("comparison selected inputs mismatch")
        if self.request.segment_index >= len(self.segments):
            raise ValueError("comparison selected segment unavailable")
        selected = self.segments[self.request.segment_index]
        if any(getattr(selected, key) != getattr(f.historical, other) for key, other in (
            ("dataset_fingerprint", "engine_dataset_fingerprint"), ("run_fingerprint", "run_fingerprint"),
            ("simulation_result_fingerprint", "simulation_result_fingerprint"))):
            raise ValueError("selected archive identity mismatch")
        if (selected.frame_count != f.historical.frame_count or
                selected.window_start != f.historical.window_start or
                selected.window_end != f.historical.window_end or
                self.provenance.source_kind != f.historical.source_kind or
                sum(s.frame_count for s in self.segments) > self.request.historical.max_frames or
                len(self.historical_trace.source_times) != len(self.historical_trace.points) or
                self.scenario_trace.source_times):
            raise ValueError("selected segment coverage mismatch")
        for trace, side in ((self.scenario_trace, f.scenario), (self.historical_trace, f.historical)):
            if (trace.run_fingerprint != side.run_fingerprint or trace.dataset_fingerprint != side.engine_dataset_fingerprint or
                    trace.simulation_result_fingerprint != side.simulation_result_fingerprint or trace.frame_count != side.frame_count or
                    len(trace.points) > self.request.trace_point_limit or
                    (self.receipt.display_policy == "BLOCKED" and trace.points)):
                raise ValueError("comparison trace identity mismatch")
        return self


def project_trace(result, side, request, frames=()):
    blocked = side == "INCOMPARABLE"
    enabled = request.include_traces and not blocked
    points = tuple(result.trace[:request.trace_point_limit]) if enabled else ()
    by_sequence = {f.sequence: f for f in frames}
    times = tuple(TraceSourceTime(sequence=p.sequence,
        book_received_at=by_sequence[p.sequence].book_observation.received_at,
        book_source_timestamp=by_sequence[p.sequence].book_observation.source_timestamp,
        book_source_event_time_verified=by_sequence[p.sequence].book_observation.source_event_time_verified,
        context_received_at=by_sequence[p.sequence].context_observation.received_at,
        context_source_timestamp=by_sequence[p.sequence].context_observation.source_timestamp,
        context_source_event_time_verified=by_sequence[p.sequence].context_observation.source_event_time_verified)
        for p in points) if frames else ()
    from app.simulation.models import stable_fingerprint
    return ComparisonTrace(run_fingerprint=result.run_fingerprint, dataset_fingerprint=result.dataset_fingerprint,
        simulation_result_fingerprint=stable_fingerprint(result.model_dump(mode="json")),
        frame_count=result.metrics.frame_count, points=points, source_times=times,
        omitted_points=result.metrics.frame_count-len(points),
        omission="INCOMPARABLE" if blocked else "NOT_REQUESTED" if not request.include_traces else
            "TRACE_UNAVAILABLE" if not result.trace else "POINT_LIMIT" if len(points)<result.metrics.frame_count else "NONE")


async def comparison_history(service, **inputs):
    # Keep all filesystem/storage exception knowledge inside this boundary.
    from .storage import StorageError, StorageCorruptionError
    from .contracts import ReplayStorageUnavailable
    try:
        return await service.replay_history(**inputs)
    except StorageCorruptionError:
        raise
    except StorageError:
        raise ReplayStorageUnavailable() from None
