import { useEffect, useRef, useState, useMemo } from 'react';
import { createChart, ColorType, LineSeries, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts';
import type { LiveMarketHistory } from '../../types';
import { liveChartSegments, type LiveChartKey } from '../../utils/liveMarketHistory';
import { livePrice } from '../../utils/format';
import { Panel, Empty } from '../TerminalPrimitives';
const lines = {midpoint:['L2 midpoint','#61b8ff'],best_bid:['Best bid','#4cd4a1'],best_ask:['Best ask','#f0788a'],mark:['Mark (receipt)','#ffc665'],oracle:['Oracle (receipt)','#b7a2ff']} as const;
export function LiveMarketChart({history,bookGap,perpGap}:{history:LiveMarketHistory | null;bookGap:number;perpGap:number}) {
  const [basis,setBasis]=useState<'L2'|'PERP_CONTEXT'>('L2');
  const [enabled,setEnabled]=useState<LiveChartKey[]>(['midpoint','best_bid','best_ask','mark','oracle']);
  const container=useRef<HTMLDivElement>(null), chart=useRef<IChartApi | null>(null), entries=useRef(new Map<LiveChartKey,ISeriesApi<'Line'>[]>());
  const fitIdentity=useRef<string | null>(null);
  const available=useMemo(()=>(basis==='L2'?['midpoint','best_bid','best_ask']:['mark','oracle']) as LiveChartKey[],[basis]);
  useEffect(()=>{
    if(!container.current)return;
    const c=createChart(container.current,{height:300,width:container.current.clientWidth,
      layout:{background:{type:ColorType.Solid,color:'#0a1420'},textColor:'#8da3b8',fontSize:11},
      grid:{vertLines:{color:'#132231'},horzLines:{color:'#132231'}},timeScale:{timeVisible:true,secondsVisible:true},rightPriceScale:{borderColor:'#223246'}});
    chart.current=c;
    const resize=new ResizeObserver(()=>{if(container.current)c.applyOptions({width:container.current.clientWidth});});resize.observe(container.current);
    return ()=>{resize.disconnect();c.remove();chart.current=null;entries.current.clear();};
  },[]);
  useEffect(()=>{
    const c=chart.current;if(!c)return;
    for(const [key,series] of entries.current)if(!available.includes(key)||!enabled.includes(key)){series.forEach(s=>c.removeSeries(s));entries.current.delete(key);}
    for(const key of available.filter(k=>enabled.includes(k))){
      const groups=history?liveChartSegments(history,key,basis==='L2'?bookGap:perpGap):[];
      const previous=entries.current.get(key)??[];
      while(previous.length>groups.length)c.removeSeries(previous.pop()!);
      while(previous.length<groups.length)previous.push(c.addSeries(LineSeries,{title:lines[key][0],color:lines[key][1],lineWidth:2,
        pointMarkersVisible:true,priceLineVisible:false,lastValueVisible:false,
        priceFormat:{type:'custom',minMove:.000001,formatter:(n:number)=>livePrice(String(n))}}));
      previous.forEach((s,i)=>s.setData(groups[i].map(p=>({time:p.time as UTCTimestamp,value:p.value}))));entries.current.set(key,previous);
    }
    const identity=history?`${history.market}:${history.observer_instance_id}:${basis}`:null;
    if(identity && history?.points.length && fitIdentity.current!==identity){c.timeScale().fitContent();fitIdentity.current=identity;}
  },[history,enabled,available,basis,bookGap,perpGap]);
  return <Panel title="Retained native price observations" meta={basis==='L2'?'L2 exchange event time':'Context receipt time · event time unverified'}>
    <div className="liveChartControls">
      <label>Time basis<select value={basis} onChange={e=>setBasis(e.target.value as typeof basis)} aria-label="Chart time basis"><option value="L2">L2 exchange time</option><option value="PERP_CONTEXT">Mark / oracle receipt time</option></select></label>
      {available.map(k=><label key={k}><input type="checkbox" checked={enabled.includes(k)} onChange={e=>setEnabled(v=>e.target.checked?[...v,k]:v.filter(x=>x!==k))}/>{lines[k][0]}</label>)}
    </div>
    <div className="liveChart" ref={container} role="img" aria-label={`${basis==='L2'?'L2 exchange-time':'Context receipt-time'} retained observation chart`}/>
    {!history?.points.some(p=>p.kind===basis) && <Empty>No retained observations for this time basis.</Empty>}
    <p className="muted panelNote">Bounded observations, not OHLCV candles or a verified continuous tick archive. Latest actual observation per second; no interpolation. Separate series at generation changes, missing values or aged intervals. {history?.gap_count?'Known gaps have no positions: isolated points only.':''}</p>
  </Panel>;
}
