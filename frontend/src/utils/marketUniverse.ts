import type { MarketUniverseIdentity, MarketUniverseResponse } from '../types/marketUniverse';

export const marketUniverseByteLimit = 5_000_000;
const maxRecords = 4096;
const maxNamespaces = 64;
const errors: readonly string[] = [
  'DISABLED', 'CLOSED', 'TIMEOUT', 'RATE_LIMITED', 'FORBIDDEN', 'UPSTREAM_ERROR', 'NETWORK_ERROR',
  'SDK_UNAVAILABLE', 'CLEANUP_ERROR', 'MISSING_METADATA', 'INVALID_DATA', 'NETWORK_MISMATCH',
  'NAMESPACE_CONFLICT', 'UNSUPPORTED_METADATA', 'RESPONSE_TOO_LARGE', 'CATALOG_CAPACITY',
];
const availability: readonly string[] = ['AVAILABLE', 'PARTIAL', 'STALE', 'UNAVAILABLE', 'DISABLED'];
const limitations = ['METADATA_ONLY', 'NO_PAPER_RESEARCH', 'NO_EXECUTION'];

const versioned = (x: unknown): x is Record<string, unknown> =>
  typeof x === 'object' && x !== null && 'contract_version' in x && x.contract_version === 'phase180b-v2';
const readOnly = (x: Record<string, unknown>) => x.read_only === true && x.authority === 'NONE';
const hasNoTradeAuthority = (x: Record<string, unknown>) =>
  readOnly(x) && x.paper_research_eligible === false && x.execution_eligible === false;
const integer = (x: unknown, min: number, max: number): x is number =>
  typeof x === 'number' && Number.isInteger(x) && x >= min && x <= max;
const namespacePart = (x: unknown, max: number): x is string =>
  typeof x === 'string' && x.length <= max && /^[A-Za-z0-9]/.test(x) && !/[^A-Za-z0-9._-]/.test(x);
const digest = (x: unknown) => typeof x === 'string' && x.length === 64 && !/[^a-f0-9]/.test(x);
const failure = (x: unknown) => typeof x === 'string' && errors.includes(x);

function malformed(): never {
  throw new Error('Invalid or unsupported market universe response.');
}

export function marketUniverseTimestamp(x: unknown): bigint {
  if (typeof x !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{6})?Z$/.test(x)) malformed();
  const milliseconds = Date.parse(x);
  if (!Number.isFinite(milliseconds) || !x.endsWith('Z') || x.startsWith('0000') ||
      new Date(milliseconds).toISOString().slice(0, 19) !== x.slice(0, 19)) malformed();
  return BigInt(milliseconds) * 1000n + BigInt(x.length === 27 ? x.slice(23, 26) : 0);
}

export function marketUniverseKey(identity: MarketUniverseIdentity): string {
  return `${identity.venue}:${identity.network}:${identity.instrument_type}:${identity.dex}:${identity.instrument_name}`;
}

export function checkedMarketUniverseIdentity(value: unknown, network: MarketUniverseResponse['network']): MarketUniverseIdentity {
  if (!versioned(value) || value.venue !== 'HYPERLIQUID' || value.network !== network ||
      !namespacePart(value.instrument_name, 64)) malformed();
  if (value.instrument_type === 'CORE_PERP' ? value.dex !== '' :
      value.instrument_type !== 'HIP3_PERP' || !namespacePart(value.dex, 32)) malformed();
  return value as unknown as MarketUniverseIdentity;
}

function checkResult(value: unknown, allowedToSkip: boolean): asserts value is Record<string, unknown> {
  if (!versioned(value)) malformed();
  if (value.status === 'REFRESHED') {
    if (value.error !== null) malformed();
    marketUniverseTimestamp(value.observed_at);
  } else if ((value.status !== 'FAILED' && !(allowedToSkip && value.status === 'SKIPPED')) ||
      value.observed_at !== null || !failure(value.error)) malformed();
}

export function checkedMarketUniverse(value: unknown): MarketUniverseResponse {
  if (!versioned(value)) malformed();
  const advertisedLimitations = value.limitations;
  if (value.schema_version !== 'phase181-v1' || !hasNoTradeAuthority(value) ||
      (value.network !== 'MAINNET' && value.network !== 'TESTNET') ||
      typeof value.availability !== 'string' || !availability.includes(value.availability) ||
      !integer(value.max_age_seconds, 1, 86400) || (value.error !== null && !failure(value.error)) ||
      !Array.isArray(advertisedLimitations) || advertisedLimitations.length !== limitations.length ||
      !limitations.every((limit, index) => advertisedLimitations[index] === limit) ||
      !Array.isArray(value.eligibility) || value.eligibility.length > maxRecords ||
      !Array.isArray(value.namespaces) || value.namespaces.length > maxNamespaces) malformed();

  const evaluatedAt = marketUniverseTimestamp(value.evaluated_at);
  const budget = BigInt(value.max_age_seconds) * 1_000_000n;
  const observations = new Map<string, unknown>();
  if (value.inventory !== null) checkResult(value.inventory, false);
  let previousDex: string | undefined;
  for (const namespace of value.namespaces) {
    checkResult(namespace, true);
    const { dex } = namespace;
    if ((dex !== '' && !namespacePart(dex, 32)) ||
        (previousDex === undefined ? dex !== '' : dex <= previousDex)) malformed();
    if (namespace.status === 'REFRESHED') observations.set(dex, namespace.observed_at);
    previousDex = dex;
  }

  const complete = value.availability === 'AVAILABLE' || value.availability === 'STALE';
  if (value.namespaces.length > 0 && value.inventory?.status !== 'REFRESHED') malformed();
  if (complete && (value.error !== null || value.namespaces.length === 0 ||
      observations.size !== value.namespaces.length)) malformed();
  if (value.availability === 'PARTIAL' && (value.error !== null || !observations.has('') ||
      observations.size === value.namespaces.length)) malformed();
  if (value.availability === 'DISABLED' && (value.error !== 'DISABLED' || value.inventory !== null ||
      value.catalog !== null)) malformed();
  if (value.availability === 'UNAVAILABLE' && value.error === null && value.inventory?.status !== 'FAILED' &&
      (value.namespaces.length === 0 || observations.size === value.namespaces.length)) malformed();

  if (value.catalog === null) {
    if (complete || value.catalog_fingerprint !== null || value.eligibility.length !== 0) malformed();
    return value as unknown as MarketUniverseResponse;
  }

  if (!versioned(value.catalog) || !readOnly(value.catalog) || !digest(value.catalog_fingerprint) ||
      !Array.isArray(value.catalog.records) || value.catalog.records.length === 0 ||
      value.catalog.records.length !== value.eligibility.length) malformed();

  const indices = new Map<string, Set<number>>();
  let previousKey = '';
  for (const [position, metadata] of value.catalog.records.entries()) {
    if (!versioned(metadata)) malformed();
    const identity = checkedMarketUniverseIdentity(metadata.identity, value.network);
    const key = marketUniverseKey(identity);
    const core = identity.instrument_type === 'CORE_PERP';
    const { dex, instrument_name } = identity;
    if (key <= previousKey || metadata.source_coin !== (core ? instrument_name : `${dex}:${instrument_name}`) ||
        metadata.metadata_source !== (core ? 'OFFICIAL_SDK_CORE_META' : 'OFFICIAL_SDK_HIP3_META') ||
        metadata.metadata_status !== (value.availability === 'AVAILABLE' ? 'EXCHANGE_VERIFIED' : 'STALE') ||
        typeof metadata.listed !== 'boolean' || !integer(metadata.sz_decimals, 0, 6) ||
        !integer(metadata.universe_index, 0, 9999)) malformed();
    previousKey = key;

    const dexIndices = indices.get(dex) ?? new Set<number>();
    if (dexIndices.has(metadata.universe_index) ||
        (complete && observations.get(dex) !== metadata.observed_at)) malformed();
    dexIndices.add(metadata.universe_index);
    indices.set(dex, dexIndices);

    const age = evaluatedAt - marketUniverseTimestamp(metadata.observed_at);
    if (value.availability === 'AVAILABLE' && (age < 0n || age > budget)) malformed();
    const reason = !metadata.listed ? 'NOT_LISTED' : age < 0n ? 'FUTURE_TIMESTAMP' :
      metadata.metadata_status === 'STALE' || age > budget ? 'STALE_METADATA' : 'DISCOVERABLE';
    const decision: unknown = value.eligibility[position];
    if (!versioned(decision) || !hasNoTradeAuthority(decision) || !digest(decision.metadata_fingerprint) ||
        marketUniverseKey(checkedMarketUniverseIdentity(decision.identity, value.network)) !== key ||
        decision.evaluated_at !== value.evaluated_at || decision.reason !== reason ||
        decision.discovery_eligible !== (reason === 'DISCOVERABLE')) malformed();
  }
  if (!indices.has('') || (complete && indices.size !== observations.size)) malformed();
  for (const dexIndices of indices.values()) {
    // Each namespace contains every original ordinal, including delisted rows.
    for (let index = 0; index < dexIndices.size; index++) if (!dexIndices.has(index)) malformed();
  }
  return value as unknown as MarketUniverseResponse;
}

export function marketUniverseHttpStatus(value: MarketUniverseResponse): number {
  if (value.availability === 'AVAILABLE' || value.availability === 'PARTIAL' || value.availability === 'STALE') return 200;
  const codes = [value.error, value.inventory?.error, ...value.namespaces.map(namespace => namespace.error)];
  return codes.includes('RATE_LIMITED') ? 429 : codes.includes('TIMEOUT') ? 504 : 503;
}

export function marketCatalogDeadline(catalog: MarketUniverseResponse | undefined): number {
  if (catalog?.availability !== 'AVAILABLE' || !catalog.catalog) return 0;
  return catalog.catalog.records.reduce((oldest, record) =>
    Math.min(oldest, Date.parse(record.observed_at) + catalog.max_age_seconds * 1000), Infinity);
}

export function marketResearchAvailability(
  catalog: MarketUniverseResponse,
  index: number,
  current: boolean,
): 'check-required' | 'unsupported' | 'unavailable' {
  const record = catalog.catalog?.records[index];
  const decision = catalog.eligibility[index];
  if (!record || !decision || !record.listed) return 'unsupported';
  return current && decision.discovery_eligible ? 'check-required' : 'unavailable';
}

export interface MarketResearchHandoff {
  key: string;
  catalogFingerprint: string;
  metadataFingerprint: string;
}

export function matchesMarketResearchHandoff(
  catalog: MarketUniverseResponse | undefined, handoff: MarketResearchHandoff, now = Date.now(),
): boolean {
  if (!catalog || catalog.catalog_fingerprint !== handoff.catalogFingerprint ||
      now >= marketCatalogDeadline(catalog)) return false;
  const index = catalog.catalog?.records.findIndex(record => marketUniverseKey(record.identity) === handoff.key) ?? -1;
  return marketResearchAvailability(catalog, index, true) === 'check-required' &&
    catalog.eligibility[index].metadata_fingerprint === handoff.metadataFingerprint;
}
