import type { MarketUniverseEligibility, MarketUniverseIdentity, MarketUniverseMetadata } from './marketUniverse';
import type { FinancialObservation, FinancialSourceStatus, PaperRiskResult, ResearchRiskModel, ResearchRiskSettings } from './marketRisk';
import type { AssetAmmResearchPolicy } from './assetAmm';

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
  research_risk?: ResearchRiskSettings;
  asset_amm_policy?: AssetAmmResearchPolicy;
}

export interface PaperBinding {
  catalog_fingerprint: string;
  metadata_fingerprint: string;
  profile_fingerprint: string;
  configuration_fingerprint: string;
  research_risk_fingerprint?: string;
  asset_policy_fingerprint?: string;
}

export const paperEvidenceBoundary = {
  version: 'phase182g-v1',
  references: 'phase182g-v1:synthetic-scenario',
  reference_clock: 'SIMULATION_FRAME_TIME',
  order_book: 'SYNTHETIC_DEPTH',
  accounting_units: 'HYPOTHETICAL_QUOTE',
  capital_reservation: 'SIMULATED_FULL_NOTIONAL',
  fees: 'HYPOTHETICAL_MAKER_TAKER',
  funding: 'HYPOTHETICAL_SCHEDULED',
  exchange_economics: 'UNVERIFIED',
  risk_readiness: 'SINGLE_MARKET_RESEARCH_ONLY',
} as const;

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
  evidence_boundary: typeof paperEvidenceBoundary;
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
  CATALOG_FINGERPRINT_MISMATCH: 'catalog_fingerprint',
  CONFIGURATION_FINGERPRINT_MISMATCH: 'configuration_fingerprint',
  RISK_FINGERPRINT_MISMATCH: 'research_risk_fingerprint',
  RISK_SOURCE_UNAVAILABLE: 'financial_source',
  RISK_SOURCE_STALE: 'financial_source',
  RISK_SOURCE_UNSUPPORTED: 'financial_source',
  RISK_UNIT_MISMATCH: 'risk_valuation',
  RISK_MARGIN_MODE_UNSUPPORTED: 'margin_mode',
  RISK_LEVERAGE_UNSUPPORTED: 'research_leverage',
  RISK_CAPITAL_INSUFFICIENT: 'research_capital',
  RISK_EXPOSURE_INVALID: 'research_exposure',
  ASSET_POLICY_FINGERPRINT_MISMATCH: 'asset_policy_fingerprint',
  ADVISORY_FINGERPRINT_MISMATCH: 'advisory_snapshot_fingerprint',
  ADVISORY_UNAVAILABLE: 'advisory_snapshot_fingerprint',
  ADVISORY_STALE: 'advisory_snapshot_fingerprint',
  ORDER_NOTIONAL_TOO_SMALL: 'minimum_order_notional',
} as const;
export type PaperReason = keyof typeof paperReasons;

export const assetPaperReasonText: Partial<Record<PaperReason, string>> = {
  ASSET_POLICY_FINGERPRINT_MISMATCH: 'The asset research policy changed. Check eligibility again.',
  ADVISORY_FINGERPRINT_MISMATCH: 'The advisory snapshot does not match this research policy and market.',
  ADVISORY_UNAVAILABLE: 'The server has no retained advisory snapshot for this fingerprint.',
  ADVISORY_STALE: 'The advisory snapshot expired. Refresh the advisory evidence.',
  ORDER_NOTIONAL_TOO_SMALL: 'A normalized quote is below the selected minimum order notional.',
};

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
  risk_source_status?: FinancialSourceStatus;
}

export type PaperAdmission = PaperDecisionEvidence & (
  | { status: 'ELIGIBLE'; reason: 'ADMITTED'; binding: PaperBinding;
      profile: GeneralizedMarketProfile; valid_until: string; risk_model?: ResearchRiskModel }
  | { status: 'REJECTED' | 'UNAVAILABLE'; reason: Exclude<PaperReason, 'ADMITTED'>; binding: null;
      profile: GeneralizedMarketProfile | null; valid_until: null; risk_source?: FinancialObservation }
);

export interface GeneralizedPaperResult {
  profile_version: typeof paperProfileVersion;
  admission: PaperAdmission & { status: 'ELIGIBLE' };
  proposal: PaperProposal;
  execution_mode: 'PAPER';
  simulated: true;
  result_fingerprint: string;
  advisory_receipt?: string;
  research_risk?: PaperRiskResult;
  started_at: string;
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
        initial_equity_quote: string; equity_quote: string; reserved_capital_quote: string;
        realized_pnl_quote: string; unrealized_pnl_quote: string;
        fees_quote: string; funding_quote: string; position_base: string };
  };
}
