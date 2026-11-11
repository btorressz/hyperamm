/** Phase 16.6C.1: presentation-only research status, diagnostics and workload metadata.
 * No progress telemetry, ETA, response polling, risk decisions, or server authority.
 */
import type { ReplaySummary } from '../types/replay';

export type ResearchRunState = 'idle' | 'running' | 'complete' | 'retired' | 'error';
export type ResearchProblem = 'busy' | 'storage' | 'validation' | 'size' | 'connection' | 'stale' | 'server' | 'unknown';
export type ResearchDiagnosis = { kind: ResearchProblem; title: string; action: string };

export function diagnoseResearchError(error: unknown): ResearchDiagnosis {
  const raw = error instanceof Error ? error.message : typeof error === 'string' ? error : '';
  // Use bounded generic guidance; never render untrusted server error bodies or
  // provider diagnostic strings as trusted operational instructions.
  const message = raw.slice(0, 350).toLowerCase();
  if (/429|busy|capacity/.test(message)) return {
    kind:'busy', title:'Shared research worker is busy',
    action:'Wait until the existing research computation completes, then submit once. A closed browser request does not free the backend worker.',
  };
  if (/413|exceeds.*(budget|limit)|oversized|too large/.test(message)) return {
    kind:'size', title:'Request or response exceeds a research limit',
    action:'Review bounded frame and trace settings. Large returned evidence cannot be bypassed through the browser.',
  };
  if (/503|storage|vault.*unavailable|admission unavailable|not configured/.test(message)) return {
    kind:'storage', title:'Research storage or admission is unavailable',
    action:'Check the local backend and its private historical replay storage configuration. Refresh the dataset catalog after service recovery.',
  };
  if (/422|rejected|invalid|provenance|fingerprint|mismatch/.test(message)) return {
    kind:'validation', title:'Research evidence or settings were rejected',
    action:'Review selected dataset identity, market, source provenance, frame bounds and execution assumptions; reload metadata before retrying.',
  };
  if (/abort|disconnect|network|connection|failed to fetch|load failed|backend connection/.test(message)) return {
    kind:'connection', title:'Browser connection to the backend was interrupted',
    action:'Check local backend availability and refresh evidence. The backend may still be processing the admitted job.',
  };
  if (/stale|retired|session/.test(message)) return {
    kind:'stale', title:'Research evidence belongs to an earlier selection or session',
    action:'Revalidate the selected source and rerun research; previously captured results are not current evidence.',
  };
  if (/500|internal|failed on the server/.test(message)) return {
    kind:'server', title:'Research could not be completed',
    action:'Review sanitized local backend diagnostics and retry after the service is healthy. No orders or strategies were activated by the research request.',
  };
  return {
    kind:'unknown', title:'Research request was not completed',
    action:'Review the local research settings and backend readiness, then retry. This interface cannot infer a server-side job outcome from the browser alone.',
  };
}

export type WorkloadField = {label:string; value:string};
export type ResearchWorkload = {fields:WorkloadField[]; large:boolean; valid:boolean; notes:string[]};
const boundedFrames = (text: string) => /^\d+$/.test(text) && Number.isSafeInteger(Number(text)) &&
  Number(text)>=2 && Number(text)<=5000;

export function researchWorkload(args:{
  dataset:ReplaySummary | null; replayFrames:string; scenarioFrames?:string;
  executionMode:'BASELINE'|'MODELED_CROSSING';
}):ResearchWorkload {
  const {dataset,replayFrames,scenarioFrames,executionMode}=args;
  const valid=boundedFrames(replayFrames) && (scenarioFrames===undefined || boundedFrames(scenarioFrames));
  const large=valid && (Number(replayFrames)>=1000 || (scenarioFrames!==undefined && Number(scenarioFrames)>=1000));
  const fields:WorkloadField[]=[
    {label:'Research market',value:dataset?dataset.market+'-PERP':'No admitted dataset selected'},
    {label:'Historical frame limit',value:boundedFrames(replayFrames)?replayFrames+' of 5,000 maximum':'Invalid frame limit'},
    ...(scenarioFrames===undefined?[]:[{label:'Scenario frame limit',value:boundedFrames(scenarioFrames)?scenarioFrames+' of 5,000 maximum':'Invalid frame limit'}]),
    {label:'PAPER execution',value:executionMode==='MODELED_CROSSING'?'Modeled crossing sensitivity':'Baseline'},
    {label:'Shared worker',value:'One research computation at a time'},
  ];
  if(dataset)fields.push(
    {label:'Admitted observations',value:String(dataset.observation_count)},
    {label:'Declared gaps',value:String(dataset.gap_count)},
    {label:'Source label',value:dataset.source_kind==='RECORDED_NATIVE'?'User-asserted recording':'Synthetic fixture'},
    {label:'Coverage status',value:dataset.coverage_status},
  );
  const notes=[
    'Frame limits are request ceilings, not a prediction of viable historical frames, fills or execution duration.',
    'Every independent historical segment resets PAPER capital, risk, inventory and orders; no return is combined across gaps.',
    'Cancellation, closing the tab or losing the browser connection does not guarantee the admitted backend computation has stopped.',
  ];
  if(large) notes.unshift('Large requested frame counts can occupy the single research worker for an extended period. No percentage or ETA is available.');
  if(dataset?.gap_count)notes.push('Declared gaps may exclude evidence and create multiple independent replay segments.');
  if(dataset?.coverage_status!=='PARTIAL' && dataset) notes.push('Coverage remains unknown; do not assume a continuous historical feed.');
  return {fields,large,valid,notes};
}
