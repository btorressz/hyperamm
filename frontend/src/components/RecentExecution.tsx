import { useState } from "react";
import type { TerminalState, Order } from "../types";
import { Panel } from "./TerminalPrimitives";
import { timestamp } from "../utils/format";
import {
  exactDecimal,
  orderActions,
  orderMode,
  orderStatus,
  orderStatuses,
  selectOrders,
  type OrderSort,
} from "../utils/orderView";
export function OrderDetails({
  o,
  t,
  historical = false,
}: {
  o: Order;
  t: TerminalState;
  historical?: boolean;
}) {
  const actions = orderActions(t, o);
  return (
    <details>
      <summary>Order details</summary>
      <dl className="orderDetails">
        {Object.entries({
          "Client order ID": o.client_order_id || "—",
          "Venue order ID": o.venue_order_id ?? "—",
          Status: orderStatus(o),
          "Reported status": o.status || "Unavailable",
          "Filled quantity": exactDecimal(o.filled_size),
          Source: o.fill_source ?? "Unavailable",
          "Mode evidence": orderMode(o),
          Created: o.created_at || "—",
          Updated: o.updated_at || "—",
          Session: t.session_id,
          Reconciliation:
            actions.map((a) => a.action).join(", ") ||
            "No matching action in latest cycle",
          "Venue reconciled":
            t.venue_reconciliation.last_reconciled_at ?? "Unavailable",
          "Venue error": t.venue_reconciliation.error ?? "No reported error",
        }).map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <p>
        {historical
          ? "Historical session evidence."
          : "Retained status evidence."}{" "}
        Latest-cycle actions and venue reconciliation time do not confirm this
        order is currently resting.
      </p>
    </details>
  );
}
export function OrderTable({
  orders,
  t,
  historical = false,
  controls = true,
}: {
  orders: Order[];
  t: TerminalState;
  historical?: boolean;
  controls?: boolean;
}) {
  const [filters, setFilters] = useState({
    status: "ALL",
    side: "ALL",
    mode: "ALL",
  });
  const [sort, setSort] = useState<OrderSort>("updated_at");
  const [descending, setDescending] = useState(true);
  const visible = selectOrders(orders, filters, sort, descending);
  return (
    <>
      {controls && (
        <div className="chartToolbar orderFilters">
          {(["status", "side", "mode"] as const).map((key) => (
            <label key={key}>
              {key === "mode"
                ? "Mode evidence"
                : key === "side"
                  ? "Side"
                  : "Status"}{" "}
              <select
                aria-label={
                  key === "mode"
                    ? "Mode evidence"
                    : key === "side"
                      ? "Side"
                      : "Status"
                }
                value={filters[key]}
                onChange={(e) =>
                  setFilters({ ...filters, [key]: e.target.value })
                }
              >
                {[
                  "ALL",
                  ...(key === "status"
                    ? orderStatuses
                    : key === "side"
                      ? ["BID", "ASK"]
                      : ["PAPER", "TESTNET", "UNKNOWN"]),
                ].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
          ))}
          <label>
            Sort{" "}
            <select
              aria-label="Sort"
              value={sort}
              onChange={(e) => setSort(e.target.value as OrderSort)}
            >
              {(["updated_at", "price", "size", "status"] as const).map((v) => (
                <option key={v} value={v}>
                  {v === "updated_at" ? "Timestamp" : v}
                </option>
              ))}
            </select>
          </label>
          <button onClick={() => setDescending(!descending)}>
            {descending ? "Descending" : "Ascending"}
          </button>
          <span>
            {visible.length} / {orders.length} retained records
          </span>
        </div>
      )}
      <p className="muted panelNote">
        {historical ? "HISTORICAL SESSION · " : ""}Retained evidence; UNKNOWN
        requires verification. PAPER fills are simulated. Mode is unavailable
        unless the order carries explicit evidence.
      </p>
      <div
        className="tableWrap orderTable"
        tabIndex={0}
        aria-label="Order lifecycle records"
      >
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Side</th>
              <th className="numeric">Price</th>
              <th className="numeric">Size</th>
              <th className="numeric">Filled</th>
              <th>Source / status</th>
              <th>Reconciliation / details</th>
            </tr>
          </thead>
          <tbody>
            {visible.length ? (
              visible.map((o, i) => (
                <tr key={o.client_order_id || `missing-${i}`}>
                  <td>{timestamp(o.updated_at)}</td>
                  <td className={o.side === "BID" ? "bidText" : "askText"}>
                    {o.side || "—"}
                  </td>
                  <td className="numeric">{exactDecimal(o.price)}</td>
                  <td className="numeric">{exactDecimal(o.size)}</td>
                  <td className="numeric">{exactDecimal(o.filled_size)}</td>
                  <td>
                    {o.fill_source ?? "Source unavailable"} ·{" "}
                    <strong>{orderStatus(o)}</strong>
                    {historical
                      ? " · HISTORICAL"
                      : orderStatus(o) === "UNKNOWN"
                        ? " · VERIFY"
                        : [
                              "FILLED",
                              "CANCELLED",
                              "REPLACED",
                              "REJECTED",
                            ].includes(orderStatus(o))
                          ? " · HISTORICAL"
                          : " · RETAINED"}
                    <br />
                    {orderMode(o) === "PAPER"
                      ? "PAPER / SIMULATED"
                      : orderMode(o) === "TESTNET"
                        ? "GUARDED TESTNET / VENUE ID"
                        : "Mode unavailable"}
                  </td>
                  <td>
                    {orderActions(t, o)
                      .map((a) => a.action)
                      .join(", ") || "No current action"}
                    <OrderDetails o={o} t={t} historical={historical} />
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7} className="emptyCell">
                  {orders.length
                    ? "No orders match these filters."
                    : "No order evidence yet."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
export function RecentExecution({
  t,
  historical = false,
}: {
  t: TerminalState;
  historical?: boolean;
}) {
  return (
    <Panel
      title="Recent execution"
      meta={`${t.strategy.config.execution_mode} · bounded lifecycle records`}
    >
      <OrderTable
        key={t.session_id}
        t={t}
        historical={historical}
        controls={false}
        orders={selectOrders(
          t.orders,
          { status: "ALL", side: "ALL", mode: "ALL" },
          "updated_at",
          true,
        ).slice(0, 6)}
      />
    </Panel>
  );
}
