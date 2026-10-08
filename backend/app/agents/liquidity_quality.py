from decimal import Decimal

from .common import ONE, ZERO, VersionedAgent, clamp
from .models import AgentHealth, LiquidityQualityAgentOutput, LiquidityQualityMetrics, LiquidityQualityState


class LiquidityQualityAgent(VersionedAgent):
    """Assess bounded normalized top-N depth rather than classify market direction."""

    def evaluate(self, evidence):
        c = self.config
        bid, ask = evidence.top_n_bid_depth_base, evidence.top_n_ask_depth_base
        metrics = LiquidityQualityMetrics(spread_bps=evidence.spread_bps, bid_depth_base=bid,
            ask_depth_base=ask, book_span_bps=evidence.book_span_bps)
        health = AgentHealth.READY
        state = LiquidityQualityState.HEALTHY
        score = ZERO
        imbalance = evidence.depth_imbalance or ZERO
        reasons = ["normalized top-N book conditions healthy"]
        levels = None
        if not c.agents_enabled or not c.liquidity_quality_agent_enabled:
            health = AgentHealth.DISABLED
            state = LiquidityQualityState.INSUFFICIENT_DATA
            reasons = ["liquidity-quality agent disabled"]
        elif bid is None or ask is None or evidence.spread_bps is None:
            health = AgentHealth.INSUFFICIENT_DATA
            state = LiquidityQualityState.INSUFFICIENT_DATA
            reasons = ["normalized book depth/spread unavailable"]
        else:
            thin = clamp(ONE-min(bid, ask)/c.liquidity_thin_depth_base)
            pressure = clamp(abs(imbalance)/c.liquidity_imbalance_threshold)
            instability = clamp((evidence.midpoint_instability_bps or ZERO)/c.liquidity_instability_threshold_bps)
            concentration = clamp((evidence.depth_concentration or ZERO)/c.liquidity_concentration_threshold)
            wide = clamp(evidence.spread_bps/c.liquidity_wide_spread_threshold_bps)
            metrics = metrics.model_copy(update=dict(thin_score=thin, imbalance_score=pressure,
                instability_score=instability, concentration_score=concentration))
            dislocated = evidence.reference_confidence in {"CONFLICTED", "INSUFFICIENT"} or abs(evidence.max_reference_deviation_bps or ZERO) >= c.regime_dislocation_bps
            if dislocated:
                state, score = LiquidityQualityState.DISLOCATED, ONE
            elif instability == ONE and evidence.volatility_score >= Decimal(".5"):
                state, score = LiquidityQualityState.UNSTABLE, ONE
            elif thin > ZERO:
                state, score = LiquidityQualityState.THIN, max(thin, wide/2)
            elif pressure == ONE:
                state, score = LiquidityQualityState.IMBALANCED, pressure
            elif wide == ONE or concentration == ONE:
                state, score = LiquidityQualityState.THIN, max(wide, concentration)/2
            if score > ZERO:
                reasons = [f"book condition {state.value}; top-N depth is in base units", "no top-of-book churn inferred without retained L2 history"]
                if state in {LiquidityQualityState.THIN, LiquidityQualityState.UNSTABLE, LiquidityQualityState.DISLOCATED}:
                    levels = c.liquidity_reduced_max_levels
                    if evidence.upstream_available_levels is not None:
                        levels = min(levels,evidence.upstream_available_levels) if evidence.upstream_available_levels else None
        advice = self.recommendation(evidence, "liquidity", score=score,
            bid_score=score if imbalance >= 0 else score/2,
            ask_score=score if imbalance <= 0 else score/2)
        if health != AgentHealth.READY:
            advice["confidence"] = ZERO
        if advice["confidence"] < c.agent_min_confidence:
            advice.update(spread_multiplier=ONE, bid_size_multiplier=ONE, ask_size_multiplier=ONE)
            levels = None
        return self._versioned(LiquidityQualityAgentOutput(agent="LIQUIDITY_QUALITY", health=health,
            state=state, metrics=metrics, reasons=reasons, max_levels=levels, **advice))
