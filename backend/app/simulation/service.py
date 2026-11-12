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

    async def historical_catalog(self, *, storage_root):
        from app.research_replay.runner import catalog
        return catalog(storage_root)

    async def run_portfolio_research(self, *, request):
        from app.portfolio_research.service import run_portfolio_research
        return await run_portfolio_research(self, request=request)

    async def analyze_portfolio_research(self, *, request):
        from app.portfolio_research.service import analyze_portfolio_research
        return await analyze_portfolio_research(self, request=request)

    async def stress_portfolio_research(self, *, request):
        from app.portfolio_research.service import stress_portfolio_research
        return await stress_portfolio_research(self, request=request)

    async def terminal_portfolio_research(self, *, request):
        from app.portfolio_research.terminal import terminal_portfolio_research
        return await terminal_portfolio_research(self, request=request)

    async def _run_portfolio_dataset(self, *, scenario, dataset):
        from app.portfolio_research.models import PortfolioResearchScenario
        from app.portfolio_research.scenarios import validate_dataset
        scenario = PortfolioResearchScenario.model_validate(scenario)
        dataset = validate_dataset(dataset, scenario)
        i = scenario.captured.inputs()
        return await self._run_scenario(scenario=scenario.scenario.value, frames=scenario.frames,
            strategy=i.strategy, agents=i.agents, risk=i.risk, simulation=i.simulation,
            market_profile=i.market_profile, preserve_captured_strategy=True,
            include_comparison_provenance=True, _trusted_dataset=dataset)

    async def historical_summaries(self, *, storage_root):
        from app.research_replay.runner import summaries
        return summaries(storage_root)

    async def historical_provenance(self, *, storage_root, dataset_id):
        from app.research_replay.runner import provenance
        return provenance(storage_root, dataset_id)

    async def replay_history(self, **inputs):
        from app.research_replay.runner import replay
        return await replay(self, **inputs)

    async def compare_scenario_historical(self, *, storage_root, request, strategy, agents, risk, market_profile):
        from app.research_replay.transport import (
            ScenarioHistoricalRequest, ScenarioHistoricalResponse, SegmentIdentity, project_trace, MAX_RESPONSE_BYTES,
            comparison_history,
        )
        from app.research_replay.quantitative import compare_quantitative_paper
        from app.simulation.models import SimulationResult, stable_fingerprint
        request = ScenarioHistoricalRequest.model_validate_json(request.model_dump_json())
        if market_profile is None or market_profile.market != request.research_market:
            raise ValueError("scenario research profile mismatch")
        # All stages run sequentially inside the already admitted worker. Never
        # recursively enter execute(); no runtime/account/signer is passed here.
        historical = await comparison_history(self, storage_root=storage_root, request=request.historical,
            strategy=strategy, agents=agents, risk=risk)
        if request.segment_index >= len(historical.segments):
            raise ValueError("historical segment unavailable")
        scenario = await self.run_scenario(scenario=request.scenario.value, frames=request.frames,
            strategy=strategy, agents=agents, risk=risk, simulation=request.simulation,
            research=request.research, market_profile=market_profile, include_comparison_provenance=True)
        receipt = compare_quantitative_paper(scenario=scenario, historical=historical, segment_index=request.segment_index)
        selected = historical.segments[request.segment_index]
        archive = SimulationResult.model_validate_json(selected.simulation_result_json)
        result = ScenarioHistoricalResponse(request=request, request_fingerprint=stable_fingerprint(request), receipt=receipt,
            segment_count=len(historical.segments), segments=tuple(SegmentIdentity(
                segment_index=s.segment_index, reset_reason=s.reset_reason, frame_count=s.frame_count,
                window_start=s.frames[0].evaluated_at, window_end=s.frames[-1].evaluated_at,
                dataset_fingerprint=s.dataset_fingerprint, run_fingerprint=s.run_fingerprint,
                simulation_result_fingerprint=s.simulation_result_fingerprint) for s in historical.segments),
            provenance=historical.provenance, declared_gaps=historical.declared_gaps,
            issues=historical.issues[:100], omitted_issues=max(0,len(historical.issues)-100),
            scenario_trace=project_trace(scenario.result, receipt.foundation.classification, request),
            historical_trace=project_trace(archive, receipt.foundation.classification, request, selected.frames))
        if len(result.model_dump_json().encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ValueError("comparison response exceeds transport budget; reduce trace point limit")
        return result

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
        include_comparison_provenance:bool=False,research:ResearchProposal|None=None,
        preserve_captured_strategy:bool=False,
    ):
        return await self._run_scenario(scenario=scenario, frames=frames, strategy=strategy,
            agents=agents, risk=risk, simulation=simulation, market_profile=market_profile,
            include_comparison_provenance=include_comparison_provenance, research=research,
            preserve_captured_strategy=preserve_captured_strategy)

    async def _run_scenario(
        self, *, scenario, frames, strategy, agents, risk, simulation, market_profile=None,
        include_comparison_provenance=False, research=None, preserve_captured_strategy=False,
        _trusted_dataset=None,
    ):
        from app.research_replay.comparison import (
            CapturedScenarioResult, ComparisonConfigSnapshot, ScenarioInputCapture, ScenarioProvenanceReceipt,
        )
        if research is not None:
            research = ResearchProposal.model_validate_json(research.model_dump_json())
            simulation = research.config.to_simulation(simulation)
        simulation = SimulationConfig.model_validate_json(simulation.model_dump_json(), strict=True)
        # The engine always overrides accounting's starting capital with this
        # value. Capture that effective configuration, including without Vault.
        simulation = simulation.model_copy(update={"accounting": simulation.accounting.model_copy(
            update={"paper_initial_equity_quote": simulation.initial_equity_quote})})
        # Validate copies before adaptation, then freeze the exact effective
        # inputs. No await or operational runtime lookup occurs during capture.
        strategy_copy=StrategyConfig.model_validate_json(strategy.model_dump_json(), strict=True)
        # Portfolio captures already contain effective market-specific AMM inputs.
        # Re-adapting would replace a deliberately captured pool reference price.
        if not preserve_captured_strategy:
            strategy_copy=self.research_strategy(strategy_copy, market_profile)
        capture=ScenarioInputCapture(strategy=strategy_copy,agents=agents,risk=risk,
            simulation=simulation,market_profile=market_profile)
        snapshot=ComparisonConfigSnapshot.from_payload(capture.model_dump(mode="json"))
        # Reconstruct engine arguments from the immutable canonical snapshot.
        captured=snapshot.inputs()
        dataset = _trusted_dataset
        if dataset is None:
            dataset=generate_scenario(scenario,frames=frames,market=captured.strategy.market,
                market_profile=captured.market_profile)
        result=await self.engine.run(
            dataset=dataset,strategy_config=captured.strategy,agent_config=captured.agents,
            risk_config=captured.risk,simulation_config=captured.simulation,
            scenario=scenario,
            market_profile=captured.market_profile,
        )
        if preserve_captured_strategy and result.dataset_fingerprint != dataset.fingerprint:
            raise ValueError("captured scenario result differs from the generated dataset")
        if research is not None:
            result.research_configuration=research.provenance()
        if not include_comparison_provenance:
            return result
        receipt=ScenarioProvenanceReceipt.bind(result=result,captured=snapshot,scenario=scenario,frames=frames)
        return CapturedScenarioResult(result=result,provenance=receipt)

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
