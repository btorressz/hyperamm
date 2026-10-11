import {create} from 'zustand';
import type {SimulationResult,ResearchEvidenceSummary,MarketResearchComparisonResult} from '../types';
import {researchSummary, type ComparisonBoundary} from '../utils/marketResearchComparison';
export type CompletedResearch = {id:string; label:string; research:ResearchEvidenceSummary};
export type FrozenComparison = {data:MarketResearchComparisonResult; boundary:ComparisonBoundary; receivedAt:number; historicalReason:string|null};
type State = {results:CompletedResearch[]; selectedId:string; version:number; artifact:FrozenComparison|null;
  retain:(result:SimulationResult,label?:string)=>void; select:(id:string)=>void;
  freeze:(artifact:FrozenComparison)=>void; retire:(reason:string)=>void};
export const useMarketResearchComparisonStore=create<State>((set,get)=>({
  results:[],selectedId:'',version:0,artifact:null,
  retain:(result,label='Completed individual PAPER run')=>{
    const research=researchSummary(result), id=research.run_fingerprint;
    set(s=>({results:[{id,label,research},...s.results.filter(r=>r.id!==id)].slice(0,3),
      selectedId:s.selectedId===id?'':s.selectedId,version:s.version+1,
      artifact:s.artifact?{...s.artifact,historicalReason:'A newer completed research result was accepted.'}:null}));
  },
  select:id=>{
    if(id && !get().results.some(r=>r.id===id))throw new Error('Completed research result unavailable');
    if(id===get().selectedId)return;
    set(s=>({selectedId:id,version:s.version+1,artifact:s.artifact?{...s.artifact,historicalReason:'Research selection changed.'}:null}));
  },
  freeze:artifact=>set({artifact}),
  retire:reason=>set(s=>({artifact:s.artifact?{...s.artifact,historicalReason:s.artifact.historicalReason??reason}:null})),
}));
