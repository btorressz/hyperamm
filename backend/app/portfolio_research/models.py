"""Phase 17.1A immutable contract boundary for shared-capital PAPER research.

This package defines inputs and future evidence shapes only. No result here
establishes synchronized market windows, aggregated equity or executed orders.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Literal

from pydantic import AwareDatetime, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.accounting.models import canonical
from app.market_data.live_models import Evidence
from app.research_replay.comparison import ComparisonConfigSnapshot
from app.research_replay.models import Fingerprint
from app.simulation.market_profiles import MARKETS, ResearchPerpMarketId
from app.simulation.models import stable_fingerprint
from app.simulation.scenarios import ScenarioName
from .allocation import allocation_totals
from .config import ExactPortfolioDecimal, MAX_PORTFOLIO_CAPITAL

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
