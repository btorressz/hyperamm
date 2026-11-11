import { useMemo } from 'react';
import type { ComparisonChartEvidence, QuantitativeComparisonReceipt, ScenarioHistoricalResponse } from '../../types/scenarioReplayComparison';
import { attachedTraceMatches } from '../../utils/scenarioReplayComparison';
import { readSegmentArchive } from '../../utils/replayEvidence';
import { Panel, Empty } from '../TerminalPrimitives';
import { SimulationTrace } from '../simulation/SimulationTrace';

/** Original points travel separately from the unchanged B receipt, after server
 * provenance validation. Never fabricate paths from aggregate metrics. */
export function ComparisonTraceCharts({receipt,evidence,transport}:{receipt:QuantitativeComparisonReceipt;evidence?:ComparisonChartEvidence;transport?:ScenarioHistoricalResponse}) {
  const pair = useMemo(()=>{
    if(!evidence || !attachedTraceMatches(receipt,evidence))return null;
    const segment=evidence.historical.segments[receipt.selected_segment_index];
    try{return {scenario:evidence.scenario,historical:readSegmentArchive(segment)};}
    catch{return null;}
  },[receipt,evidence]);
  const bounded=transport&&receipt.display_policy!=='BLOCKED'?transport:null;
  if(receipt.display_policy==='BLOCKED')return <Panel title="Trace evidence unavailable" meta="INCOMPARABLE">
    <Empty>Market or engine identity mismatch blocks paired financial traces. Inspect provenance and reasons below.</Empty>
  </Panel>;
  if(bounded)return <Panel title="Equity, PnL, inventory & risk trace" meta="TWO INDEPENDENT FRAME AXES">
    <p className="muted panelNote">Original engine points; separate starting capital and frame axes. Scenario times are generated. Historical evaluation times follow receipts; source times do not synchronize these runs. Truncated traces cover only retained points.</p>
    <div className="srcTraceColumns">{([['Scenario',bounded.scenario_trace],['Historical segment',bounded.historical_trace]] as const).map(([title,t])=><details key={title} open>
      <summary>{title} — simulated trace</summary>
      <p>{t.points.length} original points · {t.omitted_points} omitted · {t.omission}</p>
      {t.points.length?<SimulationTrace result={{trace:t.points,run_fingerprint:t.run_fingerprint,metrics:{frame_count:t.frame_count}}} requestedCap={bounded.request.trace_point_limit}/>:<Empty>Original trace unavailable: {t.omission}.</Empty>}
      {!!t.source_times.length&&<details><summary>Original receipt/source timestamps</summary><p>Source event verification flags describe recorded assertions. Synthetic fixtures are not authenticated exchange history.</p>
        <div className="tableWrap" tabIndex={0}><table><thead><tr><th>Sequence</th><th>Book receipt / source / verified</th><th>Context receipt / source / verified</th></tr></thead><tbody>
          {t.source_times.map(p=><tr key={p.sequence}><td>{p.sequence}</td><td>{p.book_received_at}<br/>{p.book_source_timestamp??'Unavailable'} · {String(p.book_source_event_time_verified)}</td><td>{p.context_received_at}<br/>{p.context_source_timestamp??'Unavailable'} · {String(p.context_source_event_time_verified)}</td></tr>)}
        </tbody></table></div></details>}
    </details>)}</div>
  </Panel>;
  return <Panel title="Equity, PnL, inventory & risk trace" meta="TWO INDEPENDENT FRAME AXES">
    {!pair?<Empty>Original traces are unavailable for this receipt. Run a server comparison with trace evidence to inspect independent paths. No chart is generated from totals or local receipt JSON.</Empty>:<>
      <p className="muted panelNote">The two plots use independent frame indexes and separate initial capital. They are not overlaid, synchronized or pooled. Original receipt timestamps remain available in chart inspection.</p>
      <div className="srcTraceColumns">
        <details><summary>Scenario — simulated trace</summary><SimulationTrace result={pair.scenario}/></details>
        <details><summary>Historical segment — simulated trace</summary><SimulationTrace result={pair.historical}/></details>
      </div>
    </>}
  </Panel>;
}
