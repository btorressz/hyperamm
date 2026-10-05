import type { TerminalState } from '../types'
const f=(x:unknown,d=2)=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d})
const signed=(x:unknown,d=2)=>x==null?'—':(Number(x)>=0?'+':'')+f(x,d)

export function PerpContextPanel({t}:{t:TerminalState}){
  const p=t.perp_context
  if(!p)return <section className="panel perpPanel"><div className="panelHead"><b>Perpetual Market Context</b><span>Waiting for context</span></div><div className="perpEmpty">No normalized perp context is available.</div></section>
  const pos=p.position
  return <section className="panel perpPanel">
    <div className="panelHead"><b>Perpetual Market Context</b><span>{p.source}{p.simulated?' · SIMULATED':''} · v{p.version}</span></div>
    <div className="perpGrid">
      <div><span>Mark Price</span><b>${f(p.mark_price)}</b></div>
      <div><span>Oracle Price</span><b>${f(p.oracle_price)}</b></div>
      <div><span>Market Mid</span><b>${f(p.market_fair_value)}</b></div>
      <div><span>Strategy Reference</span><b>${f(p.strategy_reference_price)}</b></div>
      <div><span>Funding Rate</span><b>{signed(p.funding_rate,6)}</b></div>
      <div><span>Funding Score</span><b>{signed(p.funding_score,3)}</b></div>
      <div><span>Funding Shift</span><b>{signed(p.funding_shift_bps,2)} bps</b></div>
      <div><span>Reference Shift</span><b>{signed(p.reference_shift_bps,2)} bps</b></div>
      <div><span>Open Interest</span><b>{f(p.open_interest_base,2)}</b></div>
      <div><span>OI Notional</span><b>${f(p.open_interest_notional,0)}</b></div>
      <div><span>Mark / Oracle</span><b>{signed(p.mark_oracle_basis_bps,2)} bps</b></div>
      <div><span>Mark / Mid</span><b>{signed(p.mark_mid_basis_bps,2)} bps</b></div>
      <div><span>Oracle / Mid</span><b>{signed(p.oracle_mid_basis_bps,2)} bps</b></div>
      <div><span>Context Status</span><b>{p.stale?'STALE':'FRESH'}</b></div>
    </div>
    <div className="perpPositionHead"><b>Perp Position Context</b><span>{pos?.source??t.strategy.config.execution_mode}</span></div>
    <div className="perpGrid">
      <div><span>Position</span><b>{pos?signed(pos.signed_position_base,4):'—'}</b></div>
      <div><span>Entry Price</span><b>{pos?.entry_price!=null?'$'+f(pos.entry_price):'—'}</b></div>
      <div><span>Leverage</span><b>{pos?.leverage_value!=null?f(pos.leverage_value,2)+'x '+(pos.leverage_type??''):'—'}</b></div>
      <div><span>Liquidation Price</span><b>{pos?.liquidation_price!=null?'$'+f(pos.liquidation_price):'—'}</b></div>
      <div><span>Position Value</span><b>{pos?.position_value!=null?'$'+f(pos.position_value):'—'}</b></div>
      <div><span>Margin Used</span><b>{pos?.margin_used!=null?'$'+f(pos.margin_used):'—'}</b></div>
      <div><span>Unrealized PnL</span><b>{pos?.unrealized_pnl!=null?'$'+signed(pos.unrealized_pnl):'—'}</b></div>
      <div><span>ROE</span><b>{pos?.return_on_equity!=null?signed(Number(pos.return_on_equity)*100,2)+'%':'—'}</b></div>
    </div>
  </section>
}
