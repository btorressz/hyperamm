"""Immutable portfolio configuration and independent PAPER execution receipts.

The 17.1A configuration and NOT_EXECUTED contracts remain compatible. The 17.2
bundle establishes no synchronized windows, portfolio economics or trading authority.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Literal

from pydantic import AwareDatetime, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.accounting.models import canonical
from app.market_data.live_models import Evidence, FinancialDecimal, NonnegativeDecimal, PositiveDecimal
from app.research_replay.comparison import ComparisonConfigSnapshot
from app.research_replay.models import Fingerprint
from app.simulation.market_profiles import MARKETS, ResearchPerpMarketId
from app.simulation.models import stable_fingerprint
from app.simulation.scenarios import ScenarioName
from app.accounting.models import VaultSnapshot, canonical as accounting_canonical
from app.execution.research import PaperExecutionAssumptions
from app.research_replay.comparison import CapturedScenarioResult, ScenarioProvenanceReceipt
from app.simulation.models import SimulationMetrics, ResearchMarketAssumptions
from .allocation import allocation_totals
from .config import (
    ExactPortfolioDecimal, MAX_PORTFOLIO_CAPITAL, MAX_TOTAL_FRAMES,
    MAX_QUOTE_LEVEL_FRAMES, MAX_TOTAL_TRACE_POINTS, MAX_TOTAL_LEDGER_ENTRIES,
    MAX_TOTAL_EVENT_ENTRIES,
)

CONTRACT_VERSION = "phase17-portfolio-research-v1"


class PortfolioEvidence(Evidence):
    # Frozen models can still be forged with model_copy/model_construct. Validate
    # every portfolio object again when it crosses a containing model boundary.
    model_config = ConfigDict(revalidate_instances="always")


class PortfolioCapitalBudget(PortfolioEvidence):
    quote_currency: Literal["USDC"] = "USDC"
    total_equity_quote: ExactPortfolioDecimal = Field(gt=0, le=MAX_PORTFOLIO_CAPITAL)
    minimum_reserve_quote: ExactPortfolioDecimal = Field(default=Decimal("0"), ge=0)


class MarketResearchAllocation(PortfolioEvidence):
    market: ResearchPerpMarketId
    allocated_equity_quote: ExactPortfolioDecimal = Field(gt=0)


class PortfolioRiskLimits(PortfolioEvidence):
    """Configuration ceilings, NOT an operational firewall or calculated exposure."""

    max_gross_exposure_quote: ExactPortfolioDecimal = Field(gt=0)
    max_abs_net_exposure_quote: ExactPortfolioDecimal = Field(gt=0)
    max_session_loss_quote: ExactPortfolioDecimal = Field(gt=0)
    max_drawdown_fraction: ExactPortfolioDecimal = Field(ge=0, le=1)
    max_capital_utilization: ExactPortfolioDecimal = Field(gt=0, le=1)
    max_inventory_concentration: ExactPortfolioDecimal = Field(gt=0, le=1)
    modeled_leverage_ceiling: ExactPortfolioDecimal = Field(ge=1, le=100)

    @model_validator(mode="after")
    def validate_limits(self):
        if self.max_abs_net_exposure_quote > self.max_gross_exposure_quote:
            raise ValueError("portfolio net exposure ceiling cannot exceed gross ceiling")
        return self


class PortfolioResearchScenario(PortfolioEvidence):
    """Captured single-market DEMO/PAPER settings; no historical time matching."""

    market: ResearchPerpMarketId
    scenario: ScenarioName
    frames: StrictInt = Field(ge=2, le=5000)
    captured: ComparisonConfigSnapshot
    source_kind: Literal["DETERMINISTIC_SCENARIO"] = "DETERMINISTIC_SCENARIO"
    source_authenticated: Literal[False] = False
    licensing_independently_verified: Literal[False] = False
    authority: Literal["NONE"] = "NONE"

    @field_validator("captured", mode="before")
    @classmethod
    def validate_bound_capture(cls, value):
        # Existing snapshots may arrive via model_copy(update=...), which
        # bypasses Pydantic's own validators. Revalidate exact wire identities.
        if isinstance(value, ComparisonConfigSnapshot):
            return ComparisonConfigSnapshot.model_validate_json(value.model_dump_json())
        return value

    @model_validator(mode="after")
    def verify_capture(self):
        effective = self.captured.inputs()
        if effective.strategy.market != self.market:
            raise ValueError("portfolio scenario market differs from captured strategy")
        if effective.simulation.max_frames != self.frames:
            raise ValueError("portfolio scenario frame count differs from captured simulation")
        if effective.market_profile is None or effective.market_profile.market != self.market:
            raise ValueError("portfolio research requires a validated captured market profile")
        if self.captured.market_profile_fingerprint != effective.market_profile.profile_fingerprint:
            raise ValueError("portfolio market profile identity mismatch")
        # Reuse accounting's exact numeric normalization and comparison's capture
        # algorithm. Equivalent Decimal spellings must also agree inside captures;
        # existing single-market snapshot/fingerprint conventions stay untouched.
        normalized_payload = {
            name: type(value).model_validate(canonical(value)).model_dump(mode="json")
            if value is not None else None
            for name in type(effective).model_fields
            for value in (getattr(effective, name),)
        }
        normalized = ComparisonConfigSnapshot.from_payload(normalized_payload)
        object.__setattr__(self, "captured", normalized)
        return self


class PortfolioResearchConfig(PortfolioEvidence):
    contract_version: Literal["phase17-portfolio-research-v1"] = CONTRACT_VERSION
    budget: PortfolioCapitalBudget
    allocations: tuple[MarketResearchAllocation, ...] = Field(min_length=1, max_length=3)
    scenarios: tuple[PortfolioResearchScenario, ...] = Field(min_length=1, max_length=3)
    risk_limits: PortfolioRiskLimits
    simulated: Literal[True] = True
    execution_mode: Literal["PAPER"] = "PAPER"
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def reconcile(self):
        total = self.budget.total_equity_quote
        allocated, reserve = allocation_totals(
            total, ((x.market, x.allocated_equity_quote) for x in self.allocations))
        if reserve < self.budget.minimum_reserve_quote:
            raise ValueError("portfolio reserve minimum is not satisfied")
        by_market = {x.market: x for x in self.allocations}
        scenario_markets = [s.market for s in self.scenarios]
        if len(set(scenario_markets)) != len(scenario_markets) or set(scenario_markets) != set(by_market):
            raise ValueError("portfolio scenario markets must exactly match allocations")
        for s in self.scenarios:
            captured = s.captured.inputs()
            amount = by_market[s.market].allocated_equity_quote
            if captured.simulation.initial_equity_quote != amount:
                raise ValueError("portfolio simulation capital differs from assigned allocation")
            if captured.simulation.accounting.paper_initial_equity_quote != amount:
                raise ValueError("portfolio accounting capital differs from assigned allocation")
            if captured.simulation.accounting.enabled is not True:
                raise ValueError("portfolio accounting must remain enabled")
            if captured.simulation.accounting.max_capital_utilization > self.risk_limits.max_capital_utilization:
                raise ValueError("per-market capital utilization exceeds portfolio ceiling")
        with localcontext() as ctx:
            ctx.prec = 80
            if allocated + reserve != total:
                raise ValueError("portfolio capital must reconcile exactly")
        return self

    @property
    def allocated_equity_quote(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 80
            return sum((a.allocated_equity_quote for a in self.allocations), Decimal("0"))

    @property
    def unallocated_reserve_quote(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 80
            return self.budget.total_equity_quote - self.allocated_equity_quote

    def canonical_payload(self) -> dict:
        """Canonical market order independent of request serialization order."""
        self = type(self).model_validate(self)
        return {
            "version": self.contract_version,
            "budget": self.budget.model_dump(mode="json"),
            "allocations": [x.model_dump(mode="json") for x in
                            sorted(self.allocations, key=lambda x: MARKETS.index(x.market))],
            "scenarios": [x.model_dump(mode="json") for x in
                          sorted(self.scenarios, key=lambda x: MARKETS.index(x.market))],
            "risk_limits": self.risk_limits.model_dump(mode="json"),
            "simulated": self.simulated,
            "execution_mode": self.execution_mode,
            "read_only": self.read_only,
            "authority": self.authority,
        }

    def fingerprint(self) -> str:
        return stable_fingerprint(self.canonical_payload())


class PortfolioExposureSnapshot(PortfolioEvidence):
    """Future per-market observation. Not sufficient to aggregate a portfolio."""

    market: ResearchPerpMarketId
    source_run_fingerprint: Fingerprint
    as_of: AwareDatetime
    position_base: ExactPortfolioDecimal
    mark_price_quote: ExactPortfolioDecimal = Field(gt=0)
    gross_exposure_quote: ExactPortfolioDecimal = Field(ge=0)
    signed_exposure_quote: ExactPortfolioDecimal
    portfolio_aggregate_verified: Literal[False] = False
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"


class PortfolioResearchResult(PortfolioEvidence):
    """17.1A placeholder only: never assert results before 17.2 processing."""

    contract_version: Literal["phase17-portfolio-research-v1"] = CONTRACT_VERSION
    config_fingerprint: Fingerprint
    status: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"
    aggregate_equity_quote: None = None
    aggregate_pnl_quote: None = None
    synchronized_window_verified: Literal[False] = False
    execution_authority: Literal["NONE"] = "NONE"
    simulated: Literal[True] = True


class PortfolioResearchRunRequest(PortfolioEvidence):
    """Only configuration is accepted; client results are never evidence."""

    config: PortfolioResearchConfig
    config_fingerprint: Fingerprint

    @model_validator(mode="after")
    def execution_boundary(self):
        if self.config_fingerprint != self.config.fingerprint():
            raise ValueError("portfolio configuration fingerprint mismatch")
        inputs = [s.captured.inputs() for s in self.config.scenarios]
        if (sum(s.frames for s in self.config.scenarios) > MAX_TOTAL_FRAMES or
                sum(s.frames * i.strategy.levels_per_side for s, i in zip(self.config.scenarios, inputs))
                > MAX_QUOTE_LEVEL_FRAMES or
                sum(min(s.frames, i.simulation.trace_max_points) if i.simulation.record_trace else 0
                    for s, i in zip(self.config.scenarios, inputs)) > MAX_TOTAL_TRACE_POINTS or
                sum(i.simulation.accounting.ledger_max_entries for i in inputs) > MAX_TOTAL_LEDGER_ENTRIES or
                sum(i.simulation.accounting.event_max_entries for i in inputs) > MAX_TOTAL_EVENT_ENTRIES):
            raise ValueError("portfolio workload exceeds the shared research budget")
        return self


class PortfolioMarketExecution(PortfolioEvidence):
    """Internal full native evidence, validated before bounded projection."""

    config_fingerprint: Fingerprint
    scenario: PortfolioResearchScenario
    captured_result: CapturedScenarioResult

    @field_validator("captured_result", mode="before")
    @classmethod
    def revalidate_native(cls, value):
        if isinstance(value, CapturedScenarioResult):
            return CapturedScenarioResult.model_validate_json(value.model_dump_json())
        return value

    @model_validator(mode="after")
    def bind_market(self):
        receipt, result = self.captured_result.provenance, self.captured_result.result
        if (receipt.captured != self.scenario.captured or
                receipt.requested_scenario != self.scenario.scenario or
                receipt.requested_frames != self.scenario.frames or
                result.research_market != self.scenario.market):
            raise ValueError("portfolio native result capture or market mismatch")
        vault = result.vault
        amount = self.scenario.captured.inputs().simulation.initial_equity_quote
        if (vault is None or vault.market != self.scenario.market or vault.mode != "PAPER" or
                vault.simulated is not True or vault.accounting_complete != "COMPLETE" or
                vault.initial_equity_quote != amount or
                vault.accounting_fingerprint != result.accounting_fingerprint):
            raise ValueError("portfolio native accounting evidence unavailable")
        # Existing ledger entries are newest-first and may be a bounded suffix.
        # Verify retained hashes/links; never manufacture an entire ledger archive.
        from app.accounting.models import fingerprint as accounting_fingerprint
        ledger = result.accounting_ledger
        if bool(ledger) != bool(vault.ledger_version):
            raise ValueError("portfolio retained ledger missing")
        if ledger and (ledger[0].ledger_fingerprint != vault.ledger_fingerprint or
                       ledger[0].sequence != vault.ledger_version):
            raise ValueError("portfolio ledger head mismatch")
        for index, entry in enumerate(ledger):
            if (entry.market != self.scenario.market or entry.simulated is not True or
                    entry.ledger_fingerprint != accounting_fingerprint(
                        entry.model_dump(exclude={"ledger_fingerprint"}))):
                raise ValueError("portfolio ledger evidence mismatch")
            if index and (ledger[index - 1].previous_ledger_fingerprint != entry.ledger_fingerprint or
                          ledger[index - 1].sequence != entry.sequence + 1):
                raise ValueError("portfolio ledger chain mismatch")
        if any(item.get("market") != self.scenario.market or not (
                   item.get("source") in {"SIMULATED PAPER FILL", "HYPOTHETICAL MODELED PAPER FILL"} or
                   str(item.get("source", "")).startswith("HYPOTHETICAL MODELED PAPER FILL:"))
               for item in result.fills):
            raise ValueError("portfolio fill market mismatch")
        if any(item.get("market") != self.scenario.market for item in result.orders):
            raise ValueError("portfolio order market mismatch")
        accounting_canonical(result)  # Reject nonfinite native financial evidence.
        return self


EXECUTION_LIMITATIONS = (
    "Independent deterministic DEMO/PAPER scenarios; no authenticated or synchronized historical market windows.",
    "Per-market metrics are original engine outputs; no portfolio equity, PnL, return, drawdown or ranking is calculated.",
    "Capital allocations constrain configuration; reserve is unexecuted. Shared-capital risk enforcement is deferred to Phase 17.3.",
    "Receipts are same-job service bindings, not signatures or independent engine attestations. Full results are validated before projection.",
    "Orders, fills, traces and ledger rows are omitted from transport; original full-result hashes are preserved, not hashes of a replacement result.",
    "Local in-process research only; no durable recovery, authoritative cancellation or per-frame progress.",
)


def fingerprinted(model, **values):
    """Include typed defaults using the existing canonical fingerprint function."""
    field = "receipt_fingerprint" if model is PortfolioMarketReceipt else "bundle_fingerprint"
    payload = model.model_construct(**values).model_dump(exclude={field}, mode="json")
    return model(**values, **{field: stable_fingerprint(payload)})


class PortfolioMarketReceipt(PortfolioEvidence):
    config_fingerprint: Fingerprint
    market: ResearchPerpMarketId
    status: Literal["COMPLETED"] = "COMPLETED"
    provenance: ScenarioProvenanceReceipt
    metrics: SimulationMetrics
    vault: VaultSnapshot
    market_assumptions: ResearchMarketAssumptions
    execution_assumptions: PaperExecutionAssumptions
    accounting_fingerprint: Fingerprint
    retained_ledger_fingerprint: Fingerprint
    retained_ledger_entries: StrictInt = Field(ge=0, le=500)
    original_trace_points: StrictInt = Field(ge=0, le=1500)
    receipt_fingerprint: Fingerprint
    execution_mode: Literal["PAPER"] = "PAPER"
    simulated: Literal[True] = True
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    @field_validator("provenance", "metrics", "vault", "market_assumptions", "execution_assumptions", mode="before")
    @classmethod
    def detached_native(cls, value, info):
        model = cls.model_fields[info.field_name].annotation
        if isinstance(value, model):
            return model.model_validate_json(value.model_dump_json())
        return value

    @model_validator(mode="after")
    def validate_projection(self):
        inputs = self.provenance.captured.inputs()
        if (self.market != inputs.strategy.market or self.market != self.vault.market or
                self.market != self.market_assumptions.market or
                self.provenance.requested_frames != self.metrics.frame_count or
                self.market_assumptions.frame_count != self.metrics.frame_count or
                self.market_assumptions.scenario != self.provenance.requested_scenario.value or
                self.market_assumptions.dataset_fingerprint != self.provenance.dataset_fingerprint or
                self.market_assumptions.market_profile_fingerprint != self.provenance.captured.market_profile_fingerprint or
                self.execution_assumptions.fingerprint != self.provenance.captured.execution_fingerprint or
                self.metrics.starting_equity != inputs.simulation.initial_equity_quote or
                self.vault.initial_equity_quote != self.metrics.starting_equity or
                self.vault.accounting_fingerprint != self.accounting_fingerprint or
                self.vault.mode != "PAPER" or self.vault.simulated is not True or
                self.vault.accounting_complete != "COMPLETE"):
            raise ValueError("portfolio market receipt evidence mismatch")
        accounting_canonical(self.metrics)
        if self.receipt_fingerprint != stable_fingerprint(self.model_dump(exclude={"receipt_fingerprint"}, mode="json")):
            raise ValueError("portfolio market receipt fingerprint mismatch")
        return self


class PortfolioExecutedResult(PortfolioEvidence):
    """17.2 complete result bundle; 17.1A NOT_EXECUTED remains unchanged."""

    contract_version: Literal["phase172-executed-v1"] = "phase172-executed-v1"
    config: PortfolioResearchConfig
    config_fingerprint: Fingerprint
    selected_markets: tuple[ResearchPerpMarketId, ...] = Field(min_length=1, max_length=3)
    markets: tuple[PortfolioMarketReceipt, ...] = Field(min_length=1, max_length=3)
    unallocated_reserve_quote: ExactPortfolioDecimal = Field(ge=0)
    status: Literal["COMPLETED"] = "COMPLETED"
    validation_status: Literal["VALIDATED"] = "VALIDATED"
    execution_mode: Literal["PAPER"] = "PAPER"
    simulated: Literal[True] = True
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"
    synchronized_market_windows_verified: Literal[False] = False
    portfolio_economics_verified: Literal[False] = False
    limitations: tuple[str, ...] = EXECUTION_LIMITATIONS
    bundle_fingerprint: Fingerprint

    @model_validator(mode="after")
    def validate_bundle(self):
        PortfolioResearchRunRequest(config=self.config, config_fingerprint=self.config_fingerprint)
        scenarios = sorted(self.config.scenarios, key=lambda s: MARKETS.index(s.market))
        if (self.selected_markets != tuple(s.market for s in scenarios) or
                tuple(r.market for r in self.markets) != self.selected_markets or
                self.unallocated_reserve_quote != self.config.unallocated_reserve_quote or
                self.limitations != EXECUTION_LIMITATIONS):
            raise ValueError("portfolio bundle incomplete or market/reserve mismatch")
        for s, r in zip(scenarios, self.markets):
            if (r.config_fingerprint != self.config_fingerprint or
                    r.provenance.captured != s.captured or
                    r.provenance.requested_scenario != s.scenario or
                    r.provenance.requested_frames != s.frames):
                raise ValueError("portfolio bundle substituted market evidence")
        if self.bundle_fingerprint != stable_fingerprint(self.model_dump(exclude={"bundle_fingerprint"}, mode="json")):
            raise ValueError("portfolio bundle fingerprint mismatch")
        return self


# Phase 17.3 types deliberately leave the configuration and 17.2 wire identity
# untouched. Internal observations never become client accounting authority.
def sealed(model, **values):
    payload = model.model_construct(**values).model_dump(exclude={"evidence_fingerprint"}, mode="json")
    return model(**values, evidence_fingerprint=stable_fingerprint(payload))


class AnalysisEvidence(PortfolioEvidence):
    evidence_fingerprint: Fingerprint

    @model_validator(mode="after")
    def verify_identity(self):
        if self.evidence_fingerprint != stable_fingerprint(
                self.model_dump(exclude={"evidence_fingerprint"}, mode="json")):
            raise ValueError("portfolio analysis evidence fingerprint mismatch")
        return self


class PortfolioRiskPolicy(PortfolioEvidence):
    warning_ratio: ExactPortfolioDecimal = Field(default=Decimal("0.8"), gt=0, lt=1)
    reduction_ratio: ExactPortfolioDecimal = Field(default=Decimal("0.95"), gt=0, lt=1)
    missing_critical_evidence: Literal["BLOCKED"] = "BLOCKED"

    @model_validator(mode="after")
    def ordered(self):
        if self.warning_ratio >= self.reduction_ratio:
            raise ValueError("warning must precede reduction and hard limit")
        return self


class PortfolioAnalysisRequest(PortfolioResearchRunRequest):
    risk_policy: PortfolioRiskPolicy = Field(default_factory=PortfolioRiskPolicy)


class NativeAccountingObservation(PortfolioEvidence):
    sequence: StrictInt = Field(ge=1, le=3000)
    timestamp: AwareDatetime
    equity_quote: FinancialDecimal
    session_pnl_quote: FinancialDecimal
    position_base: FinancialDecimal
    mark_price_quote: PositiveDecimal


class MarketAccountingEvidence(AnalysisEvidence):
    """Bounded, internal projection made from the accepted full native result."""
    market: ResearchPerpMarketId
    market_receipt_fingerprint: Fingerprint
    observations: tuple[NativeAccountingObservation, ...] = Field(max_length=1500)


class MarketObservationClock(AnalysisEvidence):
    market: ResearchPerpMarketId
    market_receipt_fingerprint: Fingerprint
    native_evidence_fingerprint: Fingerprint
    scenario: ScenarioName
    engine_version: str = Field(min_length=1, max_length=96)
    frames: StrictInt = Field(ge=2, le=3000)
    expected_retained: StrictInt = Field(ge=0, le=1500)
    retained: StrictInt = Field(ge=0, le=1500)
    start_at: AwareDatetime
    final_at: AwareDatetime
    complete: bool
    valid: bool
    clock: Literal["DETERMINISTIC_SCENARIO_UTC_1S_V1"] = "DETERMINISTIC_SCENARIO_UTC_1S_V1"


class PortfolioTemporalReport(AnalysisEvidence):
    contract_version: Literal["phase173-temporal-v1"] = "phase173-temporal-v1"
    classification: Literal["MODELED_ALIGNED", "FINAL_ONLY", "INCOMPARABLE", "UNAVAILABLE"]
    clocks: tuple[MarketObservationClock, ...] = Field(min_length=1, max_length=3)
    reasons: tuple[str, ...] = Field(min_length=1, max_length=10)
    historical_market_synchronization_verified: Literal[False] = False
    methodology: Literal["INDEPENDENT_PAPER_COMMON_SCENARIO_CLOCK"] = "INDEPENDENT_PAPER_COMMON_SCENARIO_CLOCK"


class PortfolioDrawdownEvidence(AnalysisEvidence):
    observation_count: StrictInt = Field(ge=2, le=1500)
    equity_series_fingerprint: Fingerprint
    native_evidence_fingerprints: tuple[Fingerprint, ...] = Field(min_length=1, max_length=3)
    peak_equity_quote: PositiveDecimal
    ending_drawdown_fraction: NonnegativeDecimal
    max_drawdown_fraction: NonnegativeDecimal

    @model_validator(mode="after")
    def valid_drawdown(self):
        if self.max_drawdown_fraction < self.ending_drawdown_fraction:
            raise ValueError("maximum drawdown below ending drawdown")
        return self


class MarketEconomicContribution(PortfolioEvidence):
    market: ResearchPerpMarketId
    market_receipt_fingerprint: Fingerprint
    equity_quote: FinancialDecimal
    net_pnl_quote: FinancialDecimal
    realized_pnl_quote: FinancialDecimal
    unrealized_pnl_quote: FinancialDecimal
    fees_quote: NonnegativeDecimal
    funding_quote: FinancialDecimal


class PortfolioAccountingReport(AnalysisEvidence):
    contract_version: Literal["phase173-accounting-v1"] = "phase173-accounting-v1"
    methodology: Literal["INDEPENDENT_CAPITAL_PAPER_NATIVE_EQUITY_V1"] = "INDEPENDENT_CAPITAL_PAPER_NATIVE_EQUITY_V1"
    quote_currency: Literal["USDC"] = "USDC"
    config_fingerprint: Fingerprint
    temporal_fingerprint: Fingerprint
    initial_capital_quote: PositiveDecimal
    allocated_capital_quote: PositiveDecimal
    reserve_quote: NonnegativeDecimal
    capital_allocation_utilization: NonnegativeDecimal
    contributions: tuple[MarketEconomicContribution, ...] = Field(min_length=1, max_length=3)
    equity_quote: FinancialDecimal | None
    pnl_quote: FinancialDecimal | None
    session_loss_quote: NonnegativeDecimal | None
    native_rounding_residual_quote: FinancialDecimal | None
    drawdown: PortfolioDrawdownEvidence | None
    status: Literal["SUPPORTED", "UNAVAILABLE"]


class MarketExposure(PortfolioEvidence):
    market: ResearchPerpMarketId
    market_receipt_fingerprint: Fingerprint
    source_run_fingerprint: Fingerprint
    market_profile_fingerprint: Fingerprint
    valuation_at: AwareDatetime
    base_currency: ResearchPerpMarketId
    quote_currency: Literal["USDC"] = "USDC"
    position_base: FinancialDecimal
    mark_price_quote: PositiveDecimal
    signed_exposure_quote: FinancialDecimal
    gross_concentration: NonnegativeDecimal | None


class PortfolioExposureReport(AnalysisEvidence):
    contract_version: Literal["phase173-exposure-v1"] = "phase173-exposure-v1"
    temporal_fingerprint: Fingerprint
    accounting_fingerprint: Fingerprint
    positions: tuple[MarketExposure, ...] = Field(min_length=1, max_length=3)
    gross_exposure_quote: NonnegativeDecimal | None
    net_exposure_quote: FinancialDecimal | None
    max_inventory_concentration: NonnegativeDecimal | None
    gross_notional_utilization: NonnegativeDecimal | None
    modeled_leverage: NonnegativeDecimal | None
    reserved_capital_quote: NonnegativeDecimal | None
    reserved_capital_utilization: NonnegativeDecimal | None
    pending_order_exposure_quote: None = None
    methodology: Literal["FILLED_BASE_TIMES_NATIVE_MARK_USDC_V1"] = "FILLED_BASE_TIMES_NATIVE_MARK_USDC_V1"


class PortfolioRiskCheck(PortfolioEvidence):
    limit: Literal["max_gross_exposure_quote", "max_abs_net_exposure_quote", "max_inventory_concentration",
                   "max_capital_utilization", "modeled_leverage_ceiling", "max_session_loss_quote", "max_drawdown_fraction"]
    observed: NonnegativeDecimal | None
    ceiling: NonnegativeDecimal
    state: Literal["NORMAL", "WARN", "REDUCE", "HALT", "UNAVAILABLE"]


class PortfolioRiskReport(AnalysisEvidence):
    contract_version: Literal["phase173-risk-v1"] = "phase173-risk-v1"
    config_fingerprint: Fingerprint
    risk_configuration_fingerprint: Fingerprint
    accounting_fingerprint: Fingerprint
    exposure_fingerprint: Fingerprint
    temporal_fingerprint: Fingerprint
    policy: PortfolioRiskPolicy
    outcome: Literal["ASSESSED", "BLOCKED"]
    decision: Literal["NORMAL", "WARN", "REDUCE", "HALT"] | None
    checks: tuple[PortfolioRiskCheck, ...] = Field(min_length=7, max_length=7)
    reasons: tuple[str, ...] = Field(min_length=1, max_length=10)
    risk_compliant: bool
    evaluation_scope: Literal["TERMINAL_LIMITS_AND_COMPLETE_HISTORY_MAX_DRAWDOWN"] = "TERMINAL_LIMITS_AND_COMPLETE_HISTORY_MAX_DRAWDOWN"
    operational_authority: Literal["NONE"] = "NONE"
    historical_orders_prevented: Literal[False] = False


ANALYSIS_LIMITATIONS = (
    "Independent-capital hypothetical PAPER model, including unexecuted USDC reserve; no cross-margin account or borrowing.",
    "A common modeled scenario clock is not authenticated historical exchange synchronization.",
    "FINAL_ONLY compares independent endpoints on the same scenario/window; no synchronized equity history or drawdown is claimed.",
    "Risk evaluates terminal limits and, only with complete aligned traces, full-history maximum portfolio drawdown; it does not prevent already executed PAPER orders.",
    "Native Decimal accounting uses 28-digit arithmetic; exact aggregate reconciliation discloses its rounding residual without changing fees/funding.",
    "Fingerprints bind same-job evidence, not signatures; omitted native histories cannot be independently reconstructed from this receipt.",
    "Reservations are native simulated full-notional reservations, not venue margin; pending-order exposure is unavailable.",
)


class PortfolioAnalysisResult(AnalysisEvidence):
    contract_version: Literal["phase173-analysis-v1"] = "phase173-analysis-v1"
    execution: PortfolioExecutedResult
    temporal: PortfolioTemporalReport
    accounting: PortfolioAccountingReport
    exposure: PortfolioExposureReport
    risk: PortfolioRiskReport
    limitations: tuple[str, ...] = ANALYSIS_LIMITATIONS
    simulated: Literal[True] = True
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"
    historical_market_synchronization_verified: Literal[False] = False

    @model_validator(mode="wrap")
    @classmethod
    def native_validation_context(cls, value, handler):
        with localcontext() as ctx:
            ctx.prec = 28
            ctx.rounding = "ROUND_HALF_EVEN"
            return handler(value)

    @model_validator(mode="after")
    def verify_analysis(self):
        from .aggregation import verify_analysis
        verify_analysis(self)
        return self
