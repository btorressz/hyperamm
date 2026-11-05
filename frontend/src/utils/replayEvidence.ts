import type { SimulationResult } from '../types';
import type { HistoricalReplayResult, ReplayArchive, ReplayFrame, ReplayIssue,
  ReplaySegment, ReplaySummary, ReplayProvenance, PaperResearchAssumptions } from '../types/replay';

export const REPLAY_MAX_FRAMES = 5000;
export const REPLAY_MAX_SEGMENTS = 32;
const hash = /^[a-f0-9]{64}$/;
const market = (value: unknown) => value === 'BTC' || value === 'ETH' || value === 'SOL';
const time = (value: unknown) => typeof value === 'string' && Number.isFinite(Date.parse(value));
const exact = (value: unknown) => typeof value === 'string' && /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value) && Number.isFinite(Number(value));
export function checkedReplaySummaries(input: unknown): ReplaySummary[] {
  if (!Array.isArray(input) || input.length > 256) throw new Error('Invalid historical dataset catalog.');
  const seen = new Set<string>();
  return input.map((raw: unknown) => {
    const x = raw as ReplaySummary;
    if (!x || typeof x !== 'object' || x.contract_version !== 'phase16-replay-v1' ||
      typeof x.dataset_id !== 'string' || !x.dataset_id || x.dataset_id.length > 120 ||
      seen.has(x.dataset_id) || !hash.test(x.dataset_fingerprint) || !market(x.market) ||
      !['RECORDED_NATIVE','SYNTHETIC_FIXTURE'].includes(x.source_kind) ||
      !time(x.coverage_start) || !time(x.coverage_end) ||
      Date.parse(x.coverage_end) <= Date.parse(x.coverage_start) ||
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
export function checkedReplayProvenance(x: ReplayProvenance, selected: ReplaySummary): ReplayProvenance {
  if (!x || x.dataset_fingerprint !== selected.dataset_fingerprint ||
    x.source_kind !== selected.source_kind || x.authority !== 'NONE' ||
    x.read_only !== true || x.source_authenticated !== false ||
    x.licensing_independently_verified !== false ||
    !Array.isArray(x.limitations) || x.observation_count !== selected.observation_count)
    throw new Error('Historical provenance does not match selected dataset.');
  return x;
}
export function checkedReplayResult(x: HistoricalReplayResult, request: {
  dataset_id: string; dataset_fingerprint: string; market: string
}): HistoricalReplayResult {
  if (!x || x.replay_version !== 'phase162-v1' || x.status !== 'COMPLETED_PARTIAL' ||
    x.simulated !== true || x.read_only !== true || x.authority !== 'NONE' ||
    x.request?.dataset_id !== request.dataset_id ||
    x.request?.dataset_fingerprint !== request.dataset_fingerprint ||
    x.request?.market !== request.market ||
    x.provenance?.dataset_fingerprint !== request.dataset_fingerprint ||
    !hash.test(x.result_fingerprint) ||
    !Array.isArray(x.segments) || x.segments.length > REPLAY_MAX_SEGMENTS ||
    !Array.isArray(x.issues) || !Array.isArray(x.declared_gaps) ||
    !Array.isArray(x.limitations)) throw new Error('Replay response has incompatible provenance or authority.');
  let total = 0;
  for (let i = 0; i < x.segments.length; i++) {
    const s = x.segments[i];
    if (s.segment_index !== i || !Array.isArray(s.frames) ||
      s.frames.length !== s.frame_count || s.frame_count < 2 ||
      !hash.test(s.simulation_result_fingerprint) ||
      s.frames.some(f => !validFrame(f, request.market)) ||
      s.dataset_fingerprint.length !== 64 ||
      typeof s.simulation_result_json !== 'string' || s.simulation_result_json.length > 16_000_000)
      throw new Error('Replay segment evidence is malformed.');
    for (let j = 1; j < s.frames.length; j++)
      if (s.frames[j].sequence <= s.frames[j-1].sequence ||
          Date.parse(s.frames[j].evaluated_at) <= Date.parse(s.frames[j-1].evaluated_at))
        throw new Error('Historical frames are not chronological.');
    total += s.frame_count;
  }
  if (total !== x.frame_count || total > REPLAY_MAX_FRAMES)
    throw new Error('Replay frame totals are inconsistent.');
  return x;
}
function validFrame(f: ReplayFrame, m: string): boolean {
  return !!f && Number.isSafeInteger(f.sequence) && time(f.evaluated_at) &&
    Array.isArray(f.receipt_batch_sequences) &&
    f.book_observation?.market === m && f.book_observation.kind === 'L2' &&
    f.context_observation?.market === m && f.context_observation.kind === 'PERP_CONTEXT' &&
    !!f.book_observation.order_book && !!f.context_observation.perp_context &&
    ['RECORDED_VALUES','SYNTHETIC_FIXTURE_VALUES'].includes(f.economics);
}
export function readSegmentArchive(segment: ReplaySegment, baseline = false): ReplayArchive {
  // Lazy selection: never parse all archived engine results on page mount.
  const wire = baseline ? segment.baseline_result_json : segment.simulation_result_json;
  if (!wire || wire.length > 16_000_000) throw new Error('Selected result archive is unavailable or exceeds UI budget.');
  let archive: SimulationResult;
  try { archive = JSON.parse(wire) as SimulationResult; }
  catch { throw new Error('Selected result archive cannot be decoded.'); }
  if (!archive || archive.simulated !== true || !archive.metrics ||
      !Array.isArray(archive.trace) || !Array.isArray(archive.limitations) ||
      archive.dataset_fingerprint !== segment.dataset_fingerprint ||
      typeof archive.run_fingerprint !== 'string')
    throw new Error('Selected PAPER result archive is inconsistent.');
  if (!baseline && archive.run_fingerprint !== segment.run_fingerprint)
    throw new Error('Modeled result identity mismatch.');
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
  if (p.version !== 'phase163-v1' || !['BASELINE','MODELED_CROSSING'].includes(p.mode)) return 'Invalid execution model.';
  for (const v of [p.order_latency_ms,p.cancel_latency_ms])
    if (!Number.isSafeInteger(v) || v < 0 || v > 60000) return 'Latency must be a whole number between 0 and 60,000 ms.';
  for (const [key,value,max] of [
    ['Slippage',p.slippage_bps,1000],['Participation',p.participation_rate,1],
    ['Max fill fraction',p.max_fill_fraction,1]
  ] as const) {
    if (!exact(value) || value.length > 40 || (value.split('.')[1]?.length ?? 0) > 18 ||
      Number(value) < 0 || Number(value) > max)
      return key + ' must be an exact bounded decimal string.';
  }
  if (p.mode === 'BASELINE' &&
    (p.order_latency_ms !== 0 || p.cancel_latency_ms !== 0 || Number(p.slippage_bps) !== 0 ||
     p.depth_sensitive || !p.allow_partial_fills || Number(p.participation_rate) !== 1 ||
     Number(p.max_fill_fraction) !== 1)) return 'Baseline execution does not accept modeled controls.';
  return null;
}
