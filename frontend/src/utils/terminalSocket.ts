import { useTerminalStore } from "../stores/terminal";
import { boundedIncrement, terminalEnvelopeFailure, MAX_TERMINAL_ENVELOPE_AGE_MS } from "./terminalIntegrity";

// One controller owns the shared store, including across StrictMode replacement.
let activeStop: (() => void) | undefined;
export function startTerminalSocket() {
  activeStop?.();
  let ws: WebSocket | undefined, retry: number | undefined, closed = false,
    attempts = 0, delay = 1500, connectedAt = Date.now(), lastValidFrameAt: number | null = null;
  const state = () => useTerminalStore.getState();
  const connect = () => {
    if (closed) return;
    if (retry !== undefined) { clearTimeout(retry); retry = undefined; }
    state().setWsState("connecting");
    const proto = location.protocol === "https:" ? "wss" : "ws";
    connectedAt = Date.now();
    lastValidFrameAt = null;
    const socket = new WebSocket(`${proto}://${location.host}/ws/terminal`);
    let closeHandled = false;
    ws = socket;
    socket.onopen = () => {
      if (closed || socket !== ws || closeHandled) return;
      // Handshake is transport evidence only; it never renews observation time.
      state().setWsState("connecting");
    };
    socket.onmessage = (e) => {
      if (closed || socket !== ws || socket.readyState !== WebSocket.OPEN || closeHandled) return;
      let payload: unknown;
      try { payload = JSON.parse(e.data); } catch {
        state().setError("PAYLOAD ERROR: Invalid JSON");
        return;
      }
      const now = Date.now();
      const result = state().setTerminal(payload, now);
      if (result.accepted) { lastValidFrameAt = now; delay = 1500; }
    };
    socket.onclose = () => {
      if (closed || socket !== ws || closeHandled) return;
      closeHandled = true;
      state().setWsState("disconnected");
      state().setReconnectAttempts(attempts = boundedIncrement(attempts));
      retry = window.setTimeout(connect, delay);
      delay = Math.min(delay * 2, 10000);
    };
    socket.onerror = () => {
      if (!closed && socket === ws && !closeHandled) socket.close();
    };
  };
  const watchdog = window.setInterval(() => {
    const now = Date.now();
    if ((ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) && (
      now - (lastValidFrameAt ?? connectedAt) > MAX_TERMINAL_ENVELOPE_AGE_MS ||
      (lastValidFrameAt !== null && state().terminal !== null &&
        terminalEnvelopeFailure(state().terminal!.emitted_at, now) !== null)
    )) {
      state().setWsState("stale");
      ws?.close();
    }
  }, 1000);
  const stop = () => {
    if (closed) return;
    closed = true;
    if (retry !== undefined) clearTimeout(retry);
    clearInterval(watchdog);
    ws?.close();
    if (activeStop === stop) { activeStop = undefined; state().setWsState("disconnected"); }
  };
  activeStop = stop;
  connect();
  return stop;
}
