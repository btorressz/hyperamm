import { useTerminalStore } from "../stores/terminal";
import { validateTerminal } from "./validateTerminal";

export function startTerminalSocket() {
  let ws: WebSocket | undefined,
    retry: number | undefined,
    closed = false,
    attempts = 0,
    delay = 1500,
    connectedAt = Date.now(),
    lastValidFrameAt: number | null = null;
  const state = () => useTerminalStore.getState();
  const connect = () => {
    if (closed) return;
    state().setWsState("connecting");
    const proto = location.protocol === "https:" ? "wss" : "ws";
    connectedAt = Date.now();
    lastValidFrameAt = null;
    const socket = new WebSocket(`${proto}://${location.host}/ws/terminal`);
    ws = socket;
    socket.onopen = () => {
      if (closed || socket !== ws) return;
      connectedAt = Date.now();
      state().setWsState("connecting");
    };
    socket.onmessage = (e) => {
      if (closed || socket !== ws || socket.readyState !== WebSocket.OPEN) return;
      try {
        state().setTerminal(validateTerminal(JSON.parse(e.data)));
        if (!state().payloadError) {
          lastValidFrameAt = Date.now();
          delay = 1500;
        }
      } catch (error) {
        state().setError(
          `PAYLOAD ERROR: ${error instanceof Error ? error.message : "Invalid JSON"}`,
        );
      }
    };
    socket.onclose = () => {
      if (closed || socket !== ws) return;
      state().setWsState("disconnected");
      state().setReconnectAttempts(++attempts);
      retry = window.setTimeout(connect, delay);
      delay = Math.min(delay * 2, 10000);
    };
    socket.onerror = () => socket.close();
  };
  const watchdog = window.setInterval(() => {
    if (
      (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) &&
      Date.now() - (lastValidFrameAt ?? connectedAt) > 5000
    ) {
      state().setWsState("stale");
      ws?.close();
    }
  }, 1000);
  connect();
  return () => {
    closed = true;
    if (retry !== undefined) clearTimeout(retry);
    clearInterval(watchdog);
    ws?.close();
  };
}
