import type { StrategyConfig } from '../types'
const API='/api/v1'
async function request<T>(path:string,init?:RequestInit):Promise<T>{
  const r=await fetch(`${API}${path}`,{headers:{'Content-Type':'application/json'},...init})
  if(!r.ok) throw new Error((await r.text())||`HTTP ${r.status}`)
  return r.json()
}
export const api={
  health:()=>request<{status:string;app:string;stale:boolean;mode:string;simulated:boolean}>('/health'),
  updateStrategy:(config:StrategyConfig)=>request('/strategy',{method:'PUT',body:JSON.stringify(config)}),
  start:()=>request('/strategy/start',{method:'POST'}), stop:()=>request('/strategy/stop',{method:'POST'}),
  kill:()=>request('/risk/kill',{method:'POST'}), resume:()=>request('/risk/resume',{method:'POST'})
}
