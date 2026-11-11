"""Phase 16.5B focused native metrics and provenance regression.

Real SimulationService, secure importer/vault, and replay receipts are reused
through the Phase 16.5A.2 integration fixtures. No browser/live trade tests.
"""
from __future__ import annotations

from decimal import Decimal
from copy import deepcopy
import pytest
from pydantic import ValidationError

from app.research_replay.quantitative import (
    METRICS, MetricObservation, MetricRow, QuantitativeComparison,
    compare_quantitative_paper,
)
from app.simulation.models import SimulationResult
from test_phase165a2_integration import pair, vault


@pytest.mark.parametrize("market", ["BTC", "ETH", "SOL"])
async def test_native_bounded_same_market_context_rows(vault, tmp_path, market):
    scenario, historical = await pair(vault, tmp_path, market)
    result = compare_quantitative_paper(
        scenario=scenario, historical=historical, segment_index=0)
    assert result.version == "phase165b-v1"
    assert result.foundation.classification == "CONTEXT_ONLY"
    assert result.display_policy == "DESCRIPTIVE_ONLY"
    assert tuple(row.name for row in result.rows) == tuple(x[0] for x in METRICS)
    assert result.risk_states is not None
    assert result.authority == "NONE" and result.read_only
    assert not result.differences_available
    assert not result.strategy_ranking_allowed
    assert not result.cross_segment_aggregation_allowed
    assert not result.matched_market_evidence_verified
    assert not hasattr(result, "delta") and not hasattr(result, "ranking")
    assert QuantitativeComparison.model_validate_json(result.model_dump_json()) == result
    archived = SimulationResult.model_validate_json(
        historical.segments[0].simulation_result_json)
    for row in result.rows:
        owner = "metrics" if row.scenario.origin == "SIMULATION_METRICS" else "vault"
        left = getattr(getattr(scenario.result, owner), row.name, None)
        right = getattr(getattr(archived, owner), row.name, None)
        assert row.scenario.value == left
        assert row.historical_segment.value == right


async def test_cross_market_is_blocked_without_paired_financial_rows(vault, tmp_path):
    scenario, historical = await pair(vault, tmp_path, "ETH", scenario_market="BTC")
    result = compare_quantitative_paper(
        scenario=scenario, historical=historical, segment_index=0)
    assert result.foundation.classification == "INCOMPARABLE"
    assert "MARKET_MISMATCH" in result.foundation.reasons
    assert result.display_policy == "BLOCKED"
    assert result.rows == ()
    assert result.risk_states is None
    assert QuantitativeComparison.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("kind", ["gap", "generation"])
async def test_receipt_references_one_segment_and_never_pools_capital(vault, tmp_path, kind):
    scenario, historical = await pair(vault, tmp_path, kind=kind)
    assert len(historical.segments) == 2
    reports = [compare_quantitative_paper(
        scenario=scenario, historical=historical, segment_index=index)
        for index in range(len(historical.segments))]
    for index, report in enumerate(reports):
        assert report.selected_segment_index == index
        assert report.foundation.historical.replay_segment_count == 2
        assert report.foundation.historical.segment_index == index
        assert report.foundation.historical.run_fingerprint == historical.segments[index].run_fingerprint
        assert report.cross_segment_aggregation_allowed is False
        assert "HISTORICAL_SEGMENT_RESETS" in report.foundation.reasons
        for row in report.rows:
            if row.name == "starting_equity":
                assert row.historical_segment.value == historical.segments[index].starting_equity
    assert not any(hasattr(report, "combined_return") for report in reports)


@pytest.mark.parametrize("field", ["fees_quote", "funding_quote", "capital_utilization",
                                   "reserved_capital_quote", "gross_exposure_quote"])
async def test_vault_metrics_are_not_recomputed_or_substituted(vault, tmp_path, field):
    scenario, historical = await pair(vault, tmp_path)
    report = compare_quantitative_paper(scenario=scenario, historical=historical, segment_index=0)
    row = next(item for item in report.rows if item.name == field)
    assert row.scenario.origin == "PAPER_VAULT"
    assert row.historical_segment.origin == "PAPER_VAULT"
    assert row.scenario.availability in ("AVAILABLE", "NOT_REPORTED")
    assert row.historical_segment.availability in ("AVAILABLE", "NOT_REPORTED")
    assert row.scenario.availability == ("AVAILABLE" if row.scenario.value is not None else "NOT_REPORTED")


async def test_zero_fills_remains_numeric_zero_not_missing(vault, tmp_path):
    scenario, historical = await pair(vault, tmp_path, kind="complete")
    report = compare_quantitative_paper(scenario=scenario, historical=historical, segment_index=0)
    counts = next(r for r in report.rows if r.name == "fill_count")
    assert counts.historical_segment.value == Decimal(0)
    assert counts.historical_segment.availability == "AVAILABLE"
    assert next(r for r in report.rows if r.name == "fill_activity_ratio").historical_segment.value is None or isinstance(
        next(r for r in report.rows if r.name == "fill_activity_ratio").historical_segment.value, Decimal)


async def test_no_mutation_of_admitted_results_or_operational_state(vault, tmp_path):
    scenario, historical = await pair(vault, tmp_path)
    old = (scenario.model_dump_json(), historical.model_dump_json())
    result = compare_quantitative_paper(scenario=scenario, historical=historical, segment_index=0)
    assert scenario.model_dump_json() == old[0]
    assert historical.model_dump_json() == old[1]
    assert result.foundation.authority == "NONE"


async def test_rejects_tampered_bound_scenario_and_replay(vault, tmp_path):
    scenario, historical = await pair(vault, tmp_path)
    tampered_scenario = scenario.model_copy(update={
        "result": scenario.result.model_copy(update={"run_fingerprint": "f" * 64})
    })
    with pytest.raises((ValueError, ValidationError)):
        compare_quantitative_paper(scenario=tampered_scenario, historical=historical, segment_index=0)
    tampered_replay = historical.model_copy(update={"result_fingerprint": "f" * 64})
    with pytest.raises((ValueError, ValidationError)):
        compare_quantitative_paper(scenario=scenario, historical=tampered_replay, segment_index=0)


@pytest.mark.parametrize("index", [-1, 32, True])
async def test_rejects_invalid_segment_selection(vault, tmp_path, index):
    scenario, historical = await pair(vault, tmp_path)
    with pytest.raises((ValueError, ValidationError)):
        compare_quantitative_paper(scenario=scenario, historical=historical, segment_index=index)


def test_exact_financial_observation_validation():
    with pytest.raises(ValidationError):
        MetricObservation(origin="SIMULATION_METRICS", availability="AVAILABLE", value=1.25)
    with pytest.raises(ValidationError):
        MetricObservation(origin="SIMULATION_METRICS", availability="AVAILABLE", value=Decimal("NaN"))
    with pytest.raises(ValidationError):
        MetricObservation(origin="SIMULATION_METRICS", availability="AVAILABLE")
    with pytest.raises(ValidationError):
        MetricObservation(origin="SIMULATION_METRICS", availability="NOT_REPORTED", value=Decimal("0"))
    valid = MetricObservation(origin="SIMULATION_METRICS", availability="AVAILABLE", value=Decimal("0"))
    assert valid.value == Decimal("0")


async def test_closed_units_and_fingerprint_tamper(vault, tmp_path):
    scenario, historical = await pair(vault, tmp_path)
    original = compare_quantitative_paper(scenario=scenario, historical=historical, segment_index=0)
    wrong = original.model_copy(update={"receipt_fingerprint": "0" * 64})
    with pytest.raises(ValidationError, match="fingerprint"):
        QuantitativeComparison.model_validate_json(wrong.model_dump_json())
    first = original.rows[0].model_copy(update={"unit": "quote"})
    with pytest.raises(ValidationError, match="unit/source"):
        MetricRow.model_validate_json(first.model_dump_json())
    wrong = original.model_copy(update={"rows": original.rows[1:]})
    with pytest.raises(ValidationError):
        QuantitativeComparison.model_validate_json(wrong.model_dump_json())


async def test_research_configuration_mismatch_stays_context_only(vault, tmp_path):
    from app.risk.firewall import RiskFirewallConfig
    scenario, historical = await pair(vault, tmp_path, risk=RiskFirewallConfig(enabled=False))
    report = compare_quantitative_paper(scenario=scenario, historical=historical, segment_index=0)
    assert report.display_policy == "DESCRIPTIVE_ONLY"
    assert "RISK_MISMATCH" in report.foundation.reasons
    assert report.differences_available is False
