from __future__ import annotations

from decimal import Decimal

from .config import AgentConfig
from .models import AgentHealth,ToxicFlowAgentOutput,ToxicFlowMetrics,ToxicFlowState


def _clamp(value:Decimal,low:Decimal=Decimal("0"),high:Decimal=Decimal("1"))->Decimal:
    return max(low,min(high,value))


class ToxicFlowAgent:
    def __init__(self,config:AgentConfig):
        self.config=config
        self.version=0
        self._signature=None

    def _versioned(self,output:ToxicFlowAgentOutput)->ToxicFlowAgentOutput:
        signature=(
            output.health,output.state,output.confidence,output.spread_multiplier,
            output.bid_size_multiplier,output.ask_size_multiplier,output.max_levels,
            tuple(output.reasons),output.metrics.bid_toxic_flow_score,
            output.metrics.ask_toxic_flow_score,output.metrics.overall_toxic_flow_score,
        )
        if signature!=self._signature:
            self.version+=1;self._signature=signature
        return output.model_copy(update={"version":self.version})

    def evaluate(self,evidence,telemetry,history)->ToxicFlowAgentOutput:
        c=self.config
        markouts,pending=telemetry.markouts(
            history,horizon_seconds=c.toxic_flow_markout_horizon_seconds,window=c.toxic_flow_window_fills
        )
        fills=telemetry.fills(c.toxic_flow_window_fills)
        adverse=[m for m in markouts if m.signed_markout_bps<0]
        bid=[m for m in markouts if m.side=="BID"]
        ask=[m for m in markouts if m.side=="ASK"]
        bid_adverse=[m for m in bid if m.signed_markout_bps<0]
        ask_adverse=[m for m in ask if m.signed_markout_bps<0]

        def score(items):
            if not items:return Decimal("0")
            adverse_items=[m for m in items if m.signed_markout_bps<0]
            rate=Decimal(len(adverse_items))/Decimal(len(items))
            severity=sum((min(Decimal("1"),abs(m.signed_markout_bps)/c.toxic_flow_adverse_markout_bps) for m in adverse_items),Decimal("0"))/Decimal(max(1,len(items)))
            return _clamp((rate+severity)/Decimal("2"))

        bid_score=score(bid);ask_score=score(ask);overall=max(bid_score,ask_score)
        matured=len(markouts)
        adverse_rate=Decimal(len(adverse))/Decimal(matured) if matured else Decimal("0")
        mean=sum((m.signed_markout_bps for m in markouts),Decimal("0"))/Decimal(matured) if matured else None
        mean_adverse=sum((m.signed_markout_bps for m in adverse),Decimal("0"))/Decimal(len(adverse)) if adverse else None
        metrics=ToxicFlowMetrics(
            total_fills=len(fills),matured_fills=matured,pending_markouts=pending,
            adverse_fill_count=len(adverse),adverse_fill_rate=adverse_rate,
            mean_signed_markout_bps=mean,mean_adverse_markout_bps=mean_adverse,
            bid_toxic_flow_score=bid_score,ask_toxic_flow_score=ask_score,
            overall_toxic_flow_score=overall,
        )
        simulated=bool(fills) and all(fill.simulated for fill in fills)
        base=dict(agent="TOXIC_FLOW",simulated=simulated or evidence.simulated,evidence_version=evidence.version,version=self.version)

        if not c.agents_enabled or not c.toxic_flow_agent_enabled:
            return self._versioned(ToxicFlowAgentOutput(
                **base,health=AgentHealth.DISABLED,confidence=Decimal("0"),
                spread_multiplier=Decimal("1"),bid_size_multiplier=Decimal("1"),ask_size_multiplier=Decimal("1"),
                reasons=["toxic-flow agent disabled"],state=ToxicFlowState.INSUFFICIENT_DATA,metrics=metrics,
            ))

        if matured<c.toxic_flow_min_matured_fills:
            return self._versioned(ToxicFlowAgentOutput(
                **base,health=AgentHealth.INSUFFICIENT_DATA,confidence=Decimal("0"),
                spread_multiplier=Decimal("1"),bid_size_multiplier=Decimal("1"),ask_size_multiplier=Decimal("1"),
                reasons=[f"matured fill markouts {matured}/{c.toxic_flow_min_matured_fills}"],
                state=ToxicFlowState.INSUFFICIENT_DATA,metrics=metrics,
            ))

        if overall>=Decimal("0.70"):state=ToxicFlowState.TOXIC
        elif overall>=Decimal("0.35"):state=ToxicFlowState.ELEVATED
        else:state=ToxicFlowState.NORMAL
        confidence=_clamp(Decimal(matured)/Decimal(max(c.toxic_flow_min_matured_fills*2,1)))
        spread=_clamp(Decimal("1")+c.toxic_flow_spread_strength*overall,Decimal("1"),c.agent_max_spread_multiplier)
        bid_size=_clamp(Decimal("1")-c.toxic_flow_size_strength*bid_score,c.agent_min_size_multiplier,Decimal("1"))
        ask_size=_clamp(Decimal("1")-c.toxic_flow_size_strength*ask_score,c.agent_min_size_multiplier,Decimal("1"))
        reasons=[f"overall adverse-selection score {overall}",f"adverse fill rate {adverse_rate}"]
        if confidence<c.agent_min_confidence:
            spread=Decimal("1");bid_size=Decimal("1");ask_size=Decimal("1")
            reasons.append("confidence below minimum; neutral recommendation")

        return self._versioned(ToxicFlowAgentOutput(
            **base,health=AgentHealth.READY,confidence=confidence,
            spread_multiplier=spread,bid_size_multiplier=bid_size,ask_size_multiplier=ask_size,
            reasons=reasons,state=state,metrics=metrics,
        ))
