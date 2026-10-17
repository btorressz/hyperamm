import type {ResearchEvidenceSummary} from '../../types';
import {Panel,Metrics} from '../TerminalPrimitives';
import {exactDecimal} from '../../utils/orderView';
import {shiftDecimal} from '../../utils/researchVault';
export function ComparisonPerformanceContext({research:r}:{research:ResearchEvidenceSummary}) {
  const p=r.performance,c=r.research_configuration;
  const decimal=(v:string|null)=>exactDecimal(v);
  const fraction=(v:string|null)=>v===null?'Unavailable':`${shiftDecimal(v,2)}%`;
  return <Panel title="Completed PAPER performance · hypothetical" meta={`${r.research_market}-PERP · ${r.scenario}`} className="comparisonPerformance">
    <p>The completed simulation's own accounting and fills produced these values. The observed snapshot did not generate those fills; no new performance was calculated.</p>
    <p className="muted">These are client-supplied PAPER results, not authenticated server execution records or observed live PnL.</p>
    <Metrics items={[
      ['Hypothetical session PnL · quote',decimal(p.session_pnl)],['Hypothetical return · percent',`${decimal(p.return_pct)}%`],
      ['Hypothetical realized PnL · quote',decimal(p.realized_pnl)],['Hypothetical unrealized PnL · quote',decimal(p.unrealized_pnl)],
      ['Hypothetical maximum drawdown',fraction(p.max_drawdown_pct)],['Hypothetical fill count',p.fill_count],
      ['Quoted notional · quote',decimal(p.quoted_notional)],['Filled notional · quote',decimal(p.filled_notional)],
      ['Fill activity ratio',fraction(p.fill_activity_ratio)],['Mean spread capture · bps',decimal(p.mean_spread_capture_bps)],
      ['Mean mature markout · bps',decimal(p.mean_mature_markout_bps)],['Adverse fill rate',fraction(p.adverse_fill_rate)],
      ['Ending inventory · base',decimal(p.ending_inventory_base)],['Maximum inventory utilization',fraction(p.max_inventory_utilization)],
      ['Risk HALT fraction',fraction(p.risk_halt_fraction)],['Actual simulated fees · quote',decimal(p.fees_quote)],
      ['Actual simulated settled funding · quote',decimal(p.funding_quote)],
    ]}/>
    <p>Simulated risk frame counts: {Object.entries(p.risk_state_counts).map(([k,v])=>`${k}: ${v}`).join(' · ')}.</p>
    {c?<details><summary>Captured Research Vault accounting assumptions</summary>
      <p>Preset: {c.selected_preset_id??'No preset selected'} · version {c.selected_preset_version??'Unavailable'} · customized {c.customized?'YES':'NO'}</p>
      <dl>{Object.entries(c.normalized_config).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{String(v)}</dd></div>)}</dl>
      <code>{c.config_fingerprint}</code></details>:<p className="muted">Research accounting configuration provenance unavailable for this legacy result. No Research Vault preset is inferred.</p>}
  </Panel>;
}
