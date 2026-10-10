import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { executionEvents } from "../utils/orderView";
import { EventTimeline } from "./EventTimeline";
import { Empty, Panel } from "./TerminalPrimitives";
export function ExecutionTimeline({
  session,
  historical,
}: {
  session: string;
  historical: boolean;
}) {
  const q = useQuery({
    queryKey: ["execution-events", session],
    queryFn: async () =>
      executionEvents(await api.terminalEvents("EXECUTION", 200), session),
    enabled: !historical,
    refetchInterval: historical ? false : 5000,
  });
  return (
    <Panel
      className="executionTimeline"
      title="Execution & reconciliation timeline"
      meta="Read-only · latest 200 authoritative session events"
    >
      {historical ? (
        <Empty>
          Historical snapshot: current-session event polling paused.
        </Empty>
      ) : q.isPending ? (
        <Empty>Loading execution events…</Empty>
      ) : q.isError ? (
        <p role="alert">Execution events unavailable: {String(q.error)}</p>
      ) : (
        <EventTimeline events={q.data} />
      )}
      <p className="muted panelNote">
        Backend status transitions and reconciliation events only. SIMULATED
        marks PAPER/DEMO evidence; venue fills are not inferred from
        transitions.
      </p>
    </Panel>
  );
}
