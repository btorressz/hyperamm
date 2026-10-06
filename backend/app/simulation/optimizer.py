from __future__ import annotations

from decimal import Decimal
from itertools import product
from math import prod

from app.agents.config import AgentConfig
from app.risk.firewall import RiskFirewallConfig
from app.strategy.models import StrategyConfig

from .config import OptimizationObjectiveConfig,SimulationConfig
from .engine import SimulationEngine
from .models import CandidateEvaluation,OptimizationResult,ScenarioEvaluation,ScoreComponents,stable_fingerprint
from .scenarios import generate_scenario


STRATEGY_PARAMETER_ALLOWLIST={
    "levels_per_side","max_distance_bps","total_liquidity","concentration_factor",
    "concentration_lower_bps","concentration_upper_bps","max_inventory_price_skew_bps",
    "inventory_size_skew_strength","volatility_low_threshold","volatility_high_threshold",
    "volatility_spread_strength","volatility_size_strength","imbalance_spread_strength",
    "imbalance_size_strength","perp_mark_weight","perp_oracle_weight",
    "max_funding_reference_shift_bps","max_perp_reference_shift_bps","base_order_size",
}
AGENT_PARAMETER_ALLOWLIST={
    "regime_trend_threshold_bps","regime_spread_strength","regime_size_strength",
    "toxic_flow_adverse_markout_bps","toxic_flow_spread_strength","toxic_flow_size_strength",
    "execution_quality_poor_markout_bps","execution_quality_max_churn_ratio",
    "execution_quality_spread_strength","execution_quality_size_strength",
}
FORBIDDEN_PARAMETERS={
    "execution_mode","market_data_mode","hard_inventory_limit_base","reference_firewall_enabled",
    "reference_warn_deviation_bps","reference_reduce_deviation_bps","reference_halt_deviation_bps",
    "max_projected_long_base","max_projected_short_base","max_gross_quote_notional",
    "max_projected_position_notional","liquidation_halt_distance_bps","drawdown_halt_pct",
    "enable_hyperliquid_testnet_orders","hyperliquid_private_key","redstone_api_key",
    "coingecko_api_key","redstone_live_ws_url","redstone_public_http_url","kraken_ws_url",
    "coingecko_api_base_url","hyperliquid_testnet_url","max_session_loss_quote",
    "source_agreement_bps","source_outlier_bps","liquidation_warn_distance_bps",
    "liquidation_reduce_distance_bps","drawdown_warn_pct","drawdown_reduce_pct",
    "risk_recovery_confirmations",
}
HARD_MAX_CANDIDATES=128


def score_metrics(metrics,objective:OptimizationObjectiveConfig)->ScoreComponents:
    return_bps=metrics.return_pct*Decimal("100")
    drawdown=objective.drawdown_weight*metrics.max_drawdown_pct*Decimal("10000")
    inventory=objective.inventory_weight*metrics.max_inventory_utilization*Decimal("10000")
    adverse_value=max(Decimal("0"),-(metrics.mean_mature_markout_bps or Decimal("0")))
    adverse=objective.adverse_markout_weight*adverse_value
    churn=objective.churn_weight*metrics.reconciliation_churn_ratio*Decimal("10000")
    halt=objective.halt_weight*metrics.risk_halt_fraction*Decimal("10000")
    final=return_bps-drawdown-inventory-adverse-churn-halt
    return ScoreComponents(
        return_contribution=return_bps,drawdown_penalty=drawdown,inventory_penalty=inventory,
        adverse_markout_penalty=adverse,churn_penalty=churn,halt_penalty=halt,final_score=final,
    )


def _mean(values:list[Decimal])->Decimal:
    return sum(values,Decimal("0"))/Decimal(len(values))


def _candidate_summary(evaluations:list[ScenarioEvaluation])->dict[str,Decimal|None]:
    frame_total=sum((e.metrics.frame_count for e in evaluations),0)
    def risk_fraction(state):
        count=sum((e.metrics.risk_state_counts.get(state,0) for e in evaluations),0)
        return Decimal(count)/Decimal(frame_total) if frame_total else Decimal("0")
    return {
        "mean_objective_score":_mean([e.score.final_score for e in evaluations]),
        "worst_objective_score":min((e.score.final_score for e in evaluations),default=Decimal("0")),
        "mean_session_pnl":_mean([e.metrics.session_pnl for e in evaluations]),
        "mean_return_pct":_mean([e.metrics.return_pct for e in evaluations]),
        "mean_max_drawdown_pct":_mean([e.metrics.max_drawdown_pct for e in evaluations]),
        "worst_drawdown_pct":max((e.metrics.max_drawdown_pct for e in evaluations),default=Decimal("0")),
        "max_inventory_utilization":max((e.metrics.max_inventory_utilization for e in evaluations),default=Decimal("0")),
        "mean_markout_bps":(
            _mean([e.metrics.mean_mature_markout_bps for e in evaluations if e.metrics.mean_mature_markout_bps is not None])
            if any(e.metrics.mean_mature_markout_bps is not None for e in evaluations) else None
        ),
        "mean_churn_ratio":_mean([e.metrics.reconciliation_churn_ratio for e in evaluations]),
        "mean_halt_fraction":_mean([e.metrics.risk_halt_fraction for e in evaluations]),
        "risk_normal_fraction":risk_fraction("NORMAL"),
        "risk_widen_fraction":risk_fraction("WIDEN"),
        "risk_reduce_fraction":risk_fraction("REDUCE"),
        "risk_halt_fraction":risk_fraction("HALT"),
    }


def candidate_ranking_key(item:CandidateEvaluation):
    summary=item.training_aggregate or _candidate_summary(item.training)
    return (
        -item.training_score,
        summary["worst_drawdown_pct"],
        summary["max_inventory_utilization"],
        summary["mean_churn_ratio"],
        item.configuration_fingerprint,
    )


class StrategyOptimizer:
    def __init__(self,engine:SimulationEngine|None=None):
        self.engine=engine or SimulationEngine()

    @staticmethod
    def _validate_grid(strategy_grid:dict,agent_grid:dict,max_candidates:int)->int:
        if max_candidates<1 or max_candidates>HARD_MAX_CANDIDATES:
            raise ValueError(f"max_candidates must be between 1 and {HARD_MAX_CANDIDATES}")
        for name,values in {**strategy_grid,**agent_grid}.items():
            if name in FORBIDDEN_PARAMETERS:
                raise ValueError(f"safety/runtime parameter cannot be optimized: {name}")
            if not isinstance(values,list) or not values:
                raise ValueError(f"parameter grid for {name} must be a non-empty list")
        unknown_strategy=set(strategy_grid)-STRATEGY_PARAMETER_ALLOWLIST
        unknown_agent=set(agent_grid)-AGENT_PARAMETER_ALLOWLIST
        if unknown_strategy:raise ValueError(f"unknown StrategyConfig optimization parameters: {sorted(unknown_strategy)}")
        if unknown_agent:raise ValueError(f"unknown AgentConfig optimization parameters: {sorted(unknown_agent)}")
        counts=[len(v) for v in list(strategy_grid.values())+list(agent_grid.values())]
        requested=prod(counts) if counts else 0
        if requested>max_candidates:
            raise ValueError(f"requested candidate count {requested} exceeds allowed maximum {max_candidates}")
        return requested

    @staticmethod
    def enumerate_grid(strategy_grid:dict,agent_grid:dict,max_candidates:int)->list[tuple[dict,dict]]:
        StrategyOptimizer._validate_grid(strategy_grid,agent_grid,max_candidates)
        skeys=sorted(strategy_grid);akeys=sorted(agent_grid)
        keys=[("strategy",k) for k in skeys]+[("agent",k) for k in akeys]
        values=[strategy_grid[k] for k in skeys]+[agent_grid[k] for k in akeys]
        if not keys:return []
        result=[]
        for combination in product(*values):
            su={};au={}
            for (kind,key),value in zip(keys,combination):
                (su if kind=="strategy" else au)[key]=value
            result.append((su,au))
        return result

    async def _evaluate(
        self,*,label,strategy,agents,risk,simulation,scenario_names,frames,objective,strategy_updates,agent_updates
    )->CandidateEvaluation:
        evaluations=[]
        for name in scenario_names:
            dataset=generate_scenario(name,frames=frames,market=strategy.market)
            result=await self.engine.run(
                dataset=dataset,strategy_config=strategy,agent_config=agents,risk_config=risk,
                simulation_config=simulation,scenario=name,
            )
            evaluations.append(ScenarioEvaluation(
                scenario=name,run_fingerprint=result.run_fingerprint,metrics=result.metrics,
                score=score_metrics(result.metrics,objective),
            ))
        score=_mean([item.score.final_score for item in evaluations])
        config_fp=stable_fingerprint({"strategy":strategy,"agents":agents})
        return CandidateEvaluation(
            label=label,strategy_updates=strategy_updates,agent_updates=agent_updates,
            configuration_fingerprint=config_fp,training=evaluations,training_score=score,
            training_aggregate=_candidate_summary(evaluations),
        )

    async def optimize(
        self,*,baseline_strategy:StrategyConfig,baseline_agents:AgentConfig,risk_config:RiskFirewallConfig,
        simulation_config:SimulationConfig,strategy_grid:dict,agent_grid:dict,
        training_scenarios:list[str],validation_scenarios:list[str],
        objective:OptimizationObjectiveConfig,max_candidates:int=32,frames:int=120,top_n:int=5,
    )->OptimizationResult:
        if not training_scenarios:raise ValueError("at least one training scenario is required")
        if not validation_scenarios:raise ValueError("at least one validation scenario is required")
        requested=self._validate_grid(strategy_grid,agent_grid,max_candidates)
        baseline=await self._evaluate(
            label="BASELINE",strategy=baseline_strategy.model_copy(deep=True),agents=baseline_agents.model_copy(deep=True),
            risk=risk_config.model_copy(deep=True),simulation=simulation_config.model_copy(deep=True),
            scenario_names=training_scenarios,frames=frames,objective=objective,strategy_updates={},agent_updates={},
        )
        candidates=[];rejected=[]
        for index,(strategy_updates,agent_updates) in enumerate(self.enumerate_grid(strategy_grid,agent_grid,max_candidates),start=1):
            try:
                strategy=StrategyConfig.model_validate({**baseline_strategy.model_dump(),**strategy_updates})
                agents=AgentConfig.model_validate({**baseline_agents.model_dump(),**agent_updates})
                candidate=await self._evaluate(
                    label=f"CANDIDATE_{index}",strategy=strategy,agents=agents,risk=risk_config.model_copy(deep=True),
                    simulation=simulation_config.model_copy(deep=True),scenario_names=training_scenarios,
                    frames=frames,objective=objective,strategy_updates=strategy_updates,agent_updates=agent_updates,
                )
                candidates.append(candidate)
            except Exception as exc:
                rejected.append({"strategy_updates":strategy_updates,"agent_updates":agent_updates,"reason":str(exc)})

        ranked=sorted(candidates,key=candidate_ranking_key)
        baseline_summary=_candidate_summary(baseline.training)
        for candidate in ranked:

        selected=ranked[:max(1,min(top_n,len(ranked)))]
        baseline_validation=[]
        for name in validation_scenarios:
            dataset=generate_scenario(name,frames=frames,market=baseline_strategy.market)
            result=await self.engine.run(
                dataset=dataset,strategy_config=baseline_strategy.model_copy(deep=True),
                agent_config=baseline_agents.model_copy(deep=True),risk_config=risk_config.model_copy(deep=True),
                simulation_config=simulation_config.model_copy(deep=True),scenario=name,
            )
            baseline_validation.append(ScenarioEvaluation(
                scenario=name,run_fingerprint=result.run_fingerprint,metrics=result.metrics,
                score=score_metrics(result.metrics,objective),
            ))
        baseline.validation=baseline_validation
        baseline.validation_score=_mean([x.score.final_score for x in baseline_validation])
        baseline.validation_aggregate=_candidate_summary(baseline_validation)
        baseline.score_delta=Decimal("0")
        baseline.baseline_delta={k:Decimal("0") if v is not None else None for k,v in _candidate_summary(baseline.training).items()}
        baseline.baseline_delta["objective_score"]=Decimal("0")

        for candidate in selected:
            strategy=StrategyConfig.model_validate({**baseline_strategy.model_dump(),**candidate.strategy_updates})
            agents=AgentConfig.model_validate({**baseline_agents.model_dump(),**candidate.agent_updates})
            validation=[]
            for name in validation_scenarios:
                dataset=generate_scenario(name,frames=frames,market=strategy.market)
                result=await self.engine.run(
                    dataset=dataset,strategy_config=strategy,agent_config=agents,risk_config=risk_config.model_copy(deep=True),
                    simulation_config=simulation_config.model_copy(deep=True),scenario=name,
                )
                validation.append(ScenarioEvaluation(
                    scenario=name,run_fingerprint=result.run_fingerprint,metrics=result.metrics,
                    score=score_metrics(result.metrics,objective),
                ))
            candidate.validation=validation
            candidate.validation_score=_mean([x.score.final_score for x in validation])
            candidate.validation_aggregate=_candidate_summary(validation)
            candidate.score_delta=candidate.training_score-baseline.training_score
            summary=_candidate_summary(candidate.training)
            candidate.baseline_delta={}
            for name,value in summary.items():
                base_value=baseline_summary.get(name)
                candidate.baseline_delta[name]=(
                    value-base_value if value is not None and base_value is not None else None
                )
            candidate.baseline_delta["objective_score"]=candidate.training_score-baseline.training_score

        return OptimizationResult(
            baseline=baseline,requested_candidate_count=requested,candidate_count=len(candidates),
            rejected_candidates=rejected,ranked_candidates=ranked,training_scenarios=training_scenarios,
            validation_scenarios=validation_scenarios,objective=objective.model_dump(mode="json"),simulated=True,
        )
