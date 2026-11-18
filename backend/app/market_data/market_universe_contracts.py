"""Versioned read-only Hyperliquid perpetual market-universe contracts."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, ConfigDict, FailFast, Field, field_validator, model_validator

from app.market_data.live_models import Evidence

CONTRACT_VERSION = "phase180b-v2"
MAX_CATALOG_RECORDS = 4096
InstrumentType = Literal["CORE_PERP", "HIP3_PERP"]
Network = Literal["MAINNET", "TESTNET"]
MetadataStatus = Literal["EXCHANGE_VERIFIED", "DEMO_PROFILE", "STALE", "UNAVAILABLE", "ERROR"]
MetadataSource = Literal["OFFICIAL_SDK_CORE_META", "OFFICIAL_SDK_HIP3_META",
                         "PINNED_RESEARCH_FIXTURE", "NONE"]
DiscoveryReason = Literal["DISCOVERABLE", "UNVERIFIED_METADATA", "NOT_LISTED",
                          "MISSING_METADATA", "METADATA_ERROR", "FUTURE_TIMESTAMP", "STALE_METADATA"]


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    try:
        return value.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ValueError("timestamp outside supported UTC range") from exc


def _strict_bool(value: object) -> bool:
    # Literal[True/False] alone also accepts the equivalent integers.
    if type(value) is not bool:
        raise ValueError("authority flags require boolean values")
    return value


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_utc)]


class MarketUniverseEvidence(Evidence):
    model_config = ConfigDict(strict=True, revalidate_instances="always", validate_default=True)

    contract_version: Literal["phase180b-v2"] = CONTRACT_VERSION


class MarketInstrumentIdentity(MarketUniverseEvidence):
    """Market identity combines the network, perpetual class, namespace and unqualified name."""

    venue: Literal["HYPERLIQUID"] = "HYPERLIQUID"
    network: Network
    instrument_type: InstrumentType
    dex: str = Field(max_length=32)
    instrument_name: str = Field(max_length=64)

    @model_validator(mode="after")
    def validate_namespace(self):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", self.instrument_name):
            raise ValueError("invalid unqualified instrument name")
        if self.instrument_type == "CORE_PERP":
            if self.dex != "":
                raise ValueError("Core perpetual identity requires the empty DEX namespace")
        elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", self.dex):
            raise ValueError("HIP-3 identity requires an explicit DEX namespace")
        return self

    @property
    def stable_key(self) -> str:
        return f"{self.venue}:{self.network}:{self.instrument_type}:{self.dex}:{self.instrument_name}"

    @property
    def exchange_coin(self) -> str:
        return f"{self.dex}:{self.instrument_name}" if self.dex else self.instrument_name


class MarketUniverseMetadata(MarketUniverseEvidence):
    """Captured perpetual metadata and its declared provenance."""

    identity: MarketInstrumentIdentity
    source_coin: str | None = Field(default=None, max_length=97)
    universe_index: int | None = Field(default=None, ge=0, lt=10_000)
    sz_decimals: int | None = Field(default=None, ge=0, le=6)
    listed: bool | None = None
    metadata_status: MetadataStatus
    metadata_source: MetadataSource
    observed_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def validate_provenance(self):
        official = ("OFFICIAL_SDK_CORE_META" if self.identity.instrument_type == "CORE_PERP"
                    else "OFFICIAL_SDK_HIP3_META")
        if self.metadata_source.startswith("OFFICIAL_SDK_") and self.metadata_source != official:
            raise ValueError("metadata source and DEX instrument class disagree")

        if self.metadata_status in {"EXCHANGE_VERIFIED", "STALE"}:
            if (self.metadata_source != official or self.source_coin is None or
                    self.observed_at is None or self.universe_index is None or
                    self.sz_decimals is None or self.listed is None):
                raise ValueError("verified or stale metadata needs complete matching official evidence")
            if self.source_coin != self.identity.exchange_coin:
                raise ValueError("source coin does not match canonical market identity")
            return self

        fixture = self.metadata_status == "DEMO_PROFILE"
        if fixture != (self.metadata_source == "PINNED_RESEARCH_FIXTURE"):
            raise ValueError("demo status and fixture provenance must agree")
        if (self.source_coin is not None or self.universe_index is not None or
                self.listed is not None or self.observed_at is not None or
                (not fixture and self.sz_decimals is not None)):
            raise ValueError("fixture or missing metadata cannot claim an exchange observation")
        return self

    def fingerprint(self) -> str:
        from app.simulation.models import stable_fingerprint

        checked = MarketUniverseMetadata.model_validate(self)
        return stable_fingerprint(checked.model_dump(mode="json"))


class MarketUniverseCatalog(MarketUniverseEvidence):
    """Bounded snapshot with deterministic record order."""

    records: Annotated[tuple[MarketUniverseMetadata, ...], FailFast()] = Field(
        default=(), max_length=MAX_CATALOG_RECORDS
    )
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    _validate_flags = field_validator("read_only", mode="before")(_strict_bool)

    @field_validator("records")
    @classmethod
    def canonical_records(cls, records):
        identities: set[str] = set()
        indices: set[tuple[str, str, str, int]] = set()
        for record in records:
            identity = record.identity
            if identity.stable_key in identities:
                raise ValueError("duplicate canonical market identity")
            identities.add(identity.stable_key)
            if record.universe_index is not None:
                index_key = (identity.network, identity.instrument_type, identity.dex, record.universe_index)
                if index_key in indices:
                    raise ValueError("duplicate universe index in network and DEX namespace")
                indices.add(index_key)
        return tuple(sorted(records, key=lambda item: item.identity.stable_key))

    def fingerprint(self) -> str:
        from app.simulation.models import stable_fingerprint

        checked = MarketUniverseCatalog.model_validate(self)
        return stable_fingerprint(checked.model_dump(mode="json"))


class DiscoveryEligibility(MarketUniverseEvidence):
    """Read-only discovery decision with permanently disabled trading eligibility."""

    identity: MarketInstrumentIdentity
    metadata_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    evaluated_at: UtcDatetime
    discovery_eligible: bool
    reason: DiscoveryReason
    paper_research_eligible: Literal[False] = False
    execution_eligible: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    _validate_flags = field_validator(
        "paper_research_eligible", "execution_eligible", "read_only", mode="before"
    )(_strict_bool)

    @model_validator(mode="after")
    def consistency(self):
        if self.discovery_eligible != (self.reason == "DISCOVERABLE"):
            raise ValueError("discovery eligibility conflicts with reason")
        return self

    def validate_against(self, metadata: MarketUniverseMetadata, *,
                         evaluated_at: datetime, max_age_seconds: int) -> DiscoveryEligibility:
        """Verify a detached decision against trusted metadata, clock and freshness budget."""
        checked = DiscoveryEligibility.model_validate(self)
        expected = evaluate_discovery(metadata, evaluated_at=evaluated_at, max_age_seconds=max_age_seconds)
        if checked != expected:
            raise ValueError("discovery decision does not match metadata and evaluation")
        return checked


def evaluate_discovery(metadata: MarketUniverseMetadata, *,
                       evaluated_at: datetime, max_age_seconds: int) -> DiscoveryEligibility:
    """Project validated metadata into a read-only discovery decision."""
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 86400:
        raise ValueError("invalid discovery metadata freshness budget")
    evaluated_at = _utc(evaluated_at)
    metadata = MarketUniverseMetadata.model_validate(metadata)
    status = metadata.metadata_status
    reason: DiscoveryReason
    if status == "DEMO_PROFILE":
        reason = "UNVERIFIED_METADATA"
    elif status == "UNAVAILABLE":
        reason = "MISSING_METADATA"
    elif status == "ERROR":
        reason = "METADATA_ERROR"
    elif metadata.listed is False:
        reason = "NOT_LISTED"
    else:
        # Complete official observations always have an observation timestamp.
        age = (evaluated_at - metadata.observed_at).total_seconds()
        if age < 0:
            reason = "FUTURE_TIMESTAMP"
        elif status == "STALE" or age > max_age_seconds:
            reason = "STALE_METADATA"
        else:
            reason = "DISCOVERABLE"

    return DiscoveryEligibility(identity=metadata.identity, metadata_fingerprint=metadata.fingerprint(),
                                evaluated_at=evaluated_at, discovery_eligible=reason == "DISCOVERABLE",
                                reason=reason)
