import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import type { HistoricalReplayResult, ReplayArchive } from '../../types/replay';
import { checkedReplayProvenance, checkedReplayResult, checkedReplaySummaries,
  paperInputError, readSegmentArchive, researchPaperDefaults } from '../../utils/replayEvidence';
import { useTerminalStore } from '../../stores/terminal';
import { Panel, Empty, StatusBanner } from '../TerminalPrimitives';
import { Badge } from '../Badge';
import { ReplayDatasetSelector } from './ReplayDatasetSelector';
import { ReplayExecutionAssumptions } from './ReplayExecutionAssumptions';
import { ReplayControls } from './ReplayControls';
import { ReplayMarketChart } from './ReplayMarketChart';
import { ReplayOrderBook } from './ReplayOrderBook';
import { ReplayPerformance } from './ReplayPerformance';
import { ReplayComparison } from './ReplayComparison';
import { ReplayProvenance } from './ReplayProvenance';
import '../../phase164.css';

function boundedInteger(value:string,min:number,max:number): number|null {
  if (!/^\d+$/.test(value))return null;
  const n=Number(value);
  return Number.isSafeInteger(n)&&n>=min&&n<=max?n:null;
}
export function HistoricalReplayWorkspace() {
  const [selected,setSelected]=useState('');
  const [paper,setPaper]=useState(researchPaperDefaults);
  const [sizeDecimals,setSizeDecimals]=useState('5');
  const [maxFrames,setMaxFrames]=useState('250');
  const [maxAge,setMaxAge]=useState('0');
  const [maxInterval,setMaxInterval]=useState('1000');
  const [pending,setPending]=useState(false);
  const [error,setError]=useState('');
  const [result,setResult]=useState<HistoricalReplayResult|null>(null);
  const [segmentIndex,setSegmentIndex]=useState(0);
  const [frameIndex,setFrameIndex]=useState(0);
  const [playing,setPlaying]=useState(false);
  const requestEpoch=useRef(0);
  const busy=useRef(false);
  const terminalIdentity=useTerminalStore(s=>(s.terminal?.process_id ?? '')+':'+(s.terminal?.session_id ?? ''));
  // Keep query promises shared through StrictMode remounts: aborting the HTTP
  // waiter would leave its admitted worker busy for the immediate replacement.
  const catalog=useQuery({queryKey:['phase164-dataset-summaries'],queryFn:async()=>checkedReplaySummaries(await api.historicalReplaySummaries()),
    retry:false,refetchOnWindowFocus:false});
  const datasets=catalog.data??[];
  const item=datasets.find(x=>x.dataset_id===selected)??null;
  const provenance=useQuery({queryKey:['phase164-provenance',item?.dataset_id,item?.dataset_fingerprint],
    queryFn:()=>api.historicalReplayProvenance(item!.dataset_id).then(p=>checkedReplayProvenance(p,item!)),
    enabled:!!item&&!pending,retry:false,staleTime:Infinity,refetchOnWindowFocus:false});
  const resetResult=useCallback(()=>{
    requestEpoch.current+=1; setResult(null);setSegmentIndex(0);setFrameIndex(0);setPlaying(false);setError('');
  },[]);
  useEffect(()=>()=>{requestEpoch.current+=1},[]);
  // Refetch/removal may change identity without a selector event.
  useEffect(()=>{resetResult()},[item?.dataset_id,item?.dataset_fingerprint,resetResult]);
  // Mark retained results historical when process/session changes; never associate them with new operational state.
  const [resultIdentity,setResultIdentity]=useState('');
  const isRetired=!!result && !!resultIdentity && resultIdentity!==terminalIdentity;
  const updateSelected=(id:string)=>{resetResult();setSelected(id)};
  const updateModel=(value:typeof paper)=>{resetResult();setPaper(value)};
  const validSize=boundedInteger(sizeDecimals,0,6);
  const validFrames=boundedInteger(maxFrames,2,5000);
  const validAge=boundedInteger(maxAge,0,30000);
  const validInterval=boundedInteger(maxInterval,1,60000);
  const validation=paperInputError(paper) ||
    (validSize===null?'Size precision must be 0–6.':null) ||
    (validFrames===null?'Frame count must be 2–5000.':null) ||
    (validAge===null?'Component age must be 0–30000 ms.':null) ||
    (validInterval===null?'Frame interval must be 1–60000 ms.':null);
  const run=async()=>{
    if(busy.current||!item||!provenance.data||provenance.isError||provenance.isFetching||catalog.isError||catalog.isFetching||validation||validSize===null||validFrames===null||validAge===null||validInterval===null)return;
    const epoch=++requestEpoch.current;
    busy.current=true;setPending(true);setError('');setResult(null);setPlaying(false);
    const captured={dataset_id:item.dataset_id,dataset_fingerprint:item.dataset_fingerprint,market:item.market,
      execution:{size_decimals:validSize,paper:{...paper}},
      policy:{max_component_age_ms:validAge,max_frame_interval_ms:validInterval},
      max_frames:validFrames,record_trace:true as const,trace_max_points:Math.min(500,validFrames)};
    try{
      const response=checkedReplayResult(await api.historicalReplayRun(captured),captured);
      if(requestEpoch.current!==epoch)return;
      setResult(response);setSegmentIndex(0);setFrameIndex(0);setResultIdentity(terminalIdentity);
    }catch(e){if(requestEpoch.current===epoch)setError(e instanceof TypeError?'Historical backend connection unavailable. Retry when it returns; a lost browser request does not stop an admitted research job.':e instanceof Error?e.message:'Historical replay request failed.');}
    finally{busy.current=false;setPending(false);}
  };
  const segment=result?.segments[segmentIndex]??null;
  const frame=segment?.frames[frameIndex]??null;
  const archive=useMemo(()=>{
    if(!segment)return null;
    try{return {modeled:readSegmentArchive(segment),
      baseline:segment.baseline_result_json?readSegmentArchive(segment,true):null,error:''};}
    catch(e){return {modeled:null,baseline:null,error:e instanceof Error?e.message:'Invalid segment archive.'};}
  },[segment]);
  const chooseSegment=useCallback((n:number)=>{setPlaying(false);setSegmentIndex(n);setFrameIndex(0)},[]);
  const chooseFrame=useCallback((n:number)=>setFrameIndex(n),[]);
  const changeNumber=(setter:(v:string)=>void)=>(v:string)=>{resetResult();setter(v)};
  return <section className="stack replayWorkspace" aria-label="Historical Replay Studio">
    <div className="researchPageTitle"><div><h2>Historical Replay Studio</h2>
      <p className="muted">Inspect admitted market observations and isolated PAPER execution sensitivities. No live orders.</p>
    </div><Badge tone="blue">PHASE 16.4 · RESEARCH</Badge></div>
    {catalog.isError&&<StatusBanner tone="bad">Historical dataset catalog unavailable. Configure the private HISTORICAL_REPLAY_ROOT on the backend, or retry. No live market history is substituted.</StatusBanner>}
    <ReplayDatasetSelector datasets={datasets} selected={item?.dataset_id??''} onSelect={updateSelected}
      refreshing={catalog.isFetching} refresh={()=>{resetResult();void catalog.refetch()}}/>
    {item&&provenance.isError&&<StatusBanner tone="bad">Selected dataset provenance is unavailable or has changed. Reload the catalog before running. <button type="button" disabled={pending||provenance.isFetching} onClick={()=>void provenance.refetch()}>Retry provenance</button></StatusBanner>}
    <ReplayExecutionAssumptions paper={paper} change={updateModel}
      sizeDecimals={sizeDecimals} setSizeDecimals={changeNumber(setSizeDecimals)}
      maxFrames={maxFrames} setMaxFrames={changeNumber(setMaxFrames)}
      maxAge={maxAge} setMaxAge={changeNumber(setMaxAge)}
      maxInterval={maxInterval} setMaxInterval={changeNumber(setMaxInterval)}/>
    <div className="actions"><button className="primary" type="button"
      disabled={pending||!item||!provenance.data||provenance.isError||provenance.isFetching||catalog.isError||!!validation||catalog.isFetching}
      onClick={()=>void run()}>{pending?'Research worker running…':'Run Historical PAPER Replay'}</button>
      {validation&&<span role="alert" className="inlineError">{validation}</span>}
    </div>
    {pending&&<p role="status">One shared research worker is occupied; a cancelled browser request does not stop its backend computation.</p>}
    {error&&<p className="inlineError" role="alert">{error}</p>}
    {isRetired&&<StatusBanner>Retained research from a previous backend session. Captured dataset/results remain historical; run again for current configuration.</StatusBanner>}
    {result&&<div className="stack">
      <Panel title="Replay receipt" meta="COMPLETED PARTIAL · ISOLATED PAPER">
        <p>{result.request.market}-PERP · {result.frame_count} viable frames · {result.segments.length} independent segments · {result.examined_observation_count} observations examined.</p>
        <p className="muted panelNote">Results are partial even without declared gaps. Every segment resets capital, risk, orders and inventory. No aggregate return is displayed.</p>
      </Panel>
      {segment&&<ReplayControls segments={result.segments} segmentIndex={segmentIndex}
        chooseSegment={chooseSegment} frameIndex={frameIndex} chooseFrame={chooseFrame}
        playing={playing} setPlaying={setPlaying}/>}
      {segment&&<div className="replayColumns">
        <ReplayMarketChart segment={segment} frame={frame}/>
        <ReplayOrderBook frame={frame}/>
      </div>}
      {archive?.error&&<StatusBanner tone="bad">{archive.error}</StatusBanner>}
      {segment&&archive?.modeled&&<>
        <ReplayPerformance key={segment.run_fingerprint} archive={archive.modeled as ReplayArchive} segment={segment}/>
        <ReplayComparison segment={segment} modeled={archive.modeled as ReplayArchive} baseline={archive.baseline as ReplayArchive|null}/>
      </>}
    </div>}
    {!result&&!pending&&<Empty>No replay has been run in this view. Stored datasets cannot be uploaded, deleted or modified here.</Empty>}
    <ReplayProvenance summary={item} provenance={provenance.data??null} result={result} frame={frame}/>
    <StatusBanner>Historical prices and execution outcomes are bounded PAPER research, not calibrated fills or independently verified complete native market history. Source licenses remain unverified. Changing browser controls never deploys strategy changes.</StatusBanner>
  </section>;
}
