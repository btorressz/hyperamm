import {
  advisoryAnalysis, advisoryCategories, advisoryIssueText, advisoryProvenance, advisoryStatuses, advisoryVersion,
} from '../types/advisory';
import type { AdvisoryPaperBinding, AdvisoryRequest, AdvisoryResponse, AdvisorySelection } from '../types/advisory';
import type { MarketUniverseIdentity } from '../types/marketUniverse';
import { checkedMarketUniverseIdentity, marketUniverseKey, marketUniverseTimestamp } from './marketUniverse';
import { checkResearchAuthority } from './marketRisk';
import { publicHourlyFundingCap } from './marketSummaries';
import { exactDecimal } from './orderView';
import { researchFingerprint } from './researchFingerprint';

type Wire = Record<string, unknown>;
type Times = { evaluated: bigint; expiry: bigint };
export const advisoryByteLimit = 65_536;
export const advisoryFingerprint = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const oneOf = (value: unknown, options: readonly string[]): value is string =>
  typeof value === 'string' && options.includes(value);
const integer = (value: unknown, min: number, max: number): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max;

function invalid(): never {
  throw new Error('Invalid or inconsistent advisory evidence.');
}

function wire(value: unknown): Wire {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) invalid();
  return value as Wire;
}

function boundedList(value: unknown, max: number): unknown[] {
  if (!Array.isArray(value) || value.length > max) invalid();
  return value;
}

function shortText(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && Array.from(value).length <= 180;
}

function texts(value: unknown, max: number) {
  if (!boundedList(value, max).every(shortText)) invalid();
}

function authority(value: Wire, recommendation = false, snapshot = false) {
  checkResearchAuthority(value);
  if (value.contract_version !== advisoryVersion || value.authority !== 'NONE' ||
      value.execution_eligible !== false || (!snapshot && value.read_only !== true) ||
      ((snapshot || recommendation) && value.affects_quotes !== false) ||
      (recommendation && (value.can_override_risk !== false || value.can_authorize_paper !== false)) ||
      (value.can_override_risk !== undefined && value.can_override_risk !== false) ||
      (value.can_authorize_paper !== undefined && value.can_authorize_paper !== false) ||
      (value.affects_quotes !== undefined && value.affects_quotes !== false)) invalid();
}

function identity(value: unknown, expected: MarketUniverseIdentity) {
  checkResearchAuthority(wire(value));
  if (marketUniverseKey(checkedMarketUniverseIdentity(value, expected.network)) !== marketUniverseKey(expected)) invalid();
}

function clock(value: unknown): bigint {
  return marketUniverseTimestamp(value);
}

function scaled(value: unknown): bigint {
  if (typeof value !== 'string' || value.length > 80 || !/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d{1,2})?$/.test(value)) invalid();
  const [whole, fraction = ''] = exactDecimal(value).split('.');
  if (fraction.length > 60) invalid();
  const result = BigInt(whole + fraction.padEnd(60, '0'));
  if (result > 10n ** 90n || result < -(10n ** 90n)) invalid();
  return result;
}

const one = 10n ** 60n;
const publicHourlyCap = scaled(publicHourlyFundingCap);
const bpsLimit = 1_000_000n * one;

function unit(value: unknown, network: string, paperOnly = false) {
  const fields = wire(value);
  checkResearchAuthority(fields);
  if (fields.contract_version !== 'phase183a-v1' || fields.network !== network) invalid();
  if (fields.kind === 'HYPOTHETICAL_QUOTE') {
    if (fields.symbol !== 'HYPOTHETICAL_QUOTE' || fields.provenance !== 'RESEARCH_ASSUMPTION' ||
        fields.asset_namespace !== '' || fields.asset_reference !== null) invalid();
  } else if (paperOnly || fields.kind !== 'EXCHANGE_ASSET' || fields.provenance !== 'DECLARED_UNVERIFIED' ||
      typeof fields.symbol !== 'string' || fields.symbol === 'HYPOTHETICAL_QUOTE' ||
      !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(fields.symbol) ||
      typeof fields.asset_namespace !== 'string' || !/^(?:[A-Za-z0-9][A-Za-z0-9._-]{0,63})?$/.test(fields.asset_namespace) ||
      typeof fields.asset_reference !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/.test(fields.asset_reference)) invalid();
}

function sourceEvidence(value: unknown, expected: MarketUniverseIdentity, times: Times) {
  const source = wire(value);
  authority(source);
  identity(source.identity, expected);
  if (source.binding_version !== advisoryAnalysis || !advisoryFingerprint(source.source_fingerprint) ||
      !oneOf(source.category, advisoryCategories) || !oneOf(source.provenance, advisoryProvenance) ||
      typeof source.source_id !== 'string' || !/^[A-Z][A-Z0-9_]{0,63}$/.test(source.source_id)) invalid();
  const captured = clock(source.captured_at);
  if (captured > times.evaluated || (source.valid_until !== undefined && clock(source.valid_until) <= captured)) invalid();
  if (source.unit !== undefined && !oneOf(source.unit, ['RATE_PER_HOUR', 'PRICE_QUOTE_PER_BASE', 'BASE',
    'REALIZED_RATE_PER_HOUR', 'RATE_PER_PAPER_INTERVAL', 'PAPER_QUOTE_PER_BASE', 'MARK_NOTIONAL_RATE_PER_PAPER_INTERVAL'])) invalid();
  if (source.limitations !== undefined) texts(source.limitations, 4);
  if (source.financial_unit !== null) unit(source.financial_unit, expected.network);
  const isScenario = /^(?:PAPER_|SCENARIO_)/.test(source.source_id);
  const isAssumed = source.source_id.startsWith('ASSUMPTION_');
  if (source.provenance === 'EXCHANGE_OBSERVED') {
    if (isScenario || isAssumed || source.scenario_at !== null ||
        (source.observation_clock === 'LOCAL_RECEIPT' ? source.observed_at !== null :
          source.observation_clock !== 'PROVIDER_EVENT' || clock(source.observed_at) > captured)) invalid();
  } else {
    if (source.observed_at !== null || source.observation_clock !== undefined) invalid();
    if (source.provenance === 'SCENARIO_SYNTHETIC') {
      clock(source.scenario_at);
      if (!isScenario || ['MARKET_METADATA', 'COLLATERAL', 'MARGIN_POLICY'].includes(String(source.category))) invalid();
    } else if (source.provenance !== 'HYPOTHETICAL_ASSUMPTION' || !isAssumed || source.scenario_at !== null) invalid();
  }
  return source as Wire & { source_fingerprint: string; category: string; provenance: string };
}

function recommendation(value: unknown, agent: string, contextFingerprint: string, evaluatedAt: unknown,
                        market: MarketUniverseIdentity, sources: Map<string, ReturnType<typeof sourceEvidence>>, times: Times) {
  const result = wire(value);
  authority(result, true);
  identity(result.identity, market);
  if (result.agent !== agent || result.analysis_version !== advisoryAnalysis ||
      result.context_fingerprint !== contextFingerprint || result.evaluated_at !== evaluatedAt ||
      !oneOf(result.status, advisoryStatuses)) invalid();
  const confidence = scaled(result.confidence);
  const fingerprints = boundedList(result.source_fingerprints, 16);
  if (new Set(fingerprints).size !== fingerprints.length) invalid();
  const cited = fingerprints.map(fp => {
    const source = typeof fp === 'string' ? sources.get(fp) : undefined;
    if (!source || (source.valid_until !== undefined && clock(source.valid_until) < times.expiry)) invalid();
    return source;
  });
  const provenances = new Set(cited.map(source => source.provenance));
  const provenance = provenances.size > 1 ? 'MIXED' : (cited[0]?.provenance ?? 'UNAVAILABLE');
  if (result.provenance !== provenance || (result.status === 'READY' ?
    confidence <= 0n || confidence > one || !cited.length : confidence !== 0n)) invalid();
  texts(result.reasons, 12);
  if (result.status !== 'READY' && (result.reasons as unknown[]).length === 0) invalid();
  if (result.missing_requirements !== undefined) texts(result.missing_requirements, 12);
  return { result, cited };
}

function checkFunding(value: ReturnType<typeof recommendation>, mode: string) {
  const { result, cited } = value;
  const provenance = mode === 'OBSERVED' ? 'EXCHANGE_OBSERVED' : 'SCENARIO_SYNTHETIC';
  const currentContext = 'HYPERLIQUID_META_AND_ASSET_CTXS';
  const providerUnits: Record<string, [string, string, string]> = {
    FUNDING: [currentContext, 'RATE_PER_HOUR', 'LOCAL_RECEIPT'],
    MARK_PRICE: [currentContext, 'PRICE_QUOTE_PER_BASE', 'LOCAL_RECEIPT'],
    ORACLE_PRICE: [currentContext, 'PRICE_QUOTE_PER_BASE', 'LOCAL_RECEIPT'],
    MID_PRICE: ['HYPERLIQUID_L2_BOOK', 'PRICE_QUOTE_PER_BASE', 'PROVIDER_EVENT'],
    OPEN_INTEREST: [currentContext, 'BASE', 'LOCAL_RECEIPT'],
    FUNDING_HISTORY: ['HYPERLIQUID_FUNDING_HISTORY', 'REALIZED_RATE_PER_HOUR', 'PROVIDER_EVENT'],
  };
  const scenarioUnits: Record<string, string> = {
    FUNDING: 'RATE_PER_PAPER_INTERVAL', MARK_PRICE: 'PAPER_QUOTE_PER_BASE',
    ORACLE_PRICE: 'PAPER_QUOTE_PER_BASE', MID_PRICE: 'PAPER_QUOTE_PER_BASE', OPEN_INTEREST: 'BASE',
  };
  const sharedClock = new Set<unknown>();
  for (const source of cited) {
    if (source.provenance !== provenance) invalid();
    if (mode === 'OBSERVED') {
      const contract = providerUnits[source.category];
      if (!contract || source.source_id !== contract[0] || source.unit !== contract[1] ||
          source.observation_clock !== contract[2]) invalid();
      if (source.source_id === currentContext) sharedClock.add(source.captured_at);
    } else {
      if (!scenarioUnits[source.category] || source.source_id !== 'PAPER_LAST_FRAME' ||
          source.unit !== scenarioUnits[source.category]) invalid();
      sharedClock.add(source.scenario_at);
    }
  }
  if (sharedClock.size > 1 || new Set(cited.map(source => source.category)).size !== cited.length) invalid();
  function field(key: string, category: string, min: bigint, max = 10n ** 90n) {
    if (result[key] == null) return null;
    const amount = scaled(result[key]);
    if (amount < min || amount > max || !cited.some(source => source.category === category)) invalid();
    return amount;
  }
  const fundingCap = mode === 'OBSERVED' ? publicHourlyCap : one;
  const rate = field('funding_rate', 'FUNDING', -fundingCap, fundingCap);
  const mark = field('mark_price', 'MARK_PRICE', 1n);
  const oracle = field('oracle_price', 'ORACLE_PRICE', 1n);
  const midpoint = field('midpoint_price', 'MID_PRICE', 1n);
  const basis = field('mark_oracle_basis_bps', 'MARK_PRICE', -bpsLimit, bpsLimit);
  const midBasis = field('mark_mid_basis_bps', 'MID_PRICE', -bpsLimit, bpsLimit);
  const oracleMid = field('oracle_mid_basis_bps', 'MID_PRICE', -bpsLimit, bpsLimit);
  field('open_interest_base', 'OPEN_INTEREST', 0n);
  const mean = field('recent_history_mean_rate', 'FUNDING_HISTORY', -publicHourlyCap, publicHourlyCap);
  if (midpoint === null && (midBasis !== null || oracleMid !== null)) invalid();
  if (result.status === 'READY') {
    if (rate === null || mark === null || oracle === null || basis === null ||
        result.funding_direction !== (rate > 0n ? 'LONGS_PAY' : rate < 0n ? 'SHORTS_PAY' : 'FLAT') ||
        !['BASIS_STRESSED', rate > 0n ? 'FUNDING_POSITIVE' : rate < 0n ? 'FUNDING_NEGATIVE' : 'NEUTRAL'].includes(String(result.state)) ||
        !integer(result.funding_interval_seconds, 1, 604_800)) invalid();
    if (mode === 'OBSERVED') {
      if (result.funding_convention !== 'HYPERLIQUID_HOURLY' || result.funding_interval_seconds !== 3600 ||
          !integer(result.history_count, 0, 24) || ((result.history_count > 0) !== (mean !== null))) invalid();
    } else if (result.funding_convention !== 'PAPER_SCHEDULED_INTERVAL' || result.history_count !== undefined || mean !== null) invalid();
  } else if (result.state !== 'UNKNOWN' || rate !== null || basis !== null || midBasis !== null || oracleMid !== null ||
      result.funding_convention !== undefined || result.funding_direction !== undefined || result.funding_interval_seconds !== null ||
      result.history_count !== undefined || mean !== null) invalid();
}

function checkQuote(value: ReturnType<typeof recommendation>, market: MarketUniverseIdentity, selected: Wire,
                    quote: AdvisoryRequest['quote']) {
  const { result, cited } = value;
  if (result.hypothetical_only !== true || result.guarantees_profit !== false) invalid();
  const costs = ['fee_cost_bps', 'funding_cost_bps', 'inventory_cost_bps', 'adverse_selection_cost_bps', 'slippage_cost_bps'];
  const details = ['submitted_bid', 'submitted_ask', 'entry_fees_quote', 'exit_fees_quote', 'quoted_notional',
    'executed_reference_notional', 'filled_base', 'residual_base', 'inventory_expansion_base'];
  const counts = ['attributed_fill_count', 'matured_markout_count', 'holding_seconds', 'funding_interval_seconds'];
  if (result.status !== 'READY') {
    if (result.state !== 'INDETERMINATE' || ['accounting_unit', 'gross_spread_bps', 'modeled_edge_bps',
      'captured_spread_bps', 'break_even_capture_bps', 'projected_margin_headroom', 'margin_headroom_unit',
      'bid_capture_bps', 'ask_capture_bps', 'fill_coverage', ...costs, ...details, ...counts]
      .some(key => result[key] != null)) invalid();
    return;
  }
  if (!quote || selected.quote_sequence === null || selected.quote_risk_state === 'HALT' ||
      result.holding_seconds !== quote.assumptions.holding_seconds) invalid();
  unit(result.accounting_unit, market.network, true);
  const required = {
    QUOTE_LADDER: 'SCENARIO_SYNTHETIC', PAPER_FILLS: 'SCENARIO_SYNTHETIC', FUNDING: 'SCENARIO_SYNTHETIC',
    FEES: 'HYPOTHETICAL_ASSUMPTION', INVENTORY: 'HYPOTHETICAL_ASSUMPTION', FILL_MARKOUT: 'SCENARIO_SYNTHETIC',
  };
  for (const [category, provenance] of Object.entries(required)) {
    const source = cited.find(item => item.category === category && item.provenance === provenance);
    if (!source) invalid();
    if (category === 'FUNDING') {
      if (source.unit !== 'MARK_NOTIONAL_RATE_PER_PAPER_INTERVAL' || source.source_id !== 'PAPER_QUOTE_CARRY') invalid();
    } else unit(source.financial_unit, market.network, true);
  }
  if (details.some(key => {
    const amount = scaled(result[key]);
    if (key === 'residual_base') return false;
    const allowZero = ['entry_fees_quote', 'exit_fees_quote', 'inventory_expansion_base'].includes(key);
    return allowZero ? amount < 0n : amount <= 0n;
  }) || scaled(result.submitted_ask) <= scaled(result.submitted_bid)) invalid();
  if (!integer(result.attributed_fill_count, 1, 1000) || result.attributed_fill_count !== result.matured_markout_count ||
      !integer(result.holding_seconds, 1, 604_800) || !integer(result.funding_interval_seconds, 1, 604_800)) invalid();
  const bps = (key: string, signed = false) => {
    const amount = scaled(result[key]);
    if (amount < (signed ? -bpsLimit : 0n) || amount > bpsLimit) invalid();
    return amount;
  };
  bps('gross_spread_bps');
  const breakEven = bps('break_even_capture_bps', true);
  const capture = bps('captured_spread_bps', true);
  const edge = bps('modeled_edge_bps', true);
  if (costs.reduce((total, key) => total + bps(key, key === 'funding_cost_bps'), 0n) !== breakEven || edge !== capture - breakEven ||
      result.state !== (edge > 0n ? 'MODELED_POSITIVE' : edge < 0n ? 'MODELED_NEGATIVE' : 'MODELED_BREAKEVEN')) invalid();
  const sideCount = ['bid_capture_bps', 'ask_capture_bps'].filter(key => {
    if (result[key] === undefined) return false;
    bps(key, true);
    return true;
  }).length;
  if (!oneOf(result.fill_coverage, ['ONE_SIDED', 'BOTH_SIDES']) ||
      sideCount !== (result.fill_coverage === 'BOTH_SIDES' ? 2 : 1)) invalid();
  if (result.projected_margin_headroom !== undefined) {
    if (scaled(result.projected_margin_headroom) < 0n) invalid();
    unit(result.margin_headroom_unit, market.network);
  } else if (result.margin_headroom_unit !== undefined) invalid();
}

export async function checkedAdvisoryResponse(value: unknown, request: AdvisoryRequest, selection: AdvisorySelection,
                                              paper?: AdvisoryPaperBinding): Promise<AdvisoryResponse> {
  const response = wire(value);
  const market = request.identity;
  authority(response, true);
  identity(response.identity, market);
  if (response.schema_version !== 'phase184e-v1' || !advisoryFingerprint(response.snapshot_fingerprint)) invalid();
  const funding = request.funding_mode ?? (request.operation === 'FUNDING_BASIS' ? 'OBSERVED' : null);
  const quote = request.operation === 'QUOTE_ECONOMICS' || request.quote !== undefined;
  const issues = boundedList(response.issues, 5);
  if (response.funding_mode !== funding || new Set(issues).size !== issues.length ||
      !issues.every(issue => typeof issue === 'string' && Object.hasOwn(advisoryIssueText, issue))) invalid();

  const snapshot = wire(response.snapshot);
  const context = wire(snapshot.context);
  authority(snapshot, false, true);
  authority(context);
  if (snapshot.scope !== 'SINGLE_MARKET_RESEARCH_ONLY' || context.scope !== snapshot.scope ||
      context.catalog_fingerprint !== request.catalog_fingerprint || context.catalog_fingerprint !== selection.catalog_fingerprint ||
      !advisoryFingerprint(context.catalog_fingerprint) || !advisoryFingerprint(context.metadata_fingerprint) ||
      context.metadata_fingerprint !== selection.metadata_fingerprint ||
      context.evaluated_at !== response.evaluated_at) invalid();
  const metadata = wire(context.metadata);
  checkResearchAuthority(metadata);
  identity(metadata.identity, market);
  if (Object.entries(selection.metadata).some(([key, expected]) => key !== 'identity' && metadata[key] !== expected)) invalid();

  const times = { evaluated: clock(response.evaluated_at), expiry: clock(response.valid_until) };
  const contextExpiry = clock(context.valid_until);
  const observed = clock(metadata.observed_at);
  if (observed > times.evaluated || times.evaluated >= times.expiry || times.expiry > contextExpiry ||
      contextExpiry > observed + BigInt(selection.max_age_seconds) * 1_000_000n) invalid();
  const sources = new Map<string, ReturnType<typeof sourceEvidence>>();
  const sourceKeys = new Set<string>();
  for (const item of boundedList(context.sources, 16)) {
    const source = sourceEvidence(item, market, times);
    const key = [source.category, source.provenance, source.source_id].join(':');
    if (sources.has(source.source_fingerprint) || sourceKeys.has(key)) invalid();
    sources.set(source.source_fingerprint, source);
    sourceKeys.add(key);
  }

  const hasPaper = response.paper_result_fingerprint !== null;
  if (hasPaper ? !request.paper_receipt || !paper || !advisoryFingerprint(response.paper_result_fingerprint) ||
      response.paper_result_fingerprint !== paper.result_fingerprint ||
      context.paper_binding_fingerprint !== paper.binding.configuration_fingerprint ||
      context.risk_model_fingerprint !== (paper.binding.research_risk_fingerprint ?? null) :
      !request.proposal && (context.paper_binding_fingerprint !== null || context.risk_model_fingerprint !== null)) invalid();
  for (const fp of [context.paper_binding_fingerprint, context.risk_model_fingerprint])
    if (fp !== null && !advisoryFingerprint(fp)) invalid();

  const cohorts = boundedList(response.quote_cohorts, 120);
  if (!cohorts.every((sequence, index) => integer(sequence, 1, 120) && (index === 0 || Number(cohorts[index - 1]) < sequence)) ||
      ((!quote || !hasPaper) && cohorts.length > 0)) invalid();
  if (response.quote_sequence === null) {
    if (response.quote_risk_state !== null || (hasPaper && request.quote && !issues.includes('INVALID_QUOTE_COHORT'))) invalid();
  } else if (!hasPaper || !request.quote || response.quote_sequence !== request.quote.sequence ||
      !cohorts.includes(response.quote_sequence) || !oneOf(response.quote_risk_state, ['NORMAL', 'WIDEN', 'REDUCE', 'HALT'])) invalid();

  const contextFingerprint = await researchFingerprint(context);
  const checked = (item: unknown, name: string) => {
    const result = recommendation(item, name, contextFingerprint, response.evaluated_at, market, sources, times);
    if (result.result.status === 'READY' && (metadata.listed !== true || metadata.metadata_status !== 'EXCHANGE_VERIFIED')) invalid();
    return result;
  };
  const { result: eligibility } = checked(snapshot.market_eligibility, 'MARKET_ELIGIBILITY');
  if (eligibility.operation !== request.operation || !oneOf(eligibility.suitability, ['SUITABLE', 'CONDITIONAL', 'NOT_SUITABLE', 'UNKNOWN']) ||
      (eligibility.status === 'READY') !== ['SUITABLE', 'CONDITIONAL'].includes(eligibility.suitability) ||
      eligibility.missing_requirements === undefined) invalid();
  if (funding) checkFunding(checked(snapshot.funding_basis, 'FUNDING_BASIS'), funding);
  else if (snapshot.funding_basis !== null) invalid();
  if (quote) checkQuote(checked(snapshot.quote_economics, 'QUOTE_ECONOMICS'), market, response, request.quote);
  else if (snapshot.quote_economics !== null) invalid();
  if (await researchFingerprint(snapshot) !== response.snapshot_fingerprint) invalid();
  return value as AdvisoryResponse;
}
