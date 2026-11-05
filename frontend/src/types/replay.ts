import type { SimulationResult } from './index';

export type ReplayMarket = 'BTC' | 'ETH' | 'SOL';
export type ReplaySourceKind = 'RECORDED_NATIVE' | 'SYNTHETIC_FIXTURE';
export type ReplaySummary = {
  contract_version: 'phase16-replay-v1'; dataset_id: string; dataset_fingerprint: string;
  market: ReplayMarket; source_kind: ReplaySourceKind;
  coverage_start: string; coverage_end: string; coverage_status: 'PARTIAL' | 'UNKNOWN';
  observation_count: number; gap_count: number; source_authenticated: false;
  licensing_independently_verified: false; continuous_history_verified: false;
  read_only: true; authority: 'NONE';
};
export type ReplayProvenance = {
  contract_version: 'phase16-replay-v1'; dataset_fingerprint: string;
  source_fingerprint: string; observations_fingerprint: string; gaps_fingerprint: string;
  source_kind: ReplaySourceKind; source_authenticated: false; licensing_independently_verified: false;
  authority: 'NONE'; read_only: true; source_event_time_policy: string;
  observation_count: number; l2_count: number; verified_l2_event_time_count: number;
  perp_context_count: number; gap_count: number; limitations: string[];
};
export type ReplayLevel = { price: string; size: string; order_count: number };
export type ReplayObservation = {
  market: ReplayMarket; kind: 'L2' | 'PERP_CONTEXT'; sequence: number;
  received_at: string; source_timestamp: string | null; source_event_time_verified: boolean;
  observer_instance_id: string; connection_generation: number;
  order_book: { bids: ReplayLevel[]; asks: ReplayLevel[]; truncated: boolean } | null;
  perp_context: { mark_price: string | null; oracle_price: string | null;
    funding_rate: string | null; open_interest_base: string | null } | null;
};
export type ReplayFrame = {
  sequence: number; evaluated_at: string; receipt_batch_sequences: number[];
  book_observation: ReplayObservation; context_observation: ReplayObservation;
  economics: 'RECORDED_VALUES' | 'SYNTHETIC_FIXTURE_VALUES'; derived_fields: string[];
};
export type ReplayIssue = {
  code: string; sequence: number | null; received_at: string | null;
  missing_fields: string[]; frame_count: number | null;
};
export type ReplayGap = { start_at: string; end_at: string; reason: string; observer_instance_id?: string | null };
export type PaperResearchAssumptions = {
  version: 'phase163-v1'; mode: 'BASELINE' | 'MODELED_CROSSING';
  order_latency_ms: number; cancel_latency_ms: number; slippage_bps: string;
  depth_sensitive: boolean; allow_partial_fills: boolean;
  participation_rate: string; max_fill_fraction: string;
};
export type HistoricalReplayRequest = {
  dataset_id: string; dataset_fingerprint: string; market: ReplayMarket;
  execution: { size_decimals: number; paper: PaperResearchAssumptions };
  policy: { max_component_age_ms: number; max_frame_interval_ms: number };
  max_frames: number; record_trace: true; trace_max_points: number;
};
export type ReplaySegment = {
  segment_index: number; reset_reason: string; dataset_fingerprint: string;
  run_fingerprint: string; frames: ReplayFrame[]; frame_count: number;
  starting_equity: string; ending_equity: string; session_pnl: string; fill_count: number;
  simulation_result_json: string; simulation_result_fingerprint: string;
  baseline_result_json?: string | null; baseline_result_fingerprint?: string | null;
  session_pnl_delta?: string | null; fill_count_delta?: number | null;
};
export type HistoricalReplayResult = {
  replay_version: 'phase162-v1'; status: 'COMPLETED_PARTIAL'; simulated: true;
  read_only: true; authority: 'NONE'; request: HistoricalReplayRequest;
  request_fingerprint: string; modeling_fingerprint: string;
  execution_assumptions_fingerprint?: string | null;
  provenance: ReplayProvenance; declared_gaps: ReplayGap[];
  examined_observation_count: number; frame_count: number;
  issues: ReplayIssue[]; segments: ReplaySegment[];
  captured_configuration_fingerprint: string; result_fingerprint: string;
  limitations: string[];
};
export type ReplayArchive = Pick<SimulationResult, 'metrics' | 'trace' | 'engine_version' |
  'run_fingerprint' | 'dataset_fingerprint' | 'simulated' | 'limitations'> & SimulationResult;
