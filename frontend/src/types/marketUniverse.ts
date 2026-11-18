export type MarketUniverseNetwork = 'MAINNET' | 'TESTNET';
export type MarketUniverseAvailability = 'AVAILABLE' | 'PARTIAL' | 'STALE' | 'UNAVAILABLE' | 'DISABLED';
export type MarketUniverseError =
  | 'DISABLED' | 'CLOSED' | 'TIMEOUT' | 'RATE_LIMITED' | 'FORBIDDEN' | 'UPSTREAM_ERROR'
  | 'NETWORK_ERROR' | 'SDK_UNAVAILABLE' | 'CLEANUP_ERROR' | 'MISSING_METADATA'
  | 'INVALID_DATA' | 'NETWORK_MISMATCH' | 'NAMESPACE_CONFLICT' | 'UNSUPPORTED_METADATA'
  | 'RESPONSE_TOO_LARGE' | 'CATALOG_CAPACITY';

interface Versioned {
  contract_version: 'phase180b-v2';
}

interface ReadOnlyDiscovery {
  read_only: true;
  authority: 'NONE';
  paper_research_eligible: false;
  execution_eligible: false;
}

export interface MarketUniverseIdentity extends Versioned {
  venue: 'HYPERLIQUID';
  network: MarketUniverseNetwork;
  instrument_type: 'CORE_PERP' | 'HIP3_PERP';
  dex: string;
  instrument_name: string;
}

export interface MarketUniverseMetadata extends Versioned {
  identity: MarketUniverseIdentity;
  source_coin: string;
  universe_index: number;
  sz_decimals: number;
  listed: boolean;
  metadata_status: 'EXCHANGE_VERIFIED' | 'STALE';
  metadata_source: 'OFFICIAL_SDK_CORE_META' | 'OFFICIAL_SDK_HIP3_META';
  observed_at: string;
}

export interface MarketUniverseEligibility extends Versioned, ReadOnlyDiscovery {
  identity: MarketUniverseIdentity;
  metadata_fingerprint: string;
  evaluated_at: string;
  discovery_eligible: boolean;
  reason: 'DISCOVERABLE' | 'NOT_LISTED' | 'FUTURE_TIMESTAMP' | 'STALE_METADATA';
}

export type MarketUniverseCheck = Versioned & (
  | { status: 'REFRESHED'; observed_at: string; error: null }
  | { status: 'FAILED' | 'SKIPPED'; observed_at: null; error: MarketUniverseError }
);

export interface MarketUniverseResponse extends Versioned, ReadOnlyDiscovery {
  schema_version: 'phase181-v1';
  network: MarketUniverseNetwork;
  availability: MarketUniverseAvailability;
  catalog: (Versioned & { records: MarketUniverseMetadata[]; read_only: true; authority: 'NONE' }) | null;
  catalog_fingerprint: string | null;
  eligibility: MarketUniverseEligibility[];
  evaluated_at: string;
  max_age_seconds: number;
  inventory: MarketUniverseCheck | null;
  namespaces: (MarketUniverseCheck & { dex: string })[];
  error: MarketUniverseError | null;
  limitations: ['METADATA_ONLY', 'NO_PAPER_RESEARCH', 'NO_EXECUTION'];
}
