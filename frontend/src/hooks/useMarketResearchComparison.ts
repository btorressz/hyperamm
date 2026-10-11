import {useEffect,useRef} from 'react';
import {useMutation} from '@tanstack/react-query';
import {api} from '../api/client';
import {useMarketResearchComparisonStore} from '../stores/marketResearchComparison';
import {useLiveMarketStore} from '../stores/liveMarkets';
import {useResearchMarketStore} from '../stores/researchMarkets';
import {checkedMarketComparison,sameBoundary,type ComparisonBoundary} from '../utils/marketResearchComparison';
import {liveFreshness} from '../utils/liveMarketEvidence';

export function comparisonBoundary(requestGeneration:number):ComparisonBoundary|null {
  const r=useMarketResearchComparisonStore.getState(),l=useLiveMarketStore.getState();
  const selected=r.results.find(x=>x.id===r.selectedId)?.research;if(!selected)return null;
  return {market:l.selectedLiveMarket,liveSelection:l.selectionEpoch,liveBoundary:l.boundaryVersion,
    observer:l.observerInstanceId,generation:l.connectionGeneration,researchRun:selected.run_fingerprint,
    researchDataset:selected.dataset_fingerprint,researchProfile:selected.market_profile_fingerprint,researchVersion:r.version,
    researchEpoch:useResearchMarketStore.getState().evidenceEpoch,requestGeneration};
}
export function useMarketResearchComparison(now:number) {
  const r=useMarketResearchComparisonStore(),l=useLiveMarketStore(),epoch=useResearchMarketStore(s=>s.evidenceEpoch);
  const requestGeneration=useRef(0),abort=useRef<AbortController|null>(null);
  const mutation=useMutation({retry:false,gcTime:0,mutationFn:async()=>{
    abort.current?.abort();const controller=new AbortController();abort.current=controller;
    const token=++requestGeneration.current,boundary=comparisonBoundary(token);
    if(!boundary)throw new Error('Choose a completed PAPER result first.');
    const selected=useMarketResearchComparisonStore.getState().results.find(x=>x.id===boundary.researchRun)!;
    const req={market:boundary.market,research:structuredClone(selected.research)};
    const data=await api.compareMarketResearch(req,controller.signal);
    const current=comparisonBoundary(token);
    if(controller.signal.aborted || token!==requestGeneration.current || !current || !sameBoundary(boundary,current))
      throw new Error('Comparison response retired after research, market or observer changed. Explicitly compare again.');
    const checked=checkedMarketComparison(data,req,boundary);
    useMarketResearchComparisonStore.getState().freeze({data:checked,boundary,receivedAt:performance.now(),historicalReason:null});
    return checked;
  }});
  useEffect(()=>{
    ++requestGeneration.current;abort.current?.abort();
    useMarketResearchComparisonStore.getState().retire('Market, research, observer or browser connection boundary changed.');
  },[r.version,l.selectionEpoch,l.boundaryVersion,l.observerInstanceId,l.connectionGeneration,epoch]);
  useEffect(()=>()=>{++requestGeneration.current;abort.current?.abort();useMarketResearchComparisonStore.getState().retire('Workspace closed; retained comparison is historical.');},[]);
  useEffect(()=>{
    const a=r.artifact;if(!a || a.historicalReason)return;
    const frozen=liveFreshness({snapshot:a.data.observed.snapshot,receivedAt:a.receivedAt,transitSeconds:Math.max(0,(Date.now()-Date.parse(a.data.observed.snapshot.status.evaluated_at))/1000-(performance.now()-a.receivedAt)/1000)},Math.max(now,performance.now()),true);
    if(a.data.observed.book_eligible && !frozen.book || a.data.observed.context_eligible && !frozen.perp)
      useMarketResearchComparisonStore.getState().retire('Captured source freshness expired. A newer live publication does not renew this artifact.');
  },[now,r.artifact]);
  return {r,l,compare:()=>{if(!mutation.isPending)mutation.mutate();},pending:mutation.isPending,error:mutation.error?.message??''};
}
