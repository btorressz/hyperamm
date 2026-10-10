import { Fragment, useId, useState } from "react";
import type { TerminalEvent } from "../types";
import { evidenceTime } from "../utils/researchEvidence";
import { eventTransition } from "../utils/terminalEventView";
import { Badge } from "./Badge";

export function EventDetails({ event: e }: { event: TerminalEvent }) {
  const nullable = (value: unknown) =>
    value === null
      ? "Null (not reported)"
      : value === undefined
        ? "Unavailable"
        : String(value);
  return (
    <dl className="operationsDetails">
      {(
        [
          ["Event ID", e.event_id],
          ["Full timestamp", e.timestamp],
          ["Category", e.category],
          ["Previous state", e.previous_state],
          ["New state", e.state],
          ["Full message", e.message],
          ["Reference", e.reference],
          ["Version", e.version],
          ["Simulated flag", String(e.simulated)],
        ] as Array<[string, unknown]>
      ).map(([label, value]) => (
        <Fragment key={label}>
          <dt>{label}</dt>
          <dd>{nullable(value)}</dd>
        </Fragment>
      ))}
    </dl>
  );
}
function EventRow({ event: e }: { event: TerminalEvent }) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  return (
    <>
      <tr>
        <td>
          <time dateTime={e.timestamp}>
            {new Date(e.timestamp).toLocaleString()}
          </time>
          {e.simulated && (
            <div>
              <Badge tone="blue">SIMULATED</Badge>
            </div>
          )}
        </td>
        <td>
          <Badge>{e.category}</Badge>
        </td>
        <td>{eventTransition(e)}</td>
        <td>
          <span className="eventMessagePreview">
            {e.message.length > 160 ? e.message.slice(0, 160) + "…" : e.message}
          </span>
          <button
            className="eventDetailsToggle"
            aria-expanded={expanded}
            aria-controls={detailsId}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "Hide" : "Inspect"} event {e.event_id}
          </button>
        </td>
        <td>
          <span className="eventReference">{e.reference ?? "Null"}</span>
          {e.version !== null && <small>v{e.version}</small>}
        </td>
      </tr>
      {expanded && (
        <tr id={detailsId}>
          <td colSpan={5}>
            <EventDetails event={e} />
            <p className="muted">
              {evidenceTime(e.timestamp)} · Reported observation; execution
              requires separate order/fill evidence.
            </p>
          </td>
        </tr>
      )}
    </>
  );
}
export function EventTimeline({
  events,
  emptyMessage = "No matching events in the retained session.",
}: {
  events: TerminalEvent[];
  emptyMessage?: string;
}) {
  return (
    <div
      className="tableWrap eventTable"
      tabIndex={0}
      role="region"
      aria-label="Loaded event timeline"
    >
      <table>
        <thead>
          <tr>
            <th scope="col">Time / evidence</th>
            <th scope="col">Category</th>
            <th scope="col">Transition</th>
            <th scope="col">Message / details</th>
            <th scope="col">Reference / version</th>
          </tr>
        </thead>
        <tbody>
          {events.length ? (
            events.map((e) => <EventRow key={e.event_id} event={e} />)
          ) : (
            <tr>
              <td colSpan={5} className="emptyCell">
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
