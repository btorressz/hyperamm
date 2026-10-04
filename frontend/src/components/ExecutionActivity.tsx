import type { Fill,Order } from '../types'
const f=(x:unknown,d=2)=>Number(x).toLocaleString(undefined,{maximumFractionDigits:d})
export function ExecutionActivity({orders,fills}:{orders:Order[],fills:Fill[]}){
  const recentOrders=orders.slice(-6).reverse(),recentFills=fills.slice(-6).reverse()
  return <div className="grid activityGrid">
    <section className="panel"><div className="panelHead"><b>Paper Orders</b><span>{orders.length} lifecycle records</span></div><div className="tableWrap"><table><thead><tr><th>Side</th><th>Price</th><th>Size</th><th>Status</th><th>Client ID</th></tr></thead><tbody>{recentOrders.length?recentOrders.map(o=><tr key={`${o.client_order_id}-${o.status}`}><td className={o.side==='BID'?'bidText':'askText'}>{o.side}</td><td>{f(o.price)}</td><td>{f(o.size,4)}</td><td>{o.status}</td><td className="monoClip">{o.client_order_id}</td></tr>):<tr><td colSpan={5} className="emptyCell">No paper orders yet.</td></tr>}</tbody></table></div></section>
    <section className="panel"><div className="panelHead"><b>Paper Fills</b><span>Simulation is explicitly labeled</span></div><div className="tableWrap"><table><thead><tr><th>Side</th><th>Price</th><th>Size</th><th>Source</th></tr></thead><tbody>{recentFills.length?recentFills.map(x=><tr key={`${x.client_order_id}-${x.timestamp}`}><td className={x.side==='BID'?'bidText':'askText'}>{x.side}</td><td>{f(x.price)}</td><td>{f(x.size,4)}</td><td>{x.source}</td></tr>):<tr><td colSpan={4} className="emptyCell">No simulated fills yet.</td></tr>}</tbody></table></div></section>
  </div>
}
