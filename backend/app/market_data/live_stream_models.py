"""Additive phase152-v1 contracts; phase151-v1 REST remains unchanged."""
from typing import Literal
from pydantic import AwareDatetime, Field, StrictInt, model_validator
from app.market_data.live_models import (Evidence, LiveMarketId, LiveMarketMetadata,
    LiveBookObservation, LivePerpObservation, LiveObservationStatus, PositiveDecimal, FinancialDecimal)

ConnectionState = Literal['DISABLED', 'CONNECTING', 'BOOTSTRAPPING', 'CONNECTED',
    'DEGRADED', 'STALE', 'RECONNECTING', 'UNAVAILABLE', 'STOPPED']
Freshness = Literal['FRESH', 'STALE', 'UNAVAILABLE']


class StreamBookObservation(LiveBookObservation):
    source: Literal['OFFICIAL_SDK_REST', 'OFFICIAL_SDK_WEBSOCKET']


class StreamPerpObservation(LivePerpObservation):
    source: Literal['OFFICIAL_SDK_REST', 'OFFICIAL_SDK_WEBSOCKET']
    # activeAssetCtx supplies no documented trusted event timestamp.
    event_time_verified: Literal[False] = False


class LiveMarketStreamStatus(Evidence):
    contract_version: Literal['phase152-v1'] = 'phase152-v1'
    market: LiveMarketId
    transport: Literal['OFFICIAL_SDK_WEBSOCKET'] = 'OFFICIAL_SDK_WEBSOCKET'
    # Additive HTTP/WS resynchronization and local age-projection boundary.
    observer_instance_id: str
    evaluated_at: AwareDatetime
    l2_stale_after_seconds: float = Field(default=10, gt=0, le=300, allow_inf_nan=False)
    perp_stale_after_seconds: float = Field(default=30, gt=0, le=300, allow_inf_nan=False)
    metadata_stale_after_seconds: float = Field(default=300, gt=0, le=3600, allow_inf_nan=False)
    connection_state: ConnectionState
    subscription_state: Literal['NONE', 'REQUESTED', 'OBSERVED', 'RETIRED']
    connection_generation: StrictInt = Field(ge=0)
    last_l2_source_timestamp: AwareDatetime | None = None
    last_l2_observed_at: AwareDatetime | None = None
    last_perp_observed_at: AwareDatetime | None = None
    l2_age_seconds: float | None = None
    perp_age_seconds: float | None = None
    metadata_age_seconds: float | None = None
    l2_freshness: Freshness = 'UNAVAILABLE'
    perp_freshness: Freshness = 'UNAVAILABLE'
    metadata_freshness: Freshness = 'UNAVAILABLE'
    perp_event_time: Literal['UNKNOWN'] = 'UNKNOWN'
    reconnect_count: StrictInt = Field(default=0, ge=0)
    rejected_update_count: StrictInt = Field(default=0, ge=0)
    dropped_update_count: StrictInt = Field(default=0, ge=0)
    last_error_code: Literal['INVALID_DATA', 'REPLAY', 'CONFLICT', 'OVERFLOW', 'TIMEOUT',
        'NETWORK_ERROR', 'RATE_LIMITED', 'FORBIDDEN', 'SDK_UNAVAILABLE', 'UPSTREAM_ERROR',
        'CLEANUP_ERROR', 'NOT_LISTED'] | None = None
    simulated: Literal[False] = False
    read_only: Literal[True] = True


class LiveStreamSnapshot(Evidence):
    market: LiveMarketId
    status: LiveMarketStreamStatus
    observation_status: LiveObservationStatus
    metadata: LiveMarketMetadata
    order_book: StreamBookObservation | None = None
    perp_context: StreamPerpObservation | None = None
    limitations: tuple[str, ...] = (
        'One Hyperliquid venue; no independent reference quorum or trading authority.',
        'Context receipt freshness does not verify economic event time.',
        'Book and context are independent acquisitions, not an atomic economic snapshot.')

    @model_validator(mode='after')
    def identities(self):
        if any(x is not None and x.market != self.market for x in
               (self.status, self.metadata, self.order_book, self.perp_context)):
            raise ValueError('mixed stream market identities')
        if self.observation_status == 'AVAILABLE' and (self.order_book is None or
            self.perp_context is None or self.status.connection_state != 'CONNECTED' or
            any(x != 'FRESH' for x in (self.status.l2_freshness,
                self.status.perp_freshness, self.status.metadata_freshness))):
            raise ValueError('available stream requires current complete evidence')
        return self


class LiveMarketStreamEnvelope(Evidence):
    contract_version: Literal['phase152-v1'] = 'phase152-v1'
    market: LiveMarketId
    observer_instance_id: str
    connection_generation: StrictInt = Field(ge=0)
    sequence: StrictInt = Field(ge=1)
    emitted_at: AwareDatetime
    observation_status: LiveObservationStatus
    payload: LiveStreamSnapshot

    @model_validator(mode='after')
    def identities(self):
        if (self.market != self.payload.market or self.connection_generation != self.payload.status.connection_generation
                or self.observer_instance_id != self.payload.status.observer_instance_id):
            raise ValueError('mixed envelope identity')
        if self.observation_status != self.payload.observation_status:
            raise ValueError('mixed envelope availability')
        return self


class LiveHistoryPoint(Evidence):
    market: LiveMarketId
    observer_instance_id: str
    connection_generation: StrictInt = Field(ge=1)
    kind: Literal['L2', 'PERP_CONTEXT']
    source: Literal['OFFICIAL_SDK_REST', 'OFFICIAL_SDK_WEBSOCKET']
    source_timestamp: AwareDatetime | None
    observed_at: AwareDatetime
    midpoint: PositiveDecimal | None = None
    best_bid: PositiveDecimal | None = None
    best_ask: PositiveDecimal | None = None
    spread: PositiveDecimal | None = None
    mark: PositiveDecimal | None = None
    oracle: PositiveDecimal | None = None
    funding: FinancialDecimal | None = None
    open_interest: FinancialDecimal | None = None
    observation_status: LiveObservationStatus


class LiveMarketHistory(Evidence):
    contract_version: Literal['phase152-v1'] = 'phase152-v1'
    market: LiveMarketId
    observer_instance_id: str
    read_only: Literal[True] = True
    simulated: Literal[False] = False
    points: tuple[LiveHistoryPoint, ...]
    coverage_start: AwareDatetime | None
    coverage_end: AwareDatetime | None
    retained_point_count: StrictInt = Field(ge=0)
    evicted_point_count: StrictInt = Field(ge=0)
    gap_count: StrictInt = Field(ge=0)
    max_points: StrictInt = Field(ge=1, le=3600)
    continuous_history_verified: Literal[False] = False
    limitations: tuple[str, ...] = (
        'In-memory accepted observations only; no interpolation or persistence.',
        'Each point records only its arriving component; other financial values remain null.',
        'Coverage is the retained receipt range; context source event time is unknown.',
        'Generation changes and feed loss create gaps; coverage does not prove continuous delivery.')
