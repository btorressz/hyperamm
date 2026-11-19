import type { MarketUniverseEligibility, MarketUniverseIdentity, MarketUniverseMetadata } from './marketUniverse';

export const paperProfileVersion = 'phase182-v1';

export interface HypotheticalEconomics {
  model: 'HYPOTHETICAL_LINEAR';
  maker_fee_bps?: string;
  taker_fee_bps?: string;
  funding_interval_seconds?: number | null;
}

export interface PaperProposal {
  profile_version: typeof paperProfileVersion;
  identity: MarketUniverseIdentity;
  simulated_reference_price: string;
  synthetic_top_depth_quote?: string;
  minimum_order_notional?: string;
  scenario: string;
  frames: number;
  trace_max_points: number;
  economics: HypotheticalEconomics;
}

export interface PaperBinding {
  metadata_fingerprint: string;
  profile_fingerprint: string;
  configuration_fingerprint: string;
}

export interface GeneralizedMarketProfile {
  profile_version: typeof paperProfileVersion;
  metadata: MarketUniverseMetadata;
  discovery: MarketUniverseEligibility;
  stable_key: string;
  exchange_coin: string;
  metadata_fingerprint: string;
  profile_fingerprint: string;
  simulated_reference_price: string;
  synthetic_top_depth_quote: string;
  economics: Required<HypotheticalEconomics>;
  reference_source: 'USER_SUPPLIED_SYNTHETIC';
  model_compatibility: 'HYPOTHETICAL_LINEAR_ONLY';
  paper_eligibility: 'REQUIRES_ADMISSION';
  limitations: string[];
  authority: 'NONE';
  execution_eligible: false;
}

export const paperReasons = {
  ADMITTED: 'admission',
  METADATA_UNAVAILABLE: 'metadata',
  METADATA_STALE: 'freshness',
  MARKET_DELISTED: 'listing',
  NETWORK_MISMATCH: 'network',
  IDENTITY_MISMATCH: 'identity',
  PROFILE_UNSUPPORTED: 'profile_version',
  PRICE_UNREPRESENTABLE: 'price_precision',
  SIZE_UNREPRESENTABLE: 'quantity_precision',
  SCENARIO_INFEASIBLE: 'scenario_preflight',
  FUNDING_MODEL_UNSUPPORTED: 'funding_assumptions',
  CONFIGURATION_INVALID: 'request',
  PROFILE_FINGERPRINT_MISMATCH: 'profile_fingerprint',
  METADATA_FINGERPRINT_MISMATCH: 'metadata_fingerprint',
  CONFIGURATION_FINGERPRINT_MISMATCH: 'configuration_fingerprint',
} as const;
export type PaperReason = keyof typeof paperReasons;

interface PaperDecisionEvidence {
  profile_version: typeof paperProfileVersion;
  identity: MarketUniverseIdentity | null;
  explanation: string;
  checks: string[];
  evaluated_at: string;
  scope: 'LOCAL_PAPER_ONLY';
  authority: 'NONE';
  execution_eligible: false;
  limitations: string[];
}

export type PaperAdmission = PaperDecisionEvidence & (
  | { status: 'ELIGIBLE'; reason: 'ADMITTED'; binding: PaperBinding;
      profile: GeneralizedMarketProfile; valid_until: string }
  | { status: 'REJECTED' | 'UNAVAILABLE'; reason: Exclude<PaperReason, 'ADMITTED'>; binding: null;
      profile: GeneralizedMarketProfile | null; valid_until: null }
);

export interface GeneralizedPaperResult {
  profile_version: typeof paperProfileVersion;
  admission: PaperAdmission & { status: 'ELIGIBLE' };
  proposal: PaperProposal;
  execution_mode: 'PAPER';
  simulated: true;
  result_fingerprint: string;
  result: {
    engine_version: string;
    run_fingerprint: string;
    dataset_fingerprint: string;
    strategy_fingerprint: string;
    scenario: string;
    research_market: string;
    market_profile_version: typeof paperProfileVersion;
    market_profile_fingerprint: string;
    simulated: true;
    metrics: { frame_count: number; fill_count: number };
    vault: { market: string; mode: 'PAPER'; simulated: true; net_pnl_quote: string;
        fees_quote: string; funding_quote: string; position_base: string };
  };
}
