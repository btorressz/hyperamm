"""Phase 17.1A: read-only, deterministic portfolio research contracts.

No orchestration, accounting aggregation, HTTP endpoints or trading authority.
"""
from .models import (
    PortfolioCapitalBudget, MarketResearchAllocation, PortfolioResearchScenario,
    PortfolioRiskLimits, PortfolioResearchConfig, PortfolioExposureSnapshot,
    PortfolioResearchResult,
)
from .provenance import PortfolioResearchProvenance, capture_portfolio_provenance

__all__ = [
    "PortfolioCapitalBudget", "MarketResearchAllocation", "PortfolioResearchScenario",
    "PortfolioRiskLimits", "PortfolioResearchConfig", "PortfolioExposureSnapshot",
    "PortfolioResearchResult", "PortfolioResearchProvenance", "capture_portfolio_provenance",
]
