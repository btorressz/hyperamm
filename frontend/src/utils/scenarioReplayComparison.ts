import type {
  ComparisonChartEvidence, ComparisonDimension, ComparisonMetricName, MetricOrigin,
  MetricUnit, QuantitativeComparisonReceipt, QuantitativeMetricRow,
} from '../types/scenarioReplayComparison';
import { exactDecimal } from './orderView';
import { receiptTime } from './replayEvidence';

const SHA = /^[a-f0-9]{64}$/;
// Pydantic Decimal emits canonical uppercase exponents (including 0E+5).
// Retain the exact wire string; bounded text expansion is display-only.
const DECIMAL = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:E[+-]\d{1,3})?$/;
const MARKETS = ['BTC','ETH','SOL'];
const DIMENSIONS: ComparisonDimension[] = [
  'MARKET','ENGINE','STRATEGY','AGENTS','RISK','ACCOUNTING',
  'EXECUTION','MARKET_PROFILE','SIMULATION_CONTROLS',
];
export const COMPARISON_METRICS: ReadonlyArray<readonly [ComparisonMetricName, MetricUnit, MetricOrigin]> = [
  ['frame_count','frames','SIMULATION_METRICS'],
  ['starting_equity','quote','SIMULATION_METRICS'],
  ['ending_equity','quote','SIMULATION_METRICS'],
  ['session_pnl','quote','SIMULATION_METRICS'],
  ['return_pct','percent','SIMULATION_METRICS'],
  ['realized_pnl','quote','SIMULATION_METRICS'],
  ['unrealized_pnl','quote','SIMULATION_METRICS'],
  ['max_drawdown_pct','percent','SIMULATION_METRICS'],
  ['fill_count','fills','SIMULATION_METRICS'],
  ['buy_fill_count','fills','SIMULATION_METRICS'],
  ['sell_fill_count','fills','SIMULATION_METRICS'],
  ['quoted_notional','quote','SIMULATION_METRICS'],
  ['filled_notional','quote','SIMULATION_METRICS'],
  ['fill_activity_ratio','ratio','SIMULATION_METRICS'],
  ['ending_inventory_base','base','SIMULATION_METRICS'],
  ['max_abs_inventory_base','base','SIMULATION_METRICS'],
  ['max_inventory_utilization','ratio','SIMULATION_METRICS'],
  ['risk_halt_fraction','ratio','SIMULATION_METRICS'],
  ['fees_quote','quote','PAPER_VAULT'],
  ['funding_quote','quote','PAPER_VAULT'],
  ['capital_utilization','ratio','PAPER_VAULT'],
  ['reserved_capital_quote','quote','PAPER_VAULT'],
  ['gross_exposure_quote','quote','PAPER_VAULT'],
] as const;
const COUNT = new Set<ComparisonMetricName>([
  'frame_count','fill_count','buy_fill_count','sell_fill_count',
]);
const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const hash = (v: unknown): v is string => typeof v === 'string' && SHA.test(v);
const safeInt = (v: unknown, min: number, max: number): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v >= min && v <= max;
const text = (v: unknown, max = 500): v is string => typeof v === 'string' && v.length <= max;
const timestamp = (v: unknown): v is string => text(v,70) &&
  /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const textArray = (v: unknown, max = 100): v is string[] =>
  Array.isArray(v) && v.length <= max && v.every(x => text(x, 500));
const assert: (p: unknown, message: string) => asserts p = (p, message) => {
  if (!p) throw new Error('Comparison receipt rejected: ' + message);
};

function side(v: unknown, kind: 'SCENARIO' | 'HISTORICAL_SEGMENT'): asserts v {
  assert(isObject(v) && v.kind === kind && MARKETS.includes(String(v.market)) &&
    hash(v.original_dataset_fingerprint) && hash(v.engine_dataset_fingerprint) &&
    hash(v.simulation_result_fingerprint) && hash(v.run_fingerprint) &&
    text(v.engine_version, 96) && (v.engine_version as string).length > 0 &&
    safeInt(v.frame_count, 2, 5000) && isObject(v.captured), 'invalid scenario/replay evidence side');
  const c = v.captured as Record<string, unknown>;
  assert(['fingerprint','strategy_fingerprint','agents_fingerprint','risk_fingerprint',
    'accounting_fingerprint','execution_fingerprint','simulation_controls_fingerprint']
    .every(k => hash(c[k])) && (c.market_profile_fingerprint === null || hash(c.market_profile_fingerprint)) &&
    text(c.canonical_json, 160000), 'invalid captured configuration identity');
  assert(v.authority === 'NONE' && v.read_only === true && v.simulated === true &&
    v.source_authenticated === false && v.licensing_independently_verified === false,
    'unsupported source trust or execution authority');
  if (kind === 'SCENARIO') {
    assert(v.source_kind === 'DETERMINISTIC_SCENARIO' && v.segment_index === null &&
      v.replay_result_fingerprint === null && v.replay_segment_count === null &&
      v.original_dataset_fingerprint === v.engine_dataset_fingerprint &&
      ['TRACE_COMPLETE','UNKNOWN'].includes(String(v.window_status)), 'scenario identity');
  } else {
    assert(['RECORDED_NATIVE','SYNTHETIC_FIXTURE'].includes(String(v.source_kind)) &&
      safeInt(v.segment_index,0,31) && safeInt(v.replay_segment_count,1,32) &&
      (v.segment_index as number) < (v.replay_segment_count as number) &&
      hash(v.replay_result_fingerprint) && v.window_status === 'SEGMENT_RECEIPTS',
      'historical segment identity');
  }
  assert((v.window_start === null && v.window_end === null) ||
    (text(v.window_start,70) && text(v.window_end,70) &&
      Number.isFinite(Date.parse(String(v.window_start))) &&
      Number.isFinite(Date.parse(String(v.window_end))) &&
      receiptTime(String(v.window_end)) > receiptTime(String(v.window_start))),
    'incomplete time coverage');
}

function observation(raw: unknown, origin: MetricOrigin, count: boolean): void {
  assert(isObject(raw) && raw.origin === origin &&
    ['AVAILABLE','NOT_REPORTED'].includes(String(raw.availability)), 'metric origin/status');
  if (raw.availability === 'NOT_REPORTED') {
    assert(raw.value === null, 'missing value must remain null');
  } else {
    assert(typeof raw.value === 'string' && raw.value.length <= 120 &&
      DECIMAL.test(raw.value), 'financial values must remain exact decimal strings');
    if (count) assert(/^\d+$/.test(raw.value), 'counts must be non-negative integers');
  }
}
function validateRows(rows: unknown): asserts rows is QuantitativeMetricRow[] {
  assert(Array.isArray(rows) && rows.length === COMPARISON_METRICS.length,'incomplete metric registry');
  rows.forEach((raw, i) => {
    const [name,unit,origin] = COMPARISON_METRICS[i];
    assert(isObject(raw) && raw.name === name && raw.unit === unit,'mismatched metric field/unit');
    observation(raw.scenario,origin,COUNT.has(name));
    observation(raw.historical_segment,origin,COUNT.has(name));
  });
}
function counts(v: unknown, expected: string): void {
  assert(isObject(v) && Object.keys(v).length <= 20,'invalid risk states');
  let sum=0;
  for(const [key,num] of Object.entries(v)) {
    assert(key.length > 0 && key.length <= 80 && safeInt(num,0,5000),'invalid risk count');
    sum+=num as number;
  }
  assert(sum === Number(expected),'risk counts do not cover simulated frames');
}

/** Only display structure is checked. SHA-256 identities require authoritative server validation. */
export function checkedQuantitativeReceipt(raw: unknown): QuantitativeComparisonReceipt {
  assert(isObject(raw) && raw.version === 'phase165b-v1' &&
    hash(raw.receipt_fingerprint) && hash(raw.scenario_receipt_fingerprint) &&
    raw.authority === 'NONE' && raw.read_only === true &&
    raw.differences_available === false && raw.strategy_ranking_allowed === false &&
    raw.cross_segment_aggregation_allowed === false &&
    raw.matched_market_evidence_verified === false &&
    textArray(raw.limitations,30) && raw.limitations.length > 0 &&
    isObject(raw.foundation), 'unsupported comparison receipt version or authority');
  const f=raw.foundation as Record<string,unknown>;
  assert(f.version === 'phase165a1-v1' && hash(f.comparison_fingerprint) &&
    f.authority === 'NONE' && f.direct_metric_deltas_allowed === false &&
    f.cross_segment_aggregation_allowed === false &&
    f.matched_market_evidence_verified === false &&
    textArray(f.reasons,40) && f.reasons.length > 0 &&
    textArray(f.limitations,30) && f.limitations.length > 0 &&
    f.classification !== 'ALIGNED', 'unsupported comparability claims');
  side(f.scenario,'SCENARIO');
  side(f.historical,'HISTORICAL_SEGMENT');
  const s=f.scenario as Record<string,unknown>, h=f.historical as Record<string,unknown>;
  const mismatch=s.market!==h.market || s.engine_version!==h.engine_version;
  assert(f.classification === (mismatch?'INCOMPARABLE':'CONTEXT_ONLY'),
    'classification must agree with hard market/engine mismatches');
  const differences=f.differing_dimensions, aligned=f.aligned_dimensions;
  assert(textArray(differences,9) && textArray(aligned,9) &&
    [...differences,...aligned].length === DIMENSIONS.length &&
    new Set([...differences,...aligned]).size === DIMENSIONS.length &&
    DIMENSIONS.every(x=>[...differences,...aligned].includes(x)),
    'invalid captured configuration dimensions');
  assert(s.source_kind === 'DETERMINISTIC_SCENARIO' &&
    h.source_kind !== 'DETERMINISTIC_SCENARIO' &&
    safeInt(raw.selected_segment_index,0,31) &&
    raw.selected_segment_index === h.segment_index,'selected historical segment mismatch');
  if (f.classification === 'INCOMPARABLE') {
    assert(raw.display_policy === 'BLOCKED' && Array.isArray(raw.rows) && raw.rows.length===0 &&
      raw.risk_states===null,'incomparable evidence must block metric display');
  } else {
    assert(raw.display_policy === 'DESCRIPTIVE_ONLY','unsupported paired comparison policy');
    validateRows(raw.rows);
    const row = (raw.rows as QuantitativeMetricRow[])[0];
    assert(isObject(raw.risk_states),'missing risk state evidence');
    const risk = raw.risk_states as Record<string,unknown>;
    const scenarioFrames=row.scenario.value;
    const historicalFrames=row.historical_segment.value;
    assert(scenarioFrames!==null && historicalFrames!==null &&
      Number(scenarioFrames) === s.frame_count &&
      Number(historicalFrames) === h.frame_count,
      'metric frame-count identity mismatch');
    counts(risk.scenario,scenarioFrames);
    counts(risk.historical_segment,historicalFrames);
  }
  return raw as unknown as QuantitativeComparisonReceipt;
}
export function parseComparisonReceipt(json: string): QuantitativeComparisonReceipt {
  if (new TextEncoder().encode(json).byteLength > 256_000) {
    throw new Error('Comparison receipt exceeds 256 KB. Use a bounded Phase 16.5B receipt.');
  }
  let value: unknown;
  try { value = JSON.parse(json); } catch { throw new Error('Comparison receipt is not valid JSON.'); }
  return checkedQuantitativeReceipt(value);
}
/** Truncate for display only, never change the authoritative receipt value. */
export function metricText(value: string|null, maxFraction=6): string {
  if (value===null) return 'Unavailable';
  const plain=exactDecimal(value).replace(/^(-?)0+(?=\d)/,'$1');
  const [whole,fraction] = plain.split('.');
  return fraction && fraction.length > maxFraction
    ? whole+'.'+fraction.slice(0,maxFraction)+'…' : plain;
}
export function attachedTraceMatches(receipt: QuantitativeComparisonReceipt,
  evidence: ComparisonChartEvidence): boolean {
  const scenario = evidence.scenario, historical = evidence.historical;
  const segment = historical.segments[receipt.selected_segment_index];
  if (!segment || receipt.foundation.classification !== 'CONTEXT_ONLY') return false;
  const a=receipt.foundation.scenario, b=receipt.foundation.historical;
  return scenario.simulated===true && scenario.run_fingerprint===a.run_fingerprint &&
    scenario.dataset_fingerprint===a.engine_dataset_fingerprint &&
    scenario.engine_version===a.engine_version &&
    historical.result_fingerprint===b.replay_result_fingerprint &&
    historical.request.dataset_fingerprint===b.original_dataset_fingerprint &&
    segment.run_fingerprint===b.run_fingerprint &&
    segment.dataset_fingerprint===b.engine_dataset_fingerprint &&
    segment.simulation_result_fingerprint===b.simulation_result_fingerprint;
}

/** Bind display evidence to the captured HTTP request; hashes are checked by the server. */
export function checkedComparisonResponse(raw:unknown, request:import('../types/scenarioReplayComparison').ScenarioHistoricalRequest):import('../types/scenarioReplayComparison').ScenarioHistoricalResponse {
  assert(isObject(raw)&&raw.version==='phase165c2-v1'&&raw.authority==='NONE'&&raw.read_only===true&&
    hash(raw.request_fingerprint)&&raw.selection_policy==='RERUN_SELECTED_SEGMENT','comparison transport');
  const receipt=checkedQuantitativeReceipt(raw.receipt), f=receipt.foundation;
  assert(isObject(raw.request),'captured request unavailable');
  // Server may fill defaults; compare every field supplied by this browser.
  const contains=(actual:unknown,expected:unknown):boolean=>{
    if(isObject(expected))return isObject(actual)&&Object.entries(expected).every(([k,v])=>contains(actual[k],v));
    return actual===expected;
  };
  assert(contains(raw.request,request),'stale captured request');
  assert(f.scenario.market===request.research_market&&f.historical.market===request.historical.market&&
    f.scenario.frame_count===request.frames&&
    f.historical.original_dataset_fingerprint===request.historical.dataset_fingerprint&&
    receipt.selected_segment_index===request.segment_index,'request/source identity');
  assert(safeInt(raw.segment_count,1,32)&&Array.isArray(raw.segments)&&raw.segments.length===raw.segment_count&&
    f.historical.replay_segment_count===raw.segment_count,'segment selection metadata');
  raw.segments.forEach((s,i)=>assert(isObject(s)&&s.segment_index===i&&safeInt(s.frame_count,2,5000)&&
    hash(s.dataset_fingerprint)&&hash(s.run_fingerprint)&&hash(s.simulation_result_fingerprint)&&
    ['WINDOW_START','DECLARED_GAP','OBSERVER_CHANGE','RECEIPT_INTERVAL','UNAVAILABLE_FRAME'].includes(String(s.reset_reason))&&
    timestamp(s.window_start)&&timestamp(s.window_end)&&receiptTime(s.window_end)>receiptTime(s.window_start),'segment identity'));
  const selected=raw.segments[request.segment_index] as Record<string,unknown>;
  assert(selected&&selected.run_fingerprint===f.historical.run_fingerprint&&
    selected.dataset_fingerprint===f.historical.engine_dataset_fingerprint&&
    selected.simulation_result_fingerprint===f.historical.simulation_result_fingerprint&&
    selected.frame_count===f.historical.frame_count&&
    receiptTime(String(selected.window_start))===receiptTime(f.historical.window_start!)&&
    receiptTime(String(selected.window_end))===receiptTime(f.historical.window_end!),'selected archive');
  assert(isObject(raw.provenance)&&raw.provenance.dataset_fingerprint===request.historical.dataset_fingerprint&&
    raw.provenance.source_authenticated===false&&raw.provenance.licensing_independently_verified===false&&
    raw.provenance.source_kind===f.historical.source_kind&&
    Array.isArray(raw.declared_gaps)&&raw.declared_gaps.length<=1024&&
    Array.isArray(raw.issues)&&raw.issues.length<=100&&safeInt(raw.omitted_issues,0,5000),'source limitations');
  for(const [key,side] of [['scenario_trace',f.scenario],['historical_trace',f.historical]] as const){
    const t=raw[key];
    assert(isObject(t)&&t.run_fingerprint===side.run_fingerprint&&t.dataset_fingerprint===side.engine_dataset_fingerprint&&
      t.simulation_result_fingerprint===side.simulation_result_fingerprint&&t.frame_count===side.frame_count&&
      Array.isArray(t.points)&&t.points.length<=Math.min(250,request.trace_point_limit)&&
      safeInt(t.omitted_points,0,5000)&&t.points.length+t.omitted_points===t.frame_count&&
      ['NONE','NOT_REQUESTED','TRACE_UNAVAILABLE','POINT_LIMIT','INCOMPARABLE'].includes(String(t.omission))&&
      Array.isArray(t.source_times)&&t.source_times.length<=250,'bounded trace evidence');
    assert((receipt.display_policy!=='BLOCKED'&&request.include_traces)||t.points.length===0,'blocked traces');
    let previous=-1, previousTime='';
    for(const p of t.points){
      assert(isObject(p)&&safeInt(p.sequence,0,Number.MAX_SAFE_INTEGER)&&p.sequence>previous&&text(p.timestamp,70)&&
        Number.isFinite(Date.parse(p.timestamp))&&(!previousTime||receiptTime(p.timestamp)>receiptTime(previousTime)),'ordered original trace');
      for(const field of ['equity','session_pnl','inventory_base','drawdown_pct','mid','mark','oracle'])
        assert(typeof p[field]==='string'&&p[field].length<=120&&DECIMAL.test(p[field]),'exact trace values');
      for(const field of ['risk_state','agent_regime','toxic_flow_state','execution_quality_state','reference_confidence'])
        assert(text(p[field],80),'trace state');
      previous=p.sequence;previousTime=p.timestamp;
    }
    assert(t.source_times.length===(key==='historical_trace'?t.points.length:0),'original source time coverage');
    t.source_times.forEach((v,i)=>assert(isObject(v)&&v.sequence===(t.points as Record<string,unknown>[])[i].sequence&&
      timestamp(v.book_received_at)&&timestamp(v.context_received_at)&&
      (v.book_source_timestamp===null||timestamp(v.book_source_timestamp))&&
      (v.context_source_timestamp===null||timestamp(v.context_source_timestamp))&&
      (receiptTime(v.book_received_at)>receiptTime(v.context_received_at)
        ?receiptTime(v.book_received_at):receiptTime(v.context_received_at))===
        receiptTime(String((t.points as Record<string,unknown>[])[i].timestamp))&&
      typeof v.book_source_event_time_verified==='boolean'&&typeof v.context_source_event_time_verified==='boolean','source times'));
  }
  return raw as unknown as import('../types/scenarioReplayComparison').ScenarioHistoricalResponse;
}
