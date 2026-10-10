import type { TerminalState } from "../types";
import { Panel, Metrics, Empty } from "../components/TerminalPrimitives";
import { OrderTable } from "../components/RecentExecution";
import { exactDecimal } from "../utils/orderView";
import { timestamp, percentage, bps } from "../utils/format";
import { ExecutionTimeline } from "../components/ExecutionTimeline";
export function Execution({
  t,
  historical = false,
}: {
  t: TerminalState;
  historical?: boolean;
}) {
  const paper = t.strategy.config.execution_mode === "PAPER",
    quality = t.agents.execution_quality?.metrics;
  return (
    <div className="stack">
      <h1>Execution</h1>
      {t.execution_summary.active_orders_truncated && (
        <p className="alert">
          Active order view capped at {t.execution_summary.active_order_limit}{" "}
          records. Summary counts include all runtime evidence.
        </p>
      )}
      <Panel
        title="Execution quality"
        meta={paper ? "PAPER / SIMULATED" : "GUARDED TESTNET"}
      >
        <Metrics
          items={[
            ["Unknown orders", t.execution_summary.status_counts.UNKNOWN],
            ["Rejected orders", t.execution_summary.status_counts.REJECTED],
            ["Order lifecycle count", t.execution_summary.order_count],
            ["Churn", percentage(quality?.reconciliation_churn_ratio)],
            ["Spread capture", bps(quality?.average_spread_capture_bps)],
            ["Mature markout", bps(quality?.average_mature_markout_bps)],
            [
              "Venue reconciled",
              timestamp(t.venue_reconciliation.last_reconciled_at),
            ],
            [
              "Venue error",
              t.venue_reconciliation.error ??
                (paper ? "Not applicable" : "No reported error"),
            ],
          ]}
        />
      </Panel>
      <Panel
        title="Active & uncertain order evidence"
        meta={
          historical
            ? "HISTORICAL SESSION"
            : "Retained venue / PAPER statuses; not resting confirmation"
        }
      >
        <OrderTable
          t={t}
          historical={historical}
          orders={t.orders.filter((o) =>
            ["OPEN", "PARTIALLY_FILLED", "UNKNOWN"].includes(o.status),
          )}
        />
      </Panel>
      <Panel
        title="Recent order history"
        meta={`Latest ${t.execution_summary.recent_limit} closed records + active`}
      >
        <OrderTable
          t={t}
          historical={historical}
          orders={t.orders}
        />
      </Panel>
      <Panel
        title={paper ? "PAPER fills" : "TESTNET fills"}
        meta={paper ? "SIMULATED · recent retained evidence" : "PARTIAL"}
      >
        {paper ? (
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Side</th>
                  <th>Price</th>
                  <th>Size</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {t.fills.length ? (
                  [...t.fills].reverse().map((f, i) => (
                    <tr key={`${f.client_order_id}-${i}`}>
                      <td>{timestamp(f.timestamp)}</td>
                      <td>{f.side}</td>
                      <td>{exactDecimal(f.price)}</td>
                      <td>{exactDecimal(f.size)}</td>
                      <td>{f.source}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="emptyCell">
                      No simulated fill evidence yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>TESTNET fill history unavailable</Empty>
        )}
      </Panel>
      <ExecutionTimeline
        key={t.session_id}
        session={t.session_id}
        historical={historical}
      />
      <Panel title="Reconciliation actions" meta="Latest strategy cycle">
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Action</th>
                <th>Side / level</th>
                <th>Desired price / size</th>
                <th>Existing status</th>
              </tr>
            </thead>
            <tbody>
              {t.reconciliation.length ? (
                t.reconciliation.map((a, i) => (
                  <tr key={i}>
                    <td>{a.action}</td>
                    <td>
                      {a.desired?.side ?? a.existing?.side} /{" "}
                      {a.desired?.level_index ?? a.existing?.level_index ?? "—"}
                    </td>
                    <td>
                      {exactDecimal(a.desired?.price)} / {exactDecimal(a.desired?.size)}
                    </td>
                    <td>{a.existing?.status ?? "—"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="emptyCell">
                    No reconciliation evidence yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
