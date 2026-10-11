import type { LiveMarketId, LiveStreamSnapshot, LiveMarketStreamEnvelope, LiveMarketHistory, LiveProviderHealth } from '../types';
import { advancingAge } from './freshness';

export const liveMarketIds: LiveMarketId[] = ['BTC', 'ETH', 'SOL'];
export const liveMarketNames = { BTC: 'Bitcoin', ETH: 'Ethereum', SOL: 'Solana' };
const observations = ['AVAILABLE', 'PARTIAL', 'DEGRADED', 'STALE', 'UNAVAILABLE', 'ERROR', 'DISABLED'];
const connections = ['DISABLED', 'CONNECTING', 'BOOTSTRAPPING', 'CONNECTED', 'DEGRADED', 'STALE', 'RECONNECTING', 'UNAVAILABLE', 'STOPPED'];
const sources = ['OFFICIAL_SDK_REST', 'OFFICIAL_SDK_WEBSOCKET'];
const errors = ['INVALID_DATA','REPLAY','CONFLICT','OVERFLOW','TIMEOUT','NETWORK_ERROR','RATE_LIMITED','FORBIDDEN','SDK_UNAVAILABLE','UPSTREAM_ERROR','CLEANUP_ERROR','NOT_LISTED'];
export function decimalValue(value: unknown): number | null {
  if (typeof value !== 'string' || value.length > 128 || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value)) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}
function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error('Missing evidence object');
  return v as Record<string, unknown>;
}
function requireThat(condition: unknown, message = 'Invalid live evidence'): asserts condition {
  if (!condition) throw new Error(message);
}
function choice(v: unknown, options: readonly string[]) { return typeof v === 'string' && options.includes(v); }
function integer(v: unknown, minimum = 0) { return typeof v === 'number' && Number.isSafeInteger(v) && v >= minimum; }
export function liveTimestamp(v: unknown, now = Date.now()): v is string {
  if (typeof v !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(v)) return false;
  const time = Date.parse(v);
  // Reject normalized impossible dates (e.g. February 30), and invalid hours/offsets.
  const [year,month,day] = v.slice(0,10).split('-').map(Number);
  const days = new Date(Date.UTC(year,month,0)).getUTCDate();
  return month >= 1 && month <= 12 && day >= 1 && day <= days && Number(v.slice(11,13)) < 24 && Number(v.slice(14,16)) < 60 && Number(v.slice(17,19)) < 60 && Number.isFinite(time) && time <= now + 1000;
}
function stamp(v: unknown, now: number, nullable = false) { requireThat(nullable && v === null || liveTimestamp(v, now), 'Invalid or future source timestamp'); }
function textList(v: unknown) { requireThat(Array.isArray(v) && v.length <= 100 && v.every(x => typeof x === 'string' && x.length < 2000)); }
function financial(v: unknown, positive = false, nullable = false) {
  if (nullable && v === null) return;
  const n = decimalValue(v); requireThat(n !== null && (!positive || n > 0), 'Invalid financial Decimal string');
}
export function checkedLiveSnapshot(value: unknown, market: LiveMarketId, now = Date.now()): LiveStreamSnapshot {
  const v = object(value), s = object(v.status), m = object(v.metadata);
  requireThat(v.market === market && s.market === market && m.market === market, 'Wrong selected market');
  requireThat(choice(v.observation_status, observations)); textList(v.limitations);
  requireThat(s.contract_version === 'phase152-v1' && s.transport === 'OFFICIAL_SDK_WEBSOCKET' && s.read_only === true && s.simulated === false);
  requireThat(choice(s.connection_state, connections) && choice(s.subscription_state, ['NONE','REQUESTED','OBSERVED','RETIRED']));
  requireThat(integer(s.connection_generation) && typeof s.observer_instance_id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s.observer_instance_id));
  stamp(s.evaluated_at, now);
  requireThat(now-Date.parse(String(s.evaluated_at)) <= 30000, 'Stale or clock-uncertain snapshot evaluation');
  for (const key of ['l2','perp','metadata']) {
    requireThat(choice(s[`${key}_freshness`], ['FRESH','STALE','UNAVAILABLE']));
    const age = s[`${key}_age_seconds`], budget = s[`${key}_stale_after_seconds`];
    requireThat(age === null || typeof age === 'number' && Number.isFinite(age) && age >= -1);
    requireThat(typeof budget === 'number' && Number.isFinite(budget) && budget > 0 && budget <= 86400);
  }
  for (const key of ['reconnect_count','rejected_update_count','dropped_update_count']) requireThat(integer(s[key]));
  requireThat(s.last_error_code === null || choice(s.last_error_code, errors));
  requireThat(s.perp_event_time === 'UNKNOWN');
  for (const key of ['last_l2_source_timestamp','last_l2_observed_at','last_perp_observed_at']) stamp(s[key], now, true);
  requireThat(m.dex === '' && choice(m.metadata_status, ['EXCHANGE_VERIFIED','UNAVAILABLE','STALE','ERROR']) && choice(m.source, ['OFFICIAL_SDK_NATIVE_META','NONE']));
  requireThat(m.sz_decimals === null || integer(m.sz_decimals) && Number(m.sz_decimals) <= 6);
  requireThat(m.asset_index === null || integer(m.asset_index)); requireThat(m.listed === null || typeof m.listed === 'boolean'); stamp(m.observed_at, now, true);
  if (m.metadata_status === 'EXCHANGE_VERIFIED') requireThat(m.source === 'OFFICIAL_SDK_NATIVE_META' && m.listed === true && m.sz_decimals !== null && m.asset_index !== null && m.observed_at !== null);
  if (v.order_book !== null) {
    const b = object(v.order_book);
    requireThat(b.market === market && choice(b.source, sources) && typeof b.truncated === 'boolean');
    stamp(b.source_timestamp, now); stamp(b.observed_at, now);
    requireThat(b.source_timestamp === s.last_l2_source_timestamp && b.observed_at === s.last_l2_observed_at);
    for (const key of ['best_bid','best_ask','midpoint','spread','spread_bps']) financial(b[key], true);
    requireThat(Number(b.best_bid) < Number(b.best_ask));
    for (const side of ['bids','asks']) {
      const levels = b[side]; requireThat(Array.isArray(levels) && levels.length > 0 && levels.length <= 20);
      let previous: number | null = null;
      for (const raw of levels) {
        const level = object(raw); financial(level.price, true); financial(level.size);
        requireThat(Number(level.size) >= 0 && integer(level.order_count));
        const px = Number(level.price);
        requireThat(previous === null || (side === 'bids' ? px < previous : px > previous)); previous = px;
      }
      requireThat(object(levels[0]).price === b[side === 'bids' ? 'best_bid' : 'best_ask']);
    }
  } else requireThat(s.l2_freshness !== 'FRESH');
  if (v.perp_context !== null) {
    const p = object(v.perp_context); requireThat(p.market === market && choice(p.source, sources) && p.source_timestamp === null && p.event_time_verified === false);
    stamp(p.observed_at, now); requireThat(p.observed_at === s.last_perp_observed_at);
    for (const key of ['mark_price','oracle_price']) financial(p[key], true);
    for (const key of ['funding_rate','open_interest_base','open_interest_notional','mark_oracle_basis_bps']) financial(p[key]);
    requireThat(Number(p.open_interest_base) >= 0 && Number(p.open_interest_notional) >= 0);
    for (const key of ['provider_mid_price','premium','mark_mid_basis_bps','oracle_mid_basis_bps']) financial(p[key], key === 'provider_mid_price', true);
  } else requireThat(s.perp_freshness !== 'FRESH');
  if (v.observation_status === 'AVAILABLE') requireThat(v.order_book && v.perp_context && s.connection_state === 'CONNECTED' && s.subscription_state === 'OBSERVED' && ['l2','perp','metadata'].every(k => s[`${k}_freshness`] === 'FRESH'));
  return structuredClone(value) as LiveStreamSnapshot;
}
export function checkedLiveEnvelope(value: unknown, market: LiveMarketId, now = Date.now()): LiveMarketStreamEnvelope {
  const v = object(value);
  requireThat(v.contract_version === 'phase152-v1' && v.market === market, 'Invalid contract or market');
  const snapshot = checkedLiveSnapshot(v.payload, market, now);
  requireThat(v.observer_instance_id === snapshot.status.observer_instance_id && v.connection_generation === snapshot.status.connection_generation && integer(v.sequence, 1), 'Mismatched observer/generation identity');
  requireThat(v.observation_status === snapshot.observation_status); stamp(v.emitted_at, now);
  requireThat(Math.abs(Date.parse(String(v.emitted_at)) - Date.parse(snapshot.status.evaluated_at)) <= 1000 && now - Date.parse(String(v.emitted_at)) <= 30000, 'Stale emission');
  return structuredClone(value) as LiveMarketStreamEnvelope;
}
export function checkedLiveHistory(value: unknown, market: LiveMarketId, observer: string, limit: number, now = Date.now()): LiveMarketHistory {
  const v = object(value);
  requireThat(v.contract_version === 'phase152-v1' && v.market === market && v.observer_instance_id === observer && v.read_only === true && v.simulated === false && v.continuous_history_verified === false, 'Retired or invalid history boundary');
  requireThat(Array.isArray(v.points) && v.points.length <= limit && limit <= 1000);
  for (const key of ['retained_point_count','evicted_point_count','gap_count','max_points']) requireThat(integer(v[key]));
  requireThat(Number(v.max_points) >= 1 && Number(v.max_points) <= 3600 && Number(v.retained_point_count) <= Number(v.max_points));
  stamp(v.coverage_start, now, true); stamp(v.coverage_end, now, true); textList(v.limitations);
  for (const raw of v.points) {
    const p = object(raw); requireThat(p.market === market && p.observer_instance_id === observer && integer(p.connection_generation,1) && choice(p.kind,['L2','PERP_CONTEXT']) && choice(p.source,sources) && choice(p.observation_status,observations));
    stamp(p.observed_at, now); stamp(p.source_timestamp, now, p.kind === 'PERP_CONTEXT');
    requireThat(p.kind !== 'PERP_CONTEXT' || p.source_timestamp === null);
    for (const key of ['midpoint','best_bid','best_ask','spread','mark','oracle','funding','open_interest']) financial(p[key], !['funding','open_interest'].includes(key), true);
    requireThat((p.kind === 'L2' ? ['mark','oracle','funding','open_interest'] : ['midpoint','best_bid','best_ask','spread']).every(k => p[k] === null), 'Mixed history component');
  }
  return structuredClone(value) as LiveMarketHistory;
}
export function checkedLiveProviders(value: unknown, market: LiveMarketId, now = Date.now()): LiveProviderHealth {
  const v = object(value), ids = ['HYPERLIQUID_MID','HYPERLIQUID_ORACLE','HYPERLIQUID_MARK','REDSTONE','KRAKEN','COINGECKO','YAHOO_FINANCE'];
  requireThat(v.contract_version === 'phase152-v1' && v.market === market && v.read_only === true && v.authority === 'NONE' && v.consensus_price === null && v.independent_usable_external_sources === 0);
  requireThat(Array.isArray(v.providers) && v.providers.length === ids.length); textList(v.limitations);
  const seen = new Set();
  for (const raw of v.providers) {
    const p = object(raw), m = object(p.mapping);
    requireThat(choice(p.provider,ids) && !seen.has(p.provider)); seen.add(p.provider);
    requireThat(m.market === market && m.provider === p.provider && m.authority === 'NONE' && p.authority === 'NONE' && p.simulated === false);
    requireThat(choice(p.status,['HEALTHY','DEGRADED','STALE','ERROR','DISABLED']) && typeof p.enabled === 'boolean' && typeof p.stale === 'boolean' && typeof p.event_time_verified === 'boolean');
    requireThat(choice(m.mapping_status,['VALIDATED','UNCONFIGURED','UNVERIFIED','UNAVAILABLE']) && typeof m.enabled === 'boolean');
    requireThat(choice(p.health_basis,['EXCHANGE_EVENT_TIME','RECEIPT_TIME','NONE']) && typeof p.independent_source_group === 'string');
    const transports=['NATIVE','LIVE_WS','PUBLIC_HTTP','DEMO','REST'];
    requireThat(choice(p.transport,transports) && choice(m.transport,transports));
    requireThat(p.transport_quality === null || choice(p.transport_quality,['PRIMARY','FALLBACK','SIMULATED']));
    requireThat(p.error === null || choice(p.error,['UNCONFIGURED','UNAVAILABLE','SOURCE_UNAVAILABLE','EVENT_TIME_UNKNOWN']));
    for (const key of ['native_symbol','expected_source_id']) requireThat(m[key] === null || typeof m[key] === 'string');
    requireThat(p.source_id === null || typeof p.source_id === 'string');
    requireThat(choice(p.role,['ORACLE','NATIVE_ORACLE','VENUE_REFERENCE','EXECUTION_VENUE','PERP_MARK','AGGREGATOR_REFERENCE']));
    if (String(p.provider).startsWith('HYPERLIQUID')) requireThat(p.independent_source_group === 'HYPERLIQUID');
    financial(p.price,true,true); stamp(p.source_timestamp,now,true); stamp(p.observed_at,now,true); stamp(m.last_validated_configuration,now,true);
    requireThat(p.age_seconds === null || typeof p.age_seconds === 'number' && Number.isFinite(p.age_seconds) && p.age_seconds >= -1);
  }
  return structuredClone(value) as LiveProviderHealth;
}
export type ReceivedSnapshot = { snapshot: LiveStreamSnapshot; receivedAt: number; transitSeconds: number };
export function liveFreshness(e: ReceivedSnapshot | null, now: number, current: boolean) {
  const s = e?.snapshot.status;
  const age = (key: 'l2'|'perp'|'metadata') => e && s ? advancingAge(s[`${key}_age_seconds`],e.receivedAt,now,e.transitSeconds) : null;
  const ages = { l2: age('l2'), perp: age('perp'), metadata: age('metadata') };
  const fresh = (key: keyof typeof ages) => !!(current && s && s[`${key}_freshness`] === 'FRESH' && ages[key] !== null && ages[key]! <= s[`${key}_stale_after_seconds`]);
  const metadata = !!(fresh('metadata') && e?.snapshot.metadata.metadata_status === 'EXCHANGE_VERIFIED' && ['BOOTSTRAPPING','CONNECTED','DEGRADED','STALE'].includes(s?.connection_state ?? ''));
  return { ages, metadata, book: !!(metadata && fresh('l2') && e?.snapshot.order_book), perp: !!(metadata && fresh('perp') && e?.snapshot.perp_context) };
}
