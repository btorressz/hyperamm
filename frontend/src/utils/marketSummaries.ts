import { compareDecimal } from './format';
import type { MarketUniverseError, MarketUniverseIdentity, MarketUniverseNetwork } from '../types/marketUniverse';
import { checkedMarketUniverseIdentity, marketUniverseKey, marketUniverseTimestamp } from './marketUniverse';
import { researchFingerprint } from './researchFingerprint';

export const marketSummariesByteLimit = 32_768;
export const publicHourlyFundingCap = '0.005';
export const marketSummaryRefreshMs = 20_000;
export const marketSummaryLifetimeMs = 30_000;
const source = 'HYPERLIQUID_INFO_META_AND_ASSET_CTXS';
const statuses = ['CURRENT', 'STALE', 'UNAVAILABLE', 'UNSUPPORTED', 'ERROR'] as const;
const failures = [
  'DISABLED', 'CLOSED', 'TIMEOUT', 'RATE_LIMITED', 'FORBIDDEN', 'UPSTREAM_ERROR',
  'NETWORK_ERROR', 'SDK_UNAVAILABLE', 'CLEANUP_ERROR', 'MISSING_METADATA', 'INVALID_DATA',
  'NETWORK_MISMATCH', 'NAMESPACE_CONFLICT', 'UNSUPPORTED_METADATA', 'RESPONSE_TOO_LARGE',
  'CATALOG_CAPACITY', 'CAPACITY', 'CATALOG_CHANGED', 'QUOTE_UNIT_MISMATCH',
] as const;
const metrics = {
  mark_price: 'positive',
  oracle_price: 'positive',
  previous_day_price: 'positive',
  funding_rate: 'funding',
  day_notional_volume: 'nonnegative',
  open_interest_base: 'nonnegative',
  mark_change_vs_previous_day_percent: 'signed',
} as const;

export interface MarketSummarySelector {
  key: string;
  metadataFingerprint: string;
  universeIndex: number;
  listed: boolean;
}

export interface MarketSummaryScope {
  network: MarketUniverseNetwork;
  catalogFingerprint: string;
  markets: readonly MarketSummarySelector[];
}

interface ReadOnly {
  read_only: true;
  execution_eligible: false;
  authority: 'NONE';
}

export type MarketSummary = ReadOnly & Record<keyof typeof metrics, string | null> & {
  identity: MarketUniverseIdentity;
  universe_index: number;
  metadata_fingerprint: string;
  status: typeof statuses[number];
  error: MarketUniverseError | 'CAPACITY' | 'CATALOG_CHANGED' | 'QUOTE_UNIT_MISMATCH' | null;
  funding_interval_seconds: 3600;
  price_unit: 'PROVIDER_QUOTE_PER_BASE';
  notional_unit: 'PROVIDER_NOTIONAL_QUOTE';
  open_interest_unit: 'BASE';
  funding_unit: 'RATE_PER_INTERVAL';
  observed_at: string | null;
  valid_until: string | null;
  provider_event_at: null;
  observation_clock: 'LOCAL_RECEIPT';
  source: typeof source;
  observation_fingerprint: string | null;
  limitations: string[];
};

export interface MarketSummaryResponse extends ReadOnly {
  schema_version: 'phase186h-v1';
  network: MarketUniverseNetwork;
  catalog_fingerprint: string;
  evaluated_at: string;
  valid_until: string;
  results: MarketSummary[];
}

const digest = (value: unknown) => typeof value === 'string' && value.length === 64 && !/[^a-f0-9]/.test(value);
const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const readOnly = (value: Record<string, unknown>) =>
  value.read_only === true && value.authority === 'NONE' && value.execution_eligible === false;
const includes = (values: readonly string[], value: unknown) =>
  typeof value === 'string' && values.includes(value);
const metricValue = (value: unknown, rule: typeof metrics[keyof typeof metrics]) => {
  if (typeof value !== 'string' || value.length > 93 || !/^-?\d+(?:\.\d{1,60})?$/.test(value) ||
      /[^0-9.\-]/.test(value)) return false;
  const maximum = rule === 'funding' ? publicHourlyFundingCap : '1' + '0'.repeat(30);
  const absolute = value.replace(/^-/, '');
  const sign = compareDecimal(value, '0');
  return compareDecimal(absolute, maximum) <= 0 && (rule !== 'positive' || sign > 0) &&
    (rule !== 'nonnegative' || sign >= 0);
};

function malformed(): never {
  throw new Error('Invalid market observations. Refresh discovery and try again.');
}

export async function checkedMarketSummaries(value: unknown, expected: MarketSummaryScope): Promise<MarketSummaryResponse> {
  if (!object(value) || !readOnly(value) || value.schema_version !== 'phase186h-v1' ||
      value.network !== expected.network || value.catalog_fingerprint !== expected.catalogFingerprint ||
      !digest(value.catalog_fingerprint) || !Array.isArray(value.results) ||
      value.results.length !== expected.markets.length || value.results.length > 13) malformed();

  const evaluated = marketUniverseTimestamp(value.evaluated_at);
  const deadline = marketUniverseTimestamp(value.valid_until);
  if (deadline <= evaluated) malformed();
  await Promise.all(value.results.map(async (row: unknown, index: number) => {
    const target = expected.markets[index];
    if (!object(row) || !readOnly(row) || !includes(statuses, row.status) ||
        (row.error !== null && !includes(failures, row.error)) ||
        marketUniverseKey(checkedMarketUniverseIdentity(row.identity, expected.network)) !== target.key ||
        row.universe_index !== target.universeIndex || !digest(row.metadata_fingerprint) ||
        row.metadata_fingerprint !== target.metadataFingerprint || row.source !== source ||
        row.funding_interval_seconds !== 3600 || row.observation_clock !== 'LOCAL_RECEIPT' ||
        row.provider_event_at !== null || row.price_unit !== 'PROVIDER_QUOTE_PER_BASE' ||
        row.notional_unit !== 'PROVIDER_NOTIONAL_QUOTE' || row.open_interest_unit !== 'BASE' ||
        row.funding_unit !== 'RATE_PER_INTERVAL' ||
        !Array.isArray(row.limitations) || row.limitations.length > 8 ||
        !row.limitations.every(item => typeof item === 'string' && /^[\w:]{1,64}$/.test(item))) malformed();

    const current = row.status === 'CURRENT';
    const hasValues = Object.entries(metrics).some(([key]) => row[key] !== null);
    if (current !== hasValues || (current && !target.listed) ||
        (row.status === 'UNSUPPORTED') !== !target.listed ||
        (row.status === 'ERROR' && row.error === null) ||
        Object.entries(metrics).some(([key, rule]) => row[key] !== null && !metricValue(row[key], rule)) ||
        (row.mark_change_vs_previous_day_percent !== null &&
          (row.mark_price === null || row.previous_day_price === null))) malformed();
    if ((row.observed_at === null) !== (row.valid_until === null)) malformed();
    if (row.observed_at !== null) {
      const observed = marketUniverseTimestamp(row.observed_at);
      const expiry = marketUniverseTimestamp(row.valid_until);
      if (expiry > deadline || (expiry <= observed && row.status !== 'STALE') || expiry - observed > BigInt(marketSummaryLifetimeMs) * 1000n ||
          (row.status !== 'STALE' && (observed > evaluated || expiry <= evaluated))) malformed();
    }
    const { observation_fingerprint: fingerprint, ...capture } = row;
    if (current && (row.observed_at === null || row.error !== null || !digest(fingerprint))) malformed();
    if (fingerprint !== null && (row.observed_at === null || row.error !== null || !digest(fingerprint) ||
        await researchFingerprint({ catalog_fingerprint: value.catalog_fingerprint, ...capture }) !== fingerprint)) malformed();
  }));
  return value as unknown as MarketSummaryResponse;
}

export function observedNumber(value: string | null | undefined, unit?: '%' | 'compact'): string {
  if (value == null) return 'Unavailable';
  return Number(value).toLocaleString(undefined, unit === '%'
    ? { style: 'percent', maximumSignificantDigits: 7 }
    : { maximumSignificantDigits: 8, notation: unit === 'compact' ? 'compact' : 'standard' });
}
