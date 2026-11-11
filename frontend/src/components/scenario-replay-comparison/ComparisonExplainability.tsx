import type { ComparisonDimension, QuantitativeComparisonReceipt } from '../../types/scenarioReplayComparison';
import { Panel } from '../TerminalPrimitives';

const labels: Record<ComparisonDimension,string> = {
  MARKET:'Research market',ENGINE:'Engine version',STRATEGY:'Strategy',
  AGENTS:'Agent configuration',RISK:'Risk authorization',
  ACCOUNTING:'PAPER accounting/capital',EXECUTION:'Execution assumptions',
  MARKET_PROFILE:'Market profile',SIMULATION_CONTROLS:'Simulation controls',
};
const labelsFor:Record<string,string> = {
  MARKET_MISMATCH:'Different market — no comparable economic experiment',
  ENGINE_VERSION_MISMATCH:'Different simulation engine revisions',
  STRATEGY_MISMATCH:'Different effective strategy inputs',
  AGENTS_MISMATCH:'Different captured agent settings',
  RISK_MISMATCH:'Different captured risk settings',
  ACCOUNTING_MISMATCH:'Different capital or accounting assumptions',
  EXECUTION_MISMATCH:'Different hypothetical execution assumptions',
  MARKET_PROFILE_MISMATCH:'Different research profile or precision',
  SIMULATION_CONTROLS_MISMATCH:'Different frame or trace controls',
  SCENARIO_AND_HISTORICAL_EVIDENCE_DIFFER:'Generated scenario data is distinct from historical research evidence',
  SCENARIO_INPUT_CAPTURE_NOT_ENGINE_ATTESTED:'Same-job capture is a service receipt, not independent engine authentication',
  TEMPORAL_ALIGNMENT_UNPROVEN:'Time windows do not establish equivalent price histories',
  HISTORICAL_SEGMENT_RESETS:'Replay contains independent capital resets or excluded evidence',
  RECORDED_NATIVE_SOURCE_UNAUTHENTICATED:'Recorded-native label is user asserted, not exchange authenticated',
  HISTORICAL_LICENSING_UNVERIFIED:'Source licensing has not been independently verified',
};
function Hash({label,value}:{label:string;value:string|null|undefined}) {
  return <div><dt>{label}</dt><dd><code className="srcHash">{value??'Unavailable'}</code></dd></div>;
}
export function ComparisonExplainability({receipt}:{receipt:QuantitativeComparisonReceipt}) {
  const f=receipt.foundation,scenario=f.scenario,history=f.historical;
  return <section aria-label="Comparison explainability and provenance" className="stack">
    <Panel title="Comparability explained" meta="SOURCE QUALITY · CONFIGURATION IDENTITY">
      <div className="srcSummary">
        <strong>{f.classification==='CONTEXT_ONLY'?'CONTEXT ONLY — descriptive side-by-side':
          'INCOMPARABLE — financial comparison blocked'}</strong>
        <p className="muted">Scenario: {scenario.market}-PERP · deterministic generated evidence. Historical segment: {history.market}-PERP · {history.source_kind.replace(/_/g,' ').toLowerCase()}.</p>
        <p>Even matching settings do not prove matching market conditions, time coverage, fill behavior or profitability.</p>
      </div>
      <div className="srcDimensions">
        <div><h3>Matching configuration identities</h3>
          {f.aligned_dimensions.length?<ul>{f.aligned_dimensions.map((d:ComparisonDimension)=><li key={d}>{labels[d]}</li>)}</ul>:<p>None</p>}
        </div>
        <div><h3>Differing configuration identities</h3>
          {f.differing_dimensions.length?<ul>{f.differing_dimensions.map((d:ComparisonDimension)=><li key={d}>{labels[d]}</li>)}</ul>:<p>None reported</p>}
        </div>
      </div>
      <h3>Why the comparison is limited</h3>
      <ul className="srcReasons">{f.reasons.map(reason=><li key={reason}>{labelsFor[reason]??reason.replace(/_/g,' ')}</li>)}</ul>
    </Panel>
    <Panel title="Evidence identity & receipt coverage" meta="FINGERPRINTS ARE NOT SOURCE AUTHENTICATION">
      <div className="srcTwoSources">
        <section><h3>Deterministic scenario</h3>
          <dl className="replayDetails">
            <div><dt>Engine</dt><dd>{scenario.engine_version}</dd></div>
            <div><dt>Frames</dt><dd>{scenario.frame_count}</dd></div>
            <div><dt>Time window</dt><dd>{scenario.window_status}</dd></div>
            <div><dt>Start</dt><dd>{scenario.window_start??'Unknown'}</dd></div>
            <div><dt>End</dt><dd>{scenario.window_end??'Unknown'}</dd></div>
          </dl>
        </section>
        <section><h3>Historical segment {history.segment_index===null?'?':history.segment_index+1}</h3>
          <dl className="replayDetails">
            <div><dt>Source</dt><dd>{history.source_kind}</dd></div>
            <div><dt>Segments in replay</dt><dd>{history.replay_segment_count??'Unknown'}</dd></div>
            <div><dt>Frames</dt><dd>{history.frame_count}</dd></div>
            <div><dt>Receipt start</dt><dd>{history.window_start??'Unknown'}</dd></div>
            <div><dt>Receipt end</dt><dd>{history.window_end??'Unknown'}</dd></div>
          </dl>
        </section>
      </div>
      <details className="srcDisclosure"><summary>Inspect exact fingerprints</summary>
        <dl className="replayDetails">
          <Hash label="Comparison receipt" value={receipt.receipt_fingerprint}/>
          <Hash label="Comparison foundation" value={f.comparison_fingerprint}/>
          <Hash label="Bound scenario input" value={receipt.scenario_receipt_fingerprint}/>
          <Hash label="Scenario run" value={scenario.run_fingerprint}/>
          <Hash label="Scenario dataset" value={scenario.original_dataset_fingerprint}/>
          <Hash label="Scenario config" value={scenario.captured.fingerprint}/>
          <Hash label="Original historical dataset" value={history.original_dataset_fingerprint}/>
          <Hash label="Selected engine segment dataset" value={history.engine_dataset_fingerprint}/>
          <Hash label="Selected replay run" value={history.run_fingerprint}/>
          <Hash label="Historical replay result" value={history.replay_result_fingerprint}/>
        </dl>
      </details>
    </Panel>
    <Panel title="Evidence limitations" meta="PAPER · UNAUTHENTICATED DATA RIGHTS">
      <ul className="srcReasons">{receipt.limitations.map((s,i)=><li key={i}>{s}</li>)}</ul>
      <details className="srcDisclosure"><summary>Additional comparison foundation limitations</summary>
        <ul>{f.limitations.map((s,i)=><li key={i}>{s}</li>)}</ul>
      </details>
    </Panel>
  </section>;
}
