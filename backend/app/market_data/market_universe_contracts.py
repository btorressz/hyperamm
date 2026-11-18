"""Phase 18.0A additive Hyperliquid market-universe contracts.

These are non-authoritative, read-only representations. They do not extend
Phase 14-17 research market allowlists or the guarded TESTNET adapter.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, field_validator, model_validator

from app.market_data.live_models import Evidence

CONTRACT_VERSION = "phase180a-v1"
InstrumentType = Literal["CORE_PERP", "HIP3_PERP"]
MetadataStatus = Literal["EXCHANGE_VERIFIED", "DEMO_PROFILE", "STALE", "UNAVAILABLE", "ERROR"]
MetadataSource = Literal["OFFICIAL_SDK_CORE_META", "OFFICIAL_SDK_HIP3_META",
                         "PINNED_RESEARCH_FIXTURE", "NONE"]
DiscoveryReason = Literal["DISCOVERABLE", "UNVERIFIED_METADATA", "NOT_LISTED",
                          "MISSING_TIMESTAMP", "FUTURE_TIMESTAMP", "STALE_METADATA"]


class MarketInstrumentIdentity(Evidence):
    """Identity is namespace + instrument, never an inferred SDK asset index."""

    contract_version: Literal["phase180a-v1"] = CONTRACT_VERSION
    venue: Literal["HYPERLIQUID"] = "HYPERLIQUID"
    instrument_type: InstrumentType
    dex: str
    instrument_name: str

    @model_validator(mode="after")
    def validate_namespace(self):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", self.instrument_name):
            raise ValueError("invalid unqualified instrument name")
        if self.instrument_type == "CORE_PERP":
            if self.dex != "":
                raise ValueError("Core perpetual identity requires the empty DEX namespace")
        elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}", self.dex):
            raise ValueError("HIP-3 identity requires an explicit DEX namespace")
        return self

    @property
    def stable_key(self) -> str:
        # Delimiter characters are forbidden in dex/instrument_name.
        return f"{self.venue}:{self.instrument_type}:{self.dex}:{self.instrument_name}"


class MarketUniverseMetadata(Evidence):
    """Captured metadata; an official observation is not trading permission."""

    contract_version: Literal["phase180a-v1"] = CONTRACT_VERSION
    identity: MarketInstrumentIdentity
    asset_index: StrictInt | None = Field(default=None, ge=0)
    sz_decimals: StrictInt | None = Field(default=None, ge=0, le=18)
    listed: StrictBool | None = None
    metadata_status: MetadataStatus
    metadata_source: MetadataSource
    observed_at: AwareDatetime | None = None

    @field_validator("observed_at")
    @classmethod
    def normalize_timestamp(cls, value):
        return value.astimezone(timezone.utc) if value is not None else None

    @model_validator(mode="after")
    def verified_evidence(self):
        official = ("OFFICIAL_SDK_CORE_META" if self.identity.instrument_type == "CORE_PERP"
                    else "OFFICIAL_SDK_HIP3_META")
        if self.metadata_source.startswith("OFFICIAL_SDK_") and self.metadata_source != official:
            raise ValueError("metadata source and DEX instrument class disagree")
        if self.metadata_status == "EXCHANGE_VERIFIED" and (
            self.metadata_source != official or self.observed_at is None or
            self.asset_index is None or self.sz_decimals is None or self.listed is None
        ):
            raise ValueError("verified metadata needs complete matching official evidence")
        if self.metadata_status == "DEMO_PROFILE" and self.metadata_source != "PINNED_RESEARCH_FIXTURE":
            raise ValueError("demo profile must be identified as a fixture")
        if self.metadata_source == "NONE" and self.metadata_status in {"EXCHANGE_VERIFIED", "DEMO_PROFILE"}:
            raise ValueError("missing source cannot establish verified metadata")
        return self

    def fingerprint(self) -> str:
        # Reuse the canonical financial research fingerprint, without accepting a caller's hash.
        from app.simulation.models import stable_fingerprint
        return stable_fingerprint(self.model_dump(mode="json"))


class MarketUniverseCatalog(Evidence):
    """Bounded snapshot; distinct namespaces may reuse symbols or local indices."""

    contract_version: Literal["phase180a-v1"] = CONTRACT_VERSION
    records: tuple[MarketUniverseMetadata, ...] = Field(default=(), max_length=4096)
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def unique_identities_and_indices(self):
        identities: set[str] = set()
        indices: set[tuple[str, str, int]] = set()
        for record in self.records:
            key = record.identity.stable_key
            if key in identities:
                raise ValueError("duplicate canonical market identity")
            identities.add(key)
            if record.metadata_status == "EXCHANGE_VERIFIED":
                index_key = (record.identity.instrument_type, record.identity.dex, record.asset_index)
                if index_key in indices:
                    raise ValueError("duplicate verified asset index in DEX namespace")
                indices.add(index_key)
        return self

    def fingerprint(self) -> str:
        from app.simulation.models import stable_fingerprint
        return stable_fingerprint({
            "contract_version": self.contract_version,
            "records": [record.model_dump(mode="json")
                        for record in sorted(self.records, key=lambda item: item.identity.stable_key)],
            "read_only": self.read_only,
            "authority": self.authority,
        })


class DiscoveryEligibility(Evidence):
    """Read-only discovery decision, never PAPER or order authorization."""

    contract_version: Literal["phase180a-v1"] = CONTRACT_VERSION
    identity: MarketInstrumentIdentity
    metadata_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: AwareDatetime
    discovery_eligible: StrictBool
    reason: DiscoveryReason
    paper_research_eligible: Literal[False] = False
    execution_eligible: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def consistency(self):
        if self.discovery_eligible != (self.reason == "DISCOVERABLE"):
            raise ValueError("discovery eligibility conflicts with reason")
        return self


def evaluate_discovery(metadata: MarketUniverseMetadata, *,
                       evaluated_at: datetime, max_age_seconds: int) -> DiscoveryEligibility:
    """Pure read-only projection. Never use this decision as execution authority."""
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 86400:
        raise ValueError("invalid discovery metadata freshness budget")
    if not isinstance(evaluated_at, datetime) or evaluated_at.utcoffset() is None:
        raise ValueError("timezone-aware evaluation time required")
    # Revalidate even if callers used model_copy(update=...) to bypass validators.
    metadata = MarketUniverseMetadata.model_validate(metadata.model_dump(mode="json"))
    if metadata.metadata_status != "EXCHANGE_VERIFIED":
        reason: DiscoveryReason = "UNVERIFIED_METADATA"
    elif metadata.listed is not True:
        reason = "NOT_LISTED"
    elif metadata.observed_at is None:
        reason = "MISSING_TIMESTAMP"
    else:
        age = (evaluated_at - metadata.observed_at).total_seconds()
        reason = ("FUTURE_TIMESTAMP" if age < 0 else
                  "STALE_METADATA" if age > max_age_seconds else "DISCOVERABLE")
    return DiscoveryEligibility(identity=metadata.identity, metadata_fingerprint=metadata.fingerprint(),
                                evaluated_at=evaluated_at, discovery_eligible=reason == "DISCOVERABLE",
                                reason=reason)
