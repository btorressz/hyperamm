import type { ReplaySummary } from '../../types/replay';
import { Panel, Empty } from '../TerminalPrimitives';
export function ReplayDatasetSelector({ datasets, selected, onSelect, refreshing, refresh }:{
  datasets: ReplaySummary[]; selected: string; onSelect:(id:string)=>void; refreshing:boolean; refresh:()=>void;
}) {
  const item = datasets.find(x=>x.dataset_id === selected);
  return <Panel title="Historical dataset" meta="PRIVATE LOCAL VAULT · READ ONLY">
    <div className="replayControls">
      <label>Admitted dataset
        <select aria-label="Historical dataset" value={selected} onChange={e=>onSelect(e.target.value)}>
          <option value="">Select a dataset</option>
          {datasets.map(d=><option key={d.dataset_id} value={d.dataset_id}>{d.market}-PERP · {d.dataset_id}</option>)}
        </select>
      </label>
      <button type="button" onClick={refresh} disabled={refreshing}>{refreshing?'Loading…':'Refresh catalog'}</button>
    </div>
    {item ? <dl className="replayDetails">
      <div><dt>Market</dt><dd>{item.market}-PERP</dd></div>
      <div><dt>Source</dt><dd>{item.source_kind === 'RECORDED_NATIVE'?'User-asserted recording':'Synthetic fixture'}</dd></div>
      <div><dt>Coverage</dt><dd>{item.coverage_status} · {item.observation_count} observations</dd></div>
      <div><dt>Receipt start</dt><dd><time>{item.coverage_start}</time></dd></div>
      <div><dt>Receipt end</dt><dd><time>{item.coverage_end}</time></dd></div>
      <div><dt>Declared gaps</dt><dd>{item.gap_count}</dd></div>
    </dl> : <Empty>No dataset selected. An operator must first admit evidence into the configured private backend vault.</Empty>}
    <p className="muted panelNote">Source labels and permitted use are assertions, not independent licensing or exchange authentication. Coverage is never certified continuous.</p>
  </Panel>;
}
