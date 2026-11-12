"""Sequential composition inside one admitted job, never child admissions."""
from app.simulation.market_profiles import MARKETS
from .aggregation import project_market
from .models import PortfolioResearchConfig, PortfolioResearchRunRequest, PortfolioMarketExecution


async def execute_markets(service, config: PortfolioResearchConfig):
    config = PortfolioResearchConfig.model_validate(config)
    fingerprint = config.fingerprint()
    PortfolioResearchRunRequest(config=config, config_fingerprint=fingerprint)
    receipts = []
    for scenario in sorted(config.scenarios, key=lambda s: MARKETS.index(s.market)):
        inputs = scenario.captured.inputs()
        # SimulationEngine.run constructs clock, paper adapter, order manager,
        # history, telemetry, agents, firewall, inventory/accounting and metrics
        # as run-local objects. The reused engine retains only network_access=False.
        # Native isolation tests retain those objects and compare standalone runs.
        captured = await service.run_scenario(
            scenario=scenario.scenario.value, frames=scenario.frames,
            strategy=inputs.strategy, agents=inputs.agents, risk=inputs.risk,
            simulation=inputs.simulation, market_profile=inputs.market_profile,
            preserve_captured_strategy=True, include_comparison_provenance=True)
        evidence = PortfolioMarketExecution(config_fingerprint=fingerprint,
            scenario=scenario, captured_result=captured)
        receipts.append(project_market(evidence))
        # Only bounded receipts survive into the next market. Full native output
        # and dataset belong to this iteration; a failure stops without retry.
        del evidence, captured
    return tuple(receipts)
