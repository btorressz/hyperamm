import { create } from 'zustand'
import type { TerminalState } from '../types'
type Store={terminal:TerminalState|null,wsState:'connecting'|'connected'|'disconnected',setTerminal:(x:TerminalState)=>void,setWsState:(x:Store['wsState'])=>void}
export const useTerminalStore=create<Store>((set)=>({terminal:null,wsState:'connecting',setTerminal:(terminal)=>set({terminal}),setWsState:(wsState)=>set({wsState})}))
