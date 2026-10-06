from __future__ import annotations

from app.agents.config import AgentConfig
from app.market_data.models import MarketDataMode
from app.risk.firewall import RiskFirewallConfig
from app.strategy.models import ExecutionMode,StrategyConfig

from .config import OptimizationObjectiveConfig,SimulationConfig
from .engine import SimulationEngine
from .optimizer import StrategyOptimizer
from .scenarios import generate_scenario,scenario_catalog


class SimulationService:
    def __init__(self):
        self.engine=SimulationEngine()
        self.optimizer=StrategyOptimizer(self.engine)

    @staticmethod
    def research_strategy(config:StrategyConfig)->StrategyConfig:
        payload=config.model_dump()
        payload["execution_mode"]=ExecutionMode.PAPER
        payload["market_data_mode"]=MarketDataMode.DEMO
        return StrategyConfig.model_validate(payload)

    def scenarios(self):
        return scenario_catalog()

    async def run_scenario(
        self,*,scenario:str,frames:int,strategy:StrategyConfig,agents:AgentConfig,
        risk:RiskFirewallConfig,simulation:SimulationConfig,
    ):
        strategy_copy=self.research_strategy(strategy.model_copy(deep=True))
        dataset=generate_scenario(scenario,frames=frames,market=strategy_copy.market)
        return await self.engine.run(
            dataset=dataset,strategy_config=strategy_copy,agent_config=agents.model_copy(deep=True),
            risk_config=risk.model_copy(deep=True),simulation_config=simulation.model_copy(deep=True),
            scenario=scenario,
        )

    async def optimize(
        self,*,strategy:StrategyConfig,agents:AgentConfig,risk:RiskFirewallConfig,
        simulation:SimulationConfig,strategy_grid:dict,agent_grid:dict,
        training_scenarios:list[str],validation_scenarios:list[str],
        objective:OptimizationObjectiveConfig,max_candidates:int,frames:int,top_n:int,
    ):
        strategy_copy=self.research_strategy(strategy.model_copy(deep=True))
        return await self.optimizer.optimize(
            baseline_strategy=strategy_copy,baseline_agents=agents.model_copy(deep=True),
            risk_config=risk.model_copy(deep=True),simulation_config=simulation.model_copy(deep=True),
            strategy_grid=strategy_grid,agent_grid=agent_grid,training_scenarios=training_scenarios,
            validation_scenarios=validation_scenarios,objective=objective,max_candidates=max_candidates,
            frames=frames,top_n=top_n,
        )
