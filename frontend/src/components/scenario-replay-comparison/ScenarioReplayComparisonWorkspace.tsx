import { useState, type FormEvent } from 'react';
import type { ComparisonChartEvidence, QuantitativeComparisonReceipt } from '../../types/scenarioReplayComparison';
import { parseComparisonReceipt, checkedQuantitativeReceipt } from '../../utils/scenarioReplayComparison';
import { Empty, Panel, StatusBanner } from '../TerminalPrimitives';
import { Badge } from '../Badge';
import { ComparisonMetrics } from './ComparisonMetrics';
import { ComparisonExplainability } from './ComparisonExplainability';
import { ComparisonTraceCharts } from './ComparisonTraceCharts';
import '../../phase165c.css';

type Props={receipt?:QuantitativeComparisonReceipt|null; evidence?:ComparisonChartEvidence};
/** Phase C.1 read-only visualization. Phase C.2 will supply a verified server receipt
 *  through the same props; importing JSON here only checks display structure.
 */
export function ScenarioReplayComparisonWorkspace({receipt:serverReceipt,evidence}:Props) {
  const [json,setJson]=useState('');
  const [localReceipt,setLocalReceipt]=useState<QuantitativeComparisonReceipt|null>(null);
  const [error,setError]=useState('');
  const [showImport,setShowImport]=useState(false);
  const active=serverReceipt??localReceipt;
  let checked:QuantitativeComparisonReceipt|null=null;
  let validationError='';
  if(active)try{checked=checkedQuantitativeReceipt(active);}
  catch(e){validationError=e instanceof Error?e.message:'Invalid comparison evidence.';}
  const importLocal=(event:FormEvent)=>{
    event.preventDefault();setError('');
    try{setLocalReceipt(parseComparisonReceipt(json));setShowImport(false);}
    catch(e){setLocalReceipt(null);setError(e instanceof Error?e.message:'Invalid comparison receipt.');}
  };
  return <section className="stack srcWorkspace" aria-label="Scenario vs Historical Replay Comparison Studio">
    <div className="researchPageTitle">
      <div><h2>Scenario vs Historical Replay</h2>
        <p className="muted">Explain what can and cannot be learned from two separately generated PAPER research paths.</p></div>
      <Badge tone="blue">16.5C.1 · READ ONLY</Badge>
    </div>
    <StatusBanner>
      This view never calculates performance differences, replays market data, deploys a strategy or places an order.
      Complete server comparison transport and native Chromium acceptance belong to Phase 16.5C.2.
    </StatusBanner>
    {!serverReceipt&&<Panel title="Load an existing Phase 16.5B comparison receipt" meta="LOCAL INSPECTION · NO DATA UPLOAD">
      <p className="muted panelNote">Phase 16.5B is currently a Python-only backend service with no comparison HTTP endpoint. This development viewer accepts a JSON receipt already produced and validated by that backend. It parses locally and does not send the text to the server. A browser cannot verify SHA-256 fingerprints, source authenticity or the original job’s provenance.</p>
      <button type="button" aria-expanded={showImport} onClick={()=>setShowImport(!showImport)}>
        {showImport?'Close local receipt inspector':'Inspect backend receipt JSON'}
      </button>
      {showImport&&<form onSubmit={importLocal} className="srcInputForm">
        <label htmlFor="src-receipt">Phase 16.5B receipt JSON (maximum 256 KB)</label>
        <textarea id="src-receipt" rows={5} value={json} maxLength={256000}
          placeholder='{"version":"phase165b-v1", ...}'
          onChange={e=>{setJson(e.target.value);setLocalReceipt(null);setError('');}}/>
        <div className="actions">
          <button type="submit" className="primary" disabled={!json.trim()}>Inspect receipt</button>
          <button type="button" onClick={()=>{setJson('');setLocalReceipt(null);setError('');}}>Clear</button>
        </div>
      </form>}
      {error&&<p className="inlineError" role="alert">{error}</p>}
      {localReceipt&&<p role="status" className="muted panelNote">Local receipt shape accepted for display only. Its hashes and origin have not been independently verified by the browser.</p>}
    </Panel>}
    {validationError&&<p className="inlineError" role="alert">{validationError}</p>}
    {!checked?<Empty>No authoritative comparison response loaded. Phase 16.5C.2 must connect this studio to the existing bound scenario and historical replay receipts using a server-validated comparison workflow. No example PnL is shown.</Empty>:<>
      <Panel title="Research pairing status" meta="SCENARIO / SELECTED HISTORICAL SEGMENT">
        <div className="srcPairing">
          <div><small>DETERMINISTIC SCENARIO</small><strong>{checked.foundation.scenario.market}-PERP</strong>
            <span>Generated simulation · {checked.foundation.scenario.frame_count} frames</span></div>
          <div><strong>{checked.foundation.classification}</strong><small>{checked.display_policy==='BLOCKED'?'Metric display blocked':'Descriptive evidence only'}</small></div>
          <div><small>HISTORICAL PAPER SEGMENT</small><strong>{checked.foundation.historical.market}-PERP</strong>
            <span>Segment {(checked.foundation.historical.segment_index??0)+1} / {checked.foundation.historical.replay_segment_count??'?'} · {checked.foundation.historical.source_kind}</span></div>
        </div>
      </Panel>
      <ComparisonMetrics receipt={checked}/>
      <ComparisonTraceCharts receipt={checked} evidence={serverReceipt?evidence:undefined}/>
      <ComparisonExplainability receipt={checked}/>
    </>}
  </section>;
}
