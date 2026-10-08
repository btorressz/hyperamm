from __future__ import annotations

from decimal import Decimal

from .common import ONE, ZERO, VersionedAgent, clamp, mean, quantile, seconds
from .models import AgentHealth, HorizonMarkoutMetrics, ToxicFlowAgentOutput, ToxicFlowMetrics, ToxicFlowState


class ToxicFlowAgent(VersionedAgent):
    """Equal horizon weighting per fill, then bounded recency weighting per side.

    Recency weight = H/(H+age_seconds). Severity = min(1, negative_bps/threshold).
    Each horizon toxicity = (adverse indicator + severity)/2. Missing horizons
    are excluded, never imputed. Confidence reports side sample/horizon coverage.
    """

    def evaluate(self, evidence, telemetry, history):
        c = self.config
        horizons = sorted(set(c.toxic_flow_markout_horizons_seconds) | {c.toxic_flow_markout_horizon_seconds})
        telemetry.register_horizons(horizons)
        fills = telemetry.fills(c.toxic_flow_window_fills)
        by_fill = {f.identity: [] for f in fills}
        summaries = []
        all_markouts = []
        primary = []
        primary_pending = 0
        means = {}
        for horizon in horizons:
            markouts, pending = telemetry.markouts(history, horizon_seconds=horizon, window=c.toxic_flow_window_fills)
            if horizon == c.toxic_flow_markout_horizon_seconds:
                primary, primary_pending = markouts, pending
            means[horizon] = mean(m.signed_markout_bps for m in markouts)
            rates = {}
            for side in ("BID", "ASK"):
                items = [m for m in markouts if m.side == side]
                rates[side] = Decimal(sum(m.signed_markout_bps < 0 for m in items))/len(items) if items else None
            summaries.append(HorizonMarkoutMetrics(horizon_seconds=Decimal(str(horizon)),
                matured_fills=len(markouts), pending_markouts=pending,
                unavailable_markouts=telemetry.unavailable_markouts(horizon_seconds=horizon, window=c.toxic_flow_window_fills),
                mean_markout_bps=means[horizon], bid_adverse_rate=rates["BID"], ask_adverse_rate=rates["ASK"]))
            for m in markouts:
                by_fill[m.fill_identity].append(m)
            all_markouts.extend(markouts)

        scores = {}
        confidences = {}
        per_fill_scores = {}
        weighted_severity = []
        adverse_rates = {}
        for fill in fills:
            items = by_fill[fill.identity]
            if items:
                severities = [clamp(-m.signed_markout_bps/c.toxic_flow_adverse_markout_bps) for m in items]
                per_fill_scores[fill.identity] = mean((Decimal(m.signed_markout_bps < 0)+s)/2 for m,s in zip(items,severities))
                weighted_severity.append(mean(severities))
        for side in ("BID", "ASK"):
            items = [f for f in fills if f.side == side and f.identity in per_fill_scores]
            weights = [c.toxic_flow_recency_half_life_seconds/(c.toxic_flow_recency_half_life_seconds+max(ZERO, seconds(evidence.updated_at-f.timestamp))) for f in items]
            scores[side] = (sum((per_fill_scores[f.identity]*w for f,w in zip(items,weights)), ZERO)/sum(weights, ZERO)) if items else ZERO
            coverage = mean(Decimal(len(by_fill[f.identity]))/len(horizons) for f in items) or ZERO
            confidences[side] = clamp(Decimal(len(items))/(c.toxic_flow_min_matured_fills*2))*coverage
            adverse_rates[side] = mean(Decimal(any(m.signed_markout_bps < 0 for m in by_fill[f.identity])) for f in items)
        overall = max(scores.values())
        matured = len(primary)
        adverse = [m for m in primary if m.signed_markout_bps < 0]
        primary_rate = Decimal(len(adverse))/matured if matured else ZERO
        notional_items = [f for f in fills if f.identity in per_fill_scores]
        total_notional = sum((f.price*f.size for f in notional_items), ZERO)
        notional_score = (sum((per_fill_scores[f.identity]*f.price*f.size for f in notional_items), ZERO)/total_notional) if total_notional else None
        values = [m.signed_markout_bps for m in primary]
        metrics = ToxicFlowMetrics(total_fills=len(fills), matured_fills=matured, pending_markouts=primary_pending,
            adverse_fill_count=len(adverse), adverse_fill_rate=primary_rate,
            mean_signed_markout_bps=mean(values), mean_adverse_markout_bps=mean(m.signed_markout_bps for m in adverse),
            bid_toxic_flow_score=scores["BID"], ask_toxic_flow_score=scores["ASK"], overall_toxic_flow_score=overall,
            horizons=tuple(summaries), markout_1s_bps=means.get(1), markout_5s_bps=means.get(5), markout_15s_bps=means.get(15),
            bid_adverse_rate=adverse_rates["BID"], ask_adverse_rate=adverse_rates["ASK"],
            weighted_adverse_severity=mean(weighted_severity) or ZERO,
            median_markout_bps=quantile(values, Decimal(".5")), lower_quantile_markout_bps=quantile(values, Decimal(".1")),
            upper_quantile_markout_bps=quantile(values, Decimal(".9")),
            recency_weighted_toxicity=overall, notional_weighted_toxicity=notional_score,
            toxicity_persistence=mean(Decimal(all(m.signed_markout_bps < 0 for m in by_fill[f.identity]))
                for f in notional_items if len(by_fill[f.identity]) == len(horizons)) or ZERO,
            bid_confidence=confidences["BID"], ask_confidence=confidences["ASK"])
        health = AgentHealth.READY
        state = ToxicFlowState.TOXIC if overall >= Decimal(".70") else ToxicFlowState.ELEVATED if overall >= Decimal(".35") else ToxicFlowState.NORMAL
        confidence = clamp(Decimal(matured)/(c.toxic_flow_min_matured_fills*2))
        reasons = [f"overall adverse-selection score {overall}", f"adverse fill rate {primary_rate}", "equal available horizons per fill; rational half-life recency weights"]
        spread = clamp(ONE+c.toxic_flow_spread_strength*overall, ONE, c.agent_max_spread_multiplier)
        bid = clamp(ONE-c.toxic_flow_size_strength*scores["BID"], c.agent_min_size_multiplier, ONE)
        ask = clamp(ONE-c.toxic_flow_size_strength*scores["ASK"], c.agent_min_size_multiplier, ONE)
        if not c.agents_enabled or not c.toxic_flow_agent_enabled:
            health = AgentHealth.DISABLED
            state = ToxicFlowState.INSUFFICIENT_DATA
            confidence = ZERO
            reasons = ["toxic-flow agent disabled"]
        elif matured < c.toxic_flow_min_matured_fills:
            health = AgentHealth.INSUFFICIENT_DATA
            state = ToxicFlowState.INSUFFICIENT_DATA
            confidence = ZERO
            reasons = [f"matured fill markouts {matured}/{c.toxic_flow_min_matured_fills}"]
        if confidence < c.agent_min_confidence or health != AgentHealth.READY:
            spread = bid = ask = ONE
        return self._versioned(ToxicFlowAgentOutput(agent="TOXIC_FLOW", health=health, confidence=confidence,
            state=state, metrics=metrics, spread_multiplier=spread, bid_size_multiplier=bid, ask_size_multiplier=ask,
            reasons=reasons, simulated=evidence.simulated or (bool(fills) and all(f.simulated for f in fills)),
            evidence_version=evidence.version, version=self.version, updated_at=evidence.updated_at))
