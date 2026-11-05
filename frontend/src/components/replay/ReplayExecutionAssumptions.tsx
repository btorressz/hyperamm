import type { PaperResearchAssumptions } from '../../types/replay';
import { paperInputError, researchPaperDefaults } from '../../utils/replayEvidence';
import { Panel } from '../TerminalPrimitives';
type Props = {
  paper: PaperResearchAssumptions; change:(value:PaperResearchAssumptions)=>void;
  sizeDecimals:string; setSizeDecimals:(value:string)=>void;
  maxFrames:string; setMaxFrames:(value:string)=>void;
  maxAge:string; setMaxAge:(value:string)=>void;
  maxInterval:string; setMaxInterval:(value:string)=>void;
};
export function ReplayExecutionAssumptions({paper,change,sizeDecimals,setSizeDecimals,maxFrames,setMaxFrames,maxAge,setMaxAge,maxInterval,setMaxInterval}:Props) {
  const set = (patch:Partial<PaperResearchAssumptions>)=>change({...paper,...patch});
  const modeled=paper.mode==='MODELED_CROSSING';
  return <Panel title="Replay & execution assumptions" meta="HYPOTHETICAL PAPER · PHASE163-V1">
    <div className="replayControls">
      <label>Execution model<select aria-label="Execution model" value={paper.mode} onChange={e=>change(e.target.value==='BASELINE'?researchPaperDefaults():{...researchPaperDefaults(),mode:'MODELED_CROSSING'})}>
        <option value="BASELINE">Original crossing-only baseline</option><option value="MODELED_CROSSING">Modeled crossing sensitivity</option></select></label>
      <label>Size precision (user asserted)<input aria-label="Size precision" type="number" min="0" max="6" step="1" value={sizeDecimals} onChange={e=>setSizeDecimals(e.target.value)}/></label>
      <label>Maximum frames<input aria-label="Maximum frames" type="number" min="2" max="5000" step="1" value={maxFrames} onChange={e=>setMaxFrames(e.target.value)}/></label>
      <label>Component age allowance (ms)<input aria-label="Component age allowance" type="number" min="0" max="30000" step="1" value={maxAge} onChange={e=>setMaxAge(e.target.value)}/></label>
      <label>Max frame interval (ms)<input aria-label="Max frame interval" type="number" min="1" max="60000" step="1" value={maxInterval} onChange={e=>setMaxInterval(e.target.value)}/></label>
    </div>
    {modeled && <div className="replayControls replayModeled">
      <label>Order latency (ms)<input type="number" min="0" max="60000" step="1" aria-label="Order latency" value={paper.order_latency_ms} onChange={e=>set({order_latency_ms:Number(e.target.value)})}/></label>
      <label>Cancel latency (ms)<input type="number" min="0" max="60000" step="1" aria-label="Cancel latency" value={paper.cancel_latency_ms} onChange={e=>set({cancel_latency_ms:Number(e.target.value)})}/></label>
      <label>Adverse slippage (bps)<input type="text" inputMode="decimal" aria-label="Slippage bps" value={paper.slippage_bps} onChange={e=>set({slippage_bps:e.target.value})}/></label>
      <label>Participation (0–1)<input type="text" inputMode="decimal" aria-label="Participation rate" value={paper.participation_rate} onChange={e=>set({participation_rate:e.target.value})}/></label>
      <label>Max fill fraction (0–1)<input type="text" inputMode="decimal" aria-label="Max fill fraction" value={paper.max_fill_fraction} onChange={e=>set({max_fill_fraction:e.target.value})}/></label>
      <label className="replayCheck"><input type="checkbox" checked={paper.depth_sensitive} onChange={e=>set({depth_sensitive:e.target.checked})}/> Traverse retained L2 depth</label>
      <label className="replayCheck"><input type="checkbox" checked={paper.allow_partial_fills} onChange={e=>set({allow_partial_fills:e.target.checked})}/> Allow partial fills</label>
    </div>}
    {paperInputError(paper) && <p className="inlineError" role="alert">{paperInputError(paper)}</p>}
    <p className="muted panelNote">Latency uses available receipt observations, not interpolated ticks. Fees and sampled funding retain existing backend research defaults unless explicitly configured elsewhere. No actual fills, hidden liquidity or queue position are established.</p>
  </Panel>;
}
