import type { ResearchMarketProfile } from '../../types';
import { Badge } from '../Badge';
export function ResearchMarketDetails({profile: p}: {profile: ResearchMarketProfile}) {
  return <div className="researchInset">
    <Badge tone={p.research_supported ? 'blue' : 'bad'}>{p.metadata_status === 'DEMO_PROFILE' ? 'DEMO · SIMULATED METADATA'
      : p.metadata_status === 'EXCHANGE_VERIFIED' ? 'EXCHANGE-VERIFIED METADATA' : 'MARKET UNAVAILABLE'}</Badge>
    <p>{p.display_name} · Hyperliquid native perpetual · PAPER / SIMULATED</p>
    <dl className="researchDetails">
      <div><dt>Hypothetical reference price (quote)</dt><dd>{p.simulated_reference_price} · fixed research anchor</dd></div>
      <div><dt>Size precision</dt><dd>{p.sz_decimals ?? 'Unavailable'} decimal places</dd></div>
      <div><dt>Native asset index</dt><dd>{p.asset_index ?? 'Unverified / unavailable'}</dd></div>
      <div><dt>Profile version</dt><dd>{p.profile_version}</dd></div>
      <div><dt>Metadata source</dt><dd>{p.metadata_source}</dd></div>
      {p.metadata_observed_at && <div><dt>Metadata observed (UTC)</dt><dd>{p.metadata_observed_at} · age {Math.floor(p.metadata_age_seconds ?? 0)}s at retrieval</dd></div>}
    </dl>
    <p className="muted">{p.research_price_rules}</p>
    {p.unavailable_reason && <p className="muted">{p.unavailable_reason}</p>}
    <details><summary>Research profile fingerprint and limitations</summary><code className="researchFingerprint">{p.profile_fingerprint}</code>
      <ul>{p.limitations.map(s => <li key={s}>{s}</li>)}</ul></details>
  </div>;
}
