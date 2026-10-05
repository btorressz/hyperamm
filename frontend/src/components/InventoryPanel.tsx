import type { TerminalState } from '../types'
const f=(x:unknown,d=2)=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d})
export function InventoryPanel({t}:{t:TerminalState}){
  const i=t.inventory,c=t.strategy.config
  if(!i)return <section className="panel inventoryPanel"><div className="panelHead"><b>Inventory & Skew</b><span>Waiting for normalized state</span></div><div className="inventoryEmpty">Inventory state has not been computed yet.</div></section>
  const hard=Number(c.hard_inventory_limit_base),pos=Number(i.deviation_base),pct=hard>0?Math.max(0,Math.min(100,(pos+hard)/(2*hard)*100)):50
  const side=Number(i.deviation_base)>0?'LONG':Number(i.deviation_base)<0?'SHORT':'FLAT'
  return <section className="panel inventoryPanel">
    <div className="panelHead"><b>Inventory & Skew</b><span>{i.source} · v{i.version}</span></div>
    <div className="inventoryGrid">
      <div><span>Current Position</span><b>{Number(i.position_base)>=0?'+':''}{f(i.position_base,4)} {i.market}</b></div>
      <div><span>Target Position</span><b>{f(i.target_base,4)} {i.market}</b></div>
      <div><span>Inventory Deviation</span><b>{Number(i.deviation_base)>=0?'+':''}{f(i.deviation_base,4)}</b></div>
      <div><span>Inventory Ratio</span><b>{f(Number(i.inventory_ratio)*100,1)}%</b></div>
      <div><span>Fair Value</span><b><span className="money">$</span>{f(t.fair_value)}</b></div>
      <div><span>Reservation Price</span><b><span className="money">$</span>{f(i.reservation_price)}</b></div>
      <div><span>Price Skew</span><b>{f(i.price_skew_bps,2)} bps</b></div>
      <div><span>Bid / Ask Size</span><b>{f(i.bid_size_multiplier,2)}x / {f(i.ask_size_multiplier,2)}x</b></div>
    </div>
    <div className="inventoryGauge"><div className="gaugeLabels"><span>SHORT −{f(hard,2)}</span><span>TARGET</span><span>LONG +{f(hard,2)}</span></div><div className="gaugeTrack"><i style={{left:String(pct)+'%'}}/></div></div>
    <div className="inventoryState"><span className="statePill">{side} / {i.hard_limit_state}</span><small>{i.stale?'STALE':'FRESH'} · soft ±{f(c.soft_inventory_limit_base,2)}</small></div>
  </section>
}
