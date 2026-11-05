import { useEffect } from 'react';
import type { ReplaySegment } from '../../types/replay';
import { Panel } from '../TerminalPrimitives';
export function ReplayControls({segments,segmentIndex,chooseSegment,frameIndex,chooseFrame,playing,setPlaying}:{
  segments: ReplaySegment[];segmentIndex:number;chooseSegment:(value:number)=>void;
  frameIndex:number;chooseFrame:(value:number)=>void;playing:boolean;setPlaying:(value:boolean)=>void;
}) {
  const segment=segments[segmentIndex] ?? null;
  const count=segment?.frames.length ?? 0;
  useEffect(()=>{
    if(!playing || count===0)return;
    const timer=window.setInterval(()=>chooseFrame(Math.min(count-1,frameIndex+1)),650);
    return ()=>window.clearInterval(timer);
  },[playing,frameIndex,chooseFrame,count]);
  useEffect(()=>{if(playing && frameIndex>=count-1)setPlaying(false)},[playing,frameIndex,count,setPlaying]);
  return <Panel title="Frame timeline" meta="RECORDED RECEIPTS · DISPLAY PLAYBACK">
    <div className="replayControls">
      <label>Independent replay segment<select aria-label="Replay segment" value={segmentIndex} onChange={e=>chooseSegment(Number(e.target.value))}>
        {segments.map((s,i)=><option key={s.segment_index} value={i}>Segment {i+1} · {s.reset_reason.replace(/_/g,' ')} · {s.frame_count} frames</option>)}
      </select></label>
      <button type="button" disabled={!count || frameIndex===0} onClick={()=>chooseFrame(Math.max(0,frameIndex-1))}>Previous</button>
      <button type="button" disabled={!count} onClick={()=>setPlaying(!playing)}>{playing?'Pause':'Play'}</button>
      <button type="button" disabled={!count || frameIndex===count-1} onClick={()=>chooseFrame(Math.min(count-1,frameIndex+1))}>Next</button>
    </div>
    {segment && <>
      <label className="replaySliderLabel">Frame {frameIndex+1} of {count}
        <input aria-label="Historical frame" type="range" min="0" max={Math.max(0,count-1)} step="1" value={frameIndex} onChange={e=>chooseFrame(Number(e.target.value))}/>
      </label>
      <p className="muted panelNote">Receipt time: {segment.frames[frameIndex]?.evaluated_at ?? 'Unavailable'} · Replay is local display navigation. Playback never sends orders or fetches live ticks.</p>
    </>}
  </Panel>;
}
