import type {
  FormDraft,
  PortfolioDraft,
  Preview,
  TerminalResult,
  TerminalRequest,
  Market,
  StressKind,
  RiskReport,
} from "../types/portfolioResearch";
export const markets: Market[] = ["BTC", "ETH", "SOL"];
export const stressKinds: Record<StressKind, string> = {
  CORRELATED_SELLOFF: "Correlated Market Selloff",
  BTC_LED_VOLATILITY: "BTC-Led Volatility Shock",
  LIQUIDITY_SHOCK: "Liquidity Shock",
  FUNDING_STRESS: "Funding Stress",
  ORACLE_DEGRADATION: "Oracle Degradation",
  CONCENTRATION_STRESS: "Concentration Stress",
};
export const riskLabels = {
  max_gross_exposure_quote: "Gross exposure (USDC)",
  max_abs_net_exposure_quote: "Absolute net exposure (USDC)",
  max_session_loss_quote: "Session loss (USDC)",
  max_drawdown_fraction: "Portfolio drawdown (fraction)",
  max_capital_utilization: "Capital utilization (fraction)",
  max_inventory_concentration: "Inventory concentration (fraction)",
  modeled_leverage_ceiling: "Modeled leverage (×)",
};
export function initialDraft(): FormDraft {
  return {
    budget: { total_equity_quote: "100000", minimum_reserve_quote: "5000" },
    allocations: [
      { market: "BTC", allocated_equity_quote: "40000" },
      { market: "ETH", allocated_equity_quote: "35000" },
      { market: "SOL", allocated_equity_quote: "20000" },
    ],
    risk_limits: {
      max_gross_exposure_quote: "100000",
      max_abs_net_exposure_quote: "100000",
      max_session_loss_quote: "10000",
      max_drawdown_fraction: "0.2",
      max_capital_utilization: "1",
      max_inventory_concentration: "0.75",
      modeled_leverage_ceiling: "3",
    },
    risk_policy: { warning_ratio: "0.8", reduction_ratio: "0.95" },
    strategy: {
      amm_model: "CONSTANT_PRODUCT",
      levels_per_side: "8",
      max_distance_bps: "100",
      base_order_size: "0.1",
      total_liquidity: "4",
      concentration_factor: "8",
      inventory_skew_enabled: true,
      market_adaptation_enabled: true,
    },
    paper: {
      fee_enabled: false,
      maker_fee_bps: "1",
      taker_fee_bps: "3",
      funding_enabled: true,
      funding_interval_seconds: 1,
      execution: {
        mode: "BASELINE",
        order_latency_ms: "0",
        cancel_latency_ms: "0",
        slippage_bps: "0",
        depth_sensitive: false,
        allow_partial_fills: true,
        participation_rate: "1",
        max_fill_fraction: "1",
      },
    },
    frames: "120",
    scenario: "FLASH_MOVE",
    stressEnabled: false,
    stressKind: "CORRELATED_SELLOFF",
    onset: "30",
    duration: "60",
    recovery: "STEP_WINDOW",
    stressFields: {
      btc_decline_fraction: "0.06",
      eth_transmission: "1.5",
      sol_transmission: "2",
      propagation_lag_frames: "0",
      bid_depth_multiplier: "0.1",
      ask_depth_multiplier: "0.2",
      spread_multiplier: "3",
      reference_source: "redstone",
      reference_mode: "MISSING",
      reference_divergence_fraction: "0.1",
      concentration_decline_fraction: "0.1",
    },
    declines: { BTC: "0.06", ETH: "0.08", SOL: "0.1" },
    funding: { BTC: "0.001", ETH: "0.001", SOL: "0.001" },
  };
}
// Exact fixed-point input checks only. Backend remains accounting and fingerprint authority.
export function exactInput(s: string): bigint | null {
  if (s.length > 80 || !/^\d+(?:\.\d{1,18})?$/.test(s)) return null;
  const [a, b = ""] = s.split(".");
  return BigInt(a) * 10n ** 18n + BigInt(b.padEnd(18, "0"));
}
export function allocationError(d: FormDraft): string | null {
  const total = exactInput(d.budget.total_equity_quote),
    reserve = exactInput(d.budget.minimum_reserve_quote);
  if (total === null || total <= 0n || reserve === null)
    return "Enter exact nonnegative USDC amounts, with positive total capital and at most 18 decimal places.";
  if (total > 10n ** 30n)
    return "Total capital exceeds the 1 trillion USDC research bound.";
  if (
    d.allocations.length < 1 ||
    d.allocations.length > 3 ||
    new Set(d.allocations.map((a) => a.market)).size !== d.allocations.length
  )
    return "Select one to three unique markets.";
  let allocated = 0n;
  for (const a of d.allocations) {
    const n = exactInput(a.allocated_equity_quote);
    if (!markets.includes(a.market) || n === null || n <= 0n)
      return "Each selected BTC, ETH or SOL market needs a positive exact allocation.";
    allocated += n;
  }
  if (allocated > total) return "Allocations exceed total portfolio capital.";
  if (total - allocated < reserve)
    return "Insufficient reserve: reduce allocations or the minimum reserve.";
  return null;
}
function integer(s: string, min: number, max: number) {
  if (!/^\d{1,6}$/.test(s) || Number(s) < min || Number(s) > max)
    throw new Error(`Enter a whole number from ${min} to ${max}.`);
  return Number(s);
}
export function draftRequest(d: FormDraft): PortfolioDraft {
  const error = allocationError(d);
  if (error) throw new Error(error);
  const selected = markets.filter((m) =>
      d.allocations.some((a) => a.market === m),
    ),
    f = d.stressFields;
  let assumptions: Record<string, unknown> = {};
  if (d.stressKind === "CORRELATED_SELLOFF")
    assumptions = {
      price_shocks: selected.map((m) => ({
        market: m,
        decline_fraction: d.declines[m],
      })),
    };
  if (d.stressKind === "BTC_LED_VOLATILITY")
    assumptions = {
      btc_decline_fraction: f.btc_decline_fraction,
      ...Object.fromEntries(
        selected
          .filter((m) => m !== "BTC")
          .map((m) => [
            `${m.toLowerCase()}_transmission`,
            f[`${m.toLowerCase()}_transmission`],
          ]),
      ),
      propagation_lag_frames: integer(f.propagation_lag_frames, 0, 300),
    };
  if (d.stressKind === "LIQUIDITY_SHOCK")
    assumptions = {
      bid_depth_multiplier: f.bid_depth_multiplier,
      ask_depth_multiplier: f.ask_depth_multiplier,
      spread_multiplier: f.spread_multiplier,
    };
  if (d.stressKind === "FUNDING_STRESS")
    assumptions = {
      funding_shocks: selected.map((m) => ({
        market: m,
        adjustment: d.funding[m],
      })),
    };
  if (d.stressKind === "ORACLE_DEGRADATION")
    assumptions = {
      reference_source: f.reference_source,
      reference_mode: f.reference_mode,
      ...(f.reference_mode === "DIVERGENT"
        ? { reference_divergence_fraction: f.reference_divergence_fraction }
        : {}),
    };
  if (d.stressKind === "CONCENTRATION_STRESS")
    assumptions = {
      concentration_decline_fraction: f.concentration_decline_fraction,
    };
  return {
    budget: d.budget,
    allocations: [...d.allocations].sort(
      (a, b) => markets.indexOf(a.market) - markets.indexOf(b.market),
    ),
    risk_limits: d.risk_limits,
    risk_policy: d.risk_policy,
    frames: integer(d.frames, 2, 3000),
    scenario: d.scenario,
    strategy: {
      ...d.strategy,
      levels_per_side: integer(d.strategy.levels_per_side, 1, 50),
    },
    paper: {
      ...d.paper,
      execution: {
        ...d.paper.execution,
        order_latency_ms: integer(d.paper.execution.order_latency_ms, 0, 60000),
        cancel_latency_ms: integer(
          d.paper.execution.cancel_latency_ms,
          0,
          60000,
        ),
      },
    },
    stress: d.stressEnabled
      ? {
          scenario_type: d.stressKind,
          selected_markets: selected,
          onset_frame: integer(d.onset, 0, 1499),
          duration_frames: integer(d.duration, 1, 1500),
          recovery_profile: d.recovery,
          assumptions,
        }
      : null,
  };
}
const fp = (v: unknown) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
function matchesDraft(actual: unknown, expected: unknown): boolean {
  if (
    typeof expected === "string" &&
    /^-?\d+(?:\.\d{1,18})?$/.test(expected) &&
    typeof actual === "string" &&
    /^-?\d+(?:\.\d{1,18})?$/.test(actual)
  ) {
    const signed = (v: string) => {
      const sign = v.startsWith("-") ? -1n : 1n;
      return sign * exactInput(v.replace("-", ""))!;
    };
    return signed(actual) === signed(expected);
  }
  if (Array.isArray(expected))
    return (
      Array.isArray(actual) &&
      expected.length === actual.length &&
      expected.every((v, i) => matchesDraft(actual[i], v))
    );
  if (expected && typeof expected === "object")
    return (
      !!actual &&
      typeof actual === "object" &&
      Object.entries(expected).every(([k, v]) =>
        matchesDraft((actual as Record<string, unknown>)[k], v),
      )
    );
  return actual === expected;
}
function authority(v: {
  simulated: boolean;
  execution_mode: string;
  read_only: boolean;
  authority: string;
}) {
  return (
    v.simulated === true &&
    v.execution_mode === "PAPER" &&
    v.read_only === true &&
    v.authority === "NONE"
  );
}
export function checkedPreview(p: Preview, d: PortfolioDraft): Preview {
  if (
    !p ||
    p.contract_version !== "phase175-preview-v1" ||
    !authority(p) ||
    !authority(p.config) ||
    !fp(p.config_fingerprint) ||
    p.config.allocations.length !== d.allocations.length ||
    p.config.scenarios.length !== d.allocations.length ||
    exactInput(p.config.budget.total_equity_quote) !==
      exactInput(d.budget.total_equity_quote) ||
    d.allocations.some(
      (a) =>
        !p.config.allocations.some(
          (b) =>
            a.market === b.market &&
            exactInput(a.allocated_equity_quote) ===
              exactInput(b.allocated_equity_quote),
        ),
    ) ||
    !matchesDraft(p.config.risk_limits, d.risk_limits) ||
    !matchesDraft(p.config.budget, d.budget) ||
    !matchesDraft(p.risk_policy, d.risk_policy) ||
    !matchesDraft(p.stress, d.stress) ||
    p.config.scenarios.some(
      (s) =>
        !fp(s.captured.market_profile_fingerprint) ||
        !fp(s.captured.fingerprint) ||
        s.frames !== d.frames ||
        s.scenario !== d.scenario,
    )
  )
    throw new Error(
      "Portfolio preview identity or authority rejected. Validate again.",
    );
  for (const scenario of p.config.scenarios) {
    try {
      const c = JSON.parse(scenario.captured.canonical_json);
      if (
        c.strategy?.execution_mode !== "PAPER" ||
        c.strategy?.market !== scenario.market ||
        c.market_profile?.profile_fingerprint !==
          scenario.captured.market_profile_fingerprint ||
        c.strategy.amm_model !== d.strategy.amm_model ||
        c.strategy.levels_per_side !== d.strategy.levels_per_side ||
        !matchesDraft(c.simulation.execution, d.paper.execution) ||
        !matchesDraft(
          c.simulation.initial_equity_quote,
          d.allocations.find((a) => a.market === scenario.market)
            ?.allocated_equity_quote,
        )
      )
        throw new Error();
    } catch {
      throw new Error(
        "Portfolio captured assumptions rejected. Validate again.",
      );
    }
  }
  return p;
}
export function checkedTerminal(
  r: TerminalResult,
  q: TerminalRequest,
): TerminalResult {
  const fail = () => {
    throw new Error(
      "Portfolio evidence identity, eligibility or authority rejected. Run again.",
    );
  };
  if (
    !r ||
    r.contract_version !== "phase175-terminal-v1" ||
    !authority(r) ||
    r.config_fingerprint !== q.config_fingerprint ||
    r.mode !== q.mode ||
    !fp(r.evidence_fingerprint) ||
    (q.mode === "STRESS") !== !!r.stressed
  )
    fail();
  for (const leg of [r.baseline, ...(r.stressed ? [r.stressed] : [])]) {
    if (!leg) fail();
    const known = ["HALT", "REDUCE", "WARN", "NORMAL"].find(
      (state) => leg.risk.checks.some((c) => c.state === state),
    ) ?? "NORMAL";
    const decision = leg.risk.outcome === "BLOCKED"
      ? (known === "HALT" ? "HALT" : null) : known;
    if (
      !leg ||
      leg.status !== "COMPLETED" ||
      !fp(leg.analysis_fingerprint) ||
      leg.risk.operational_authority !== "NONE" ||
      leg.risk.historical_orders_prevented !== false ||
      !["ASSESSED", "BLOCKED"].includes(leg.risk.outcome) ||
      !["NORMAL", "WARN", "REDUCE", "HALT", null].includes(leg.risk.decision) ||
      (leg.risk.outcome === "ASSESSED" && !leg.risk.decision) ||
      leg.risk.decision !== decision ||
      (leg.risk.outcome === "ASSESSED" && leg.risk.checks.some((c) => c.state === "UNAVAILABLE")) ||
      (leg.risk.outcome === "BLOCKED" &&
        leg.risk.decision !== null &&
        leg.risk.decision !== "HALT") ||
      leg.markets.length !== q.config.scenarios.length ||
      new Set(leg.markets.map((m) => m.market)).size !== leg.markets.length ||
      !matchesDraft(leg.risk.policy, q.risk_policy) ||
      leg.markets.some(
        (m) =>
          m.market_profile_fingerprint !==
          q.config.scenarios.find((s) => s.market === m.market)?.captured
            .market_profile_fingerprint,
      )
    )
      fail();
    const c = leg.charts;
    if (
      c.analysis_fingerprint !== leg.analysis_fingerprint ||
      c.accounting_fingerprint !== leg.accounting.evidence_fingerprint ||
      c.temporal_fingerprint !== leg.temporal.evidence_fingerprint ||
      c.points.length > 120 ||
      c.native_evidence_fingerprints.join() !==
        leg.temporal.clocks.map((k) => k.native_evidence_fingerprint).join()
    )
      fail();
    if (c.status === "AVAILABLE") {
      if (
        leg.temporal.classification !== "MODELED_ALIGNED" ||
        c.points.length < 2 ||
        c.points[0].sequence !== 1 ||
        c.points.at(-1)?.sequence !== c.source_count ||
        c.sampled !== (c.points.length < c.source_count) ||
        leg.temporal.clocks.some((k) => !k.complete || k.frames !== c.source_count) ||
        !matchesDraft(c.points.at(-1)?.equity_quote, leg.accounting.equity_quote) ||
        !matchesDraft(c.points.at(-1)?.pnl_quote, leg.accounting.pnl_quote) ||
        c.equity_series_fingerprint !==
          leg.accounting.drawdown?.equity_series_fingerprint
      )
        fail();
      c.points.forEach((p, i) => {
        if (
          !Number.isSafeInteger(p.sequence) ||
          !Number.isFinite(Date.parse(p.timestamp)) ||
          ![p.equity_quote, p.pnl_quote, p.drawdown_fraction].every(
            (v) => typeof v === "string" && /^-?\d+(?:\.\d+)?$/.test(v),
          ) ||
          (i > 0 &&
            (p.sequence <= c.points[i - 1].sequence ||
              Date.parse(p.timestamp) <= Date.parse(c.points[i - 1].timestamp)))
        )
          fail();
      });
    } else if (c.status !== "UNAVAILABLE" || c.points.length) fail();
  }
  return r;
}
export function riskState(r: RiskReport): string {
  return r.outcome === "BLOCKED"
    ? `BLOCKED${r.decision ? " · known " + r.decision : ""}`
    : (r.decision ?? "Unavailable");
}
export function decimalDisplay(
  v: string | null | undefined,
  unit = "",
): string {
  if (typeof v !== "string" || v.length > 160 || !/^-?\d+(?:\.\d+)?$/.test(v))
    return "Unavailable";
  const [a, b = ""] = v.split(".");
  return (
    a.replace(/\B(?=(\d{3})+(?!\d))/g, ",") +
    (b ? "." + b.slice(0, 6).replace(/0+$/, "") : "").replace(/\.$/, "") +
    (unit ? " " + unit : "")
  );
}
export function fractionDisplay(v: string | null | undefined): string {
  if (typeof v !== "string" || !/^-?\d+(?:\.\d+)?$/.test(v))
    return "Unavailable";
  const sign = v.startsWith("-") ? "-" : "",
    [a, b = ""] = v.replace("-", "").split(".");
  return decimalDisplay(
    sign +
      (BigInt(a) * 100n + BigInt(b.padEnd(2, "0").slice(0, 2))).toString() +
      "." +
      b.slice(2).padEnd(4, "0"),
    "%",
  );
}
