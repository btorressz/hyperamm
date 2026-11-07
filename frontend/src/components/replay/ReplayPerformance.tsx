import { useState } from 'react';
import type { ReplayArchive, ReplaySegment } from '../../types/replay';
import { SimulationPanel } from '../SimulationPanel';
import { SimulationTrace } from '../simulation/SimulationTrace';
import { Panel, Metrics } from '../TerminalPrimitives';
import { livePrice } from '../../utils/format';
export function ReplayPerformance({archive,segment}:{archive:ReplayArchive;segment:ReplaySegment}) {
  const [traceOpen,setTraceOpen]=useState(false);
  return <section className="stack" aria-label="Selected segment PAPER performance">
    <Panel title="Segment-only PAPER results" meta={'SEGMENT '+(segment.segment_index+1)+' · NO CROSS-GAP RETURNS'}>
      <Metrics items={[
        ['Starting equity (quote)',livePrice(String(segment.starting_equity))],
        ['Ending equity (quote)',livePrice(String(segment.ending_equity))],
        ['Session PnL (quote)',livePrice(String(segment.session_pnl))],
        ['Hypothetical fills',String(segment.fill_count)]
      ]}/>
      <p className="muted panelNote">Capital resets for every historical segment. No result here is an uninterrupted portfolio return.</p>
    </Panel>
    <SimulationPanel m={archive.metrics}/>
    <details className="replayDetailsDisclosure" onToggle={e=>setTraceOpen(e.currentTarget.open)}>
      <summary>Explore segment equity, PnL, inventory, risk and execution trace</summary>
      {traceOpen&&<SimulationTrace result={archive} requestedCap={Math.min(500,segment.frame_count)}/>}
    </details>
  </section>;
}
