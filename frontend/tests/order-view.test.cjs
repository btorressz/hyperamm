const { test } = require("node:test"),
  assert = require("node:assert/strict"),
  path = require("node:path"),
  React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const read = (p) => require(path.join(process.env.TERMINAL_TEST_BUILD, p));
const {
  orderStatuses,
  orderStatus,
  orderMode,
  exactDecimal,
  selectOrders,
  executionEvents,
} = read("utils/orderView.js");
const { OrderTable, OrderDetails } = read("components/RecentExecution.js");
const { quoteEvidence } = read("utils/quoteEvidence.js");
const valid = require("./fixtures/terminal-valid.json");
const o = (status = "OPEN", overrides = {}) => ({
  client_order_id: "one",
  venue_order_id: null,
  market: "ETH",
  side: "BID",
  level_index: 0,
  price: "3000.00000001",
  size: "0.123456789",
  filled_size: "0",
  created_at: "2026-10-09T00:00:00Z",
  updated_at: "2026-10-09T01:00:00Z",
  status,
  ...overrides,
});
const all = { status: "ALL", side: "ALL", mode: "ALL" };
const render = (C, props) =>
  renderToStaticMarkup(React.createElement(C, props));
for (const status of orderStatuses)
  test("table and expanded details preserve " + status, () => {
    const order = o(status, {
        filled_size: status === "PARTIALLY_FILLED" ? "0.02" : "0",
      }),
      html = render(OrderTable, { orders: [order], t: valid });
    assert.match(html, new RegExp("<strong>" + status));
    assert.match(html, /<details>/);
    assert.match(html, /0.123456789/);
    const detail = render(OrderDetails, { o: order, t: valid });
    for (const text of [
      "Client order ID",
      "Venue order ID",
      "Filled quantity",
      "2026-10-09T00:00:00Z",
    ])
      assert.ok(detail.includes(text));
  });
test("empty table never fabricates orders", () =>
  assert.match(
    render(OrderTable, { orders: [], t: valid }),
    /No order evidence yet/,
  ));
test("unknown/missing status/source/financial/time evidence is explicit", () => {
  const order = o("", {
    price: null,
    size: undefined,
    updated_at: "invalid",
    fill_source: null,
  });
  assert.equal(orderStatus(order), "UNKNOWN");
  const html = render(OrderTable, { orders: [order], t: valid });
  for (const text of ["VERIFY", "Source unavailable", "Mode unavailable", "—"])
    assert.ok(html.includes(text));
});
test("historical session OPEN and partial are labeled historical", () => {
  const html = render(OrderTable, {
    orders: [o(), o("PARTIALLY_FILLED", { client_order_id: "two" })],
    t: valid,
    historical: true,
  });
  assert.match(html, /HISTORICAL SESSION/);
  assert.match(html, /Historical session evidence/);
});
for (const status of orderStatuses)
  test("status filter selects " + status, () => {
    const orders = orderStatuses.map((s) => o(s, { client_order_id: s }));
    assert.deepEqual(
      selectOrders(orders, { ...all, status }, "status", false).map(
        (x) => x.status,
      ),
      [status],
    );
  });
test("side, mode and combined filters including no matches", () => {
  const orders = [
    o("FILLED", { fill_source: "SIMULATED PAPER FILL" }),
    o("OPEN", { side: "ASK", venue_order_id: "42" }),
  ];
  assert.equal(
    selectOrders(orders, { ...all, side: "ASK" }, "price", false)[0],
    orders[1],
  );
  assert.equal(
    selectOrders(
      orders,
      { status: "FILLED", side: "BID", mode: "PAPER" },
      "price",
      false,
    )[0],
    orders[0],
  );
  assert.equal(
    selectOrders(orders, { ...all, mode: "UNKNOWN" }, "price", false).length,
    0,
  );
});
test("mode needs explicit per-order evidence", () => {
  assert.equal(orderMode(o()), "UNKNOWN");
  assert.equal(
    orderMode(o("FILLED", { fill_source: "SIMULATED PAPER FILL" })),
    "PAPER",
  );
  assert.equal(orderMode(o("OPEN", { venue_order_id: "1" })), "TESTNET");
});
for (const sort of ["updated_at", "price", "size", "status"])
  test("stable " + sort + " sorting both ways does not mutate", () => {
    const orders = [
        o("OPEN", { client_order_id: "a" }),
        o("OPEN", { client_order_id: "b" }),
      ],
      before = JSON.stringify(orders);
    for (const desc of [false, true])
      assert.deepEqual(
        selectOrders(orders, all, sort, desc).map((x) => x.client_order_id),
        ["a", "b"],
      );
    assert.equal(JSON.stringify(orders), before);
  });
test("exact decimal sorting exceeds floating point and display precision", () => {
  const orders = [
    o("OPEN", { price: "9007199254740993.00000002" }),
    o("OPEN", { price: "9007199254740993.00000001" }),
  ];
  assert.equal(selectOrders(orders, all, "price", false)[0], orders[1]);
  assert.equal(selectOrders(orders, all, "price", true)[0], orders[0]);
  assert.equal(exactDecimal("0.000000001234567890"), "0.000000001234567890");
  assert.equal(exactDecimal(null), "—");
  assert.equal(exactDecimal("NaN"), "—");
});
test("missing numeric/timestamp data sorts last both ways", () => {
  for (const field of ["price", "size", "updated_at"])
    for (const desc of [true, false]) {
      const orders = [o("OPEN", { [field]: null }), o()];
      assert.equal(selectOrders(orders, all, field, desc)[1], orders[0]);
    }
});
test("timestamp and status sorting changes actual order", () => {
  const orders = [
    o("OPEN"),
    o("FILLED", { updated_at: "2026-10-09T02:00:00Z" }),
  ];
  assert.equal(selectOrders(orders, all, "updated_at", true)[0], orders[1]);
  assert.equal(selectOrders(orders, all, "status", false)[0], orders[1]);
});
test("details match all latest-cycle actions only by identity", () => {
  const t = {
      ...valid,
      reconciliation: [
        { action: "REPLACE", existing: o() },
        { action: "CANCEL", existing: o() },
        { action: "KEEP", existing: o("OPEN", { client_order_id: "other" }) },
      ],
    },
    html = render(OrderDetails, { o: o(), t });
  assert.match(html, /REPLACE, CANCEL/);
  assert.doesNotMatch(html, /KEEP/);
  assert.match(html, /do not confirm/);
});
test("timeline bounded, empty, category filtered and session checked", () => {
  const data = {
    session_id: "one",
    events: Array.from({ length: 250 }, (_, i) => ({
      category: "EXECUTION",
      event_id: String(i),
    })),
  };
  assert.equal(executionEvents(data, "one").length, 200);
  assert.throws(() => executionEvents(data, "two"), /session changed/);
  assert.deepEqual(executionEvents({ ...data, events: [] }, "one"), []);
  assert.equal(
    executionEvents({ ...data, events: [{ category: "RISK" }] }, "one").length,
    0,
  );
});
const quote = {
  side: "BID",
  level_index: 0,
  price: "3000.00000001",
  size: "0.123456789",
};
test("older exact open cannot override newer replacement slot", () => {
  assert.equal(
    quoteEvidence(
      quote,
      [
        o(),
        o("OPEN", {
          client_order_id: "replacement",
          price: "3001",
          updated_at: "2026-10-09T02:00:00Z",
        }),
      ],
      "AUTHORIZED",
    ).kind,
    "uncertain",
  );
});
test("duplicate active slot histories and ties stay uncertain", () => {
  const orders = [
    o(),
    o("PARTIALLY_FILLED", { client_order_id: "two", filled_size: "0.02" }),
  ];
  for (const records of [orders, [...orders].reverse()])
    assert.equal(quoteEvidence(quote, records, "AUTHORIZED").kind, "uncertain");
});
test("latest partial matches original quantity after replacement history", () => {
  const r = quoteEvidence(
    quote,
    [
      o("REPLACED", { updated_at: "2026-10-09T00:30:00Z" }),
      o("PARTIALLY_FILLED", { client_order_id: "new", filled_size: "0.02" }),
    ],
    "AUTHORIZED",
  );
  assert.equal(r.kind, "active");
  assert.equal(r.orderId, "new");
});
test("historical and invalid timestamp cannot label OPEN active", () => {
  assert.equal(
    quoteEvidence(quote, [o()], "AUTHORIZED", true).kind,
    "historical",
  );
  assert.equal(
    quoteEvidence(quote, [o("OPEN", { updated_at: "" })], "AUTHORIZED").kind,
    "uncertain",
  );
});

test("scientific decimal wire values preserve exact magnitude in display and sort", () => {
  assert.equal(exactDecimal("1.2300E-8"), "0.000000012300");
  assert.equal(exactDecimal("1E+3"), "1000");
  assert.equal(exactDecimal("1E+99999"), "—");
  const orders = [o("OPEN", { size: "2E-8" }), o("OPEN", { size: "1E-8" })];
  assert.equal(selectOrders(orders, all, "size", false)[0], orders[1]);
});
test("closed exact history stays historical when newer slot differs", () => {
  assert.equal(
    quoteEvidence(
      quote,
      [
        o("FILLED"),
        o("OPEN", {
          price: "3001",
          client_order_id: "new",
          updated_at: "2026-10-09T02:00:00Z",
        }),
      ],
      "AUTHORIZED",
    ).kind,
    "historical",
  );
});

const { QueryClient, QueryClientProvider } = require("@tanstack/react-query");
const { ExecutionTimeline } = read("components/ExecutionTimeline.js");
function timeline(data, historical = false, error = null) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, retryOnMount: false, gcTime: Infinity },
    },
  });
  if (data) client.setQueryData(["execution-events", "session"], data);
  if (error)
    client
      .getQueryCache()
      .build(client, { queryKey: ["execution-events", "session"] })
      .setState({ status: "error", error: new Error(error) });
  return renderToStaticMarkup(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(ExecutionTimeline, {
        session: "session",
        historical,
      }),
    ),
  );
}
test("timeline loading and unavailable states never fabricate events", () => {
  assert.match(timeline(null), /Loading execution events/);
  assert.match(
    timeline(null, false, "Disconnected"),
    /Execution events unavailable/,
  );
});
test("historical timeline suppresses cached session events", () => {
  const html = timeline(
    [
      {
        event_id: "1",
        category: "EXECUTION",
        timestamp: "2026-10-09T00:00:00Z",
        message: "cached-event",
      },
    ],
    true,
  );
  assert.match(html, /polling paused/);
  assert.doesNotMatch(html, /cached-event/);
});
test("timeline renders authoritative event fields and simulation provenance", () => {
  const html = timeline([
    {
      event_id: "1",
      category: "EXECUTION",
      timestamp: "2026-10-09T00:00:00Z",
      previous_state: "OPEN",
      state: "FILLED",
      message: "Reconciliation: REPLACE BID",
      reference: "order-one",
      version: 2,
      simulated: true,
    },
  ]);
  for (const text of [
    "SIMULATED",
    "OPEN",
    "FILLED",
    "order-one",
    "REPLACE BID",
  ])
    assert.ok(html.includes(text));
});
test("empty timeline describes bounded retained session", () =>
  assert.match(timeline([]), /No matching events in the retained session/));
