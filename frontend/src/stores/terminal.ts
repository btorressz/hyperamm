import { create } from "zustand";
import type { TerminalState } from "../types";
import { validateTerminal } from "../utils/validateTerminal";
import { boundedIncrement, compareEmissionTimes, terminalEnvelopeFailure, RETIRED_IDENTITY_CAPACITY,
  type RejectionReason, type TerminalAcceptanceResult } from "../utils/terminalIntegrity";
export type WsState = "connecting" | "connected" | "disconnected" | "stale" | "error";
type Identity = { processId: string; sessionId: string };
type Store = {
  terminal: TerminalState | null;
  wsState: WsState;
  lastValidFrameAt: number | null;
  lastEmittedAtMs: number | null;
  lastSequence: number | null;
  retiredIdentities: Identity[];
  retiredProcesses: string[];
  rejectedFrames: Record<RejectionReason, number>;
  terminalContractVersion: string | null;
  payloadError: string | null;
  connectionNotice: string | null;
  reconnectAttempts: number;
  setTerminal: (x: unknown, nowMs?: number) => TerminalAcceptanceResult;
  setWsState: (x: WsState) => void;
  setError: (error: string, reason?: RejectionReason) => void;
  setReconnectAttempts: (n: number) => void;
};
const errors: Record<RejectionReason, string> = {
  schema: "Invalid terminal schema or JSON",
  stale: "Terminal envelope stale: emission is more than 5 seconds old",
  future: "Terminal clock error: emission is more than 2 seconds in the future",
  replay: "Retired terminal process/session replay rejected",
  sequence: "Out-of-order terminal frame: process sequence must increase",
  timeRegression: "Terminal emission time regressed within the active process",
};
export const useTerminalStore = create<Store>((set, get) => ({
  terminal: null, wsState: "connecting", lastValidFrameAt: null, lastEmittedAtMs: null,
  lastSequence: null, retiredIdentities: [], retiredProcesses: [],
  rejectedFrames: { schema: 0, stale: 0, future: 0, replay: 0, sequence: 0, timeRegression: 0 },
  terminalContractVersion: null, payloadError: null, connectionNotice: null, reconnectAttempts: 0,
  setTerminal: (value, nowMs = Date.now()) => {
    const reject = (reason: RejectionReason): TerminalAcceptanceResult => {
      get().setError(errors[reason], reason);
      return { accepted: false, reason };
    };
    let terminal: TerminalState;
    try { terminal = validateTerminal(value); } catch { return reject("schema"); }
    const emittedAtMs = Date.parse(terminal.emitted_at);
    const temporalFailure = terminalEnvelopeFailure(terminal.emitted_at, nowMs);
    if (temporalFailure) return reject(temporalFailure);
    const s = get(), previous = s.terminal;
    const sameProcess = previous?.process_id === terminal.process_id;
    if (s.retiredProcesses.includes(terminal.process_id) || s.retiredIdentities.some(
      id => id.processId === terminal.process_id && id.sessionId === terminal.session_id,
    )) return reject("replay");
    // Sequence is process-wide: changing only session cannot reset its watermark.
    if (sameProcess && s.lastSequence !== null && terminal.sequence <= s.lastSequence)
      return reject("sequence");
    if (sameProcess && previous && compareEmissionTimes(terminal.emitted_at, previous.emitted_at) < 0)
      return reject("timeRegression");
    const restarted = !!previous && !sameProcess;
    const transition = !!previous && (restarted || previous.session_id !== terminal.session_id);
    const gap = sameProcess && s.lastSequence !== null && terminal.sequence > s.lastSequence + 1;
    set({
      terminal, lastSequence: terminal.sequence, lastEmittedAtMs: emittedAtMs,
      terminalContractVersion: terminal.contract_version, lastValidFrameAt: nowMs,
      payloadError: null, wsState: "connected",
      retiredIdentities: transition
        ? [...s.retiredIdentities, { processId: previous.process_id, sessionId: previous.session_id }].slice(-RETIRED_IDENTITY_CAPACITY)
        : s.retiredIdentities,
      retiredProcesses: restarted
        ? [...s.retiredProcesses, previous.process_id].slice(-RETIRED_IDENTITY_CAPACITY)
        : s.retiredProcesses,
      connectionNotice: restarted ? "Backend process restarted; prior identity retired."
        : transition ? "Backend session changed; process sequence retained; prior session retired."
        : gap ? "Observation sequence gap; current snapshot loaded. Other observers may advance the sequence."
        : s.connectionNotice,
    });
    return { accepted: true, restarted };
  },
  setWsState: (wsState) => set({ wsState }),
  setError: (payloadError, reason = "schema") => set(s => ({
    payloadError, wsState: reason === "stale" ? "stale" : "error",
    rejectedFrames: { ...s.rejectedFrames, [reason]: boundedIncrement(s.rejectedFrames[reason]) },
  })),
  setReconnectAttempts: (reconnectAttempts) => set({ reconnectAttempts }),
}));
