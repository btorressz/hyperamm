import type {
  StrategyState,
  TerminalHistory,
  TerminalEvents,
  HistoryRange,
  EventCategory,
  AccountingLedgerState,
  PnlBreakdownState,
  VaultSnapshot,
  OptimizationResult,
  SimulationResult,
  StrategyConfig,
  AgentEvent,
} from "../types";
import type { AgentName } from '../utils/researchEvidence';
const API = "/api/v1";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (r.status === 429 && path.startsWith("/simulation/"))
    throw new Error(
      "Research capacity is busy. Try again after the current simulation or optimization finishes.",
    );
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    const detail = body?.detail;
    if (path.startsWith('/simulation/')) {
      const message = Array.isArray(detail)
        ? detail.map((e: {loc: unknown[]; msg: string}) => `${e.loc.slice(1).join('.')}: ${e.msg}`).join('; ')
        : typeof detail === 'string' ? detail : `HTTP ${r.status}`;
      const advice = r.status === 422
        ? 'Review the scenario, frame bounds and parameter grid.'
        : r.status === 503
          ? 'Research service unavailable. Retry when capacity coordination is restored.'
          : r.status >= 500
            ? 'Research failed on the server. Retry or inspect backend diagnostics.'
            : 'Retry the research request.';
      throw new Error(`${message} ${advice}`);
    }
    throw new Error(
      Array.isArray(detail)
        ? detail
            .map(
              (e: { loc: unknown[]; msg: string }) =>
                `${e.loc.slice(1).join(".")}: ${e.msg}`,
            )
            .join("; ")
        : typeof detail === "string"
          ? detail
          : `HTTP ${r.status}`,
    );
  }
  return r.json();
}
export const api = {
  terminalHistory: (range: HistoryRange = "session", limit = 600, signal?: AbortSignal) =>
    request<TerminalHistory>(`/terminal/history?range=${range}&limit=${limit}`, { signal }),
  terminalEvents: (category?: EventCategory, limit = 100) =>
    request<TerminalEvents>(
      `/terminal/events?limit=${limit}${category ? "&category=" + category : ""}`,
    ),
  health: () =>
    request<{
      status: string;
      app: string;
      stale: boolean;
      mode: string;
      simulated: boolean;
    }>("/health"),
  vault: () => request<VaultSnapshot>("/vault"),
  accountingPnl: () => request<PnlBreakdownState>("/accounting/pnl"),
  accountingLedger: (limit = 100, signal?: AbortSignal) =>
    request<AccountingLedgerState>(`/accounting/ledger?limit=${limit}`, { signal }),
  accountingEvents: () => request("/accounting/events"),
  marketAdaptation: () => request("/market-adaptation"),
  perpContext: () => request("/perp-context"),
  references: () => request("/references"),
  referenceObservations: () => request<{
    market: string; authority: "NONE";
    observations: Array<{
      provider: string; symbol: string; role: string; authority: string;
      price: string | null; source_timestamp: string | null; age_ms: number;
      healthy: boolean; stale: boolean; status: string; error: string | null;
      deviations_bps: Record<string, string | null>;
    }>;
  }>("/references/observations"),
  agents: () => request("/agents"),
  agentEvents: (agent?: AgentName, limit = 100, signal?: AbortSignal) =>
    request<AgentEvent[]>(`/agents/events?limit=${Math.min(250, Math.max(1, limit))}${agent ? '&agent=' + encodeURIComponent(agent) : ''}`, { signal }),
  riskEvidence: () => request("/risk/evidence"),
  riskEvents: () => request("/risk/events"),
  riskAuthorization: () => request("/risk/authorization"),
  simulationScenarios: () =>
    request<{
      simulated: boolean;
      scenarios: Array<{ name: string; description: string }>;
    }>("/simulation/scenarios"),
  runSimulation: (body: unknown) =>
    request<SimulationResult>("/simulation/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  optimizeSimulation: (body: unknown) =>
    request<OptimizationResult>("/simulation/optimize", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateStrategy: (config: StrategyConfig) =>
    request<StrategyState>("/strategy", {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  start: () => request("/strategy/start", { method: "POST" }),
  stop: () => request("/strategy/stop", { method: "POST" }),
  kill: () => request("/risk/kill", { method: "POST" }),
  resume: () => request("/risk/resume", { method: "POST" }),
};
