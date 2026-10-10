from __future__ import annotations

from app.agents.config import AgentConfig
from app.market_data.models import MarketDataMode
from app.risk.firewall import RiskFirewallConfig
from app.strategy.models import ExecutionMode,StrategyConfig

from .config import OptimizationObjectiveConfig,SimulationConfig
from .engine import SimulationEngine
from .optimizer import StrategyOptimizer
from .scenarios import generate_scenario,scenario_catalog
from .research_vault import LIMITATIONS, ResearchProposal, ResearchComparisonResult, result_deltas
from .market_profiles import research_strategy as adapt_market_strategy


class SimulationService:
    def __init__(self):
        self.engine=SimulationEngine()
        self.optimizer=StrategyOptimizer(self.engine)

    @staticmethod
    def research_strategy(config:StrategyConfig, market_profile=None)->StrategyConfig:
        if market_profile is not None:
            return adapt_market_strategy(config, market_profile)
        payload=config.model_dump()
        payload["execution_mode"]=ExecutionMode.PAPER
        payload["market_data_mode"]=MarketDataMode.DEMO
        return StrategyConfig.model_validate(payload)

    def scenarios(self):
        return scenario_catalog()

    async def compare_research_configs(self, *, scenario, frames, strategy, agents, risk,
                                       simulation, baseline: ResearchProposal, custom: ResearchProposal, market_profile=None):
        # One request captures all runtime inputs before admission. One dataset and
        # sequential fresh engine states make this a controlled accounting study.
        strategy_copy = self.research_strategy(strategy.model_copy(deep=True), market_profile)
        agents_copy, risk_copy = agents.model_copy(deep=True), risk.model_copy(deep=True)
        dataset = generate_scenario(scenario, frames=frames, market=strategy_copy.market, market_profile=market_profile)
        results = []
        for proposal in (baseline, custom):
            result = await self.engine.run(dataset=dataset, scenario=scenario,
                strategy_config=strategy_copy.model_copy(deep=True),
                agent_config=agents_copy.model_copy(deep=True), risk_config=risk_copy.model_copy(deep=True),
                simulation_config=proposal.config.to_simulation(simulation), market_profile=market_profile)
            result.research_configuration = proposal.provenance()
            results.append(result)
        old, new = results
        limitations = list(LIMITATIONS) + ["Both runs share one captured strategy/agent/risk snapshot and deterministic dataset; only research accounting assumptions differ."]
        if baseline.config.initial_equity_quote != custom.config.initial_equity_quote:
            limitations.append("Starting capital differs: interpret absolute PnL, returns and utilization in the context of different capital assumptions.")
        return ResearchComparisonResult(baseline_config_fingerprint=baseline.config.fingerprint(),
            custom_config_fingerprint=custom.config.fingerprint(), baseline_provenance=baseline.provenance(),
            custom_provenance=custom.provenance(), scenario=scenario, frame_count=frames,
            baseline_result=old, custom_result=new, comparison_deltas=result_deltas(old, new),
            risk_state_counts={"baseline": old.metrics.risk_state_counts, "custom": new.metrics.risk_state_counts},
            limitations=limitations)

    async def run_scenario(
        self,*,scenario:str,frames:int,strategy:StrategyConfig,agents:AgentConfig,
        risk:RiskFirewallConfig,simulation:SimulationConfig,market_profile=None,
    ):
        strategy_copy=self.research_strategy(strategy.model_copy(deep=True), market_profile)
        dataset=generate_scenario(scenario,frames=frames,market=strategy_copy.market,market_profile=market_profile)
        return await self.engine.run(
            dataset=dataset,strategy_config=strategy_copy,agent_config=agents.model_copy(deep=True),
            risk_config=risk.model_copy(deep=True),simulation_config=simulation.model_copy(deep=True),
            scenario=scenario,
            market_profile=market_profile,
        )

    async def optimize(
        self,*,strategy:StrategyConfig,agents:AgentConfig,risk:RiskFirewallConfig,
        simulation:SimulationConfig,strategy_grid:dict,agent_grid:dict,
        training_scenarios:list[str],validation_scenarios:list[str],
        objective:OptimizationObjectiveConfig,max_candidates:int,frames:int,top_n:int,market_profile=None,
    ):
        strategy_copy=self.research_strategy(strategy.model_copy(deep=True), market_profile)
        return await self.optimizer.optimize(
            baseline_strategy=strategy_copy,baseline_agents=agents.model_copy(deep=True),
            risk_config=risk.model_copy(deep=True),simulation_config=simulation.model_copy(deep=True),
            strategy_grid=strategy_grid,agent_grid=agent_grid,training_scenarios=training_scenarios,
            validation_scenarios=validation_scenarios,objective=objective,max_candidates=max_candidates,
            frames=frames,top_n=top_n,
            market_profile=market_profile,
        )
