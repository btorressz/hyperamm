import type { LiveProviderHealth } from '../../types';
import { advancingAge } from '../../utils/freshness';
import { livePrice } from '../../utils/format';
import { Badge } from '../Badge';
import { Panel, Empty } from '../TerminalPrimitives';
const labels={HYPERLIQUID_MID:'Hyperliquid L2 midpoint',HYPERLIQUID_ORACLE:'Hyperliquid native oracle',HYPERLIQUID_MARK:'Hyperliquid perpetual mark',REDSTONE:'RedStone · primary / HTTP fallback',KRAKEN:'Kraken · exchange reference',COINGECKO:'CoinGecko · aggregator',YAHOO_FINANCE:'Yahoo Finance · research observation'};
export function LiveProviderStatus({evidence,now,current,bookCurrent,perpCurrent,bookBudget,perpBudget,sourceDegraded=false}:{evidence:{health:LiveProviderHealth;receivedAt:number;transitSeconds:number}|null;now:number;current:boolean;bookCurrent:boolean;perpCurrent:boolean;bookBudget:number;perpBudget:number;sourceDegraded?:boolean}) {
  return <Panel title="Observational provider evidence" meta="Trading authority NONE · consensus unavailable">
    <p className="muted panelNote">Native midpoint, oracle and mark belong to one Hyperliquid source group. Fresh source observations can exist during REST bootstrap; provider health does not confirm streaming. RedStone primary and fallback share one identity.</p>
    {evidence?<div className="tableWrap providerTable" role="region" aria-label="Live provider evidence" tabIndex={0}><table>
      <thead><tr><th scope="col">Provider / source group</th><th scope="col">Reported price</th><th scope="col">Health / transport</th><th scope="col">Source / receipt time</th></tr></thead>
      <tbody>{evidence.health.providers.map(p=>{
        const native=p.independent_source_group==='HYPERLIQUID';
        const age=advancingAge(p.age_seconds,evidence.receivedAt,now,evidence.transitSeconds);
        const book=p.provider==='HYPERLIQUID_MID';
        const usable=current && !p.stale && p.enabled && (!native || ((book?bookCurrent:perpCurrent) && age!==null && age<=(book?bookBudget:perpBudget)));
        // Stream health arrives sooner than the periodic provider GET. A cached
        // healthy row must not contradict a newly degraded native source.
        const degraded=native && sourceDegraded;
        const status=degraded && p.status==='HEALTHY'?'DEGRADED':p.status;
        return <tr key={p.provider}><td>{labels[p.provider]}<br/><span className="muted">{p.independent_source_group} · {p.role} · authority NONE</span></td>
          <td>{livePrice(usable?p.price:null)}{!usable&&p.price&&<small>Last reported {livePrice(p.price)} · historical</small>}</td>
          <td><Badge tone="neutral">{!p.enabled?p.status:!usable?'STALE / HISTORICAL':status}</Badge><br/>{p.transport} · {p.transport_quality ?? 'No transport evidence'}<br/>{p.error ?? (degraded?'Native source degraded':'No error reported')}<br/>{!p.enabled?'Not configured / No live evidence':`${age===null?'Uncertain age':age.toFixed(1)+'s'} · ${p.health_basis}`}</td>
          <td>Source {p.source_timestamp ?? 'Unknown'}<br/>Receipt {p.observed_at ?? 'Unavailable'}<br/>{p.event_time_verified?'Exchange-event-time evidence':'Event time unverified'}</td></tr>;
      })}</tbody>
    </table></div>:<Empty>No accepted per-market provider evidence.</Empty>}
    <p className="muted panelNote">Live Market Intelligence is observational only. Provider health does not authorize HyperAMM to place orders. No independent external quorum or consensus price is available.</p>
  </Panel>;
}
