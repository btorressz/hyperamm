import type { MarketUniverseIdentity, MarketUniverseMetadata, MarketUniverseNetwork } from './marketUniverse';

export const riskEvidenceVersion = 'phase183e-v1';
export const riskModelVersion = 'phase183c-v1';
export const paperRiskResultVersion = 'phase183d-v1';
export const maxResearchStresses = 8;

export type FinancialSourceStatus = 'SOURCE_OBSERVED' | 'STALE' | 'UNAVAILABLE' | 'UNSUPPORTED';
export type ObservedMarginMode = 'STRICT_ISOLATED' | 'NO_CROSS' | 'CROSS_ELIGIBLE' | 'ISOLATED_UNSPECIFIED' | 'UNKNOWN';
export type ResearchMarginMode = 'ISOLATED' | 'STRICT_ISOLATED' | 'NO_CROSS';
export type ResearchRiskMode = 'HYPOTHETICAL' | 'SOURCE_CONSTRAINED';
export type SourceConstraintReason = 'RISK_SOURCE_UNAVAILABLE' | 'RISK_SOURCE_STALE' |
  'RISK_SOURCE_UNSUPPORTED' | 'RISK_MARGIN_MODE_UNSUPPORTED';

interface NoExecutionAuthority {
  authority: 'NONE';
  execution_eligible: false;
}

interface RiskFoundation {
  contract_version: 'phase183a-v1';
}

export type FinancialUnit = RiskFoundation & { network: MarketUniverseNetwork } & (
  | { kind: 'HYPOTHETICAL_QUOTE'; symbol: 'HYPOTHETICAL_QUOTE'; asset_namespace: '';
      asset_reference: null; provenance: 'RESEARCH_ASSUMPTION' }
  | { kind: 'EXCHANGE_ASSET'; symbol: string; asset_namespace: 'hyperliquid.spot';
      asset_reference: string; provenance: 'DECLARED_UNVERIFIED' }
);

export interface ObservedCollateral {
  network: MarketUniverseNetwork;
  index: number;
  token_id: string;
  symbol: string;
  namespace: 'hyperliquid.spot';
  observed_at: string;
  canonical: boolean | null;
}

export interface MarginTier {
  lower_bound: string;
  max_leverage: number;
}

export interface ObservedMarginPolicy {
  mode: ObservedMarginMode;
  reported_mode: string | null;
  only_isolated: boolean | null;
  table_id: number | null;
  reported_max_leverage: number | null;
  tier_source: 'EXPLICIT_TABLE' | 'DOCUMENTED_TABLE_ID' | null;
  tiers: MarginTier[];
}

export interface FinancialObservation extends NoExecutionAuthority {
  schema_version: 'phase183b-v1';
  source: 'HYPERLIQUID_INFO_META';
  metadata: MarketUniverseMetadata;
  metadata_fingerprint: string;
  collateral_token_index: number | null;
  collateral: ObservedCollateral | null;
  collateral_source: 'HYPERLIQUID_INFO_SPOT_META' | null;
  collateral_status: FinancialSourceStatus;
  margin: ObservedMarginPolicy;
  margin_status: FinancialSourceStatus;
  issues: string[];
  price_quote_unit: null;
  settlement_unit: null;
  account_mode: 'UNKNOWN';
  documented_units: {
    source: 'HYPERLIQUID_CONTRACT_SPECIFICATIONS'; price_denomination: 'USDT'; pnl_unit: FinancialUnit;
  } | null;
  read_only: true;
}

export interface FinancialEvidenceSelection {
  metadata: MarketUniverseMetadata;
  metadata_fingerprint: string;
  catalog_fingerprint: string;
  max_age_seconds: number;
}

export interface FinancialEvidence extends NoExecutionAuthority {
  schema_version: typeof riskEvidenceVersion;
  model_version: typeof riskModelVersion;
  identity: MarketUniverseIdentity;
  catalog_fingerprint: string;
  metadata_fingerprint: string;
  evaluated_at: string;
  valid_until: string;
  status: FinancialSourceStatus;
  observation: FinancialObservation | null;
  source_fingerprint: string | null;
  source_constraint_reason: SourceConstraintReason | null;
  source_margin_modes: ResearchMarginMode[];
  scope: 'LOCAL_PAPER_ONLY';
  read_only: true;
}

export interface ValuationAssumption {
  collateral_unit: Extract<FinancialUnit, { kind: 'EXCHANGE_ASSET' }>;
  collateral_per_paper_quote: string;
  provenance: 'FIXED_HYPOTHETICAL_SCENARIO_RATE';
}

export const stressFields = ['price_shock_bps', 'collateral_loss_bps', 'capital_reduction_bps', 'funding_cost_bps', 'fees_bps'] as const;
export type StressField = typeof stressFields[number];
export type StressAssumption = { name: string } & Record<StressField, string>;

export interface ResearchRiskSettings {
  mode: ResearchRiskMode;
  margin_mode: ResearchMarginMode;
  capital_paper_quote: string;
  initial_margin_fraction: string | null;
  maintenance_margin_fraction: string | null;
  max_leverage: string | null;
  leverage: string | null;
  valuation: ValuationAssumption | null;
  stresses: StressAssumption[];
}

interface DeclaredFinancialUnits extends RiskFoundation {
  metadata: MarketUniverseMetadata;
  metadata_fingerprint: string;
  paper_accounting_unit: FinancialUnit;
  collateral_unit: FinancialUnit | null;
  price_quote_unit: null;
  settlement_unit: null;
  unit_evidence: 'DECLARED_UNVERIFIED';
  verified_collateral: false;
  verified_settlement: false;
  read_only: true;
  authority: 'NONE';
}

interface ResearchMarginPolicy extends RiskFoundation, NoExecutionAuthority {
  financial_units: DeclaredFinancialUnits;
  account_mode: 'UNKNOWN';
  margin_mode: ResearchMarginMode;
  policy_evidence: 'HYPOTHETICAL' | 'UNVERIFIED';
  initial_margin_fraction: string | null;
  maintenance_margin_fraction: string | null;
  modeled_max_leverage: string | null;
  liquidation_price: null;
  exchange_margin_verified: false;
  shared_capital_eligible: false;
  cross_market_netting_eligible: false;
}

export interface ResearchRiskModel extends NoExecutionAuthority {
  version: typeof riskModelVersion;
  settings: ResearchRiskSettings;
  declaration: ResearchMarginPolicy;
  readiness: RiskFoundation & NoExecutionAuthority & {
    identity: MarketUniverseIdentity;
    metadata_fingerprint: string;
    collateral_fingerprint: string;
    margin_policy_fingerprint: string;
    evaluated_at: string;
    status: 'BLOCKED';
    reason: string;
    scope: 'SINGLE_MARKET_RESEARCH_ONLY';
    read_only: true;
    risk_ready: false;
    exchange_margin_verified: false;
    shared_capital_eligible: false;
    cross_market_netting_eligible: false;
    leverage_eligible: false;
  };
  source: FinancialObservation | null;
  source_fingerprint: string | null;
  margin_unit: FinancialUnit;
  formula: 'HYPOTHETICAL_LINEAR' | 'DOCUMENTED_HYPERLIQUID_TIERS';
}

export const exposureDecimals = [
  'mark_paper_quote_per_base', 'signed_base', 'absolute_notional', 'gross_long_notional', 'gross_short_notional',
  'proposed_bid_notional', 'proposed_ask_notional', 'resting_bid_notional', 'resting_ask_notional',
  'effective_bid_notional', 'effective_ask_notional', 'projected_long_base', 'projected_short_base',
  'inventory_utilization', 'capital_concentration',
] as const;

export type ResearchExposure = Record<typeof exposureDecimals[number], string> & {
  base_instrument: MarketUniverseIdentity;
  quote_unit: FinancialUnit;
};

export interface Requirements {
  initial: string;
  maintenance: string;
  tier_lower_bound: string | null;
  source_max_leverage: number | null;
  margin_leverage: string | null;
  leverage_supported: boolean;
}

export const marginDecimals = ['capital', 'projected_initial', 'projected_maintenance',
  'initial_headroom', 'maintenance_headroom', 'projected_headroom'] as const;
export type ResearchMargin = Record<typeof marginDecimals[number], string> & {
  unit: FinancialUnit;
  current: Requirements;
  projected_long: Requirements;
  projected_short: Requirements;
  projected_utilization: string | null;
};

export interface StressResult {
  assumptions: StressAssumption;
  mark_paper_quote_per_base: string;
  adverse_pnl_paper_quote: string;
  costs_paper_quote: string;
  margin: ResearchMargin;
  headroom_deterioration: string;
  tier_changed: boolean;
  feasible: boolean;
}

export interface ResearchRiskSnapshot extends NoExecutionAuthority {
  valuation_time: string;
  configuration_fingerprint: string;
  exposure: ResearchExposure;
  margin: ResearchMargin;
  stresses: StressResult[];
}

export interface PaperRiskFrame {
  sequence: number;
  state: 'NORMAL' | 'WIDEN' | 'REDUCE' | 'HALT';
  candidate_quotes: number;
  authorized_quotes: number;
  margin_retired_quotes: boolean;
  projected_headroom: string | null;
  decision_reasons: string[];
}

export interface PaperRiskResult extends NoExecutionAuthority {
  version: typeof paperRiskResultVersion;
  model_fingerprint: string;
  frames: PaperRiskFrame[];
  final_snapshot: ResearchRiskSnapshot | null;
  final_snapshot_status: 'MODELED' | 'RISK_EXPOSURE_INVALID';
  capital_treatment: 'SEPARATE_RESEARCH_BUDGET';
}
