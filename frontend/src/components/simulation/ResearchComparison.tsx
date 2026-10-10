import type { ResearchComparison } from '../../types';
import { SimulationPanel } from '../SimulationPanel';
import { SimulationTrace } from './SimulationTrace';
import { Panel } from '../TerminalPrimitives';
import { accountingValue } from '../../utils/researchEvidence';
export function ResearchComparisonView({data}: {data: ResearchComparison}) {
  const equivalent = data.baseline_result.dataset_fingerprint === data.custom_result.dataset_fingerprint
    && data.baseline_result.strategy_fingerprint === data.custom_result.strategy_fingerprint
    && data.baseline_result.engine_version === data.custom_result.engine_version;
  if (!equivalent || !data.simulated) return <p role="alert">Comparison evidence is incompatible; a controlled comparison is unavailable.</p>;
  return <section aria-label="Baseline vs customized research" className="stack">
    <h2>Baseline vs customized PAPER research · {data.scenario} · {data.frame_count} frames</h2>
    <p>Both runs share one captured strategy, agent and risk configuration and one deterministic dataset. Differences are customized accounting assumptions.</p>
    <div className="researchComparisonGrid">{(['baseline','custom'] as const).map(key => {
      const result = key === 'baseline' ? data.baseline_result : data.custom_result;
      const provenance = key === 'baseline' ? data.baseline_provenance : data.custom_provenance;
      return <div className="stack" key={key}><h3>{key === 'baseline' ? 'Selected preset baseline' : 'Customized configuration'}</h3>
        <SimulationPanel m={result.metrics}/><p>Fees: {accountingValue(result.vault?.fees_quote)} quote · funding: {accountingValue(result.vault?.funding_quote)} quote · ending capital utilization: {accountingValue(result.vault?.capital_utilization, true)}</p>
        <details className="researchInset"><summary>Inspect {key} trace and provenance</summary>
          <p>Schema {provenance.research_config_version} · preset {provenance.selected_preset_id} v{provenance.selected_preset_version}</p>
          <code className="researchFingerprint">Configuration: {provenance.config_fingerprint}</code>
          <code className="researchFingerprint">Engine: {result.engine_version}</code>
          <code className="researchFingerprint">Run: {result.run_fingerprint}</code>
          <code className="researchFingerprint">Dataset: {result.dataset_fingerprint}</code>
          <code className="researchFingerprint">Strategy: {result.strategy_fingerprint}</code>
          <SimulationTrace result={result}/>
        </details>
      </div>;
    })}</div>
    <Panel title="Actual simulation deltas" meta="CUSTOM MINUS BASELINE">
      <div className="researchTableScroll"><table><thead><tr><th>Metric</th><th>Difference</th></tr></thead>
        <tbody>{Object.entries(data.comparison_deltas).map(([key,value]) => <tr key={key}><td>{key}</td><td>{accountingValue(value)}</td></tr>)}</tbody></table></div>
      <p>Drawdown, utilization and halt differences use backend fractions; return_pct is percentage points. Fees, funding, equity and PnL are quote currency. Fill count is a count.</p>
      <p>Risk-state observations — baseline: {JSON.stringify(data.risk_state_counts.baseline)}; customized: {JSON.stringify(data.risk_state_counts.custom)}. Counts do not establish causality or future performance.</p>
      <ul className="researchReasons">{data.limitations.map(l => <li key={l}>{l}</li>)}</ul>
    </Panel>
  </section>;
}
