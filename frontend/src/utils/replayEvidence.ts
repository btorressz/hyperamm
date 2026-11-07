import { exactDecimal } from './orderView';
import type { HistoricalReplayResult, ReplayArchive, ReplayFrame, ReplayIssue,
  ReplaySegment, ReplaySummary, ReplayProvenance, PaperResearchAssumptions, HistoricalReplayRequest } from '../types/replay';

export const REPLAY_MAX_FRAMES = 5000;
export const REPLAY_MAX_SEGMENTS = 32;
const hash = /^[a-f0-9]{64}$/;
const market = (value: unknown) => value === 'BTC' || value === 'ETH' || value === 'SOL';
const time = (value: unknown) => typeof value === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
// Python receipt clocks retain microseconds. Date.parse alone collapses distinct
// sub-millisecond receipts; chart/navigation identity must preserve their order.
function receiptTime(value: string): bigint {
  const fraction = /\.(\d{1,6})/.exec(value)?.[1] ?? '';
  return BigInt(Date.parse(value)) * 1000n + BigInt(fraction.padEnd(6,'0').slice(3));
}
const exact = (value: unknown) => typeof value === 'string' && /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value) && Number.isFinite(Number(value));
export function checkedReplaySummaries(input: unknown): ReplaySummary[] {
  if (!Array.isArray(input) || input.length > 256) throw new Error('Invalid historical dataset catalog.');
  const seen = new Set<string>();
  return input.map((raw: unknown) => {
    const x = raw as ReplaySummary;
    if (!x || typeof x !== 'object' || x.contract_version !== 'phase16-replay-v1' ||
      !identifier(x.dataset_id) ||
      seen.has(x.dataset_id) || !hash.test(x.dataset_fingerprint) || !market(x.market) ||
      !['RECORDED_NATIVE','SYNTHETIC_FIXTURE'].includes(x.source_kind) ||
      !time(x.coverage_start) || !time(x.coverage_end) ||
      receiptTime(x.coverage_end) <= receiptTime(x.coverage_start) ||
      !['PARTIAL','UNKNOWN'].includes(x.coverage_status) ||
      !Number.isSafeInteger(x.observation_count) || x.observation_count < 2 || x.observation_count > 5000 ||
      !Number.isSafeInteger(x.gap_count) || x.gap_count < 0 || x.gap_count > 1024 ||
      x.authority !== 'NONE' || x.read_only !== true ||
      x.source_authenticated !== false || x.licensing_independently_verified !== false ||
      x.continuous_history_verified !== false) throw new Error('Invalid historical dataset metadata.');
    seen.add(x.dataset_id);
    return x;
  });
}
const integer = (v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(v) && (v as number) >= min && (v as number) <= max;
const fingerprint = (v: unknown) => typeof v === 'string' && hash.test(v);
const identifier = (v: unknown) => typeof v === 'string' && v.length <= 120 && /^[A-Za-z0-9][A-Za-z0-9_.:/-]*$/.test(v);
const texts = (v: unknown, max = 64): v is string[] => Array.isArray(v) && v.length <= max && v.every(s => typeof s === 'string' && s.length <= 4096);
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const decimal = (v: unknown) => typeof v === 'string' && v.length <= 1024 && exactDecimal(v) !== '—' && Number.isFinite(Number(v));
// Equality only: no client financial recalculation.
function decimalKey(v: unknown) {
  if (!decimal(v)) return null;
  const raw = exactDecimal(v), [whole, fraction = ''] = raw.replace(/^[+-]/, '').split('.');
  const digits = whole.replace(/^0+(?=\d)/, '') + '.' + fraction.replace(/0+$/, '');
  return digits === '0.' ? '0.' : (raw.startsWith('-') ? '-' : '') + digits;
}
export function checkedReplayProvenance(x: ReplayProvenance, selected: ReplaySummary): ReplayProvenance {
  if (!validProvenance(x) || x.dataset_fingerprint !== selected.dataset_fingerprint ||
    x.source_kind !== selected.source_kind || x.observation_count !== selected.observation_count || x.gap_count !== selected.gap_count)
    throw new Error('Historical provenance does not match selected dataset.');
  return x;
}
function validProvenance(x: ReplayProvenance): boolean {
  return !!x && x.contract_version === 'phase16-replay-v1' &&
    [x.dataset_fingerprint,x.source_fingerprint,x.observations_fingerprint,x.gaps_fingerprint].every(fingerprint) &&
    ['RECORDED_NATIVE','SYNTHETIC_FIXTURE'].includes(x.source_kind) && x.authority === 'NONE' &&
    x.read_only === true && x.source_authenticated === false && x.licensing_independently_verified === false &&
    integer(x.observation_count,2,5000) && integer(x.gap_count,0,1024) && integer(x.l2_count,0,5000) && integer(x.perp_context_count,0,5000) &&
    x.l2_count + x.perp_context_count === x.observation_count && integer(x.verified_l2_event_time_count,0,x.l2_count) &&
    ['RECORDED_L2_VERIFIED_CONTEXT_RECEIPT_ONLY','RECORDED_L2_UNVERIFIED_OR_MISSING','SYNTHETIC_TIMES_NOT_EXCHANGE_VERIFIED'].includes(x.source_event_time_policy) &&
    (x.source_kind !== 'SYNTHETIC_FIXTURE' || (x.verified_l2_event_time_count === 0 && x.source_event_time_policy === 'SYNTHETIC_TIMES_NOT_EXCHANGE_VERIFIED')) && texts(x.limitations);
}
export function checkedReplayResult(x: HistoricalReplayResult, request: {
  dataset_id: string; dataset_fingerprint: string; market: string;
  execution?: HistoricalReplayRequest['execution']; policy?: HistoricalReplayRequest['policy'];
  max_frames?: number; record_trace?: boolean; trace_max_points?: number;
}): HistoricalReplayResult {
  if (!x || x.replay_version !== 'phase162-v1' || x.status !== 'COMPLETED_PARTIAL' ||
    x.simulated !== true || x.read_only !== true || x.authority !== 'NONE' || !validRequest(x.request) ||
    x.request.dataset_id !== request.dataset_id || x.request.dataset_fingerprint !== request.dataset_fingerprint || x.request.market !== request.market ||
    !validProvenance(x.provenance) || x.provenance.dataset_fingerprint !== request.dataset_fingerprint ||
    ![x.request_fingerprint,x.modeling_fingerprint,x.result_fingerprint,x.captured_configuration_fingerprint].every(fingerprint) ||
    (x.execution_assumptions_fingerprint != null && !fingerprint(x.execution_assumptions_fingerprint)) ||
    !validCapturedConfiguration(x.captured_configuration_json,request.market) ||
    !Array.isArray(x.segments) || !integer(x.segments.length,1,REPLAY_MAX_SEGMENTS) ||
    !integer(x.examined_observation_count,2,x.provenance.observation_count) ||
    !Array.isArray(x.issues) || x.issues.length > 10000 || !x.issues.every(validIssue) ||
    !Array.isArray(x.declared_gaps) || x.declared_gaps.length !== x.provenance.gap_count ||
    !x.declared_gaps.every(g => !!g && time(g.start_at) && time(g.end_at) && receiptTime(g.end_at) > receiptTime(g.start_at) &&
      ['DISCONNECT','DROPPED','OBSERVER_RESTART','MISSING_SOURCE','UNKNOWN_COVERAGE'].includes(g.reason)) || !texts(x.limitations))
    throw new Error('Replay response has incompatible provenance or authority.');
  if ((request.execution && (x.request.execution.size_decimals !== request.execution.size_decimals ||
      !samePaper(x.request.execution.paper ?? researchPaperDefaults(), request.execution.paper))) ||
      (request.policy && (x.request.policy.max_component_age_ms !== request.policy.max_component_age_ms || x.request.policy.max_frame_interval_ms !== request.policy.max_frame_interval_ms)) ||
      (request.max_frames !== undefined && x.request.max_frames !== request.max_frames) ||
      (request.record_trace !== undefined && x.request.record_trace !== request.record_trace) ||
      (request.trace_max_points !== undefined && x.request.trace_max_points !== request.trace_max_points))
    throw new Error('Replay response does not match captured settings.');
  let total = 0, archives = 0, previous: ReplayFrame | undefined;
  const modeled = x.request.execution.paper?.mode === 'MODELED_CROSSING';
  for (let i = 0; i < x.segments.length; i++) {
    const s = x.segments[i];
    if (!s || s.segment_index !== i || !Array.isArray(s.frames) || s.frames.length !== s.frame_count || !integer(s.frame_count,2,REPLAY_MAX_FRAMES) ||
      !['WINDOW_START','DECLARED_GAP','OBSERVER_CHANGE','RECEIPT_INTERVAL','UNAVAILABLE_FRAME'].includes(s.reset_reason) ||
      ![s.dataset_fingerprint,s.run_fingerprint,s.simulation_result_fingerprint].every(fingerprint) ||
      ![s.starting_equity,s.ending_equity,s.session_pnl].every(decimal) || !integer(s.fill_count) ||
      typeof s.simulation_result_json !== 'string' || s.simulation_result_json.length > 16_000_000 ||
      (modeled ? typeof s.baseline_result_json !== 'string' || s.baseline_result_json.length > 16_000_000 ||
        !fingerprint(s.baseline_result_fingerprint) || !decimal(s.session_pnl_delta) || !integer(s.fill_count_delta,-Number.MAX_SAFE_INTEGER)
        : [s.baseline_result_json,s.baseline_result_fingerprint,s.session_pnl_delta,s.fill_count_delta].some(v => v != null)))
      throw new Error('Replay segment evidence is malformed.');
    for (const f of s.frames) {
      if (!validFrame(f, request.market, x.provenance.source_kind) || (previous &&
        (f.sequence <= previous.sequence || receiptTime(f.evaluated_at) <= receiptTime(previous.evaluated_at))))
        throw new Error('Historical frame evidence is malformed or not chronological.');
      previous = f;
    }
    total += s.frame_count;
    archives += s.simulation_result_json.length + (s.baseline_result_json?.length ?? 0);
  }
  if (total !== x.frame_count || total > x.request.max_frames || total > REPLAY_MAX_FRAMES || archives > 64_000_000)
    throw new Error('Replay frame totals or archive budget are inconsistent.');
  return x;
}
function validCapturedConfiguration(wire: unknown, selectedMarket: string): boolean {
  if (typeof wire !== 'string' || wire.length > 100_000) return false;
  try {
    const c: unknown = JSON.parse(wire);
    return object(c) && object(c.strategy) && c.strategy.execution_mode === 'PAPER' &&
      c.strategy.market === selectedMarket && object(c.agents) && object(c.risk) &&
      object(c.simulation) && object(c.market_profile);
  } catch { return false; }
}
function validRequest(r: HistoricalReplayRequest): boolean {
  return !!r && identifier(r.dataset_id) && fingerprint(r.dataset_fingerprint) && market(r.market) &&
    integer(r.execution?.size_decimals,0,6) && paperInputError(r.execution?.paper ?? researchPaperDefaults()) === null &&
    !!r.policy && integer(r.policy.max_component_age_ms,0,30000) && integer(r.policy.max_frame_interval_ms,1,60000) &&
    (r.replay_version === undefined || r.replay_version === 'phase162-v1') &&
    (r.start_at == null || time(r.start_at)) && (r.end_at == null || time(r.end_at)) &&
    (r.policy.pairing === undefined || r.policy.pairing === 'RECEIPT_BATCH_LAST_COMPONENT') &&
    (r.policy.missing_economics === undefined || r.policy.missing_economics === 'REJECT_FRAME') &&
    (r.policy.discontinuity === undefined || r.policy.discontinuity === 'RESET_ALL_SIMULATION_STATE') &&
    (r.execution.metadata === undefined || r.execution.metadata === 'USER_ASSERTED_RESEARCH_PRECISION') &&
    (r.execution.strategy_scaling === undefined || r.execution.strategy_scaling === 'EXISTING_DEMO_MARKET_PROFILE') &&
    (r.execution.fill_model === undefined || r.execution.fill_model === 'PAPER_CROSSING_ONLY') &&
    (r.execution.external_references === undefined || r.execution.external_references === 'UNAVAILABLE') &&
    integer(r.max_frames,2,5000) && typeof r.record_trace === 'boolean' && integer(r.trace_max_points,0,5000);
}
function samePaper(a: PaperResearchAssumptions, b: PaperResearchAssumptions): boolean {
  return (Object.keys(b) as Array<keyof PaperResearchAssumptions>).every(k =>
    ['slippage_bps','participation_rate','max_fill_fraction'].includes(k) ? decimalKey(a[k]) === decimalKey(b[k]) : a[k] === b[k]);
}
function validIssue(i: ReplayIssue): boolean {
  return !!i && ['INCOMPLETE_FRAME','COMPONENT_TOO_OLD','SHORT_SEGMENT','NO_VIABLE_FRAMES','FRAME_LIMIT','SEGMENT_LIMIT','IDENTITY_MISMATCH'].includes(i.code) &&
    (i.sequence === null || integer(i.sequence)) && (i.received_at === null || time(i.received_at)) && (i.frame_count === null || integer(i.frame_count)) &&
    Array.isArray(i.missing_fields) && i.missing_fields.length <= 7 &&
    i.missing_fields.every(f => ['order_book','perp_context','mark_price','oracle_price','funding_rate','open_interest_base','positive_l2_sizes'].includes(f));
}
function validFrame(f: ReplayFrame, m: string, source: string): boolean {
  if (!f || !integer(f.sequence) || !time(f.evaluated_at) || !texts(f.derived_fields,16) ||
    !Array.isArray(f.receipt_batch_sequences) || !integer(f.receipt_batch_sequences.length,1,5000) ||
    !f.receipt_batch_sequences.every((s,i,a) => integer(s) && (!i || s > a[i-1])) || f.receipt_batch_sequences.at(-1) !== f.sequence ||
    f.economics !== (source === 'RECORDED_NATIVE' ? 'RECORDED_VALUES' : 'SYNTHETIC_FIXTURE_VALUES')) return false;
  const b = f.book_observation, c = f.context_observation;
  for (const o of [b,c]) if (!o || o.market !== m || !integer(o.sequence,0,f.sequence) || !time(o.received_at) ||
    receiptTime(o.received_at) > receiptTime(f.evaluated_at) || !identifier(o.observer_instance_id) || !integer(o.connection_generation)) return false;
  if (b.kind !== 'L2' || c.kind !== 'PERP_CONTEXT' || b.perp_context !== null || c.order_book !== null ||
    c.source_timestamp !== null || c.source_event_time_verified !== false || (b.source_timestamp !== null && !time(b.source_timestamp)) ||
    typeof b.source_event_time_verified !== 'boolean' || (b.source_event_time_verified && (source !== 'RECORDED_NATIVE' || !b.source_timestamp)) ||
    b.observer_instance_id !== c.observer_instance_id || b.connection_generation !== c.connection_generation) return false;
  const book = b.order_book, ctx = c.perp_context;
  return !!book && typeof book.truncated === 'boolean' && [book.bids,book.asks].every(levels => Array.isArray(levels) && integer(levels.length,1,20) &&
    levels.every(l => !!l && decimal(l.price) && Number(l.price) > 0 && decimal(l.size) && Number(l.size) > 0 && integer(l.order_count))) && !!ctx &&
    [ctx.mark_price,ctx.oracle_price,ctx.funding_rate,ctx.open_interest_base].every(decimal);
}
const decimalMetrics = ['starting_equity','ending_equity','session_pnl','return_pct','realized_pnl','unrealized_pnl','max_drawdown_pct',
  'quoted_notional','filled_notional','ending_inventory_base','max_abs_inventory_base','max_inventory_utilization','reconciliation_churn_ratio','risk_halt_fraction'];
const nullableMetrics = ['fill_activity_ratio','mean_spread_capture_bps','mean_mature_markout_bps','adverse_fill_rate'];
const countMetrics = ['fill_count','buy_fill_count','sell_fill_count','keep_count','create_count','replace_count','cancel_count'];
function checkedArchive(segment: ReplaySegment, baseline: boolean): ReplayArchive {
  const wire = baseline ? segment.baseline_result_json : segment.simulation_result_json;
  if (typeof wire !== 'string' || !wire || wire.length > 16_000_000) throw new Error('Selected result archive is unavailable or exceeds UI budget.');
  let value: unknown;
  try { value = JSON.parse(wire); } catch { throw new Error('Selected result archive cannot be decoded.'); }
  if (!object(value) || value.simulated !== true || value.scenario !== 'historical-replay' || typeof value.engine_version !== 'string' ||
    !fingerprint(value.run_fingerprint) || !fingerprint(value.strategy_fingerprint) || value.dataset_fingerprint !== segment.dataset_fingerprint ||
    !texts(value.limitations) || !object(value.metrics) || !Array.isArray(value.trace) || value.trace.length > Math.min(segment.frame_count,5000))
    throw new Error('Selected PAPER result archive is inconsistent.');
  const m = value.metrics;
  if (m.frame_count !== segment.frame_count || !decimalMetrics.every(k => decimal(m[k])) || !nullableMetrics.every(k => m[k] === null || decimal(m[k])) ||
    !countMetrics.every(k => integer(m[k])) || !['risk_state_counts','agent_regime_counts','toxic_flow_state_counts','execution_quality_state_counts'].every(k =>
      object(m[k]) && Object.keys(m[k]).length <= 32 && Object.values(m[k]).every(v => integer(v,0,segment.frame_count))))
    throw new Error('Selected PAPER metrics are malformed.');
  if (!baseline && (value.run_fingerprint !== segment.run_fingerprint || m.fill_count !== segment.fill_count ||
    !['starting_equity','ending_equity','session_pnl'].every(k => decimalKey(m[k]) === decimalKey(segment[k as keyof ReplaySegment]))))
    throw new Error('Selected result identity or segment metrics mismatch.');
  const frames = new Map(segment.frames.map(f => [f.sequence,f.evaluated_at]));
  let sequence = -1;
  for (const t of value.trace) {
    if (!object(t) || !integer(t.sequence) || (t.sequence as number) <= sequence || !time(t.timestamp) || frames.get(t.sequence as number) !== t.timestamp ||
      !['mid','mark','oracle','inventory_base','session_pnl','equity','drawdown_pct'].every(k => decimal(t[k])) ||
      !['desired_quote_count','agent_quote_count','authorized_quote_count','open_order_count','fill_count'].every(k => integer(t[k])) ||
      !['reference_confidence','agent_regime','toxic_flow_state','execution_quality_state','risk_state'].every(k => typeof t[k] === 'string' && (t[k] as string).length <= 120))
      throw new Error('Selected PAPER trace does not belong to this segment.');
    sequence = t.sequence as number;
  }
  return value as unknown as ReplayArchive;
}
export function readSegmentArchive(segment: ReplaySegment, baseline = false): ReplayArchive {
  // Decode only the selected segment; each engine run has its own identity.
  const archive = checkedArchive(segment, baseline);
  if (baseline) {
    const modeled = checkedArchive(segment, false);
    if (archive.strategy_fingerprint !== modeled.strategy_fingerprint || archive.run_fingerprint === modeled.run_fingerprint ||
      (archive.execution_assumptions as {mode?: string} | null)?.mode === 'MODELED_CROSSING')
      throw new Error('Baseline comparison identity mismatch.');
  }
  return archive;
}
export function framePrices(frame: ReplayFrame) {
  const book = frame.book_observation.order_book;
  const context = frame.context_observation.perp_context;
  const bid = book?.bids[0]?.price ?? null, ask = book?.asks[0]?.price ?? null;
  return { bid, ask, mid: exact(bid) && exact(ask) ? (Number(bid)+Number(ask))/2 : null,
    mark: context?.mark_price ?? null, oracle: context?.oracle_price ?? null };
}
export function issueLabel(issue: ReplayIssue): string {
  return [issue.code.replace(/_/g,' '), issue.sequence == null ? '' : 'sequence ' + issue.sequence,
    issue.missing_fields?.length ? 'missing ' + issue.missing_fields.join(', ') : ''].filter(Boolean).join(' · ');
}
export function researchPaperDefaults(): PaperResearchAssumptions {
  return {version:'phase163-v1', mode:'BASELINE', order_latency_ms:0, cancel_latency_ms:0,
    slippage_bps:'0', depth_sensitive:false, allow_partial_fills:true,
    participation_rate:'1', max_fill_fraction:'1'};
}
export function paperInputError(p: PaperResearchAssumptions): string | null {
  if (!p || typeof p.depth_sensitive !== 'boolean' || typeof p.allow_partial_fills !== 'boolean') return 'Invalid execution controls.';
  if (p.version !== 'phase163-v1' || !['BASELINE','MODELED_CROSSING'].includes(p.mode)) return 'Invalid execution model.';
  for (const v of [p.order_latency_ms,p.cancel_latency_ms])
    if (!Number.isSafeInteger(v) || v < 0 || v > 60000) return 'Latency must be a whole number between 0 and 60,000 ms.';
  for (const [key,value,max] of [
    ['Slippage',p.slippage_bps,1000],['Participation',p.participation_rate,1],
    ['Max fill fraction',p.max_fill_fraction,1]
  ] as const) {
    if (!exact(value) || value.startsWith('-') || value.length > 40 || (value.split('.')[1]?.length ?? 0) > 18 ||
      Number(value) < 0 || Number(value) > max)
      return key + ' must be an exact bounded decimal string.';
  }
  if (p.mode === 'BASELINE' &&
    (p.order_latency_ms !== 0 || p.cancel_latency_ms !== 0 || Number(p.slippage_bps) !== 0 ||
     p.depth_sensitive || !p.allow_partial_fills || Number(p.participation_rate) !== 1 ||
     Number(p.max_fill_fraction) !== 1)) return 'Baseline execution does not accept modeled controls.';
  return null;
}
