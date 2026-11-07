import { useMemo } from 'react';
import type { ReplayFrame, ReplaySegment } from '../../types/replay';
import { HistoryChart, type HistoryLine } from '../HistoryChart';
import { Panel } from '../TerminalPrimitives';
import { framePrices } from '../../utils/replayEvidence';
import { livePrice } from '../../utils/format';
const lines:HistoryLine[]=[
  {key:'mid',label:'BBO midpoint',color:'#61b8ff',unit:'quote/base'},
  {key:'bid',label:'Best bid',color:'#4cd4a1',unit:'quote/base'},
  {key:'ask',label:'Best ask',color:'#f0788a',unit:'quote/base'},
  {key:'mark',label:'Mark (context receipt)',color:'#ffc665',unit:'quote/base'},
  {key:'oracle',label:'Oracle (context receipt)',color:'#b7a2ff',unit:'quote/base'}
];
export function ReplayMarketChart({segment,frame}:{segment:ReplaySegment;frame:ReplayFrame|null}) {
  const points=useMemo(()=>segment.frames.map(f=>({sequence:f.sequence,timestamp:f.evaluated_at,...framePrices(f)})),[segment]);
  const p=frame?framePrices(frame):null;
  return <Panel title="Historical market observations" meta="RECEIPT-ORDERED · PER SEGMENT">
    <HistoryChart points={points} lines={lines} axis="frame" height={260} fitKey={segment.run_fingerprint}/>
    <div className="replayPrices">
      <span>Bid <strong>{livePrice(p?.bid)}</strong></span>
      <span>Ask <strong>{livePrice(p?.ask)}</strong></span>
      <span>Mid <strong>{p?.mid==null?'—':livePrice(String(p.mid))}</strong></span>
      <span>Mark <strong>{livePrice(p?.mark)}</strong></span>
      <span>Oracle <strong>{livePrice(p?.oracle)}</strong></span>
    </div>
    <p className="muted panelNote">Frame indices preserve distinct receipt batches. Mark/oracle timestamps are receipt clocks, not verified exchange event clocks. No OHLCV or continuous history is inferred.</p>
  </Panel>;
}
