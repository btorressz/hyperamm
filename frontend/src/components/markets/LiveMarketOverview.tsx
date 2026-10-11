import { useQueries } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useLiveMarketStore } from '../../stores/liveMarkets';
import { checkedLiveSnapshot, liveFreshness, liveMarketIds, type ReceivedSnapshot } from '../../utils/liveMarketEvidence';
import { livePrice, percentage } from '../../utils/format';
import { Badge } from '../Badge';
export function LiveMarketOverview({now}:{now:number}) {
  const s=useLiveMarketStore();
  const queries=useQueries({queries:liveMarketIds.map(m=>({queryKey:['live-overview',m,s.selectionEpoch,s.boundaryVersion],
    retry:false,staleTime:15000,gcTime:0,refetchInterval:15000,refetchOnWindowFocus:false,
    queryFn:async({signal}:{signal:AbortSignal}):Promise<ReceivedSnapshot>=>{
      const started=performance.now();
      const snapshot=checkedLiveSnapshot(await api.liveStreamSnapshot(m,signal),m);
      return {snapshot,receivedAt:performance.now(),transitSeconds:Math.max(0,(performance.now()-started)/1000,(Date.now()-Date.parse(snapshot.status.evaluated_at))/1000)};
    }}))});
  return <div className="liveOverview" aria-label="Three native perpetual observations">
    {liveMarketIds.map((m,i)=>{
      const q=queries[i], selected=m===s.selectedLiveMarket;
      const e=selected?s.evidence:q.data ?? null;
      const f=liveFreshness(e,Math.max(now,performance.now()),selected?s.current:!q.isError);
      const snap=e?.snapshot;
      return <section className={`panel liveCard ${selected?'selected':''}`} key={m} aria-label={`${m}-PERP overview`}>
        <div className="panelHead"><h2>{m}-PERP</h2><Badge tone="neutral">{snap ? selected&&!s.current?`LAST REPORTED ${snap.observation_status}`:snap.observation_status :q.isError?'UNAVAILABLE':'CONNECTING'}</Badge></div>
        <strong className="liveCardPrice">{livePrice(f.book?snap?.order_book?.midpoint:null)}</strong>
        <p className="muted">Mark {livePrice(f.perp?snap?.perp_context?.mark_price:null)} · funding {percentage(f.perp?snap?.perp_context?.funding_rate:null,4)}</p>
        <p>{snap?.status.connection_state ?? 'No backend evidence'} · book {f.book?'FRESH SOURCE':'STALE / UNAVAILABLE'} · age {f.ages.l2===null?'—':`${f.ages.l2.toFixed(1)}s`}</p>
        <p className="muted">{snap?.order_book?.source==='OFFICIAL_SDK_REST'?'REST observation':snap?.order_book?'Native WS observation':'No price observation'}{selected?` · browser ${s.streamStatus}`:''}</p>
        {q.isError && !selected && <button onClick={()=>void q.refetch()}>Retry {m} overview</button>}
      </section>;
    })}
  </div>;
}
