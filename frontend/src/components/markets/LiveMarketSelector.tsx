import { useLiveMarketStore } from '../../stores/liveMarkets';
import { liveMarketIds, liveMarketNames } from '../../utils/liveMarketEvidence';
export function LiveMarketSelector() {
  const selected=useLiveMarketStore(s=>s.selectedLiveMarket), select=useLiveMarketStore(s=>s.selectMarket);
  return <div className="liveSelector" role="group" aria-label="Live observation market">
    {liveMarketIds.map(m=><button key={m} aria-pressed={selected===m} onClick={()=>select(m)}>{m}-PERP — {liveMarketNames[m]}</button>)}
  </div>;
}
