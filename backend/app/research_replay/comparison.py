"""Immutable scenario-vs-replay provenance and admitted scenario receipts.

No runtime mutation, metric deltas, combined returns or trading authority.
ALIGNED is reserved until a later phase can prove paired economic/time evidence.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from app.agents.config import AgentConfig
from app.execution.research import PaperExecutionAssumptions
from app.market_data.live_models import Evidence
from app.market_data.models import MarketDataMode
from app.research_replay.contracts import HistoricalReplayResult
from app.research_replay.models import Fingerprint
from app.risk.firewall import RiskFirewallConfig
from app.simulation.config import SimulationConfig
from app.simulation.market_profiles import ResearchPerpMarketId, ResearchPerpMarketProfile
from app.simulation.models import SimulationResult, stable_fingerprint
from app.simulation.scenarios import ScenarioName
from app.strategy.models import ExecutionMode, StrategyConfig

CONTRACT_VERSION = "phase165a1-v1"
Dimensions = Literal[
    "MARKET", "ENGINE", "STRATEGY", "AGENTS", "RISK",
    "ACCOUNTING", "EXECUTION", "MARKET_PROFILE", "SIMULATION_CONTROLS",
]
Reason = Literal[
    "MARKET_MISMATCH", "ENGINE_VERSION_MISMATCH",
    "STRATEGY_MISMATCH", "AGENTS_MISMATCH", "RISK_MISMATCH",
    "ACCOUNTING_MISMATCH", "EXECUTION_MISMATCH",
    "MARKET_PROFILE_MISMATCH", "SIMULATION_CONTROLS_MISMATCH",
    "SCENARIO_AND_HISTORICAL_EVIDENCE_DIFFER",
    "SCENARIO_INPUT_CAPTURE_NOT_ENGINE_ATTESTED",
    "TEMPORAL_ALIGNMENT_UNPROVEN", "HISTORICAL_SEGMENT_RESETS",
    "RECORDED_NATIVE_SOURCE_UNAUTHENTICATED",
    "HISTORICAL_LICENSING_UNVERIFIED",
]
LIMITATIONS = (
    "Configuration matching is not proof of equivalent market conditions, timing or strategy performance.",
    "Scenario input capture is caller supplied; existing SimulationResult does not authenticate every agent/risk input.",
    "Historical recorded-native and permitted-use labels are user assertions, not independently verified.",
    "Historical replay runs independent segments; never aggregate capital, returns, equity or risk across resets.",
    "No financial deltas, profitability ranking, execution forecast or trading authority are created by this contract.",
)


def _canonical_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _capture_payload(strategy: StrategyConfig, agents: AgentConfig, risk: RiskFirewallConfig,
                     simulation: SimulationConfig, market_profile: ResearchPerpMarketProfile | None) -> dict:
    return {
        "strategy": strategy.model_dump(mode="json"),
        "agents": agents.model_dump(mode="json"),
        "risk": risk.model_dump(mode="json"),
        "simulation": simulation.model_dump(mode="json"),
        "market_profile": market_profile.model_dump(mode="json") if market_profile is not None else None,
    }


def _typed_config(data: dict):
    if not isinstance(data, dict) or set(data) != {
        "strategy", "agents", "risk", "simulation", "market_profile"
    }:
        raise ValueError("comparison capture must contain the five existing configuration fields")
    strategy = _validated_config(StrategyConfig, data["strategy"])
    agents = _validated_config(AgentConfig, data["agents"])
    risk = _validated_config(RiskFirewallConfig, data["risk"])
    simulation = _validated_config(SimulationConfig, data["simulation"])
    profile = (_validated_config(ResearchPerpMarketProfile, data["market_profile"])
               if data["market_profile"] is not None else None)
    if strategy.execution_mode != ExecutionMode.PAPER or strategy.market_data_mode != MarketDataMode.DEMO:
        raise ValueError("comparison capture must be an isolated DEMO/PAPER strategy")
    if profile is not None and (profile.market != strategy.market or
                                profile.sz_decimals != strategy.size_precision or
                                not profile.research_supported):
        raise ValueError("comparison market profile does not match research strategy")
    if profile is not None:
        from app.simulation.market_profiles import ResearchPerpMarketMetadata, profile as build_profile
        metadata = ResearchPerpMarketMetadata.model_validate({
            name: getattr(profile, name) for name in ResearchPerpMarketMetadata.model_fields})
        expected = build_profile(metadata)
        if (profile.profile_fingerprint != expected.profile_fingerprint or
                profile.profile_version != expected.profile_version or
                profile.simulated_reference_price != expected.simulated_reference_price):
            raise ValueError("comparison market profile fingerprint mismatch")
    return strategy, agents, risk, simulation, profile


def _validated_config(model, value):
    # Existing operational Strategy/Risk models ignore extras and may be mutable.
    # Research captures must reject them and revalidate model_copy bypasses too.
    if isinstance(value, model):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict) or set(value) - set(model.model_fields):
        raise ValueError("unexpected comparison configuration fields or type")
    result = model.model_validate_json(_canonical_json(value), strict=True)
    if _canonical_json(value) != _canonical_json(result.model_dump(mode="json")):
        raise ValueError("comparison configuration requires complete normalized canonical values")
    return result


class ScenarioInputCapture(Evidence):
    """Caller-captured effective research inputs, not raw operational config.

    SimulationService binds these copies to the same admitted scenario job.
    Existing scenario results attest strategy, execution, capital, and dataset,
    but do not independently attest the agent and risk snapshots.
    """

    strategy: StrategyConfig
    agents: AgentConfig
    risk: RiskFirewallConfig
    simulation: SimulationConfig
    market_profile: ResearchPerpMarketProfile | None = None

    @field_validator("strategy", "agents", "risk", "simulation", "market_profile", mode="before")
    @classmethod
    def detached_validated_inputs(cls, value, info):
        if info.field_name == "market_profile" and value is None:
            return None
        models = dict(strategy=StrategyConfig, agents=AgentConfig, risk=RiskFirewallConfig,
                      simulation=SimulationConfig, market_profile=ResearchPerpMarketProfile)
        return _validated_config(models[info.field_name], value)

    @model_validator(mode="after")
    def effective_research_inputs(self):
        _typed_config(_capture_payload(self.strategy, self.agents, self.risk,
                                      self.simulation, self.market_profile))
        return self


class ComparisonConfigSnapshot(Evidence):
    """Frozen canonical values and reproducible individual-domain fingerprints."""

    canonical_json: str = Field(min_length=2, max_length=160_000)
    fingerprint: Fingerprint
    strategy_fingerprint: Fingerprint
    agents_fingerprint: Fingerprint
    risk_fingerprint: Fingerprint
    accounting_fingerprint: Fingerprint
    execution_fingerprint: Fingerprint
    simulation_controls_fingerprint: Fingerprint
    market_profile_fingerprint: Fingerprint | None

    def inputs(self) -> ScenarioInputCapture:
        return ScenarioInputCapture.model_validate_json(self.canonical_json)

    @classmethod
    def from_payload(cls, payload: dict) -> "ComparisonConfigSnapshot":
        strategy, agents, risk, simulation, profile = _typed_config(payload)
        normalized = _capture_payload(strategy, agents, risk, simulation, profile)
        return cls(
            canonical_json=_canonical_json(normalized),
            fingerprint=stable_fingerprint(normalized),
            strategy_fingerprint=stable_fingerprint(strategy),
            agents_fingerprint=stable_fingerprint(agents),
            risk_fingerprint=stable_fingerprint(risk),
            accounting_fingerprint=stable_fingerprint({
                "initial_equity_quote": simulation.initial_equity_quote,
                "accounting": simulation.accounting,
            }),
            execution_fingerprint=simulation.execution.fingerprint,
            simulation_controls_fingerprint=stable_fingerprint({
                "max_frames": simulation.max_frames,
                "record_trace": simulation.record_trace,
                "trace_max_points": simulation.trace_max_points,
                "fill_model": simulation.fill_model,
            }),
            market_profile_fingerprint=profile.profile_fingerprint if profile else None,
        )

    @model_validator(mode="after")
    def verify_snapshot(self):
        try:
            data = json.loads(self.canonical_json)
            if self.canonical_json != _canonical_json(data):
                raise ValueError("noncanonical comparison configuration")
            expected = type(self).from_payload_unchecked(data)
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid comparison configuration JSON") from exc
        if any(getattr(self, field) != expected[field] for field in expected):
            raise ValueError("comparison configuration fingerprint mismatch")
        return self

    @staticmethod
    def from_payload_unchecked(data: dict) -> dict:
        strategy, agents, risk, simulation, profile = _typed_config(data)
        normalized = _capture_payload(strategy, agents, risk, simulation, profile)
        return dict(
            fingerprint=stable_fingerprint(normalized),
            strategy_fingerprint=stable_fingerprint(strategy),
            agents_fingerprint=stable_fingerprint(agents),
            risk_fingerprint=stable_fingerprint(risk),
            accounting_fingerprint=stable_fingerprint({
                "initial_equity_quote": simulation.initial_equity_quote,
                "accounting": simulation.accounting,
            }),
            execution_fingerprint=simulation.execution.fingerprint,
            simulation_controls_fingerprint=stable_fingerprint({
                "max_frames": simulation.max_frames,
                "record_trace": simulation.record_trace,
                "trace_max_points": simulation.trace_max_points,
                "fill_model": simulation.fill_model,
            }),
            market_profile_fingerprint=profile.profile_fingerprint if profile else None,
        )


class ScenarioProvenanceReceipt(Evidence):
    """Immutable service binding, not a signature or independent engine attestation."""

    version: Literal["phase165a2-v1"] = "phase165a2-v1"
    requested_scenario: ScenarioName
    requested_frames: StrictInt = Field(ge=2, le=5000)
    captured: ComparisonConfigSnapshot
    result_fingerprint: Fingerprint
    run_fingerprint: Fingerprint
    dataset_fingerprint: Fingerprint
    engine_version: str = Field(min_length=1, max_length=96)
    input_capture_engine_attested: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"
    receipt_fingerprint: Fingerprint

    @model_validator(mode="after")
    def receipt_identity(self):
        if self.requested_frames > self.captured.inputs().simulation.max_frames:
            raise ValueError("scenario request exceeds captured frame bound")
        if self.receipt_fingerprint != stable_fingerprint(self.model_dump(exclude={"receipt_fingerprint"})):
            raise ValueError("scenario provenance receipt fingerprint mismatch")
        return self

    @classmethod
    def bind(cls, *, result, captured, scenario, frames):
        values = dict(requested_scenario=ScenarioName(scenario), requested_frames=frames,
            captured=captured, result_fingerprint=stable_fingerprint(result.model_dump(mode="json")),
            run_fingerprint=result.run_fingerprint, dataset_fingerprint=result.dataset_fingerprint,
            engine_version=result.engine_version)
        defaults = {name: field.default for name, field in cls.model_fields.items()
                    if not field.is_required()}
        return cls(**values, receipt_fingerprint=stable_fingerprint({**defaults, **values}))

    def verify_result(self, result):
        if (self.result_fingerprint != stable_fingerprint(result.model_dump(mode="json")) or
                self.run_fingerprint != result.run_fingerprint or
                self.dataset_fingerprint != result.dataset_fingerprint or
                self.engine_version != result.engine_version or
                self.requested_scenario.value != result.scenario or
                self.requested_frames != result.metrics.frame_count):
            raise ValueError("scenario result does not match admitted provenance receipt")
        _validate_scenario_capture(result, self.captured.inputs())


class CapturedScenarioResult(Evidence):
    """Opt-in response; the frozen receipt hashes the existing native result."""

    result: SimulationResult
    provenance: ScenarioProvenanceReceipt

    @model_validator(mode="after")
    def bound_result(self):
        self.provenance.verify_result(self.result)
        return self


class ComparisonSide(Evidence):
    kind: Literal["SCENARIO", "HISTORICAL_SEGMENT"]
    market: ResearchPerpMarketId
    source_kind: Literal["DETERMINISTIC_SCENARIO", "SYNTHETIC_FIXTURE", "RECORDED_NATIVE"]
    original_dataset_fingerprint: Fingerprint
    engine_dataset_fingerprint: Fingerprint
    simulation_result_fingerprint: Fingerprint
    run_fingerprint: Fingerprint
    engine_version: str = Field(min_length=1, max_length=96)
    frame_count: StrictInt = Field(ge=2, le=5000)
    captured: ComparisonConfigSnapshot
    window_start: AwareDatetime | None
    window_end: AwareDatetime | None
    window_status: Literal["TRACE_COMPLETE", "UNKNOWN", "SEGMENT_RECEIPTS"]
    segment_index: StrictInt | None = Field(default=None, ge=0, le=31)
    replay_result_fingerprint: Fingerprint | None = None
    replay_segment_count: StrictInt | None = Field(default=None, ge=1, le=32)
    source_authenticated: Literal[False] = False
    licensing_independently_verified: Literal[False] = False
    simulated: Literal[True] = True
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def validate_side(self):
        if self.market != self.captured.inputs().strategy.market:
            raise ValueError("comparison side market disagrees with captured configuration")
        if (self.kind == "SCENARIO") != (self.segment_index is None):
            raise ValueError("scenario cannot carry a historical segment index")
        if self.kind == "SCENARIO":
            if (self.source_kind != "DETERMINISTIC_SCENARIO" or
                self.replay_result_fingerprint is not None or self.replay_segment_count is not None or
                self.original_dataset_fingerprint != self.engine_dataset_fingerprint):
                raise ValueError("scenario provenance cannot assert a historical source")
        elif (self.source_kind == "DETERMINISTIC_SCENARIO" or
              self.replay_result_fingerprint is None or self.replay_segment_count is None):
            raise ValueError("incomplete historical segment provenance")
        if self.kind == "HISTORICAL_SEGMENT" and (
                self.segment_index >= self.replay_segment_count or self.window_start is None):
            raise ValueError("historical segment index/window unavailable")
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("time window must be complete or unavailable")
        if self.window_start is not None and self.window_end <= self.window_start:
            raise ValueError("comparison window must increase")
        if self.kind == "HISTORICAL_SEGMENT" and self.window_status != "SEGMENT_RECEIPTS":
            raise ValueError("historical window must use retained receipts")
        if self.kind == "SCENARIO" and (self.window_status == "SEGMENT_RECEIPTS" or
              (self.window_status == "TRACE_COMPLETE") != (self.window_start is not None)):
            raise ValueError("scenario time window cannot be fabricated")
        return self


def _dimension_pairs(scenario_side, historical_side):
    scenario_snapshot, historical_snapshot = scenario_side.captured, historical_side.captured
    return (
        ("MARKET", scenario_side.market, historical_side.market, "MARKET_MISMATCH"),
        ("ENGINE", scenario_side.engine_version, historical_side.engine_version, "ENGINE_VERSION_MISMATCH"),
        ("STRATEGY", scenario_snapshot.strategy_fingerprint, historical_snapshot.strategy_fingerprint, "STRATEGY_MISMATCH"),
        ("AGENTS", scenario_snapshot.agents_fingerprint, historical_snapshot.agents_fingerprint, "AGENTS_MISMATCH"),
        ("RISK", scenario_snapshot.risk_fingerprint, historical_snapshot.risk_fingerprint, "RISK_MISMATCH"),
        ("ACCOUNTING", scenario_snapshot.accounting_fingerprint, historical_snapshot.accounting_fingerprint, "ACCOUNTING_MISMATCH"),
        ("EXECUTION", scenario_snapshot.execution_fingerprint, historical_snapshot.execution_fingerprint, "EXECUTION_MISMATCH"),
        ("MARKET_PROFILE", scenario_snapshot.market_profile_fingerprint, historical_snapshot.market_profile_fingerprint, "MARKET_PROFILE_MISMATCH"),
        ("SIMULATION_CONTROLS", scenario_snapshot.simulation_controls_fingerprint,
         historical_snapshot.simulation_controls_fingerprint, "SIMULATION_CONTROLS_MISMATCH"),
    )


class ComparisonFoundation(Evidence):
    version: Literal["phase165a1-v1"] = CONTRACT_VERSION
    classification: Literal["ALIGNED", "CONTEXT_ONLY", "INCOMPARABLE"]
    scenario: ComparisonSide
    historical: ComparisonSide
    aligned_dimensions: tuple[Dimensions, ...]
    differing_dimensions: tuple[Dimensions, ...]
    reasons: tuple[Reason, ...]
    direct_metric_deltas_allowed: Literal[False] = False
    cross_segment_aggregation_allowed: Literal[False] = False
    matched_market_evidence_verified: Literal[False] = False
    authority: Literal["NONE"] = "NONE"
    limitations: tuple[str, ...] = LIMITATIONS
    comparison_fingerprint: Fingerprint

    @model_validator(mode="after")
    def validate_classification(self):
        # ALIGNED requires a future authenticated paired-data lineage contract.
        # A matching strategy fingerprint alone never makes scenario and replay
        # economically equivalent. Avoid inventing source/time matching.
        if self.classification == "ALIGNED":
            raise ValueError("ALIGNED requires paired market evidence not available in phase165a1-v1")
        pairs = _dimension_pairs(self.scenario, self.historical)
        aligned = tuple(name for name, left, right, _ in pairs if left == right)
        differing = tuple(name for name, left, right, _ in pairs if left != right)
        mismatches = tuple(code for _, left, right, code in pairs if left != right)
        if (self.aligned_dimensions != aligned or self.differing_dimensions != differing or
                tuple(code for code in self.reasons if code.endswith("_MISMATCH")) != mismatches):
            raise ValueError("comparison dimensions and mismatch reasons disagree with captured identities")
        required = {"SCENARIO_AND_HISTORICAL_EVIDENCE_DIFFER",
                    "SCENARIO_INPUT_CAPTURE_NOT_ENGINE_ATTESTED", "TEMPORAL_ALIGNMENT_UNPROVEN",
                    "HISTORICAL_LICENSING_UNVERIFIED"}
        if (not required.issubset(self.reasons) or len(set(self.reasons)) != len(self.reasons) or
                self.limitations != LIMITATIONS):
            raise ValueError("comparison must retain provenance limitations")
        if (self.historical.source_kind == "RECORDED_NATIVE" and
                "RECORDED_NATIVE_SOURCE_UNAUTHENTICATED" not in self.reasons):
            raise ValueError("comparison must retain historical source trust limitation")
        if (self.historical.replay_segment_count > 1 and "HISTORICAL_SEGMENT_RESETS" not in self.reasons):
            raise ValueError("comparison must retain independent historical segment resets")
        if (self.classification == "INCOMPARABLE") != bool({"MARKET", "ENGINE"}.intersection(differing)):
            raise ValueError("classification and hard mismatches disagree")
        if self.scenario.kind != "SCENARIO" or self.historical.kind != "HISTORICAL_SEGMENT":
            raise ValueError("comparison requires scenario and historical segment")
        if self.comparison_fingerprint != stable_fingerprint(self.model_dump(exclude={"comparison_fingerprint"})):
            raise ValueError("comparison identity mismatch")
        return self


def _validate_scenario_capture(scenario, scenario_inputs):
    if not scenario.simulated or scenario.scenario == "historical-replay" or not scenario.research_assumptions:
        raise ValueError("a real deterministic scenario SimulationResult is required")
    a = scenario.research_assumptions
    execution = PaperExecutionAssumptions.model_validate(scenario.execution_assumptions)
    if execution.fingerprint != scenario.execution_assumptions_fingerprint:
        raise ValueError("scenario execution assumptions fingerprint mismatch")
    if (scenario.strategy_fingerprint != stable_fingerprint(scenario_inputs.strategy) or
        scenario.execution_assumptions_fingerprint != scenario_inputs.simulation.execution.fingerprint or
        scenario.metrics.starting_equity != scenario_inputs.simulation.initial_equity_quote or
        scenario.metrics.frame_count != a.frame_count or
        a.dataset_fingerprint != scenario.dataset_fingerprint or a.scenario != scenario.scenario or
        a.market != scenario_inputs.strategy.market or
        scenario_inputs.strategy.execution_mode != ExecutionMode.PAPER or
        scenario_inputs.strategy.market_data_mode != MarketDataMode.DEMO or
        scenario.metrics.frame_count < 2 or scenario.metrics.frame_count > 5000):
        raise ValueError("scenario output does not match captured strategy/execution/capital/evidence")
    expected_profile = (scenario_inputs.market_profile.profile_fingerprint
                        if scenario_inputs.market_profile else None)
    if (scenario.market_profile_fingerprint != expected_profile or
        a.market_profile_fingerprint != expected_profile or
        scenario.research_market not in (None, a.market) or
        (scenario_inputs.market_profile is not None and
         scenario_inputs.market_profile.market != a.market)):
        raise ValueError("scenario research market profile identity mismatch")

    return a


def capture_comparison_foundation(*, scenario: SimulationResult,
                                  scenario_inputs: ScenarioInputCapture | None = None,
                                  scenario_provenance: ScenarioProvenanceReceipt | None = None,
                                  historical: HistoricalReplayResult,
                                  segment_index: int) -> ComparisonFoundation:
    """Pure, strict provenance builder; no computation, strategy writes or PnL deltas."""
    if type(segment_index) is not int:
        raise ValueError("historical segment index must be an integer")
    # Revalidate even model_copy(update=...) inputs, which bypass Pydantic checks.
    scenario = SimulationResult.model_validate_json(scenario.model_dump_json())
    historical = HistoricalReplayResult.model_validate_json(historical.model_dump_json())
    if scenario_provenance is not None:
        scenario_provenance = ScenarioProvenanceReceipt.model_validate_json(scenario_provenance.model_dump_json())
        scenario_provenance.verify_result(scenario)
        bound_inputs = scenario_provenance.captured.inputs()
        if scenario_inputs is not None and ComparisonConfigSnapshot.from_payload(
                json.loads(scenario_inputs.model_dump_json())) != scenario_provenance.captured:
            raise ValueError("scenario configuration capture differs from admitted receipt")
        scenario_inputs = bound_inputs
    if not isinstance(scenario_inputs, ScenarioInputCapture):
        raise ValueError("scenario configuration capture or provenance receipt is required")
    scenario_inputs = ScenarioInputCapture.model_validate_json(scenario_inputs.model_dump_json())
    if segment_index < 0 or segment_index >= len(historical.segments):
        raise ValueError("historical segment index is unavailable")
    a = _validate_scenario_capture(scenario, scenario_inputs)

    scenario_snapshot = ComparisonConfigSnapshot.from_payload(_capture_payload(
        scenario_inputs.strategy, scenario_inputs.agents, scenario_inputs.risk,
        scenario_inputs.simulation, scenario_inputs.market_profile))
    # An incomplete trace cannot be treated as a complete scenario time window.
    full_trace = (len(scenario.trace) == scenario.metrics.frame_count and len(scenario.trace) >= 2 and
                  all(x.timestamp.tzinfo is not None for x in scenario.trace) and
                  all(x.sequence < y.sequence and x.timestamp < y.timestamp
                      for x, y in zip(scenario.trace, scenario.trace[1:])))
    scenario_side = ComparisonSide(
        kind="SCENARIO", market=a.market, source_kind="DETERMINISTIC_SCENARIO",
        original_dataset_fingerprint=scenario.dataset_fingerprint,
        engine_dataset_fingerprint=scenario.dataset_fingerprint,
        simulation_result_fingerprint=stable_fingerprint(scenario.model_dump(mode="json")),
        run_fingerprint=scenario.run_fingerprint, engine_version=scenario.engine_version,
        frame_count=scenario.metrics.frame_count, captured=scenario_snapshot,
        window_start=scenario.trace[0].timestamp if full_trace else None,
        window_end=scenario.trace[-1].timestamp if full_trace else None,
        window_status="TRACE_COMPLETE" if full_trace else "UNKNOWN")

    segment = historical.segments[segment_index]
    replay_payload = json.loads(historical.captured_configuration_json)
    historical_snapshot = ComparisonConfigSnapshot.from_payload(replay_payload)
    if historical_snapshot.fingerprint != historical.captured_configuration_fingerprint:
        raise ValueError("historical captured configuration mismatch")
    archived = SimulationResult.model_validate_json(segment.simulation_result_json)
    replay_strategy, _, _, replay_simulation, replay_profile = _typed_config(replay_payload)
    expected_simulation = historical.request.execution.accounting.to_simulation(SimulationConfig(
        max_frames=historical.request.max_frames, record_trace=historical.request.record_trace,
        trace_max_points=historical.request.trace_max_points))
    expected_simulation = expected_simulation.model_copy(update={"execution": historical.request.execution.paper})
    if (archived.strategy_fingerprint != historical_snapshot.strategy_fingerprint or
        archived.execution_assumptions_fingerprint != historical_snapshot.execution_fingerprint or
        archived.market_profile_fingerprint != historical_snapshot.market_profile_fingerprint or
        archived.metrics.starting_equity != replay_simulation.initial_equity_quote or
        replay_strategy.market != historical.request.market or
        replay_profile is None or replay_profile.market != historical.request.market or
        replay_profile.sz_decimals != historical.request.execution.size_decimals or
        replay_profile.metadata_source != historical.request.execution.metadata or
        stable_fingerprint(replay_simulation) != stable_fingerprint(expected_simulation) or
        historical.request.dataset_fingerprint != historical.provenance.dataset_fingerprint or
        segment.segment_index != segment_index or
        replay_simulation.execution.fingerprint != historical.request.execution.paper.fingerprint):
        raise ValueError("historical segment does not match captured configuration")
    # Reuse the adapter to verify the selected engine dataset from retained
    # receipts. This is deliberately distinct from original storage identity.
    from .adapter import ReplaySegment, segment_dataset, simulation_frame
    expected_dataset = segment_dataset(ReplaySegment(segment.reset_reason, tuple(
        simulation_frame(frame.book_observation, frame.context_observation,
            timestamp=frame.evaluated_at, sequence=frame.sequence) for frame in segment.frames),
        segment.frames), historical.request)
    if expected_dataset.fingerprint != segment.dataset_fingerprint:
        raise ValueError("historical engine dataset does not match retained segment evidence")
    historical_side = ComparisonSide(
        kind="HISTORICAL_SEGMENT", market=historical.request.market,
        source_kind=historical.provenance.source_kind,
        original_dataset_fingerprint=historical.request.dataset_fingerprint,
        engine_dataset_fingerprint=segment.dataset_fingerprint,
        simulation_result_fingerprint=segment.simulation_result_fingerprint,
        run_fingerprint=segment.run_fingerprint, engine_version=archived.engine_version,
        frame_count=segment.frame_count, captured=historical_snapshot,
        window_start=segment.frames[0].evaluated_at, window_end=segment.frames[-1].evaluated_at,
        window_status="SEGMENT_RECEIPTS", segment_index=segment_index,
        replay_result_fingerprint=historical.result_fingerprint,
        replay_segment_count=len(historical.segments))

    pairs = _dimension_pairs(scenario_side, historical_side)
    aligned = tuple(name for name, left, right, _ in pairs if left == right)
    differing = tuple(name for name, left, right, _ in pairs if left != right)
    reasons: list[Reason] = [code for _, left, right, code in pairs if left != right and code is not None]
    reasons.extend((
        "SCENARIO_AND_HISTORICAL_EVIDENCE_DIFFER",
        "SCENARIO_INPUT_CAPTURE_NOT_ENGINE_ATTESTED",
        "TEMPORAL_ALIGNMENT_UNPROVEN",
        "HISTORICAL_LICENSING_UNVERIFIED",
    ))
    if len(historical.segments) > 1 or historical.declared_gaps or historical.issues:
        reasons.append("HISTORICAL_SEGMENT_RESETS")
    if historical.provenance.source_kind == "RECORDED_NATIVE":
        reasons.append("RECORDED_NATIVE_SOURCE_UNAUTHENTICATED")
    classification = ("INCOMPARABLE" if "MARKET_MISMATCH" in reasons or
                      "ENGINE_VERSION_MISMATCH" in reasons else "CONTEXT_ONLY")
    fields = dict(classification=classification, scenario=scenario_side,
                  historical=historical_side, aligned_dimensions=aligned,
                  differing_dimensions=differing, reasons=tuple(reasons))
    defaults = {
        key: fld.default for key, fld in ComparisonFoundation.model_fields.items()
        if key not in fields and key != "comparison_fingerprint" and not fld.is_required()
    }
    return ComparisonFoundation(**fields,
        comparison_fingerprint=stable_fingerprint({**defaults, **fields}))
