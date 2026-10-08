from .common import ONE, ZERO, VersionedAgent, clamp
from .models import AgentHealth, PerpCrowdingAgentOutput, PerpCrowdingMetrics, PerpCrowdingState


class PerpCrowdingAgent(VersionedAgent):
    """Crowding requires aligned funding, basis, momentum AND observed OI expansion."""

    def evaluate(self, evidence):
        c = self.config
        oi = evidence.open_interest_change_ratio
        basis = evidence.mark_oracle_basis_bps
        basis_score = clamp(max(abs(basis), abs(evidence.mark_mid_basis_bps))/c.crowding_basis_threshold_bps)
        funding_score = clamp(abs(evidence.funding_rate)/c.crowding_funding_threshold)
        momentum = evidence.momentum_bps or ZERO
        trend_score = clamp(abs(momentum)/c.regime_trend_threshold_bps)
        expansion = clamp((oi or ZERO)/c.crowding_oi_change_threshold)
        long_score = min(funding_score, basis_score, trend_score, expansion) if evidence.funding_rate > 0 and basis > 0 and momentum > 0 and evidence.mark_mid_basis_bps >= 0 else ZERO
        short_score = min(funding_score, basis_score, trend_score, expansion) if evidence.funding_rate < 0 and basis < 0 and momentum < 0 and evidence.mark_mid_basis_bps <= 0 else ZERO
        state = PerpCrowdingState.NEUTRAL
        health = AgentHealth.READY
        confidence = ONE
        score = bid_score = ask_score = ZERO
        reasons = ["funding alone does not establish crowded positioning"]
        if not c.agents_enabled or not c.perp_crowding_agent_enabled:
            state, health, confidence = PerpCrowdingState.INSUFFICIENT_DATA, AgentHealth.DISABLED, ZERO
            reasons = ["perp-crowding agent disabled"]
        elif evidence.perp_stale:
            state, health, confidence = PerpCrowdingState.INSUFFICIENT_DATA, AgentHealth.INSUFFICIENT_DATA, ZERO
            reasons = ["perpetual evidence stale"]
        elif long_score >= c.agent_min_confidence and long_score > 0:
            state = PerpCrowdingState.LONG_CROWDED
            score = bid_score = long_score
            reasons = ["positive funding/basis/momentum with observed OI expansion; reduce BID exposure only"]
        elif short_score >= c.agent_min_confidence and short_score > 0:
            state = PerpCrowdingState.SHORT_CROWDED
            score = ask_score = short_score
            reasons = ["negative funding/basis/momentum with observed OI expansion; reduce ASK exposure only"]
        elif basis_score == ONE and funding_score >= c.agent_min_confidence:
            state = PerpCrowdingState.BASIS_STRESSED
            score = bid_score = ask_score = basis_score
            reasons = ["combined funding and basis stress"]
        elif oi is None:
            state, health, confidence = PerpCrowdingState.INSUFFICIENT_DATA, AgentHealth.INSUFFICIENT_DATA, ZERO
            reasons = ["OI trend unavailable: requires distinct source observations over configured span"]
        elif oi >= c.crowding_oi_change_threshold:
            state = PerpCrowdingState.OI_EXPANSION
            score = bid_score = ask_score = clamp(oi/c.crowding_oi_change_threshold)/2
            reasons = ["observed OI expansion without aligned crowding evidence"]
        elif oi <= -c.crowding_oi_change_threshold:
            state = PerpCrowdingState.OI_UNWIND
            score = bid_score = ask_score = clamp(-oi/c.crowding_oi_change_threshold)/2
            reasons = ["observed OI unwind"]
        metrics = PerpCrowdingMetrics(long_crowding_score=long_score if health == AgentHealth.READY else ZERO,
            short_crowding_score=short_score if health == AgentHealth.READY else ZERO,
            basis_stress_score=basis_score, oi_change_ratio=oi, funding_rate_delta=evidence.funding_rate_delta,
            observation_count=evidence.perp_observation_count)
        advice = self.recommendation(evidence, "crowding", score=score, bid_score=bid_score, ask_score=ask_score)
        advice["confidence"] = confidence
        if confidence < c.agent_min_confidence:
            advice.update(spread_multiplier=ONE, bid_size_multiplier=ONE, ask_size_multiplier=ONE)
        return self._versioned(PerpCrowdingAgentOutput(agent="PERP_CROWDING", health=health, state=state,
            metrics=metrics, reasons=reasons, **advice))
