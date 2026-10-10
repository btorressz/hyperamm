import { useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useTerminalStore } from "../stores/terminal";
import { useResearchSession } from "./useResearchSession";
import { checkedTerminalEvents } from "../utils/terminalEventView";
import type { EventCategory, TerminalEvents, TerminalState } from "../types";

export function useTerminalEvents(
  t: TerminalState,
  historical: boolean,
  category?: EventCategory,
  limit = 200,
) {
  const session = useResearchSession(t, historical);
  const identity = `${t.process_id}:${t.session_id}:${category ?? "ALL"}:${limit}`;
  const last = useRef<{
    identity: string;
    epoch: number;
    data: TerminalEvents;
  } | null>(null);
  const query = useQuery({
    queryKey: [
      "terminal-events",
      t.process_id,
      t.session_id,
      session.epoch,
      category,
      limit,
    ],
    queryFn: async ({ signal }) => {
      session.check();
      const data = await api.terminalEvents(category, limit, signal);
      session.check();
      return checkedTerminalEvents(
        data,
        t,
        useTerminalStore.getState(),
        category,
        limit,
      );
    },
    enabled: session.enabled,
    refetchInterval: session.enabled ? 5000 : false,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });
  if (session.enabled) {
    if (last.current?.epoch !== session.epoch) last.current = null;
    if (query.data)
      last.current = { identity, epoch: session.epoch, data: query.data };
  }
  return {
    ...query,
    historical: !session.enabled,
    checkCurrent: session.check,
    data: session.enabled
      ? query.data
      : last.current?.identity === identity
        ? last.current.data
        : undefined,
  };
}
