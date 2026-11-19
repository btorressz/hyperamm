"""Source binding for independently invoked, server-owned research evaluators."""
from datetime import datetime, timedelta
from decimal import localcontext
from typing import Iterable

from app.market_data.market_universe_contracts import (
    MarketUniverseMetadata,
    _utc,
    evaluate_discovery,
)
from app.simulation.models import stable_fingerprint

from .advisory_contracts import ANALYSIS_VERSION, AdvisoryContext, AdvisorySourceEvidence


class AdvisoryBindingError(ValueError):
    """A captured value disagrees with the server's context or provenance."""


def captured_source(*, metadata: MarketUniverseMetadata, value, **fields) -> AdvisorySourceEvidence:
    """Bind content, market generation and source envelope to a distinct digest."""
    unsealed = {
        "identity": metadata.identity, "binding_version": ANALYSIS_VERSION,
        **fields,
    }
    digest = stable_fingerprint({
        "metadata": metadata,
        "value": value,
        "source": unsealed,
    })
    return AdvisorySourceEvidence(**unsealed, source_fingerprint=digest)


def discovery_source(metadata: MarketUniverseMetadata) -> AdvisorySourceEvidence:
    metadata = MarketUniverseMetadata.model_validate(metadata)
    if metadata.metadata_status != "EXCHANGE_VERIFIED":
        raise AdvisoryBindingError("discovery source requires verified metadata")
    return captured_source(
        metadata=metadata, value=metadata, category="MARKET_METADATA",
        provenance="EXCHANGE_OBSERVED", source_id=metadata.metadata_source,
        captured_at=metadata.observed_at, observation_clock="LOCAL_RECEIPT",
        limitations=("Discovery timestamp is the metadata acquisition time.",),
    )


class AdvisoryEvaluation:
    """Validate the context and consume only exact captured source references."""

    def __init__(self, context: AdvisoryContext, *, as_of: datetime, max_metadata_age_seconds: int):
        self.context = AdvisoryContext.model_validate(context)
        self.as_of = _utc(as_of)
        if self.as_of < self.context.evaluated_at:
            raise AdvisoryBindingError("advisory evaluation clock precedes context capture")
        self.discovery = evaluate_discovery(
            self.context.metadata, evaluated_at=self.as_of, max_age_seconds=max_metadata_age_seconds,
        )
        self._context_sources = {source.source_fingerprint: source for source in self.context.sources}
        self.sources: list[AdvisorySourceEvidence] = []

    @property
    def market_issue(self):
        reason = self.discovery.reason
        if self.context.metadata.observed_at is not None and (
            self.context.metadata.observed_at > self.context.evaluated_at
        ):
            return "ERROR", "Market metadata was captured after the context."
        if reason == "NOT_LISTED":
            return "UNSUPPORTED", "Market is delisted."
        if reason == "STALE_METADATA":
            return "STALE", "Market metadata is stale."
        if reason == "METADATA_ERROR":
            return "ERROR", "Market metadata acquisition failed."
        if reason != "DISCOVERABLE" or self.context.metadata.sz_decimals is None:
            return "INSUFFICIENT_DATA", "Verified listing and size precision are required."
        if self.context.valid_until is None:
            return "INSUFFICIENT_DATA", "A bounded research evidence lifetime is required."
        if self.as_of >= self.context.valid_until:
            return "STALE", "Research evidence has expired."
        return None

    def bind(self, sources: Iterable[AdvisorySourceEvidence], *, contribute: bool = True) -> bool:
        selected = tuple(sources)
        for source in selected:
            if self._context_sources.get(source.source_fingerprint) != source:
                raise AdvisoryBindingError(f"{source.category} does not match captured context evidence")
        if any(source.valid_until is not None and self.as_of >= source.valid_until for source in selected):
            return False
        if contribute:
            self.sources.extend(source for source in selected if source not in self.sources)
        return True

    def fields(self):
        classes = {source.provenance for source in self.sources}
        provenance = ("MIXED" if len(classes) > 1 else next(iter(classes), "UNAVAILABLE"))
        return dict(
            identity=self.context.identity, context_fingerprint=self.context.fingerprint(),
            evaluated_at=self.context.evaluated_at, provenance=provenance,
            analysis_version=ANALYSIS_VERSION,
            source_fingerprints=tuple(sorted(source.source_fingerprint for source in self.sources)),
        )


def capture_context(
    metadata: MarketUniverseMetadata, *, evaluated_at: datetime, valid_until: datetime,
    sources: Iterable[AdvisorySourceEvidence] = (), catalog_fingerprint: str | None = None,
    risk_model_fingerprint: str | None = None, paper_binding_fingerprint: str | None = None,
    max_metadata_age_seconds: int = 60,
) -> AdvisoryContext:
    """Construct a context from backend captures for the later observational coordinator."""
    metadata = MarketUniverseMetadata.model_validate(metadata)
    evaluate_discovery(metadata, evaluated_at=evaluated_at, max_age_seconds=max_metadata_age_seconds)
    expiry = _utc(valid_until)
    selected = list(sources)
    if metadata.observed_at is not None:
        expiry = min(expiry, metadata.observed_at + timedelta(seconds=max_metadata_age_seconds))
    if metadata.metadata_status == "EXCHANGE_VERIFIED":
        selected.append(discovery_source(metadata))
    return AdvisoryContext(
        metadata=metadata, metadata_fingerprint=metadata.fingerprint(), evaluated_at=evaluated_at,
        valid_until=expiry if expiry > _utc(evaluated_at) else None,
        sources=tuple(sorted(selected, key=lambda source: (source.category, source.source_id, source.provenance))),
        catalog_fingerprint=catalog_fingerprint, risk_model_fingerprint=risk_model_fingerprint,
        paper_binding_fingerprint=paper_binding_fingerprint,
    )


def captured_paper_scenario(paper):
    """Resolve the generalized run's deterministic source frames by digest."""
    from app.simulation.generalized_market_profiles import DECIMAL_CONTEXT, _build_scenario

    with localcontext(DECIMAL_CONTEXT):
        prepared = _build_scenario(paper.proposal, paper.admission.profile)
    if (prepared.dataset.fingerprint != paper.result.dataset_fingerprint
            or len(prepared.dataset.frames) != paper.result.metrics.frame_count):
        raise AdvisoryBindingError("PAPER scenario does not match the captured run")
    return prepared
