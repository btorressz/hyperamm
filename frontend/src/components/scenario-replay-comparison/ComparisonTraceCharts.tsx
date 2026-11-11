import { useMemo } from 'react';
import type { ComparisonChartEvidence, QuantitativeComparisonReceipt } from '../../types/scenarioReplayComparison';
import { attachedTraceMatches } from '../../utils/scenarioReplayComparison';
import { readSegmentArchive } from '../../utils/replayEvidence';
import { Panel, Empty } from '../TerminalPrimitives';
import { SimulationTrace } from '../simulation/SimulationTrace';

/** Original source traces are intentionally NOT carried in the Phase 16.5B metric receipt.
 *  C.2 should supply them after server provenance validation; never fabricate charts
 *  from aggregate metrics or stretch a historical segment across receipt gaps.
 */
export function ComparisonTraceCharts({receipt,evidence}:{receipt:QuantitativeComparisonReceipt;evidence?:ComparisonChartEvidence}) {
  const pair = useMemo(()=>{
    if(!evidence || !attachedTraceMatches(receipt,evidence))return null;
    const segment=evidence.historical.segments[receipt.selected_segment_index];
    try{return {scenario:evidence.scenario,historical:readSegmentArchive(segment)};}
    catch{return null;}
  },[receipt,evidence]);
  return <Panel title="Equity, PnL, inventory & risk trace" meta="TWO INDEPENDENT FRAME AXES">
    {!pair?<Empty>Charts require separately validated original scenario and selected historical segment traces. The Phase 16.5B metrics receipt does not contain trace arrays, so no equity path or synthetic chart is generated from totals. Native trace transport is a Phase 16.5C.2 integration gate.</Empty>:<>
      <p className="muted panelNote">The two plots use independent frame indexes and separate initial capital. They are not overlaid, synchronized or pooled. Original receipt timestamps remain available in chart inspection.</p>
      <div className="srcTraceColumns">
        <details><summary>Scenario — simulated trace</summary><SimulationTrace result={pair.scenario}/></details>
        <details><summary>Historical segment — simulated trace</summary><SimulationTrace result={pair.historical}/></details>
      </div>
    </>}
  </Panel>;
}
