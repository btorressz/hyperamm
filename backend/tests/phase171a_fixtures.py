"""Reusable Phase 17.1A fixture-only contract builders, no job submission."""
from __future__ import annotations

from decimal import Decimal

from app.agents.config import AgentConfig
from app.accounting.config import AccountingConfig
from app.research_replay.comparison import ComparisonConfigSnapshot
from app.risk.firewall import RiskFirewallConfig
from app.simulation.config import SimulationConfig
from app.simulation.market_profiles import (
    DEMO_PROFILES, ResearchPerpMarketMetadata, profile, research_strategy,
)
from app.simulation.models import stable_fingerprint
from app.strategy.models import StrategyConfig
from app.portfolio_research.models import (
    PortfolioCapitalBudget, MarketResearchAllocation, PortfolioRiskLimits,
    PortfolioResearchScenario, PortfolioResearchConfig,
)


def market_scenario(market: str, amount: str, **kwargs) -> PortfolioResearchScenario:
    meta = ResearchPerpMarketMetadata(
        market=market, sz_decimals=DEMO_PROFILES[market][1], asset_index=None,
        listed=None, metadata_status="DEMO_PROFILE", metadata_source="LOCAL_FIXTURE",
    )
    selected = profile(meta)
    strategy = research_strategy(StrategyConfig(), selected)
    money = Decimal(amount)
    simulation = SimulationConfig(
        initial_equity_quote=money,
        accounting=AccountingConfig(paper_initial_equity_quote=money),
        max_frames=4, trace_max_points=4,
    )
    payload = {
        "strategy": strategy.model_dump(mode="json"),
        "agents": AgentConfig().model_dump(mode="json"),
        "risk": RiskFirewallConfig().model_dump(mode="json"),
        "simulation": simulation.model_dump(mode="json"),
        "market_profile": selected.model_dump(mode="json"),
    }
    for field, value in kwargs.items():
        if field not in payload:
            raise ValueError("unsupported fixture override")
        payload[field] = value
    captured = ComparisonConfigSnapshot.from_payload(payload)
    return PortfolioResearchScenario(market=market, scenario="QUIET", frames=4, captured=captured)


def config(*, markets=("BTC", "ETH", "SOL"), amounts=("40000", "35000", "20000"),
           total="100000", minimum_reserve="0") -> PortfolioResearchConfig:
    pairs = tuple(zip(markets, amounts, strict=True))
    limits = PortfolioRiskLimits(
        max_gross_exposure_quote="100000",
        max_abs_net_exposure_quote="100000",
        max_session_loss_quote="10000",
        max_drawdown_fraction="0.20",
        max_capital_utilization="1",
        max_inventory_concentration="0.75",
        modeled_leverage_ceiling="3",
    )
    return PortfolioResearchConfig(
        budget=PortfolioCapitalBudget(total_equity_quote=total, minimum_reserve_quote=minimum_reserve),
        allocations=tuple(MarketResearchAllocation(market=m,allocated_equity_quote=a) for m,a in pairs),
        scenarios=tuple(market_scenario(m,a) for m,a in pairs),
        risk_limits=limits,
    )
