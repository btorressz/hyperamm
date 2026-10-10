const { test } = require("node:test");
const assert = require("node:assert/strict"),
  path = require("node:path"),
  React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const Module = require("node:module"),
  originalLoad = Module._load;
Module._load = function (name, ...args) {
  if (name.endsWith(".css")) return {};
  return originalLoad.call(this, name, ...args);
};
const savedStorage = global.localStorage,
  savedWindow = global.window,
  storage = new Map();
global.localStorage = {
  getItem: (k) => storage.get(k) ?? null,
  setItem: (k, v) => storage.set(k, v),
  removeItem: (k) => storage.delete(k),
};
global.window = { localStorage: global.localStorage };
const read = (p) => require(path.join(process.env.TERMINAL_TEST_BUILD, p));
delete require.cache[
  path.join(process.env.TERMINAL_TEST_BUILD, "stores/display.js")
];
const {
  checkedTerminalEvents,
  checkedEventLimit,
  eventView,
  eventTransition,
  eventExport,
  eventCategories,
} = read("utils/terminalEventView.js");
const { EventTimeline, EventDetails } = read("components/EventTimeline.js");
const { Settings } = read("pages/Settings.js");
const { ProviderHealthSummary } = read(
  "components/settings/ProviderHealthSummary.js",
);
const { SystemHealth } = read("components/SystemHealth.js");
const {
  useDisplayStore: display,
  displayDefaults,
  validatedDisplay,
} = read("stores/display.js");
const { useTerminalStore: terminal } = read("stores/terminal.js");
const { api } = read("api/client.js");
Module._load = originalLoad;
global.localStorage = savedStorage;
global.window = savedWindow;
const valid = require("./fixtures/terminal-valid.json");
const render = (C, props) =>
  renderToStaticMarkup(React.createElement(C, props));
const frame = () => ({
  ...structuredClone(valid),
  emitted_at: new Date().toISOString(),
});
const event = (id = "event-full-id", patch = {}) => ({
  event_id: id,
  timestamp: "2026-01-01T00:00:00Z",
  category: "RISK",
  previous_state: "NORMAL",
  state: "WIDEN",
  message: "Backend reference check",
  reference: "risk-reference-full",
  version: 0,
  simulated: true,
  ...patch,
});
const response = (t, events = [event()], patch = {}) => ({
  session_id: t.session_id,
  order: "newest-first",
  max_events: 500,
  events,
  ...patch,
});
const current = (t) => ({ terminal: t, wsState: "connected" });

for (const category of eventCategories)
  test("events preserve backend category " + category, () => {
    const t = frame(),
      data = response(t, [event(category, { category })]);
    assert.equal(checkedTerminalEvents(data, t, current(t), category), data);
    assert.throws(
      () =>
        checkedTerminalEvents(
          data,
          t,
          current(t),
          category === "SYSTEM" ? "RISK" : "SYSTEM",
        ),
      /incompatible/,
    );
  });
for (const patch of [
  { session_id: "retired" },
  { order: "oldest-first" },
  { max_events: 999 },
  { events: {} },
  { events: [event(), event()] },
])
  test(
    "reject incompatible event envelope " + JSON.stringify(patch).slice(0, 50),
    () => {
      const t = frame();
      assert.throws(
        () =>
          checkedTerminalEvents(response(t, undefined, patch), t, current(t)),
        /incompatible/,
      );
    },
  );
for (const patch of [
  { event_id: "" },
  { timestamp: "invalid" },
  { category: "UNREPORTED" },
  { previous_state: undefined },
  { state: 1 },
  { message: null },
  { reference: undefined },
  { version: -1 },
  { version: 1.5 },
  { simulated: "true" },
])
  test(
    "reject malformed event record " +
      Object.keys(patch)[0] +
      ":" +
      String(Object.values(patch)[0]),
    () => {
      const t = frame();
      assert.throws(
        () =>
          checkedTerminalEvents(
            response(t, [event("e", patch)]),
            t,
            current(t),
          ),
        /incompatible/,
      );
    },
  );
test("empty records succeed; null references and zero versions remain distinct", () => {
  const t = frame();
  assert.deepEqual(
    checkedTerminalEvents(response(t, []), t, current(t)).events,
    [],
  );
  const e = event("null", {
    reference: null,
    previous_state: null,
    state: null,
    version: null,
  });
  assert.equal(
    checkedTerminalEvents(response(t, [e]), t, current(t)).events[0],
    e,
  );
});
test("bounded response distinguishes 200 loaded from retention capacity and enforces requested limit", () => {
  const t = frame(),
    events = Array.from({ length: 500 }, (_, i) => event("id-" + i));
  assert.equal(
    checkedTerminalEvents(response(t, events), t, current(t), undefined, 500)
      .events.length,
    500,
  );
  assert.throws(
    () =>
      checkedTerminalEvents(response(t, events), t, current(t), undefined, 200),
    /incompatible/,
  );
});
for (const limit of [0, 501, 1.5, NaN, Infinity])
  test("reject unbounded event limit " + limit, () =>
    assert.throws(() => checkedEventLimit(limit), /1 to 500/),
  );
test("case-insensitive trimmed search matches each declared searchable field", () => {
  const e = event("CaseIdentity", {
    reference: "CaseReference",
    previous_state: "BeforeState",
    state: "AfterState",
    message: "Mixed Message",
    version: 42,
  });
  for (const term of [
    " caseidentity ",
    "CASEREFERENCE",
    "beforestate",
    "AFTERSTATE",
    "MIXED MESSAGE",
    "risk",
    "42",
  ])
    assert.deepEqual(eventView([e], term, "newest-first"), [e]);
  assert.deepEqual(eventView([e], "absent", "newest-first"), []);
  assert.deepEqual(eventView([e], "  ", "newest-first"), [e]);
  assert.deepEqual(eventView([e], "", "newest-first"), [e]);
});
test("newest order preserves backend position; oldest order keeps equal timestamps stable without ID chronology", () => {
  const events = [
    event("a", { timestamp: "2026-01-01T00:00:02Z" }),
    event("z"),
    event("b"),
  ];
  const before = structuredClone(events);
  assert.deepEqual(
    eventView(events, "", "newest-first").map((e) => e.event_id),
    ["a", "z", "b"],
  );
  assert.deepEqual(
    eventView(events, "", "oldest-first").map((e) => e.event_id),
    ["z", "b", "a"],
  );
  assert.deepEqual(events, before);
});
test("ordering preserves sub-millisecond source time", () => {
  const events = [
    event("new", { timestamp: "2026-01-01T00:00:00.000900Z" }),
    event("old", { timestamp: "2026-01-01T00:00:00.000100Z" }),
  ];
  assert.deepEqual(
    eventView(events, "", "oldest-first").map((e) => e.event_id),
    ["old", "new"],
  );
});
for (const [previous_state, state, expected] of [
  ["NORMAL", "HALT", "NORMAL → HALT"],
  [null, "NORMAL", "Observed state: NORMAL"],
  ["NORMAL", null, "new state not reported"],
  [null, null, "No state transition reported"],
])
  test(
    "event transition preserves missing states " + previous_state + "/" + state,
    () =>
      assert.ok(
        eventTransition(event("e", { previous_state, state })).includes(
          expected,
        ),
      ),
  );
test("event details preserve full message, identity, timestamp and null values without execution claims", () => {
  const e = event("full-id-" + "a".repeat(90), {
    message: "long message ".repeat(100),
    reference: null,
    version: null,
  });
  const html = render(EventDetails, { event: e });
  for (const value of [
    e.event_id,
    e.message,
    e.timestamp,
    "Null (not reported)",
    "Simulated flag",
    "true",
  ])
    assert.ok(html.includes(value));
  assert.doesNotMatch(html, /venue transaction|executed order/i);
});
test("timeline uses native expansion buttons, explicit empty state and neutral RISK category", () => {
  const html = render(EventTimeline, { events: [event()] });
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /aria-controls=/);
  assert.match(html, /SIMULATED/);
  assert.match(html, /class="badge neutral">RISK/);
  assert.doesNotMatch(html, /class="badge bad"/);
  assert.match(
    render(EventTimeline, {
      events: [],
      emptyMessage: "Filtered empty evidence",
    }),
    /Filtered empty evidence/,
  );
});
for (const kind of ["process", "session", "disconnected", "expired", "future"])
  test("events reject " + kind + " attribution at completion", () => {
    const t = frame(),
      state = current(structuredClone(t));
    if (kind === "process") state.terminal.process_id = "replacement-process";
    if (kind === "session") state.terminal.session_id = "replacement-session";
    if (kind === "disconnected") state.wsState = "disconnected";
    if (kind === "expired") state.terminal.emitted_at = "2001-01-01T00:00:00Z";
    if (kind === "future")
      state.terminal.emitted_at = new Date(Date.now() + 60000).toISOString();
    assert.throws(
      () => checkedTerminalEvents(response(t), t, state),
      /retired|disconnected/,
    );
  });
test("in-flight REST completion cannot seed a replacement terminal session", async () => {
  const before = global.fetch,
    t = frame(),
    state = current(t);
  let release;
  global.fetch = () =>
    new Promise((resolve) => {
      release = () => resolve({ ok: true, json: async () => response(t) });
    });
  try {
    const pending = api.terminalEvents();
    state.terminal = {
      ...t,
      process_id: "new-process",
      session_id: "new-session",
    };
    release();
    const data = await pending;
    assert.throws(() => checkedTerminalEvents(data, t, state), /retired/);
  } finally {
    global.fetch = before;
  }
});
test("events API passes category, limit and AbortSignal and exposes HTTP failures", async () => {
  const before = global.fetch,
    signal = new AbortController().signal;
  let args;
  try {
    global.fetch = async (...x) => {
      args = x;
      return { ok: true, json: async () => ({}) };
    };
    await api.terminalEvents("RISK", 500, signal);
    assert.equal(args[0], "/api/v1/terminal/events?limit=500&category=RISK");
    assert.equal(args[1].signal, signal);
    global.fetch = async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: "Events unavailable" }),
    });
    await assert.rejects(api.terminalEvents(), /Events unavailable/);
  } finally {
    global.fetch = before;
  }
});
test("export preserves filtered event records, nulls and safe bounded session metadata", () => {
  const t = frame(),
    events = [
      event("simulated", { version: null, reference: null }),
      event("other", { simulated: false }),
    ],
    data = response(t, events);
  const metadata = {
    processId: t.process_id,
    sessionId: t.session_id,
    category: undefined,
    limit: 200,
    historical: true,
    order: "oldest-first",
  };
  const out = eventExport(data, [events[0]], metadata, "2026-01-01T01:00:00Z");
  assert.equal(out.loaded_event_count, 2);
  assert.equal(out.exported_event_count, 1);
  assert.equal(out.max_retained_events, 500);
  assert.equal(out.display_state, "HISTORICAL");
  assert.equal(out.backend_order, "newest-first");
  assert.equal(out.display_order, "oldest-first");
  assert.deepEqual(out.events, [events[0]]);
  assert.equal(out.generated_at, "2026-01-01T01:00:00Z");
  assert.match(out.provenance, /not server-authenticated/);
  assert.throws(
    () => eventExport(data, [event("unloaded")], metadata),
    /loaded session/,
  );
  assert.throws(
    () => eventExport(data, [], { ...metadata, sessionId: "other" }),
    /loaded session/,
  );
});
test("export omits browser storage, arbitrary response fields and unrelated diagnostics", () => {
  const t = frame(),
    e = event("selected", {
      internal_diagnostics: "DO-NOT-EXPORT",
      api_key: "DO-NOT-EXPORT",
    });
  const data = response(t, [e], {
    browser_storage: "DO-NOT-EXPORT",
    private_key: "DO-NOT-EXPORT",
  });
  const out = JSON.stringify(
    eventExport(data, [e], {
      processId: t.process_id,
      sessionId: t.session_id,
      limit: 200,
      historical: false,
      order: "newest-first",
    }),
  );
  assert.doesNotMatch(
    out,
    /DO-NOT-EXPORT|browser_storage|api_key|private_key|internal_diagnostics/,
  );
});
test("display controls persist all four preferences and preserve supported saved ranges", () => {
  display.getState().setDense(true);
  display.getState().setSidebarCollapsed(true);
  display.getState().setHistorySize(1000);
  display.getState().setDefaultRange("1h");
  assert.deepEqual(JSON.parse(storage.get("hyperamm-display-v1")).state, {
    dense: true,
    sidebarCollapsed: true,
    historySize: 1000,
    defaultRange: "1h",
  });
});
test("reset restores four defaults, writes owned persistence and preserves terminal, ledger, kill and strategy evidence", () => {
  const old = terminal.getState(),
    t = frame();
  terminal.setState({ terminal: t, wsState: "connected" });
  storage.set("unrelated-key", "retain");
  try {
    display.getState().resetDisplayPreferences();
    assert.deepEqual(
      JSON.parse(storage.get("hyperamm-display-v1")).state,
      displayDefaults,
    );
    assert.equal(storage.get("unrelated-key"), "retain");
    assert.equal(terminal.getState().terminal, t);
    assert.equal(terminal.getState().terminal.vault, t.vault);
    assert.equal(terminal.getState().terminal.risk, t.risk);
    assert.equal(terminal.getState().terminal.strategy, t.strategy);
  } finally {
    terminal.setState(old);
  }
});
test("reset survives actual Zustand storage rehydration", async () => {
  display.getState().setDense(true);
  display.getState().resetDisplayPreferences();
  const saved = storage.get("hyperamm-display-v1");
  display.setState({ dense: true, historySize: 100 });
  storage.set("hyperamm-display-v1", saved);
  await display.persist.rehydrate();
  assert.equal(display.getState().dense, false);
  assert.equal(display.getState().historySize, 600);
});
for (const corrupt of [
  null,
  [],
  "bad",
  {
    dense: "true",
    sidebarCollapsed: 1,
    historySize: 999999,
    defaultRange: "10y",
  },
  { historySize: NaN, defaultRange: null },
])
  test(
    "display hydration validates unsupported persisted values " +
      JSON.stringify(corrupt),
    () => assert.deepEqual(validatedDisplay(corrupt), displayDefaults),
  );
test("hydration cannot replace display actions or import unowned preference fields", async () => {
  storage.set(
    "hyperamm-display-v1",
    JSON.stringify({
      state: {
        dense: true,
        resetDisplayPreferences: "injected",
        private_key: "unowned",
      },
      version: 0,
    }),
  );
  await display.persist.rehydrate();
  assert.equal(typeof display.getState().resetDisplayPreferences, "function");
  assert.equal(display.getState().private_key, undefined);
  display.getState().resetDisplayPreferences();
});
test("Settings exposes preference ownership and works without accepted backend state", () => {
  const html = render(Settings, { t: null, historical: true });
  for (const label of [
    "Layout density",
    "Sidebar layout",
    "Default chart range",
    "History view size",
    "Reset display preferences",
    "Browser-only",
    "not shared account preferences",
    "Waiting for accepted terminal evidence",
  ])
    assert.ok(html.includes(label), label);
  assert.doesNotMatch(
    html,
    /type="password"|private.key|enable signed orders|Save environment/i,
  );
});
test("Settings differentiates manual kill, risk halt, TESTNET eligibility and backend authority", () => {
  const t = frame(),
    old = terminal.getState();
  t.risk.kill_switch_active = false;
  t.risk_firewall.state = "HALT";
  t.diagnostics.testnet_enabled = true;
  terminal.setState({ terminal: t, wsState: "connected" });
  try {
    const html = render(Settings, { t });
    for (const label of [
      "KILL INACTIVE",
      "HALT",
      "ENABLED",
      "does not prove account authentication",
      "Backend-owned",
      "Redis availability",
      "one backend worker",
    ])
      assert.ok(html.includes(label), label);
    assert.doesNotMatch(html, /type="password"|Save environment/i);
  } finally {
    terminal.setState(old);
  }
});
for (const reason of ["disconnected", "stale", "process", "session"])
  test(
    "SystemHealth retains historical evidence for " +
      reason +
      " without green current health",
    () => {
      const t = frame(),
        accepted = structuredClone(t),
        old = terminal.getState();
      if (reason === "stale") accepted.emitted_at = "2001-01-01T00:00:00Z";
      if (reason === "process") accepted.process_id = "other";
      if (reason === "session") accepted.session_id = "other";
      terminal.setState({
        terminal: accepted,
        wsState: reason === "disconnected" ? "disconnected" : "connected",
      });
      try {
        const html = render(SystemHealth, { t });
        assert.match(html, /HISTORICAL/);
        assert.doesNotMatch(html, /badge good/);
      } finally {
        terminal.setState(old);
      }
    },
  );
test("provider summary shows reported hierarchy, exact prices, source time, stale/error and transport evidence", () => {
  const t = frame();
  t.references.evidence.REDSTONE = {
    ...t.references.evidence.KRAKEN,
    provider: "REDSTONE",
    price: "3000.00000000000000001",
    source_timestamp: "2026-01-01T00:00:00Z",
    stale: true,
    healthy: false,
    status: "DEGRADED",
    error: "Reported transport failure",
    transport: "LIVE_WS",
  };
  const html = render(ProviderHealthSummary, { t, historical: false });
  for (const label of [
    "Primary external oracle",
    "3000.00000000000000001",
    "2026-01-01T00:00:00Z",
    "REPORTED STALE",
    "DEGRADED",
    "LIVE_WS",
    "Reported transport failure",
    "do not grant permission",
  ])
    assert.ok(html.includes(label), label);
});
test("missing providers remain unavailable; historical sources make no current freshness claim", () => {
  const t = frame();
  const html = render(ProviderHealthSummary, { t, historical: true });
  assert.match(html, /HISTORICAL/);
  assert.doesNotMatch(html, /badge good/);
  t.references = null;
  assert.match(
    render(ProviderHealthSummary, { t, historical: false }),
    /Provider evidence unavailable/,
  );
});
test("provider roles use actual native provider IDs and preserve the backend hierarchy", () => {
  const html = render(ProviderHealthSummary, { t: frame(), historical: false });
  for (const role of [
    "Primary external oracle",
    "Native oraclePx",
    "Independent exchange reference",
    "Tertiary aggregate",
    "Execution venue midpoint",
    "Perpetual mark",
  ])
    assert.ok(html.includes(role), role);
  assert.ok(
    html.indexOf("Primary external oracle") < html.indexOf("Native oraclePx"),
  );
  assert.ok(
    html.indexOf("Native oraclePx") <
      html.indexOf("Independent exchange reference"),
  );
});
