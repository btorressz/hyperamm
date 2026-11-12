"""Sequential composition inside one admitted job, never child admissions."""
from app.simulation.market_profiles import MARKETS
from .aggregation import project_market
from .models import PortfolioResearchConfig, PortfolioResearchRunRequest, PortfolioMarketExecution


async def execute_markets(service, config: PortfolioResearchConfig, *, collect_accounting=False, _datasets=None):
    config = PortfolioResearchConfig.model_validate(config)
    fingerprint = config.fingerprint()
    PortfolioResearchRunRequest(config=config, config_fingerprint=fingerprint)
    if _datasets is not None and set(_datasets) != {s.market for s in config.scenarios}:
        raise ValueError("trusted dataset market set mismatch")
    receipts = []
    observations = []
    for scenario in sorted(config.scenarios, key=lambda s: MARKETS.index(s.market)):
        inputs = scenario.captured.inputs()
        # SimulationEngine.run constructs clock, paper adapter, order manager,
        # history, telemetry, agents, firewall, inventory/accounting and metrics
        # as run-local objects. The reused engine retains only network_access=False.
        # Native isolation tests retain those objects and compare standalone runs.
        if _datasets is None:
            captured = await service.run_scenario(
                scenario=scenario.scenario.value, frames=scenario.frames,
                strategy=inputs.strategy, agents=inputs.agents, risk=inputs.risk,
                simulation=inputs.simulation, market_profile=inputs.market_profile,
                preserve_captured_strategy=True, include_comparison_provenance=True)
        else:
            captured = await service._run_portfolio_dataset(scenario=scenario, dataset=_datasets[scenario.market])
            if captured.provenance.dataset_fingerprint != _datasets[scenario.market].fingerprint:
                raise ValueError("engine substituted trusted portfolio dataset")
        evidence = PortfolioMarketExecution(config_fingerprint=fingerprint,
            scenario=scenario, captured_result=captured)
        receipt = project_market(evidence)
        receipts.append(receipt)
        if collect_accounting:
            from .accounting import collect_native_accounting
            observations.append(collect_native_accounting(evidence, receipt))
        # Only bounded receipts/optional observations survive into the next
        # market. Full native output belongs to this iteration; no retry.
        del evidence, captured
    if collect_accounting:
        return tuple(receipts), tuple(observations)
    return tuple(receipts)
