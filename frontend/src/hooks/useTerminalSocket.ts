import { useEffect } from "react";
import { useTerminalStore } from "../stores/terminal";
import { validateTerminal } from "../utils/validateTerminal";
export function useTerminalSocket() {
  useEffect(() => {
    let ws: WebSocket | undefined,
      retry: number | undefined,
      closed = false,
      attempts = 0,
      delay = 1500,
      openedAt = 0;
    const state = () => useTerminalStore.getState();
    const connect = () => {
      if (closed) return;
      state().setWsState("connecting");
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/terminal`);
      ws.onopen = () => {
        openedAt = Date.now();
        state().setWsState("connecting");
      };
      ws.onmessage = (e) => {
        try {
          state().setTerminal(validateTerminal(JSON.parse(e.data)));
          if (!state().payloadError) delay = 1500;
        } catch (error) {
          state().setError(
            `PAYLOAD ERROR: ${error instanceof Error ? error.message : "Invalid JSON"}`,
          );
        }
      };
      ws.onclose = () => {
        if (closed) return;
        state().setWsState("disconnected");
        state().setReconnectAttempts(++attempts);
        retry = window.setTimeout(connect, delay);
        delay = Math.min(delay * 2, 10000);
      };
      ws.onerror = () => ws?.close();
    };
    const watchdog = window.setInterval(() => {
      const s = state();
      if (
        ws?.readyState === WebSocket.OPEN &&
        Date.now() - Math.max(s.lastMessageAt ?? 0, openedAt) > 5000 &&
        s.wsState !== "error"
      ) {
        s.setWsState("stale");
        ws.close();
      }
    }, 1000);
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      clearInterval(watchdog);
      ws?.close();
    };
  }, []);
}
