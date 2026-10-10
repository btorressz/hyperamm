import type { SimulationResult } from "../types";
export const optimizationPresets = {
  Balanced: {
    description:
      "Investigate liquidity ladder density, concentration and regime widening.",
    strategy_grid: {
      levels_per_side: [6, 8],
      concentration_factor: ["6", "10"],
    },
    agent_grid: { regime_spread_strength: ["0.3", "0.5"] },
  },
  Inventory: {
    description:
      "Investigate inventory price skew and inventory size reduction.",
    strategy_grid: {
      max_inventory_price_skew_bps: ["15", "25"],
      inventory_size_skew_strength: ["0.5", "0.9"],
    },
    agent_grid: {},
  },
  AdverseFlow: {
    description:
      "Investigate volatility widening and adverse-flow thresholds / size reduction.",
    strategy_grid: { volatility_spread_strength: ["0.8", "1.2"] },
    agent_grid: {
      toxic_flow_adverse_markout_bps: ["2", "4"],
      toxic_flow_size_strength: ["0.4", "0.7"],
    },
  },
} as const;
export const trainingScenarios = ["TREND_UP", "TREND_DOWN", "HIGH_VOLATILITY"];
export const validationScenarios = ["MEAN_REVERTING", "FLASH_MOVE"];
export function frameError(value: string) {
  const n = Number(value);
  return !value.trim() || !Number.isInteger(n) || n < 2 || n > 1000
    ? "Enter a whole frame count from 2 to 1000. Grid search uses at most 250 frames per scenario."
    : "";
}
export function presetCandidateCount(preset: keyof typeof optimizationPresets) {
  const p = optimizationPresets[preset];
  return [
    ...Object.values(p.strategy_grid),
    ...Object.values(p.agent_grid),
  ].reduce((n, v) => n * v.length, 1);
}
export type RunConfiguration = {
  kind: "run" | "opt";
  scenario: string;
  frames: number;
  preset: keyof typeof optimizationPresets;
};
// Synchronous admission closes the double-click window before React rerenders.
export class ResearchRunGate {
  private generation = 0;
  private active: number | null = null;
  start() {
    if (this.active !== null) return null;
    this.active = ++this.generation;
    return this.active;
  }
  current(token: number) {
    return token === this.active && token === this.generation;
  }
  finish(token: number) {
    if (!this.current(token)) return false;
    this.active = null;
    return true;
  }
  retire() {
    this.generation++;
    this.active = null;
  }
}
export function traceFrames(trace: SimulationResult["trace"], limit = 250) {
  const unique = new Map<number, SimulationResult["trace"][number]>();
  for (const p of trace) {
    if (
      p &&
      Number.isSafeInteger(p.sequence) &&
      p.sequence >= 0 &&
      !unique.has(p.sequence)
    )
      unique.set(p.sequence, p);
  }
  // Sequence is the backend frame identity; timestamps (including invalid/missing ones) never merge frames.
  return [...unique.values()]
    .sort((a, b) => a.sequence - b.sequence)
    .slice(0, Math.max(0, Math.min(250, limit)));
}
export function metricValue(key: string) {
  // return_pct is already percent; these named backend fields are fractional.
  const fractions = new Set([
    "max_drawdown_pct",
    "drawdown_pct",
    "max_inventory_utilization",
    "fill_activity_ratio",
    "adverse_fill_rate",
    "reconciliation_churn_ratio",
    "risk_halt_fraction",
    "mean_max_drawdown_pct",
    "worst_drawdown_pct",
    "mean_churn_ratio",
    "mean_halt_fraction",
    "risk_normal_fraction",
    "risk_widen_fraction",
    "risk_reduce_fraction",
    "mean_adverse_fill_rate",
  ]);
  return {
    fraction: fractions.has(key),
    unit: key.endsWith("_bps")
      ? "bps"
      : key.includes("inventory_base")
        ? "base"
        : key.includes("equity") ||
            key.includes("pnl") ||
            key.includes("notional")
          ? "quote"
          : key.endsWith("return_pct")
            ? "%"
            : "",
  };
}
