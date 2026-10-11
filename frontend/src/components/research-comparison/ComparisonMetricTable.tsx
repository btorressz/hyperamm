import type {ComparisonMetric} from '../../types';
import {Panel} from '../TerminalPrimitives';
import {exactDecimal} from '../../utils/orderView';
const labels={midpoint:'Midpoint',best_bid:'Best bid',best_ask:'Best ask',mark_price:'Mark price',oracle_price:'Oracle price',spread_quote:'Spread · quote units',spread_bps:'Spread · basis points',funding_rate:'Funding · raw rate',bid_depth_base:'Bid visible depth',ask_depth_base:'Ask visible depth',open_interest_base:'Open interest'};
export function ComparisonMetricTable({metrics,title}:{metrics:ComparisonMetric[];title:string}) {
  return <Panel title={title} meta="OBSERVED MINUS HYPOTHETICAL">
    <div className="comparisonTableScroll" tabIndex={0} role="region" aria-label={`${title} table`}>
      <table><thead><tr><th scope="col">Metric / unit</th><th scope="col">Observed market</th><th scope="col">Hypothetical research</th><th scope="col">Difference</th><th scope="col">Difference bps</th><th scope="col">Eligibility / reason</th></tr></thead>
        <tbody>{metrics.map(m=><tr key={m.metric_name}><th scope="row">{labels[m.metric_name]}<small>{m.unit}</small></th>
          <td>{exactDecimal(m.observed_value)}</td><td>{exactDecimal(m.research_assumed_value)}</td><td>{exactDecimal(m.absolute_difference)}</td><td>{exactDecimal(m.difference_bps)}</td>
          <td><strong className="comparisonStatus">{m.comparison_status}</strong><p>{m.reason}</p></td></tr>)}</tbody></table>
    </div>
  </Panel>;
}
