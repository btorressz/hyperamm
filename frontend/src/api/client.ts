import type {PortfolioDraft,Preview,TerminalRequest,TerminalResult} from '../types/portfolioResearch';
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
import type { AdvisoryPaperBinding, AdvisoryRequest, AdvisorySelection } from '../types/advisory';
import { advisoryByteLimit, advisoryFingerprint, checkedAdvisoryResponse } from '../utils/advisory';
import type { MarketUniverseResponse } from '../types/marketUniverse';
import { checkedMarketUniverse, marketUniverseByteLimit, marketUniverseHttpStatus } from '../utils/marketUniverse';
import type { GeneralizedPaperResult, PaperAdmission, PaperBinding, PaperProposal } from '../types/generalizedPaper';
import { checkedPaperAdmission, checkedPaperResult, paperAdmissionHttpStatus, paperResponseByteLimit } from '../utils/generalizedPaper';
import type { FinancialEvidenceSelection } from '../types/marketRisk';
import { checkedFinancialEvidence } from '../utils/marketRisk';
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
    if (path.startsWith('/simulation/') || path.startsWith('/research-vault/')) {
      // Error bodies may come from a proxy or contain private worker details.
      // Classify by HTTP status without parsing or displaying untrusted text.
      const advice = r.status === 413
        ? 'Research payload exceeds its size limit. Reduce the request.'
        : r.status === 422
        ? 'Review the scenario, frame bounds and parameter grid; check Research Vault capital and accounting settings.'
        : r.status === 503
          ? 'Research service unavailable. Retry when coordination is restored.'
          : r.status >= 500
            ? 'Research failed on the server. Retry or inspect backend diagnostics.'
            : 'Retry the research request.';
      throw new Error(`Research request failed (HTTP ${r.status}). ${advice}`);
    }
    const body = await r.json().catch(() => null);
    const detail = body?.detail;
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
    for(;;){const {done,value}=await reader.read().catch(()=>{
        throw new Error('Historical backend connection interrupted. The admitted job may still be processing.');
      });if(done)break;
      size+=value.byteLength;
      if(size>limit)throw new Error('Historical response exceeds the browser evidence budget.');
      wire+=decoder.decode(value,{stream:true});
    }
    wire+=decoder.decode();
    return JSON.parse(wire) as unknown;
  }catch(error){
    await reader.cancel().catch(()=>{});
    if(error instanceof SyntaxError || error instanceof TypeError)throw new Error('Historical response is invalid or malformed.');
    throw error;
  }
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
async function portfolioRequest<T>(path:string,body:unknown,signal?:AbortSignal):Promise<T>{
  const response=await fetch(API+'/portfolio-research/'+path,{method:'POST',body:JSON.stringify(body),signal,cache:'no-store',headers:{'Content-Type':'application/json'}});
  if(!response.ok){
    if(response.status===422){
      const wire=await readHistoricalJson(response,4096).catch(()=>null) as {
        detail?:{code?:unknown;market?:unknown;side?:unknown;size_decimals?:unknown};
      }|null;
      const detail=wire?.detail;
      if(detail?.code==='LIQUIDITY_DEPTH_PRECISION' &&
        (detail.market==='BTC'||detail.market==='ETH'||detail.market==='SOL') &&
        (detail.side==='BID'||detail.side==='ASK') && typeof detail.size_decimals==='number' &&
        Number.isInteger(detail.size_decimals) && detail.size_decimals>=0 && detail.size_decimals<=6){
        const places=detail.size_decimals===1?'decimal place':'decimal places';
        throw new Error(`${detail.market} ${detail.side} stressed depth is below market size precision (${detail.size_decimals} ${places}). Increase the depth multiplier for this side.`);
      }
    }
    const guidance:Record<number,string>={429:'Shared research worker busy. Retry after its current job completes.',
      413:'Request or response exceeds the portfolio size limit. Reduce frames or selected markets.',
      422:'Configuration rejected. Check positive allocations, minimum reserve, risk limits, strategy feasibility and combined stress window/workload. Funding needs an observed accrual boundary; concentration needs complete pre-onset positions.',
      503:'Research admission unavailable. Check the local backend and coordination service.',500:'Portfolio research failed. Inspect local backend diagnostics and retry.'};
    throw new Error(`Portfolio request failed (HTTP ${response.status}). ${guidance[response.status]??'Local research API unavailable.'} Browser cancellation does not stop an admitted worker.`);
  }
  return await readHistoricalJson(response,200000) as T;
}
async function generalizedPaperRequest(
  proposal: PaperProposal, expected?: PaperBinding, signal?: AbortSignal,
): Promise<PaperAdmission | GeneralizedPaperResult> {
  const path = expected ? 'run' : 'eligibility';
  const response = await fetch(API + '/generalized-paper/' + path, {
    method: 'POST', cache: 'no-store', signal, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(expected ? { ...proposal, expected } : proposal),
  });
  if (![200, 409, 422, 503].includes(response.status)) {
    await response.body?.cancel().catch(() => {});
    throw new Error(response.status === 429 ? 'The shared PAPER worker is busy. Try again after the current run.' :
      response.status === 413 ? 'The PAPER request exceeds its size limit.' : 'The local PAPER request failed.');
  }
  const wire = await readHistoricalJson(response, paperResponseByteLimit);
  if (expected && response.ok) {
    const result = checkedPaperResult(wire, proposal, expected);
    const receipt = response.headers.get('X-Paper-Advisory-Receipt');
    return { ...result, advisory_receipt: advisoryFingerprint(receipt) ? receipt : undefined };
  }
  if (response.status === 503 && typeof wire === 'object' && wire !== null && 'detail' in wire) {
    throw new Error('The shared PAPER worker is unavailable.');
  }
  const admission = checkedPaperAdmission(wire, proposal);
  if (response.status !== paperAdmissionHttpStatus(admission)) throw new Error('PAPER decision disagrees with its HTTP status.');
  return admission;
}

export const api = {
  paperEligibility: async (proposal: PaperProposal, signal?: AbortSignal): Promise<PaperAdmission> => {
    const evidence = await generalizedPaperRequest(proposal, undefined, signal);
    if (!('status' in evidence)) throw new Error('PAPER eligibility evidence is missing.');
    return evidence;
  },
  runGeneralizedPaper: (proposal: PaperProposal, expected: PaperBinding, signal?: AbortSignal) =>
    generalizedPaperRequest(proposal, expected, signal),
  advisory: async (body: AdvisoryRequest, selection: AdvisorySelection, paper?: AdvisoryPaperBinding, signal?: AbortSignal) => {
    const response = await fetch(API + '/market-universe/advisory', {
      method: 'POST', cache: 'no-store', signal, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const evidence = await readHistoricalJson(response, advisoryByteLimit);
    if (!response.ok) {
      const code = (evidence as { detail?: { code?: unknown } } | null)?.detail?.code;
      const guidance: Record<string, string> = {
        WRONG_NETWORK: 'This market belongs to a different discovery network.',
        WRONG_DEX: 'The DEX namespace is unavailable in this catalog.',
        UNKNOWN_MARKET: 'The selected market is unavailable in this catalog.',
        CATALOG_UNAVAILABLE: 'Current discovery metadata is unavailable.',
        CATALOG_STALE: 'Discovery changed or expired. Refresh discovery and select the market again.',
        PAPER_BINDING_MISMATCH: 'The retained PAPER run belongs to a different market.',
        RESEARCH_WORKER_UNAVAILABLE: 'Advisory research is busy or unavailable. Try again.',
        EVIDENCE_EXPIRED: 'Advisory evidence expired during evaluation. Try again.',
        EVIDENCE_BINDING_FAILURE: 'Advisory evidence failed its server binding checks.',
      };
      throw new Error(typeof code === 'string' && Object.hasOwn(guidance, code) ? guidance[code] :
        'The advisory request could not be evaluated. Check the selected research inputs.');
    }
    return checkedAdvisoryResponse(evidence, body, selection, paper);
  },
  marketRiskEvidence: async (selection: FinancialEvidenceSelection, signal?: AbortSignal) => {
    const { network, instrument_type, dex, instrument_name } = selection.metadata.identity;
    const query = new URLSearchParams({ network, instrument_type, dex, instrument_name,
      catalog_fingerprint: selection.catalog_fingerprint });
    const response = await fetch(API + '/market-universe/risk-evidence?' + query, { cache: 'no-store', signal });
    if (!response.ok) {
      await response.body?.cancel().catch(() => {});
      throw new Error(response.status === 409
        ? 'The discovery generation changed. Refresh discovery to inspect current financial evidence.'
        : 'Public collateral and margin evidence is unavailable.');
    }
    return checkedFinancialEvidence(await readHistoricalJson(response, 16_384), selection);
  },
  portfolioPreview:(body:PortfolioDraft,signal?:AbortSignal)=>portfolioRequest<Preview>('preview',body,signal),
  portfolioTerminal:(body:TerminalRequest,signal?:AbortSignal)=>portfolioRequest<TerminalResult>('terminal',body,signal),
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
  marketUniverse: async (signal?: AbortSignal): Promise<MarketUniverseResponse> => {
    const response = await fetch(API + '/market-universe', {method: 'GET', signal, cache: 'no-store'});
    if (![200, 429, 503, 504].includes(response.status)) {
      await response.body?.cancel().catch(() => {});
      throw new Error('Market universe endpoint returned an unexpected status.');
    }
    const wire = await readHistoricalJson(response, marketUniverseByteLimit).catch(() => {
      throw new Error('Market universe response could not be read within its evidence budget.');
    });
    const result = checkedMarketUniverse(wire);
    if (response.status !== marketUniverseHttpStatus(result)) {
      throw new Error('Market universe response disagrees with its HTTP status.');
    }
    return result;
  },
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
