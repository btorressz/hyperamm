import type { PaperProposal, PaperBinding } from './generalizedPaper';
import type { FinancialUnit } from './marketRisk';
import type { MarketUniverseIdentity, MarketUniverseMetadata } from './marketUniverse';

export const advisoryVersion = 'phase184a-v1';
export const advisoryAnalysis = 'phase184bcd-v1';
export const advisoryOperations = [
  'DISCOVERY', 'STANDARD_PAPER', 'HYPOTHETICAL_RISK', 'SOURCE_CONSTRAINED_RISK',
  'FUNDING_BASIS', 'QUOTE_ECONOMICS',
] as const;
export type AdvisoryOperation = typeof advisoryOperations[number];
export const advisoryStatuses = ['READY', 'INSUFFICIENT_DATA', 'STALE', 'UNSUPPORTED', 'ERROR'] as const;
export const advisoryProvenance = ['EXCHANGE_OBSERVED', 'SCENARIO_SYNTHETIC', 'HYPOTHETICAL_ASSUMPTION', 'UNAVAILABLE'] as const;
export const advisoryCategories = [
  'MARKET_METADATA', 'COLLATERAL', 'MARGIN_POLICY', 'PAPER_ADMISSION', 'FUNDING', 'MARK_PRICE',
  'ORACLE_PRICE', 'MID_PRICE', 'BASIS', 'QUOTE_LADDER', 'FEES', 'INVENTORY', 'FILL_MARKOUT', 'RISK_MODEL',
  'OPEN_INTEREST', 'FUNDING_HISTORY', 'PAPER_FILLS',
] as const;
export const advisoryIssueText = {
  PAPER_RESULT_REQUIRED: 'Complete a local PAPER run to inspect this evidence.',
  PAPER_RESULT_UNAVAILABLE: 'The server no longer has this PAPER result. Start a new run.',
  PAPER_EVIDENCE_EXPIRED: 'This PAPER evidence expired. Refresh discovery and start a new run.',
  QUOTE_COHORT_REQUIRED: 'Select a retained quote frame and enter the research cost assumptions.',
  INVALID_QUOTE_COHORT: 'This quote frame is absent from the retained PAPER trace.',
  PROVIDER_OBSERVATION_UNAVAILABLE: 'Some required public provider observations are unavailable.',
  PROVIDER_RATE_LIMITED: 'The public provider is rate limited. Try again after the backoff.',
  PROVIDER_TIMEOUT: 'The public provider request timed out.',
  PROVIDER_IDENTITY_MISMATCH: 'The public response could not be bound to this market and network.',
} as const;

export type FundingMode = 'OBSERVED' | 'PAPER';
export interface QuoteAssumptions {
  holding_seconds: number;
  closing_liquidity: 'MAKER' | 'TAKER';
  exit_slippage_bps: string;
  inventory_rate_bps: string;
}
export interface AdvisoryRequest {
  identity: MarketUniverseIdentity;
  catalog_fingerprint: string;
  operation: AdvisoryOperation;
  proposal?: PaperProposal;
  funding_mode?: FundingMode;
  paper_receipt?: string;
  quote?: { sequence: number; assumptions: QuoteAssumptions };
}
export interface AdvisorySelection {
  metadata: MarketUniverseMetadata;
  metadata_fingerprint: string;
  catalog_fingerprint: string;
  max_age_seconds: number;
}
export interface AdvisoryPaperBinding {
  result_fingerprint: string;
  binding: PaperBinding;
}

type Provenance = typeof advisoryProvenance[number];
interface ReadOnly {
  contract_version: typeof advisoryVersion;
  read_only: true;
  authority: 'NONE';
  execution_eligible: false;
}
interface NoAuthority extends ReadOnly {
  affects_quotes: false;
  can_override_risk: false;
  can_authorize_paper: false;
}
export interface AdvisorySource extends ReadOnly {
  identity: MarketUniverseIdentity;
  category: typeof advisoryCategories[number];
  provenance: Provenance;
  source_id: string;
  binding_version: typeof advisoryAnalysis;
  source_fingerprint: string;
  captured_at: string;
  observed_at: string | null;
  observation_clock?: 'PROVIDER_EVENT' | 'LOCAL_RECEIPT';
  scenario_at: string | null;
  valid_until?: string;
  unit?: string;
  financial_unit: FinancialUnit | null;
  limitations?: string[];
}
interface Recommendation extends NoAuthority {
  analysis_version: typeof advisoryAnalysis;
  identity: MarketUniverseIdentity;
  context_fingerprint: string;
  evaluated_at: string;
  status: typeof advisoryStatuses[number];
  confidence: string;
  provenance: Provenance | 'MIXED';
  source_fingerprints: string[];
  reasons: string[];
  missing_requirements?: string[];
}
export interface EligibilityAdvisory extends Recommendation {
  agent: 'MARKET_ELIGIBILITY';
  operation: AdvisoryOperation;
  suitability: 'SUITABLE' | 'CONDITIONAL' | 'NOT_SUITABLE' | 'UNKNOWN';
}
export interface FundingAdvisory extends Recommendation {
  agent: 'FUNDING_BASIS';
  state: 'FUNDING_POSITIVE' | 'FUNDING_NEGATIVE' | 'BASIS_STRESSED' | 'NEUTRAL' | 'UNKNOWN';
  funding_rate: string | null;
  funding_interval_seconds: number | null;
  mark_price?: string;
  oracle_price?: string;
  midpoint_price?: string;
  mark_oracle_basis_bps: string | null;
  mark_mid_basis_bps: string | null;
  oracle_mid_basis_bps?: string;
  funding_convention?: 'HYPERLIQUID_HOURLY' | 'PAPER_SCHEDULED_INTERVAL';
  funding_direction?: 'LONGS_PAY' | 'SHORTS_PAY' | 'FLAT';
  open_interest_base?: string;
  history_count?: number;
  recent_history_mean_rate?: string;
}
export interface QuoteAdvisory extends Recommendation {
  agent: 'QUOTE_ECONOMICS';
  state: 'MODELED_POSITIVE' | 'MODELED_NEGATIVE' | 'MODELED_BREAKEVEN' | 'INDETERMINATE';
  hypothetical_only: true;
  guarantees_profit: false;
  accounting_unit: FinancialUnit | null;
  gross_spread_bps: string | null;
  fee_cost_bps: string | null;
  funding_cost_bps: string | null;
  inventory_cost_bps: string | null;
  adverse_selection_cost_bps: string | null;
  modeled_edge_bps: string | null;
  captured_spread_bps?: string;
  slippage_cost_bps?: string;
  break_even_capture_bps?: string;
  submitted_bid?: string;
  submitted_ask?: string;
  entry_fees_quote?: string;
  exit_fees_quote?: string;
  attributed_fill_count?: number;
  matured_markout_count?: number;
  quoted_notional?: string;
  executed_reference_notional?: string;
  holding_seconds?: number;
  funding_interval_seconds?: number;
  fill_coverage?: 'ONE_SIDED' | 'BOTH_SIDES';
  bid_capture_bps?: string;
  ask_capture_bps?: string;
  filled_base?: string;
  residual_base?: string;
  inventory_expansion_base?: string;
  projected_margin_headroom?: string;
  margin_headroom_unit?: FinancialUnit;
}
export type AdvisoryRecommendation = EligibilityAdvisory | FundingAdvisory | QuoteAdvisory;

export interface AdvisoryResponse extends NoAuthority {
  schema_version: 'phase184e-v1';
  identity: MarketUniverseIdentity;
  snapshot_fingerprint: string;
  evaluated_at: string;
  valid_until: string;
  funding_mode: FundingMode | null;
  paper_result_fingerprint: string | null;
  quote_cohorts: number[];
  quote_sequence: number | null;
  quote_risk_state: 'NORMAL' | 'WIDEN' | 'REDUCE' | 'HALT' | null;
  issues: (keyof typeof advisoryIssueText)[];
  snapshot: {
    contract_version: typeof advisoryVersion;
    authority: 'NONE';
    affects_quotes: false;
    execution_eligible: false;
    scope: 'SINGLE_MARKET_RESEARCH_ONLY';
    context: ReadOnly & {
      metadata: MarketUniverseMetadata;
      metadata_fingerprint: string;
      catalog_fingerprint: string;
      paper_binding_fingerprint: string | null;
      risk_model_fingerprint: string | null;
      evaluated_at: string;
      valid_until: string;
      scope: 'SINGLE_MARKET_RESEARCH_ONLY';
      sources: AdvisorySource[];
    };
    market_eligibility: EligibilityAdvisory;
    funding_basis: FundingAdvisory | null;
    quote_economics: QuoteAdvisory | null;
  };
}
