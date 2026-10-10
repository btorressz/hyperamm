import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useResearchMarketStore } from '../../stores/researchMarkets';
import { checkedMarketCatalog, researchMarketIds } from '../../utils/researchMarkets';
import type { ResearchMarketId } from '../../types';
import { ResearchMarketDetails } from './ResearchMarketDetails';
import '../../phase146.css';

export function ResearchMarketSelector() {
  const s = useResearchMarketStore();
  const query = useQuery({queryKey: ['research-markets', s.evidenceEpoch], retry: false,
    staleTime: 0, gcTime: 0, refetchOnWindowFocus: false,
    queryFn: async ({signal}) => {
      const epoch = s.evidenceEpoch;
      const catalog = checkedMarketCatalog(await api.researchMarkets(signal));
      if (!useResearchMarketStore.getState().acceptCatalog(catalog, epoch)) throw new Error('Retired market catalog response.');
      return catalog;
    }});
  const selected = s.catalog?.markets.find(p => p.market === s.selectedResearchMarket);
  return <section className="researchMarketSelector stack" aria-label="Research Perpetual Market">
    <div className="formGrid"><label>Research Perpetual Market<select aria-label="Research Perpetual Market" value={s.selectedResearchMarket}
      onChange={e => s.selectMarket(e.target.value as ResearchMarketId)} disabled={!s.catalog}>
      {researchMarketIds.map(id => <option key={id} value={id}>{id}-PERP — {{BTC:'Bitcoin',ETH:'Ethereum',SOL:'Solana'}[id]}</option>)}
    </select></label></div>
    {query.isPending && <p role="status">Loading / validating research market metadata…</p>}
    {query.isError && <p role="alert" className="inlineError">Market catalog unavailable: {query.error.message} <button onClick={() => void query.refetch()}>Retry markets</button></p>}
    {selected && <ResearchMarketDetails profile={selected}/>}
    <p className="muted">One selected market per isolated research request. Selection does not change the operational market, Vault accounting or trading authority.</p>
  </section>;
}
