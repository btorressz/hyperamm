import type { LiveStreamSnapshot } from '../../types';
import { livePrice, liveSize, percentage, bps, number } from '../../utils/format';
import { Metrics, Panel } from '../TerminalPrimitives';
export function LivePerpMetrics({context,current,decimals,market}:{context:LiveStreamSnapshot['perp_context'];current:boolean;decimals:number|null;market:string}) {
  const p=current?context:null;
  return <Panel title="Native perpetual metrics" meta={current?'Recent native context observation · event time unverified':'Context stale / unavailable'}>
    <Metrics items={[
      ['Mark price',livePrice(p?.mark_price)],['Native oracle price',livePrice(p?.oracle_price)],['Context midpoint',livePrice(p?.provider_mid_price)],
      ['Raw venue funding rate',percentage(p?.funding_rate,6)],['OI (base asset)',`${liveSize(p?.open_interest_base,decimals)} ${market}`],['OI notional (quote)',number(p?.open_interest_notional)],
      ['Premium',percentage(p?.premium,4)],['Mark / oracle basis',bps(p?.mark_oracle_basis_bps)],['Mark / mid basis',bps(p?.mark_mid_basis_bps)],['Oracle / mid basis',bps(p?.oracle_mid_basis_bps)],
    ]}/>
    <p className="muted panelNote">Context exchange event time UNKNOWN. Funding is the raw reported rate; no APY or projected income. Basis values are computed by the backend from the same context acquisition.</p>
    {context && <details><summary>Context source and receipt</summary><p>{context.source} · received {context.observed_at} · source timestamp unavailable.</p></details>}
  </Panel>;
}
