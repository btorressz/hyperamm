import type {
  MarketResearchComparisonRequest, MarketResearchComparisonResult,
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
  ResearchCatalog, ResearchProposal, ResearchPreviewResponse, ResearchComparison,
  ResearchMarketCatalog, LiveMarketId, LiveMarketStreamStatus, LiveMarketHistory, LiveProviderHealth, LiveStreamSnapshot,
} from "../types";
import type { ReplaySummary, ReplayProvenance, HistoricalReplayRequest, HistoricalReplayResult } from '../types/replay';
import type { AgentName } from '../utils/researchEvidence';
import type { ScenarioHistoricalRequest, ScenarioHistoricalResponse } from '../types/scenarioReplayComparison';
import { checkedComparisonResponse } from '../utils/scenarioReplayComparison';
const API = "/api/v1";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (r.status === 429 && (path.startsWith("/simulation/") || path.startsWith('/research-vault/')))
    throw new Error(
      "Research capacity is busy. Try again after the current simulation or optimization finishes.",
    );
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    const detail = body?.detail;
    if (path.startsWith('/simulation/') || path.startsWith('/research-vault/')) {
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
// Bound bytes before parsing untrusted research JSON, including chunked bodies.
export async function readHistoricalJson(response:Response, limit=64_000_000):Promise<unknown> {
  const length=response.headers.get('Content-Length');
  if(length && Number(length)>limit){await response.body?.cancel();throw new Error('Historical response exceeds the browser evidence budget.');}
  const reader=response.body?.getReader();
  if(!reader)throw new Error('Historical response is unavailable.');
  const decoder=new TextDecoder('utf-8',{fatal:true});
  let size=0,wire='';
  try{
    for(;;){const {done,value}=await reader.read();if(done)break;
      size+=value.byteLength;
      if(size>limit)throw new Error('Historical response exceeds the browser evidence budget.');
      wire+=decoder.decode(value,{stream:true});
    }
    wire+=decoder.decode();
    return JSON.parse(wire) as unknown;
  }catch{await reader.cancel().catch(()=>{});throw new Error('Historical response is malformed or exceeds the browser evidence budget.');}
  finally{reader.releaseLock();}
}
async function historicalRequest<T>(path:string,init?:RequestInit,limit=64_000_000):Promise<T> {
  const response=await fetch(API+path,{...init,headers:{'Content-Type':'application/json'},cache:'no-store'});
  if(!response.ok){
    if(response.status===429)throw new Error('Shared research worker busy. Retry after its current job completes; cancelling a browser request does not stop a running job.');
    if(response.status===503)throw new Error('Historical replay vault or research admission unavailable. Configure private local storage in the backend.');
    if(response.status===422){
      const wire=await readHistoricalJson(response,64000).catch(()=>null) as {detail?:{issues?:unknown[]}}|null;
      const allowedCodes=['INCOMPLETE_FRAME','COMPONENT_TOO_OLD','SHORT_SEGMENT','NO_VIABLE_FRAMES','FRAME_LIMIT','SEGMENT_LIMIT','IDENTITY_MISMATCH'];
      const allowedFields=['order_book','perp_context','mark_price','oracle_price','funding_rate','open_interest_base','positive_l2_sizes'];
      const issues=Array.isArray(wire?.detail?.issues)?wire.detail.issues.slice(0,8).map(raw=>{
        const i=raw as {code?:unknown;missing_fields?:unknown[]}|null;
        const code=typeof i?.code==='string'&&allowedCodes.includes(i.code)?i.code:'REJECTED';
        const fields=Array.isArray(i?.missing_fields)?i.missing_fields.filter((f):f is string=>typeof f==='string'&&allowedFields.includes(f)).slice(0,7):[];
        return code+(fields.length?' ('+fields.join(', ')+')':'');
      }).join('; '):null;
      throw new Error(issues?'Historical replay rejected: '+issues:'Historical evidence or replay settings rejected (422).');
    }
    throw new Error('Historical research request failed (HTTP '+response.status+').');
  }
  return await readHistoricalJson(response,limit) as T;
}
function livePath(market: LiveMarketId, resource: string) {
  if (!['BTC','ETH','SOL'].includes(market)) throw new Error('Unsupported live market');
  return `/live-markets/${market}/${resource}`;
}
export const api = {
  scenarioHistoricalComparison: async(body:ScenarioHistoricalRequest,signal?:AbortSignal):Promise<ScenarioHistoricalResponse> =>
    checkedComparisonResponse(await historicalRequest('/research-comparison/scenario-historical',
      {method:'POST',body:JSON.stringify(body),signal},1_000_000),body),
  historicalReplaySummaries: (signal?:AbortSignal)=>historicalRequest<ReplaySummary[]>('/historical-replay/dataset-summaries',{signal}),
  historicalReplayProvenance: (id:string,signal?:AbortSignal)=>historicalRequest<ReplayProvenance>('/historical-replay/provenance?dataset_id='+encodeURIComponent(id),{signal}),
  historicalReplayRun: (body:HistoricalReplayRequest,signal?:AbortSignal)=>historicalRequest<HistoricalReplayResult>('/historical-replay/run',{method:'POST',body:JSON.stringify(body),signal}),
  compareMarketResearch: (body: MarketResearchComparisonRequest, signal?: AbortSignal) =>
    request<MarketResearchComparisonResult>('/research-market-comparison/compare', {method:'POST', body:JSON.stringify(body), signal, cache:'no-store'}),
  liveStreamStatus: (market: LiveMarketId, signal?: AbortSignal) =>
    request<LiveMarketStreamStatus>(livePath(market,'stream-status'), {signal,cache:'no-store'}),
  liveStreamSnapshot: (market: LiveMarketId, signal?: AbortSignal) =>
    request<LiveStreamSnapshot>(livePath(market,'stream-snapshot'), {signal,cache:'no-store'}),
  liveMarketHistory: (market: LiveMarketId, limit = 100, signal?: AbortSignal) => {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 1000) throw new Error('History limit must be 1–1000');
    return request<LiveMarketHistory>(livePath(market,`history?limit=${limit}`), {signal,cache:'no-store'});
  },
  liveProviderHealth: (market: LiveMarketId, signal?: AbortSignal) =>
    request<LiveProviderHealth>(livePath(market,'references'), {signal,cache:'no-store'}),
  researchMarkets: (signal?: AbortSignal) => request<ResearchMarketCatalog>('/research-markets', {signal}),
  researchPresets: (signal?: AbortSignal) => request<ResearchCatalog>('/research-vault/presets', {signal}),
  researchPreview: (body: ResearchProposal, signal?: AbortSignal) => request<ResearchPreviewResponse>('/research-vault/preview',
    {method: 'POST', body: JSON.stringify(body), signal}),
  compareResearch: (body: unknown) => request<ResearchComparison>('/research-vault/compare',
    {method: 'POST', body: JSON.stringify(body)}),
  terminalHistory: (range: HistoryRange = "session", limit = 600, signal?: AbortSignal) =>
    request<TerminalHistory>(`/terminal/history?range=${range}&limit=${limit}`, { signal }),
  terminalEvents: (category?: EventCategory, limit = 100, signal?: AbortSignal) =>
    request<TerminalEvents>(
      `/terminal/events?limit=${limit}${category ? "&category=" + category : ""}`,
      { signal },
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
