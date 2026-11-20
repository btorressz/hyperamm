import type { MarketUniverseIdentity, MarketUniverseMetadata } from './marketUniverse';
import type { FinancialUnit, ResearchRiskSettings } from './marketRisk';
import type { paperProfileVersion } from './generalizedPaper';

export const assetAmmVersion = 'phase185a-v1';
export const assetFamilies = {
  CRYPTO: 'Crypto', EQUITY: 'Equity', INDEX: 'Index', COMMODITY: 'Commodity',
  ENERGY: 'Energy', FX: 'Foreign exchange', RATES: 'Rates', OTHER: 'Other', UNKNOWN: 'Unknown',
} as const;
export const assetModels = { CONSTANT_PRODUCT: 'Constant Product', CONCENTRATED: 'Concentrated Liquidity' } as const;
export type AssetFamily = keyof typeof assetFamilies;
export type AssetAmmModel = keyof typeof assetModels;

export const assetDecimalFields = {
  max_distance_bps: ['Maximum quote distance (bps)', 0, 2500, true],
  base_order_size: ['Base order size (base units)', 0, 1_000_000_000, true],
  total_liquidity: ['Total research liquidity per side (base units)', 0, 1_000_000_000, true],
  virtual_base_reserve: ['Virtual base reserve (base units)', 0, 1_000_000_000, true],
  virtual_quote_reserve: ['Virtual quote reserve (hypothetical quote units)', 0, 1_000_000_000_000, true],
  concentration_factor: ['Concentration factor (dimensionless)', 0, 1000],
  concentration_lower_bps: ['Lower concentration bound (bps)', 0, 2500],
  concentration_upper_bps: ['Upper concentration bound (bps)', 0, 2500, true],
  target_inventory_base: ['Target inventory (base units)', -1_000_000_000, 1_000_000_000],
  soft_inventory_limit_base: ['Soft inventory limit (base units)', 0, 1_000_000_000, true],
  hard_inventory_limit_base: ['Hard inventory limit (base units)', 0, 1_000_000_000, true],
  max_inventory_price_skew_bps: ['Maximum inventory price skew (bps)', 0, 500],
  volatility_spread_strength: ['Volatility spread strength (dimensionless)', 0, 10],
  volatility_size_strength: ['Volatility size strength (dimensionless)', 0, 1],
  max_funding_reference_shift_bps: ['Maximum funding reference shift (bps)', 0, 100],
} as const;
export type AssetDecimalField = keyof typeof assetDecimalFields;
type Versioned = { contract_version: typeof assetAmmVersion };

export interface AssetResearchClassification extends Versioned {
  family: AssetFamily;
  provenance: 'OPERATOR_DECLARED_RESEARCH';
  exchange_class_verified: false;
  tradability_verified: false;
}

export type AssetAmmResearchControls = Versioned & Record<AssetDecimalField, string> & {
  amm_model: AssetAmmModel;
  levels_per_side: number;
  price_precision_policy: 'REUSE_GENERALIZED_PRECISION';
  size_precision_policy: 'REUSE_DISCOVERED_SZ_DECIMALS';
  provenance: 'HYPOTHETICAL_RESEARCH_SETTINGS';
};

interface ResearchAuthority {
  risk_ready: false;
  affects_quotes: false;
  can_override_risk: false;
  execution_eligible: false;
  read_only: true;
  authority: 'NONE';
}

export interface AssetAmmResearchPolicy extends Versioned, ResearchAuthority {
  metadata: MarketUniverseMetadata;
  metadata_fingerprint: string;
  classification: AssetResearchClassification;
  controls: AssetAmmResearchControls;
  hypothetical_accounting_unit: Extract<FinancialUnit, { kind: 'HYPOTHETICAL_QUOTE' }>;
  simulated_reference_price: string;
  declared_at: string;
  catalog_fingerprint: string;
  research_risk_fingerprint: string | null;
  advisory_snapshot_fingerprint: string | null;
  reference_provenance: 'USER_SUPPLIED_SYNTHETIC';
  source_provenance: 'DECLARED_HYPOTHETICAL_POLICY';
  research_scope: 'SINGLE_MARKET_RESEARCH_ONLY';
  execution_mode: 'PAPER';
  can_authorize_paper: false;
}

export type AssetAmmPolicyAssessment = Versioned & ResearchAuthority & {
  identity: MarketUniverseIdentity;
  metadata_fingerprint: string;
  policy_fingerprint: string;
  evaluated_at: string;
  eligible_for_paper: false;
  eligible_for_testnet: false;
  eligible_for_live: false;
} & (
  { status: 'RESEARCH_DRAFT'; reason: 'DISCOVERABLE' } |
  { status: 'BLOCKED'; reason: 'NOT_LISTED' | 'UNVERIFIED_METADATA' | 'MISSING_METADATA' |
      'METADATA_ERROR' | 'FUTURE_TIMESTAMP' | 'STALE_METADATA' }
);

export type AssetControlInputs = Pick<AssetAmmResearchControls, AssetDecimalField | 'amm_model' | 'levels_per_side'>;

export interface AssetPolicyPreviewRequest {
  profile_version: typeof paperProfileVersion;
  identity: MarketUniverseIdentity;
  catalog_fingerprint: string;
  simulated_reference_price: string;
  minimum_order_notional: string;
  family: AssetFamily;
  controls?: Partial<AssetControlInputs>;
  research_risk?: ResearchRiskSettings;
  advisory_snapshot_fingerprint?: string;
}

export interface AssetPolicyPreview {
  policy: AssetAmmResearchPolicy;
  assessment: AssetAmmPolicyAssessment;
}
