import { create } from "zustand";
import type { TerminalState } from "../types";
export type WsState =
  "connecting" | "connected" | "disconnected" | "stale" | "error";
type Store = {
  terminal: TerminalState | null;
  wsState: WsState;
  lastMessageAt: number | null;
  lastSequence: number | null;
  terminalContractVersion: string | null;
  payloadError: string | null;
  connectionNotice: string | null;
  reconnectAttempts: number;
  setTerminal: (x: TerminalState) => void;
  setWsState: (x: WsState) => void;
  setError: (error: string) => void;
  setReconnectAttempts: (n: number) => void;
};
export const useTerminalStore = create<Store>((set, get) => ({
  terminal: null,
  wsState: "connecting",
  lastMessageAt: null,
  lastSequence: null,
  terminalContractVersion: null,
  payloadError: null,
  connectionNotice: null,
  reconnectAttempts: 0,
  setTerminal: (terminal) => {
    const s = get();
    if (
      s.terminal?.process_id === terminal.process_id &&
      s.lastSequence !== null &&
      terminal.sequence <= s.lastSequence
    ) {
      set({ payloadError: "Out-of-order terminal frame", wsState: "error" });
      return;
    }
    const restart =
        !!s.terminal && s.terminal.process_id !== terminal.process_id,
      gap =
        !restart &&
        s.lastSequence !== null &&
        terminal.sequence > s.lastSequence + 1;
    set({
      terminal,
      lastSequence: terminal.sequence,
      terminalContractVersion: terminal.contract_version,
      lastMessageAt: Date.now(),
      payloadError: null,
      wsState: "connected",
      connectionNotice: restart
        ? "Backend restarted; session history reset."
        : gap
          ? "Observation sequence gap; current snapshot loaded. Other observers may advance the sequence."
          : null,
    });
  },
  setWsState: (wsState) => set({ wsState }),
  setError: (payloadError) => set({ payloadError, wsState: "error" }),
  setReconnectAttempts: (reconnectAttempts) => set({ reconnectAttempts }),
}));
