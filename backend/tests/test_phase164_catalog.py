"""Phase 16.4 read-only summary regression without raw book disclosure."""
import asyncio

import pytest

from app.research_replay.runner import summaries
from app.research_replay.storage import HistoricalStorage, StorageError
from app.research_replay.summary import HistoricalDatasetSummary
from app.simulation.executor import SimulationExecutor
from test_phase162_replay import capture


def test_historical_summary_catalog_exact_identity_and_no_economics(tmp_path):
    root = tmp_path / "replay"
    root.mkdir(mode=0o700)
    vault = HistoricalStorage(root)
    btc = vault.save(capture(market="BTC", native=True))
    sol = vault.save(capture(market="SOL", native=False))
    rows = summaries(root)
    assert tuple(row.dataset_id for row in rows) == tuple(sorted((btc.dataset_id, sol.dataset_id)))
    for row in rows:
        assert isinstance(row, HistoricalDatasetSummary)
        original = vault.read(row.dataset_id)
        assert row.dataset_fingerprint == original.dataset_fingerprint
        assert row.market == original.market
        assert row.coverage_start == original.coverage_start
        assert row.coverage_end == original.coverage_end
        assert row.observation_count == len(original.observations)
        assert row.gap_count == len(original.gaps)
        assert row.authority == "NONE" and row.read_only
        assert row.source_authenticated is False
        assert row.licensing_independently_verified is False
        assert row.continuous_history_verified is False
        assert not {"observations", "order_book", "perp_context", "funding_rate", "source_id"} & set(row.model_dump())


@pytest.mark.asyncio
async def test_catalog_uses_existing_single_research_executor(tmp_path):
    root = tmp_path / "replay"
    root.mkdir(mode=0o700)
    stored = HistoricalStorage(root).save(capture())
    executor = SimulationExecutor()
    try:
        rows = await executor.execute("historical_summaries", storage_root=str(root))
        assert len(rows) == 1 and rows[0].dataset_fingerprint == stored.dataset_fingerprint
    finally:
        await executor.shutdown()


def test_catalog_fails_closed_for_unsafe_or_corrupt_storage(tmp_path):
    root = tmp_path / "replay"
    root.mkdir(mode=0o700)
    vault = HistoricalStorage(root)
    dataset = vault.save(capture())
    root.chmod(0o755)
    with pytest.raises(StorageError):
        summaries(root)
    root.chmod(0o700)
    path = next(root.glob("*.json"))
    path.write_bytes(b"{}")
    with pytest.raises(ValueError):
        summaries(root)
