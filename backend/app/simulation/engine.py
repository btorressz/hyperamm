from __future__ import annotations

from collections import deque
from datetime import datetime
from decimal import Decimal

from app.agents import AgentConfig,AgentSupervisor,AgentTelemetryStore,build_agent_evidence,transform_quotes
from app.execution.order_manager import OrderManager
from app.execution.paper import PaperExecutionAdapter
from app.market_data.history import MarketPriceHistory
from app.risk.authorization import authorize,fingerprint
from app.risk.firewall import RiskFirewall,RiskFirewallConfig
from app.accounting import AccountingConfig,AccountingService
from app.accounting.pnl import to_pnl_drawdown
from app.risk.limits import validate_quotes
from app.risk.models import RiskStatus
from app.strategy.inventory import build_inventory_state
from app.strategy.models import ExecutionMode,StrategyConfig
from app.strategy.quote_engine import QuoteEngine

from app.agents.model_artifact import LogisticModelArtifact
from app.research.ml.shadow_evaluation import ShadowEvaluationAccumulator

from .config import SimulationConfig
from .metrics import MetricsAccumulator
from .models import SimulationDataset,SimulationResult,SimulationTracePoint,stable_fingerprint
from .references import build_simulated_references
from .replay import bounded_frames
from . import version


LIMITATIONS=[
    "SIMULATED / OFFLINE / PAPER research only.",
    "PAPER fill model is deterministic crossing-only; queue priority is not simulated.",
    "PAPER fees and funding use configurable research assumptions, never venue facts.",
    "No exchange latency model.",
    "No hidden-liquidity model.",
    "No stochastic fill probability.",
    "Net PnL includes only configured simulated fees and deterministic funding intervals.",
    "Full-notional capital reservation is simulated, not exchange margin.",
]


class SimulationClock:
    def __init__(self,initial:datetime):
        self.current=initial
    def set(self,value:datetime):
        if value<self.current:raise ValueError("simulation clock cannot move backward")
        self.current=value
    def __call__(self)->datetime:
        return self.current


class SimulationEngine:
    def __init__(self):
        self.network_access=False

    async def run(
        self,
        *,
        dataset:SimulationDataset,
        strategy_config:StrategyConfig,
        agent_config:AgentConfig,
        risk_config:RiskFirewallConfig,
        simulation_config:SimulationConfig,
        scenario:str|None=None,
        predictive_model:LogisticModelArtifact|None=None,
    )->SimulationResult:
        frames=bounded_frames(dataset,simulation_config.max_frames)
        strategy=strategy_config.model_copy(deep=True)
        agents=agent_config.model_copy(deep=True)
        risk=risk_config.model_copy(deep=True)
        if strategy.execution_mode!=ExecutionMode.PAPER:
            raise ValueError("simulation requires PAPER execution_mode")
        if strategy.market!=dataset.market:
            raise ValueError("strategy market must match simulation dataset")

        clock=SimulationClock(frames[0].timestamp)
        accounting_payload=simulation_config.accounting.model_dump()
        accounting_payload["paper_initial_equity_quote"]=simulation_config.initial_equity_quote
        accounting=AccountingService(strategy.market,config=AccountingConfig.model_validate(accounting_payload),clock=clock)
        paper=PaperExecutionAdapter(clock=clock)
        history=MarketPriceHistory(max_samples=max(1000,strategy.volatility_window_samples,agents.regime_momentum_window_samples))
        telemetry=AgentTelemetryStore()
        supervisor=AgentSupervisor(agents)
        if predictive_model is not None:
            supervisor.predictive_adverse_selection.install_artifact(predictive_model)
            telemetry.register_horizons((float(predictive_model.provenance.markout_horizon_seconds),))
        shadow_evaluation=ShadowEvaluationAccumulator()
        active_prediction=None
        firewall=RiskFirewall(risk)
        quote_engine=QuoteEngine()
        risk_status=RiskStatus()
        metrics=MetricsAccumulator(simulation_config.initial_equity_quote)
        trace=deque(maxlen=simulation_config.trace_max_points or None) if simulation_config.record_trace and simulation_config.trace_max_points>0 else None
        fill_refs=None

        def on_fill(fill):
            telemetry.observe_fill_from_references(fill,fill_refs)
            shadow_evaluation.observe_fill(fill,telemetry.fill_identity(fill))
            accounting.ingest_fill(fill)
            accounting.observe_execution_fills(paper.fills.all(), retired_count=paper.fills.retired_count,
                                               duplicate_fills=paper.fills.duplicate_pending(accounting))
            paper.fills.acknowledge(fill, accounting, agent_consumed=True)
        paper.on_fill=on_fill
        def observe_orders(observed):
            telemetry.observe_orders(observed)
            shadow_evaluation.observe_orders(observed,active_prediction)
        paper.orders.observer=observe_orders

        current_authorization=None
        current_agent=None
        current_risk=None
        current_refs=None
        current_quotes=[]
        expected={}

        async def simulation_authority():
            accounting.observe_execution_fills(paper.fills.all(), retired_count=paper.fills.retired_count,
                                               duplicate_fills=paper.fills.duplicate_pending(accounting))
            if current_authorization is None or not current_authorization.authorized:
                raise PermissionError("simulation FinalQuoteAuthorization is not authorized")
            if current_agent is None or current_risk is None or current_refs is None:
                raise RuntimeError("simulation authority state is incomplete")
            checks={
                "market":history.version,
                "inventory":accounting.position.version,
                "perp":expected["perp"],
                "reference":current_refs.version,
                "agent":current_agent.version,
                "risk":current_risk.version,
                "accounting":accounting.version,
            }
            for name,value in checks.items():
                if value!=expected[name]:
                    raise RuntimeError(f"simulation {name} authority changed before transmission")
            if current_agent.fingerprint!=expected["agent_fingerprint"]:
                raise RuntimeError("simulation agent fingerprint changed before transmission")
            if current_authorization.agent_fingerprint!=expected["agent_fingerprint"]:
                raise RuntimeError("simulation authorization agent fingerprint mismatch")
            accounting.require_fresh()
            if (accounting.fingerprint!=expected["accounting_fingerprint"]
                    or current_authorization.accounting_fingerprint!=accounting.fingerprint
                    or current_authorization.accounting_version!=accounting.version):
                raise RuntimeError("simulation accounting authority changed before transmission")
            if fingerprint(current_quotes)!=current_authorization.quote_fingerprint:
                raise RuntimeError("simulation authorized quote fingerprint mismatch")

        orders=OrderManager(paper,authority=simulation_authority)
        strategy_fingerprint=stable_fingerprint(strategy)
        run_fingerprint=stable_fingerprint({
            "engine_version":version.SIMULATION_ENGINE_VERSION,
            "dataset_fingerprint":dataset.fingerprint,
            "strategy":strategy,
            "agents":agents,
            "observational_model_sha256":predictive_model.provenance.model_sha256 if predictive_model else None,
            "risk":risk,
            "accounting":accounting.config,
            "accounting_schema":"phase11-v1",
            "simulation":{
                "initial_equity_quote":simulation_config.initial_equity_quote,
                "max_frames":simulation_config.max_frames,
                "record_trace":simulation_config.record_trace,
                "trace_max_points":simulation_config.trace_max_points,
                "fill_model":simulation_config.fill_model,
            },
        })

        for frame in frames:
            clock.set(frame.timestamp)
            refs=build_simulated_references(
                frame,agreement_bps=risk.source_agreement_bps,outlier_bps=risk.source_outlier_bps,
                version=frame.sequence,
            )
            # Bind this frame before resting-order or immediate submit fills can occur.
            fill_refs=refs
            paper.update_market(frame.market)
            inventory=build_inventory_state(
                market=strategy.market,position=accounting.position.position_base,
                target=strategy.target_inventory_base,soft_limit=strategy.soft_inventory_limit_base,
                source="PAPER",updated_at=paper.last_fill_at or frame.timestamp,stale=False,
                version=accounting.position.version,
            )
            history.add_snapshot(frame.market)
            fair,pool,proposed,inventory_decision,market_decision,perp_decision=quote_engine.generate_perp_market_adaptive(
                strategy,frame.market,inventory,history,frame.perp_context
            )
            telemetry.observe_orders(await paper.get_open_orders())
            agent_evidence=build_agent_evidence(
                market_decision=market_decision,inventory=inventory,perp_context=frame.perp_context,
                refs=refs,history=history,momentum_window=agents.regime_momentum_window_samples,
                market_snapshot=frame.market,config=agents,telemetry=telemetry,observed_at=frame.timestamp,upstream_quotes=proposed,
            )
            agent_decision=supervisor.evaluate(
                evidence=agent_evidence,telemetry=telemetry,history=history,execution_mode="PAPER"
            )
            active_prediction=agent_decision.predictive_adverse_selection
            agent_quotes=transform_quotes(
                proposed,agent_decision,center=inventory_decision.reservation_price,
                tick_size=strategy.tick_size,size_precision=strategy.size_precision,
            )

            accounting.observe_funding(frame.perp_context)
            accounting.mark(frame.perp_context.mark_price,observed_at=frame.timestamp)
            existing=await paper.get_open_orders()
            vault=accounting.reservation_snapshot(agent_quotes,existing)
            pnl_for_risk=to_pnl_drawdown(vault)
            risk_decision=firewall.evaluate(
                refs=refs,quotes=agent_quotes,current_position=inventory.position_base,
                mark=frame.perp_context.mark_price,liquidation=None,pnl=pnl_for_risk,
                market_version=market_decision.version,inventory_version=inventory.version,
                perp_version=frame.perp_context.version,venue_uncertain=False,existing_orders=existing,
                capital=vault,max_capital_utilization=accounting.config.max_capital_utilization,
            )
            risk_decision=risk_decision.model_copy(update={"created_at":frame.timestamp})
            authorized=firewall.transform(
                agent_quotes,risk_decision,center=inventory_decision.reservation_price,
                tick_size=strategy.tick_size,size_precision=strategy.size_precision,
                base_order_size=strategy.base_order_size,
            )
            validate_quotes(authorized,frame.market,risk_status)
            accounting.reserve(authorized,existing)
            vault=accounting.snapshot()
            authorization=authorize(authorized,refs,risk_decision,agent_decision,vault)

            current_authorization=authorization
            current_agent=agent_decision
            current_risk=risk_decision
            current_refs=refs
            current_quotes=authorized
            expected={
                "market":history.version,"inventory":inventory.version,"perp":frame.perp_context.version,
                "reference":refs.version,"agent":agent_decision.version,"risk":risk_decision.version,
                "agent_fingerprint":agent_decision.fingerprint,
                "accounting":accounting.version,"accounting_fingerprint":accounting.fingerprint,
            }
            actions=await orders.reconcile(
                strategy.market,authorized,strategy.replace_tolerance_bps,strategy.size_tolerance
            )
            telemetry.observe_reconcile(actions,await paper.get_open_orders())
            shadow_evaluation.mature(telemetry,history)

            # Immediate crossing fills, if any, belong to this frame and deterministic clock.
            inventory_after=build_inventory_state(
                market=strategy.market,position=accounting.position.position_base,
                target=strategy.target_inventory_base,soft_limit=strategy.soft_inventory_limit_base,
                source="PAPER",updated_at=paper.last_fill_at or frame.timestamp,stale=False,
                version=accounting.position.version,
            )
            accounting.mark(frame.perp_context.mark_price,observed_at=frame.timestamp)
            accounting.reserve(authorized,await paper.get_open_orders())
            vault_after=accounting.snapshot()
            session_after=vault_after.net_pnl_quote
            equity_after=vault_after.equity_quote
            drawdown_after=vault_after.drawdown_pct
            metrics.record(
                authorized_quotes=authorized,inventory=inventory_after,risk_decision=risk_decision,
                agent_decision=agent_decision,equity=equity_after,drawdown_pct=drawdown_after,actions=actions,
            )
            if trace is not None:
                trace.append(SimulationTracePoint(
                    sequence=frame.sequence,timestamp=frame.timestamp,mid=frame.market.mid_price,
                    mark=frame.perp_context.mark_price,oracle=frame.perp_context.oracle_price,
                    inventory_base=inventory_after.position_base,session_pnl=session_after,equity=equity_after,
                    drawdown_pct=drawdown_after,reference_confidence=refs.consensus.confidence_state,
                    agent_regime=agent_decision.regime.state.value,
                    toxic_flow_state=agent_decision.toxic_flow.state.value,
                    execution_quality_state=agent_decision.execution_quality.state.value,
                    liquidity_quality_state=agent_decision.liquidity_quality.state.value,
                    perp_crowding_state=agent_decision.perp_crowding.state.value,
                    predictive_state=agent_decision.predictive_adverse_selection.state.value,
                    bid_adverse_probability=agent_decision.predictive_adverse_selection.metrics.bid_adverse_probability,
                    ask_adverse_probability=agent_decision.predictive_adverse_selection.metrics.ask_adverse_probability,
                    risk_state=risk_decision.state.value,desired_quote_count=len(proposed),
                    agent_quote_count=len(agent_quotes),authorized_quote_count=len(authorized),
                    open_order_count=len(await paper.get_open_orders()),fill_count=paper.fills.version,
                ))

        final_metrics=metrics.finalize(
            paper=paper,market=strategy.market,vault=accounting.snapshot(),telemetry=telemetry,history=history,
            agent_config=agents,frame_count=len(frames),
        )
        return SimulationResult(
            engine_version=version.SIMULATION_ENGINE_VERSION,
            run_fingerprint=run_fingerprint,scenario=scenario or dataset.source,
            dataset_fingerprint=dataset.fingerprint,strategy_fingerprint=strategy_fingerprint,
            metrics=final_metrics,trace=list(trace or []),simulated=True,limitations=list(LIMITATIONS),
            orders=[o.model_dump(mode="json") for o in paper.all_orders()],
            fills=[f.model_dump(mode="json") for f in paper.fills.all()],
            vault=accounting.snapshot(),accounting_ledger=accounting.ledger.entries(500),
            accounting_fingerprint=accounting.fingerprint,
            predictive_evaluation=shadow_evaluation.result() if predictive_model is not None else None,
        )
