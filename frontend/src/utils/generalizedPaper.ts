import type { GeneralizedPaperResult, PaperAdmission, PaperBinding, PaperProposal, PaperReason } from '../types/generalizedPaper';
import { paperEvidenceBoundary, paperProfileVersion, paperReasons } from '../types/generalizedPaper';
import { checkedMarketUniverseIdentity, marketUniverseKey, marketUniverseTimestamp } from './marketUniverse';
import { exactDecimal } from './orderView';
import {
  checkedFinancialObservation, checkedPaperRiskResult, checkedResearchModel, checkResearchAuthority,
  checkRiskSettings, checkSourceStatus,
} from './marketRisk';

const maxFrames = 120;
export const paperResponseByteLimit = 2_000_000;

const object = (x: unknown): x is Record<string, unknown> =>
  typeof x === 'object' && x !== null && !Array.isArray(x);
const integer = (x: unknown, min: number, max: number): x is number =>
  typeof x === 'number' && Number.isInteger(x) && x >= min && x <= max;
const digest = (x: unknown) => typeof x === 'string' && x.length === 64 && /^[a-f0-9]+$/.test(x);

function malformed(): never {
  throw new Error('Invalid or unsupported generalized PAPER evidence.');
}

function decimal(value: unknown): string {
  if (typeof value !== 'string' || value.length > 128) malformed();
  const raw = exactDecimal(value);
  if (raw === '—' || !Number.isFinite(Number(raw))) malformed();
  const plain = raw.replace(/^\+/, '').replace(/^(-?)0+(?=\d)/, '$1');
  if (Number(plain) === 0) return '0';
  return plain.includes('.') ? plain.replace(/0+$/, '').replace(/\.$/, '') : plain;
}

function sameDecimal(wire: unknown, expected: string) {
  return decimal(wire) === decimal(expected);
}

function sameEconomics(value: unknown, expected: PaperProposal['economics']) {
  return object(value) && value.model === 'HYPOTHETICAL_LINEAR' &&
    sameDecimal(value.maker_fee_bps, expected.maker_fee_bps ?? '0') &&
    sameDecimal(value.taker_fee_bps, expected.taker_fee_bps ?? '0') &&
    value.funding_interval_seconds === (expected.funding_interval_seconds ?? null);
}

function matchesIdentity(value: unknown, proposal: PaperProposal) {
  return marketUniverseKey(checkedMarketUniverseIdentity(value, proposal.identity.network)) === marketUniverseKey(proposal.identity);
}

function matchesResearchBoundary(value: unknown) {
  return object(value) && Object.keys(value).length === Object.keys(paperEvidenceBoundary).length &&
    Object.entries(paperEvidenceBoundary).every(([key, expected]) => value[key] === expected);
}

export function checkedPaperAdmission(value: unknown, proposal: PaperProposal): PaperAdmission {
  if (!object(value) || value.profile_version !== paperProfileVersion || value.scope !== 'LOCAL_PAPER_ONLY' ||
      value.authority !== 'NONE' || value.execution_eligible !== false || typeof value.reason !== 'string' ||
      !Object.hasOwn(paperReasons, value.reason) || typeof value.explanation !== 'string' ||
      value.explanation.length < 1 || value.explanation.length > 180 ||
      !Array.isArray(value.checks) || !Array.isArray(value.limitations) || value.limitations.length !== 5 ||
      value.limitations.some(item => typeof item !== 'string' || item.length > 180)) malformed();
  checkResearchAuthority(value);

  const reason = value.reason as PaperReason;
  const eligible = reason === 'ADMITTED';
  const status = eligible ? 'ELIGIBLE' :
    ['METADATA_STALE', 'METADATA_UNAVAILABLE', 'RISK_SOURCE_STALE', 'RISK_SOURCE_UNAVAILABLE'].includes(reason)
      ? 'UNAVAILABLE' : 'REJECTED';
  if (value.status !== status || value.checks.length !== (eligible ? 0 : 1) ||
      (!eligible && value.checks[0] !== paperReasons[reason]) ||
      (value.identity === null ? reason !== 'CONFIGURATION_INVALID' : !matchesIdentity(value.identity, proposal))) malformed();
  const evaluated = marketUniverseTimestamp(value.evaluated_at);
  const profile = value.profile;
  const binding = value.binding;

  if (profile !== null) {
    if (!object(profile) || profile.profile_version !== paperProfileVersion || profile.authority !== 'NONE' ||
        profile.execution_eligible !== false || profile.paper_eligibility !== 'REQUIRES_ADMISSION' ||
        profile.reference_source !== 'USER_SUPPLIED_SYNTHETIC' || profile.model_compatibility !== 'HYPOTHETICAL_LINEAR_ONLY' ||
        !matchesResearchBoundary(profile.evidence_boundary) ||
        !Array.isArray(profile.limitations) || profile.limitations.length !== value.limitations.length ||
        profile.limitations.some((limit, index) => limit !== (value.limitations as string[])[index]) ||
        !digest(profile.profile_fingerprint) || !digest(profile.metadata_fingerprint) ||
        profile.stable_key !== marketUniverseKey(proposal.identity) ||
        !sameDecimal(profile.simulated_reference_price, proposal.simulated_reference_price) ||
        !sameDecimal(profile.synthetic_top_depth_quote, proposal.synthetic_top_depth_quote ?? '18000') ||
        !sameEconomics(profile.economics, proposal.economics) || !object(profile.metadata) || !object(profile.discovery)) malformed();
    checkResearchAuthority(profile);
    const metadata = profile.metadata;
    checkResearchAuthority(metadata);
    const { dex, instrument_name } = proposal.identity;
    const coin = dex ? `${dex}:${instrument_name}` : instrument_name;
    if (metadata.contract_version !== 'phase180b-v2' || !matchesIdentity(metadata.identity, proposal) ||
        profile.exchange_coin !== coin || metadata.source_coin !== coin ||
        metadata.metadata_source !== (dex ? 'OFFICIAL_SDK_HIP3_META' : 'OFFICIAL_SDK_CORE_META') ||
        (metadata.metadata_status !== 'EXCHANGE_VERIFIED' && metadata.metadata_status !== 'STALE') ||
        typeof metadata.listed !== 'boolean' || !integer(metadata.universe_index, 0, 9999) ||
        !integer(metadata.sz_decimals, 0, 6)) malformed();
    const observed = marketUniverseTimestamp(metadata.observed_at);
    const discovery = profile.discovery;
    checkResearchAuthority(discovery);
    if (discovery.contract_version !== 'phase180b-v2' || !matchesIdentity(discovery.identity, proposal) ||
        discovery.metadata_fingerprint !== profile.metadata_fingerprint || discovery.read_only !== true ||
        discovery.authority !== 'NONE' || discovery.paper_research_eligible !== false || discovery.execution_eligible !== false ||
        typeof discovery.reason !== 'string' || !['DISCOVERABLE', 'NOT_LISTED', 'FUTURE_TIMESTAMP', 'STALE_METADATA'].includes(discovery.reason) ||
        discovery.discovery_eligible !== (discovery.reason === 'DISCOVERABLE')) malformed();
    const discovered = marketUniverseTimestamp(discovery.evaluated_at);
    if (eligible) {
      const expires = marketUniverseTimestamp(value.valid_until);
      if (metadata.metadata_status !== 'EXCHANGE_VERIFIED' || metadata.listed !== true ||
          discovered !== evaluated || discovery.discovery_eligible !== true || observed > evaluated || evaluated >= expires || expires - observed > 86_400_000_000n ||
          !object(binding) || binding.metadata_fingerprint !== profile.metadata_fingerprint ||
          binding.profile_fingerprint !== profile.profile_fingerprint || !digest(binding.configuration_fingerprint) ||
          !digest(binding.catalog_fingerprint)) malformed();
      checkResearchAuthority(binding);
      if (value.risk_source !== undefined) malformed();
      if (proposal.research_risk) {
        if (!digest(binding.research_risk_fingerprint) || typeof value.evaluated_at !== 'string' ||
            typeof value.valid_until !== 'string') malformed();
        const model = checkedResearchModel(value.risk_model, proposal.research_risk,
          metadata as unknown as NonNullable<PaperAdmission['profile']>['metadata'], String(profile.metadata_fingerprint),
          value.evaluated_at, value.valid_until);
        const sourceStatus = checkSourceStatus(value.risk_source_status);
        const observedStatuses = [model.source?.collateral_status, model.source?.margin_status];
        const expectedSourceStatus = observedStatuses.includes('UNSUPPORTED') ? 'UNSUPPORTED' :
          observedStatuses.includes('UNAVAILABLE') ? 'UNAVAILABLE' : 'SOURCE_OBSERVED';
        if ((model.source ? sourceStatus !== expectedSourceStatus : !['UNAVAILABLE', 'STALE'].includes(sourceStatus)) ||
            (model.settings.mode === 'SOURCE_CONSTRAINED' && sourceStatus !== 'SOURCE_OBSERVED')) malformed();
      } else if (binding.research_risk_fingerprint !== undefined || value.risk_model !== undefined ||
          value.risk_source_status !== undefined) malformed();
    }
  }
  if (eligible ? profile === null : value.valid_until !== null || binding !== null) malformed();
  if (!eligible) {
    if (value.risk_model !== undefined || (!proposal.research_risk &&
        (value.risk_source_status !== undefined || value.risk_source !== undefined || reason.startsWith('RISK_')))) malformed();
    if (value.risk_source_status !== undefined) checkSourceStatus(value.risk_source_status);
    if (value.risk_source !== undefined) {
      if (!object(profile) || !object(profile.metadata) || typeof profile.metadata_fingerprint !== 'string' ||
          value.risk_source_status === undefined) malformed();
      checkedFinancialObservation(value.risk_source,
        profile.metadata as unknown as NonNullable<PaperAdmission['profile']>['metadata'], profile.metadata_fingerprint);
    }
  }
  return value as unknown as PaperAdmission;
}

export function paperAdmissionHttpStatus(admission: PaperAdmission): number {
  if (admission.status === 'ELIGIBLE') return 200;
  if (admission.status === 'UNAVAILABLE') return 503;
  return admission.reason.endsWith('_FINGERPRINT_MISMATCH') ? 409 : 422;
}

export function paperAdmissionIsCurrent(admission: PaperAdmission | null, now = Date.now()): boolean {
  return admission?.status === 'ELIGIBLE' &&
    now >= Date.parse(admission.evaluated_at) && now < Date.parse(admission.valid_until);
}

export function checkedPaperResult(value: unknown, proposal: PaperProposal, expected: PaperBinding): GeneralizedPaperResult {
  if (!object(value) || value.profile_version !== paperProfileVersion || value.execution_mode !== 'PAPER' ||
      value.simulated !== true || !digest(value.result_fingerprint) || !object(value.proposal)) malformed();
  checkResearchAuthority(value);
  const admission = checkedPaperAdmission(value.admission, proposal);
  if (admission.status !== 'ELIGIBLE' || admission.binding.profile_fingerprint !== expected.profile_fingerprint ||
      admission.binding.metadata_fingerprint !== expected.metadata_fingerprint ||
      admission.binding.catalog_fingerprint !== expected.catalog_fingerprint ||
      admission.binding.research_risk_fingerprint !== expected.research_risk_fingerprint ||
      admission.binding.configuration_fingerprint !== expected.configuration_fingerprint) malformed();
  const started = marketUniverseTimestamp(value.started_at);
  if (started < marketUniverseTimestamp(admission.evaluated_at) ||
      started >= marketUniverseTimestamp(admission.valid_until)) malformed();
  const captured = value.proposal;
  if (captured.profile_version !== paperProfileVersion || !matchesIdentity(captured.identity, proposal) ||
      captured.scenario !== proposal.scenario || captured.frames !== proposal.frames ||
      captured.trace_max_points !== proposal.trace_max_points ||
      !sameDecimal(captured.simulated_reference_price, proposal.simulated_reference_price) ||
      !sameDecimal(captured.minimum_order_notional, proposal.minimum_order_notional ?? '100') ||
      !sameDecimal(captured.synthetic_top_depth_quote, proposal.synthetic_top_depth_quote ?? '18000') ||
      !sameEconomics(captured.economics, proposal.economics)) malformed();
  checkResearchAuthority(captured);
  if (proposal.research_risk) checkRiskSettings(captured.research_risk, proposal.research_risk);
  else if (captured.research_risk !== undefined || value.research_risk !== undefined) malformed();

  const result = value.result;
  if (!object(result) || result.simulated !== true || result.research_market !== admission.profile.stable_key ||
      result.market_profile_version !== paperProfileVersion || result.market_profile_fingerprint !== expected.profile_fingerprint ||
      typeof result.engine_version !== 'string' || !result.engine_version || result.engine_version.length > 96 ||
      result.scenario !== proposal.scenario || !digest(result.run_fingerprint) || !digest(result.dataset_fingerprint) ||
      !digest(result.strategy_fingerprint) || !object(result.metrics) ||
      !integer(result.metrics.frame_count, 2, maxFrames) || result.metrics.frame_count !== proposal.frames ||
      !integer(result.metrics.fill_count, 0, maxFrames * 8) || !object(result.vault) ||
      result.vault.simulated !== true || result.vault.mode !== 'PAPER' || result.vault.market !== result.research_market) malformed();
  for (const field of ['net_pnl_quote', 'fees_quote', 'funding_quote', 'position_base', 'initial_equity_quote',
    'equity_quote', 'reserved_capital_quote', 'realized_pnl_quote', 'unrealized_pnl_quote']) decimal(result.vault[field]);
  checkResearchAuthority(result);
  checkResearchAuthority(result.vault);
  if (admission.risk_model && admission.binding.research_risk_fingerprint)
    checkedPaperRiskResult(value.research_risk, admission.risk_model, proposal.identity,
      admission.binding.research_risk_fingerprint, proposal.frames, String(result.vault.position_base));
  return value as unknown as GeneralizedPaperResult;
}
