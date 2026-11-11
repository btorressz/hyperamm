import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import type { ComparisonChartEvidence, QuantitativeComparisonReceipt, ScenarioHistoricalRequest, ScenarioHistoricalResponse } from '../../types/scenarioReplayComparison';
import { parseComparisonReceipt, checkedQuantitativeReceipt } from '../../utils/scenarioReplayComparison';
import { checkedReplaySummaries, checkedReplayProvenance, paperInputError, researchPaperDefaults } from '../../utils/replayEvidence';
import { useTerminalStore } from '../../stores/terminal';
import { capturedResearch, useResearchVaultStore } from '../../stores/researchVault';
import { ResearchMarketSelector } from '../markets/ResearchMarketSelector';
import { capturedMarket, useResearchMarketStore } from '../../stores/researchMarkets';
import { ReplayDatasetSelector } from '../replay/ReplayDatasetSelector';
import { ReplayExecutionAssumptions } from '../replay/ReplayExecutionAssumptions';
import { ReplayProvenance } from '../replay/ReplayProvenance';
import { Empty, Panel, StatusBanner } from '../TerminalPrimitives';
import { Badge } from '../Badge';
import { ResearchRunStatus } from '../research/ResearchRunStatus';
import { ResearchDiagnostics } from '../research/ResearchDiagnostics';
import { ResearchWorkloadPreview } from '../research/ResearchWorkloadPreview';
import { ComparisonMetrics } from './ComparisonMetrics';
import { ComparisonExplainability } from './ComparisonExplainability';
import { ComparisonTraceCharts } from './ComparisonTraceCharts';
import '../../phase164.css';
import '../../phase165c.css';
import '../../phase166c.css';

type Props={receipt?:QuantitativeComparisonReceipt|null; evidence?:ComparisonChartEvidence};
const integer=(s:string,min:number,max:number)=>/^\d+$/.test(s)&&Number.isSafeInteger(Number(s))&&Number(s)>=min&&Number(s)<=max;
// Read-only catalog refreshes can overlap a prior workspace's admitted job.
// Retry only busy metadata reads, never computational POSTs.
const retryMetadata=(count:number,error:Error)=>count<3&&error.message.includes('busy');
export function ScenarioReplayComparisonWorkspace({receipt:serverReceipt,evidence}:Props) {
  const [selected,setSelected]=useState(''),[scenario,setScenario]=useState('QUIET'),[frames,setFrames]=useState('120');
  const [paper,setPaper]=useState(researchPaperDefaults),[size,setSize]=useState('5');
  const [maxFrames,setMaxFrames]=useState('250'),[age,setAge]=useState('0'),[interval,setInterval]=useState('1000');
  const [segmentIndex,setSegmentIndex]=useState(0),[pending,setPending]=useState(false),[error,setError]=useState('');
  const [response,setResponse]=useState<{data:ScenarioHistoricalResponse;key:string;session:string;epoch:number}|null>(null);
  const [json,setJson]=useState(''),[localReceipt,setLocalReceipt]=useState<QuantitativeComparisonReceipt|null>(null),[showImport,setShowImport]=useState(false);
  const epoch=useRef(0),busy=useRef(false),controller=useRef<AbortController|null>(null);
  const market=useResearchMarketStore(),vault=useResearchVaultStore();
  const session=useTerminalStore(s=>(s.terminal?.process_id??'')+':'+(s.terminal?.session_id??'')+':'+s.wsState);
  const catalog=useQuery({queryKey:['phase164-dataset-summaries',session],queryFn:async()=>checkedReplaySummaries(await api.historicalReplaySummaries()),retry:retryMetadata,retryDelay:500,refetchOnWindowFocus:false});
  const scenarios=useQuery({queryKey:['simulation-scenarios'],queryFn:api.simulationScenarios,retry:false});
  const datasets=catalog.data??[],item=datasets.find(x=>x.dataset_id===selected)??null;
  const provenance=useQuery({queryKey:['phase164-provenance',session,item?.dataset_id,item?.dataset_fingerprint],
    queryFn:()=>api.historicalReplayProvenance(item!.dataset_id).then(p=>checkedReplayProvenance(p,item!)),
    enabled:!!item&&!pending&&!catalog.isFetching&&!catalog.isError,retry:retryMetadata,retryDelay:500,staleTime:Infinity,refetchOnWindowFocus:false});
  const inputKey=JSON.stringify([item?.dataset_id,item?.dataset_fingerprint,scenario,frames,paper,size,maxFrames,age,interval,
    market.selectedResearchMarket,market.marketSelectionVersion,market.evidenceEpoch,market.marketProfileFingerprint,
    vault.draftVersion,vault.evidenceEpoch,vault.useForResearch,vault.lastValidatedFingerprint]);
  const latest=useRef({inputKey,session});latest.current={inputKey,session};
  const invalidate=()=>{epoch.current++;setError('');setLocalReceipt(null);setSegmentIndex(0)};
  // A connection/input transition permanently retires evidence, including a
  // reconnect to the same process. Returning to the old key cannot revive it.
  useEffect(()=>{epoch.current++;setLocalReceipt(null);setSegmentIndex(0)},[inputKey,session]);
  useEffect(()=>()=>{epoch.current++;controller.current?.abort()},[]);
  const current=!!response&&response.epoch===epoch.current&&response.key===inputKey&&response.session===session&&response.data.receipt.selected_segment_index===segmentIndex;
  const selectionCurrent=!!response&&response.epoch===epoch.current&&response.key===inputKey&&response.session===session;
  const validation=paperInputError(paper)||(!integer(frames,2,5000)?'Scenario frames must be 2–5000.':null)||
    (!integer(size,0,6)?'Size precision must be 0–6.':null)||(!integer(maxFrames,2,5000)?'Replay frames must be 2–5000.':null)||
    (!integer(age,0,30000)?'Component age must be 0–30000 ms.':null)||(!integer(interval,1,60000)?'Frame interval must be 1–60000 ms.':null);
  const ready=!pending&&!!item&&!!provenance.data&&!provenance.isError&&!provenance.isFetching&&!catalog.isError&&!catalog.isFetching&&
    !!scenarios.data?.scenarios.some(x=>x.name===scenario)&&!validation&&!!capturedMarket();
  const run=async(index=segmentIndex)=>{
    if(busy.current||!ready||!item)return;
    const research=capturedResearch();
    if(vault.useForResearch&&!research){setError('Research Vault preview expired. Revalidate the preset in Vault.');return;}
    const captured:ScenarioHistoricalRequest={scenario,frames:Number(frames),research_market:market.selectedResearchMarket,
      simulation:{max_frames:Number(frames),record_trace:true,trace_max_points:120},
      ...(research?{research:research.proposal}:{}),
      historical:{dataset_id:item.dataset_id,dataset_fingerprint:item.dataset_fingerprint,market:item.market,
        execution:{size_decimals:Number(size),paper:{...paper},...(research?{accounting:research.proposal.config}:{})},
        policy:{max_component_age_ms:Number(age),max_frame_interval_ms:Number(interval)},
        max_frames:Number(maxFrames),record_trace:true,trace_max_points:120},
      segment_index:index,include_traces:true,trace_point_limit:120};
    const token=++epoch.current,key=inputKey,identity=session;
    const abort=new AbortController();controller.current=abort;
    busy.current=true;setPending(true);setError('');setLocalReceipt(null);setResponse(null);
    try{
      const data=await api.scenarioHistoricalComparison(captured,abort.signal);
      if(epoch.current!==token||latest.current.inputKey!==key||latest.current.session!==identity)return;
      setResponse({data,key,session:identity,epoch:token});setSegmentIndex(index);
    }catch(e){if(epoch.current===token&&latest.current.inputKey===key&&latest.current.session===identity)
      setError(e instanceof TypeError?'Backend connection unavailable. A lost browser request does not stop admitted computation.':e instanceof Error?e.message:'Comparison failed.');}
    finally{busy.current=false;if(controller.current===abort){setPending(false);controller.current=null}}
  };
  let checked:QuantitativeComparisonReceipt|null=null,validationError='';
  const active=serverReceipt??(current?response?.data.receipt:null)??localReceipt;
  if(active)try{checked=checkedQuantitativeReceipt(active)}catch(e){validationError=e instanceof Error?e.message:'Invalid comparison evidence.'}
  const importLocal=(event:FormEvent)=>{event.preventDefault();setError('');try{setLocalReceipt(parseComparisonReceipt(json));setShowImport(false)}catch(e){setLocalReceipt(null);setError(e instanceof Error?e.message:'Invalid receipt.')}};
  const update=(setter:(v:string)=>void)=>(v:string)=>{invalidate();setter(v)};
  return <section className="stack srcWorkspace" aria-label="Scenario vs Historical Replay Comparison Studio">
    <div className="researchPageTitle"><div><h2>Scenario vs Historical Replay</h2><p className="muted">Two independent PAPER research paths, verified by the backend.</p></div><Badge tone="blue">16.5C.2 · READ ONLY</Badge></div>
    <StatusBanner>One shared research worker runs the existing engines. No strategy deployment, orders, performance deltas or cross-segment returns.</StatusBanner>
    {!serverReceipt&&<>
      <ResearchMarketSelector/>
      <Panel title="Scenario selection" meta="DETERMINISTIC GENERATED DATA">
        <div className="replayControls">
          <label>Scenario<select aria-label="Comparison scenario" value={scenario} onChange={e=>update(setScenario)(e.target.value)}>
            {(scenarios.data?.scenarios??[]).map(s=><option key={s.name} value={s.name}>{s.name} · {s.description}</option>)}
          </select></label>
          <label>Scenario frames<input aria-label="Scenario frames" type="number" min="2" max="5000" value={frames} onChange={e=>update(setFrames)(e.target.value)}/></label>
        </div>
        <p className="muted panelNote">{vault.useForResearch?'Validated Research Vault accounting applied separately to both paths.':'Default scenario and historical accounting captured independently.'} Manage optional accounting presets in Vault.</p>
        {scenarios.isError&&<p role="alert">Scenario catalog unavailable.</p>}
      </Panel>
      {catalog.isError&&<StatusBanner tone="bad">Historical dataset catalog unavailable. Configure the private backend vault and retry.</StatusBanner>}
      {catalog.isError&&<ResearchDiagnostics error={catalog.error ?? 'Historical storage unavailable (503)'}/>} 
      <ReplayDatasetSelector datasets={datasets} selected={selected} onSelect={update(setSelected)} refreshing={catalog.isFetching}
        refresh={()=>{invalidate();setResponse(null);void catalog.refetch()}}/>
      {provenance.isError&&<ResearchDiagnostics error={provenance.error ?? 'Historical provenance mismatch'}/>} 
      <ReplayExecutionAssumptions paper={paper} change={p=>{invalidate();setPaper(p)}} sizeDecimals={size} setSizeDecimals={update(setSize)}
        maxFrames={maxFrames} setMaxFrames={update(setMaxFrames)} maxAge={age} setMaxAge={update(setAge)} maxInterval={interval} setMaxInterval={update(setInterval)}/>
      <ReplayProvenance summary={item} provenance={provenance.data??null} result={null} frame={null}/>
      <ResearchWorkloadPreview dataset={item} replayFrames={maxFrames} scenarioFrames={frames} executionMode={paper.mode}/>
      <div className="actions"><button type="button" className="primary" disabled={!ready} onClick={()=>void run()}>{pending?'Comparison worker running…':'Run Scenario / Historical Comparison'}</button></div>
      {validation&&<p role="alert" className="inlineError">{validation}</p>}
      <ResearchRunStatus operation="Scenario comparison"
        state={pending?'running':error?'error':response&&!current?'retired':current?'complete':'idle'}/>
      {response&&!current&&<StatusBanner>Retired result: captured {response.data.request.research_market} scenario / {response.data.request.historical.dataset_id}, segment {response.data.request.segment_index+1}. Run again for the current inputs or backend session. Financial displays are hidden.</StatusBanner>}
      {selectionCurrent&&<Panel title="Independent historical segments" meta="SELECTION RERUNS VALIDATED EVIDENCE">
        <label>Selected historical segment<select aria-label="Comparison historical segment" value={segmentIndex} disabled={pending}
          onChange={e=>{const index=Number(e.target.value);epoch.current++;setSegmentIndex(index);void run(index)}}>
          {response.data.segments.map(s=><option key={s.segment_index} value={s.segment_index}>Segment {s.segment_index+1} · {s.reset_reason} · {s.frame_count} frames</option>)}
        </select></label>
        <p className="muted panelNote">{response.data.segment_count} independent segments. Each resets capital, positions, orders and risk. Selection reruns the bounded replay and scenario; there is no persistent result session.</p>
        <details><summary>Receipt gaps and excluded evidence</summary>
          {response.data.declared_gaps.map((g,i)=><p key={i}>{g.reason} · {g.start_at} → {g.end_at}</p>)}
          {!response.data.declared_gaps.length&&<p>No gaps declared; continuous coverage remains unverified.</p>}
          {response.data.issues.map((i,n)=><p key={n}>{i.code} · {i.missing_fields.join(', ')}</p>)}
          <p>{response.data.omitted_issues} additional issues omitted.</p>
        </details>
      </Panel>}
      <details className="srcDisclosure"><summary>Developer receipt inspector (local, unauthenticated)</summary>
        <p>Only display structure is checked locally. Pasted hashes and origin are not independently authenticated.</p>
        <button type="button" onClick={()=>setShowImport(!showImport)}>Inspect backend receipt JSON</button>
        {showImport&&<form onSubmit={importLocal} className="srcInputForm"><label htmlFor="src-receipt">Phase 16.5B receipt JSON (256 KB maximum)</label>
          <textarea id="src-receipt" rows={5} value={json} maxLength={256000} onChange={e=>{setJson(e.target.value);setLocalReceipt(null)}}/>
          <button type="submit" disabled={!json.trim()}>Inspect receipt</button></form>}
        {localReceipt&&<p role="status">Local receipt shape accepted for display only; hashes and origin unverified.</p>}
      </details>
    </>}
    <ResearchDiagnostics error={error||validationError}/>
    {!checked?<Empty>No current comparison receipt loaded.</Empty>:<>
      <Panel title="Research pairing status" meta="SCENARIO / SELECTED HISTORICAL SEGMENT">
        <div className="srcPairing">
          <div><small>DETERMINISTIC SCENARIO</small><strong>{checked.foundation.scenario.market}-PERP</strong><span>Generated simulation · {checked.foundation.scenario.frame_count} frames</span></div>
          <div><strong>{checked.foundation.classification}</strong><small>{checked.display_policy==='BLOCKED'?'Metric display blocked':'Descriptive evidence only'}</small></div>
          <div><small>HISTORICAL PAPER SEGMENT</small><strong>{checked.foundation.historical.market}-PERP</strong><span>Segment {(checked.foundation.historical.segment_index??0)+1} / {checked.foundation.historical.replay_segment_count} · {checked.foundation.historical.source_kind}</span></div>
        </div>
        {current&&<details className="srcDisclosure"><summary>Captured request identity</summary><code className="srcHash">{response.data.request_fingerprint}</code><pre>{JSON.stringify(response.data.request,null,2)}</pre></details>}
      </Panel>
      <ComparisonMetrics receipt={checked}/>
      <ComparisonTraceCharts receipt={checked} evidence={serverReceipt?evidence:undefined} transport={current&&!localReceipt?response.data:undefined}/>
      <ComparisonExplainability receipt={checked}/>
    </>}
  </section>;
}
