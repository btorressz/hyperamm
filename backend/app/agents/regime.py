from __future__ import annotations

from decimal import Decimal

from .config import AgentConfig
from .models import (
    AgentHealth,
    AgentRecommendation,
    MarketRegime,
    RegimeAgentOutput,
    RegimeDirection,
)


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(high, value))


class RegimeAgent:
    """Consume Phase 6 per-observation RMS/score/regime without recomputing it.

    Momentum also uses an observation window, not elapsed-time normalization.
    """
    def __init__(self, config: AgentConfig):
        self.config=config
        self.version=0
        self._signature=None

    def _versioned(self, output: RegimeAgentOutput) -> RegimeAgentOutput:
        signature=(
            output.health,output.state,output.direction,output.confidence,
            output.spread_multiplier,output.bid_size_multiplier,output.ask_size_multiplier,
            output.max_levels,tuple(output.reasons),
        )
        if signature!=self._signature:
            self.version+=1
            self._signature=signature
        return output.model_copy(update={"version":self.version})

    def evaluate(self, evidence) -> RegimeAgentOutput:
        c=self.config
        neutral=dict(
            agent="REGIME",spread_multiplier=Decimal("1"),
            bid_size_multiplier=Decimal("1"),ask_size_multiplier=Decimal("1"),
            max_levels=None,simulated=evidence.simulated,evidence_version=evidence.version,
            version=self.version,
        )
        if not c.agents_enabled or not c.regime_agent_enabled:
            return self._versioned(RegimeAgentOutput(
                **neutral,health=AgentHealth.DISABLED,confidence=Decimal("0"),
                reasons=["regime agent disabled"],state=MarketRegime.NORMAL,
                direction=RegimeDirection.NEUTRAL,momentum_bps=evidence.momentum_bps,
                realized_volatility=evidence.realized_volatility,
                volatility_score=evidence.volatility_score,book_imbalance=evidence.book_imbalance,
            ))

        if evidence.history_sample_count<c.regime_min_samples or evidence.momentum_bps is None:
            return self._versioned(RegimeAgentOutput(
                **neutral,health=AgentHealth.WARMING_UP,confidence=Decimal("0"),
                reasons=[f"market history warming up: {evidence.history_sample_count}/{c.regime_min_samples} samples"],
                state=MarketRegime.WARMING_UP,direction=RegimeDirection.NEUTRAL,
                momentum_bps=evidence.momentum_bps,realized_volatility=evidence.realized_volatility,
                volatility_score=evidence.volatility_score,book_imbalance=evidence.book_imbalance,
            ))

        momentum=evidence.momentum_bps
        funding_score=_clamp(abs(evidence.funding_rate)/c.regime_funding_stress_threshold,Decimal("0"),Decimal("1"))
        basis_score=_clamp(max(abs(evidence.mark_oracle_basis_bps),abs(evidence.mark_mid_basis_bps))/c.regime_basis_stress_threshold_bps,Decimal("0"),Decimal("1"))
        book_score=abs(evidence.book_imbalance)
        inventory_score=_clamp(abs(evidence.inventory_ratio),Decimal("0"),Decimal("1"))
        trend_strength=_clamp(abs(momentum)/(c.regime_trend_threshold_bps*Decimal("3")),Decimal("0"),Decimal("1"))
        if momentum>c.regime_trend_threshold_bps:
            direction=RegimeDirection.UP
        elif momentum<-c.regime_trend_threshold_bps:
            direction=RegimeDirection.DOWN
        else:
            direction=RegimeDirection.NEUTRAL

        deviation=abs(evidence.max_reference_deviation_bps or Decimal("0"))
        dislocated=evidence.reference_confidence in {"CONFLICTED","INSUFFICIENT"} or deviation>=c.regime_dislocation_bps or (basis_score==1 and funding_score>=Decimal("0.5"))
        if dislocated:
            state=MarketRegime.DISLOCATED
            score=Decimal("1")
            reasons=[f"reference state {evidence.reference_confidence}",f"reference deviation {deviation} bps"]
        elif evidence.market_adaptation_regime=="HIGH_VOLATILITY":
            state=MarketRegime.HIGH_VOLATILITY
            score=max(Decimal("0.85"),evidence.volatility_score)
            reasons=["Phase 6 high-volatility regime"]
        elif abs(momentum)>=c.regime_trend_threshold_bps:
            state=MarketRegime.TRENDING
            momentum_score=_clamp(abs(momentum)/max(c.regime_trend_threshold_bps*Decimal("3"),Decimal("1")),Decimal("0"),Decimal("1"))
            score=max(Decimal("0.35"),momentum_score)
            reasons=[f"momentum {momentum} bps exceeds trend threshold"]
        elif evidence.volatility_score==0 and abs(momentum)<c.regime_trend_threshold_bps/Decimal("2") and max(funding_score,basis_score,book_score)<Decimal("0.25"):
            state=MarketRegime.QUIET
            score=Decimal("0")
            reasons=["low volatility and low momentum"]
        else:
            state=MarketRegime.NORMAL
            score=_clamp(max(evidence.volatility_score,abs(momentum)/max(c.regime_trend_threshold_bps*Decimal("3"),Decimal("1"))),Decimal("0"),Decimal("1"))
            reasons=["mixed normalized market conditions"]

        # Combinations add caution; inventory alone never becomes a direction signal.
        combined_stress=(funding_score+basis_score)/Decimal("2")
        aligned_pressure=book_score*trend_strength if momentum*evidence.book_imbalance>0 else Decimal("0")
        score=_clamp(max(score,combined_stress,aligned_pressure)*(Decimal("1")+inventory_score/Decimal("5")),Decimal("0"),Decimal("1"))
        if combined_stress>0 or aligned_pressure>0:
            reasons.append("bounded funding/basis stress and momentum/book pressure; inventory context may increase caution")

        confidence=_clamp(Decimal("0.5")+Decimal("0.5")*min(Decimal("1"),Decimal(evidence.history_sample_count)/Decimal(c.regime_momentum_window_samples)),Decimal("0"),Decimal("1"))
        spread=_clamp(Decimal("1")+c.regime_spread_strength*score,Decimal("1"),c.agent_max_spread_multiplier)
        size=_clamp(Decimal("1")-c.regime_size_strength*score,c.agent_min_size_multiplier,Decimal("1"))
        if confidence<c.agent_min_confidence:
            spread=Decimal("1");size=Decimal("1")
            reasons.append("confidence below minimum; neutral recommendation")

        return self._versioned(RegimeAgentOutput(
            agent="REGIME",health=AgentHealth.READY,confidence=confidence,
            spread_multiplier=spread,bid_size_multiplier=size,ask_size_multiplier=size,
            max_levels=None,reasons=reasons,simulated=evidence.simulated,
            evidence_version=evidence.version,version=self.version,state=state,direction=direction,
            momentum_bps=momentum,realized_volatility=evidence.realized_volatility,
            volatility_score=evidence.volatility_score,book_imbalance=evidence.book_imbalance,
            trend_strength=trend_strength,funding_stress_score=funding_score,
            basis_stress_score=basis_score,book_pressure_score=book_score,
            inventory_stress_score=inventory_score,updated_at=evidence.updated_at,
        ))
