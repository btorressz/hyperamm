import type { TerminalEvent } from "../types";
import { timestamp } from "../utils/format";
export function EventTimeline({ events }: { events: TerminalEvent[] }) {
  return (
    <div className="tableWrap eventTable">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Category</th>
            <th>Transition</th>
            <th>Message</th>
            <th>Reference / version</th>
          </tr>
        </thead>
        <tbody>
          {events.length ? (
            events.map((e) => (
              <tr key={e.event_id}>
                <td>
                  {timestamp(e.timestamp)}
                  {e.simulated && <small> SIMULATED</small>}
                </td>
                <td>{e.category}</td>
                <td>
                  {e.previous_state ?? "—"} → {e.state ?? "—"}
                </td>
                <td>{e.message}</td>
                <td>
                  {e.reference ?? "—"}{" "}
                  {e.version !== null ? `v${e.version}` : ""}
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={5} className="emptyCell">
                No matching events in the retained session.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
