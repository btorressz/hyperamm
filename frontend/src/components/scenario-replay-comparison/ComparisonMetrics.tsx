import type { QuantitativeComparisonReceipt, QuantitativeMetricRow } from '../../types/scenarioReplayComparison';
import { metricText } from '../../utils/scenarioReplayComparison';
import { Empty, Panel } from '../TerminalPrimitives';

const LABELS: Record<string,string> = {
  frame_count:'Simulated frames',starting_equity:'Starting equity',ending_equity:'Ending equity',
  session_pnl:'Session PnL',return_pct:'PAPER return',realized_pnl:'Realized PnL',
  unrealized_pnl:'Unrealized PnL',max_drawdown_pct:'Max drawdown',
  fill_count:'Hypothetical fills',buy_fill_count:'Buy fills',sell_fill_count:'Sell fills',
  quoted_notional:'Quoted notional',filled_notional:'Filled notional',
  fill_activity_ratio:'Fill activity ratio',ending_inventory_base:'Ending inventory',
  max_abs_inventory_base:'Max absolute inventory',max_inventory_utilization:'Max inventory utilization',
  risk_halt_fraction:'Risk HALT fraction',fees_quote:'PAPER fees',
  funding_quote:'PAPER funding',capital_utilization:'Capital utilization',
  reserved_capital_quote:'Reserved capital',gross_exposure_quote:'Gross exposure',
};
const GROUPS: ReadonlyArray<[string,string[]]> = [
  ['PAPER PnL & equity',['starting_equity','ending_equity','session_pnl','return_pct','realized_pnl','unrealized_pnl','max_drawdown_pct']],
  ['Execution & fills',['fill_count','buy_fill_count','sell_fill_count','quoted_notional','filled_notional','fill_activity_ratio']],
  ['Inventory, capital & risk',['ending_inventory_base','max_abs_inventory_base','max_inventory_utilization','risk_halt_fraction','capital_utilization','reserved_capital_quote','gross_exposure_quote']],
  ['Accounting & evidence',['fees_quote','funding_quote','frame_count']],
];
function Cell({value,unit}:{value:string|null;unit:string}) {
  return <td className="srcMetricValue">
    {value===null?<span className="muted">Unavailable</span>:
      <span title={value} aria-label={value+' '+unit} className="srcExact">
        {metricText(value)} <small className="muted">{unit}</small>
      </span>}
  </td>;
}
function Group({title,rows}:{title:string;rows:QuantitativeMetricRow[]}) {
  return <details className="srcMetricGroup" open={title==='PAPER PnL & equity'}>
    <summary>{title} <small className="muted">({rows.length} separately reported fields)</small></summary>
    <div className="tableWrap srcMetricsTable" role="region" tabIndex={0} aria-label={title+' descriptive comparison'}>
      <table><thead><tr><th>Backend metric</th><th>Scenario · simulated</th><th>Historical segment · simulated</th></tr></thead>
        <tbody>{rows.map(row=><tr key={row.name}>
          <th scope="row"><span>{LABELS[row.name]??row.name}</span>
            <small className="muted srcMetricOrigin">{row.scenario.origin==='PAPER_VAULT'?'PAPER Vault':'SimulationMetrics'}</small>
          </th>
          <Cell value={row.scenario.value} unit={row.unit}/>
          <Cell value={row.historical_segment.value} unit={row.unit}/>
        </tr>)}</tbody></table>
    </div>
  </details>;
}
function RiskCounts({receipt}:{receipt:QuantitativeComparisonReceipt}) {
  if(!receipt.risk_states)return null;
  const risk=receipt.risk_states;
  const states=[...new Set([...Object.keys(risk.scenario),...Object.keys(risk.historical_segment)])].sort();
  return <details className="srcMetricGroup"><summary>Risk state counts (separate runs)</summary>
    <div className="tableWrap" role="region" tabIndex={0} aria-label="Risk states">
      <table><thead><tr><th>State</th><th>Scenario frames</th><th>Historical segment frames</th></tr></thead>
      <tbody>{states.map(state=><tr key={state}>
        <th scope="row">{state}</th>
        <td>{risk.scenario[state]??'Not reported'}</td>
        <td>{risk.historical_segment[state]??'Not reported'}</td>
      </tr>)}</tbody></table>
    </div>
    <p className="muted panelNote">Counts are shown independently. The table does not measure differences or establish why a risk state occurred.</p>
  </details>;
}
export function ComparisonMetrics({receipt}:{receipt:QuantitativeComparisonReceipt}) {
  return <Panel title="PAPER metrics — two separate evidence paths" meta="BACKEND VALUES ONLY · NO NUMERICAL DELTAS">
    {receipt.display_policy==='BLOCKED' ? <Empty>
      These evidence paths are INCOMPARABLE (market or engine mismatch). Paired financial metrics are blocked by the Phase 16.5B contract.
    </Empty> : <>
      <p className="muted panelNote">Each cell copies its own backend result. Values are not normalized to the same market period, subtracted, ranked or combined. Long decimals are visually truncated; hover for the exact stored string.</p>
      {GROUPS.map(([group,keys])=><Group key={group} title={group}
        rows={receipt.rows.filter(row=>keys.includes(row.name))}/>)}
      <RiskCounts receipt={receipt}/>
    </>}
  </Panel>;
}
