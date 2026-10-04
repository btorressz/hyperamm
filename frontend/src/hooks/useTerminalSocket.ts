import { useEffect } from 'react'
import { useTerminalStore } from '../stores/terminal'
export function useTerminalSocket(){
  const setTerminal=useTerminalStore(s=>s.setTerminal),setWsState=useTerminalStore(s=>s.setWsState)
  useEffect(()=>{
    let ws:WebSocket|undefined; let retry:number|undefined; let closed=false
    const connect=()=>{
      if(closed)return; setWsState('connecting')
      const proto=location.protocol==='https:'?'wss':'ws'; ws=new WebSocket(`${proto}://${location.host}/ws/terminal`)
      ws.onopen=()=>setWsState('connected')
      ws.onmessage=(e)=>{try{setTerminal(JSON.parse(e.data))}catch{}}
      ws.onclose=()=>{setWsState('disconnected'); if(!closed)retry=window.setTimeout(connect,1500)}
      ws.onerror=()=>ws?.close()
    }
    connect(); return()=>{closed=true;if(retry)clearTimeout(retry);ws?.close()}
  },[setTerminal,setWsState])
}
