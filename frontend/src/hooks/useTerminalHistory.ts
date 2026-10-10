import { useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useTerminalStore } from "../stores/terminal";
import { useDisplayStore } from "../stores/display";
import { useResearchSession } from "./useResearchSession";
import { checkedHistory } from "../utils/terminalHistory";
import type { HistoryRange, TerminalHistory } from "../types";
export function useTerminalHistory(range: HistoryRange = "session") {
  const t = useTerminalStore((s) => s.terminal),
    ws = useTerminalStore((s) => s.wsState);
  const limit = useDisplayStore((s) => s.historySize),
    session = useResearchSession(t, ws !== "connected");
  const identity = `${t?.process_id}:${t?.session_id}:${range}:${limit}`;
  const last = useRef<{ identity: string; data: TerminalHistory } | null>(null);
  const query = useQuery({
    queryKey: [
      "terminal-history",
      t?.process_id,
      t?.session_id,
      session.epoch,
      range,
      limit,
    ],
    queryFn: async ({ signal }) => {
      session.check();
      const history = await api.terminalHistory(range, limit, signal);
      session.check();
      return checkedHistory(
        history,
        t!,
        useTerminalStore.getState(),
        range,
        limit,
      );
    },
    refetchInterval: session.enabled ? 5000 : false,
    enabled: session.enabled,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });
  if (query.data && session.enabled)
    last.current = { identity, data: query.data };
  const historical = !session.enabled;
  const data = session.enabled
    ? query.data
    : last.current?.identity === identity
      ? last.current.data
      : undefined;
  return { ...query, data, historical };
}
