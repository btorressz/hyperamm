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
    queryFn: () => api.terminalHistory(range, limit),
    refetchInterval: 5000,
    enabled: !!session,
  });
}
