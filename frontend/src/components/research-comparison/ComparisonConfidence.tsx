import type {MarketResearchComparisonResult} from '../../types';
import {Panel} from '../TerminalPrimitives';
export function ComparisonConfidence({data}:{data:MarketResearchComparisonResult}) {
  return <Panel title="Evidence completeness & interpretation" meta={data.explainability.completeness}>
    <p><strong>CROSS_CONTEXT_DESCRIPTIVE_ONLY</strong> · Evidence completeness measures available inputs; it does not predict strategy profitability.</p>
    <p>Available: {data.explainability.available_metrics.join(', ')||'None'}.</p>
    <p>Missing / incomparable: {data.explainability.missing_metrics.join(', ')||'None for supported metrics'}.</p>
    <ul>{data.limitations.map((s,i)=><li key={i}>{s}</li>)}</ul>
  </Panel>;
}
