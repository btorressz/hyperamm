"""Phase 16.5A.1: immutable scenario-vs-replay provenance only.

No API, runtime mutation, metric deltas, combined returns or trading authority.
ALIGNED is reserved until a later phase can prove paired economic/time evidence.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import AwareDatetime, Field, StrictInt, model_validator

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
    strategy = StrategyConfig.model_validate(data["strategy"])
    agents = AgentConfig.model_validate(data["agents"])
    risk = RiskFirewallConfig.model_validate(data["risk"])
    simulation = SimulationConfig.model_validate(data["simulation"])
    profile = (ResearchPerpMarketProfile.model_validate(data["market_profile"])
               if data["market_profile"] is not None else None)
    if strategy.execution_mode != ExecutionMode.PAPER or strategy.market_data_mode != MarketDataMode.DEMO:
        raise ValueError("comparison capture must be an isolated DEMO/PAPER strategy")
    if profile is not None and (profile.market != strategy.market or
                                profile.sz_decimals != strategy.size_precision or
                                not profile.research_supported):
        raise ValueError("comparison market profile does not match research strategy")
    return strategy, agents, risk, simulation, profile


class ScenarioInputCapture(Evidence):
    """Caller-captured effective research inputs, not raw operational config.

    Phase 16.5A.2 must bind these copies to the *same admitted scenario job*.
    Existing scenario results attest strategy, execution, capital, and dataset,
    but do not independently attest the agent and risk snapshots.
    """

    strategy: StrategyConfig
    agents: AgentConfig
    risk: RiskFirewallConfig
    simulation: SimulationConfig
    market_profile: ResearchPerpMarketProfile | None = None


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
        if (self.classification == "INCOMPARABLE") != any(
            reason in self.reasons for reason in ("MARKET_MISMATCH", "ENGINE_VERSION_MISMATCH")
        ):
            raise ValueError("classification and hard mismatches disagree")
        if self.scenario.kind != "SCENARIO" or self.historical.kind != "HISTORICAL_SEGMENT":
            raise ValueError("comparison requires scenario and historical segment")
        if self.comparison_fingerprint != stable_fingerprint(self.model_dump(exclude={"comparison_fingerprint"})):
            raise ValueError("comparison identity mismatch")
        return self


def capture_comparison_foundation(*, scenario: SimulationResult,
                                  scenario_inputs: ScenarioInputCapture,
                                  historical: HistoricalReplayResult,
                                  segment_index: int) -> ComparisonFoundation:
    """Pure, strict provenance builder; no computation, strategy writes or PnL deltas."""
    if type(segment_index) is not int:
        raise ValueError("historical segment index must be an integer")
    # Revalidate even model_copy(update=...) inputs, which bypass Pydantic checks.
    scenario = SimulationResult.model_validate_json(scenario.model_dump_json())
    historical = HistoricalReplayResult.model_validate_json(historical.model_dump_json())
    scenario_inputs = ScenarioInputCapture.model_validate_json(scenario_inputs.model_dump_json())
    if segment_index < 0 or segment_index >= len(historical.segments):
        raise ValueError("historical segment index is unavailable")
    if not scenario.simulated or scenario.scenario == "historical-replay" or not scenario.research_assumptions:
        raise ValueError("a real deterministic scenario SimulationResult is required")
    a = scenario.research_assumptions
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
    if (archived.strategy_fingerprint != historical_snapshot.strategy_fingerprint or
        archived.execution_assumptions_fingerprint != historical_snapshot.execution_fingerprint or
        archived.market_profile_fingerprint != historical_snapshot.market_profile_fingerprint or
        archived.metrics.starting_equity != replay_simulation.initial_equity_quote or
        replay_strategy.market != historical.request.market or
        replay_profile is None or replay_profile.market != historical.request.market or
        replay_simulation.execution.fingerprint != historical.request.execution.paper.fingerprint):
        raise ValueError("historical segment does not match captured configuration")
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

    pairs: tuple[tuple[Dimensions, object, object, Reason | None], ...] = (
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
