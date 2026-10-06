from __future__ import annotations

from collections import deque
from datetime import datetime
from decimal import Decimal

from app.agents import AgentConfig,AgentSupervisor,AgentTelemetryStore,build_agent_evidence,transform_quotes
from app.execution.order_manager import OrderManager
from app.execution.paper import PaperExecutionAdapter
from app.market_data.history import MarketPriceHistory
from app.risk.authorization import authorize,fingerprint
from app.risk.firewall import PnlDrawdown,RiskFirewall,RiskFirewallConfig,paper_pnl
from app.risk.limits import validate_quotes
from app.risk.models import RiskStatus
from app.strategy.inventory import build_inventory_state
from app.strategy.models import ExecutionMode,StrategyConfig
from app.strategy.quote_engine import QuoteEngine

from .config import SimulationConfig
from .metrics import MetricsAccumulator
from .models import SimulationDataset,SimulationResult,SimulationTracePoint,stable_fingerprint
from .references import build_simulated_references
from .replay import bounded_frames


LIMITATIONS=[
    "SIMULATED / OFFLINE / PAPER research only.",
    "PAPER fill model is deterministic crossing-only; queue priority is not simulated.",
    "No maker/taker fee accounting.",
    "No funding cash-flow accounting.",
    "No exchange latency model.",
    "No hidden-liquidity model.",
    "No stochastic fill probability.",
    "PnL is gross strategy PnL before fees and funding.",
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
        paper=PaperExecutionAdapter(clock=clock)
        history=MarketPriceHistory(max_samples=max(1000,strategy.volatility_window_samples,agents.regime_momentum_window_samples))
        telemetry=AgentTelemetryStore()
        supervisor=AgentSupervisor(agents)
        firewall=RiskFirewall(risk)
        quote_engine=QuoteEngine()
        risk_status=RiskStatus()
        metrics=MetricsAccumulator(simulation_config.initial_equity_quote)
        trace=deque(maxlen=simulation_config.trace_max_points or None) if simulation_config.record_trace and simulation_config.trace_max_points>0 else None
        current_fill_reference:Decimal|None=None

        def on_fill(fill):
            telemetry.observe_fill(fill,current_fill_reference)
        paper.on_fill=on_fill

        current_authorization=None
        current_agent=None
        current_risk=None
        current_refs=None
        current_quotes=[]
        expected={}

        async def simulation_authority():
            if current_authorization is None or not current_authorization.authorized:
                raise PermissionError("simulation FinalQuoteAuthorization is not authorized")
            if current_agent is None or current_risk is None or current_refs is None:
                raise RuntimeError("simulation authority state is incomplete")
            checks={
                "market":history.version,
                "inventory":paper.inventory_version,
                "perp":expected["perp"],
                "reference":current_refs.version,
                "agent":current_agent.version,
                "risk":current_risk.version,
            }
            for name,value in checks.items():
                if value!=expected[name]:
                    raise RuntimeError(f"simulation {name} authority changed before transmission")
            if current_agent.fingerprint!=expected["agent_fingerprint"]:
                raise RuntimeError("simulation agent fingerprint changed before transmission")
            if current_authorization.agent_fingerprint!=expected["agent_fingerprint"]:
                raise RuntimeError("simulation authorization agent fingerprint mismatch")
            if fingerprint(current_quotes)!=current_authorization.quote_fingerprint:
                raise RuntimeError("simulation authorized quote fingerprint mismatch")

        orders=OrderManager(paper,authority=simulation_authority)
        strategy_fingerprint=stable_fingerprint(strategy)
        run_fingerprint=stable_fingerprint({
            "engine_version":simulation_config.engine_version,
            "dataset_fingerprint":dataset.fingerprint,
            "strategy":strategy,
            "agents":agents,
            "risk":risk,
            "simulation":{
                "initial_equity_quote":simulation_config.initial_equity_quote,
                "max_frames":simulation_config.max_frames,
                "record_trace":simulation_config.record_trace,
                "trace_max_points":simulation_config.trace_max_points,
                "fill_model":simulation_config.fill_model,
                "engine_version":simulation_config.engine_version,
            },
        })

        for frame in frames:
            clock.set(frame.timestamp)
            current_fill_reference=frame.market.mid_price
            paper.update_market(frame.market)
            inventory=build_inventory_state(
                market=strategy.market,position=paper.position_base(strategy.market),
                target=strategy.target_inventory_base,soft_limit=strategy.soft_inventory_limit_base,
                source="PAPER",updated_at=paper.last_fill_at or frame.timestamp,stale=False,
                version=paper.inventory_version,
            )
            history.add_snapshot(frame.market)
            fair,pool,proposed,inventory_decision,market_decision,perp_decision=quote_engine.generate_perp_market_adaptive(
                strategy,frame.market,inventory,history,frame.perp_context
            )
            refs=build_simulated_references(
                frame,agreement_bps=risk.source_agreement_bps,outlier_bps=risk.source_outlier_bps,
                version=frame.sequence,
            )
            current_fill_reference=refs.consensus.consensus_price or frame.market.mid_price
            telemetry.observe_orders(paper.all_orders())
            agent_evidence=build_agent_evidence(
                market_decision=market_decision,inventory=inventory,perp_context=frame.perp_context,
                refs=refs,history=history,momentum_window=agents.regime_momentum_window_samples,
            )
            agent_decision=supervisor.evaluate(
                evidence=agent_evidence,telemetry=telemetry,history=history,execution_mode="PAPER"
            )
            agent_quotes=transform_quotes(
                proposed,agent_decision,center=inventory_decision.reservation_price,
                tick_size=strategy.tick_size,size_precision=strategy.size_precision,
            )

            pnl=paper_pnl(paper.fills.all(),strategy.market,frame.perp_context.mark_price)
            session=pnl.session_pnl or Decimal("0")
            equity=simulation_config.initial_equity_quote+session
            metrics.peak_equity=max(metrics.peak_equity,equity)
            drawdown=(metrics.peak_equity-equity)/metrics.peak_equity if metrics.peak_equity>0 else Decimal("0")
            pnl_for_risk=PnlDrawdown(
                realized_pnl=pnl.realized_pnl,unrealized_pnl=pnl.unrealized_pnl,session_pnl=session,
                current_equity=equity,peak_equity=metrics.peak_equity,drawdown_pct=drawdown,
                source="SIMULATION PAPER PNL",simulated=True,
            )
            existing=await paper.get_open_orders()
            risk_decision=firewall.evaluate(
                refs=refs,quotes=agent_quotes,current_position=inventory.position_base,
                mark=frame.perp_context.mark_price,liquidation=None,pnl=pnl_for_risk,
                market_version=market_decision.version,inventory_version=inventory.version,
                perp_version=frame.perp_context.version,venue_uncertain=False,existing_orders=existing,
            )
            risk_decision=risk_decision.model_copy(update={"created_at":frame.timestamp})
            authorized=firewall.transform(
                agent_quotes,risk_decision,center=inventory_decision.reservation_price,
                tick_size=strategy.tick_size,size_precision=strategy.size_precision,
                base_order_size=strategy.base_order_size,
            )
            validate_quotes(authorized,frame.market,risk_status)
            authorization=authorize(authorized,refs,risk_decision,agent_decision)

            current_authorization=authorization
            current_agent=agent_decision
            current_risk=risk_decision
            current_refs=refs
            current_quotes=authorized
            expected={
                "market":history.version,"inventory":inventory.version,"perp":frame.perp_context.version,
                "reference":refs.version,"agent":agent_decision.version,"risk":risk_decision.version,
                "agent_fingerprint":agent_decision.fingerprint,
            }
            actions=await orders.reconcile(
                strategy.market,authorized,strategy.replace_tolerance_bps,strategy.size_tolerance
            )
            telemetry.observe_reconcile(actions,paper.all_orders())

            # Immediate crossing fills, if any, belong to this frame and deterministic clock.
            inventory_after=build_inventory_state(
                market=strategy.market,position=paper.position_base(strategy.market),
                target=strategy.target_inventory_base,soft_limit=strategy.soft_inventory_limit_base,
                source="PAPER",updated_at=paper.last_fill_at or frame.timestamp,stale=False,
                version=paper.inventory_version,
            )
            pnl_after=paper_pnl(paper.fills.all(),strategy.market,frame.perp_context.mark_price)
            session_after=pnl_after.session_pnl or Decimal("0")
            equity_after=simulation_config.initial_equity_quote+session_after
            metrics.peak_equity=max(metrics.peak_equity,equity_after)
            drawdown_after=(metrics.peak_equity-equity_after)/metrics.peak_equity if metrics.peak_equity>0 else Decimal("0")
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
                    risk_state=risk_decision.state.value,desired_quote_count=len(proposed),
                    agent_quote_count=len(agent_quotes),authorized_quote_count=len(authorized),
                    open_order_count=len(await paper.get_open_orders()),fill_count=len(paper.fills.all()),
                ))

        final_mark=frames[-1].perp_context.mark_price
        final_metrics=metrics.finalize(
            paper=paper,market=strategy.market,mark=final_mark,telemetry=telemetry,history=history,
            agent_config=agents,frame_count=len(frames),
        )
        return SimulationResult(
            run_fingerprint=run_fingerprint,scenario=scenario or dataset.source,
            dataset_fingerprint=dataset.fingerprint,strategy_fingerprint=strategy_fingerprint,
            metrics=final_metrics,trace=list(trace or []),simulated=True,limitations=list(LIMITATIONS),
            orders=[o.model_dump(mode="json") for o in paper.all_orders()],
            fills=[f.model_dump(mode="json") for f in paper.fills.all()],
        )
