"""Bounded read-only Phase 16.4 dataset summaries; no new storage authority."""
from __future__ import annotations

from typing import Literal
from pydantic import AwareDatetime, Field, StrictInt

from app.market_data.live_models import Evidence
from app.simulation.market_profiles import ResearchPerpMarketId
from .models import Fingerprint, HistoricalDataset, Identifier, SourceKind


class HistoricalDatasetSummary(Evidence):
    contract_version: Literal["phase16-replay-v1"] = "phase16-replay-v1"
    dataset_id: Identifier
    dataset_fingerprint: Fingerprint
    market: ResearchPerpMarketId
    source_kind: SourceKind
    coverage_start: AwareDatetime
    coverage_end: AwareDatetime
    coverage_status: Literal["PARTIAL", "UNKNOWN"]
    observation_count: StrictInt = Field(ge=2, le=5000)
    gap_count: StrictInt = Field(ge=0, le=1024)
    source_authenticated: Literal[False] = False
    licensing_independently_verified: Literal[False] = False
    continuous_history_verified: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    @classmethod
    def from_dataset(cls, dataset: HistoricalDataset) -> "HistoricalDatasetSummary":
        return cls(
            dataset_id=dataset.dataset_id,
            dataset_fingerprint=dataset.dataset_fingerprint,
            market=dataset.market,
            source_kind=dataset.source.source_kind,
            coverage_start=dataset.coverage_start,
            coverage_end=dataset.coverage_end,
            coverage_status=dataset.coverage_status,
            observation_count=len(dataset.observations),
            gap_count=len(dataset.gaps),
        )
