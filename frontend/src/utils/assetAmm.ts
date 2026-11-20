import { assetAmmVersion, assetDecimalFields, assetFamilies, assetModels } from '../types/assetAmm';
import type { AssetControlInputs, AssetDecimalField, AssetPolicyPreview, AssetPolicyPreviewRequest } from '../types/assetAmm';
import type { FinancialEvidenceSelection } from '../types/marketRisk';
import { marketUniverseTimestamp } from './marketUniverse';
import { exactDecimal } from './orderView';
import { canonicalResearchJson, researchFingerprint } from './researchFingerprint';

export const assetPreviewByteLimit = 16_384;
export const assetDecimalKeys = Object.keys(assetDecimalFields) as AssetDecimalField[];
const scale = 10n ** 60n;
const paperQuantum = 10n ** 48n;
const authority = {
  contract_version: assetAmmVersion, authority: 'NONE', read_only: true,
  risk_ready: false, affects_quotes: false, can_override_risk: false, execution_eligible: false,
};

function invalid(): never {
  throw new Error('Invalid or unsupported asset AMM research evidence.');
}

function fields(value: unknown, fixed: Record<string, unknown>, variable: readonly string[]) {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) invalid();
  const wire = value as Record<string, unknown>;
  if (Object.keys(wire).length !== Object.keys(fixed).length + variable.length ||
      Object.entries(fixed).some(([key, expected]) => wire[key] !== expected) ||
      variable.some(key => !Object.hasOwn(wire, key))) invalid();
  return wire;
}

function scaled(value: unknown): bigint {
  if (typeof value !== 'string' || value.length > 80) invalid();
  const match = /^-?\d+(?:\.(\d+))?(?:[eE]([+-]?\d{1,2}))?$/.exec(value);
  if (!match) invalid();
  const exponent = Number(match[2] ?? 0) - (match[1]?.length ?? 0);
  if (exponent < -60 || exponent > 30) invalid();
  const [whole, fraction = ''] = exactDecimal(value).split('.');
  return BigInt(whole + fraction.padEnd(60, '0'));
}

function bounded(value: unknown, min: number, max: number, positive = false) {
  const amount = scaled(value);
  if (amount < BigInt(min) * scale || amount > BigInt(max) * scale || (positive && amount === 0n)) invalid();
  return amount;
}

export function assetControlInput(key: keyof AssetControlInputs, value: string): string | number {
  if (key === 'levels_per_side') {
    if (!/^(?:[1-9]|[1-4][0-9]|50)$/.test(value)) throw new Error('Levels per side must be a whole number from 1 to 50.');
    return Number(value);
  }
  if (key === 'amm_model') {
    if (!Object.hasOwn(assetModels, value)) invalid();
    return value;
  }
  const [label, min, max, positive] = assetDecimalFields[key];
  try {
    bounded(value, min, max, positive);
  } catch {
    throw new Error(`${label} must be an exact decimal ${positive ? 'greater than' : 'at least'} ${min} and at most ${max}.`);
  }
  return value;
}

export function assetMinimumNotional(value: string): string {
  try {
    if (bounded(value, 0, 2000, true) % paperQuantum !== 0n) invalid();
  } catch {
    throw new Error('Minimum research order notional must be greater than 0 and at most 2000, with up to 12 decimal places.');
  }
  return value;
}

export function assetReferenceIsValid(value: string): boolean {
  try {
    return bounded(value, 0, 10_000_000, true) % paperQuantum === 0n;
  } catch {
    return false;
  }
}

export async function checkedAssetPolicyPreview(
  value: unknown, request: AssetPolicyPreviewRequest, selection: FinancialEvidenceSelection, now = Date.now(),
): Promise<AssetPolicyPreview> {
  const { policy: rawPolicy, assessment: rawAssessment } = fields(value, {}, ['policy', 'assessment']);
  const policy = fields(rawPolicy, {
    ...authority, execution_mode: 'PAPER', can_authorize_paper: false,
    reference_provenance: 'USER_SUPPLIED_SYNTHETIC', source_provenance: 'DECLARED_HYPOTHETICAL_POLICY',
    research_scope: 'SINGLE_MARKET_RESEARCH_ONLY', catalog_fingerprint: selection.catalog_fingerprint,
    metadata_fingerprint: selection.metadata_fingerprint,
    advisory_snapshot_fingerprint: request.advisory_snapshot_fingerprint ?? null,
  }, ['metadata', 'classification', 'controls', 'hypothetical_accounting_unit', 'simulated_reference_price',
    'declared_at', 'research_risk_fingerprint']);
  const riskFingerprint = policy.research_risk_fingerprint;
  if (request.research_risk ? typeof riskFingerprint !== 'string' || !/^[a-f0-9]{64}$/.test(riskFingerprint) :
      riskFingerprint !== null) invalid();
  const metadata = selection.metadata;
  if (request.catalog_fingerprint !== selection.catalog_fingerprint || !metadata.listed ||
      metadata.metadata_status !== 'EXCHANGE_VERIFIED' ||
      canonicalResearchJson(request.identity) !== canonicalResearchJson(metadata.identity) ||
      canonicalResearchJson(policy.metadata) !== canonicalResearchJson(metadata) ||
      await researchFingerprint(metadata) !== selection.metadata_fingerprint ||
      bounded(policy.simulated_reference_price, 0, 10_000_000, true) !== scaled(request.simulated_reference_price)) invalid();

  const declared = marketUniverseTimestamp(policy.declared_at);
  const observed = marketUniverseTimestamp(metadata.observed_at);
  if (declared < observed || declared > BigInt(now) * 1000n + 999n ||
      declared >= observed + BigInt(selection.max_age_seconds) * 1_000_000n) invalid();
  if (!Object.hasOwn(assetFamilies, request.family)) invalid();
  fields(policy.classification, {
    contract_version: assetAmmVersion, provenance: 'OPERATOR_DECLARED_RESEARCH', family: request.family,
    exchange_class_verified: false, tradability_verified: false,
  }, []);
  fields(policy.hypothetical_accounting_unit, {
    contract_version: 'phase183a-v1', network: request.identity.network, kind: 'HYPOTHETICAL_QUOTE',
    symbol: 'HYPOTHETICAL_QUOTE', asset_namespace: '', asset_reference: null, provenance: 'RESEARCH_ASSUMPTION',
  }, []);

  const controls = fields(policy.controls, {
    contract_version: assetAmmVersion, provenance: 'HYPOTHETICAL_RESEARCH_SETTINGS',
    price_precision_policy: 'REUSE_GENERALIZED_PRECISION', size_precision_policy: 'REUSE_DISCOVERED_SZ_DECIMALS',
  }, ['amm_model', 'levels_per_side', ...assetDecimalKeys]);
  if (typeof controls.amm_model !== 'string' || !Object.hasOwn(assetModels, controls.amm_model) ||
      typeof controls.levels_per_side !== 'number' || !Number.isInteger(controls.levels_per_side) ||
      controls.levels_per_side < 1 || controls.levels_per_side > 50) invalid();
  for (const key of assetDecimalKeys) {
    const [, min, max, positive] = assetDecimalFields[key];
    bounded(controls[key], min, max, positive);
  }
  if (scaled(controls.concentration_lower_bps) >= scaled(controls.concentration_upper_bps) ||
      scaled(controls.soft_inventory_limit_base) >= scaled(controls.hard_inventory_limit_base) ||
      scaled(controls.base_order_size) * BigInt(controls.levels_per_side) > scaled(controls.total_liquidity)) invalid();
  for (const [key, override] of Object.entries(request.controls ?? {})) {
    if (Object.hasOwn(assetDecimalFields, key) ? scaled(controls[key]) !== scaled(override) : controls[key] !== override) invalid();
  }
  const assessment = fields(rawAssessment, {
    ...authority, status: 'RESEARCH_DRAFT', reason: 'DISCOVERABLE', evaluated_at: policy.declared_at,
    metadata_fingerprint: selection.metadata_fingerprint, eligible_for_paper: false,
    eligible_for_testnet: false, eligible_for_live: false,
  }, ['identity', 'policy_fingerprint']);
  if (canonicalResearchJson(assessment.identity) !== canonicalResearchJson(request.identity) ||
      assessment.policy_fingerprint !== await researchFingerprint(policy)) invalid();
  return value as AssetPolicyPreview;
}
