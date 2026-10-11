"""Economic identity excludes processing/publication time and advancing ages."""
from app.simulation.models import stable_fingerprint
from .models import ComparisonProvenance


def provenance(request, observed, metrics):
    snap = observed.snapshot
    semantic = observed.model_dump()
    status = semantic['snapshot']['status']
    for key in ('evaluated_at', 'l2_age_seconds', 'perp_age_seconds', 'metadata_age_seconds',
                'reconnect_count', 'rejected_update_count', 'dropped_update_count', 'last_error_code'):
        status.pop(key, None)
    a = request.research.assumptions
    return ComparisonProvenance(
        comparison_fingerprint=stable_fingerprint({'contract_version': 'phase154-v1', 'market': request.market,
            'research': request.research, 'accepted_observed_evidence': semantic, 'metrics': metrics}),
        observer_instance_id=snap.status.observer_instance_id, connection_generation=snap.status.connection_generation,
        research_frame_timestamp=a.representative_frame_timestamp if a else None,
        l2_source_timestamp=snap.order_book.source_timestamp if snap.order_book else None,
        l2_observed_at=snap.order_book.observed_at if snap.order_book else None,
        perp_observed_at=snap.perp_context.observed_at if snap.perp_context else None)
