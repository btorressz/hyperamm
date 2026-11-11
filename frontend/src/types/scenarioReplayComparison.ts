/** Display-only types mirroring Phase 16.5A/B. Backend remains authoritative. */
import type { SimulationResult } from './index';
import type { HistoricalReplayResult, ReplayMarket } from './replay';

export type ComparisonDimension =
  'MARKET' | 'ENGINE' | 'STRATEGY' | 'AGENTS' | 'RISK' | 'ACCOUNTING' |
  'EXECUTION' | 'MARKET_PROFILE' | 'SIMULATION_CONTROLS';
export type ComparisonClassification = 'ALIGNED' | 'CONTEXT_ONLY' | 'INCOMPARABLE';
export type ComparisonSide = {
  kind: 'SCENARIO' | 'HISTORICAL_SEGMENT';
  market: ReplayMarket;
  source_kind: 'DETERMINISTIC_SCENARIO' | 'RECORDED_NATIVE' | 'SYNTHETIC_FIXTURE';
  original_dataset_fingerprint: string;
  engine_dataset_fingerprint: string;
  simulation_result_fingerprint: string;
  run_fingerprint: string;
  engine_version: string;
  frame_count: number;
  captured: {
    fingerprint: string;
    strategy_fingerprint: string;
    agents_fingerprint: string;
    risk_fingerprint: string;
    accounting_fingerprint: string;
    execution_fingerprint: string;
    market_profile_fingerprint: string | null;
    simulation_controls_fingerprint: string;
    canonical_json: string;
  };
  window_start: string | null;
  window_end: string | null;
  window_status: 'TRACE_COMPLETE' | 'UNKNOWN' | 'SEGMENT_RECEIPTS';
  segment_index: number | null;
  replay_result_fingerprint: string | null;
  replay_segment_count: number | null;
  source_authenticated: false;
  licensing_independently_verified: false;
  simulated: true;
  read_only: true;
  authority: 'NONE';
};
export type ComparisonFoundation = {
  version: 'phase165a1-v1';
  classification: ComparisonClassification;
  scenario: ComparisonSide;
  historical: ComparisonSide;
  aligned_dimensions: ComparisonDimension[];
  differing_dimensions: ComparisonDimension[];
  reasons: string[];
  direct_metric_deltas_allowed: false;
  cross_segment_aggregation_allowed: false;
  matched_market_evidence_verified: false;
  authority: 'NONE';
  limitations: string[];
  comparison_fingerprint: string;
};
export type ComparisonMetricName =
  'frame_count' | 'starting_equity' | 'ending_equity' | 'session_pnl' |
  'return_pct' | 'realized_pnl' | 'unrealized_pnl' | 'max_drawdown_pct' |
  'fill_count' | 'buy_fill_count' | 'sell_fill_count' | 'quoted_notional' |
  'filled_notional' | 'fill_activity_ratio' | 'ending_inventory_base' |
  'max_abs_inventory_base' | 'max_inventory_utilization' |
  'risk_halt_fraction' | 'fees_quote' | 'funding_quote' |
  'capital_utilization' | 'reserved_capital_quote' | 'gross_exposure_quote';
export type MetricUnit = 'frames' | 'quote' | 'percent' | 'fills' | 'base' | 'ratio';
export type MetricOrigin = 'SIMULATION_METRICS' | 'PAPER_VAULT';
export type MetricObservation = {
  origin: MetricOrigin;
  availability: 'AVAILABLE' | 'NOT_REPORTED';
  value: string | null;
};
export type QuantitativeMetricRow = {
  name: ComparisonMetricName;
  unit: MetricUnit;
  scenario: MetricObservation;
  historical_segment: MetricObservation;
};
export type QuantitativeComparisonReceipt = {
  version: 'phase165b-v1';
  foundation: ComparisonFoundation;
  scenario_receipt_fingerprint: string;
  selected_segment_index: number;
  display_policy: 'DESCRIPTIVE_ONLY' | 'BLOCKED';
  rows: QuantitativeMetricRow[];
  risk_states: { scenario: Record<string, number>; historical_segment: Record<string, number> } | null;
  differences_available: false;
  cross_segment_aggregation_allowed: false;
  strategy_ranking_allowed: false;
  matched_market_evidence_verified: false;
  authority: 'NONE';
  read_only: true;
  limitations: string[];
  receipt_fingerprint: string;
};
/** Optional paired original evidence for trace charts; NOT inside the B receipt. */
export type ComparisonChartEvidence = {
  scenario: SimulationResult;
  historical: HistoricalReplayResult;
};

export type ScenarioHistoricalRequest = {
  scenario: string; frames: number; research_market: ReplayMarket;
  simulation: {max_frames:number; record_trace:boolean; trace_max_points:number};
  research?: import('./index').ResearchProposal;
  historical: import('./replay').HistoricalReplayRequest;
  segment_index:number; include_traces:boolean; trace_point_limit:number;
};
export type ComparisonTrace = {
  run_fingerprint:string; dataset_fingerprint:string; simulation_result_fingerprint:string;
  frame_count:number; points:SimulationResult['trace']; omitted_points:number;
  omission:'NONE'|'NOT_REQUESTED'|'TRACE_UNAVAILABLE'|'POINT_LIMIT'|'INCOMPARABLE';
  source_times:Array<{sequence:number;book_received_at:string;book_source_timestamp:string|null;
    book_source_event_time_verified:boolean;context_received_at:string;context_source_timestamp:string|null;
    context_source_event_time_verified:boolean}>;
};
export type ScenarioHistoricalResponse = {
  version:'phase165c2-v1'; request:ScenarioHistoricalRequest; request_fingerprint:string;
  receipt:QuantitativeComparisonReceipt; segment_count:number;
  segments:Array<{segment_index:number;reset_reason:string;frame_count:number;window_start:string;window_end:string;
    dataset_fingerprint:string;run_fingerprint:string;simulation_result_fingerprint:string}>;
  selection_policy:'RERUN_SELECTED_SEGMENT'; provenance:import('./replay').ReplayProvenance;
  declared_gaps:import('./replay').ReplayGap[];issues:import('./replay').ReplayIssue[];omitted_issues:number;
  scenario_trace:ComparisonTrace;historical_trace:ComparisonTrace;read_only:true;authority:'NONE';
};
