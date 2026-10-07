from __future__ import annotations

from decimal import Decimal

from app.execution.models import OrderStatus
from .config import AgentConfig
from .models import AgentHealth,ExecutionQualityAgentOutput,ExecutionQualityMetrics,ExecutionQualityState


def spread_capture_bps(side:str,fill_price:Decimal,reference_price:Decimal)->Decimal:
    if fill_price<=0 or reference_price<=0 or not fill_price.is_finite() or not reference_price.is_finite():
        raise ValueError("spread-capture prices must be finite and positive")
    if side=="BID":return (reference_price-fill_price)/reference_price*Decimal("10000")
    if side=="ASK":return (fill_price-reference_price)/reference_price*Decimal("10000")
    raise ValueError("fill side must be BID or ASK")


def churn_ratio(keep:int,create:int,replace:int,cancel:int)->Decimal:
    """Order-changing activity ratio; KEEP count is observability only."""
    for value in (keep,create,replace,cancel):
        if value<0:raise ValueError("reconciliation counts must be non-negative")
    return Decimal(replace+cancel)/Decimal(max(1,create+replace+cancel))


def _clamp(value:Decimal,low:Decimal=Decimal("0"),high:Decimal=Decimal("1"))->Decimal:
    return max(low,min(high,value))


class ExecutionQualityAgent:
    def __init__(self,config:AgentConfig):
        self.config=config
        self.version=0
        self._signature=None

    def _versioned(self,output:ExecutionQualityAgentOutput)->ExecutionQualityAgentOutput:
        signature=(
            output.health,output.state,output.confidence,output.spread_multiplier,
            output.bid_size_multiplier,output.ask_size_multiplier,output.max_levels,
            tuple(output.reasons),output.metrics.reconciliation_churn_ratio,
            output.metrics.reject_count,output.metrics.unknown_order_count,
        )
        if signature!=self._signature:
            self.version+=1;self._signature=signature
        return output.model_copy(update={"version":self.version})

    def evaluate(self,evidence,telemetry,history,execution_mode:str)->ExecutionQualityAgentOutput:
        c=self.config
        fills=telemetry.fills(c.execution_quality_window) if execution_mode=="PAPER" else []
        captures=[spread_capture_bps(f.side,f.price,f.reference_price) for f in fills if f.reference_price is not None]
        average_capture=sum(captures,Decimal("0"))/Decimal(len(captures)) if captures else None
        markouts,_=telemetry.markouts(history,horizon_seconds=c.toxic_flow_markout_horizon_seconds,window=c.execution_quality_window) if execution_mode=="PAPER" else ([],0)
        average_markout=sum((m.signed_markout_bps for m in markouts),Decimal("0"))/Decimal(len(markouts)) if markouts else None
        cycles=telemetry.reconcile(c.execution_quality_window)
        keep=sum(x.keep_count for x in cycles)
        activity=telemetry.action_reconcile(c.execution_quality_window)
        create=sum(x.create_count for x in activity)
        replace=sum(x.replace_count for x in activity);cancel=sum(x.cancel_count for x in activity)
        churn=churn_ratio(keep,create,replace,cancel)
        statuses=telemetry.order_status_counts()
        rejected=statuses.get(OrderStatus.REJECTED.value,0)
        unknown=statuses.get(OrderStatus.UNKNOWN.value,0)
        terminal=sum(statuses.get(s.value,0) for s in (OrderStatus.FILLED,OrderStatus.CANCELLED,OrderStatus.REPLACED,OrderStatus.REJECTED))
        filled=statuses.get(OrderStatus.FILLED.value,0)
        filled_ratio=Decimal(filled)/Decimal(terminal) if terminal else None
        metrics=ExecutionQualityMetrics(
            fill_count=len(fills),filled_order_ratio=filled_ratio,
            average_spread_capture_bps=average_capture,average_mature_markout_bps=average_markout,
            reject_count=rejected,unknown_order_count=unknown,keep_count=keep,create_count=create,
            replace_count=replace,cancel_count=cancel,reconciliation_churn_ratio=churn,
        )
        simulated=execution_mode=="PAPER" and bool(fills) and all(f.simulated for f in fills)
        base=dict(agent="EXECUTION_QUALITY",simulated=simulated or evidence.simulated,evidence_version=evidence.version,version=self.version)

        if not c.agents_enabled or not c.execution_quality_agent_enabled:
            return self._versioned(ExecutionQualityAgentOutput(
                **base,health=AgentHealth.DISABLED,confidence=Decimal("0"),
                spread_multiplier=Decimal("1"),bid_size_multiplier=Decimal("1"),ask_size_multiplier=Decimal("1"),
                reasons=["execution-quality agent disabled"],state=ExecutionQualityState.INSUFFICIENT_DATA,metrics=metrics,
            ))

        if execution_mode!="PAPER":
            order_risk=Decimal("1") if rejected or unknown else _clamp(churn/c.execution_quality_max_churn_ratio)
            if order_risk>0:
                spread=_clamp(Decimal("1")+c.execution_quality_spread_strength*order_risk,Decimal("1"),c.agent_max_spread_multiplier)
                size=_clamp(Decimal("1")-c.execution_quality_size_strength*order_risk,c.agent_min_size_multiplier,Decimal("1"))
                return self._versioned(ExecutionQualityAgentOutput(
                    **base,health=AgentHealth.DEGRADED,confidence=Decimal("1"),
                    spread_multiplier=spread,bid_size_multiplier=size,ask_size_multiplier=size,
                    reasons=["TESTNET fill-quality unavailable; authoritative order/reconciliation evidence is degraded",
                             f"reconciliation churn {churn}; rejects {rejected}; unknown {unknown}"],
                    state=ExecutionQualityState.POOR,metrics=metrics,
                ))
            return self._versioned(ExecutionQualityAgentOutput(
                **base,health=AgentHealth.INSUFFICIENT_DATA,confidence=Decimal("0"),
                spread_multiplier=Decimal("1"),bid_size_multiplier=Decimal("1"),ask_size_multiplier=Decimal("1"),
                reasons=["TESTNET authoritative fill ledger unavailable; fill quality not fabricated"],
                state=ExecutionQualityState.INSUFFICIENT_DATA,metrics=metrics,
            ))

        if len(fills)<c.execution_quality_min_fills:
            return self._versioned(ExecutionQualityAgentOutput(
                **base,health=AgentHealth.INSUFFICIENT_DATA,confidence=Decimal("0"),
                spread_multiplier=Decimal("1"),bid_size_multiplier=Decimal("1"),ask_size_multiplier=Decimal("1"),
                reasons=[f"fill observations {len(fills)}/{c.execution_quality_min_fills}"]
                    + (["provisional: mature markout unavailable"] if average_capture is not None and average_capture>0 and average_markout is None else []),
                state=ExecutionQualityState.INSUFFICIENT_DATA,metrics=metrics,
            ))

        poor_markout=average_markout is not None and average_markout<=-c.execution_quality_poor_markout_bps
        poor_capture=average_capture is not None and average_capture<0
        poor=poor_markout or poor_capture or churn>c.execution_quality_max_churn_ratio or rejected>0 or unknown>0
        good=(not poor and average_capture is not None and average_capture>0 and (average_markout is not None and average_markout>=0) and churn<c.execution_quality_max_churn_ratio/Decimal("2"))
        state=ExecutionQualityState.POOR if poor else ExecutionQualityState.GOOD if good else ExecutionQualityState.NORMAL
        churn_score=_clamp(churn/c.execution_quality_max_churn_ratio)
        markout_score=_clamp(abs(min(average_markout or Decimal("0"),Decimal("0")))/c.execution_quality_poor_markout_bps)
        order_score=Decimal("1") if rejected or unknown else Decimal("0")
        risk_score=max(churn_score,markout_score,order_score)
        confidence=_clamp(Decimal(len(fills))/Decimal(max(c.execution_quality_min_fills*2,1)))
        spread=_clamp(Decimal("1")+c.execution_quality_spread_strength*risk_score,Decimal("1"),c.agent_max_spread_multiplier)
        size=_clamp(Decimal("1")-c.execution_quality_size_strength*risk_score,c.agent_min_size_multiplier,Decimal("1"))
        reasons=[f"reconciliation churn {churn}",f"rejects {rejected}; unknown {unknown}"]
        if average_markout is None:
            reasons.append("provisional: mature markout unavailable")
        else:
            reasons.append(f"mature markout {average_markout} bps ({len(markouts)} fills)")
        if confidence<c.agent_min_confidence:
            spread=Decimal("1");size=Decimal("1")
            reasons.append("confidence below minimum; neutral recommendation")
        return self._versioned(ExecutionQualityAgentOutput(
            **base,health=AgentHealth.READY,confidence=confidence,
            spread_multiplier=spread,bid_size_multiplier=size,ask_size_multiplier=size,
            reasons=reasons,state=state,metrics=metrics,
        ))
