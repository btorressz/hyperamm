from __future__ import annotations

from collections import deque
from decimal import Decimal

from app.amm.discretizer import normalize_price,normalize_size
from .config import AgentConfig
from .execution_quality import ExecutionQualityAgent
from .models import (
    AgentEvent,AgentHealth,AgentSupervisorDecision,
    ExecutionQualityAgentOutput,ExecutionQualityMetrics,ExecutionQualityState,
    MarketRegime,RegimeAgentOutput,RegimeDirection,
    ToxicFlowAgentOutput,ToxicFlowMetrics,ToxicFlowState,
    recommendation_signature,semantic_fingerprint,utcnow,
)
from .regime import RegimeAgent
from .toxic_flow import ToxicFlowAgent


def _neutral_regime(evidence, reason, *, health=AgentHealth.ERROR):
    return RegimeAgentOutput(
        agent="REGIME",health=health,confidence=Decimal("0"),
        spread_multiplier=Decimal("1"),bid_size_multiplier=Decimal("1"),ask_size_multiplier=Decimal("1"),
        reasons=[reason],simulated=evidence.simulated,evidence_version=evidence.version,version=0,
        state=MarketRegime.WARMING_UP if health==AgentHealth.WARMING_UP else MarketRegime.NORMAL,
        direction=RegimeDirection.NEUTRAL,momentum_bps=evidence.momentum_bps,
        realized_volatility=evidence.realized_volatility,volatility_score=evidence.volatility_score,
        book_imbalance=evidence.book_imbalance,
    )


def _neutral_toxic(evidence, reason, *, health=AgentHealth.ERROR):
    return ToxicFlowAgentOutput(
        agent="TOXIC_FLOW",health=health,confidence=Decimal("0"),
        spread_multiplier=Decimal("1"),bid_size_multiplier=Decimal("1"),ask_size_multiplier=Decimal("1"),
        reasons=[reason],simulated=evidence.simulated,evidence_version=evidence.version,version=0,
        state=ToxicFlowState.INSUFFICIENT_DATA,
        metrics=ToxicFlowMetrics(total_fills=0,matured_fills=0,pending_markouts=0,adverse_fill_count=0,
            adverse_fill_rate=Decimal("0"),bid_toxic_flow_score=Decimal("0"),ask_toxic_flow_score=Decimal("0"),
            overall_toxic_flow_score=Decimal("0")),
    )


def _neutral_execution(evidence, reason, *, health=AgentHealth.ERROR):
    return ExecutionQualityAgentOutput(
        agent="EXECUTION_QUALITY",health=health,confidence=Decimal("0"),
        spread_multiplier=Decimal("1"),bid_size_multiplier=Decimal("1"),ask_size_multiplier=Decimal("1"),
        reasons=[reason],simulated=evidence.simulated,evidence_version=evidence.version,version=0,
        state=ExecutionQualityState.INSUFFICIENT_DATA,
        metrics=ExecutionQualityMetrics(fill_count=0,reject_count=0,unknown_order_count=0,keep_count=0,
            create_count=0,replace_count=0,cancel_count=0,reconciliation_churn_ratio=Decimal("0")),
    )


class AgentSupervisor:
    def __init__(self,config:AgentConfig):
        self.config=config
        self.regime=RegimeAgent(config)
        self.toxic_flow=ToxicFlowAgent(config)
        self.execution_quality=ExecutionQualityAgent(config)
        self.version=0
        self.fingerprint=semantic_fingerprint({"enabled":config.agents_enabled,"initial":True})
        self._signature=None
        self._states={}
        self.events:deque[AgentEvent]=deque(maxlen=250)

    def _record_state(self,agent,state,reasons):
        previous=self._states.get(agent)
        if previous!=state:
            self.events.append(AgentEvent(agent=agent,previous_state=previous,new_state=state,reasons=list(reasons),version=self.version))
            self._states[agent]=state

    def evaluate(self,*,evidence,telemetry,history,execution_mode:str)->AgentSupervisorDecision:
        try:regime=self.regime.evaluate(evidence)
        except Exception as exc:regime=_neutral_regime(evidence,f"regime agent error: {exc}")
        try:toxic=self.toxic_flow.evaluate(evidence,telemetry,history)
        except Exception as exc:toxic=_neutral_toxic(evidence,f"toxic-flow agent error: {exc}")
        try:execution=self.execution_quality.evaluate(evidence,telemetry,history,execution_mode)
        except Exception as exc:execution=_neutral_execution(evidence,f"execution-quality agent error: {exc}")

        enabled=self.config.agents_enabled
        if enabled:
            spread=max(regime.spread_multiplier,toxic.spread_multiplier,execution.spread_multiplier)
            bid=min(regime.bid_size_multiplier,toxic.bid_size_multiplier,execution.bid_size_multiplier)
            ask=min(regime.ask_size_multiplier,toxic.ask_size_multiplier,execution.ask_size_multiplier)
            levels=[x.max_levels for x in (regime,toxic,execution) if x.max_levels is not None]
            max_levels=min(levels) if levels else None
        else:
            spread=Decimal("1");bid=Decimal("1");ask=Decimal("1");max_levels=None

        spread=max(Decimal("1"),min(self.config.agent_max_spread_multiplier,spread))
        bid=max(self.config.agent_min_size_multiplier,min(Decimal("1"),bid))
        ask=max(self.config.agent_min_size_multiplier,min(Decimal("1"),ask))
        reasons=[
            f"REGIME: {'; '.join(regime.reasons)}",
            f"TOXIC_FLOW: {'; '.join(toxic.reasons)}",
            f"EXECUTION_QUALITY: {'; '.join(execution.reasons)}",
        ]
        semantic={
            "enabled":enabled,
            "regime":recommendation_signature(regime),
            "toxic_flow":recommendation_signature(toxic),
            "execution_quality":recommendation_signature(execution),
            "spread_multiplier":spread,
            "bid_size_multiplier":bid,
            "ask_size_multiplier":ask,
            "max_levels":max_levels,
            "market_version":evidence.market_version,
            "inventory_version":evidence.inventory_version,
            "perp_version":evidence.perp_version,
            "reference_version":evidence.reference_version,
        }
        fingerprint=semantic_fingerprint(semantic)
        decision_material={
            "enabled":enabled,
            "regime":recommendation_signature(regime),
            "toxic_flow":recommendation_signature(toxic),
            "execution_quality":recommendation_signature(execution),
            "spread_multiplier":spread,
            "bid_size_multiplier":bid,
            "ask_size_multiplier":ask,
            "max_levels":max_levels,
        }
        signature=semantic_fingerprint(decision_material)
        if signature!=self._signature:
            self.version+=1
            self._signature=signature
            self.events.append(AgentEvent(agent="SUPERVISOR",previous_state=None,new_state="MATERIAL_CHANGE",reasons=reasons,version=self.version))
        self.fingerprint=fingerprint
        self._record_state("REGIME",regime.state.value,regime.reasons)
        self._record_state("TOXIC_FLOW",toxic.state.value,toxic.reasons)
        self._record_state("EXECUTION_QUALITY",execution.state.value,execution.reasons)

        return AgentSupervisorDecision(
            market=evidence.market,enabled=enabled,regime=regime,toxic_flow=toxic,
            execution_quality=execution,spread_multiplier=spread,bid_size_multiplier=bid,
            ask_size_multiplier=ask,max_levels=max_levels,reasons=reasons,
            market_version=evidence.market_version,inventory_version=evidence.inventory_version,
            perp_version=evidence.perp_version,reference_version=evidence.reference_version,
            simulated=evidence.simulated,version=self.version,fingerprint=fingerprint,updated_at=utcnow(),
        )

    def event_payload(self):
        return [event.model_dump(mode="json") for event in self.events]


def transform_quotes(quotes,decision:AgentSupervisorDecision,*,center,tick_size,size_precision):
    if not decision.enabled:
        return list(quotes)
    if decision.spread_multiplier==1 and decision.bid_size_multiplier==1 and decision.ask_size_multiplier==1 and decision.max_levels is None:
        return [q.model_copy(update={
            "pre_agent_price":q.price,"pre_agent_size":q.size,"agent_spread_multiplier":Decimal("1"),
            "agent_size_multiplier":Decimal("1"),"agent_regime":decision.regime.state.value,
            "agent_toxic_flow_state":decision.toxic_flow.state.value,
            "agent_execution_quality_state":decision.execution_quality.state.value,
            "agent_version":decision.version,
        }) for q in quotes]

    quantum=Decimal(1).scaleb(-size_precision)
    out=[]
    for quote in quotes:
        if decision.max_levels is not None and quote.level_index>=decision.max_levels:
            continue
        distance=abs(quote.price-center)
        widened=distance*decision.spread_multiplier
        if quote.side=="BID":
            price=normalize_price(center-widened,tick_size,"BID")
            multiplier=decision.bid_size_multiplier
        elif quote.side=="ASK":
            price=normalize_price(center+widened,tick_size,"ASK")
            multiplier=decision.ask_size_multiplier
        else:
            raise ValueError("agent quote side must be BID or ASK")
        if quote.side=="BID" and price>quote.price:
            raise ValueError("agent transform may not tighten BID")
        if quote.side=="ASK" and price<quote.price:
            raise ValueError("agent transform may not tighten ASK")
        raw_size=max(quote.size*multiplier,quantum)
        size=normalize_size(raw_size,size_precision)
        if size>quote.size:
            size=quote.size
        if size<=0 or not size.is_finite() or price<=0 or not price.is_finite():
            raise ValueError("agent-adapted quotes must be finite and positive")
        fair=quote.market_fair_value or center
        distance_bps=abs(price-fair)/fair*Decimal("10000")
        out.append(quote.model_copy(update={
            "price":price,"size":size,"distance_bps":distance_bps,
            "pre_agent_price":quote.price,"pre_agent_size":quote.size,
            "agent_spread_multiplier":decision.spread_multiplier,
            "agent_size_multiplier":multiplier,"agent_regime":decision.regime.state.value,
            "agent_toxic_flow_state":decision.toxic_flow.state.value,
            "agent_execution_quality_state":decision.execution_quality.state.value,
            "agent_version":decision.version,
        }))
    bids=sorted((q for q in out if q.side=="BID"),key=lambda q:q.price,reverse=True)
    asks=sorted((q for q in out if q.side=="ASK"),key=lambda q:q.price)
    if bids and asks and bids[0].price>=asks[0].price:
        raise ValueError("agent-adapted quote market is crossed")
    return bids+asks
