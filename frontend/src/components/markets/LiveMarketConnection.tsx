import { useLiveMarketStore } from '../../stores/liveMarkets';
import { liveFreshness } from '../../utils/liveMarketEvidence';
import { Panel, Metrics, StatusBanner } from '../TerminalPrimitives';
export function LiveMarketConnection({now,retry}:{now:number;retry:()=>void}) {
  const s=useLiveMarketStore(), snap=s.evidence?.snapshot, status=snap?.status, f=liveFreshness(s.evidence,now,s.current);
  const confirmed=s.current && s.streamStatus==='CONNECTED' && status?.connection_state==='CONNECTED' && status.subscription_state==='OBSERVED';
  const message=s.streamStatus==='DISABLED'?'Live market observation is disabled by the backend operator'
    :!s.current?s.connectionNotice ?? 'Waiting for validated observations'
    :!f.book?'L2 source stale or unavailable · last observation retained for inspection'
    :confirmed?'Native market evidence available · confirmed backend streaming'
    :`${snap?.order_book?.source==='OFFICIAL_SDK_REST'?'Fresh REST source observation':'Fresh source observation'} · streaming not yet confirmed`;
  return <Panel title={`${s.selectedLiveMarket}-PERP observation connection`} meta={`Browser ${s.streamStatus} · backend ${status?.connection_state ?? 'UNAVAILABLE'}`}>
    <StatusBanner>{message}</StatusBanner>
    {s.connectionNotice && s.current && <p role="status">{s.connectionNotice}</p>}
    {!f.perp && <p className="muted">Perpetual context unavailable or stale · mark and funding not current.</p>}
    <details><summary>Freshness ages, connection counters and source identity</summary>
    <Metrics items={[
      ['Subscription',status?.subscription_state ?? '—'],['Generation',status?.connection_generation ?? '—'],
      ['Reconnects',status?.reconnect_count ?? '—'],['Rejected / dropped backend',status?`${status.rejected_update_count} / ${status.dropped_update_count}`:'—'],
      ['Rejected browser frames',s.rejectedFrames],['L2 source age',f.ages.l2===null?'Unavailable':`${f.ages.l2.toFixed(1)}s`],
      ['Context receipt age',f.ages.perp===null?'Unavailable':`${f.ages.perp.toFixed(1)}s`],['Metadata age',f.ages.metadata===null?'Unavailable':`${f.ages.metadata.toFixed(1)}s`],
    ]}/>
    <dl className="liveDetails">
      <dt>L2 exchange time</dt><dd>{status?.last_l2_source_timestamp ?? 'Unavailable'}</dd>
      <dt>L2 receipt</dt><dd>{status?.last_l2_observed_at ?? 'Unavailable'}</dd>
      <dt>Context receipt</dt><dd>{status?.last_perp_observed_at ?? 'Unavailable'}</dd>
      <dt>Observer</dt><dd>{s.observerInstanceId ?? 'Unavailable'}</dd>
      <dt>Publication sequence (not exchange sequence)</dt><dd>{s.latestStreamSequence || 'No accepted stream frame'}</dd>
      <dt>Backend error</dt><dd>{status?.last_error_code ?? 'None reported'}</dd>
    </dl></details>
    <button onClick={retry}>Retry live observation</button>
  </Panel>;
}
