"""Phase 16.5A.1 immutable contracts from real scenario/replay PAPER outputs.

No API, market feed, signing, worker changes or synthetic return aggregation.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.config import AgentConfig
from app.research_replay.comparison import (
    ComparisonConfigSnapshot, ComparisonFoundation, ScenarioInputCapture,
    capture_comparison_foundation,
)
from app.risk.firewall import RiskFirewallConfig
from app.simulation.config import SimulationConfig
from app.simulation.service import SimulationService
from app.strategy.models import StrategyConfig
from test_phase162_replay import capture, inputs, vault


@pytest.fixture
async def paired(vault):
    service = SimulationService()
    strategy, agents, risk = StrategyConfig(), AgentConfig(), RiskFirewallConfig()
    simulation = SimulationConfig(max_frames=4, record_trace=True, trace_max_points=4)
    captured = ScenarioInputCapture(strategy=strategy, agents=agents, risk=risk, simulation=simulation)
    scenario = await service.run_scenario(scenario="QUIET", frames=4,
        strategy=strategy, agents=agents, risk=risk, simulation=simulation)
    dataset = vault.save(capture(market="ETH", native=True))
    historical = await service.replay_history(**inputs(vault, dataset))
    return scenario, captured, historical, vault


def build(pair, **kwargs):
    scenario, captured, historical, _ = pair
    return capture_comparison_foundation(scenario=kwargs.get("scenario", scenario),
        scenario_inputs=kwargs.get("scenario_inputs", captured),
        historical=kwargs.get("historical", historical),
        segment_index=kwargs.get("segment_index", 0))


async def test_real_compatible_market_is_context_only_and_has_no_financial_deltas(paired):
    scenario, inputs_, historical, _ = paired
    result = build(paired)
    assert result.version == "phase165a1-v1"
    assert result.classification == "CONTEXT_ONLY"
    assert result.scenario.kind == "SCENARIO"
    assert result.historical.kind == "HISTORICAL_SEGMENT"
    assert result.scenario.market == result.historical.market == "ETH"
    assert result.scenario.run_fingerprint == scenario.run_fingerprint
    assert result.historical.run_fingerprint == historical.segments[0].run_fingerprint
    assert result.historical.original_dataset_fingerprint == historical.request.dataset_fingerprint
    assert result.historical.engine_dataset_fingerprint == historical.segments[0].dataset_fingerprint
    assert result.historical.original_dataset_fingerprint != result.historical.engine_dataset_fingerprint
    assert result.direct_metric_deltas_allowed is False
    assert result.cross_segment_aggregation_allowed is False
    assert result.matched_market_evidence_verified is False
    assert "SCENARIO_AND_HISTORICAL_EVIDENCE_DIFFER" in result.reasons
    assert "SCENARIO_INPUT_CAPTURE_NOT_ENGINE_ATTESTED" in result.reasons
    assert "HISTORICAL_LICENSING_UNVERIFIED" in result.reasons
    assert "RECORDED_NATIVE_SOURCE_UNAUTHENTICATED" in result.reasons
    assert ComparisonFoundation.model_validate_json(result.model_dump_json()) == result
    assert set(result.model_dump()).isdisjoint({"session_pnl_delta", "return_delta", "combined_equity"})


async def test_snapshot_retains_exact_captured_configuration_and_fingerprint(paired):
    report = build(paired)
    for side in (report.scenario, report.historical):
        snapshot = side.captured
        assert ComparisonConfigSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
        assert '"strategy":' in snapshot.canonical_json
        assert '"agents":' in snapshot.canonical_json
        assert '"risk":' in snapshot.canonical_json
        assert '"simulation":' in snapshot.canonical_json
        assert len(snapshot.fingerprint) == 64
        invalid = snapshot.model_copy(update={"strategy_fingerprint": "0" * 64})
        with pytest.raises(ValidationError, match="fingerprint"):
            ComparisonConfigSnapshot.model_validate_json(invalid.model_dump_json())


async def test_scenario_strategy_input_cannot_be_silently_substituted(paired):
    scenario, captured, _, _ = paired
    bad = captured.model_copy(update={"strategy": captured.strategy.model_copy(update={"market": "BTC"})})
    with pytest.raises(ValueError, match="captured strategy"):
        build(paired, scenario_inputs=bad)
    invalid_result = scenario.model_copy(update={"dataset_fingerprint": "0" * 64})
    with pytest.raises(ValueError, match="evidence"):
        build(paired, scenario=invalid_result)


async def test_unverified_agent_risk_inputs_are_explicit_not_trusted(paired):
    _, captured, _, _ = paired
    alt_agents = captured.agents.model_copy(update={"agents_enabled": False})
    alt_risk = captured.risk.model_copy(update={"enabled": False})
    changed = captured.model_copy(update={"agents": alt_agents, "risk": alt_risk})
    report = build(paired, scenario_inputs=changed)
    # Existing scenario output has no standalone engine-signed agent/risk
    # fingerprints. An explicit capture is auditable but not self-authenticating.
    assert report.classification == "CONTEXT_ONLY"
    assert "SCENARIO_INPUT_CAPTURE_NOT_ENGINE_ATTESTED" in report.reasons
    assert "AGENTS_MISMATCH" in report.reasons
    assert "RISK_MISMATCH" in report.reasons


async def test_no_result_or_operational_configuration_mutation(paired):
    scenario, captured, historical, _ = paired
    old = (scenario.model_dump_json(), captured.model_dump_json(), historical.model_dump_json())
    _ = build(paired)
    assert (scenario.model_dump_json(), captured.model_dump_json(), historical.model_dump_json()) == old


async def test_tampered_result_fingerprints_or_segment_index_fail_closed(paired):
    _, _, historical, _ = paired
    tampered = historical.model_copy(update={"result_fingerprint": "0" * 64})
    with pytest.raises(ValidationError):
        build(paired, historical=tampered)
    for index in (-1, True, 32):
        with pytest.raises(ValueError, match="segment"):
            build(paired, segment_index=index)
    valid = build(paired)
    invalid = valid.model_copy(update={"comparison_fingerprint": "0" * 64})
    with pytest.raises(ValidationError, match="comparison identity"):
        ComparisonFoundation.model_validate_json(invalid.model_dump_json())
    forged_aligned = valid.model_copy(update={"classification": "ALIGNED"})
    with pytest.raises(ValidationError, match="paired market evidence"):
        ComparisonFoundation.model_validate_json(forged_aligned.model_dump_json())


async def test_engine_version_mismatch_is_incomparable(paired):
    scenario, _, _, _ = paired
    revised = scenario.model_copy(update={"engine_version": "different-unverified-engine"})
    result = build(paired, scenario=revised)
    assert result.classification == "INCOMPARABLE"
    assert "ENGINE_VERSION_MISMATCH" in result.reasons
    assert result.direct_metric_deltas_allowed is False


async def test_different_markets_are_incomparable(paired):
    scenario, captured, _, vault_ = paired
    dataset = vault_.save(capture(market="BTC", native=False))
    historical = await SimulationService().replay_history(**inputs(vault_, dataset))
    report = build(paired, historical=historical)
    assert report.classification == "INCOMPARABLE"
    assert "MARKET_MISMATCH" in report.reasons
    assert report.scenario.market == "ETH" and report.historical.market == "BTC"
    assert report.historical.source_kind == "SYNTHETIC_FIXTURE"


async def test_declared_gaps_require_separate_segment_evidence(paired):
    _, _, _, vault_ = paired
    dataset = vault_.save(capture(market="SOL", native=False,
        times=(0, 1, 4, 5), gaps=((1, 4, "DISCONNECT"),)))
    historical = await SimulationService().replay_history(**inputs(vault_, dataset))
    assert len(historical.segments) == 2
    report = build(paired, historical=historical, segment_index=1)
    assert report.classification == "INCOMPARABLE"  # ETH scenario versus SOL evidence
    assert report.historical.segment_index == 1
    assert report.historical.replay_segment_count == 2
    assert "HISTORICAL_SEGMENT_RESETS" in report.reasons
    assert report.cross_segment_aggregation_allowed is False
    assert report.historical.window_start == historical.segments[1].frames[0].evaluated_at
    assert report.historical.window_end == historical.segments[1].frames[-1].evaluated_at


async def test_unknown_scenario_time_window_is_not_inferred(paired):
    scenario, captured, _, _ = paired
    no_trace = SimulationConfig(max_frames=4, record_trace=False, trace_max_points=0)
    new_result = await SimulationService().run_scenario(scenario="QUIET", frames=4,
        strategy=captured.strategy, agents=captured.agents,
        risk=captured.risk, simulation=no_trace)
    no_trace_capture = captured.model_copy(update={"simulation": no_trace})
    report = build(paired, scenario=new_result, scenario_inputs=no_trace_capture)
    assert report.scenario.window_status == "UNKNOWN"
    assert report.scenario.window_start is None and report.scenario.window_end is None
    assert "TEMPORAL_ALIGNMENT_UNPROVEN" in report.reasons


async def test_forged_origin_dataset_cannot_be_accepted(paired):
    _, _, historical, _ = paired
    altered = historical.model_copy(update={"request_fingerprint": "0" * 64})
    with pytest.raises(ValidationError):
        build(paired, historical=altered)
