import type { LiveMarketHistory as History } from '../../types';
import { livePrice, liveSize, percentage } from '../../utils/format';
import { Panel, Empty, Metrics } from '../TerminalPrimitives';
export function LiveMarketHistory({history,limit,onLimit,refresh,decimals}:{history:History|null;limit:number;onLimit:(n:number)=>void;refresh:()=>void;decimals:number|null}) {
  return <Panel title="Actual retained observation history" meta="In memory · continuous history NOT verified">
    <div className="liveChartControls"><label>Retained record limit<select aria-label="Retained record limit" value={limit} onChange={e=>onLimit(Number(e.target.value))}>
      {[100,300,600,1000].map(n=><option key={n} value={n}>{n} records</option>)}</select></label><button onClick={refresh}>Refresh retained history</button></div>
    <Metrics items={[
      ['Retained points',history?.retained_point_count ?? '—'],['Returned points',history?.points.length ?? '—'],['Evicted points',history?.evicted_point_count ?? '—'],['History gaps',history?.gap_count ?? '—'],
      ['Coverage start (receipt)',history?.coverage_start ?? '—'],['Coverage end (receipt)',history?.coverage_end ?? '—'],
    ]}/>
    <details><summary>Inspect retained component records</summary>
      {history?.points.length?<div className="tableWrap" role="region" aria-label="Retained live observations" tabIndex={0}><table>
        <thead><tr>{['Observation / source','Observed time','Source time','Midpoint','Mark','Oracle','Raw funding','OI (base)','Observer / generation'].map(t=><th scope="col" key={t}>{t}</th>)}</tr></thead>
        <tbody>{history.points.slice().reverse().map((p,i)=><tr key={i}>
          <td>{p.kind} · {p.source}<br/>{p.observation_status}</td><td>{p.observed_at}</td><td>{p.source_timestamp ?? 'UNKNOWN'}</td>
          <td>{livePrice(p.midpoint)}</td><td>{livePrice(p.mark)}</td><td>{livePrice(p.oracle)}</td><td>{percentage(p.funding,6)}</td><td>{liveSize(p.open_interest,decimals)}</td><td>{p.observer_instance_id}<br/>generation {p.connection_generation}</td>
        </tr>)}</tbody></table></div>:<Empty>No retained observations.</Empty>}
    </details>
    <p className="muted panelNote">Restart creates a new observer and empties prior in-memory history. Null component values remain unavailable. No uninterrupted archive or prior-session coverage is implied.</p>
  </Panel>;
}
