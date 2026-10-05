import type { TerminalState } from '../types'

const f=(x:unknown,d=2)=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d})

export function MarketAdaptationPanel({t}:{t:TerminalState}){
  const m=t.market_adaptation
  if(!m)return <section className="panel marketAdaptPanel"><div className="panelHead"><b>Market Adaptation</b><span>Waiting for state</span></div><div className="adaptEmpty">No Phase 6 decision yet.</div></section>
  const volPct=m.realized_volatility==null?null:Number(m.realized_volatility)*100
  const score=Math.max(0,Math.min(1,Number(m.volatility_score)))
  const imbalance=Math.max(-1,Math.min(1,Number(m.book_imbalance)))
  const imbalancePct=(imbalance+1)*50
  return <section className="panel marketAdaptPanel">
    <div className="panelHead"><b>Market Adaptation</b><span>{m.volatility_ready?m.regime:'WARMING UP'} · v{m.version}</span></div>
    <div className="adaptGrid">
      <div><span>Realized Volatility</span><b>{volPct==null?'—':f(volPct,4)+'%'}</b></div>
      <div><span>Volatility Score</span><b>{f(score,2)}</b></div>
      <div><span>Sample Count</span><b>{m.sample_count}</b></div>
      <div><span>Regime</span><b>{m.regime}</b></div>
      <div><span>Bid Depth</span><b>{f(m.bid_depth,3)}</b></div>
      <div><span>Ask Depth</span><b>{f(m.ask_depth,3)}</b></div>
      <div><span>Book Imbalance</span><b>{imbalance>=0?'+':''}{f(imbalance*100,1)}%</b></div>
      <div><span>Imbalance State</span><b>{m.imbalance_state.replace('_',' ')}</b></div>
      <div><span>Spread Multiplier</span><b>{f(m.spread_multiplier,2)}x</b></div>
      <div><span>Global Size</span><b>{f(m.global_size_multiplier,2)}x</b></div>
      <div><span>Bid Market Size</span><b>{f(m.bid_size_multiplier,2)}x</b></div>
      <div><span>Ask Market Size</span><b>{f(m.ask_size_multiplier,2)}x</b></div>
    </div>
    <div className="adaptGauge">
      <div className="gaugeLabels"><span>QUIET</span><span>NORMAL</span><span>ELEVATED</span><span>HIGH</span></div>
      <div className="gaugeTrack"><i style={{left:String(score*100)+'%'}}/></div>
    </div>
    <div className="adaptGauge">
      <div className="gaugeLabels"><span>ASK HEAVY</span><span>BALANCED</span><span>BID HEAVY</span></div>
      <div className="gaugeTrack"><i style={{left:String(imbalancePct)+'%'}}/></div>
    </div>
  </section>
}
