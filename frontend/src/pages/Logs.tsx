import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { EventCategory, TerminalState } from "../types";
import { Panel, Empty } from "../components/TerminalPrimitives";
import { EventTimeline } from "../components/EventTimeline";
const categories: EventCategory[] = [
  "MARKET",
  "REFERENCES",
  "STRATEGY",
  "AGENTS",
  "RISK",
  "EXECUTION",
  "ACCOUNTING",
  "SYSTEM",
];
export function Logs({ t }: { t: TerminalState }) {
  const [category, setCategory] = useState<EventCategory | undefined>();
  const q = useQuery({
    queryKey: ["terminal-events", t.session_id, category],
    queryFn: () => api.terminalEvents(category, 200),
    refetchInterval: 5000,
  });
  return (
    <div className="stack">
      <h1>System event timeline</h1>
      <Panel title="Structured events" meta="Read-only · bounded to 500 events">
        <div className="chartToolbar segmented">
          {[undefined, ...categories].map((c) => (
            <button
              key={c ?? "ALL"}
              aria-pressed={category === c}
              onClick={() => setCategory(c)}
            >
              {c ?? "ALL"}
            </button>
          ))}
        </div>
        {q.isPending ? (
          <Empty>Loading events…</Empty>
        ) : q.isError ? (
          <p className="inlineError" role="alert">
            Events unavailable: {String(q.error)}
          </p>
        ) : (
          <EventTimeline events={q.data.events} />
        )}
      </Panel>
    </div>
  );
}
