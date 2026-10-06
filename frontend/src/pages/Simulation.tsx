import{useState}from'react';import{useQuery}from'@tanstack/react-query';import{api}from'../api/client';import type{OptimizationResult,SimulationResult}from'../types';import{SimulationPanel}from'../components/SimulationPanel';import'../phase10.css'
const f=(x:unknown,d=2)=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:d})
const presets={
 Balanced:{strategy_grid:{levels_per_side:[6,8],concentration_factor:['6','10']},agent_grid:{regime_spread_strength:['0.3','0.5']}},
 Inventory:{strategy_grid:{max_inventory_price_skew_bps:['15','25'],inventory_size_skew_strength:['0.5','0.9']},agent_grid:{}},
 AdverseFlow:{strategy_grid:{volatility_spread_strength:['0.8','1.2']},agent_grid:{toxic_flow_adverse_markout_bps:['2','4'],toxic_flow_size_strength:['0.4','0.7']}}
} as const
export function Simulation(){
 const scenarios=useQuery({queryKey:['simulation-scenarios'],queryFn:api.simulationScenarios})
 const[scenario,setScenario]=useState('QUIET'),[frames,setFrames]=useState(120),[preset,setPreset]=useState<keyof typeof presets>('Balanced')
 const[result,setResult]=useState<SimulationResult|null>(null),[opt,setOpt]=useState<OptimizationResult|null>(null),[busy,setBusy]=useState(''),[error,setError]=useState('')
 const run=async()=>{setBusy('run');setError('');try{setResult(await api.runSimulation({scenario,frames,simulation:{max_frames:frames,record_trace:true,trace_max_points:250}}))}catch(e){setError(String(e))}finally{setBusy('')}}
 const optimize=async()=>{setBusy('opt');setError('');try{const p=presets[preset];setOpt(await api.optimizeSimulation({...p,training_scenarios:['TREND_UP','TREND_DOWN','HIGH_VOLATILITY'],validation_scenarios:['MEAN_REVERTING','FLASH_MOVE'],frames:Math.min(frames,250),max_candidates:32,top_n:5}))}catch(e){setError(String(e))}finally{setBusy('')}}
 return <><section className="panel pagePanel simControls"><div className="panelHead"><b>Simulation & Optimization</b><span>SIMULATED · PAPER · OFFLINE</span></div><div className="formGrid">
 <label>Scenario<select value={scenario} onChange={e=>setScenario(e.target.value)}>{(scenarios.data?.scenarios??[]).map(s=><option key={s.name} value={s.name}>{s.name}</option>)}</select></label>
 <label>Frames<input type="number" min={2} max={1000} value={frames} onChange={e=>setFrames(Math.max(2,Math.min(1000,Number(e.target.value))))}/></label>
 <label>Optimization preset<select value={preset} onChange={e=>setPreset(e.target.value as keyof typeof presets)}>{Object.keys(presets).map(x=><option key={x}>{x}</option>)}</select></label>
 </div><div className="actions"><button className="primary" disabled={!!busy} onClick={run}>{busy==='run'?'Running…':'Run Simulation'}</button><button disabled={!!busy} onClick={optimize}>{busy==='opt'?'Optimizing…':'Run Bounded Grid Search'}</button></div>
 <p className="muted">Research only. Results never modify the live strategy, risk settings, TESTNET state, or kill switch.</p>{error&&<p className="dangerText">{error}</p>}</section>
 {result&&<><SimulationPanel m={result.metrics}/><section className="panel pagePanel"><div className="panelHead"><b>{result.scenario}</b><span>{result.run_fingerprint.slice(0,16)}…</span></div><p className="muted">{result.limitations.join(' · ')}</p></section></>}
 {opt&&<section className="panel simCandidates"><div className="panelHead"><b>Highest-ranked candidates under this objective</b><span>{opt.candidate_count} valid · baseline included</span></div><div className="tableWrap"><table><thead><tr><th>Candidate</th><th>Train</th><th>Validation</th><th>Δ Score</th><th>Parameters</th></tr></thead><tbody><tr><td>BASELINE</td><td>{f(opt.baseline.training_score,2)}</td><td>{f(opt.baseline.validation_score,2)}</td><td>0</td><td>Current defaults</td></tr>{opt.ranked_candidates.map(c=><tr key={c.configuration_fingerprint}><td>{c.label}</td><td>{f(c.training_score,2)}</td><td>{f(c.validation_score,2)}</td><td>{f(c.score_delta,2)}</td><td className="monoClip">{JSON.stringify({...c.strategy_updates,...c.agent_updates})}</td></tr>)}</tbody></table></div><p className="muted">Ranking is deterministic training-scenario research. Validation is evaluation-only. No candidate is automatically applied or deployed.</p></section>}
 </>}
