from decimal import Decimal as D

import pytest

from app.agents.config import AgentConfig
from app.risk.firewall import RiskFirewallConfig
from app.strategy.models import StrategyConfig
from app.simulation.config import OptimizationObjectiveConfig,SimulationConfig
from app.simulation.models import CandidateEvaluation
from app.simulation.optimizer import StrategyOptimizer,candidate_ranking_key,score_metrics


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type",[RuntimeError,AttributeError,KeyError,TypeError])
async def test_unexpected_candidate_engine_errors_propagate(monkeypatch,error_type):
    from app.simulation.engine import SimulationEngine
    original=SimulationEngine.run
    calls=0
    async def fail_candidate(self,**inputs):
        nonlocal calls
        calls+=1
        if calls==2:
            raise error_type("internal candidate invariant")
        return await original(self,**inputs)
    monkeypatch.setattr(SimulationEngine,"run",fail_candidate)
    with pytest.raises(error_type,match="internal candidate invariant"):
        await StrategyOptimizer().optimize(
            baseline_strategy=StrategyConfig(),baseline_agents=AgentConfig(),risk_config=RiskFirewallConfig(),
            simulation_config=SimulationConfig(max_frames=3,record_trace=False),
            strategy_grid={"levels_per_side":[4,6]},agent_grid={},
            training_scenarios=["QUIET"],validation_scenarios=["TREND_UP"],
            objective=OptimizationObjectiveConfig(),max_candidates=2,frames=3,top_n=1,
        )
    assert calls==2


@pytest.mark.asyncio
async def test_expected_candidate_domain_value_error_is_rejected(monkeypatch):
    from app.simulation.engine import SimulationEngine
    original=SimulationEngine.run
    async def domain_failure(self,**inputs):
        if inputs["strategy_config"].levels_per_side==4:
            raise ValueError("unsupported candidate parameter combination")
        return await original(self,**inputs)
    monkeypatch.setattr(SimulationEngine,"run",domain_failure)
    result=await StrategyOptimizer().optimize(
        baseline_strategy=StrategyConfig(),baseline_agents=AgentConfig(),risk_config=RiskFirewallConfig(),
        simulation_config=SimulationConfig(max_frames=3,record_trace=False),
        strategy_grid={"levels_per_side":[4,6]},agent_grid={},
        training_scenarios=["QUIET"],validation_scenarios=["TREND_UP"],
        objective=OptimizationObjectiveConfig(),max_candidates=2,frames=3,top_n=1,
    )
    assert result.candidate_count==1
    assert len(result.rejected_candidates)==1
    assert result.rejected_candidates[0]["reason"]=="unsupported candidate parameter combination"


def test_grid_enumeration_exact_and_bounded():
    grid=StrategyOptimizer.enumerate_grid(
        {"levels_per_side":[4,8]},{"regime_spread_strength":[".2",".4"]},max_candidates=4
    )
    assert len(grid)==4
    assert {item[0]["levels_per_side"] for item in grid}=={4,8}
    with pytest.raises(ValueError,match="requested candidate count"):
        StrategyOptimizer.enumerate_grid(
            {"levels_per_side":[2,4,6]},{"regime_spread_strength":[".2",".4"]},max_candidates=5
        )


@pytest.mark.parametrize(
    "field",
    ["execution_mode","market_data_mode","hard_inventory_limit_base","reference_halt_deviation_bps","hyperliquid_private_key"],
)
def test_safety_parameters_are_explicitly_rejected(field):
    with pytest.raises(ValueError,match="cannot be optimized"):
        StrategyOptimizer.enumerate_grid({field:["x"]},{},max_candidates=4)


def test_unknown_parameter_is_rejected():
    with pytest.raises(ValueError,match="unknown StrategyConfig"):
        StrategyOptimizer.enumerate_grid({"made_up_parameter":[1,2]},{},max_candidates=4)


def test_score_components_sum_exactly():
    from app.simulation.models import SimulationMetrics
    metrics=SimulationMetrics(
        frame_count=10,starting_equity=D("1000"),ending_equity=D("1010"),session_pnl=D("10"),return_pct=D("1"),
        realized_pnl=D("10"),unrealized_pnl=D("0"),max_drawdown_pct=D(".02"),fill_count=2,buy_fill_count=1,sell_fill_count=1,
        quoted_notional=D("10000"),filled_notional=D("1000"),fill_activity_ratio=D(".1"),ending_inventory_base=D("0"),
        max_abs_inventory_base=D("1"),max_inventory_utilization=D(".2"),mean_spread_capture_bps=D("2"),
        mean_mature_markout_bps=D("-3"),adverse_fill_rate=D(".5"),keep_count=1,create_count=2,replace_count=1,cancel_count=1,
        reconciliation_churn_ratio=D(".4"),risk_state_counts={"NORMAL":9,"HALT":1},risk_halt_fraction=D(".1"),
        agent_regime_counts={"NORMAL":10},toxic_flow_state_counts={"NORMAL":10},execution_quality_state_counts={"NORMAL":10},
    )
    score=score_metrics(metrics,OptimizationObjectiveConfig())
    assert score.final_score==(
        score.return_contribution-score.drawdown_penalty-score.inventory_penalty
        -score.adverse_markout_penalty-score.churn_penalty-score.halt_penalty
    )


@pytest.mark.asyncio
async def test_optimizer_baseline_validation_isolation_and_reproducibility():
    optimizer=StrategyOptimizer()
    kwargs=dict(
        baseline_strategy=StrategyConfig(),baseline_agents=AgentConfig(),risk_config=RiskFirewallConfig(),
        simulation_config=SimulationConfig(max_frames=12,record_trace=False),
        strategy_grid={"levels_per_side":[4,6]},agent_grid={},
        training_scenarios=["QUIET","TREND_UP"],validation_scenarios=["MEAN_REVERTING"],
        objective=OptimizationObjectiveConfig(),max_candidates=4,frames=12,top_n=2,
    )
    first=await optimizer.optimize(**kwargs)
    second=await optimizer.optimize(**kwargs)
    assert first.baseline.label=="BASELINE"
    assert first.baseline.validation
    assert [(x.configuration_fingerprint,x.training_score) for x in first.ranked_candidates]==[
        (x.configuration_fingerprint,x.training_score) for x in second.ranked_candidates
    ]
    assert first.baseline.training_score==second.baseline.training_score
    assert all(item.score_delta==item.training_score-first.baseline.training_score for item in first.ranked_candidates)
    assert all(item.baseline_delta.get("objective_score")==item.score_delta for item in first.ranked_candidates)
    assert all("worst_objective_score" in item.training_aggregate for item in first.ranked_candidates)
    assert all("worst_drawdown_pct" in item.training_aggregate for item in first.ranked_candidates)


@pytest.mark.asyncio
async def test_candidate_a_b_a_state_isolation():
    from app.simulation.engine import SimulationEngine
    from app.simulation.scenarios import generate_scenario
    engine=SimulationEngine()
    data=generate_scenario("FLASH_MOVE",frames=12)
    sim=SimulationConfig(max_frames=12,record_trace=False)
    risk=RiskFirewallConfig()
    agents=AgentConfig()
    a_cfg=StrategyConfig(levels_per_side=4)
    b_cfg=StrategyConfig(levels_per_side=6)

    a1=await engine.run(dataset=data,strategy_config=a_cfg,agent_config=agents,risk_config=risk,simulation_config=sim)
    await engine.run(dataset=data,strategy_config=b_cfg,agent_config=agents,risk_config=risk,simulation_config=sim)
    a2=await engine.run(dataset=data,strategy_config=a_cfg,agent_config=agents,risk_config=risk,simulation_config=sim)
    assert a1.metrics==a2.metrics
    assert a1.orders==a2.orders
    assert a1.fills==a2.fills


@pytest.mark.asyncio
async def test_candidate_run_order_independence():
    from app.simulation.engine import SimulationEngine
    from app.simulation.scenarios import generate_scenario
    engine=SimulationEngine()
    data=generate_scenario("MEAN_REVERTING",frames=10)
    sim=SimulationConfig(max_frames=10,record_trace=False)
    configs=[StrategyConfig(levels_per_side=n) for n in (4,6,8)]

    first={}
    for config in configs:
        result=await engine.run(dataset=data,strategy_config=config,agent_config=AgentConfig(),risk_config=RiskFirewallConfig(),simulation_config=sim)
        first[config.levels_per_side]=(result.run_fingerprint,result.metrics)

    second={}
    for config in reversed(configs):
        result=await engine.run(dataset=data,strategy_config=config,agent_config=AgentConfig(),risk_config=RiskFirewallConfig(),simulation_config=sim)
        second[config.levels_per_side]=(result.run_fingerprint,result.metrics)

    assert first==second


@pytest.mark.asyncio
async def test_invalid_strategy_and_agent_candidates_are_reported():
    optimizer=StrategyOptimizer()
    result=await optimizer.optimize(
        baseline_strategy=StrategyConfig(),baseline_agents=AgentConfig(),risk_config=RiskFirewallConfig(),
        simulation_config=SimulationConfig(max_frames=6,record_trace=False),
        strategy_grid={"concentration_lower_bps":["300"]},agent_grid={"regime_spread_strength":["2"]},
        training_scenarios=["QUIET"],validation_scenarios=["TREND_UP"],
        objective=OptimizationObjectiveConfig(),max_candidates=4,frames=6,top_n=1,
    )
    assert result.baseline.label=="BASELINE"
    assert result.rejected_candidates
    assert result.candidate_count==0


def test_stable_tie_breaking_uses_drawdown_inventory_churn_then_fingerprint():
    common=dict(
        label="X",strategy_updates={},agent_updates={},training=[],validation=[],
        training_score=D("10"),validation_score=None,score_delta=None,baseline_delta={},
        validation_aggregate={},
    )
    a=CandidateEvaluation(
        **common,configuration_fingerprint="b",
        training_aggregate={"worst_drawdown_pct":D(".02"),"max_inventory_utilization":D(".3"),"mean_churn_ratio":D(".2")},
    )
    b=CandidateEvaluation(
        **common,configuration_fingerprint="a",
        training_aggregate={"worst_drawdown_pct":D(".01"),"max_inventory_utilization":D(".9"),"mean_churn_ratio":D(".9")},
    )
    assert sorted([a,b],key=candidate_ranking_key)[0] is b

    c=CandidateEvaluation(
        **common,configuration_fingerprint="a",
        training_aggregate={"worst_drawdown_pct":D(".02"),"max_inventory_utilization":D(".3"),"mean_churn_ratio":D(".2")},
    )
    assert sorted([a,c],key=candidate_ranking_key)[0] is c


@pytest.mark.asyncio
async def test_invalid_strategy_candidate_is_reported_separately():
    result=await StrategyOptimizer().optimize(
        baseline_strategy=StrategyConfig(),baseline_agents=AgentConfig(),risk_config=RiskFirewallConfig(),
        simulation_config=SimulationConfig(max_frames=6,record_trace=False),
        strategy_grid={"concentration_lower_bps":["300"]},agent_grid={},
        training_scenarios=["QUIET"],validation_scenarios=["TREND_UP"],
        objective=OptimizationObjectiveConfig(),max_candidates=2,frames=6,top_n=1,
    )
    assert result.candidate_count==0
    assert result.rejected_candidates


@pytest.mark.asyncio
async def test_invalid_agent_candidate_is_reported_separately():
    result=await StrategyOptimizer().optimize(
        baseline_strategy=StrategyConfig(),baseline_agents=AgentConfig(),risk_config=RiskFirewallConfig(),
        simulation_config=SimulationConfig(max_frames=6,record_trace=False),
        strategy_grid={},agent_grid={"regime_spread_strength":["2"]},
        training_scenarios=["QUIET"],validation_scenarios=["TREND_UP"],
        objective=OptimizationObjectiveConfig(),max_candidates=2,frames=6,top_n=1,
    )
    assert result.candidate_count==0
    assert result.rejected_candidates
