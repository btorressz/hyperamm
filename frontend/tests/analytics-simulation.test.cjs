const { test } = require("node:test"),
  assert = require("node:assert/strict"),
  path = require("node:path"),
  React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const read = (p) => require(path.join(process.env.TERMINAL_TEST_BUILD, p));
// Load the actual ESM-only chart package for the CommonJS test compilation.
// Styles are exercised in Chromium, not in server-rendered markup tests.
const Module = require("node:module"),
  originalLoad = Module._load;
Module._load = function (name, ...args) {
  if (name.endsWith(".css")) return {};
  if (name === "lightweight-charts")
    return originalLoad.call(
      this,
      path.resolve(
        __dirname,
        "../node_modules/lightweight-charts/dist/lightweight-charts.development.mjs",
      ),
      ...args,
    );
  return originalLoad.call(this, name, ...args);
};
const {
  effectiveRange,
  checkedHistory,
  historySeries,
  observationCounts,
  boundedObservations,
  needsFit,
} = read("utils/terminalHistory.js");
const {
  reconcileSeries,
  seriesCoordinates,
  contiguousSegments,
  plotSegments,
  chartValue,
} = read("components/HistoryChart.js");
const {
  HistoryRangeSelector,
  AnalyticsOverview,
  ExecutionQualitySummary,
  HistoryMetadata,
} = read("pages/Analytics.js");
const { SimulationPanel, researchMetric } = read(
  "components/SimulationPanel.js",
);
const { SimulationTrace } = read("components/simulation/SimulationTrace.js");
const { CandidateComparison, ParameterChanges } = read(
  "components/simulation/CandidateComparison.js",
);
const { frameError, ResearchRunGate, traceFrames, presetCandidateCount } = read(
  "utils/simulationResearch.js",
);
const { StateDistribution } = read("components/StateDistribution.js");
const { useDisplayStore } = read("stores/display.js"),
  { api } = read("api/client.js");
Module._load = originalLoad;
const valid = require("./fixtures/terminal-valid.json");
const render = (C, p) => renderToStaticMarkup(React.createElement(C, p));
const terminal = () => ({
  ...structuredClone(valid),
  emitted_at: new Date().toISOString(),
});
const point = (sequence, patch = {}) => ({
  sequence,
  timestamp: new Date(Date.UTC(2026, 0, 1, 0, 0, sequence)).toISOString(),
  equity: "100",
  drawdown_pct: "0.05",
  capital_utilization: "0.25",
  risk_state: "NORMAL",
  agent_regime: "QUIET",
  ...patch,
});
const history = (t) => ({
  session_id: t.session_id,
  range: "session",
  retained_points: 50,
  retained_seconds: 49,
  available_ranges: ["session"],
  oldest_at: point(1).timestamp,
  latest_at: point(50).timestamp,
  points: [point(1)],
  max_points: 3600,
  query_max: 1000,
});
const metrics = () => ({
  frame_count: 3,
  starting_equity: "100",
  ending_equity: "101.00000000000000000001",
  session_pnl: "1.00000000000000000001",
  return_pct: "1",
  realized_pnl: "0",
  unrealized_pnl: "1",
  max_drawdown_pct: "0.05",
  fill_count: 2,
  buy_fill_count: 1,
  sell_fill_count: 1,
  quoted_notional: "500",
  filled_notional: "50",
  fill_activity_ratio: "0.1",
  ending_inventory_base: "-0.01",
  max_abs_inventory_base: "0.02",
  max_inventory_utilization: "0.25",
  mean_spread_capture_bps: null,
  mean_mature_markout_bps: null,
  adverse_fill_rate: null,
  keep_count: 1,
  create_count: 2,
  replace_count: 3,
  cancel_count: 4,
  reconciliation_churn_ratio: "0.5",
  risk_state_counts: { NORMAL: 2, HALT: 1 },
  risk_halt_fraction: "0.333",
  agent_regime_counts: { QUIET: 3 },
  toxic_flow_state_counts: { INSUFFICIENT_DATA: 3 },
  execution_quality_state_counts: { NORMAL: 3 },
});
const candidate = (label, patch = {}) => ({
  label,
  strategy_updates: {},
  agent_updates: {},
  configuration_fingerprint: label + "-full-fingerprint",
  training: [],
  validation: [],
  training_score: "9.00000000000000000001",
  validation_score: null,
  training_aggregate: { mean_return_pct: "1", worst_drawdown_pct: "0.05" },
  validation_aggregate: { mean_markout_bps: null },
  score_delta: null,
  baseline_delta: {},
  ...patch,
});
const result = () => ({
  engine_version: "phase10.1-v3",
  run_fingerprint: "run-full",
  dataset_fingerprint: "dataset-full",
  strategy_fingerprint: "strategy-full",
  scenario: "QUIET",
  simulated: true,
  limitations: ["Backend limitation"],
  metrics: metrics(),
  trace: [
    point(1, { inventory_base: "0", session_pnl: "0", mid: "100" }),
    point(2, { inventory_base: null, session_pnl: "1", mid: null }),
  ],
});
test("range fallback preserves saved preference and history size", () => {
  const previous = { ...useDisplayStore.getState() };
  useDisplayStore.getState().setDefaultRange("15m");
  assert.equal(
    effectiveRange(useDisplayStore.getState().defaultRange, ["session", "1m"]),
    "session",
  );
  assert.equal(useDisplayStore.getState().defaultRange, "15m");
  assert.equal(useDisplayStore.getState().historySize, previous.historySize);
  assert.equal(effectiveRange("15m", ["session", "15m"]), "15m");
  useDisplayStore.setState(previous);
});
test("unavailable ranges disabled; effective session pressed", () => {
  const html = render(HistoryRangeSelector, {
    preference: "5m",
    available: ["session", "1m"],
    onChange: () => {},
  });
  assert.match(html, /aria-pressed="true"[^>]*>SESSION/);
  assert.match(html, /disabled=""[^>]*>5M/);
  assert.doesNotMatch(html, /disabled=""[^>]*>1M/);
});
test("all backend-available ranges enabled", () => {
  const html = render(HistoryRangeSelector, {
    preference: "1h",
    available: ["session", "1m", "5m", "15m", "1h"],
    onChange: () => {},
  });
  assert.doesNotMatch(html, /disabled/);
  assert.match(html, /aria-pressed="true"[^>]*>1H/);
});
for (const transition of [
  "session",
  "process",
  "disconnect",
  "stale",
  "future",
  "range",
  "response-session",
  "size",
])
  test("in-flight history rejects " + transition, async () => {
    const t = terminal(),
      data = history(t),
      current = { terminal: structuredClone(t), wsState: "connected" };
    let resolve;
    const request = new Promise((r) => (resolve = r)).then((data) =>
      checkedHistory(data, t, current, "session", 10),
    );
    if (transition === "session") current.terminal.session_id = "next";
    if (transition === "process") current.terminal.process_id = "next";
    if (transition === "disconnect") current.wsState = "disconnected";
    if (transition === "stale")
      current.terminal.emitted_at = "2001-01-01T00:00:00Z";
    if (transition === "future")
      current.terminal.emitted_at = "2099-01-01T00:00:00Z";
    if (transition === "range") data.range = "1m";
    if (transition === "response-session") data.session_id = "next";
    if (transition === "size")
      data.points = Array.from({ length: 11 }, (_, i) => point(i));
    resolve(data);
    await assert.rejects(request);
  });
test("matching history remains original backend evidence", () => {
  const t = terminal(),
    data = history(t);
  assert.equal(
    checkedHistory(
      data,
      t,
      { terminal: t, wsState: "connected" },
      "session",
      10,
    ),
    data,
  );
});
test("history compaction keeps sequence identity and latest second-bucket sequence", () => {
  const points = [
    point(3),
    point(1),
    point(2, { timestamp: point(1).timestamp, equity: "200" }),
    point(2, { equity: "999" }),
  ];
  assert.deepEqual(
    boundedObservations(points, 100).map((p) => p.sequence),
    [2, 3],
  );
  assert.deepEqual(
    historySeries(points, "equity").map((p) => p.value),
    [200, 100],
  );
});
for (const key of ["drawdown_pct", "capital_utilization"])
  test(key + " fraction scales once", () => {
    const p = point(1);
    assert.equal(
      historySeries([p], key, true)[0].value,
      key === "drawdown_pct" ? 5 : 25,
    );
    assert.equal(p[key], key === "drawdown_pct" ? "0.05" : "0.25");
  });
test("missing values, nonfinite values and invalid history timestamps stay absent", () => {
  const data = historySeries(
    [
      point(1, { equity: null }),
      point(2, { equity: "NaN" }),
      point(3, { timestamp: "invalid" }),
      point(4, { equity: "Infinity" }),
    ],
    "equity",
  );
  assert.equal(data.length, 3);
  assert.ok(data.every((p) => p.value === null));
});
test("long history bounded; polling preserves zoom fit identity", () => {
  assert.equal(
    boundedObservations(
      Array.from({ length: 1200 }, (_, i) => point(i)),
      2000,
    ).length,
    1000,
  );
  assert.equal(needsFit("session:1m", "session:1m", true), false);
  assert.equal(needsFit("old", "new", true), true);
  assert.equal(needsFit(null, "new", false), false);
});
function chartMock() {
  return {
    added: [],
    removed: [],
    addSeries(kind, options) {
      const s = {
        options,
        data: [],
        applyOptions(p) {
          Object.assign(this.options, p);
        },
        setData(d) {
          this.data = d;
        },
        createPriceLine(p) {
          this.zero = p;
        },
      };
      this.added.push(s);
      return s;
    },
    removeSeries(s) {
      this.removed.push(s);
    },
  };
}
test("series lifecycle updates labels, scale, kind, additions and removals", () => {
  const c = chartMock(),
    entries = new Map(),
    line = { key: "equity", label: "Equity", color: "green" };
  reconcileSeries(c, entries, [line]);
  const first = entries.get("equity").series;
  reconcileSeries(c, entries, [{ ...line }]);
  assert.equal(c.added.length, 1);
  reconcileSeries(c, entries, [
    { ...line, label: "New label", percent: true, signed: true },
  ]);
  assert.ok(c.removed.includes(first));
  assert.equal(entries.get("equity").series.options.title, "New label");
  assert.equal(
    entries.get("equity").series.options.priceFormat.formatter(5),
    "5%",
  );
  reconcileSeries(c, entries, []);
  assert.equal(entries.size, 0);
  assert.equal(c.removed.length, 2);
});
test("gaps produce contiguous series and remove obsolete segments", () => {
  const data = [
    { time: 1, value: 1 },
    { time: 2, value: null },
    { time: 3, value: 3 },
    { time: 4, value: 4 },
    { time: 5, value: null },
  ];
  assert.deepEqual(contiguousSegments(data), [
    [{ time: 1, value: 1 }],
    [
      { time: 3, value: 3 },
      { time: 4, value: 4 },
    ],
  ]);
  const c = chartMock(),
    entries = new Map(),
    line = { key: "equity", label: "Equity", color: "green" };
  reconcileSeries(c, entries, [line]);
  const entry = entries.get("equity");
  plotSegments(c, entry, line, data);
  assert.equal(entry.segments.length, 1);
  assert.deepEqual(entry.series.data, [
    { time: 1, value: 1 },
    { time: 2 },
    { time: 3 },
    { time: 4 },
    { time: 5 },
  ]);
  assert.deepEqual(entry.segments[0].data, [
    { time: 3, value: 3 },
    { time: 4, value: 4 },
  ]);
  plotSegments(c, entry, line, [{ time: 1, value: 1 }]);
  assert.equal(entry.segments.length, 0);
  assert.equal(c.removed.length, 1);
});
test("removed configuration cleans gap segments too", () => {
  const c = chartMock(),
    entries = new Map(),
    line = { key: "equity", label: "Equity", color: "green" };
  reconcileSeries(c, entries, [line]);
  plotSegments(c, entries.get("equity"), line, [
    { time: 1, value: 1 },
    { time: 2, value: null },
    { time: 3, value: 3 },
  ]);
  reconcileSeries(c, entries, []);
  assert.equal(c.removed.length, 2);
});
test("tooltips retain exact economics and percent conversion", () => {
  assert.equal(
    chartValue("9007199254740993.00000001", { unit: "quote" }),
    "9007199254740993.00000001 quote",
  );
  assert.equal(chartValue("0.05", { percent: true }), "5%");
  assert.equal(chartValue(null, { unit: "base" }), "Unavailable");
});
test("distributions count returned samples, never duration", () => {
  const counts = observationCounts(
    [point(1), point(2), point(3, { risk_state: "HALT" })],
    "risk_state",
  );
  assert.deepEqual(counts, { NORMAL: 2, HALT: 1 });
  const html = render(StateDistribution, { counts, label: "Risk states" });
  assert.match(html, /2 observations/);
  assert.match(html, /not time-weighted duration/);
  assert.match(
    render(StateDistribution, { counts: {}, label: "Risk states" }),
    /No observations/,
  );
});
test("overview separates session and current net PnL; missing TESTNET equity stays unavailable", () => {
  const t = terminal();
  Object.assign(t.vault, {
    session_pnl_quote: "123.01",
    net_pnl_quote: "999",
    equity_quote: null,
    mode: "TESTNET",
    accounting_complete: "PARTIAL",
  });
  const html = render(AnalyticsOverview, { t, historical: true });
  assert.match(html, /123.01 quote/);
  assert.doesNotMatch(html, /999 quote/);
  for (const label of ["Unavailable", "HISTORICAL", "PARTIAL"])
    assert.ok(html.includes(label));
});
test("pending markouts never counted as completed evidence", () => {
  const t = terminal();
  t.agents.toxic_flow.metrics.matured_fills = 0;
  t.agents.execution_quality.metrics.average_mature_markout_bps = "25";
  const html = render(ExecutionQualitySummary, { t });
  assert.doesNotMatch(html, /25 bps/);
  assert.match(html, /Mature markout<\/span><strong>Unavailable/);
  assert.match(html, /Adverse fill rate<\/span><strong>Unavailable/);
});
test("supported markouts preserve signed bps and adverse fraction", () => {
  const t = terminal();
  t.agents.toxic_flow.metrics.matured_fills = 2;
  t.agents.toxic_flow.metrics.adverse_fill_rate = "0.5";
  t.agents.execution_quality.metrics.average_mature_markout_bps = "-2.5";
  const html = render(ExecutionQualitySummary, { t });
  assert.match(html, /-2.5 bps/);
  assert.match(html, /50%/);
});
test("retention metadata separates sampled response from full retained count", () => {
  const html = render(HistoryMetadata, { data: history(terminal()) });
  assert.match(html, /50 observations/);
  assert.match(html, /1 returned samples/);
  assert.match(html, /not permanent account history/);
});
for (const input of ["", "1", "1001", "2.5", "NaN", "Infinity", "-5"])
  test("frame input rejects " + input, () => assert.ok(frameError(input)));
test("bounded frame limits and existing preset sizes valid", () => {
  assert.equal(frameError("2"), "");
  assert.equal(frameError("1000"), "");
  assert.equal(presetCandidateCount("Balanced"), 8);
  assert.equal(presetCandidateCount("Inventory"), 4);
  assert.equal(presetCandidateCount("AdverseFlow"), 8);
});
test("research admission prevents duplicate submissions and obsolete completions", () => {
  const gate = new ResearchRunGate(),
    a = gate.start();
  assert.equal(gate.start(), null);
  assert.equal(gate.finish(a), true);
  const b = gate.start();
  assert.equal(gate.current(a), false);
  assert.equal(gate.finish(a), false);
  assert.equal(gate.current(b), true);
  gate.retire();
  assert.equal(gate.current(b), false);
  assert.notEqual(gate.start(), b);
});
test("same-second trace frames retain backend sequence order", () => {
  const trace = [
    point(3),
    point(1),
    point(2, { timestamp: point(1).timestamp }),
    point(2, { equity: "999" }),
  ];
  assert.deepEqual(
    traceFrames(trace).map((p) => p.sequence),
    [1, 2, 3],
  );
  assert.equal(
    seriesCoordinates(traceFrames(trace), { key: "equity" }, "frame").length,
    3,
  );
});
test("invalid timestamp retains frame identity and invalid value stays missing", () => {
  const p = point(1, { timestamp: "invalid", equity: "NaN" });
  assert.equal(traceFrames([p])[0], p);
  assert.deepEqual(seriesCoordinates([p], { key: "equity" }, "frame"), [
    { time: 1, value: null },
  ]);
});
test("trace empty, singleton, invalid sequence and oversized response bounded", () => {
  assert.equal(traceFrames([]).length, 0);
  assert.equal(traceFrames([point(1)]).length, 1);
  assert.equal(
    traceFrames([{ sequence: NaN }, { sequence: -1 }, point(1)]).length,
    1,
  );
  assert.equal(
    traceFrames(Array.from({ length: 1000 }, (_, i) => point(i))).length,
    250,
  );
});
test("simulation exact quote/base economics, percent and bps units", () => {
  const html = render(SimulationPanel, { m: metrics() });
  for (const value of [
    "101.00000000000000000001 quote",
    "1.00000000000000000001 quote",
    "1%",
    "5%",
    "25%",
    "-0.01 base",
    "Unavailable",
  ])
    assert.ok(html.includes(value), value);
  assert.equal(researchMetric("mean_mature_markout_bps", "5"), "5 bps");
  assert.equal(researchMetric("return_pct", null), "Unavailable");
});
test("trace chart labels separate units, frame axis and state evidence", () => {
  const html = render(SimulationTrace, { result: result() });
  for (const label of [
    "Simulated equity",
    "Simulated session PnL",
    "Market / perpetual references",
    "Simulated inventory",
    "Simulated drawdown",
    "Quote &amp; order activity",
    "Frame state evidence",
    "SIMULATED FRAME INDEX",
    "requested cap 250",
  ])
    assert.ok(html.includes(label), label);
  assert.match(
    render(SimulationTrace, { result: { ...result(), trace: [] } }),
    /No trace points were returned/,
  );
});
test("parameters preserve separate groups, original keys and exact values", () => {
  const c = candidate("a", {
      strategy_updates: { same_key: "0.00000000000000001" },
      agent_updates: { same_key: "99999999999999999" },
    }),
    html = render(ParameterChanges, { candidate: c });
  for (const text of [
    "strategy_updates",
    "agent_updates",
    "same_key",
    "0.00000000000000001",
    "99999999999999999",
    "Unreported baseline parameter values are unavailable",
    c.configuration_fingerprint,
  ])
    assert.ok(html.includes(text), text);
});
test("candidate ranking, null validation, baseline and rejected reasons remain backend-owned", () => {
  const r = {
    engine_version: "v",
    simulated: true,
    baseline: candidate("baseline"),
    ranked_candidates: [
      candidate("Backend first"),
      candidate("Backend second", { training_score: "999" }),
    ],
    requested_candidate_count: 3,
    candidate_count: 2,
    rejected_candidates: [
      {
        reason: "bounded field invalid",
        strategy_updates: { levels_per_side: 0 },
      },
    ],
    training_scenarios: ["QUIET"],
    validation_scenarios: ["FLASH_MOVE"],
    objective: { return_weight: "1" },
  };
  const html = render(CandidateComparison, { result: r });
  assert.ok(
    html.indexOf("1. Backend first") < html.indexOf("2. Backend second"),
  );
  for (const label of [
    "BASELINE",
    "Unavailable",
    "bounded field invalid",
    "Compare left",
    "Compare right",
    "Validation evaluation only",
    "mean_markout_bps",
    "worst_drawdown_pct",
    "5%",
  ])
    assert.ok(html.includes(label), label);
  assert.doesNotMatch(html, /Deploy|Current defaults/);
  const capped = render(CandidateComparison, {
    result: {
      ...r,
      ranked_candidates: [
        ...r.ranked_candidates,
        candidate("Third"),
        candidate("Fourth"),
        candidate("Fifth"),
        candidate("Beyond five"),
      ],
    },
  });
  assert.match(capped, /5 shown of 6 ranked candidates/);
  assert.doesNotMatch(capped, /Beyond five/);
});
for (const [status, detail, expected] of [
  [
    422,
    [{ loc: ["body", "frames"], msg: "out of bounds" }],
    "Review the scenario",
  ],
  [429, "busy", "Research capacity is busy"],
  [503, "unavailable", "coordination is restored"],
  [500, "failure", "backend diagnostics"],
])
  test("HTTP " + status + " research error actionable", async () => {
    const before = global.fetch;
    try {
      global.fetch = async () => ({
        ok: false,
        status,
        json: async () => ({ detail }),
      });
      await assert.rejects(api.runSimulation({}), new RegExp(expected));
    } finally {
      global.fetch = before;
    }
  });
test("history request carries range, size and AbortSignal", async () => {
  const before = global.fetch,
    signal = new AbortController().signal;
  let captured;
  try {
    global.fetch = async (...args) => {
      captured = args;
      return { ok: true, json: async () => ({}) };
    };
    await api.terminalHistory("1m", 100, signal);
    assert.equal(captured[0], "/api/v1/terminal/history?range=1m&limit=100");
    assert.equal(captured[1].signal, signal);
  } finally {
    global.fetch = before;
  }
});

test("chart display rejects overflow after scaling and invalid value types", () => {
  for (const value of ["1e308", true, [], { value: 5 }]) {
    assert.equal(
      historySeries(
        [point(1, { drawdown_pct: value })],
        "drawdown_pct",
        true,
      )[0].value,
      null,
    );
    assert.equal(
      seriesCoordinates(
        [point(1, { drawdown_pct: value })],
        { key: "drawdown_pct", percent: true },
        "frame",
      )[0].value,
      null,
    );
  }
});
