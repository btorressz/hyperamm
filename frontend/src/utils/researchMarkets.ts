import type { ResearchMarketCatalog, ResearchMarketEvidence, ResearchMarketProfile } from '../types';

export const researchMarketIds = ['BTC', 'ETH', 'SOL'] as const;
const fingerprint = (x: unknown) => typeof x === 'string' && /^[a-f0-9]{64}$/.test(x);
export function checkedMarketCatalog(value: ResearchMarketCatalog): ResearchMarketCatalog {
  const fail = () => { throw new Error('Malformed research market catalog; market remains unvalidated.'); };
  if (!value || value.research_only !== true || value.execution_mode !== 'PAPER' || !value.catalog_version
      || !Array.isArray(value.markets) || value.markets.length !== 3) fail();
  for (const id of researchMarketIds) {
    const matches = value.markets.filter(p => p?.market === id);
    if (matches.length !== 1) fail();
    const p = matches[0];
    if (p.display_name !== `${id}-PERP` || p.exchange !== 'HYPERLIQUID' || p.dex !== '' || p.market_type !== 'PERPETUAL'
        || !p.profile_version || !fingerprint(p.profile_fingerprint) || !Array.isArray(p.limitations)
        || typeof p.simulated_reference_price !== 'string' || !/^\d+(\.\d+)?$/.test(p.simulated_reference_price)
        || !/[1-9]/.test(p.simulated_reference_price) || typeof p.research_price_rules !== 'string'
        || !['DEMO_PROFILE','EXCHANGE_VERIFIED','UNAVAILABLE'].includes(p.metadata_status)
        || typeof p.research_supported !== 'boolean') fail();
    if (p.research_supported && (!Number.isInteger(p.sz_decimals) || p.sz_decimals! < 0 || p.sz_decimals! > 6
        || p.metadata_status === 'UNAVAILABLE' || p.listed === false)) fail();
    if (p.metadata_status === 'DEMO_PROFILE' && (p.asset_index !== null || p.listed !== null
        || p.metadata_source !== 'PINNED_RESEARCH_FIXTURE' || p.metadata_observed_at !== null)) fail();
    if (p.metadata_status === 'EXCHANGE_VERIFIED' && (p.listed !== true || !p.research_supported
        || !Number.isSafeInteger(p.asset_index) || p.asset_index! < 0
        || p.metadata_source !== 'OFFICIAL_SDK_NATIVE_META' || !p.metadata_observed_at
        || !Number.isFinite(Date.parse(p.metadata_observed_at)) || p.metadata_age_seconds === null
        || !Number.isFinite(p.metadata_age_seconds) || p.metadata_age_seconds < 0)) fail();
    if (p.metadata_status === 'UNAVAILABLE' && p.research_supported) fail();
  }
  return value;
}

export function checkedMarketEvidence<T extends ResearchMarketEvidence>(value: T, captured: ResearchMarketProfile): T {
  if (value.research_market !== captured.market || value.market_profile_fingerprint !== captured.profile_fingerprint
      || value.market_profile_version !== captured.profile_version || value.metadata_status !== captured.metadata_status
      || value.metadata_source !== captured.metadata_source) {
    throw new Error('Research response market/profile evidence does not match the captured request. Reload the market catalog and retry.');
  }
  return value;
}
