import type { MarketUniverseIdentity, MarketUniverseMetadata } from '../types/marketUniverse';
import type {
  FinancialEvidence, FinancialEvidenceSelection, FinancialObservation, FinancialUnit, ObservedCollateral,
  PaperRiskResult, ResearchRiskModel, ResearchRiskSettings, ResearchMargin, StressAssumption,
} from '../types/marketRisk';
import {
  exposureDecimals, marginDecimals, maxResearchStresses, paperRiskResultVersion, riskEvidenceVersion,
  riskModelVersion, stressFields,
} from '../types/marketRisk';
import { checkedMarketUniverseIdentity, marketUniverseKey, marketUniverseTimestamp } from './marketUniverse';
import { exactDecimal } from './orderView';

const sourceStates = ['SOURCE_OBSERVED', 'STALE', 'UNAVAILABLE', 'UNSUPPORTED'] as const;
const observedModes = ['STRICT_ISOLATED', 'NO_CROSS', 'CROSS_ELIGIBLE', 'ISOLATED_UNSPECIFIED', 'UNKNOWN'] as const;
const researchModes = ['ISOLATED', 'STRICT_ISOLATED', 'NO_CROSS'] as const;
const sourceIssues = ['COLLATERAL_MISSING', 'COLLATERAL_INVALID', 'TOKEN_METADATA_UNAVAILABLE',
  'TOKEN_UNRESOLVED', 'MARGIN_MODE_MISSING', 'MARGIN_MODE_UNSUPPORTED', 'MARGIN_MODE_DEPRECATED_ONLY',
  'MARGIN_TABLE_MISSING', 'MARGIN_TABLE_INVALID', 'MARKET_DELISTED'] as const;
const readinessReasons = ['MARKET_METADATA_UNAVAILABLE', 'MARKET_DELISTED', 'MARKET_METADATA_STALE',
  'COLLATERAL_NOT_ESTABLISHED', 'COLLATERAL_UNVERIFIED', 'MARGIN_POLICY_UNVERIFIED', 'HYPOTHETICAL_ONLY'] as const;
const unsafeFlags = ['execution_eligible', 'exchange_margin_verified', 'risk_ready', 'shared_capital_eligible',
  'cross_market_netting_eligible', 'leverage_eligible', 'verified_collateral', 'verified_settlement'];
const spotNamespace = 'hyperliquid.spot';
const maxTokenIndex = 2 ** 31 - 1;
const symbolPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const tokenPattern = /^0x[0-9a-f]{32}$/;

export function invalidFinancialEvidence(): never {
  throw new Error('Invalid or unsupported PAPER financial evidence.');
}

type Wire = Record<string, unknown>;
function wire(value: unknown): Wire {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) invalidFinancialEvidence();
  return value as Wire;
}

export function checkResearchAuthority(value: Wire) {
  if (('authority' in value && value.authority !== 'NONE') ||
      unsafeFlags.some(flag => flag in value && value[flag] !== false)) invalidFinancialEvidence();
}

function noAuthority(value: Wire) {
  checkResearchAuthority(value);
  if (value.authority !== 'NONE' || value.execution_eligible !== false) invalidFinancialEvidence();
}

const oneOf = <T extends string>(value: unknown, options: readonly T[]): value is T =>
  typeof value === 'string' && options.includes(value as T);
const integer = (value: unknown, min: number, max: number): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max;
const fingerprint = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const boolean = (value: unknown): value is boolean => typeof value === 'boolean';
const matches = (value: unknown, pattern: RegExp): value is string => typeof value === 'string' && pattern.test(value);

function decimal(value: unknown): string {
  if (typeof value !== 'string' || value.length > 160) invalidFinancialEvidence();
  const raw = exactDecimal(value);
  if (raw === '—' || raw.length > 160) invalidFinancialEvidence();
  const plain = raw.replace(/^\+/, '').replace(/^(-?)0+(?=\d)/, '$1');
  const canonical = plain.includes('.') ? plain.replace(/0+$/, '').replace(/\.$/, '') : plain;
  return canonical === '-0' ? '0' : canonical;
}

function compareDecimal(left: string, right: string): number {
  const precision = Math.max(left.split('.')[1]?.length ?? 0, right.split('.')[1]?.length ?? 0);
  function scale(value: string) {
    const [whole, fraction = ''] = value.split('.');
    return BigInt(whole + fraction.padEnd(precision, '0'));
  }
  const a = scale(left), b = scale(right);
  return a < b ? -1 : a > b ? 1 : 0;
}

export function boundedRiskInput(value: unknown, min: string, max: string, exclusiveMin = false): string {
  // Keep inputs as plain decimals and compare exactly. Requirements are calculated by the server.
  if (typeof value !== 'string' || value.length > 32 ||
      !/^-?\d+(?:\.\d{1,12})?$/.test(value)) invalidFinancialEvidence();
  const normalized = decimal(value);
  if (compareDecimal(normalized, min) < (exclusiveMin ? 1 : 0) || compareDecimal(normalized, max) > 0)
    invalidFinancialEvidence();
  return normalized;
}

function checkedIdentity(value: unknown, expected: MarketUniverseIdentity) {
  checkResearchAuthority(wire(value));
  if (marketUniverseKey(checkedMarketUniverseIdentity(value, expected.network)) !== marketUniverseKey(expected))
    invalidFinancialEvidence();
}

function checkMetadata(value: unknown, expected: MarketUniverseMetadata) {
  const meta = wire(value);
  checkedIdentity(meta.identity, expected.identity);
  checkResearchAuthority(meta);
  for (const key of ['contract_version', 'source_coin', 'universe_index', 'sz_decimals', 'listed',
    'metadata_source', 'metadata_status', 'observed_at'] as const) {
    if (meta[key] !== expected[key]) invalidFinancialEvidence();
  }
}

function checkUnit(value: unknown, expected: FinancialUnit) {
  const unit = wire(value);
  checkResearchAuthority(unit);
  if (Object.keys(unit).length !== Object.keys(expected).length ||
      Object.entries(expected).some(([key, field]) => unit[key] !== field)) invalidFinancialEvidence();
}

function paperUnit(network: MarketUniverseIdentity['network']): FinancialUnit {
  return { contract_version: 'phase183a-v1', network, kind: 'HYPOTHETICAL_QUOTE', symbol: 'HYPOTHETICAL_QUOTE',
    asset_namespace: '', asset_reference: null, provenance: 'RESEARCH_ASSUMPTION' };
}

export function collateralUnit(collateral: ObservedCollateral): Extract<FinancialUnit, { kind: 'EXCHANGE_ASSET' }> {
  return { contract_version: 'phase183a-v1', network: collateral.network, kind: 'EXCHANGE_ASSET',
    symbol: collateral.symbol, asset_namespace: collateral.namespace, asset_reference: collateral.token_id,
    provenance: 'DECLARED_UNVERIFIED' };
}

export function checkSourceStatus(value: unknown) {
  if (!oneOf(value, sourceStates)) invalidFinancialEvidence();
  return value;
}

export function checkedFinancialObservation(value: unknown, metadata: MarketUniverseMetadata, metadataFingerprint: string): FinancialObservation {
  const observation = wire(value);
  noAuthority(observation);
  checkMetadata(observation.metadata, metadata);
  if (observation.schema_version !== 'phase183b-v1' || observation.source !== 'HYPERLIQUID_INFO_META' ||
      observation.read_only !== true || observation.account_mode !== 'UNKNOWN' ||
      observation.metadata_fingerprint !== metadataFingerprint || metadata.metadata_status !== 'EXCHANGE_VERIFIED' ||
      observation.price_quote_unit !== null || observation.settlement_unit !== null ||
      !Array.isArray(observation.issues) || observation.issues.length > 5 ||
      observation.issues.some(issue => !oneOf(issue, sourceIssues)) ||
      new Set(observation.issues).size !== observation.issues.length ||
      (observation.collateral_token_index !== null && !integer(observation.collateral_token_index, 0, maxTokenIndex)))
    invalidFinancialEvidence();
  checkSourceStatus(observation.collateral_status);
  checkSourceStatus(observation.margin_status);
  if (observation.collateral !== null) {
    const collateral = wire(observation.collateral);
    checkResearchAuthority(collateral);
    if (collateral.network !== metadata.identity.network || !integer(collateral.index, 0, maxTokenIndex) ||
        collateral.index !== observation.collateral_token_index || !matches(collateral.token_id, tokenPattern) ||
        !matches(collateral.symbol, symbolPattern) || collateral.symbol === 'HYPOTHETICAL_QUOTE' ||
        collateral.namespace !== spotNamespace ||
        (collateral.canonical !== null && !boolean(collateral.canonical)) ||
        observation.collateral_source !== 'HYPERLIQUID_INFO_SPOT_META') invalidFinancialEvidence();
    marketUniverseTimestamp(collateral.observed_at);
  } else if (observation.collateral_source !== null || observation.collateral_status === 'SOURCE_OBSERVED') {
    invalidFinancialEvidence();
  }
  const margin = wire(observation.margin);
  checkResearchAuthority(margin);
  if (!oneOf(margin.mode, observedModes) || (margin.reported_mode !== null &&
      (typeof margin.reported_mode !== 'string' || margin.reported_mode.length > 40)) ||
      (margin.only_isolated !== null && !boolean(margin.only_isolated)) ||
      (margin.table_id !== null && !integer(margin.table_id, 1, maxTokenIndex)) ||
      (margin.reported_max_leverage !== null && !integer(margin.reported_max_leverage, 1, 100)) ||
      !Array.isArray(margin.tiers) || margin.tiers.length > 32) invalidFinancialEvidence();

  let priorBound: string | null = null;
  let priorLeverage = 100;
  for (const item of margin.tiers) {
    const tier = wire(item);
    checkResearchAuthority(tier);
    const lower = decimal(tier.lower_bound);
    if (!integer(tier.max_leverage, 1, priorLeverage) ||
        (priorBound === null ? lower !== '0' || tier.max_leverage !== margin.reported_max_leverage :
          compareDecimal(lower, priorBound) <= 0)) invalidFinancialEvidence();
    priorBound = lower;
    priorLeverage = tier.max_leverage;
  }
  if (margin.tiers.length === 0) {
    if (margin.tier_source !== null || observation.margin_status === 'SOURCE_OBSERVED') invalidFinancialEvidence();
  } else if (!oneOf(margin.tier_source, ['EXPLICIT_TABLE', 'DOCUMENTED_TABLE_ID']) ||
      !integer(margin.table_id, 1, maxTokenIndex) ||
      (margin.table_id < 50 && (margin.tiers.length !== 1 || margin.table_id !== priorLeverage)) ||
      (margin.table_id >= 50 && margin.tier_source === 'DOCUMENTED_TABLE_ID') ||
      (margin.mode === 'UNKNOWN' && observation.margin_status === 'SOURCE_OBSERVED')) invalidFinancialEvidence();
  const checked = observation as unknown as FinancialObservation;
  if (checked.documented_units !== null) {
    const units = wire(checked.documented_units);
    if (!checked.collateral || !canonicalUsdc(checked.collateral) || !metadata.listed ||
        metadata.identity.network !== 'MAINNET' || metadata.identity.instrument_type !== 'CORE_PERP' ||
        !['BTC', 'ETH', 'SOL'].includes(metadata.identity.instrument_name) ||
        units.source !== 'HYPERLIQUID_CONTRACT_SPECIFICATIONS' || units.price_denomination !== 'USDT')
      invalidFinancialEvidence();
    checkUnit(units.pnl_unit, collateralUnit(checked.collateral));
  }
  return checked;
}

function canonicalUsdc(collateral: ObservedCollateral) {
  return collateral.index === 0 && collateral.symbol === 'USDC' && collateral.canonical === true &&
    (collateral.network !== 'MAINNET' || collateral.token_id === '0x6d1e7cde53ba9467b783cb7c530ce054');
}

export function checkedFinancialEvidence(value: unknown, selection: FinancialEvidenceSelection): FinancialEvidence {
  const packet = wire(value);
  const { metadata, metadata_fingerprint: metadataFingerprint, catalog_fingerprint: catalogFingerprint } = selection;
  noAuthority(packet);
  checkedIdentity(packet.identity, metadata.identity);
  if (packet.schema_version !== riskEvidenceVersion || packet.model_version !== riskModelVersion ||
      packet.scope !== 'LOCAL_PAPER_ONLY' || packet.read_only !== true ||
      packet.catalog_fingerprint !== catalogFingerprint || packet.metadata_fingerprint !== metadataFingerprint ||
      !Array.isArray(packet.source_margin_modes) || packet.source_margin_modes.length > 2) invalidFinancialEvidence();
  const evaluated = marketUniverseTimestamp(packet.evaluated_at);
  const deadline = marketUniverseTimestamp(packet.valid_until);
  const marketTime = marketUniverseTimestamp(metadata.observed_at);
  const status = checkSourceStatus(packet.status);
  const observation = packet.observation === null ? null :
    checkedFinancialObservation(packet.observation, metadata, metadataFingerprint);
  const spotTime = observation?.collateral ? marketUniverseTimestamp(observation.collateral.observed_at) : marketTime;
  const oldest = marketTime < spotTime ? marketTime : spotTime;
  if (marketTime > evaluated || deadline > oldest + BigInt(selection.max_age_seconds) * 1_000_000n ||
      (observation ? !fingerprint(packet.source_fingerprint) : packet.source_fingerprint !== null))
    invalidFinancialEvidence();
  const sourceStatuses = [observation?.collateral_status, observation?.margin_status];
  const stale = evaluated >= deadline || spotTime > evaluated || sourceStatuses.includes('STALE');
  const expectedStatus = !metadata.listed ? 'UNSUPPORTED' : stale ? 'STALE' :
    sourceStatuses.includes('UNSUPPORTED') ? 'UNSUPPORTED' :
    !observation || sourceStatuses.includes('UNAVAILABLE') ? 'UNAVAILABLE' : 'SOURCE_OBSERVED';
  let reason = null;
  if (!metadata.listed) reason = 'RISK_SOURCE_UNSUPPORTED';
  else if (expectedStatus === 'STALE') reason = 'RISK_SOURCE_STALE';
  else if (!observation || observation.collateral_status === 'UNAVAILABLE') reason = 'RISK_SOURCE_UNAVAILABLE';
  else if (observation.margin.mode === 'UNKNOWN' || observation.margin.mode === 'ISOLATED_UNSPECIFIED')
    reason = 'RISK_MARGIN_MODE_UNSUPPORTED';
  else if (expectedStatus === 'UNAVAILABLE') reason = 'RISK_SOURCE_UNAVAILABLE';
  else if (expectedStatus !== 'SOURCE_OBSERVED' || !observation.collateral ||
           (observation.margin.tiers.length > 1 &&
            (metadata.identity.instrument_type !== 'CORE_PERP' || !canonicalUsdc(observation.collateral))))
    reason = 'RISK_SOURCE_UNSUPPORTED';
  const mode = observation?.margin.mode;
  const modes = reason ? [] : mode === 'STRICT_ISOLATED' || mode === 'NO_CROSS' ? ['ISOLATED', mode] : ['ISOLATED'];
  if (status !== expectedStatus || packet.source_constraint_reason !== reason ||
      packet.source_margin_modes.length !== modes.length ||
      modes.some((entry, index) => (packet.source_margin_modes as unknown[])[index] !== entry))
    invalidFinancialEvidence();
  return packet as unknown as FinancialEvidence;
}

export function financialEvidenceIsCurrent(evidence: FinancialEvidence | undefined, now = Date.now()) {
  return evidence !== undefined && evidence.status !== 'STALE' &&
    Date.parse(evidence.evaluated_at) <= now && now < Date.parse(evidence.valid_until);
}

function sameOptionalDecimal(value: unknown, expected: string | null) {
  return expected === null ? value === null : decimal(value) === decimal(expected);
}

function sameStress(value: unknown, expected: StressAssumption) {
  const stress = wire(value);
  checkResearchAuthority(stress);
  if (stress.name !== expected.name || stressFields.some(field => decimal(stress[field]) !== decimal(expected[field])))
    invalidFinancialEvidence();
}

export function checkRiskSettings(value: unknown, expected: ResearchRiskSettings) {
  const settings = wire(value);
  checkResearchAuthority(settings);
  if (settings.mode !== expected.mode || !oneOf(settings.margin_mode, researchModes) ||
      settings.margin_mode !== expected.margin_mode ||
      decimal(settings.capital_paper_quote) !== decimal(expected.capital_paper_quote) ||
      !sameOptionalDecimal(settings.initial_margin_fraction, expected.initial_margin_fraction) ||
      !sameOptionalDecimal(settings.maintenance_margin_fraction, expected.maintenance_margin_fraction) ||
      !sameOptionalDecimal(settings.max_leverage, expected.max_leverage) ||
      !sameOptionalDecimal(settings.leverage, expected.leverage) ||
      !Array.isArray(settings.stresses) || settings.stresses.length > maxResearchStresses ||
      settings.stresses.length !== expected.stresses.length) invalidFinancialEvidence();
  settings.stresses.forEach((item, index) => sameStress(item, expected.stresses[index]));
  if (!expected.valuation) {
    if (settings.valuation !== null) invalidFinancialEvidence();
  } else {
    const valuation = wire(settings.valuation);
    checkResearchAuthority(valuation);
    if (valuation.provenance !== 'FIXED_HYPOTHETICAL_SCENARIO_RATE' ||
        decimal(valuation.collateral_per_paper_quote) !== decimal(expected.valuation.collateral_per_paper_quote))
      invalidFinancialEvidence();
    checkUnit(valuation.collateral_unit, expected.valuation.collateral_unit);
  }
}

export function checkedResearchModel(value: unknown, settings: ResearchRiskSettings, metadata: MarketUniverseMetadata,
    metadataFingerprint: string, evaluatedAt: string, validUntil: string): ResearchRiskModel {
  const model = wire(value);
  noAuthority(model);
  if (model.version !== riskModelVersion) invalidFinancialEvidence();
  checkRiskSettings(model.settings, settings);
  const source = model.source === null ? null : checkedFinancialObservation(model.source, metadata, metadataFingerprint);
  if (source ? !fingerprint(model.source_fingerprint) : model.source_fingerprint !== null) invalidFinancialEvidence();
  if (source?.collateral_status === 'STALE' || source?.margin_status === 'STALE') invalidFinancialEvidence();
  const evaluated = marketUniverseTimestamp(evaluatedAt);
  const deadline = marketUniverseTimestamp(validUntil);
  if (source?.collateral && (marketUniverseTimestamp(source.collateral.observed_at) > evaluated ||
      deadline - marketUniverseTimestamp(source.collateral.observed_at) > 86_400_000_000n)) invalidFinancialEvidence();
  const paper = paperUnit(metadata.identity.network);
  const collateral = source?.collateral ? collateralUnit(source.collateral) : null;
  const hypothetical = settings.mode === 'HYPOTHETICAL';
  if (hypothetical) {
    if (model.formula !== 'HYPOTHETICAL_LINEAR') invalidFinancialEvidence();
    checkUnit(model.margin_unit, paper);
  } else {
    if (model.formula !== 'DOCUMENTED_HYPERLIQUID_TIERS' || !collateral || !settings.valuation ||
        !source?.margin.tiers.length || source.margin_status !== 'SOURCE_OBSERVED' ||
        source.collateral_status !== 'SOURCE_OBSERVED' ||
        (source.margin.mode === 'UNKNOWN' || source.margin.mode === 'ISOLATED_UNSPECIFIED') ||
        (settings.margin_mode !== 'ISOLATED' && settings.margin_mode !== source.margin.mode) ||
        (source.margin.tiers.length > 1 &&
          (metadata.identity.instrument_type !== 'CORE_PERP' || !canonicalUsdc(source.collateral!))))
      invalidFinancialEvidence();
    checkUnit(settings.valuation.collateral_unit, collateral);
    checkUnit(model.margin_unit, collateral);
  }

  const declaration = wire(model.declaration);
  noAuthority(declaration);
  if (declaration.contract_version !== 'phase183a-v1' || declaration.liquidation_price !== null ||
      declaration.account_mode !== 'UNKNOWN' || declaration.exchange_margin_verified !== false ||
      declaration.shared_capital_eligible !== false || declaration.cross_market_netting_eligible !== false ||
      declaration.margin_mode !== settings.margin_mode || declaration.policy_evidence !== (hypothetical ? 'HYPOTHETICAL' : 'UNVERIFIED') ||
      !sameOptionalDecimal(declaration.initial_margin_fraction, settings.initial_margin_fraction) ||
      !sameOptionalDecimal(declaration.maintenance_margin_fraction, settings.maintenance_margin_fraction) ||
      !sameOptionalDecimal(declaration.modeled_max_leverage, settings.max_leverage)) invalidFinancialEvidence();
  const units = wire(declaration.financial_units);
  checkResearchAuthority(units);
  checkMetadata(units.metadata, metadata);
  if (units.contract_version !== 'phase183a-v1' || units.authority !== 'NONE' || units.read_only !== true ||
      units.metadata_fingerprint !== metadataFingerprint || units.price_quote_unit !== null || units.settlement_unit !== null ||
      units.verified_collateral !== false || units.verified_settlement !== false || units.unit_evidence !== 'DECLARED_UNVERIFIED')
    invalidFinancialEvidence();
  checkUnit(units.paper_accounting_unit, paper);
  if (collateral) checkUnit(units.collateral_unit, collateral);
  else if (units.collateral_unit !== null) invalidFinancialEvidence();

  const readiness = wire(model.readiness);
  noAuthority(readiness);
  checkedIdentity(readiness.identity, metadata.identity);
  if (readiness.contract_version !== 'phase183a-v1' || readiness.read_only !== true || readiness.status !== 'BLOCKED' ||
      readiness.scope !== 'SINGLE_MARKET_RESEARCH_ONLY' || readiness.metadata_fingerprint !== metadataFingerprint ||
      readiness.risk_ready !== false || readiness.exchange_margin_verified !== false || readiness.leverage_eligible !== false ||
      readiness.shared_capital_eligible !== false || readiness.cross_market_netting_eligible !== false ||
      !fingerprint(readiness.collateral_fingerprint) || !fingerprint(readiness.margin_policy_fingerprint) ||
      marketUniverseTimestamp(readiness.evaluated_at) !== evaluated || !oneOf(readiness.reason, readinessReasons))
    invalidFinancialEvidence();
  return model as unknown as ResearchRiskModel;
}

function checkMargin(value: unknown, model: ResearchRiskModel) {
  const margin = wire(value);
  checkResearchAuthority(margin);
  checkUnit(margin.unit, model.margin_unit);
  for (const field of marginDecimals) decimal(margin[field]);
  if (margin.projected_utilization !== null) decimal(margin.projected_utilization);
  for (const field of ['current', 'projected_long', 'projected_short']) {
    const requirements = wire(margin[field]);
    checkResearchAuthority(requirements);
    if (decimal(requirements.initial).startsWith('-') || decimal(requirements.maintenance).startsWith('-') ||
        !boolean(requirements.leverage_supported)) invalidFinancialEvidence();
    if (requirements.margin_leverage !== null && compareDecimal(decimal(requirements.margin_leverage), '1') < 0)
      invalidFinancialEvidence();
    if (model.settings.mode === 'SOURCE_CONSTRAINED') {
      if (!model.source?.margin.tiers.some(t => decimal(t.lower_bound) === decimal(requirements.tier_lower_bound) &&
          t.max_leverage === requirements.source_max_leverage) || requirements.margin_leverage === null)
        invalidFinancialEvidence();
    } else if (requirements.tier_lower_bound !== null || requirements.source_max_leverage !== null ||
        requirements.margin_leverage !== null) invalidFinancialEvidence();
  }
  return margin as unknown as ResearchMargin;
}

export function checkedPaperRiskResult(value: unknown, model: ResearchRiskModel, identity: MarketUniverseIdentity,
    modelFingerprint: string, frames: number, finalPosition: string): PaperRiskResult {
  const risk = wire(value);
  noAuthority(risk);
  if (risk.version !== paperRiskResultVersion || risk.model_fingerprint !== modelFingerprint ||
      risk.capital_treatment !== 'SEPARATE_RESEARCH_BUDGET' || !Array.isArray(risk.frames) ||
      risk.frames.length !== frames || frames < 2 || frames > 120) invalidFinancialEvidence();
  for (const [index, item] of risk.frames.entries()) {
    const frame = wire(item);
    checkResearchAuthority(frame);
    if (frame.sequence !== index + 1 || !oneOf(frame.state, ['NORMAL', 'WIDEN', 'REDUCE', 'HALT']) ||
        !integer(frame.candidate_quotes, 0, 64) || !integer(frame.authorized_quotes, 0, frame.candidate_quotes) ||
        !boolean(frame.margin_retired_quotes) || (frame.margin_retired_quotes && frame.authorized_quotes !== 0) ||
        (frame.state === 'HALT' && frame.authorized_quotes !== 0) ||
        !Array.isArray(frame.decision_reasons) || frame.decision_reasons.length > 16 ||
        frame.decision_reasons.some(reason => typeof reason !== 'string' || reason.length > 180)) invalidFinancialEvidence();
    if (frame.projected_headroom !== null) decimal(frame.projected_headroom);
  }
  if (risk.final_snapshot_status === 'RISK_EXPOSURE_INVALID' && risk.final_snapshot === null)
    return risk as unknown as PaperRiskResult;
  if (risk.final_snapshot_status !== 'MODELED') invalidFinancialEvidence();
  const snapshot = wire(risk.final_snapshot);
  noAuthority(snapshot);
  marketUniverseTimestamp(snapshot.valuation_time);
  if (snapshot.configuration_fingerprint !== modelFingerprint || !Array.isArray(snapshot.stresses) ||
      snapshot.stresses.length !== model.settings.stresses.length || snapshot.stresses.length > maxResearchStresses)
    invalidFinancialEvidence();
  const exposure = wire(snapshot.exposure);
  checkResearchAuthority(exposure);
  checkedIdentity(exposure.base_instrument, identity);
  checkUnit(exposure.quote_unit, paperUnit(identity.network));
  for (const field of exposureDecimals) decimal(exposure[field]);
  if (decimal(exposure.signed_base) !== decimal(finalPosition)) invalidFinancialEvidence();
  checkMargin(snapshot.margin, model);
  for (const [index, item] of snapshot.stresses.entries()) {
    const stress = wire(item);
    checkResearchAuthority(stress);
    sameStress(stress.assumptions, model.settings.stresses[index]);
    checkMargin(stress.margin, model);
    for (const field of ['mark_paper_quote_per_base', 'adverse_pnl_paper_quote', 'costs_paper_quote', 'headroom_deterioration'])
      decimal(stress[field]);
    if (!boolean(stress.feasible) || !boolean(stress.tier_changed)) invalidFinancialEvidence();
  }
  return risk as unknown as PaperRiskResult;
}

export function buildRiskSettings(mode: ResearchRiskSettings['mode'], marginMode: ResearchRiskSettings['margin_mode'],
    capital: string, initial: string, maintenance: string, leverage: string, ceiling: string, rate: string,
    stresses: StressAssumption[], evidence?: FinancialEvidence): ResearchRiskSettings {
  const names = new Set<string>();
  const checkedStresses = stresses.map(stress => {
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(stress.name) || names.has(stress.name))
      throw new Error('Give each stress a unique name starting with a letter. Use up to 32 letters, digits, hyphens or underscores.');
    names.add(stress.name);
    const checked = { ...stress };
    for (const field of stressFields) {
      try {
        checked[field] = field === 'price_shock_bps'
          ? boundedRiskInput(stress[field], '-10000', '100000', true)
          : boundedRiskInput(stress[field], '0', '10000');
      } catch {
        throw new Error('Check stress bounds. Price shock must be above −10,000 and at most 100,000 bps. Other stresses use 0–10,000 bps.');
      }
    }
    return checked;
  });
  if (checkedStresses.length > maxResearchStresses) invalidFinancialEvidence();
  const input = (value: string, min: string, max: string, label: string, exclusiveMin = false) => {
    try { return boundedRiskInput(value.trim(), min, max, exclusiveMin); }
    catch {
      throw new Error(`${label} must be ${exclusiveMin ? 'greater than' : 'at least'} ${min} and at most ${max}, with up to 12 decimal places.`);
    }
  };
  const settings: ResearchRiskSettings = {
    mode, margin_mode: marginMode, capital_paper_quote: input(capital, '0', '1000000000', 'Research capital', true),
    initial_margin_fraction: null, maintenance_margin_fraction: null, max_leverage: null, leverage: null,
    valuation: null, stresses: checkedStresses,
  };
  const observed = financialEvidenceIsCurrent(evidence) ? evidence?.observation : null;
  if (mode === 'HYPOTHETICAL') {
    settings.initial_margin_fraction = input(initial, '0', '1', 'Initial margin fraction', true);
    settings.maintenance_margin_fraction = input(maintenance, '0', '1', 'Maintenance margin fraction', true);
    if (compareDecimal(settings.maintenance_margin_fraction, settings.initial_margin_fraction) > 0)
      throw new Error('Maintenance margin fraction must be at most the initial margin fraction.');
    if (leverage.trim()) {
      settings.leverage = input(leverage, '1', '100', 'Research leverage');
      settings.max_leverage = input(ceiling, '1', '100', 'Declared leverage ceiling');
      if (compareDecimal(settings.leverage, settings.max_leverage) > 0)
        throw new Error('Research leverage exceeds the declared ceiling.');
      const observedCap = observed?.margin.tiers.at(-1)?.max_leverage;
      if (observedCap !== undefined && compareDecimal(settings.leverage, String(observedCap)) > 0)
        throw new Error(`Research leverage exceeds the observed conservative ceiling of ${observedCap}×.`);
      const scale = (value: string) => BigInt(value.replace('.', '') + '0'.repeat(12 - (value.split('.')[1]?.length ?? 0)));
      if (scale(settings.leverage) * scale(settings.initial_margin_fraction) < 10n ** 24n)
        throw new Error('The initial margin fraction must be at least the reciprocal of research leverage.');
    }
    return settings;
  }
  if (!observed?.collateral || !evidence?.source_margin_modes.includes(marginMode))
    throw new Error('Source-constrained research requires current, supported collateral and margin evidence.');
  settings.leverage = input(leverage, '1', String(observed.margin.tiers[0].max_leverage), 'Research leverage');
  if (settings.leverage.includes('.')) throw new Error('Source-constrained leverage must be a whole number.');
  settings.valuation = { collateral_unit: collateralUnit(observed.collateral),
    collateral_per_paper_quote: input(rate, '0', '1000000', 'Scenario valuation', true),
    provenance: 'FIXED_HYPOTHETICAL_SCENARIO_RATE' };
  return settings;
}
