import { compareDecimal } from '../../utils/format';
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { generalizedDiscoveryQuery, useGeneralizedMarketSelection } from '../../stores/researchMarkets';
import { marketCatalogDeadline, marketResearchAvailability, marketUniverseKey, matchesMarketResearchHandoff } from '../../utils/marketUniverse';
import { workspaceHref } from '../../utils/navigation';
import { useMarketSummaries } from '../../hooks/useMarketSummaries';
import { observedNumber, type MarketSummary } from '../../utils/marketSummaries';
import { Badge } from '../Badge';
import { Panel, StatusBanner } from '../TerminalPrimitives';

const pageSize = 12;
const emptyFilters = { search: '', venue: '', listing: '', metadata: '', research: '' };
const availabilityLabels = {
  'check-required': 'PAPER check required',
  unsupported: 'Unsupported',
  unavailable: 'Evidence unavailable',
};

const sorts = {
  alphabetical: 'Symbol',
  day_notional_volume: '24h volume',
  funding_rate: 'Hourly funding',
  mark_price: 'Mark price',
} as const;
type Sort = keyof typeof sorts;

const metadataSources = {
  OFFICIAL_SDK_CORE_META: 'Hyperliquid Core metadata',
  OFFICIAL_SDK_HIP3_META: 'Hyperliquid HIP-3 metadata',
};

function sourceStatus(row: MarketSummary | undefined, current: boolean, loading: boolean, fresh: boolean, error?: string) {
  if (!fresh) return 'Stale catalog';
  if (error) return error;
  if (loading) return 'Updating';
  if (!row) return 'Unavailable';
  if (row.error === 'CATALOG_CHANGED') return 'Catalog changed · refresh discovery';
  if (row.error === 'CAPACITY') return 'Unavailable · namespace budget';
  if (row.error === 'RATE_LIMITED') return 'Provider rate limit';
  if (row.error === 'TIMEOUT') return 'Provider timeout';
  if (row.status === 'ERROR') return `Provider error · ${row.error?.toLowerCase().replaceAll('_', ' ')}`;
  if (row.status === 'CURRENT') return current ? 'Current' : 'Stale';
  return row.status[0] + row.status.slice(1).toLowerCase();
}

export function MarketExplorer() {
  const discovery = useQuery(generalizedDiscoveryQuery);
  const launch = useGeneralizedMarketSelection(state => state.select);
  const catalog = discovery.data;
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState('');
  const [launchError, setLaunchError] = useState(false);
  const [sort, setSort] = useState<Sort>('alphabetical');
  const [, tick] = useState(0);
  const catalogDeadline = marketCatalogDeadline(catalog);
  const refreshDiscovery = discovery.refetch;
  const fresh = !discovery.isError && Date.now() < catalogDeadline;
  useEffect(() => {
    if (!catalogDeadline || discovery.isError) return;
    const check = () => {
      tick(previous => previous + 1);
      if (!document.hidden && Date.now() >= catalogDeadline) void refreshDiscovery({ cancelRefetch: false });
    };
    const timer = window.setTimeout(check, Math.max(0, catalogDeadline - Date.now()));
    document.addEventListener('visibilitychange', check);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', check);
    };
  }, [catalogDeadline, discovery.isError, refreshDiscovery]);
  const records = useMemo(() => {
    if (!catalog?.catalog) return [];
    return catalog.catalog.records.map((record, index) => ({
      record, key: marketUniverseKey(record.identity), decision: catalog.eligibility[index],
      research: marketResearchAvailability(catalog, index, fresh),
    }));
  }, [catalog, fresh]);
  const filtered = useMemo(() => {
    const query = filters.search.trim().toLowerCase();
    return records.filter(({ record, research }) =>
      (!query || [record.source_coin, record.identity.dex || 'core', record.identity.instrument_name]
        .some(value => value.toLowerCase().includes(query))) &&
      (!filters.venue || record.identity.instrument_type === filters.venue) &&
      (!filters.listing || record.listed === (filters.listing === 'listed')) &&
      (!filters.metadata || (fresh && record.metadata_status === 'EXCHANGE_VERIFIED') === (filters.metadata === 'verified')) &&
      (!filters.research || research === filters.research))
      .sort((a, b) => a.record.source_coin.localeCompare(b.record.source_coin));
  }, [records, filters, fresh]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(page, pageCount - 1);
  const visible = filtered.slice(current * pageSize, (current + 1) * pageSize);
  const detail = records.find(row => row.key === selected);
  const requested = detail && !visible.some(row => row.key === selected) ? [...visible, detail] : visible;
  const observations = useMarketSummaries(catalog?.catalog_fingerprint ? {
    catalogFingerprint: catalog.catalog_fingerprint,
    network: catalog.network,
    markets: requested.map(({ key, record, decision }) => ({
      key, metadataFingerprint: decision.metadata_fingerprint, universeIndex: record.universe_index, listed: record.listed,
    })),
  } : null, fresh);
  const detailSummary = observations.rows.get(selected);
  const detailCurrent = discovery.isFetching ? undefined : observations.current(detailSummary);
  const displayed = sort === 'alphabetical' ? visible : [...visible].sort((a, b) => {
    const first = observations.current(observations.rows.get(a.key))?.[sort];
    const second = observations.current(observations.rows.get(b.key))?.[sort];
    if (first == null) return second == null ? 0 : 1;
    return second == null ? -1 : compareDecimal(second, first);
  });
  function filter(name: keyof typeof emptyFilters, value: string) {
    setFilters(previous => ({ ...previous, [name]: value }));
    setPage(0);
  }
  function openResearch(row: (typeof records)[number]) {
    const handoff = {
      key: row.key,
      catalogFingerprint: catalog?.catalog_fingerprint ?? '',
      metadataFingerprint: row.decision.metadata_fingerprint,
    };
    if (discovery.isError || discovery.isFetching || !matchesMarketResearchHandoff(catalog, handoff)) {
      setLaunchError(true);
      return;
    }
    launch(handoff);
    window.location.hash = workspaceHref('paper');
  }

  return <div className="stack marketExplorer">
    <div className="experienceIntro">
      <div>
        <h1>Market Explorer</h1>
        <p>Browse Hyperliquid Core and HIP-3 perpetuals. Choose a market to test a hypothetical market-making scenario.</p>
      </div>
      <div className="explorerCardActions">
        <button type="button" disabled={discovery.isFetching} onClick={() => {
          setLaunchError(false);
          void discovery.refetch();
        }}>Refresh discovery</button>
        <button type="button" className="primary" disabled={!fresh || !requested.length || observations.isFetching}
          onClick={observations.refresh}>Refresh observations</button>
      </div>
    </div>
    <Panel title="Discovered markets" meta={catalog?.network}>
      <div className="explorerFilters">
        <label>Market or DEX<input type="search" placeholder="Symbol or DEX" value={filters.search}
          onChange={event => filter('search', event.target.value)} /></label>
        <label>Instrument type<select value={filters.venue} onChange={event => filter('venue', event.target.value)}>
          <option value="">All instruments</option><option value="CORE_PERP">Core</option><option value="HIP3_PERP">HIP-3</option>
        </select></label>
        <label>Listing<select value={filters.listing} onChange={event => filter('listing', event.target.value)}>
          <option value="">All listings</option><option value="listed">Listed</option><option value="delisted">Delisted</option>
        </select></label>
        <label>Metadata<select value={filters.metadata} onChange={event => filter('metadata', event.target.value)}>
          <option value="">All metadata</option><option value="verified">Current</option><option value="stale">Stale or unavailable</option>
        </select></label>
        <label>Research<select value={filters.research} onChange={event => filter('research', event.target.value)}>
          <option value="">All research states</option>
          {Object.entries(availabilityLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <label>Sort by<select value={sort} onChange={event => setSort(event.target.value as Sort)}>
          {Object.entries(sorts).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
        </select></label>
        <button type="button" onClick={() => { setFilters(emptyFilters); setPage(0); }}>Clear filters</button>
      </div>
      <p role="status" aria-live="polite">{discovery.isFetching ? 'Refreshing discovery metadata…' :
        `${filtered.length.toLocaleString()} of ${records.length.toLocaleString()} discovered markets`}</p>
      {discovery.isError && <StatusBanner tone="bad">Discovery could not be loaded. Refresh discovery to try again.</StatusBanner>}
      {!discovery.isError && catalog && !fresh && <StatusBanner>
        {catalog.availability === 'AVAILABLE' ? 'Catalog evidence expired.' :
          `Discovery is ${catalog.availability.toLowerCase()}.`} Research requires a current catalog.
      </StatusBanner>}
      {launchError && <StatusBanner tone="bad">The selection is out of date. Refresh discovery and select it again.</StatusBanner>}
      <p className="muted">Hyperliquid public observations are informational. The 24h mark comparison uses the provider’s previous-day reference. Financial sorting covers current observations on this page, in as-reported units.</p>
      {detail && <section className="explorerSelection" aria-label="Selected market details">
        <h3>{detail.record.source_coin} details</h3>
        <dl className="researchDetails">
          <div><dt>Canonical market</dt><dd><code>{detail.key}</code></dd></div>
          <div><dt>Mark price</dt><dd title={detailCurrent?.mark_price ?? undefined}>{observedNumber(detailCurrent?.mark_price)}</dd></div>
          <div><dt>Funding / hour</dt><dd>{observedNumber(detailCurrent?.funding_rate, '%')}</dd></div>
          <div><dt>Funding interval</dt><dd>1 hour</dd></div>
          <div><dt>Observed metadata</dt><dd><time dateTime={detail.record.observed_at}>{detail.record.observed_at}</time></dd></div>
          <div><dt>Metadata source</dt><dd>{metadataSources[detail.record.metadata_source] ?? 'Unavailable'}</dd></div>
          <div><dt>Catalog fingerprint</dt><dd><code>{catalog?.catalog_fingerprint}</code></dd></div>
          <div><dt>Size precision</dt><dd>{detail.record.sz_decimals} decimals</dd></div>
          <div><dt>Metadata status</dt><dd>{fresh ? detail.record.metadata_status : 'STALE'}</dd></div>
          <div><dt>Metadata fingerprint</dt><dd><code>{detail.decision.metadata_fingerprint}</code></dd></div>
          <div><dt>Observation status</dt><dd>{sourceStatus(detailSummary, !!detailCurrent, discovery.isFetching || observations.isFetching, fresh, observations.error)}</dd></div>
          <div><dt>Observation source</dt><dd>Hyperliquid public Info · metaAndAssetCtxs</dd></div>
          {detailSummary?.observed_at && <div><dt>Server receipt time</dt><dd><time dateTime={detailSummary.observed_at}>{detailSummary.observed_at}</time></dd></div>}
          <div><dt>Provider event time</dt><dd>Unavailable</dd></div>
          <div><dt>Price units</dt><dd>Provider quote per base · denomination not independently verified</dd></div>
          <div><dt>Volume units</dt><dd>Provider notional quote · denomination unverified</dd></div>
          <div><dt>Oracle price</dt><dd>{observedNumber(detailCurrent?.oracle_price)}</dd></div>
          <div><dt>Previous-day reference</dt><dd>{observedNumber(detailCurrent?.previous_day_price)}</dd></div>
          <div><dt>Mark / oracle basis</dt><dd>Unavailable · compatible denominations unverified</dd></div>
          {detailSummary?.observation_fingerprint && <div><dt>Observation fingerprint</dt><dd><code>{detailSummary.observation_fingerprint}</code></dd></div>}
          {!!detailSummary?.limitations.length && <div><dt>Source limitations</dt><dd>{detailSummary.limitations.join(' · ')}</dd></div>}
          <div><dt>Discovery decision</dt><dd>{detail.decision.reason.replaceAll('_', ' ').toLowerCase()}</dd></div>
        </dl>
      </section>}
      {filtered.length === 0 && !discovery.isFetching && !discovery.isError && <p>
        {records.length ? 'No markets match your filters.' : 'No market records are available.'}
      </p>}
      <div className="explorerCards">
        {displayed.map(row => {
          const { record, key, research } = row;
          const core = record.identity.instrument_type === 'CORE_PERP';
          const observed = observations.rows.get(key);
          const live = observations.current(observed);
          const status = record.listed ? sourceStatus(observed, !!live, observations.isFetching, fresh, observations.error) : 'Unsupported';
          const age = live?.observed_at ? Math.max(0, Math.floor((Date.now() - Date.parse(live.observed_at)) / 1000)) : null;
          return <article key={key} className="explorerCard">
            <div className="explorerCardHead">
              <h3>{record.source_coin}</h3><Badge tone={core ? 'blue' : 'neutral'}>{core ? 'Core' : 'HIP-3'}</Badge>
            </div>
            <p className="explorerContext">{record.identity.dex || 'Core'} · {record.identity.network === 'MAINNET' ? 'Mainnet' : 'Testnet'} · {record.listed ? 'Listed' : 'Delisted'}</p>
            <dl className="explorerMetrics">
              <div className="explorerMark"><dt>Mark price</dt><dd title={live?.mark_price ?? undefined}>{observedNumber(live?.mark_price)}</dd></div>
              <div><dt>vs. previous-day ref.</dt><dd>{live?.mark_change_vs_previous_day_percent == null ? 'Unavailable' :
                `${observedNumber(live.mark_change_vs_previous_day_percent)}%`}</dd></div>
              <div><dt>Funding / hour</dt><dd>{observedNumber(live?.funding_rate, '%')}</dd></div>
              <div><dt>24h notional volume</dt><dd>{observedNumber(live?.day_notional_volume, 'compact')}</dd></div>
              <div><dt>Open interest · base</dt><dd>{observedNumber(live?.open_interest_base)}</dd></div>
            </dl>
            <p className="explorerObservation"><Badge tone={live ? 'good' : 'neutral'}>{status}</Badge>
              {age !== null && <span>Public Info · {age}s ago</span>}
            </p>
            <p className="explorerContext">{metadataSources[record.metadata_source] ?? 'Metadata unavailable'} · {fresh ? 'Current' : 'Stale'}<br />
              {availabilityLabels[research]}</p>
            <div className="explorerCardActions">
              <button type="button" aria-label={`Details for ${record.source_coin}`} aria-pressed={selected === key}
                onClick={() => setSelected(selected === key ? '' : key)}>Details</button>
              <button type="button" className="primary" aria-label={`Open Research for ${record.source_coin}`}
                disabled={discovery.isFetching || research !== 'check-required'}
                onClick={() => openResearch(row)}>Open Research</button>
            </div>
          </article>;
        })}
      </div>
      {pageCount > 1 && <nav className="explorerPagination" aria-label="Market results pages">
        <button type="button" disabled={current === 0} onClick={() => setPage(current - 1)}>Previous</button>
        <span role="status">Page {current + 1} of {pageCount}</span>
        <button type="button" disabled={current + 1 === pageCount} onClick={() => setPage(current + 1)}>Next</button>
      </nav>}
    </Panel>
  </div>;
}
