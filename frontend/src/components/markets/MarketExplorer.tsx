import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { generalizedDiscoveryQuery, useGeneralizedMarketSelection } from '../../stores/researchMarkets';
import { marketCatalogDeadline, marketResearchAvailability, marketUniverseKey, matchesMarketResearchHandoff } from '../../utils/marketUniverse';
import { workspaceHref } from '../../utils/navigation';
import { Badge } from '../Badge';
import { Panel, StatusBanner } from '../TerminalPrimitives';

const pageSize = 12;
const emptyFilters = { search: '', venue: '', listing: '', metadata: '', research: '' };
const availabilityLabels = {
  'check-required': 'PAPER check required',
  unsupported: 'Unsupported',
  unavailable: 'Evidence unavailable',
};

export function MarketExplorer() {
  const discovery = useQuery(generalizedDiscoveryQuery);
  const launch = useGeneralizedMarketSelection(state => state.select);
  const catalog = discovery.data;
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState('');
  const [launchError, setLaunchError] = useState(false);
  const fresh = !discovery.isError && Date.now() < marketCatalogDeadline(catalog);
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
      (!filters.research || research === filters.research));
  }, [records, filters, fresh]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(page, pageCount - 1);
  const detail = records.find(row => row.key === selected);
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
      <button type="button" disabled={discovery.isFetching} onClick={() => {
        setLaunchError(false);
        void discovery.refetch();
      }}>Refresh discovery</button>
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
      <p className="muted">Discovery provides listing metadata. Price and funding observations are unavailable here. PAPER eligibility is checked for each proposal.</p>
      {detail && <section className="explorerSelection" aria-label="Selected market details">
        <h3>{detail.record.source_coin} details</h3>
        <dl className="researchDetails">
          <div><dt>Canonical market</dt><dd><code>{detail.key}</code></dd></div>
          <div><dt>Observed metadata</dt><dd><time dateTime={detail.record.observed_at}>{detail.record.observed_at}</time></dd></div>
          <div><dt>Metadata source</dt><dd>{detail.record.metadata_source}</dd></div>
          <div><dt>Catalog fingerprint</dt><dd><code>{catalog?.catalog_fingerprint}</code></dd></div>
          <div><dt>Discovery decision</dt><dd>{detail.decision.reason.replaceAll('_', ' ').toLowerCase()}</dd></div>
        </dl>
      </section>}
      {filtered.length === 0 && !discovery.isFetching && !discovery.isError && <p>
        {records.length ? 'No markets match your filters.' : 'No market records are available.'}
      </p>}
      <div className="explorerCards">
        {filtered.slice(current * pageSize, (current + 1) * pageSize).map(row => {
          const { record, key, research } = row;
          const core = record.identity.instrument_type === 'CORE_PERP';
          return <article key={key} className="explorerCard">
            <div className="explorerCardHead">
              <h3>{record.source_coin}</h3><Badge tone={core ? 'blue' : 'neutral'}>{core ? 'Core' : 'HIP-3'}</Badge>
            </div>
            <dl>
              <div><dt>DEX</dt><dd>{record.identity.dex || 'Core'}</dd></div>
              <div><dt>Listing</dt><dd>{record.listed ? 'Listed' : 'Delisted'}</dd></div>
              <div><dt>Size precision</dt><dd>{record.sz_decimals} decimals</dd></div>
              <div><dt>Metadata source</dt><dd>Official Hyperliquid SDK</dd></div>
              <div><dt>Metadata freshness</dt><dd>{fresh ? 'Current' : 'Stale or unavailable'}</dd></div>
              <div><dt>Research</dt><dd>{availabilityLabels[research]}</dd></div>
            </dl>
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
