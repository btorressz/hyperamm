"""Phase 16.1A deterministic source/dataset fingerprints and explicit trust limits."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictInt

from app.market_data.live_models import Evidence
from .models import HistoricalDataset, Fingerprint, SourceKind


def _fingerprint(value) -> str:
    # Reuse the established Phase 10/14/15 SHA-256 canonicalization rules.
    # Lazy import avoids coupling historical contracts to simulation engine startup.
    from app.simulation.models import stable_fingerprint
    return stable_fingerprint(value)


def dataset_content_fingerprint(dataset: HistoricalDataset) -> str:
    """No import time, filesystem path, processing clock or self-referential hash."""
    return _fingerprint(dataset.model_dump(exclude={"dataset_fingerprint"}))


class HistoricalDatasetProvenance(Evidence):
    contract_version: Literal["phase16-replay-v1"] = "phase16-replay-v1"
    dataset_fingerprint: Fingerprint
    source_fingerprint: Fingerprint
    observations_fingerprint: Fingerprint
    gaps_fingerprint: Fingerprint
    source_kind: SourceKind
    source_authenticated: Literal[False] = False
    licensing_independently_verified: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"
    source_event_time_policy: Literal[
        "RECORDED_L2_VERIFIED_CONTEXT_RECEIPT_ONLY",
        "RECORDED_L2_UNVERIFIED_OR_MISSING",
        "SYNTHETIC_TIMES_NOT_EXCHANGE_VERIFIED",
    ]
    observation_count: StrictInt = Field(ge=2, le=5000)
    l2_count: StrictInt = Field(ge=0, le=5000)
    verified_l2_event_time_count: StrictInt = Field(ge=0, le=5000)
    perp_context_count: StrictInt = Field(ge=0, le=5000)
    gap_count: StrictInt = Field(ge=0, le=1024)
    limitations: tuple[str, ...] = (
        "Recorded-source and permitted-use labels are user assertions, not verified license or exchange authentication.",
        "Receipt coverage and explicit gaps never establish continuous historical market delivery.",
        "Order-book snapshots do not prove queue position, intermediate trades or actual passive fills.",
        "Perpetual-context event time is unknown; no synthetic external provider history is implied.",
        "Research evidence has no order, capital, reference-consensus or strategy authority.",
    )


def describe_provenance(dataset: HistoricalDataset) -> HistoricalDatasetProvenance:
    """Produce reproducible component identities from validated immutable evidence."""
    return HistoricalDatasetProvenance(
        dataset_fingerprint=dataset_content_fingerprint(dataset),
        source_fingerprint=_fingerprint(dataset.source),
        observations_fingerprint=_fingerprint(dataset.observations),
        gaps_fingerprint=_fingerprint(dataset.gaps),
        source_kind=dataset.source.source_kind,
        source_event_time_policy=(
            "SYNTHETIC_TIMES_NOT_EXCHANGE_VERIFIED"
            if dataset.source.source_kind == "SYNTHETIC_FIXTURE"
            else "RECORDED_L2_VERIFIED_CONTEXT_RECEIPT_ONLY"
            if all(p.source_event_time_verified for p in dataset.observations if p.kind == "L2")
            else "RECORDED_L2_UNVERIFIED_OR_MISSING"
        ),
        observation_count=len(dataset.observations),
        l2_count=sum(p.kind == "L2" for p in dataset.observations),
        verified_l2_event_time_count=sum(
            p.kind == "L2" and p.source_event_time_verified for p in dataset.observations
        ),
        perp_context_count=sum(p.kind == "PERP_CONTEXT" for p in dataset.observations),
        gap_count=len(dataset.gaps),
    )
