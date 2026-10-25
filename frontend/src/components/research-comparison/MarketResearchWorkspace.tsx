import {useLiveMarket} from '../../hooks/useLiveMarket';
import {useMarketResearchComparison} from '../../hooks/useMarketResearchComparison';
import type {LiveMarketId} from '../../types';
import {Panel,Empty,StatusBanner} from '../TerminalPrimitives';
import {Badge} from '../Badge';
import {ComparisonPriceChart} from './ComparisonPriceChart';
import {ComparisonMetricTable} from './ComparisonMetricTable';
import {ComparisonConfidence} from './ComparisonConfidence';
import {ComparisonPerformanceContext} from './ComparisonPerformanceContext';
import {comparisonTimestamp,capturedEvidenceLabel} from '../../utils/marketResearchComparison';
import '../../phase154.css';
export function MarketResearchWorkspace() {
  const {now}=useLiveMarket();
  const {r,l,compare,pending,error}=useMarketResearchComparison(now);
  const selected=r.results.find(x=>x.id===r.selectedId);
  const artifact=r.artifact, data=artifact?.data;
  return <div className="marketResearchWorkspace stack">
    <div className="researchPageTitle"><div><h2>Market vs Research</h2><p className="muted">Choose completed PAPER evidence → explicitly capture observations → inspect descriptive differences</p></div><Badge tone="neutral">READ ONLY · RESEARCH</Badge></div>
    <Panel title="Select independent evidence" meta="NO AUTOMATIC RESEARCH OR OPTIMIZATION">
      <div className="comparisonSelection">
        <label>Observed native market<select aria-label="Comparison observed market" value={l.selectedLiveMarket} onChange={e=>l.selectMarket(e.target.value as LiveMarketId)}>{(['BTC','ETH','SOL'] as const).map(m=><option key={m} value={m}>{m}-PERP</option>)}</select></label>
        <label>Completed PAPER result<select aria-label="Completed PAPER result" value={r.selectedId} onChange={e=>r.select(e.target.value)}><option value="">Choose completed result</option>{r.results.map(x=><option key={x.id} value={x.id}>{x.research.research_market}-PERP · {x.research.scenario} · {x.label} · {x.id.slice(0,10)}</option>)}</select></label>
      </div>
      {!r.results.length && <Empty>No completed research result. <a href="#/simulation">Run an isolated PAPER scenario in Simulation</a>, then return here. Optimizer summaries are not individual completed simulations.</Empty>}
      {selected && <div className="comparisonSelected"><p>Captured research: <strong>{selected.research.research_market}-PERP · {selected.research.scenario}</strong> · {selected.research.performance.frame_count} frames · {selected.research.metadata_status??'Legacy metadata unavailable'}</p><code>{selected.id}</code>
        {!selected.research.assumptions && <p>Research assumption detail unavailable for this prior result</p>}
        {selected.research.research_market!==l.selectedLiveMarket && <StatusBanner>NOT_COMPARABLE · Observed and research markets differ. No cross-asset price difference will be calculated.</StatusBanner>}
      </div>}
      <div className="actions"><button className="primary" disabled={!selected||pending} onClick={compare}>{pending?'Capturing comparison…':'Compare with observed market'}</button>
        {data && <button disabled={!selected||pending} onClick={compare}>Refresh observed comparison</button>}</div>
      <p className="muted">Each action captures the server's accepted in-memory snapshot. Later live updates do not recalculate this result or refresh venue networking. Live source: {l.evidence?.snapshot.observation_status??'Unavailable'}.</p>
      {error && <p role="alert" className="inlineError">{error}</p>}
    </Panel>
    {!data && selected && <><StatusBanner>Research evidence is available. Observed evidence has not been captured for comparison. Use the explicit comparison action.</StatusBanner><ComparisonPerformanceContext research={selected.research}/></>}
    {data && <section className="stack" aria-label="Frozen market research comparison">
      <StatusBanner>{artifact.historicalReason?`HISTORICAL ARTIFACT · ${artifact.historicalReason}`:'FROZEN CAPTURE · Values and freshness are reported at capture, not continuously current.'} Explicit refresh is required to capture newer observed evidence.</StatusBanner>
      <div className="comparisonEvidenceGrid">
        <Panel title="Observed native market" meta={`${data.market}-PERP · ${data.observed.snapshot.observation_status}`}>
          <p>{data.observed.snapshot.status.connection_state} · {data.observed.snapshot.metadata.source} · {data.observed.snapshot.metadata.metadata_status}</p>
          <p><strong>Book: {capturedEvidenceLabel(data,'book',artifact.historicalReason)}</strong><br/><strong>Context: {capturedEvidenceLabel(data,'context',artifact.historicalReason)}</strong></p>
          <p>L2 {data.observed.snapshot.status.l2_freshness} · captured age {data.observed.snapshot.status.l2_age_seconds??'Unavailable'}s<br/>Context {data.observed.snapshot.status.perp_freshness} · captured receipt age {data.observed.snapshot.status.perp_age_seconds??'Unavailable'}s</p>
          <p>L2 source: {data.observed.snapshot.order_book?.source??'Unavailable'}<br/>Context source: {data.observed.snapshot.perp_context?.source??'Unavailable'}</p>
          <p>Acquisition gap: {data.observed.acquisition_gap_seconds??'Unavailable'} seconds. Context economic event time: UNKNOWN.</p>
        </Panel>
        <Panel title="Hypothetical research assumptions" meta={`${data.research.research_market}-PERP · PAPER`}>
          <p>{data.research.scenario} · {data.research.metadata_status??'Legacy metadata unavailable'} · profile {data.research.market_profile_version??'Unavailable'}</p>
          {data.research.assumptions?<><p>Last consumed dataset frame #{data.research.assumptions.representative_frame_sequence}, of {data.research.assumptions.frame_count} frames. This frame does not represent the entire scenario.</p><time>{comparisonTimestamp(data.research.assumptions.representative_frame_timestamp)}</time><p>Reference source: {data.research.assumptions.reference_source}</p></>:<p>Research assumption detail unavailable for this prior result</p>}
          <p>Comparison eligibility: <strong>{data.comparison_status}</strong></p>
        </Panel>
      </div>
      <ComparisonPriceChart data={data} historicalReason={artifact.historicalReason}/>
      <ComparisonMetricTable title="Price & spread differences" historicalReason={artifact.historicalReason} metrics={data.metrics.filter(m=>['midpoint','best_bid','best_ask','mark_price','oracle_price','spread_quote','spread_bps'].includes(m.metric_name))}/>
      <ComparisonMetricTable title="Liquidity & book assumptions" historicalReason={artifact.historicalReason} metrics={data.metrics.filter(m=>m.metric_name.includes('depth'))}/>
      <Panel title="Visible depth measurement" meta="TOP FIVE DISTINCT PRICES PER SIDE · BASE UNITS">
        <p>Observed native book {data.observed.depth_level_count} retained levels per side · {data.observed.snapshot.order_book?.truncated?'TRUNCATED to reported visible levels':'bounded visible depth'}.</p>
        <p>Research: {data.research.assumptions?.depth_level_count??'Unavailable'} modeled levels per side. Repeated modeled prices or fewer than five levels block a like-for-like depth delta. Neither side establishes executable liquidity.</p>
      </Panel>
      <ComparisonMetricTable title="Funding & perpetual context" historicalReason={artifact.historicalReason} metrics={data.metrics.filter(m=>['funding_rate','open_interest_base'].includes(m.metric_name))}/>
      <Panel title="Funding conventions" meta="RAW RATES · NO ANNUALIZATION"><p>Native venue: raw hourly rate; economic event time unknown. Research: raw scenario rate per sampled research interval. {data.research.research_configuration?`Captured interval: ${data.research.research_configuration.normalized_config.paper_funding_interval_seconds}s.`:'Research accounting interval provenance unavailable.'} The subtraction is descriptive; it does not compare settled payments.</p></Panel>
      <ComparisonPerformanceContext research={data.research}/>
      <ComparisonConfidence data={data}/>
      <Panel title="Provenance & audit details" meta="STRUCTURALLY VALIDATED · NOT AUTHENTICATED">
        <p>Client-supplied fingerprints do not prove server execution. No durable run registry or cryptographic execution attestation is provided.</p>
        <details><summary>Inspect captured identities and independent timestamps</summary><dl>
          {Object.entries(data.provenance).map(([k,v])=><div key={k}><dt>{k}</dt><dd><code>{v??'Unavailable'}</code></dd></div>)}
          {(['run_fingerprint','dataset_fingerprint','strategy_fingerprint','market_profile_fingerprint'] as const).map(k=><div key={k}><dt>{k}</dt><dd><code>{data.research[k]??'Unavailable'}</code></dd></div>)}
          <div><dt>research_assumptions_fingerprint</dt><dd><code>{data.research.assumptions?.assumption_fingerprint??'Unavailable'}</code></dd></div>
          <div><dt>comparison_processing_time</dt><dd>{comparisonTimestamp(data.generated_at)}</dd></div></dl></details>
      </Panel>
    </section>}
    <p className="muted">A bounded in-memory selection retains up to three completed research summaries. Financial results are not persisted to browser storage.</p>
  </div>;
}
