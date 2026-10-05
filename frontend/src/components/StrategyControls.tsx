import { useEffect,useState,type ChangeEvent } from 'react'
import { api } from '../api/client'
import type { StrategyConfig,TerminalState } from '../types'
export function StrategyControls({t}:{t:TerminalState}){
  const [c,setC]=useState<StrategyConfig>(t.strategy.config),[msg,setMsg]=useState('')
  useEffect(()=>setC(t.strategy.config),[t.strategy.config])
  const set=(k:keyof StrategyConfig,v:unknown)=>setC(x=>({...x,[k]:v}))
  const update=async()=>{try{await api.updateStrategy(c);setMsg('Strategy updated')}catch(e){setMsg(String(e))}}
  const input=(key:keyof StrategyConfig,label:string)=><label>{label}<input value={String(c[key])} onChange={(e:ChangeEvent<HTMLInputElement>)=>set(key,e.target.value)}/></label>
  return <section className="panel controls"><div className="panelHead"><b>AMM Control Panel</b><span>Server validated</span></div>
    <div className="controlGroup"><h4>AMM & Execution</h4><div className="formGrid">
      <label>Market data<select value={c.market_data_mode} onChange={(e)=>set('market_data_mode',e.target.value)}><option value="DEMO">DEMO</option><option value="LIVE">LIVE</option></select></label>
      <label>Execution<select value={c.execution_mode} onChange={(e)=>set('execution_mode',e.target.value)}><option value="PAPER">PAPER</option><option value="TESTNET">TESTNET</option></select></label>
      <label>AMM Model<select value={c.amm_model} onChange={(e)=>set('amm_model',e.target.value)}><option>CONSTANT_PRODUCT</option><option>CONCENTRATED</option></select></label>
      <label>Levels / side<input type="number" value={c.levels_per_side} onChange={(e)=>set('levels_per_side',Number(e.target.value))}/></label>
      {input('max_distance_bps','Max distance (bps)')}{input('total_liquidity','Liquidity / side')}{input('base_order_size','Base order size')}{input('virtual_base_reserve','Virtual base reserve')}{input('virtual_quote_reserve','Virtual quote reserve')}{input('concentration_factor','Concentration factor')}{input('concentration_lower_bps','Lower bound (bps)')}{input('concentration_upper_bps','Upper bound (bps)')}
      <label>Refresh (ms)<input type="number" value={c.quote_refresh_interval_ms} onChange={(e)=>set('quote_refresh_interval_ms',Number(e.target.value))}/></label>
    </div></div>
    <div className="controlGroup"><h4>Inventory-Aware Quoting</h4><div className="formGrid">
      <label>Inventory skew<select value={c.inventory_skew_enabled?'ENABLED':'DISABLED'} onChange={(e)=>set('inventory_skew_enabled',e.target.value==='ENABLED')}><option>ENABLED</option><option>DISABLED</option></select></label>
      {input('target_inventory_base','Target inventory')}{input('soft_inventory_limit_base','Soft inventory limit')}{input('hard_inventory_limit_base','Hard inventory limit')}{input('max_inventory_price_skew_bps','Max price skew (bps)')}{input('inventory_size_skew_strength','Size skew strength')}{input('min_inventory_size_multiplier','Min size multiplier')}{input('max_inventory_size_multiplier','Max size multiplier')}
      <label>Inventory stale after (s)<input type="number" value={c.inventory_stale_after_seconds} onChange={(e)=>set('inventory_stale_after_seconds',Number(e.target.value))}/></label>
    </div><small className="controlHint">Disabling skew removes price/size bias; hard inventory limits remain safety-authoritative.</small></div>
    <div className="actions"><button className="primary" onClick={update}>Update Strategy</button><button onClick={()=>setC(t.strategy.config)}>Reset</button><button className="goodBtn" onClick={()=>api.start()}>Start</button><button onClick={()=>api.stop()}>Stop</button></div>{msg&&<small className="formMsg">{msg}</small>}
  </section>
}
