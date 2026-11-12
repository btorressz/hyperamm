"""Portfolio coordination through the lifespan-owned SimulationService worker."""
from app.simulation.market_profiles import MARKETS
from .aggregation import assemble_bundle
from .models import PortfolioResearchConfig, PortfolioResearchRunRequest
from .orchestration import execute_markets
from .provenance import capture_portfolio_provenance


async def run_portfolio_research(service, *, request):
    request = PortfolioResearchRunRequest.model_validate(request)
    # Use one canonical wire order as well as canonical configuration identity.
    raw = request.config.model_dump()
    for name in ("allocations", "scenarios"):
        raw[name] = tuple(sorted(raw[name], key=lambda item: MARKETS.index(item["market"])))
    config = PortfolioResearchConfig.model_validate(raw)
    capture_portfolio_provenance(config).verify_config(request.config)
    markets = await execute_markets(service, config)
    return assemble_bundle(config, markets)


async def analyze_portfolio_research(service, *, request):
    from .models import PortfolioAnalysisRequest
    from .aggregation import assemble_analysis
    request = PortfolioAnalysisRequest.model_validate(request)
    raw = request.config.model_dump()
    for name in ("allocations", "scenarios"):
        raw[name] = tuple(sorted(raw[name], key=lambda item: MARKETS.index(item["market"])))
    config = PortfolioResearchConfig.model_validate(raw)
    capture_portfolio_provenance(config).verify_config(request.config)
    markets, evidence = await execute_markets(service, config, collect_accounting=True)
    return assemble_analysis(config, markets, evidence, request.risk_policy)


async def stress_portfolio_research(service, *, request):
    from .stress import execute_stress
    return await execute_stress(service, request=request)
