import type { LiveMarketHistory, LiveHistoryPoint } from '../types';
import { decimalValue } from './liveMarketEvidence';
export type LiveChartKey = 'midpoint'|'best_bid'|'best_ask'|'mark'|'oracle';
export type LiveChartPoint = {time:number;value:number};
// Source times for L2; receipt times for context. Within a second, keep the
// observation with latest genuine timestamp (stable last record on exact ties).
// No shifted timestamps, forward fills, interpolation or artificial candles.
export function liveChartSegments(history: LiveMarketHistory, key: LiveChartKey, gapSeconds: number) {
  const kind=key==='mark'||key==='oracle'?'PERP_CONTEXT':'L2';
  const segments: LiveChartPoint[][]=[];
  let current: LiveChartPoint[]=[], previous: LiveHistoryPoint | null=null;
  function finish(){if(current.length)segments.push(current);current=[];}
  for(const p of history.points.filter(p=>p.kind===kind)) {
    const stamp=kind==='L2'?p.source_timestamp:p.observed_at;
    const exact=stamp?Date.parse(stamp)/1000:NaN, value=decimalValue(p[key]);
    if(p.observer_instance_id!==history.observer_instance_id || !Number.isFinite(exact) || value===null || ['STALE','UNAVAILABLE','ERROR','DISABLED'].includes(p.observation_status)) {finish();previous=null;continue;}
    const oldStamp=previous && (kind==='L2'?previous.source_timestamp:previous.observed_at);
    const oldTime=oldStamp?Date.parse(oldStamp)/1000:null;
    // A global gap counter has no individual gap positions. Conservatively use
    // separate markers throughout such a response instead of guessing continuity.
    if(history.gap_count>0 || previous && (p.connection_generation!==previous.connection_generation || p.observer_instance_id!==previous.observer_instance_id || oldTime===null || exact<oldTime || exact-oldTime>gapSeconds))finish();
    const time=Math.floor(exact);
    if(current.at(-1)?.time===time)current[current.length-1]={time,value};
    else current.push({time,value});
    previous=p;
  }
  finish();return segments;
}
