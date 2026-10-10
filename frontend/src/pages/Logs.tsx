import { useState } from "react";
import type { EventCategory, TerminalState } from "../types";
import {
  Panel,
  Empty,
  Metrics,
  StatusBanner,
} from "../components/TerminalPrimitives";
import { Badge } from "../components/Badge";
import { EventTimeline } from "../components/EventTimeline";
import { useTerminalEvents } from "../hooks/useTerminalEvents";
import {
  eventCategories,
  eventExport,
  eventView,
  type EventOrder,
} from "../utils/terminalEventView";
import { evidenceTime } from "../utils/researchEvidence";
import "../phase1333.css";
import { useTerminalStore } from "../stores/terminal";

export function Logs({
  t,
  historical = false,
}: {
  t: TerminalState;
  historical?: boolean;
}) {
  const [category, setCategory] = useState<EventCategory | undefined>();
  const [limit, setLimit] = useState(200);
  const [search, setSearch] = useState("");
  const [order, setOrder] = useState<EventOrder>("newest-first");
  const [exportError, setExportError] = useState<string | null>(null);
  const q = useTerminalEvents(t, historical, category, limit);
  const loaded = q.data?.events ?? [];
  const selected = eventView(loaded, search, order);
  const latest = loaded.reduce<string | null>(
    (value, e) =>
      !value || Date.parse(e.timestamp) > Date.parse(value)
        ? e.timestamp
        : value,
    null,
  );
  function exportLoaded() {
    if (!q.data || q.isError) return;
    try {
      const accepted = useTerminalStore.getState().terminal;
      if (
        accepted?.process_id !== t.process_id ||
        accepted.session_id !== t.session_id
      )
        throw new Error("Event identity changed.");
      if (!q.historical) q.checkCurrent();
      const payload = eventExport(q.data, selected, {
        processId: t.process_id,
        sessionId: t.session_id,
        category,
        limit,
        historical: q.historical,
        order,
      });
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(payload, null, 2)], {
          type: "application/json",
        }),
      );
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = "hyperamm-loaded-events.json";
        document.body.append(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
      setExportError(null);
    } catch {
      setExportError(
        "Export unavailable. Reload matching session evidence and retry.",
      );
    }
  }
  return (
    <div className="operationsWorkspace logsPage stack">
      <div className="researchPageTitle">
        <div>
          <h1>Operational logs & diagnostics</h1>
          <p className="muted">
            Search and inspect bounded, read-only session evidence
          </p>
        </div>
        <Badge tone={q.historical ? "warn" : "blue"}>
          {q.historical ? "HISTORICAL SESSION" : "CURRENT SESSION"}
        </Badge>
      </div>
      {q.historical && (
        <StatusBanner>
          Historical event evidence · last-known records are not live activity
          or current trading authority. Current-session polling is paused.
        </StatusBanner>
      )}
      <Panel
        title="Event evidence summary"
        meta="In-memory retention · maximum 500"
      >
        <Metrics
          items={[
            ["Session evidence", q.historical ? "HISTORICAL" : "CURRENT"],
            ["Events returned", q.data ? loaded.length : "Unavailable"],
            ["Requested category / limit", `${category ?? "ALL"} / ${limit}`],
            [
              "Simulated loaded events",
              q.data ? loaded.filter((e) => e.simulated).length : "Unavailable",
            ],
            ["Search matches", q.data ? selected.length : "Unavailable"],
            ["Latest loaded timestamp", evidenceTime(latest)],
          ]}
        />
        <details className="researchInset">
          <summary>Inspect event session identity and scope</summary>
          <dl className="operationsDetails">
            <dt>Client-observed process</dt>
            <dd>
              <code>{t.process_id}</code>
            </dd>
            <dt>Returned session</dt>
            <dd>
              <code>{q.data?.session_id ?? "Unavailable"}</code>
            </dd>
            <dt>Backend ordering</dt>
            <dd>{q.data?.order ?? "Unavailable"}</dd>
          </dl>
          <p className="muted">
            The REST response declares a session, but no authenticated process
            identity. Client checks protect attribution. These records are
            bounded observations, not a complete audit archive.
          </p>
        </details>
      </Panel>
      <Panel title="Structured events" meta="Read-only · no event mutations">
        <div
          className="eventCategories"
          role="group"
          aria-label="Event category"
        >
          {[undefined, ...eventCategories].map((c) => (
            <button
              key={c ?? "ALL"}
              aria-pressed={category === c}
              onClick={() => setCategory(c)}
            >
              {c ?? "ALL"}
            </button>
          ))}
        </div>
        <div className="formGrid operationsFilters">
          <label>
            Search loaded events
            <input
              aria-label="Search loaded events"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Message, reference, state or event ID"
            />
          </label>
          <label>
            Requested event limit
            <select
              aria-label="Requested event limit"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              {[100, 200, 500].map((n) => (
                <option key={n} value={n}>
                  {n} events
                </option>
              ))}
            </select>
          </label>
          <label>
            Display order
            <select
              aria-label="Display order"
              value={order}
              onChange={(e) => setOrder(e.target.value as EventOrder)}
            >
              <option value="newest-first">Newest first</option>
              <option value="oldest-first">Oldest first</option>
            </select>
          </label>
        </div>
        <div className="operationsActions">
          <button disabled={!search} onClick={() => setSearch("")}>
            Clear search
          </button>
          <button
            onClick={() => {
              setCategory(undefined);
              setSearch("");
              setOrder("newest-first");
            }}
          >
            Reset filters
          </button>
          <button
            disabled={!q.data || q.isError || !selected.length}
            onClick={exportLoaded}
          >
            Export loaded events (bounded session evidence)
          </button>
        </div>
        <p className="muted panelNote">
          Search applies only to returned records. Loaded counts for a selected
          category do not count other categories. Export preserves selected
          records; review messages and references before sharing sensitive
          operational information.
        </p>
        {exportError && (
          <p role="alert" className="inlineError">
            {exportError}
          </p>
        )}
        {q.isError ? (
          <div role="alert" className="inlineError">
            Events unavailable: {String(q.error)}
            {!q.historical && (
              <button onClick={() => void q.refetch()}>Retry events</button>
            )}
          </div>
        ) : !q.data ? (
          <Empty>
            {q.historical
              ? "No locally retained events for this session, category and limit."
              : "Loading events…"}
          </Empty>
        ) : (
          <>
            <p role="status" className="eventMatchCount">
              {selected.length} matching events out of {loaded.length} loaded
              events. Showing filtered results from the latest {limit} requested
              events (up to {q.data.max_events} retained; total store count
              unavailable).
            </p>
            <EventTimeline
              events={selected}
              emptyMessage={
                loaded.length
                  ? "No loaded events match this search. Clear search or reset filters."
                  : "No events returned for this session and category."
              }
            />
          </>
        )}
        <p className="muted panelNote">
          A subsystem state change does not establish an executed order.
          SIMULATED is the event flag; it does not prove a signed TESTNET fill
          or complete venue history.
        </p>
      </Panel>
    </div>
  );
}
