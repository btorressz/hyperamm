const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { quoteEvidence } = require(path.join(process.env.TERMINAL_TEST_BUILD, "utils/quoteEvidence.js"));

const quote = { side: "BID", level_index: 2, price: "3000.00", size: "0.2500" };
const order = (status, overrides = {}) => ({
  side: "BID", level_index: 2, price: "3000", size: "0.25", status,
  client_order_id: status, updated_at: "2026-10-09T12:00:00Z", ...overrides,
});

test("proposal stages never claim a resting order", () => {
  for (const stage of ["STRATEGY", "AGENT"]) {
    const result = quoteEvidence(quote, [order("OPEN")], stage);
    assert.equal(result.kind, "proposal");
    assert.equal(result.orderId, null);
  }
});
test("authorized quote with no exact matched order is not resting", () => {
  assert.equal(quoteEvidence(quote, [], "AUTHORIZED").kind, "authorized");
  assert.equal(quoteEvidence(quote, [order("OPEN", { price: "2999" })], "AUTHORIZED").kind, "authorized");
  assert.equal(quoteEvidence(quote, [order("OPEN", { size: "0.2" })], "AUTHORIZED").kind, "authorized");
  assert.equal(quoteEvidence(quote, [order("OPEN", { level_index: 3 })], "AUTHORIZED").kind, "authorized");
});
for (const [status, kind] of [
  ["OPEN", "active"], ["PARTIALLY_FILLED", "active"], ["UNKNOWN", "uncertain"],
  ["FILLED", "historical"], ["CANCELLED", "historical"], ["REPLACED", "historical"],
  ["REJECTED", "historical"], ["OTHER", "uncertain"],
]) test(status + " is never mislabeled as resting/filled", () => {
  const result = quoteEvidence(quote, [order(status)], "AUTHORIZED");
  assert.equal(result.kind, kind);
  assert.equal(result.orderId, status);
  assert.ok(result.label.includes(status === "OTHER" ? "UNRECOGNIZED" : status));
  assert.doesNotMatch(result.label, /RESTING|PAPER_FILLED/);
});
test("current evidence only matches exact executable price and size", () => {
  const r = quoteEvidence(quote, [order("CANCELLED", { updated_at: "2026-10-09T13:00:00Z" }), order("OPEN", { updated_at: "2026-10-09T14:00:00Z" })], "AUTHORIZED");
  assert.equal(r.kind, "active");
  assert.equal(r.orderId, "OPEN");
});
