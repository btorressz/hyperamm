import type { Order, TerminalEvents, TerminalState } from "../types";
export const orderStatuses = [
  "OPEN",
  "PARTIALLY_FILLED",
  "FILLED",
  "UNKNOWN",
  "CANCELLED",
  "REPLACED",
  "REJECTED",
] as const;
export type OrderSort = "updated_at" | "price" | "size" | "status";
export function orderStatus(o: Order): string {
  return (orderStatuses as readonly string[]).includes(o.status)
    ? o.status
    : "UNKNOWN";
}
// Order payloads do not carry execution mode. Only explicit per-order evidence is classified.
export function orderMode(o: Order): string {
  if (o.fill_source?.includes("PAPER")) return "PAPER";
  if (o.venue_order_id != null && o.venue_order_id !== "") return "TESTNET";
  return "UNKNOWN";
}
export function exactDecimal(value: unknown): string {
  const raw =
    typeof value === "string" || typeof value === "number" ? String(value) : "";
  if (/^[+-]?\d+(?:\.\d+)?$/.test(raw)) return raw;
  const match = /^([+-]?)(\d+)(?:\.(\d+))?[eE]([+-]?\d+)$/.exec(raw);
  if (!match || Math.abs(Number(match[4])) > 1000) return "—";
  const digits = match[2] + (match[3] ?? "");
  const point = match[2].length + Number(match[4]);
  return (
    match[1] +
    (point <= 0
      ? "0." + "0".repeat(-point) + digits
      : point >= digits.length
        ? digits + "0".repeat(point - digits.length)
        : digits.slice(0, point) + "." + digits.slice(point))
  );
}
function compareDecimal(a: unknown, b: unknown): number {
  const x = exactDecimal(a),
    y = exactDecimal(b);
  if (x === "—" || y === "—") return x === y ? 0 : x === "—" ? 1 : -1;
  const width = Math.max(
    x.split(".")[1]?.length ?? 0,
    y.split(".")[1]?.length ?? 0,
  );
  const scaled = (v: string) => {
    const [i, f = ""] = v.split(".");
    return BigInt(i + f.padEnd(width, "0"));
  };
  const left = scaled(x),
    right = scaled(y);
  return left < right ? -1 : left > right ? 1 : 0;
}
export function selectOrders(
  orders: readonly Order[],
  filters: { status: string; side: string; mode: string },
  sort: OrderSort,
  descending: boolean,
): Order[] {
  return orders
    .map((order, index) => ({ order, index }))
    .filter(
      ({ order }) =>
        (filters.status === "ALL" || orderStatus(order) === filters.status) &&
        (filters.side === "ALL" || order.side === filters.side) &&
        (filters.mode === "ALL" || orderMode(order) === filters.mode),
    )
    .sort((a, b) => {
      const x = a.order[sort],
        y = b.order[sort];
      // Missing values remain last in both directions.
      const missing = (v: unknown) =>
        sort === "updated_at"
          ? !Number.isFinite(Date.parse(String(v)))
          : sort === "status"
            ? !v
            : exactDecimal(v) === "—";
      if (missing(x) !== missing(y)) return missing(x) ? 1 : -1;
      const cmp =
        sort === "price" || sort === "size"
          ? compareDecimal(x, y)
          : sort === "updated_at"
            ? Date.parse(String(x)) - Date.parse(String(y)) || 0
            : orderStatus(a.order).localeCompare(orderStatus(b.order));
      return (descending ? -cmp : cmp) || a.index - b.index;
    })
    .map(({ order }) => order);
}
export function orderActions(t: TerminalState, o: Order) {
  return t.reconciliation.filter(
    (a) => a.existing?.client_order_id === o.client_order_id,
  );
}
export function executionEvents(data: TerminalEvents, session: string) {
  if (data.session_id !== session)
    throw new Error("Execution events session changed during request");
  return data.events.filter((e) => e.category === "EXECUTION").slice(0, 200);
}
