import type{SimulationMetrics}from'../types'
const f=(x:unknown,d=2)=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:d})
export function SimulationPanel({m}:{m:SimulationMetrics}){
 const risk=Object.entries(m.risk_state_counts).map(([k,v])=>k+' '+v).join(' · ')
 const regimes=Object.entries(m.agent_regime_counts).map(([k,v])=>k+' '+v).join(' · ')
 return <section className="panel simPanel"><div className="panelHead"><b>Simulation Metrics</b><span>SIMULATED · NO LIVE ORDERS</span></div><div className="simMetrics">
  <div><span>PnL</span><b>${f(m.session_pnl)}</b></div><div><span>Return</span><b>{f(m.return_pct,3)}%</b></div>
  <div><span>Max Drawdown</span><b>{f(Number(m.max_drawdown_pct)*100,3)}%</b></div><div><span>Ending Inventory</span><b>{f(m.ending_inventory_base,4)}</b></div>
  <div><span>Max Inventory Util.</span><b>{f(Number(m.max_inventory_utilization)*100,1)}%</b></div><div><span>Fills</span><b>{m.fill_count}</b></div>
  <div><span>Mean Markout</span><b>{f(m.mean_mature_markout_bps,2)} bps</b></div><div><span>Churn</span><b>{f(Number(m.reconciliation_churn_ratio)*100,1)}%</b></div>
 </div><div className="simSummary"><p><b>Risk</b> {risk||'—'}</p><p><b>Regimes</b> {regimes||'—'}</p></div></section>
}