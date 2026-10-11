"""Read-only source health. No ReferenceService/consensus/authorization imports."""
from typing import Literal
from datetime import datetime, timezone
from pydantic import AwareDatetime
from app.market_data.live_models import Evidence, LiveMarketId, PositiveDecimal
from app.references.models import (PriceEvidence, ProviderId, ProviderStatus, ReferenceTransport,
    SourceType, TransportQuality)
from app.references.live_provider_mappings import LiveProviderMapping, external_mappings, NATIVE, ROLES


class LiveProviderEvidence(Evidence):
    provider: ProviderId
    role: SourceType
    mapping: LiveProviderMapping
    transport: ReferenceTransport
    transport_quality: TransportQuality | None = None
    enabled: bool
    price: PositiveDecimal | None = None
    source_timestamp: AwareDatetime | None = None
    observed_at: AwareDatetime | None = None
    age_seconds: float | None = None
    status: ProviderStatus
    stale: bool = False
    event_time_verified: bool = False
    source_id: str | None = None
    error: Literal['UNCONFIGURED', 'UNAVAILABLE', 'SOURCE_UNAVAILABLE', 'EVENT_TIME_UNKNOWN'] | None = None
    simulated: Literal[False] = False
    authority: Literal['NONE'] = 'NONE'
    independent_source_group: str
    health_basis: Literal['EXCHANGE_EVENT_TIME', 'RECEIPT_TIME', 'NONE']


class LiveProviderHealth(Evidence):
    contract_version: Literal['phase152-v1'] = 'phase152-v1'
    market: LiveMarketId
    read_only: Literal[True] = True
    authority: Literal['NONE'] = 'NONE'
    providers: tuple[LiveProviderEvidence, ...]
    independent_usable_external_sources: Literal[0] = 0
    consensus_price: Literal[None] = None
    limitations: tuple[str, ...] = (
        'Native mid/oracle/mark and REST/WS are one Hyperliquid source group.',
        'RedStone Live and public HTTP fallback are one provider, not two votes.',
        'External mappings do not inherit operational configuration; collectors remain disabled.',
        'Context rows are DEGRADED when recent because exchange event time is unknown.',
        'No independent temporally usable external evidence; agreement/consensus unavailable.',
        'All rows have authority NONE; health cannot authorize orders.')


def provider_health(snapshot):
    market, status = snapshot.market, snapshot.status
    rows = []
    for provider in NATIVE:
        book = provider == ProviderId.HYPERLIQUID_MID
        value = snapshot.order_book if book else snapshot.perp_context
        available = status.connection_state in {'CONNECTED', 'BOOTSTRAPPING', 'DEGRADED', 'STALE'} and value is not None
        timestamp = value.source_timestamp if available else None
        receipt = value.observed_at if available else None
        age = (status.l2_age_seconds if book else status.perp_age_seconds) if available else None
        fresh = status.l2_freshness if book else status.perp_freshness
        state = 'ERROR' if not available else 'STALE' if fresh != 'FRESH' else 'HEALTHY' if book else 'DEGRADED'
        verified = snapshot.metadata.metadata_status == 'EXCHANGE_VERIFIED' and status.metadata_freshness == 'FRESH'
        if not verified:
            available, timestamp, receipt, age, state = False, None, None, None, 'ERROR'
        mapping = LiveProviderMapping(market=market, provider=provider, native_symbol=market if verified else None,
            expected_source_id=f'hyperliquid:{market}:{provider.value}' if verified else None,
            transport='NATIVE', mapping_status='VALIDATED' if verified else 'UNVERIFIED', enabled=verified,
            last_validated_configuration=snapshot.metadata.observed_at if verified else None)
        price = (value.midpoint if book else value.oracle_price if provider == ProviderId.HYPERLIQUID_ORACLE
                 else value.mark_price) if available else None
        # Reuse the existing evidence validation contract without publishing it into authority.
        evidence = PriceEvidence(market=market, provider=provider, source_type=ROLES[provider], price=price,
            observed_at=receipt or snapshot.metadata.observed_at or datetime.now(timezone.utc),
            source_timestamp=timestamp, status=state, healthy=state == 'HEALTHY', stale=state == 'STALE',
            transport=ReferenceTransport.NATIVE, source_id=mapping.expected_source_id,
            transport_quality=TransportQuality.PRIMARY, simulated=False)
        rows.append(LiveProviderEvidence(provider=provider, role=ROLES[provider], mapping=mapping,
            transport=evidence.transport, transport_quality=evidence.transport_quality, enabled=verified,
            price=price, source_timestamp=timestamp, observed_at=receipt, age_seconds=age,
            status=evidence.status, stale=evidence.stale, event_time_verified=book and timestamp is not None,
            source_id=evidence.source_id, error='SOURCE_UNAVAILABLE' if not available else
                'EVENT_TIME_UNKNOWN' if not book else None,
            independent_source_group='HYPERLIQUID', health_basis='EXCHANGE_EVENT_TIME' if book else 'RECEIPT_TIME'))
    for mapping in external_mappings(market):
        rows.append(LiveProviderEvidence(provider=mapping.provider, role=ROLES[mapping.provider], mapping=mapping,
            transport=mapping.transport, enabled=False, status='DISABLED', error=mapping.mapping_status,
            independent_source_group=mapping.provider.value, health_basis='NONE'))
    return LiveProviderHealth(market=market, providers=tuple(rows))
