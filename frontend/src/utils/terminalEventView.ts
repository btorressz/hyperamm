import type {
  EventCategory,
  TerminalEvent,
  TerminalEvents,
  TerminalState,
} from "../types";
import { sessionCurrent, type EvidenceState } from "./researchEvidence";
import { compareEmissionTimes } from "./terminalIntegrity";

export const eventCategories: EventCategory[] = [
  "MARKET",
  "REFERENCES",
  "STRATEGY",
  "AGENTS",
  "RISK",
  "EXECUTION",
  "ACCOUNTING",
  "SYSTEM",
];
export type EventOrder = "newest-first" | "oldest-first";
export function checkedEventLimit(limit: number) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 500)
    throw new Error("Event limit must be a whole number from 1 to 500.");
  return limit;
}
// Validate the REST session and client attribution before exposing any records.
// REST declares no process ID; these checks are not authenticated server identity.
export function checkedTerminalEvents(
  data: unknown,
  expected: TerminalState,
  current: EvidenceState,
  category?: EventCategory,
  limit = 200,
): TerminalEvents {
  checkedEventLimit(limit);
  if (!sessionCurrent(expected, current))
    throw new Error(
      "Event request belongs to a retired or disconnected observation.",
    );
  const d = data as TerminalEvents | null;
  const nullableString = (x: unknown) => x === null || typeof x === "string";
  const ids = new Set<string>();
  if (
    !d ||
    d.session_id !== expected.session_id ||
    d.order !== "newest-first" ||
    d.max_events !== 500 ||
    !Array.isArray(d.events) ||
    d.events.length > limit ||
    d.events.some((e) => {
      if (
        !e ||
        typeof e.event_id !== "string" ||
        !e.event_id ||
        ids.has(e.event_id)
      )
        return true;
      ids.add(e.event_id);
      return (
        !eventCategories.includes(e.category) ||
        (category !== undefined && e.category !== category) ||
        typeof e.timestamp !== "string" ||
        !Number.isFinite(Date.parse(e.timestamp)) ||
        typeof e.message !== "string" ||
        !nullableString(e.previous_state) ||
        !nullableString(e.state) ||
        !nullableString(e.reference) ||
        !(
          e.version === null ||
          (Number.isSafeInteger(e.version) && e.version >= 0)
        ) ||
        typeof e.simulated !== "boolean"
      );
    })
  )
    throw new Error(
      "Events response is incompatible with the requested session or event contract.",
    );
  return d;
}
export function eventView(
  events: TerminalEvent[],
  search: string,
  order: EventOrder,
): TerminalEvent[] {
  const term = search.trim().toLowerCase();
  const selected = events
    .map((event, position) => ({ event, position }))
    .filter(
      ({ event: e }) =>
        !term ||
        [
          e.message,
          e.category,
          e.previous_state,
          e.state,
          e.reference,
          e.event_id,
          e.version,
        ].some(
          (value) =>
            value !== null && String(value).toLowerCase().includes(term),
        ),
    );
  if (order === "oldest-first")
    selected.sort(
      (a, b) =>
        compareEmissionTimes(a.event.timestamp, b.event.timestamp) ||
        a.position - b.position,
    );
  return selected.map((x) => x.event);
}
export function eventTransition(e: TerminalEvent) {
  if (e.previous_state !== null && e.state !== null)
    return `${e.previous_state} → ${e.state}`;
  if (e.state !== null) return `Observed state: ${e.state}`;
  if (e.previous_state !== null)
    return `Previous state: ${e.previous_state} · new state not reported`;
  return "No state transition reported";
}
export function eventExport(
  data: TerminalEvents,
  selected: TerminalEvent[],
  identity: {
    processId: string;
    sessionId: string;
    category?: EventCategory;
    limit: number;
    historical: boolean;
    order: EventOrder;
  },
  generatedAt = new Date().toISOString(),
) {
  checkedEventLimit(identity.limit);
  if (
    data.session_id !== identity.sessionId ||
    selected.some((e) => !data.events.includes(e))
  )
    throw new Error("Export does not belong to the loaded session evidence.");
  return {
    generated_at: generatedAt,
    client_observed_identity: {
      process_id: identity.processId,
      session_id: identity.sessionId,
    },
    provenance:
      "Client-observed attribution; not server-authenticated process identity or a complete audit archive.",
    requested_category: identity.category ?? "ALL",
    requested_limit: identity.limit,
    max_retained_events: data.max_events,
    loaded_event_count: data.events.length,
    exported_event_count: selected.length,
    backend_order: data.order,
    display_order: identity.order,
    display_state: identity.historical ? "HISTORICAL" : "CURRENT",
    // Only declared event fields. No store, storage, extra response diagnostics or search text.
    events: selected.map((e) => ({
      event_id: e.event_id,
      timestamp: e.timestamp,
      category: e.category,
      previous_state: e.previous_state,
      state: e.state,
      message: e.message,
      reference: e.reference,
      version: e.version,
      simulated: e.simulated,
    })),
  };
}
