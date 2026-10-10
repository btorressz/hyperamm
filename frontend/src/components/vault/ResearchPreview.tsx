import type { ResearchPreviewResponse } from '../../types';
import { Panel, StatusBanner } from '../TerminalPrimitives';
export function ResearchPreview({ preview, current }: { preview: ResearchPreviewResponse; current: boolean }) {
  return <Panel title="Research configuration preview" meta={current ? 'VALIDATED CURRENT DRAFT' : 'OUTDATED PREVIEW'}>
    {!current && <StatusBanner>Outdated preview: draft or backend connection changed. Revalidate before using this configuration.</StatusBanner>}
    <p>Illustrative utilization ceiling: <strong>{preview.illustrative_utilization_ceiling_quote} quote</strong>.
      Configuration-derived hypothetical limit; no venue margin or guaranteed allocation.</p>
    <p>Funding {preview.normalized_config.paper_funding_accounting_enabled ? 'enabled' : 'disabled'} · interval {preview.normalized_config.paper_funding_interval_seconds} seconds.
      Scenario rates and sampled positions determine actual simulated accruals; this preview predicts no funding payment.</p>
    <p>Baseline: {preview.baseline_preset_id}. Last validated configuration · {preview.research_config_version} · preset version {preview.selected_preset_version ?? 'Unavailable'}.</p>
    <details className="researchInset"><summary>Inspect validated assumptions and fingerprint</summary>
      <code className="researchFingerprint">{preview.config_fingerprint}</code>
      <dl className="researchDetails">{Object.entries(preview.normalized_config).map(([key, value]) =>
        <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>
    </details>
    <div className="researchTableScroll"><table><caption>Configuration differences from selected preset</caption>
      <thead><tr><th>Field</th><th>Old value</th><th>New value</th><th>Difference</th><th>Units</th></tr></thead>
      <tbody>{preview.changed_fields.map(d => <tr key={d.field}><td>{d.field}</td><td>{String(d.old_value)}</td><td>{String(d.new_value)}</td><td>{d.difference ?? 'Unavailable'}</td><td>{d.units}</td></tr>)}</tbody>
    </table></div>
    {!preview.changed_fields.length && <p className="muted">No differences from preset.</p>}
    {preview.warnings.map(w => <p key={w} role="status">{w}</p>)}
    <ul className="researchReasons">{preview.limitations.map(l => <li key={l}>{l}</li>)}</ul>
  </Panel>;
}
