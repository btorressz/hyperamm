import type {SimulationResult, ResearchEvidenceSummary, MarketResearchComparisonRequest, MarketResearchComparisonResult, LiveMarketId, ComparisonMetricName, ResearchMarketAssumptions} from '../types';
import {checkedLiveSnapshot, liveTimestamp, liveMarketIds} from './liveMarketEvidence';
import {isResearchConfig, shiftDecimal} from './researchVault';

export const comparisonMetricNames: ComparisonMetricName[] = ['midpoint','best_bid','best_ask','mark_price','oracle_price','spread_quote','spread_bps','funding_rate','bid_depth_base','ask_depth_base','open_interest_base'];
const metricFields = ['frame_count','session_pnl','return_pct','realized_pnl','unrealized_pnl','max_drawdown_pct','fill_count','quoted_notional','filled_notional','fill_activity_ratio','mean_spread_capture_bps','mean_mature_markout_bps','adverse_fill_rate','ending_inventory_base','max_inventory_utilization','risk_halt_fraction','risk_state_counts'] as const;
const nullablePerformance = new Set(['fill_activity_ratio','mean_spread_capture_bps','mean_mature_markout_bps','adverse_fill_rate','fees_quote','funding_quote']);
const statuses = ['COMPARABLE','PARTIAL','NOT_COMPARABLE','UNAVAILABLE'];
const fingerprint = (x:unknown) => typeof x==='string' && /^[a-f0-9]{64}$/.test(x);
const int = (x:unknown,min=0,max=5000) => typeof x==='number' && Number.isSafeInteger(x) && x>=min && x<=max;
function requireThat(value:unknown): asserts value {if(!value)throw new Error('Malformed market/research evidence; comparison remains unavailable.');}
function textList(x:unknown) {return Array.isArray(x) && x.length<=100 && x.every(v=>typeof v==='string' && v.length<=2000);}
export function financialString(x:unknown, nullable=false): boolean {
  if(nullable && x===null)return true;
  return typeof x==='string' && x.length<=128 && /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d{1,3})?$/.test(x) && Number.isFinite(Number(x)) && Math.abs(Number(x))<=1e30;
}
// Simulation's legacy serializer may return exponent notation. Convert text only,
// with bounded shifts; authoritative values never pass through binary arithmetic.
export function plainFinancial(x:unknown): string | null {
  if(x===null)return null;
  requireThat(financialString(x));
  const [mantissa,exponent]=String(x).split(/[eE]/);
  return (exponent===undefined ? mantissa : shiftDecimal(mantissa,Number(exponent))).replace(/^(-?)0+(?=\d)/,'$1');
}
export function checkedAssumptions(a:ResearchMarketAssumptions, r:ResearchEvidenceSummary) {
  requireThat(a.contract_version==='phase154-v1' && a.simulated===true && a.market===r.research_market
    && a.scenario===r.scenario && a.dataset_fingerprint===r.dataset_fingerprint
    && a.market_profile_fingerprint===r.market_profile_fingerprint && a.market_profile_version===r.market_profile_version
    && a.frame_count===r.performance.frame_count && a.representative_frame==='LAST_CONSUMED_DATASET_FRAME'
    && int(a.representative_frame_sequence,0,100000000) && liveTimestamp(a.representative_frame_timestamp)
    && fingerprint(a.assumption_fingerprint) && a.depth_measurement_method==='TOP_5_LEVELS_PER_SIDE_BASE'
    && a.funding_convention==='RAW_RATE_PER_SAMPLED_RESEARCH_INTERVAL' && int(a.depth_level_count,1,5)
    && typeof a.reference_source==='string' && a.reference_source.length<=200 && textList(a.limitations));
  for(const k of ['midpoint','best_bid','best_ask','spread_quote','spread_bps','mark_price','oracle_price','funding_rate','bid_depth_base','ask_depth_base','open_interest_base'] as const)
    requireThat(financialString(a[k],k==='open_interest_base'));
  requireThat(Number(a.best_bid)>0 && Number(a.best_bid)<Number(a.best_ask) && Number(a.mark_price)>0 && Number(a.oracle_price)>0);
  for(const [side,levels] of [['bid',a.bid_levels],['ask',a.ask_levels]] as const) {
    requireThat(Array.isArray(levels) && levels.length>=1 && levels.length<=5);
    levels.forEach((l,i)=>requireThat(financialString(l.price) && Number(l.price)>0 && financialString(l.size) && Number(l.size)>=0
      && (!i || (side==='bid'?Number(levels[i-1].price)>=Number(l.price):Number(levels[i-1].price)<=Number(l.price)))));
  }
  requireThat(a.bid_levels[0].price===a.best_bid && a.ask_levels[0].price===a.best_ask);
  return a;
}
export function checkedResearchSummary(r:ResearchEvidenceSummary): ResearchEvidenceSummary {
  requireThat(r && r.simulated===true && liveMarketIds.includes(r.research_market) && fingerprint(r.run_fingerprint)
    && fingerprint(r.dataset_fingerprint) && fingerprint(r.strategy_fingerprint) && typeof r.engine_version==='string'
    && /^[A-Z_]{1,64}$/.test(r.scenario) && r.performance && int(r.performance.frame_count,2)
    && int(r.performance.fill_count,0,1000000));
  requireThat(/^[a-zA-Z0-9._-]{1,64}$/.test(r.engine_version) && metricFields.every(k=>k in r.performance));
  requireThat(r.market_profile_fingerprint===null || fingerprint(r.market_profile_fingerprint));
  requireThat((r.market_profile_version===null && r.market_profile_fingerprint===null) || r.market_profile_version==='phase146-v1' && fingerprint(r.market_profile_fingerprint));
  requireThat((r.metadata_status===null && r.metadata_source===null) || (r.metadata_status==='DEMO_PROFILE' && r.metadata_source==='PINNED_RESEARCH_FIXTURE') || (r.metadata_status==='EXCHANGE_VERIFIED' && r.metadata_source==='OFFICIAL_SDK_NATIVE_META'));
  for(const [k,v] of Object.entries(r.performance)) {
    if(k==='frame_count'||k==='fill_count'||k==='risk_state_counts')continue;
    requireThat(financialString(v,nullablePerformance.has(k)));
  }
  const counts=r.performance.risk_state_counts;
  requireThat(counts && Object.keys(counts).length<=4 && Object.entries(counts).every(([k,v])=>['NORMAL','WIDEN','REDUCE','HALT'].includes(k)&&int(v))
    && Object.values(counts).reduce((sum,n)=>sum+n,0)===r.performance.frame_count);
  if(r.assumptions!==null)checkedAssumptions(r.assumptions,r);
  const c=r.research_configuration;
  if(c!==null)requireThat(c.research_config_version==='phase14-v1' && isResearchConfig(c.normalized_config) && fingerprint(c.config_fingerprint));
  requireThat(JSON.stringify(r).length<=60000);
  return r;
}
export function researchSummary(result:SimulationResult): ResearchEvidenceSummary {
  requireThat(result && result.simulated===true && result.metrics && Array.isArray(result.trace));
  const performance=Object.fromEntries(metricFields.map(k=>[k,result.metrics[k]]));
  for(const k of metricFields)if(!['frame_count','fill_count','risk_state_counts'].includes(k))performance[k]=plainFinancial(performance[k]);
  performance.fees_quote=plainFinancial(result.vault?.fees_quote ?? null);
  performance.funding_quote=plainFinancial(result.vault?.funding_quote ?? null);
  const r={engine_version:result.engine_version, research_market:result.research_market,
    market_profile_version:result.market_profile_version??null,market_profile_fingerprint:result.market_profile_fingerprint??null,
    metadata_source:result.metadata_source??null,metadata_status:result.metadata_status??null,run_fingerprint:result.run_fingerprint,
    dataset_fingerprint:result.dataset_fingerprint,strategy_fingerprint:result.strategy_fingerprint,scenario:result.scenario,
    simulated:true, assumptions:result.research_assumptions??null,performance,research_configuration:result.research_configuration??null} as ResearchEvidenceSummary;
  return checkedResearchSummary(structuredClone(r));
}
export type ComparisonBoundary = {market:LiveMarketId; liveSelection:number; liveBoundary:number; observer:string|null; generation:number|null;
  researchRun:string; researchDataset:string; researchProfile:string|null; researchVersion:number; researchEpoch:number; requestGeneration:number};
export function sameBoundary(a:ComparisonBoundary,b:ComparisonBoundary) {
  return (Object.keys(a) as Array<keyof ComparisonBoundary>).every(k=>a[k]===b[k]);
}
// Own cancellation independently of React render/effect timing. A retired ticket
// can never become current again, even if every selected identity changes back.
export class ComparisonRequestGate {
  private generation=0;
  private controller:AbortController|null=null;
  retire() {++this.generation;this.controller?.abort();}
  begin() {
    this.retire();this.controller=new AbortController();
    return {generation:this.generation,signal:this.controller.signal};
  }
  accepts(ticket:{generation:number;signal:AbortSignal},captured:ComparisonBoundary,current:ComparisonBoundary|null) {
    return !ticket.signal.aborted && ticket.generation===this.generation && !!current && sameBoundary(captured,current);
  }
}

export function capturedEvidenceLabel(data:MarketResearchComparisonResult, component:'book'|'context', historicalReason:string|null=null) {
  const observed=data.observed,s=observed.snapshot;
  if(!(component==='book'?s.order_book:s.perp_context))return 'UNAVAILABLE';
  if(historicalReason)return 'HISTORICAL';
  if(s.status[component==='book'?'l2_freshness':'perp_freshness']==='STALE' || s.status.metadata_freshness==='STALE')return 'STALE';
  return (component==='book'?observed.book_eligible:observed.context_eligible)?'CURRENT / ELIGIBLE AT CAPTURE':'HISTORICAL / INELIGIBLE';
}
export function checkedMarketComparison(v:MarketResearchComparisonResult, req:MarketResearchComparisonRequest, boundary:ComparisonBoundary): MarketResearchComparisonResult {
  requireThat(v && v.contract_version==='phase154-v1' && v.read_only===true && v.market===req.market
    && liveTimestamp(v.generated_at) && statuses.includes(v.comparison_status) && v.research);
  checkedResearchSummary(v.research);
  requireThat(JSON.stringify(v.research)===JSON.stringify(req.research));
  const s=checkedLiveSnapshot(v.observed?.snapshot,req.market);
  requireThat(v.provenance && fingerprint(v.provenance.comparison_fingerprint)
    && v.provenance.research_trust==='STRUCTURALLY_VALIDATED_CLIENT_SUPPLIED_NOT_AUTHENTICATED'
    && v.provenance.observer_instance_id===s.status.observer_instance_id && v.provenance.connection_generation===s.status.connection_generation
    && (boundary.observer===null || boundary.observer===v.provenance.observer_instance_id)
    && (boundary.generation===null || boundary.generation===v.provenance.connection_generation)
    && v.provenance.perp_event_time==='UNKNOWN'
    && v.provenance.l2_source_timestamp===(s.order_book?.source_timestamp??null)
    && v.provenance.l2_observed_at===(s.order_book?.observed_at??null)
    && v.provenance.perp_observed_at===(s.perp_context?.observed_at??null)
    && v.provenance.research_frame_timestamp===(v.research.assumptions?.representative_frame_timestamp??null));
  requireThat(typeof v.observed.book_eligible==='boolean' && typeof v.observed.context_eligible==='boolean'
    && int(v.observed.depth_level_count,0,5) && v.observed.depth_measurement_method==='TOP_5_LEVELS_PER_SIDE_BASE'
    && v.observed.funding_convention==='NATIVE_RAW_HOURLY_RATE_EVENT_TIME_UNKNOWN'
    && financialString(v.observed.bid_depth_base,true) && financialString(v.observed.ask_depth_base,true)
    && (v.observed.acquisition_gap_seconds===null || Number.isFinite(v.observed.acquisition_gap_seconds)&&v.observed.acquisition_gap_seconds>=0));
  requireThat(Array.isArray(v.metrics) && v.metrics.length===comparisonMetricNames.length);
  const found=new Set<string>();
  const status=s.status;
  const metadata=['BOOTSTRAPPING','CONNECTED','DEGRADED','STALE'].includes(status.connection_state)
    && status.metadata_freshness==='FRESH' && s.metadata.metadata_status==='EXCHANGE_VERIFIED';
  requireThat(v.observed.book_eligible===!!(metadata && s.order_book && status.l2_freshness==='FRESH')
    && v.observed.context_eligible===!!(metadata && s.perp_context && status.perp_freshness==='FRESH'));
  const bookMetrics=new Set(['midpoint','best_bid','best_ask','spread_quote','spread_bps','bid_depth_base','ask_depth_base']);
  const b=s.order_book,p=s.perp_context;
  const expectedObserved={midpoint:b?.midpoint??null,best_bid:b?.best_bid??null,best_ask:b?.best_ask??null,
    mark_price:p?.mark_price??null,oracle_price:p?.oracle_price??null,spread_quote:b?.spread??null,spread_bps:b?.spread_bps??null,
    funding_rate:p?.funding_rate??null,open_interest_base:p?.open_interest_base??null,
    bid_depth_base:v.observed.bid_depth_base,ask_depth_base:v.observed.ask_depth_base};
  const canonical=(value:string|null)=>value===null?null:plainFinancial(value)!.replace(/(\.\d*?)0+$/,'$1').replace(/\.$/,'').replace(/^-0$/,'0');
  for(const m of v.metrics) {
    requireThat(comparisonMetricNames.includes(m.metric_name) && !found.has(m.metric_name) && statuses.includes(m.comparison_status)
      && typeof m.reason==='string' && m.reason.length<=500 && ['quote/base','quote','bps','raw rate','base'].includes(m.unit));
    found.add(m.metric_name);
    for(const value of [m.observed_value,m.research_assumed_value])requireThat(financialString(value,true));
    // Relative output differences can legitimately exceed the bounded input range.
    for(const value of [m.absolute_difference,m.difference_bps])requireThat(value===null || typeof value==='string' && value.length<=256 && /^-?\d+(?:\.\d+)?$/.test(value) && Number.isFinite(Number(value)));
    requireThat(canonical(m.observed_value)===canonical(expectedObserved[m.metric_name])
      && canonical(m.research_assumed_value)===canonical(v.research.assumptions?.[m.metric_name]??null));
    const comparable=['COMPARABLE','PARTIAL'].includes(m.comparison_status);
    requireThat(comparable ? m.observed_value!==null && m.research_assumed_value!==null && m.absolute_difference!==null : m.absolute_difference===null && m.difference_bps===null);
    if(req.market!==req.research.research_market)requireThat(m.comparison_status==='NOT_COMPARABLE');
    if(!req.research.assumptions || (bookMetrics.has(m.metric_name)?!v.observed.book_eligible:!v.observed.context_eligible))requireThat(!comparable);
    if(m.metric_name.includes('depth') && (v.observed.depth_level_count!==5 || req.research.assumptions?.depth_level_count!==5
      || new Set(req.research.assumptions?.bid_levels.map(x=>x.price)).size!==5
      || new Set(req.research.assumptions?.ask_levels.map(x=>x.price)).size!==5))requireThat(!comparable);
    if(comparable && ['funding_rate','open_interest_base'].includes(m.metric_name))requireThat(m.comparison_status==='PARTIAL');
  }
  const e=v.explainability;
  requireThat(e && e.interpretation==='CROSS_CONTEXT_DESCRIPTIVE_ONLY' && ['COMPLETE_FOR_SUPPORTED_METRICS','PARTIAL','INSUFFICIENT','UNAVAILABLE'].includes(e.completeness)
    && textList(e.available_metrics) && textList(e.missing_metrics) && textList(e.statements) && textList(v.limitations));
  requireThat(e.available_metrics.length+e.missing_metrics.length===comparisonMetricNames.length && new Set([...e.available_metrics,...e.missing_metrics]).size===comparisonMetricNames.length);
  requireThat(v.metrics.every(m=>(['COMPARABLE','PARTIAL'].includes(m.comparison_status)?e.available_metrics:e.missing_metrics).includes(m.metric_name)));
  return v;
}
export function pairedPriceEvidence(r:MarketResearchComparisonResult,historicalReason:string|null=null) {
  const m=r.metrics.find(x=>x.metric_name==='midpoint');
  return {observed:{value:m?.observed_value??null,time:r.provenance.l2_source_timestamp,label:`${capturedEvidenceLabel(r,'book',historicalReason)} · Observed native L2 exchange time`},
    research:{value:m?.research_assumed_value??null,time:r.provenance.research_frame_timestamp,label:'Hypothetical last dataset frame time'}};
}

export function comparisonTimestamp(value:string|null) {
  return value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'long'}) : 'Unavailable';
}
