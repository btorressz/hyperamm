import type { TerminalState } from "../types";

// Consume backend emission-time source freshness, never browser connection time.
export function currentSourcePrices(t: TerminalState | null, observationCurrent = true) {
  const p = observationCurrent ? t?.perp_context : null;
  const c = t?.reference_consensus;
  const evidence = t?.references?.evidence;
  const supported = !!(observationCurrent && t && c && evidence && c.eligible_providers.length &&
    Date.parse(c.updated_at) <= Date.parse(t.emitted_at) &&
    c.eligible_providers.every(provider => {
      const e = evidence[provider];
      return e && e.healthy && !e.stale && e.price != null;
    }));
  return {
    strategy_reference_price: p && !p.stale ? p.strategy_reference_price : null,
    mark_price: p && !p.stale ? p.mark_price : null,
    oracle_price: p && !p.stale ? p.oracle_price : null,
    consensus_price: supported ? c!.consensus_price : null,
  };
}

// Display projection only. Keep accepted evidence and backend decisions immutable.
// External-provider budgets stay backend-owned; receipt cannot renew source time.
export function displayedTerminal(t: TerminalState, nowMs: number): TerminalState {
  const emittedMs = Date.parse(t.emitted_at);
  const elapsed = Math.max(0, nowMs - emittedMs);
  const p = t.perp_context;
  const perpStale = p && (p.stale ||
    nowMs - Date.parse(p.updated_at) > t.strategy.config.perp_context_stale_after_seconds * 1000);
  return {
    ...t,
    perp_context: p ? { ...p, stale: !!perpStale } : null,
    references: t.references ? {
      ...t.references,
      evidence: Object.fromEntries(Object.entries(t.references.evidence).map(([key, e]) => [key, {
        ...e, age_ms: e.age_ms + elapsed,
      }])),
    } : null,
  };
}

// Pure presentation age for independent observations. An unreliable monotonic
// interval is uncertainty; it can never renew evidence or reduce a reported age.
export function advancingAge(reported: number | null, receivedAt: number, now: number, transitSeconds = 0): number | null {
  if (reported === null || ![reported, receivedAt, now, transitSeconds].every(Number.isFinite) || now < receivedAt || transitSeconds < 0) return null;
  return Math.max(0, reported) + transitSeconds + (now - receivedAt) / 1000;
}
