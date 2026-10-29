"""Phase 16.1A: immutable historical research evidence, never execution authority.

Import, persistence, licensed-data acquisition and replay execution are NOT part
of this module. These contracts cannot establish exchange access or data rights.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, model_validator

from app.market_data.live_models import (
    Evidence, FinancialDecimal, LiveBookLevel, NonnegativeDecimal, PositiveDecimal,
)
from app.simulation.market_profiles import ResearchPerpMarketId


CONTRACT_VERSION = "phase16-replay-v1"
Fingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")]
SourceKind = Literal["RECORDED_NATIVE", "SYNTHETIC_FIXTURE"]
ObservationKind = Literal["L2", "PERP_CONTEXT"]


class HistoricalSource(Evidence):
    """Source assertion, NOT verified license or authenticated exchange proof."""

    market: ResearchPerpMarketId
    source_kind: SourceKind
    provider: Literal["HYPERLIQUID", "SYNTHETIC"]
    source_id: Identifier
    collection_method: Literal[
        "OFFICIAL_SDK_REST", "OFFICIAL_SDK_WEBSOCKET", "RECORDED_FILE_IMPORT", "SYNTHETIC_GENERATOR"
    ]
    use_attestation: Literal["USER_ASSERTED_PERMITTED_USE", "SYNTHETIC_LOCAL_ONLY"]
    original_dataset_fingerprint: Fingerprint | None = None
    source_authenticated: Literal[False] = False
    licensing_independently_verified: Literal[False] = False

    @model_validator(mode="after")
    def consistent_source(self):
        if self.source_kind == "RECORDED_NATIVE":
            if (self.provider != "HYPERLIQUID" or
                self.collection_method == "SYNTHETIC_GENERATOR" or
                self.use_attestation != "USER_ASSERTED_PERMITTED_USE"):
                raise ValueError("recorded native evidence requires an identified native source and user use attestation")
        elif (self.provider != "SYNTHETIC" or
              self.collection_method != "SYNTHETIC_GENERATOR" or
              self.use_attestation != "SYNTHETIC_LOCAL_ONLY"):
            raise ValueError("synthetic evidence cannot claim a recorded native source")
        return self


class HistoricalBook(Evidence):
    """Accepted L2 levels; no implied trades or queue-position information."""

    bids: tuple[LiveBookLevel, ...] = Field(min_length=1, max_length=20)
    asks: tuple[LiveBookLevel, ...] = Field(min_length=1, max_length=20)
    truncated: StrictBool = False

    @model_validator(mode="after")
    def valid_levels(self):
        if any(a.price <= b.price for a, b in zip(self.bids, self.bids[1:])):
            raise ValueError("bids must be strictly descending")
        if any(a.price >= b.price for a, b in zip(self.asks, self.asks[1:])):
            raise ValueError("asks must be strictly ascending")
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("historical book is crossed or locked")
        return self


class HistoricalPerpContext(Evidence):
    """Only present provider values; no fabricated mid, funding or OI."""

    mark_price: PositiveDecimal | None = None
    oracle_price: PositiveDecimal | None = None
    funding_rate: FinancialDecimal | None = None
    open_interest_base: NonnegativeDecimal | None = None

    @model_validator(mode="after")
    def has_actual_evidence(self):
        if all(getattr(self, field) is None for field in (
            "mark_price", "oracle_price", "funding_rate", "open_interest_base"
        )):
            raise ValueError("perpetual context needs at least one provided value")
        return self


class HistoricalObservation(Evidence):
    """Receipt-ordered component event; source time is independently attributed."""

    market: ResearchPerpMarketId
    sequence: StrictInt = Field(ge=0)
    kind: ObservationKind
    received_at: AwareDatetime
    source_timestamp: AwareDatetime | None = None
    source_event_time_verified: StrictBool = False
    observer_instance_id: Identifier
    connection_generation: StrictInt = Field(ge=0)
    source_sequence: StrictInt | None = Field(default=None, ge=0)
    order_book: HistoricalBook | None = None
    perp_context: HistoricalPerpContext | None = None

    @model_validator(mode="after")
    def component_identity(self):
        if self.kind == "L2":
            if self.order_book is None or self.perp_context is not None:
                raise ValueError("L2 requires book evidence, without perpetual context")
            if self.source_event_time_verified and self.source_timestamp is None:
                raise ValueError("verified L2 event time requires an actual source timestamp")
        elif (self.perp_context is None or self.order_book is not None or
              self.source_timestamp is not None or self.source_event_time_verified):
            # Official activeAssetCtx has no trusted exchange event timestamp.
            raise ValueError("perp context requires receipt time only; event time remains unknown")
        return self


class HistoricalGap(Evidence):
    """Explicit missing receipt-time interval; never interpolated."""

    start_at: AwareDatetime
    end_at: AwareDatetime
    reason: Literal["DISCONNECT", "DROPPED", "OBSERVER_RESTART", "MISSING_SOURCE", "UNKNOWN_COVERAGE"]
    observer_instance_id: Identifier | None = None

    @model_validator(mode="after")
    def positive_gap(self):
        if self.end_at <= self.start_at:
            raise ValueError("historical gap must have positive duration")
        return self


class HistoricalDataset(Evidence):
    """One bounded research dataset, without import/storage/replay side effects."""

    contract_version: Literal["phase16-replay-v1"] = CONTRACT_VERSION
    dataset_id: Identifier
    market: ResearchPerpMarketId
    source: HistoricalSource
    simulated: StrictBool
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"
    observations: tuple[HistoricalObservation, ...] = Field(min_length=2, max_length=5000)
    gaps: tuple[HistoricalGap, ...] = Field(default=(), max_length=1024)
    coverage_start: AwareDatetime
    coverage_end: AwareDatetime
    coverage_status: Literal["PARTIAL", "UNKNOWN"] = "UNKNOWN"
    continuous_history_verified: Literal[False] = False
    dataset_fingerprint: Fingerprint | None = None

    @model_validator(mode="after")
    def consistent_dataset(self):
        if self.source.market != self.market or self.simulated != (self.source.source_kind == "SYNTHETIC_FIXTURE"):
            raise ValueError("historical dataset source/market/simulation identity mismatch")
        if (self.coverage_start != self.observations[0].received_at or
            self.coverage_end != self.observations[-1].received_at or
            self.coverage_end <= self.coverage_start):
            raise ValueError("coverage must equal first/last receipt time; not assert continuity")
        last_sequence, last_received = -1, None
        last_generations: dict[str, int] = {}
        last_book_times: dict[tuple[str, int], datetime] = {}
        for point in self.observations:
            if point.market != self.market or point.sequence <= last_sequence:
                raise ValueError("historical observation market or sequence mismatch")
            if last_received is not None and point.received_at < last_received:
                raise ValueError("receipt times must not move backward")
            generation = last_generations.get(point.observer_instance_id, -1)
            if point.connection_generation < generation:
                raise ValueError("observer generation cannot regress")
            last_generations[point.observer_instance_id] = point.connection_generation
            if point.kind == "L2":
                if point.source_event_time_verified and self.source.source_kind != "RECORDED_NATIVE":
                    raise ValueError("synthetic L2 cannot claim verified exchange event time")
                if point.source_timestamp is not None:
                    key = (point.observer_instance_id, point.connection_generation)
                    previous = last_book_times.get(key)
                    if previous is not None and point.source_timestamp <= previous:
                        raise ValueError("L2 source timestamps must increase within a generation")
                    last_book_times[key] = point.source_timestamp
            last_sequence, last_received = point.sequence, point.received_at
        previous_gap_end = None
        for gap in self.gaps:
            if (gap.start_at < self.coverage_start or gap.end_at > self.coverage_end or
                (previous_gap_end is not None and gap.start_at < previous_gap_end)):
                raise ValueError("gaps must be ordered, bounded and nonoverlapping")
            if any(gap.start_at < x.received_at < gap.end_at for x in self.observations):
                raise ValueError("explicit missing interval contains an accepted observation")
            previous_gap_end = gap.end_at
        from .provenance import dataset_content_fingerprint
        expected = dataset_content_fingerprint(self)
        if self.dataset_fingerprint is not None and self.dataset_fingerprint != expected:
            raise ValueError("historical dataset fingerprint mismatch")
        object.__setattr__(self, "dataset_fingerprint", expected)
        return self
