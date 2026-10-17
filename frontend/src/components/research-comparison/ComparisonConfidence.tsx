import type {MarketResearchComparisonResult} from '../../types';
import {Panel} from '../TerminalPrimitives';
export function ComparisonConfidence({data}:{data:MarketResearchComparisonResult}) {
  return <Panel title="Evidence completeness & interpretation" meta={data.explainability.completeness}>
    <p><strong>CROSS_CONTEXT_DESCRIPTIVE_ONLY</strong> · Evidence completeness measures available inputs; it does not predict strategy profitability.</p>
    <p>Available: {data.explainability.available_metrics.join(', ')||'None'}.</p>
    <p>Missing / incomparable: {data.explainability.missing_metrics.join(', ')||'None for supported metrics'}.</p>
    <p>Partially comparable: {data.metrics.filter(m=>m.comparison_status==='PARTIAL').map(m=>m.metric_name).join(', ')||'None'}. Raw funding and modeled open interest do not establish equivalent cash flows or executable liquidity.</p>
    <p>Client-supplied provenance is structurally validated, not authenticated server execution evidence. Captured freshness does not renew when a newer observation arrives.</p>
    <ul>{data.explainability.statements.map((s,i)=><li key={i}>{s}</li>)}</ul>
    <ul>{data.limitations.map((s,i)=><li key={i}>{s}</li>)}</ul>
  </Panel>;
}
