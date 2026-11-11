"""Phase 16.6A: verify serialization optimization changes no receipt/economics.

Uses actual Phase 16.5A/C fixture-backed engine outputs, not mock summaries.
"""
from __future__ import annotations

import json

import pytest

from app.research_replay.contracts import HistoricalReplayResult
from app.research_replay.runner import archive_wire_and_fingerprint, canonical_json
from app.simulation.models import SimulationResult, stable_fingerprint
from test_phase165a2_integration import pair, vault


@pytest.mark.parametrize("market", ["BTC", "ETH", "SOL"])
@pytest.mark.parametrize("modeled", [False, True])
async def test_archive_bytes_and_fingerprints_preserve_legacy_behavior(
    vault, tmp_path, market, modeled,
):
    scenario, historical = await pair(vault, tmp_path, market=market, modeled=modeled)
    original = historical.model_dump_json()
    assert historical.segments
    for segment in historical.segments:
        for archive_field, fingerprint_field in (
            ("simulation_result_json", "simulation_result_fingerprint"),
            ("baseline_result_json", "baseline_result_fingerprint"),
        ):
            wire = getattr(segment, archive_field)
            if wire is None:
                assert getattr(segment, fingerprint_field) is None
                continue
            result = SimulationResult.model_validate_json(wire)
            new_wire, new_hash = archive_wire_and_fingerprint(result)
            # This is intentionally the old double-serialization baseline,
            # retained in tests and not as a production hot-path fallback.
            legacy_wire = canonical_json(result)
            legacy_hash = stable_fingerprint(json.loads(legacy_wire))
            assert new_wire == legacy_wire == wire
            assert new_hash == legacy_hash == getattr(segment, fingerprint_field)
            assert (result.model_dump_json(), result.run_fingerprint) == (
                SimulationResult.model_validate_json(new_wire).model_dump_json(),
                result.run_fingerprint,
            )
    assert historical.model_dump_json() == original
    assert HistoricalReplayResult.model_validate_json(original) == historical
    assert scenario.result.simulated and historical.simulated
    assert not historical.authority or historical.authority == "NONE"


def test_archive_uses_one_json_payload_without_mutating_typed_source():
    from app.simulation.config import SimulationConfig
    from app.simulation.models import stable_fingerprint
    # A real immutable nested configuration checks decimal/exponent handling,
    # key ordering and JSON-mode materialization without needing a venue.
    cfg = SimulationConfig()
    before = cfg.model_dump_json()
    # The optimized function is intended for actual SimulationResult only;
    # compare the canonicalization primitives on this simpler typed model.
    payload = cfg.model_dump(mode="json")
    assert stable_fingerprint(payload) == stable_fingerprint(json.loads(canonical_json(cfg)))
    assert cfg.model_dump_json() == before
