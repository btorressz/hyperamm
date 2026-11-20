"""Phase 18.5A: asset-aware AMM research declarations, NOT a quote policy runtime.

Reuse the existing AMM/StrategyConfig and Generalized PAPER precision rules later.
Neither an asset-family label, a source fingerprint nor discoverable metadata
authenticates exchange economics, risk readiness or trade authorization here.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.accounting.config import bounded_exact_decimal
from app.amm.models import AmmModel
from app.market_data.live_models import Evidence
from app.market_data.market_universe_contracts import (
    DiscoveryReason, MarketInstrumentIdentity, MarketUniverseMetadata, UtcDatetime,
    _strict_bool, _utc, evaluate_discovery,
)
from app.risk.market_risk_contracts import RiskFinancialUnit, RiskFingerprint
from app.simulation.models import stable_fingerprint

CONTRACT_VERSION = "phase185a-v1"
ExactResearchDecimal = Annotated[Decimal, BeforeValidator(bounded_exact_decimal)]
AssetFamily = Literal[
    "CRYPTO", "EQUITY", "INDEX", "COMMODITY", "ENERGY", "FX", "RATES",
    "OTHER", "UNKNOWN",
]


class AssetAmmEvidence(Evidence):
    model_config = ConfigDict(strict=True, validate_default=True, revalidate_instances="always")
    contract_version: Literal["phase185a-v1"] = CONTRACT_VERSION


class AssetResearchClassification(AssetAmmEvidence):
    """An operator-supplied research label, NOT an exchange-verified instrument classification."""

    family: AssetFamily
    provenance: Literal["OPERATOR_DECLARED_RESEARCH"] = "OPERATOR_DECLARED_RESEARCH"
    exchange_class_verified: Literal[False] = False
    tradability_verified: Literal[False] = False

    _flags = field_validator(
        "exchange_class_verified", "tradability_verified", mode="before",
    )(_strict_bool)


class AssetAmmResearchControls(AssetAmmEvidence):
    """Small declared subset of existing StrategyConfig parameters.

    B/C must apply/verify these against StrategyConfig and the real
    precision/curve/quote compiler. This class neither generates nor approves quotes.
    Sizes and inventory are BASE units; distances and skew are basis points.
    """

    amm_model: AmmModel
    virtual_base_reserve: ExactResearchDecimal = Field(gt=0, le=1_000_000_000)
    virtual_quote_reserve: ExactResearchDecimal = Field(gt=0, le=1_000_000_000_000)
    levels_per_side: StrictInt = Field(ge=1, le=50)
    max_distance_bps: ExactResearchDecimal = Field(gt=0, le=2500)
    base_order_size: ExactResearchDecimal = Field(gt=0, le=1_000_000_000)
    total_liquidity: ExactResearchDecimal = Field(gt=0, le=1_000_000_000)
    concentration_factor: ExactResearchDecimal = Field(ge=0, le=1000)
    concentration_lower_bps: ExactResearchDecimal = Field(ge=0, le=2500)
    concentration_upper_bps: ExactResearchDecimal = Field(gt=0, le=2500)
    target_inventory_base: ExactResearchDecimal = Field(ge=-1_000_000_000, le=1_000_000_000)
    soft_inventory_limit_base: ExactResearchDecimal = Field(gt=0, le=1_000_000_000)
    hard_inventory_limit_base: ExactResearchDecimal = Field(gt=0, le=1_000_000_000)
    max_inventory_price_skew_bps: ExactResearchDecimal = Field(ge=0, le=500)
    volatility_spread_strength: ExactResearchDecimal = Field(ge=0, le=10)
    volatility_size_strength: ExactResearchDecimal = Field(ge=0, le=1)
    max_funding_reference_shift_bps: ExactResearchDecimal = Field(ge=0, le=100)
    price_precision_policy: Literal["REUSE_GENERALIZED_PRECISION"] = "REUSE_GENERALIZED_PRECISION"
    size_precision_policy: Literal["REUSE_DISCOVERED_SZ_DECIMALS"] = "REUSE_DISCOVERED_SZ_DECIMALS"
    provenance: Literal["HYPOTHETICAL_RESEARCH_SETTINGS"] = "HYPOTHETICAL_RESEARCH_SETTINGS"

    @model_validator(mode="after")
    def consistency(self):
        if self.concentration_upper_bps <= self.concentration_lower_bps:
            raise ValueError("concentration upper bound must exceed lower bound")
        if self.hard_inventory_limit_base <= self.soft_inventory_limit_base:
            raise ValueError("hard inventory bound must exceed soft bound")
        if self.base_order_size * self.levels_per_side > self.total_liquidity:
            raise ValueError("declared liquidity cannot cover minimum per-side quote sizes")
        return self


class AssetAmmResearchPolicy(AssetAmmEvidence):
    """One hypothetical single-market AMM configuration with canonical evidence."""

    metadata: MarketUniverseMetadata
    metadata_fingerprint: RiskFingerprint
    classification: AssetResearchClassification
    controls: AssetAmmResearchControls
    hypothetical_accounting_unit: RiskFinancialUnit
    simulated_reference_price: ExactResearchDecimal = Field(gt=0, le=10_000_000)
    declared_at: UtcDatetime
    catalog_fingerprint: RiskFingerprint | None = None
    research_risk_fingerprint: RiskFingerprint | None = None
    advisory_snapshot_fingerprint: RiskFingerprint | None = None
    reference_provenance: Literal["USER_SUPPLIED_SYNTHETIC"] = "USER_SUPPLIED_SYNTHETIC"
    source_provenance: Literal["DECLARED_HYPOTHETICAL_POLICY"] = "DECLARED_HYPOTHETICAL_POLICY"
    research_scope: Literal["SINGLE_MARKET_RESEARCH_ONLY"] = "SINGLE_MARKET_RESEARCH_ONLY"
    execution_mode: Literal["PAPER"] = "PAPER"
    risk_ready: Literal[False] = False
    affects_quotes: Literal[False] = False
    can_authorize_paper: Literal[False] = False
    can_override_risk: Literal[False] = False
    execution_eligible: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    _flags = field_validator(
        "risk_ready", "affects_quotes", "can_authorize_paper",
        "can_override_risk", "execution_eligible", "read_only", mode="before",
    )(_strict_bool)

    @model_validator(mode="after")
    def bind_evidence(self):
        if self.metadata_fingerprint != self.metadata.fingerprint():
            raise ValueError("asset-aware policy metadata fingerprint mismatch")
        if (self.hypothetical_accounting_unit.network != self.metadata.identity.network
                or self.hypothetical_accounting_unit.kind != "HYPOTHETICAL_QUOTE"):
            raise ValueError("PAPER policy requires same-network hypothetical accounting units")
        if self.metadata.observed_at is not None and self.metadata.observed_at > self.declared_at:
            raise ValueError("research policy cannot predate observed metadata")
        return self

    @property
    def identity(self) -> MarketInstrumentIdentity:
        return self.metadata.identity

    def fingerprint(self) -> str:
        checked = AssetAmmResearchPolicy.model_validate_json(self.model_dump_json())
        return stable_fingerprint(checked.model_dump(mode="json"))


class AssetAmmPolicyAssessment(AssetAmmEvidence):
    """Research draft or blocked metadata; NOT PAPER admission or risk readiness."""

    identity: MarketInstrumentIdentity
    metadata_fingerprint: RiskFingerprint
    policy_fingerprint: RiskFingerprint
    evaluated_at: UtcDatetime
    status: Literal["RESEARCH_DRAFT", "BLOCKED"]
    reason: DiscoveryReason
    eligible_for_paper: Literal[False] = False
    eligible_for_testnet: Literal[False] = False
    eligible_for_live: Literal[False] = False
    risk_ready: Literal[False] = False
    affects_quotes: Literal[False] = False
    can_override_risk: Literal[False] = False
    execution_eligible: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    _flags = field_validator(
        "eligible_for_paper", "eligible_for_testnet", "eligible_for_live",
        "risk_ready", "affects_quotes", "can_override_risk", "execution_eligible",
        "read_only", mode="before",
    )(_strict_bool)

    @model_validator(mode="after")
    def decision_consistency(self):
        expected = "RESEARCH_DRAFT" if self.reason == "DISCOVERABLE" else "BLOCKED"
        if self.status != expected:
            raise ValueError("research draft status disagrees with discovery evidence")
        return self


def assess_asset_amm_policy(
    policy: AssetAmmResearchPolicy, *, evaluated_at: datetime, max_age_seconds: int,
) -> AssetAmmPolicyAssessment:
    """Pure fail-closed discovery precheck; no strategy, paper or trading authorization."""
    policy = AssetAmmResearchPolicy.model_validate_json(policy.model_dump_json())
    at = _utc(evaluated_at)
    if at < policy.declared_at:
        raise ValueError("assessment precedes policy declaration")
    discovery = evaluate_discovery(
        policy.metadata, evaluated_at=at, max_age_seconds=max_age_seconds,
    )
    return AssetAmmPolicyAssessment(
        identity=policy.identity,
        metadata_fingerprint=policy.metadata_fingerprint,
        policy_fingerprint=policy.fingerprint(),
        evaluated_at=at,
        status="RESEARCH_DRAFT" if discovery.discovery_eligible else "BLOCKED",
        reason=discovery.reason,
    )
