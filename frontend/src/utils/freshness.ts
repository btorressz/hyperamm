import type { TerminalState } from "../types";

// Consume backend emission-time source freshness, never browser connection time.
export function currentSourcePrices(t: TerminalState | null) {
  const p = t?.perp_context;
  const c = t?.reference_consensus;
  const evidence = t?.references?.evidence;
  const supported = !!(t && c && evidence && c.eligible_providers.length &&
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
