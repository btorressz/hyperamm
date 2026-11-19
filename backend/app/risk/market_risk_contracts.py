"""Phase 18.3A: non-authoritative collateral, margin and risk-evidence contracts.

These models describe *declared* financial units and hypothetical research policy.
Official discovery metadata does not verify collateral, settlement or margin.
No calculations, SDK calls, portfolio admission or exchange authority live here.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field, field_validator, model_validator

from app.accounting.config import bounded_exact_decimal
from app.market_data.live_models import Evidence
from app.market_data.market_universe_contracts import (
    MarketInstrumentIdentity, MarketUniverseMetadata, Network, UtcDatetime,
    _strict_bool, evaluate_discovery,
)

CONTRACT_VERSION = "phase183a-v1"
RiskFingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
MarginFraction = Annotated[Decimal, BeforeValidator(bounded_exact_decimal), Field(gt=0, le=1)]
ModeledLeverage = Annotated[Decimal, BeforeValidator(bounded_exact_decimal), Field(ge=1, le=100)]


class RiskFoundationEvidence(Evidence):
    model_config = ConfigDict(strict=True, revalidate_instances="always", validate_default=True)

    contract_version: Literal["phase183a-v1"] = CONTRACT_VERSION


class RiskFinancialUnit(RiskFoundationEvidence):
    """An explicitly declared unit, NOT evidence that an exchange supports it."""

    network: Network
    kind: Literal["EXCHANGE_ASSET", "HYPOTHETICAL_QUOTE"]
    symbol: str = Field(min_length=1, max_length=64)
    asset_namespace: str = Field(default="", max_length=64)
    asset_reference: str | None = Field(default=None, max_length=128)
    provenance: Literal["DECLARED_UNVERIFIED", "RESEARCH_ASSUMPTION"]

    @model_validator(mode="after")
    def validate_unit(self):
        if self.kind == "HYPOTHETICAL_QUOTE":
            if (self.symbol != "HYPOTHETICAL_QUOTE" or self.asset_namespace != "" or
                    self.asset_reference is not None or self.provenance != "RESEARCH_ASSUMPTION"):
                raise ValueError("hypothetical accounting unit cannot claim exchange identity")
        else:
            if (self.symbol == "HYPOTHETICAL_QUOTE" or
                    self.provenance != "DECLARED_UNVERIFIED" or
                    not self.asset_reference):
                raise ValueError("exchange asset must have an explicit, unverified asset reference")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", self.symbol):
                raise ValueError("invalid exchange asset symbol")
            if self.asset_namespace and not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9._-]*", self.asset_namespace):
                raise ValueError("invalid asset namespace")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", self.asset_reference):
                raise ValueError("invalid asset reference")
        return self


class MarketCollateralIdentity(RiskFoundationEvidence):
    """Separates a derivative's price quote, collateral, settlement and PAPER units.

    Deliberately does not infer any of these units from coin, DEX or szDecimals.
    """

    metadata: MarketUniverseMetadata
    metadata_fingerprint: RiskFingerprint
    price_quote_unit: RiskFinancialUnit | None = None
    collateral_unit: RiskFinancialUnit | None = None
    settlement_unit: RiskFinancialUnit | None = None
    paper_accounting_unit: RiskFinancialUnit
    unit_evidence: Literal["DECLARED_UNVERIFIED"] = "DECLARED_UNVERIFIED"
    verified_collateral: Literal[False] = False
    verified_settlement: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    _validate_flags = field_validator(
        "verified_collateral", "verified_settlement", "read_only", mode="before"
    )(_strict_bool)

    @model_validator(mode="after")
    def validate_financial_units(self):
        if self.metadata_fingerprint != self.metadata.fingerprint():
            raise ValueError("collateral identity metadata fingerprint mismatch")
        for unit in (self.price_quote_unit, self.collateral_unit, self.settlement_unit):
            if unit is not None and (unit.network != self.metadata.identity.network or
                                     unit.kind != "EXCHANGE_ASSET"):
                raise ValueError("unsupported or cross-network exchange financial unit")
        if (self.paper_accounting_unit.network != self.metadata.identity.network or
                self.paper_accounting_unit.kind != "HYPOTHETICAL_QUOTE"):
            raise ValueError("PAPER accounting must use an explicitly hypothetical unit")
        return self

    @property
    def instrument(self) -> MarketInstrumentIdentity:
        return self.metadata.identity

    def fingerprint(self) -> str:
        from app.simulation.models import stable_fingerprint
        checked = MarketCollateralIdentity.model_validate_json(self.model_dump_json())
        return stable_fingerprint(checked.model_dump(mode="json"))


class MarketMarginPolicy(RiskFoundationEvidence):
    """Research policy declaration, never exchange-certified margin rules."""

    financial_units: MarketCollateralIdentity
    account_mode: Literal["UNKNOWN", "STANDARD", "UNIFIED", "PORTFOLIO_MARGIN"] = "UNKNOWN"
    margin_mode: Literal["UNSPECIFIED", "ISOLATED", "STRICT_ISOLATED",
                         "NO_CROSS", "CROSS"] = "UNSPECIFIED"
    policy_evidence: Literal["UNVERIFIED", "HYPOTHETICAL"] = "UNVERIFIED"
    initial_margin_fraction: MarginFraction | None = None
    maintenance_margin_fraction: MarginFraction | None = None
    modeled_max_leverage: ModeledLeverage | None = None
    liquidation_price: None = None
    exchange_margin_verified: Literal[False] = False
    shared_capital_eligible: Literal[False] = False
    cross_market_netting_eligible: Literal[False] = False
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"

    _validate_flags = field_validator(
        "exchange_margin_verified", "shared_capital_eligible",
        "cross_market_netting_eligible", "execution_eligible", mode="before"
    )(_strict_bool)

    @model_validator(mode="after")
    def validate_policy(self):
        has_numbers = (self.initial_margin_fraction is not None or
                       self.maintenance_margin_fraction is not None or
                       self.modeled_max_leverage is not None)
        if self.policy_evidence == "UNVERIFIED":
            if has_numbers:
                raise ValueError("unverified margin policy cannot assert financial parameters")
        else:
            if (self.margin_mode == "UNSPECIFIED" or
                    self.initial_margin_fraction is None or
                    self.maintenance_margin_fraction is None):
                raise ValueError("hypothetical margin policy needs explicit mode and fractions")
            if self.maintenance_margin_fraction > self.initial_margin_fraction:
                raise ValueError("maintenance margin exceeds initial margin")
        return self

    def fingerprint(self) -> str:
        from app.simulation.models import stable_fingerprint
        checked = MarketMarginPolicy.model_validate_json(self.model_dump_json())
        return stable_fingerprint(checked.model_dump(mode="json"))


RiskBlockReason = Literal[
    "MARKET_METADATA_UNAVAILABLE", "MARKET_DELISTED", "MARKET_METADATA_STALE",
    "COLLATERAL_NOT_ESTABLISHED", "COLLATERAL_UNVERIFIED",
    "MARGIN_POLICY_UNVERIFIED", "HYPOTHETICAL_ONLY",
]


class MarketRiskReadiness(RiskFoundationEvidence):
    """A versioned blocked readiness decision, NOT an operational risk decision."""

    identity: MarketInstrumentIdentity
    metadata_fingerprint: RiskFingerprint
    collateral_fingerprint: RiskFingerprint
    margin_policy_fingerprint: RiskFingerprint
    evaluated_at: UtcDatetime
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: RiskBlockReason
    scope: Literal["SINGLE_MARKET_RESEARCH_ONLY"] = "SINGLE_MARKET_RESEARCH_ONLY"
    risk_ready: Literal[False] = False
    exchange_margin_verified: Literal[False] = False
    shared_capital_eligible: Literal[False] = False
    leverage_eligible: Literal[False] = False
    cross_market_netting_eligible: Literal[False] = False
    execution_eligible: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    _validate_flags = field_validator(
        "risk_ready", "exchange_margin_verified", "shared_capital_eligible",
        "leverage_eligible", "cross_market_netting_eligible", "execution_eligible",
        "read_only", mode="before"
    )(_strict_bool)


def assess_market_risk_readiness(
    policy: MarketMarginPolicy, *, evaluated_at: datetime, max_age_seconds: int
) -> MarketRiskReadiness:
    """Pure, fail-closed 18.3A handoff; not margin calculation or trading authorization.

    Model copies may have bypassed nested validation: deserialize and validate
    the full captured policy before inspecting it or producing a fingerprint.
    """
    policy = MarketMarginPolicy.model_validate_json(policy.model_dump_json())
    units = policy.financial_units
    discovery = evaluate_discovery(
        units.metadata, evaluated_at=evaluated_at, max_age_seconds=max_age_seconds
    )
    if discovery.reason == "NOT_LISTED":
        reason: RiskBlockReason = "MARKET_DELISTED"
    elif discovery.reason in {"STALE_METADATA", "FUTURE_TIMESTAMP"}:
        reason = "MARKET_METADATA_STALE"
    elif not discovery.discovery_eligible:
        reason = "MARKET_METADATA_UNAVAILABLE"
    elif units.collateral_unit is None:
        reason = "COLLATERAL_NOT_ESTABLISHED"
    elif not units.verified_collateral:
        reason = "COLLATERAL_UNVERIFIED"
    elif policy.policy_evidence == "UNVERIFIED":
        reason = "MARGIN_POLICY_UNVERIFIED"
    else:
        reason = "HYPOTHETICAL_ONLY"
    # In v1 the verified_collateral flag is a literal False, so no declaration
    # can progress to a risk-ready state. Phase 18.3B must separately establish
    # trusted evidence before any new eligibility contract may be introduced.
    return MarketRiskReadiness(
        identity=units.instrument,
        metadata_fingerprint=units.metadata_fingerprint,
        collateral_fingerprint=units.fingerprint(),
        margin_policy_fingerprint=policy.fingerprint(),
        evaluated_at=discovery.evaluated_at,
        reason=reason,
    )
