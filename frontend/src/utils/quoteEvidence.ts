import type { Order, Quote } from "../types";

export type QuoteStage = "STRATEGY" | "AGENT" | "AUTHORIZED";

export type QuoteEvidence = {
  label: string;
  kind: "proposal" | "authorized" | "active" | "uncertain" | "historical";
  orderId: string | null;
};

const statuses = new Set([
  "OPEN",
  "PARTIALLY_FILLED",
  "UNKNOWN",
  "FILLED",
  "CANCELLED",
  "REPLACED",
  "REJECTED",
]);

/** Compare positive decimal wire values without floating-point rounding. */
function decimalKey(value: string | number): string {
  const raw = String(value).trim();
  const match = /^([+]?)(\d+)(?:\.(\d*))?$/.exec(raw);
  if (!match) return raw;
  const integer = match[2].replace(/^0+(?=\d)/, "");
  const fractional = (match[3] ?? "").replace(/0+$/, "");
  return fractional ? integer + "." + fractional : integer;
}

export function quoteEvidence(
  quote: Quote,
  orders: readonly Order[],
  stage: QuoteStage,
  historical = false,
): QuoteEvidence {
  if (stage !== "AUTHORIZED")
    return {
      label: stage === "STRATEGY" ? "STRATEGY PROPOSAL" : "AGENT PROPOSAL",
      kind: "proposal",
      orderId: null,
    };

  const slot = orders.filter(
    (order) =>
      order.side === quote.side && order.level_index === quote.level_index,
  );
  const sorted = [...slot].sort((a, b) => {
    const time = Date.parse(b.updated_at) - Date.parse(a.updated_at);
    return (
      (Number.isNaN(time) ? 0 : time) ||
      b.client_order_id.localeCompare(a.client_order_id)
    );
  });
  const exact = sorted.find(
    (order) =>
      decimalKey(order.price) === decimalKey(quote.price) &&
      decimalKey(order.size) === decimalKey(quote.size),
  );
  if (!exact) {
    return {
      label: sorted.length
        ? "AUTHORIZED · NO MATCHED ORDER (HISTORY EXISTS)"
        : "AUTHORIZED · NO MATCHED ORDER",
      kind: "authorized",
      orderId: null,
    };
  }
  // A newer slot record or ambiguous duplicate cannot renew an older exact match.
  const superseded =
    !Number.isFinite(Date.parse(exact.updated_at)) ||
    sorted[0] !== exact ||
    slot.some(
      (o) =>
        o !== exact &&
        ["OPEN", "PARTIALLY_FILLED", "UNKNOWN"].includes(o.status),
    );
  const status = statuses.has(exact.status) ? exact.status : "UNRECOGNIZED";
  const closed = ["FILLED", "CANCELLED", "REPLACED", "REJECTED"].includes(
    status,
  );
  const kind =
    historical || closed
      ? "historical"
      : superseded || status === "UNKNOWN" || status === "UNRECOGNIZED"
        ? "uncertain"
        : "active";
  const label =
    kind === "active"
      ? status + " · RETAINED EVIDENCE"
      : kind === "uncertain"
        ? status + " · VERIFY"
        : status + " · HISTORICAL";
  return { label, kind, orderId: exact.client_order_id };
}
