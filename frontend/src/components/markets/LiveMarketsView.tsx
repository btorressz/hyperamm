import { useLiveMarket } from '../../hooks/useLiveMarket';
import { useLiveMarketHistory } from '../../hooks/useLiveMarketHistory';
import { liveFreshness } from '../../utils/liveMarketEvidence';
import { LiveMarketSelector } from './LiveMarketSelector';
import { LiveMarketOverview } from './LiveMarketOverview';
import { LiveMarketConnection } from './LiveMarketConnection';
import { LiveMarketChart } from './LiveMarketChart';
import { LiveMarketOrderBook } from './LiveMarketOrderBook';
import { LivePerpMetrics } from './LivePerpMetrics';
import { LiveProviderStatus } from './LiveProviderStatus';
import { LiveMarketHistory } from './LiveMarketHistory';
export function LiveMarketsView() {
  const {s,now,retry}=useLiveMarket(),{history,providers,limit,setLimit}=useLiveMarketHistory();
  const snap=s.evidence?.snapshot,f=liveFreshness(s.evidence,Math.max(now,performance.now()),s.current),decimals=snap?.metadata.sz_decimals ?? null;
  const acceptedHistory=history.data ?? null;
  return <div className="stack liveWorkspace" aria-label="Live Market Intelligence">
    <p className="muted">Read-only BTC / ETH / SOL observations. Operational strategy and PAPER research selection are independent.</p>
    <LiveMarketSelector/><LiveMarketOverview now={now}/><LiveMarketConnection now={Math.max(now,performance.now())} retry={retry}/>
    <div className="liveMarketColumns">
      <LiveMarketChart history={acceptedHistory} bookGap={snap?.status.l2_stale_after_seconds ?? 10} perpGap={snap?.status.perp_stale_after_seconds ?? 30}/>
      <LiveMarketOrderBook book={snap?.order_book ?? null} decimals={decimals} current={f.book} age={f.ages.l2}/>
    </div>
    <LivePerpMetrics context={snap?.perp_context ?? null} current={f.perp} decimals={decimals} market={s.selectedLiveMarket}/>
    {providers.isError&&<p role="alert">Provider evidence unavailable: {providers.error.message} <button onClick={()=>void providers.refetch()}>Retry provider evidence</button></p>}
    <LiveProviderStatus evidence={providers.data ?? null} now={Math.max(now,performance.now())} current={s.current} bookCurrent={f.book} perpCurrent={f.perp} bookBudget={snap?.status.l2_stale_after_seconds ?? 10} perpBudget={snap?.status.perp_stale_after_seconds ?? 30}/>
    {history.isError&&<p role="alert">Retained history unavailable: {history.error.message}</p>}
    <LiveMarketHistory history={acceptedHistory} limit={limit} onLimit={setLimit} refresh={()=>void history.refetch()} decimals={decimals}/>
  </div>;
}
