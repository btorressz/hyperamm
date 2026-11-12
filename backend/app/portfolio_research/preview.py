"""Stateless configuration preparation using trusted research constructors."""
from decimal import Decimal, localcontext
from typing import Literal
from pydantic import Field, StrictBool, StrictInt, model_validator
from app.agents.config import AgentConfig
from app.amm.models import AmmModel
from app.risk.firewall import RiskFirewallConfig
from app.strategy.models import StrategyConfig
from app.execution.research import PaperExecutionAssumptions
from app.research_replay.comparison import ComparisonConfigSnapshot
from app.simulation.config import SimulationConfig
from app.simulation.market_profiles import MARKETS, research_strategy
from app.simulation.research_vault import ResearchVaultConfig
from app.simulation.scenarios import ScenarioName
from .config import (ExactPortfolioDecimal, MAX_TOTAL_FRAMES, MAX_QUOTE_LEVEL_FRAMES,
    MAX_TOTAL_TRACE_POINTS, MAX_TOTAL_LEDGER_ENTRIES, MAX_TOTAL_EVENT_ENTRIES, MAX_RESPONSE_BYTES)
from .models import (PortfolioEvidence, PortfolioCapitalBudget, MarketResearchAllocation,
    PortfolioRiskLimits, PortfolioResearchConfig, PortfolioResearchScenario,
    PortfolioResearchRunRequest, PortfolioRiskPolicy, PortfolioStressRequest, PortfolioStressScenario)


class StrategyDraft(PortfolioEvidence):
    amm_model: AmmModel = AmmModel.CONSTANT_PRODUCT
    levels_per_side: StrictInt = Field(default=8, ge=1, le=50)
    max_distance_bps: ExactPortfolioDecimal = Field(default=Decimal("100"), gt=0, le=2500)
    base_order_size: ExactPortfolioDecimal = Field(default=Decimal("0.1"), gt=0, le=10)
    total_liquidity: ExactPortfolioDecimal = Field(default=Decimal("4"), gt=0, le=1000)
    concentration_factor: ExactPortfolioDecimal = Field(default=Decimal("8"), ge=0, le=1000)
    inventory_skew_enabled: StrictBool = True
    market_adaptation_enabled: StrictBool = True


class PaperDraft(PortfolioEvidence):
    fee_enabled: StrictBool = False
    maker_fee_bps: ExactPortfolioDecimal = Field(default=Decimal("1"), ge=0, le=100)
    taker_fee_bps: ExactPortfolioDecimal = Field(default=Decimal("3"), ge=0, le=100)
    funding_enabled: StrictBool = True
    funding_interval_seconds: Literal[1, 60, 300, 3600, 28800, 86400] = 1
    execution: PaperExecutionAssumptions = Field(default_factory=PaperExecutionAssumptions)


class PortfolioDraft(PortfolioEvidence):
    budget: PortfolioCapitalBudget
    allocations: tuple[MarketResearchAllocation, ...] = Field(min_length=1, max_length=3)
    risk_limits: PortfolioRiskLimits
    risk_policy: PortfolioRiskPolicy = Field(default_factory=PortfolioRiskPolicy)
    strategy: StrategyDraft = Field(default_factory=StrategyDraft)
    paper: PaperDraft = Field(default_factory=PaperDraft)
    frames: StrictInt = Field(default=120, ge=2, le=3000)
    scenario: ScenarioName = ScenarioName.FLASH_MOVE
    stress: PortfolioStressScenario | None = None

    @model_validator(mode="after")
    def unique_markets(self):
        if len({a.market for a in self.allocations}) != len(self.allocations):
            raise ValueError("duplicate portfolio allocation")
        return self


class PreviewResult(PortfolioEvidence):
    contract_version: Literal["phase175-preview-v1"] = "phase175-preview-v1"
    config: PortfolioResearchConfig
    config_fingerprint: str
    risk_policy: PortfolioRiskPolicy
    stress: PortfolioStressScenario | None
    allocated_quote: ExactPortfolioDecimal
    reserve_quote: ExactPortfolioDecimal
    allocation_percentages: dict[str, str]
    workload: dict[str, int]
    workload_limits: dict[str, int] = Field(default_factory=lambda: dict(
        selected_markets=3, executed_frames=MAX_TOTAL_FRAMES,
        quote_level_frames=MAX_QUOTE_LEVEL_FRAMES, native_observations=MAX_TOTAL_TRACE_POINTS,
        ledger_entries=MAX_TOTAL_LEDGER_ENTRIES, event_entries=MAX_TOTAL_EVENT_ENTRIES,
        request_bytes=65536, response_bytes=MAX_RESPONSE_BYTES, chart_observations_per_leg=120))
    trace_eligibility: Literal["MODELED_ALIGNED", "FINAL_ONLY"]
    simulated: Literal[True] = True
    execution_mode: Literal["PAPER"] = "PAPER"
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"


def prepare(draft, profiles):
    draft = PortfolioDraft.model_validate(draft)
    legs = 2 if draft.stress else 1
    count = len(draft.allocations)
    retention = min(draft.frames, 1500 // (count * legs))
    scenarios = []
    for a in sorted(draft.allocations, key=lambda a: MARKETS.index(a.market)):
        selected = profiles[a.market]
        strategy = research_strategy(StrategyConfig(**draft.strategy.model_dump()), selected)
        vault = ResearchVaultConfig(initial_equity_quote=a.allocated_equity_quote,
            paper_fee_model_enabled=draft.paper.fee_enabled,
            paper_maker_fee_bps=draft.paper.maker_fee_bps, paper_taker_fee_bps=draft.paper.taker_fee_bps,
            paper_funding_accounting_enabled=draft.paper.funding_enabled,
            paper_funding_interval_seconds=draft.paper.funding_interval_seconds,
            max_capital_utilization=draft.risk_limits.max_capital_utilization)
        simulation = vault.to_simulation(SimulationConfig(max_frames=draft.frames, trace_max_points=retention))
        # Existing administrative bounds are shared across both stress legs.
        accounting = simulation.accounting.model_copy(update={"ledger_max_entries": 5000, "event_max_entries": 125})
        simulation = SimulationConfig.model_validate({**simulation.model_dump(),
            "accounting": accounting, "execution": draft.paper.execution})
        captured = ComparisonConfigSnapshot.from_payload(dict(strategy=strategy.model_dump(mode="json"),
            agents=AgentConfig().model_dump(mode="json"), risk=RiskFirewallConfig().model_dump(mode="json"),
            simulation=simulation.model_dump(mode="json"), market_profile=selected.model_dump(mode="json")))
        scenarios.append(PortfolioResearchScenario(market=a.market, scenario=draft.scenario,
            frames=draft.frames, captured=captured))
    config = PortfolioResearchConfig(budget=draft.budget, allocations=draft.allocations,
        risk_limits=draft.risk_limits, scenarios=tuple(scenarios))
    request = PortfolioResearchRunRequest(config=config, config_fingerprint=config.fingerprint())
    if draft.stress:
        PortfolioStressRequest(**request.model_dump(), risk_policy=draft.risk_policy, scenario=draft.stress)
    from .scenarios import workload
    costs = workload(config)
    with localcontext() as ctx:
        ctx.prec = 80
        percentages = {a.market: format(a.allocated_equity_quote / config.budget.total_equity_quote * 100, ".4f")
            for a in config.allocations}
    return PreviewResult(config=config, config_fingerprint=config.fingerprint(), risk_policy=draft.risk_policy,
        stress=draft.stress, allocated_quote=config.allocated_equity_quote, reserve_quote=config.unallocated_reserve_quote,
        allocation_percentages=percentages, workload=dict(zip(
            ("executed_frames", "quote_level_frames", "native_observations", "ledger_entries", "event_entries"),
            (c * legs for c in costs))), trace_eligibility="MODELED_ALIGNED" if retention == draft.frames else "FINAL_ONLY")
