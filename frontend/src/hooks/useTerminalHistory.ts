import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useTerminalStore } from "../stores/terminal";
import { useDisplayStore } from "../stores/display";
import type { HistoryRange } from "../types";
export function useTerminalHistory(range: HistoryRange = "session") {
  const session = useTerminalStore((s) => s.terminal?.session_id),
    limit = useDisplayStore((s) => s.historySize);
  return useQuery({
    queryKey: ["terminal-history", session, range, limit],
    queryFn: async () => {
      const history = await api.terminalHistory(range, limit);
      // A reset while the GET is in flight must not seed another session's cache.
      if (history.session_id !== session || history.range !== range)
        throw new Error("History session/range changed during request");
      return history;
    },
    refetchInterval: 5000,
    enabled: !!session,
  });
}
