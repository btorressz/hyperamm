import type { HistoricalReplayResult, ReplayFrame, ReplayProvenance, ReplaySummary } from '../../types/replay';
import { Panel, Empty } from '../TerminalPrimitives';
import { issueLabel } from '../../utils/replayEvidence';
export function ReplayProvenance({summary,provenance,result,frame}:{summary:ReplaySummary|null;provenance:ReplayProvenance|null;result:HistoricalReplayResult|null;frame:ReplayFrame|null}) {
  const p=result?.provenance ?? provenance;
  return <Panel title="Historical evidence & provenance" meta="SOURCE TRUST LIMITS · NO EXECUTION AUTHORITY">
    {!p?<Empty>Select an admitted dataset to inspect source identity and evidence coverage.</Empty>:<>
      <dl className="replayDetails">
        <div><dt>Source</dt><dd>{p.source_kind === 'RECORDED_NATIVE'?'User-asserted Hyperliquid recording':'Synthetic research fixture'}</dd></div>
        <div><dt>Observed L2 / context</dt><dd>{p.l2_count} / {p.perp_context_count}</dd></div>
        <div><dt>Verified-time *labels* / L2</dt><dd>{p.verified_l2_event_time_count} / {p.l2_count}</dd></div>
        <div><dt>Gaps</dt><dd>{p.gap_count}</dd></div>
        <div><dt>Source-time policy</dt><dd>{p.source_event_time_policy}</dd></div>
        <div><dt>Authenticated</dt><dd>No</dd></div>
        <div><dt>Independent license verification</dt><dd>No</dd></div>
        <div><dt>Historical coverage</dt><dd>{summary?.coverage_status ?? 'PARTIAL/UNKNOWN'} · not continuous</dd></div>
        {frame && <div><dt>Selected frame context receipt</dt><dd>{frame.context_observation.received_at} · exchange event time unknown</dd></div>}
      </dl>
      <details className="replayDetailsDisclosure"><summary>Inspect identity fingerprints</summary>
        <dl className="replayDetails">
          {([
            ['Dataset',p.dataset_fingerprint],['Source',p.source_fingerprint],
            ['Observations',p.observations_fingerprint],['Declared gaps',p.gaps_fingerprint],
            ['Replay request',result?.request_fingerprint],['Modeling',result?.modeling_fingerprint],
            ['Execution assumptions',result?.execution_assumptions_fingerprint],
            ['Replay result',result?.result_fingerprint]
          ] as Array<[string,string|null|undefined]>).map(([label,value])=>value?<div key={label}><dt>{label}</dt><dd><code className="replayHash">{value}</code></dd></div>:null)}
        </dl></details>
      {result && <>
        <h3>Declared receipt gaps</h3>
        {result.declared_gaps.length ? <ul className="replayIssues">{result.declared_gaps.map((g,i)=><li key={i}>{g.reason} · {g.start_at} → {g.end_at}</li>)}</ul>:<p className="muted">No gaps declared. That does not prove continuous coverage.</p>}
        <h3>Excluded or incomplete evidence</h3>
        {result.issues.length?<ul className="replayIssues">{result.issues.slice(0,100).map((issue,i)=><li key={i}>{issueLabel(issue)}</li>)}</ul>:<p className="muted">No explicit exclusions in the returned bounded replay.</p>}
        {result.issues.length>100&&<p className="muted">Showing first 100 reported issues.</p>}
      </>}
      <details className="replayDetailsDisclosure"><summary>Limitations and trust policy</summary>
        <ul className="replayIssues">{(result?.limitations??p.limitations).map((s,i)=><li key={i}>{s}</li>)}</ul>
      </details>
    </>}
  </Panel>;
}
