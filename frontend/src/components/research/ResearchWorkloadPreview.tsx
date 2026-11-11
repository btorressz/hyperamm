import type { ReplaySummary } from '../../types/replay';
import { researchWorkload } from '../../utils/researchStatus';
import { Panel } from '../TerminalPrimitives';

export function ResearchWorkloadPreview({dataset,replayFrames,scenarioFrames,executionMode}:{
  dataset:ReplaySummary|null; replayFrames:string; scenarioFrames?:string;
  executionMode:'BASELINE'|'MODELED_CROSSING';
}) {
  const workload=researchWorkload({dataset,replayFrames,scenarioFrames,executionMode});
  if(!dataset)return null;
  return <Panel title="Research workload preview" meta="PRE-SUBMISSION · NOT A TIME ESTIMATE">
    <dl className="researchWorkloadDetails">
      {workload.fields.map(field=><div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}
    </dl>
    {!workload.valid&&<p className="researchWorkloadWarning">Correct invalid frame limits before submitting.</p>}
    {workload.large&&<p className="researchWorkloadWarning">Large research request · shared worker capacity will be occupied during computation.</p>}
    <details className="researchWorkloadNotes"><summary>Coverage and execution limitations</summary>
      <ul>{workload.notes.map((note,i)=><li key={i}>{note}</li>)}</ul>
    </details>
  </Panel>;
}
