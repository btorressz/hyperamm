import type {TerminalState} from '../types'
const f=(x:unknown,d=2)=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:d})
export function AgentPanel({t}:{t:TerminalState}){
 const a=t.agents,s=a?.supervisor,r=a?.regime,tox=a?.toxic_flow,eq=a?.execution_quality
 if(!s)return <section className="panel agentPanel"><div className="panelHead"><b>Supervisory Agents</b><span>Waiting for evidence</span></div></section>
 const sim=s.simulated?' · PAPER / SIMULATED':''
 return <section className="panel agentPanel"><div className="panelHead"><b>Supervisory Agents</b><span>v{s.version}{sim}</span></div>
 <div className="agentGrid">
  <div><small>REGIME</small><b>{r?.state??'—'} · {r?.direction??'—'}</b><span>conf {f(r?.confidence,2)} · mom {f(r?.momentum_bps,1)} bps · vol {f(r?.volatility_score,2)}</span><em>{f(r?.spread_multiplier,2)}x spread / {f(r?.bid_size_multiplier,2)}x size</em></div>
  <div><small>TOXIC FLOW</small><b>{tox?.state??'—'}</b><span>score {f(tox?.metrics.overall_toxic_flow_score,2)} · bid {f(tox?.metrics.bid_toxic_flow_score,2)} · ask {f(tox?.metrics.ask_toxic_flow_score,2)}</span><em>{tox?.metrics.matured_fills??0} matured · {tox?.metrics.pending_markouts??0} pending · markout {f(tox?.metrics.mean_signed_markout_bps,1)} bps</em></div>
  <div><small>EXECUTION QUALITY</small><b>{eq?.state??'—'}</b><span>conf {f(eq?.confidence,2)} · fills {eq?.metrics.fill_count??0} · capture {f(eq?.metrics.average_spread_capture_bps,1)} bps</span><em>markout {f(eq?.metrics.average_mature_markout_bps,1)} bps · churn {f(Number(eq?.metrics.reconciliation_churn_ratio??0)*100,1)}% · reject/unknown {eq?.metrics.reject_count??0}/{eq?.metrics.unknown_order_count??0}</em></div>
  <div><small>SUPERVISOR</small><b>{s.enabled?'ENABLED':'DISABLED'}</b><span>{f(s.spread_multiplier,2)}x spread · bid {f(s.bid_size_multiplier,2)}x · ask {f(s.ask_size_multiplier,2)}x</span><em>max levels {s.max_levels??'—'} · fingerprint {s.fingerprint.slice(0,12)}…</em></div>
 </div>
 <div className="agentReasons">{s.reasons.map((x,i)=><p key={i}>• {x}</p>)}</div></section>
}