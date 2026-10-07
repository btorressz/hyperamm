import type { TerminalState } from "../types";
export function validateTerminal(x: unknown): TerminalState {
  if (!x || typeof x !== "object")
    throw new Error("Terminal frame must be an object");
  const t = x as TerminalState;
  if (t.contract_version !== "phase12-v1")
    throw new Error("Unsupported terminal contract");
  if (
    !Number.isSafeInteger(t.sequence) ||
    t.sequence < 1 ||
    !Number.isFinite(Date.parse(t.emitted_at)) ||
    !t.process_id ||
    !t.session_id
  )
    throw new Error("Invalid terminal metadata");
  for (const key of [
    "quotes",
    "strategy_quotes",
    "agent_quotes",
    "authorized_quotes",
    "orders",
    "fills",
    "agent_events",
    "risk_events",
    "reconciliation",
  ] as const)
    if (!Array.isArray(t[key])) throw new Error(`Invalid ${key}`);
  if (
    !t.market ||
    !t.strategy?.config ||
    !t.vault?.execution_accounting ||
    !t.accounting?.pnl ||
    !Array.isArray(t.accounting.events) ||
    !t.risk ||
    !t.risk_firewall ||
    !t.risk_authorization ||
    !t.agents ||
    !t.system_health?.subsystems ||
    !t.execution_summary?.status_counts ||
    !t.diagnostics
  )
    throw new Error("Incomplete terminal state");
  for (const q of [
    ...t.quotes,
    ...t.strategy_quotes,
    ...t.agent_quotes,
    ...t.authorized_quotes,
  ])
    if (
      !q ||
      !["BID", "ASK"].includes(q.side) ||
      !Number.isFinite(Number(q.price)) ||
      !Number.isFinite(Number(q.size))
    )
      throw new Error("Invalid quote evidence");
  if (
    t.references &&
    (!t.references.evidence ||
      !t.references.consensus ||
      !Array.isArray(t.references.consensus.outliers))
  )
    throw new Error("Invalid reference evidence");
  if (t.agents.supervisor && !Array.isArray(t.agents.supervisor.reasons))
    throw new Error("Invalid agent reasons");
  if (
    !["LIVE", "DEMO"].includes(t.market.mode) ||
    !["PAPER", "TESTNET"].includes(t.strategy.config.execution_mode) ||
    typeof t.strategy.running !== "boolean"
  )
    throw new Error("Invalid market / strategy state");
  if (
    t.market.book &&
    (!Array.isArray(t.market.book.bids) ||
      !Array.isArray(t.market.book.asks) ||
      [...t.market.book.bids, ...t.market.book.asks].some(
        (l) =>
          !l ||
          !Number.isFinite(Number(l.price)) ||
          !Number.isFinite(Number(l.size)),
      ))
  )
    throw new Error("Invalid L2 evidence");
  if (
    t.risk_events.some((e) => !e || !Array.isArray(e.reasons)) ||
    t.agent_events.some((e) => !e || !Array.isArray(e.reasons)) ||
    t.accounting.events.some((e) => !e || typeof e.message !== "string")
  )
    throw new Error("Invalid event evidence");
  if (
    t.orders.some(
      (o) =>
        !o ||
        typeof o.client_order_id !== "string" ||
        typeof o.status !== "string",
    ) ||
    t.fills.some((f) => !f || typeof f.timestamp !== "string")
  )
    throw new Error("Invalid execution evidence");
  if (
    !["HEALTHY", "DEGRADED", "HALTED", "UNAVAILABLE"].includes(
      t.system_health.status,
    ) ||
    Object.values(t.system_health.subsystems).some(
      (s) =>
        !s ||
        typeof s.reason !== "string" ||
        !["HEALTHY", "DEGRADED", "HALTED", "UNAVAILABLE"].includes(s.status),
    )
  )
    throw new Error("Invalid system health");
  for (const k of ["regime", "toxic_flow", "execution_quality"] as const) {
    const a = t.agents[k];
    if (a && !Array.isArray(a.reasons))
      throw new Error("Invalid agent evidence");
  }
  return t;
}
