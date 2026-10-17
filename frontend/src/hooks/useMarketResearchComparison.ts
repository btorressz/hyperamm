import {useEffect,useRef} from 'react';
import {useMutation} from '@tanstack/react-query';
import {api} from '../api/client';
import {useMarketResearchComparisonStore} from '../stores/marketResearchComparison';
import {useLiveMarketStore} from '../stores/liveMarkets';
import {useResearchMarketStore} from '../stores/researchMarkets';
import {checkedMarketComparison,ComparisonRequestGate,type ComparisonBoundary} from '../utils/marketResearchComparison';
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
  // The gate owns AbortController and a monotonic generation across requests.
  const gate=useRef(new ComparisonRequestGate());
  const mutation=useMutation({retry:false,gcTime:0,mutationFn:async()=>{
    const ticket=gate.current.begin(),token=ticket.generation,boundary=comparisonBoundary(token);
    if(!boundary)throw new Error('Choose a completed PAPER result first.');
    const selected=useMarketResearchComparisonStore.getState().results.find(x=>x.id===boundary.researchRun)!;
    const req={market:boundary.market,research:structuredClone(selected.research)};
    const data=await api.compareMarketResearch(req,ticket.signal);
    const current=comparisonBoundary(token);
    if(!gate.current.accepts(ticket,boundary,current))
      throw new Error('Comparison response retired after research, market or observer changed. Explicitly compare again.');
    const checked=checkedMarketComparison(data,req,boundary);
    useMarketResearchComparisonStore.getState().freeze({data:checked,boundary,receivedAt:performance.now(),historicalReason:null});
    return checked;
  }});
  useEffect(()=>{
    gate.current.retire();
    useMarketResearchComparisonStore.getState().retire('Market, research, observer or browser connection boundary changed.');
  },[r.version,l.selectionEpoch,l.boundaryVersion,l.observerInstanceId,l.connectionGeneration,epoch]);
  useEffect(()=>()=>{gate.current.retire();useMarketResearchComparisonStore.getState().retire('Workspace closed; retained comparison is historical.');},[]);
  useEffect(()=>{
    const a=r.artifact;if(!a || a.historicalReason)return;
    const frozen=liveFreshness({snapshot:a.data.observed.snapshot,receivedAt:a.receivedAt,transitSeconds:a.transitSeconds??0},Math.max(now,performance.now()),true);
    if(a.data.observed.book_eligible && !frozen.book || a.data.observed.context_eligible && !frozen.perp)
      useMarketResearchComparisonStore.getState().retire('Captured source freshness expired. A newer live publication does not renew this artifact.');
  },[now,r.artifact]);
  return {r,l,compare:()=>{if(!mutation.isPending)mutation.mutate();},pending:mutation.isPending,error:mutation.error?.message??''};
}
