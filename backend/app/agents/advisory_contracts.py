"""Phase 18.4A: immutable, non-authoritative market advisory contracts.

These describe evidence and recommendations; they do not implement agents,
provider acquisition, PAPER admission, quotes, Risk Firewall or order actions.
A self-described EXCHANGE_OBSERVED source is NOT provider authentication.
18.4B-E must bind it to a server-owned validated observation.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Context, Decimal, localcontext
from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field, field_validator, model_serializer, model_validator

from app.accounting.config import bounded_exact_decimal
from app.market_data.live_models import Evidence
from app.market_data.market_universe_contracts import (
    MarketInstrumentIdentity, MarketUniverseMetadata, UtcDatetime, _strict_bool,
    _utc,
)
from app.risk.market_risk_contracts import RiskFinancialUnit, RiskFingerprint
from app.simulation.models import stable_fingerprint

CONTRACT_VERSION = "phase184a-v1"
ANALYSIS_VERSION = "phase184bcd-v1"
AdvisoryStatus = Literal["READY", "INSUFFICIENT_DATA", "STALE", "UNSUPPORTED", "ERROR"]
Provenance = Literal[
    "EXCHANGE_OBSERVED", "SCENARIO_SYNTHETIC", "HYPOTHETICAL_ASSUMPTION", "UNAVAILABLE",
]
OutputProvenance = Literal[
    "EXCHANGE_OBSERVED", "SCENARIO_SYNTHETIC", "HYPOTHETICAL_ASSUMPTION", "MIXED", "UNAVAILABLE",
]
EvidenceCategory = Literal[
    "MARKET_METADATA", "COLLATERAL", "MARGIN_POLICY", "PAPER_ADMISSION",
    "FUNDING", "MARK_PRICE", "ORACLE_PRICE", "MID_PRICE", "BASIS",
    "QUOTE_LADDER", "FEES", "INVENTORY", "FILL_MARKOUT", "RISK_MODEL",
    "OPEN_INTEREST", "FUNDING_HISTORY", "PAPER_FILLS",
]
ResearchOperation = Literal[
    "DISCOVERY", "STANDARD_PAPER", "HYPOTHETICAL_RISK",
    "SOURCE_CONSTRAINED_RISK", "FUNDING_BASIS", "QUOTE_ECONOMICS",
]
AdvisoryDecimal = Annotated[Decimal, BeforeValidator(bounded_exact_decimal)]
AdvisoryConfidence = Annotated[AdvisoryDecimal, Field(ge=0, le=1)]
AdvisoryBps = Annotated[AdvisoryDecimal, Field(ge=-1_000_000, le=1_000_000)]
ShortReason = Annotated[str, Field(min_length=1, max_length=180)]


class AdvisoryEvidence(Evidence):
    """Reuse existing Evidence's immutable/forbid-extra behavior."""

    model_config = ConfigDict(strict=True, revalidate_instances="always", validate_default=True)
    contract_version: Literal["phase184a-v1"] = CONTRACT_VERSION


class AdvisorySourceEvidence(AdvisoryEvidence):
    """A bounded provenance claim; server-side adapters must verify authenticity."""

    identity: MarketInstrumentIdentity
    category: EvidenceCategory
    provenance: Provenance
    source_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    captured_at: UtcDatetime
    binding_version: Literal["phase184bcd-v1"] | None = None
    observed_at: UtcDatetime | None = None
    observation_clock: Literal["PROVIDER_EVENT", "LOCAL_RECEIPT"] | None = None
    scenario_at: UtcDatetime | None = None
    valid_until: UtcDatetime | None = None
    unit: ShortReason | None = None
    limitations: tuple[ShortReason, ...] = Field(default=(), max_length=4)
    source_fingerprint: RiskFingerprint | None = None
    financial_unit: RiskFinancialUnit | None = None
    read_only: Literal[True] = True
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"

    _bools = field_validator("read_only", "execution_eligible", mode="before")(_strict_bool)

    @model_serializer(mode="wrap")
    def omit_unset_extension(self, serialize):
        data = serialize(self)
        for field in ("binding_version", "observation_clock", "valid_until", "unit", "limitations"):
            if not data.get(field):
                data.pop(field, None)
        return data

    @model_validator(mode="after")
    def provenance_boundary(self):
        observed = self.provenance == "EXCHANGE_OBSERVED"
        synthetic = self.provenance == "SCENARIO_SYNTHETIC"
        hypothetical = self.provenance == "HYPOTHETICAL_ASSUMPTION"
        unavailable = self.provenance == "UNAVAILABLE"

        if self.financial_unit is not None and self.financial_unit.network != self.identity.network:
            raise ValueError("advisory financial unit crosses market network")
        if self.valid_until is not None and self.valid_until <= self.captured_at:
            raise ValueError("invalid advisory source expiry")
        if self.observation_clock is not None and not observed:
            raise ValueError("only exchange observations have an observation clock")
        if observed:
            receipt_only = self.observation_clock == "LOCAL_RECEIPT"
            if ((receipt_only and self.observed_at is not None)
                    or (not receipt_only and (self.observed_at is None or self.observed_at > self.captured_at))
                    or self.scenario_at is not None or self.source_fingerprint is None
                    or self.source_id.startswith(("SCENARIO_", "PAPER_", "ASSUMPTION_"))):
                raise ValueError("exchange observation requires distinct, captured source evidence")
        elif synthetic:
            if (self.scenario_at is None or self.observed_at is not None
                    or self.source_fingerprint is None
                    or not self.source_id.startswith(("SCENARIO_", "PAPER_"))
                    or self.category in {"MARKET_METADATA", "COLLATERAL", "MARGIN_POLICY"}):
                raise ValueError("synthetic evidence cannot impersonate exchange metadata/provider")
        elif hypothetical:
            if (self.observed_at is not None or self.scenario_at is not None
                    or self.source_fingerprint is None
                    or not self.source_id.startswith("ASSUMPTION_")):
                raise ValueError("hypothetical assumptions must not claim provider observations")
        elif unavailable and (self.source_id != "NONE" or self.source_fingerprint is not None
                              or self.observed_at is not None or self.scenario_at is not None
                              or self.financial_unit is not None or self.valid_until is not None
                              or self.unit is not None):
            raise ValueError("unavailable source cannot carry invented evidence")
        return self


class AdvisoryContext(AdvisoryEvidence):
    """Snapshot-scoped market and evidence binding, not an admission decision."""

    metadata: MarketUniverseMetadata
    metadata_fingerprint: RiskFingerprint
    catalog_fingerprint: RiskFingerprint | None = None
    risk_model_fingerprint: RiskFingerprint | None = None
    paper_binding_fingerprint: RiskFingerprint | None = None
    evaluated_at: UtcDatetime
    valid_until: UtcDatetime | None = None
    sources: tuple[AdvisorySourceEvidence, ...] = Field(default=(), max_length=16)
    scope: Literal["SINGLE_MARKET_RESEARCH_ONLY"] = "SINGLE_MARKET_RESEARCH_ONLY"
    read_only: Literal[True] = True
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"

    _bools = field_validator("read_only", "execution_eligible", mode="before")(_strict_bool)

    @model_validator(mode="after")
    def context_boundary(self):
        if self.metadata_fingerprint != self.metadata.fingerprint():
            raise ValueError("advisory metadata fingerprint mismatch")
        seen: set[tuple[str, str, str]] = set()
        fingerprints: set[str] = set()
        for source in self.sources:
            if source.identity != self.metadata.identity or source.captured_at > self.evaluated_at:
                raise ValueError("advisory source does not belong to captured market/generation")
            if source.provenance == "EXCHANGE_OBSERVED" and self.metadata.metadata_status != "EXCHANGE_VERIFIED":
                raise ValueError("unverified discovery metadata cannot carry observed advisory inputs")
            key = (source.category, source.provenance, source.source_id)
            if key in seen:
                raise ValueError("duplicate advisory source identity")
            seen.add(key)
            if source.source_fingerprint is not None:
                if source.source_fingerprint in fingerprints:
                    raise ValueError("advisory source fingerprint ambiguity")
                fingerprints.add(source.source_fingerprint)
        if self.valid_until is not None and self.valid_until <= self.evaluated_at:
            raise ValueError("expired advisory context")
        return self

    @property
    def identity(self) -> MarketInstrumentIdentity:
        return self.metadata.identity

    def fingerprint(self) -> str:
        checked = AdvisoryContext.model_validate_json(self.model_dump_json())
        return stable_fingerprint(checked.model_dump(mode="json"))


class AdvisoryRecommendation(AdvisoryEvidence):
    """Observational output; intentionally NOT agents.models.AgentRecommendation."""

    identity: MarketInstrumentIdentity
    context_fingerprint: RiskFingerprint
    evaluated_at: UtcDatetime
    analysis_version: Literal["phase184bcd-v1"] | None = None
    status: AdvisoryStatus
    confidence: AdvisoryConfidence = Decimal("0")
    provenance: OutputProvenance = "UNAVAILABLE"
    source_fingerprints: tuple[RiskFingerprint, ...] = Field(default=(), max_length=16)
    reasons: tuple[ShortReason, ...] = Field(default=(), max_length=12)
    affects_quotes: Literal[False] = False
    can_override_risk: Literal[False] = False
    can_authorize_paper: Literal[False] = False
    execution_eligible: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    _bools = field_validator(
        "affects_quotes", "can_override_risk", "can_authorize_paper",
        "execution_eligible", "read_only", mode="before",
    )(_strict_bool)

    @model_serializer(mode="wrap")
    def omit_unset_extension(self, serialize):
        data = serialize(self)
        for field in (
            "analysis_version", "oracle_mid_basis_bps", "funding_convention", "funding_direction",
            "open_interest_base", "history_count", "recent_history_mean_rate", "captured_spread_bps",
            "slippage_cost_bps", "break_even_capture_bps", "quoted_notional", "executed_reference_notional",
            "holding_seconds", "fill_coverage", "bid_capture_bps", "ask_capture_bps", "filled_base",
            "residual_base", "inventory_expansion_base", "projected_margin_headroom", "margin_headroom_unit",
            "mark_price", "oracle_price", "midpoint_price", "submitted_bid", "submitted_ask",
            "entry_fees_quote", "exit_fees_quote", "attributed_fill_count", "matured_markout_count",
        ):
            if data.get(field) is None:
                data.pop(field, None)
        agent = data.get("agent")
        if agent == "QUOTE_ECONOMICS" and data.get("funding_interval_seconds") is None:
            data.pop("funding_interval_seconds", None)
        if agent != "MARKET_ELIGIBILITY" and not data.get("missing_requirements"):
            data.pop("missing_requirements", None)
        return data

    @model_validator(mode="after")
    def neutral_and_no_authority(self):
        if len(set(self.source_fingerprints)) != len(self.source_fingerprints):
            raise ValueError("duplicate advisory evidence fingerprints")
        if self.status == "READY":
            if self.confidence <= 0 or not self.source_fingerprints or self.provenance == "UNAVAILABLE":
                raise ValueError("ready advisory requires scored, source-bound evidence")
        elif self.confidence != 0:
            raise ValueError("unavailable, stale, unsupported and error advice must have zero confidence")
        if self.status != "READY" and not self.reasons:
            raise ValueError("non-ready advice requires bounded explanation")
        if self.provenance == "UNAVAILABLE" and self.source_fingerprints:
            raise ValueError("unavailable advisory cannot cite available evidence")
        return self

    def fingerprint(self) -> str:
        checked = type(self).model_validate_json(self.model_dump_json())
        return stable_fingerprint(checked.model_dump(mode="json"))


class MarketEligibilityAdvisory(AdvisoryRecommendation):
    agent: Literal["MARKET_ELIGIBILITY"] = "MARKET_ELIGIBILITY"
    operation: ResearchOperation
    suitability: Literal["SUITABLE", "CONDITIONAL", "NOT_SUITABLE", "UNKNOWN"]
    missing_requirements: tuple[ShortReason, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def suitability_boundary(self):
        if self.suitability in {"SUITABLE", "CONDITIONAL"} and self.status != "READY":
            raise ValueError("non-ready market cannot be presented as suitable")
        return self


class FundingBasisAdvisory(AdvisoryRecommendation):
    agent: Literal["FUNDING_BASIS"] = "FUNDING_BASIS"
    state: Literal[
        "FUNDING_POSITIVE", "FUNDING_NEGATIVE", "BASIS_STRESSED",
        "NEUTRAL", "UNKNOWN",
    ] = "UNKNOWN"
    funding_rate: AdvisoryDecimal | None = None
    funding_interval_seconds: int | None = Field(default=None, ge=1, le=604800)
    mark_oracle_basis_bps: AdvisoryBps | None = None
    mark_mid_basis_bps: AdvisoryBps | None = None
    oracle_mid_basis_bps: AdvisoryBps | None = None
    funding_convention: Literal["HYPERLIQUID_HOURLY", "PAPER_SCHEDULED_INTERVAL"] | None = None
    funding_direction: Literal["LONGS_PAY", "SHORTS_PAY", "FLAT"] | None = None
    open_interest_base: Annotated[AdvisoryDecimal, Field(ge=0)] | None = None
    mark_price: Annotated[AdvisoryDecimal, Field(gt=0)] | None = None
    oracle_price: Annotated[AdvisoryDecimal, Field(gt=0)] | None = None
    midpoint_price: Annotated[AdvisoryDecimal, Field(gt=0)] | None = None
    history_count: int | None = Field(default=None, ge=0, le=24)
    recent_history_mean_rate: AdvisoryDecimal | None = None
    missing_requirements: tuple[ShortReason, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def signal_boundary(self):
        if self.status != "READY" and self.state != "UNKNOWN":
            raise ValueError("incomplete funding evidence cannot produce active signal")
        if self.state in {"FUNDING_POSITIVE", "FUNDING_NEGATIVE"} and self.funding_rate is None:
            raise ValueError("funding signal must have an evidenced rate")
        if self.state == "BASIS_STRESSED" and self.mark_oracle_basis_bps is None:
            raise ValueError("basis signal must have evidenced basis")
        if self.analysis_version is not None and self.status == "READY" and (
                self.funding_convention is None or self.state == "UNKNOWN"):
            raise ValueError("ready funding analysis requires an explicit convention and signal")
        if self.funding_convention is not None:
            if (self.status != "READY" or self.funding_rate is None or self.funding_interval_seconds is None
                    or self.mark_oracle_basis_bps is None):
                raise ValueError("funding convention requires complete ready funding/basis evidence")
            direction = ("LONGS_PAY" if self.funding_rate > 0 else
                         "SHORTS_PAY" if self.funding_rate < 0 else "FLAT")
            if self.funding_direction != direction:
                raise ValueError("funding direction does not match rate")
            if self.funding_convention == "HYPERLIQUID_HOURLY" and (
                    self.funding_interval_seconds != 3600 or self.provenance != "EXCHANGE_OBSERVED"):
                raise ValueError("official current funding is hourly and exchange observed")
            if self.funding_convention == "PAPER_SCHEDULED_INTERVAL" and self.provenance != "SCENARIO_SYNTHETIC":
                raise ValueError("scheduled PAPER rates require synthetic evidence")
        return self


class QuoteEconomicsAdvisory(AdvisoryRecommendation):
    agent: Literal["QUOTE_ECONOMICS"] = "QUOTE_ECONOMICS"
    state: Literal[
        "MODELED_POSITIVE", "MODELED_NEGATIVE", "MODELED_BREAKEVEN", "INDETERMINATE",
    ] = "INDETERMINATE"
    accounting_unit: RiskFinancialUnit | None = None
    gross_spread_bps: Annotated[AdvisoryDecimal, Field(ge=0)] | None = None
    fee_cost_bps: Annotated[AdvisoryDecimal, Field(ge=0)] | None = None
    funding_cost_bps: AdvisoryBps | None = None
    inventory_cost_bps: Annotated[AdvisoryDecimal, Field(ge=0)] | None = None
    adverse_selection_cost_bps: Annotated[AdvisoryDecimal, Field(ge=0)] | None = None
    modeled_edge_bps: AdvisoryBps | None = None
    captured_spread_bps: AdvisoryBps | None = None
    slippage_cost_bps: Annotated[AdvisoryDecimal, Field(ge=0)] | None = None
    break_even_capture_bps: AdvisoryBps | None = None
    quoted_notional: Annotated[AdvisoryDecimal, Field(gt=0)] | None = None
    executed_reference_notional: Annotated[AdvisoryDecimal, Field(gt=0)] | None = None
    holding_seconds: int | None = Field(default=None, ge=1, le=604800)
    funding_interval_seconds: int | None = Field(default=None, ge=1, le=604800)
    fill_coverage: Literal["ONE_SIDED", "BOTH_SIDES"] | None = None
    bid_capture_bps: AdvisoryBps | None = None
    ask_capture_bps: AdvisoryBps | None = None
    filled_base: Annotated[AdvisoryDecimal, Field(gt=0)] | None = None
    residual_base: AdvisoryDecimal | None = None
    inventory_expansion_base: Annotated[AdvisoryDecimal, Field(ge=0)] | None = None
    projected_margin_headroom: AdvisoryDecimal | None = None
    margin_headroom_unit: RiskFinancialUnit | None = None
    missing_requirements: tuple[ShortReason, ...] = Field(default=(), max_length=12)
    submitted_bid: Annotated[AdvisoryDecimal, Field(gt=0)] | None = None
    submitted_ask: Annotated[AdvisoryDecimal, Field(gt=0)] | None = None
    entry_fees_quote: Annotated[AdvisoryDecimal, Field(ge=0)] | None = None
    exit_fees_quote: Annotated[AdvisoryDecimal, Field(ge=0)] | None = None
    attributed_fill_count: int | None = Field(default=None, ge=1, le=1000)
    matured_markout_count: int | None = Field(default=None, ge=1, le=1000)
    hypothetical_only: Literal[True] = True
    guarantees_profit: Literal[False] = False

    _bools_economics = field_validator("hypothetical_only", "guarantees_profit", mode="before")(_strict_bool)

    @model_validator(mode="after")
    def model_boundary(self):
        if self.state != "INDETERMINATE":
            if self.status != "READY" or self.provenance in {"EXCHANGE_OBSERVED", "UNAVAILABLE"}:
                raise ValueError("quote economics signal is modeled, never exchange-certified profit")
            inputs = (self.accounting_unit, self.gross_spread_bps, self.fee_cost_bps,
                      self.funding_cost_bps, self.inventory_cost_bps,
                      self.adverse_selection_cost_bps, self.modeled_edge_bps)
            if any(value is None for value in inputs):
                raise ValueError("modeled quote economics requires complete assumption components")
            if self.accounting_unit.kind != "HYPOTHETICAL_QUOTE":
                raise ValueError("modeled quote edge must use the PAPER accounting unit")
            if self.state == "MODELED_POSITIVE" and self.modeled_edge_bps <= 0:
                raise ValueError("positive modeled edge has incorrect sign")
            if self.state == "MODELED_NEGATIVE" and self.modeled_edge_bps >= 0:
                raise ValueError("negative modeled edge has incorrect sign")
            if self.state == "MODELED_BREAKEVEN" and self.modeled_edge_bps != 0:
                raise ValueError("break-even modeled edge must equal zero")
        if self.captured_spread_bps is not None:
            costs = (self.fee_cost_bps, self.funding_cost_bps, self.inventory_cost_bps,
                     self.adverse_selection_cost_bps, self.slippage_cost_bps)
            with localcontext(Context(prec=120)):
                if (self.state == "INDETERMINATE" or any(value is None for value in costs)
                        or self.break_even_capture_bps != sum(costs)
                        or self.modeled_edge_bps != self.captured_spread_bps - self.break_even_capture_bps):
                    raise ValueError("modeled edge must reconcile with capture and costs")
        if self.analysis_version is not None:
            required = (self.captured_spread_bps, self.quoted_notional, self.executed_reference_notional,
                        self.holding_seconds, self.funding_interval_seconds, self.fill_coverage,
                        self.filled_base, self.residual_base, self.inventory_expansion_base)
            if self.status == "READY" and any(value is None for value in required):
                raise ValueError("ready quote analysis requires captured fills, horizon and funding interval")
        detail = (self.submitted_bid, self.submitted_ask, self.entry_fees_quote, self.exit_fees_quote,
                  self.attributed_fill_count, self.matured_markout_count)
        if any(value is not None for value in detail):
            if (self.status != "READY" or any(value is None for value in detail)
                    or self.submitted_ask <= self.submitted_bid
                    or self.attributed_fill_count != self.matured_markout_count):
                raise ValueError("quote details require a reconciled ladder and mature PAPER fills")
        if (self.projected_margin_headroom is None) != (self.margin_headroom_unit is None):
            raise ValueError("margin headroom requires its exact denomination")
        return self


class AdvisorySnapshot(AdvisoryEvidence):
    """Independent sidecar snapshot; never aggregated into material supervisor output."""

    context: AdvisoryContext
    market_eligibility: MarketEligibilityAdvisory | None = None
    funding_basis: FundingBasisAdvisory | None = None
    quote_economics: QuoteEconomicsAdvisory | None = None
    scope: Literal["SINGLE_MARKET_RESEARCH_ONLY"] = "SINGLE_MARKET_RESEARCH_ONLY"
    affects_quotes: Literal[False] = False
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"

    _bools = field_validator("affects_quotes", "execution_eligible", mode="before")(_strict_bool)

    @model_validator(mode="after")
    def snapshot_binding(self):
        context = AdvisoryContext.model_validate_json(self.context.model_dump_json())
        sources = {
            source.source_fingerprint: source for source in context.sources
            if source.source_fingerprint is not None
        }
        for result in (self.market_eligibility, self.funding_basis, self.quote_economics):
            if result is None:
                continue
            if (result.identity != context.identity or
                    result.context_fingerprint != context.fingerprint() or
                    result.evaluated_at != context.evaluated_at):
                raise ValueError("advisory result does not match captured market/context")
            selected = []
            for fp in result.source_fingerprints:
                if fp not in sources:
                    raise ValueError("advisory output references unknown source evidence")
                selected.append(sources[fp].provenance)
            selected_types = set(selected)
            expected = ("MIXED" if len(selected_types) > 1 else
                        next(iter(selected_types)) if selected_types else "UNAVAILABLE")
            if result.provenance != expected:
                raise ValueError("advisory output provenance mismatches referenced sources")
            if result.analysis_version is not None and any(
                    sources[fp].binding_version != ANALYSIS_VERSION for fp in result.source_fingerprints):
                raise ValueError("implementation output must cite content-bound sources")
            if result.status == "READY" and (
                context.metadata.metadata_status != "EXCHANGE_VERIFIED"
                or context.metadata.listed is not True
                or context.valid_until is None
                or context.metadata.observed_at > context.evaluated_at
                or any(sources[fp].valid_until is not None
                       and sources[fp].valid_until <= context.evaluated_at for fp in result.source_fingerprints)
            ):
                raise ValueError("stale or unsupported market cannot produce ready advice")
            if isinstance(result, FundingBasisAdvisory):
                kinds = {source.category for source in context.sources
                         if source.source_fingerprint in result.source_fingerprints}
                prices = {"MARK_PRICE": result.mark_price, "ORACLE_PRICE": result.oracle_price,
                          "MID_PRICE": result.midpoint_price}
                if any(price is not None and category not in kinds for category, price in prices.items()):
                    raise ValueError("funding display prices require corresponding captured sources")
                if result.funding_rate is not None and "FUNDING" not in kinds:
                    raise ValueError("funding rate lacks funding-specific evidence")
                if (result.mark_oracle_basis_bps is not None or result.mark_mid_basis_bps is not None) and not (
                        "BASIS" in kinds or {"MARK_PRICE", "ORACLE_PRICE"} <= kinds):
                    raise ValueError("basis requires basis or compatible mark/oracle evidence")
                if result.funding_convention is not None:
                    if not {"FUNDING", "MARK_PRICE", "ORACLE_PRICE"} <= kinds:
                        raise ValueError("funding convention requires aligned price and rate sources")
                    if ((result.mark_mid_basis_bps is not None or result.oracle_mid_basis_bps is not None)
                            and "MID_PRICE" not in kinds):
                        raise ValueError("mid basis requires midpoint evidence")
                    if result.history_count and "FUNDING_HISTORY" not in kinds:
                        raise ValueError("funding history summary requires historical source")
                    if result.open_interest_base is not None and "OPEN_INTEREST" not in kinds:
                        raise ValueError("open interest requires its own source")
            if isinstance(result, QuoteEconomicsAdvisory) and result.accounting_unit is not None:
                if result.accounting_unit.network != context.identity.network:
                    raise ValueError("quote economics accounting unit crosses network")
                if result.margin_headroom_unit is not None and result.margin_headroom_unit.network != context.identity.network:
                    raise ValueError("margin headroom crosses network")
                if result.captured_spread_bps is not None:
                    selected_sources = {sources[fp].category: sources[fp] for fp in result.source_fingerprints}
                    required = {
                        "QUOTE_LADDER": "SCENARIO_SYNTHETIC", "PAPER_FILLS": "SCENARIO_SYNTHETIC",
                        "FUNDING": "SCENARIO_SYNTHETIC", "FEES": "HYPOTHETICAL_ASSUMPTION",
                        "INVENTORY": "HYPOTHETICAL_ASSUMPTION", "FILL_MARKOUT": "SCENARIO_SYNTHETIC",
                    }
                    if (not required.keys() <= selected_sources.keys() or any(
                            selected_sources[category].provenance != provenance
                            or (category != "FUNDING" and selected_sources[category].financial_unit != result.accounting_unit)
                            for category, provenance in required.items())):
                        raise ValueError("modeled edge lacks evidence for capture and mandatory costs")
        return self

    def validate_at(self, *, as_of: datetime) -> AdvisorySnapshot:
        """Revalidate before publishing a captured snapshot at a later clock."""
        checked = AdvisorySnapshot.model_validate(self)
        as_of = _utc(as_of)
        if as_of < checked.context.evaluated_at:
            raise ValueError("publication clock precedes captured context")
        ready_sources = {fp for result in (checked.market_eligibility, checked.funding_basis, checked.quote_economics)
                         if result is not None and result.status == "READY" for fp in result.source_fingerprints}
        if ready_sources and (as_of >= checked.context.valid_until or any(
                source.source_fingerprint in ready_sources and source.valid_until is not None
                and as_of >= source.valid_until for source in checked.context.sources)):
            raise ValueError("advisory snapshot contains expired READY evidence")
        return checked

    def fingerprint(self) -> str:
        checked = AdvisorySnapshot.model_validate_json(self.model_dump_json())
        return stable_fingerprint(checked.model_dump(mode="json"))
