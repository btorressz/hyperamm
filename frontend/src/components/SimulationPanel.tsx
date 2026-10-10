import type { SimulationMetrics } from "../types";
import { Panel, Metrics } from "./TerminalPrimitives";
import { StateDistribution } from "./StateDistribution";
import { accountingValue } from "../utils/researchEvidence";
import { metricValue } from "../utils/simulationResearch";
export function researchMetric(key: string, value: unknown) {
  const { fraction, unit } = metricValue(key),
    v = accountingValue(value, fraction);
  return v === "Unavailable" || fraction
    ? v
    : `${v}${unit === "%" ? "%" : unit ? " " + unit : ""}`;
}
export function SimulationPanel({ m }: { m: SimulationMetrics }) {
  const items = (definitions: Array<[string, keyof SimulationMetrics]>) =>
    definitions.map(([label, key]): [string, string] => [
      label,
      researchMetric(key, m[key]),
    ]);
  return (
    <Panel
      title="Simulation Metrics"
      meta={`SIMULATED · ${m.frame_count} frames · NO LIVE ORDERS`}
    >
      <Metrics
        items={items([
          ["Starting equity", "starting_equity"],
          ["Ending equity", "ending_equity"],
          ["Session PnL", "session_pnl"],
          ["Return", "return_pct"],
          ["Maximum drawdown", "max_drawdown_pct"],
          ["Ending inventory", "ending_inventory_base"],
        ])}
      />
      <details className="researchInset">
        <summary>Execution, inventory and order lifecycle metrics</summary>
        <h3>Performance breakdown</h3>
        <Metrics
          items={items([
            ["Realized PnL", "realized_pnl"],
            ["Unrealized PnL", "unrealized_pnl"],
          ])}
        />
        <h3>Execution evidence</h3>
        <Metrics
          items={items([
            ["Fills", "fill_count"],
            ["Buy fills", "buy_fill_count"],
            ["Sell fills", "sell_fill_count"],
            ["Quoted notional", "quoted_notional"],
            ["Filled notional", "filled_notional"],
            ["Fill activity ratio", "fill_activity_ratio"],
            ["Spread capture", "mean_spread_capture_bps"],
            ["Mature markout", "mean_mature_markout_bps"],
            ["Adverse fill rate", "adverse_fill_rate"],
          ])}
        />
        <h3>Inventory and risk</h3>
        <Metrics
          items={items([
            ["Maximum absolute inventory", "max_abs_inventory_base"],
            ["Maximum inventory utilization", "max_inventory_utilization"],
            ["Risk HALT fraction", "risk_halt_fraction"],
          ])}
        />
        <h3>Order lifecycle</h3>
        <Metrics
          items={items([
            ["KEEP", "keep_count"],
            ["CREATE", "create_count"],
            ["REPLACE", "replace_count"],
            ["CANCEL", "cancel_count"],
            ["Reconciliation churn", "reconciliation_churn_ratio"],
          ])}
        />
      </details>
      <details className="researchInset">
        <summary>Inspect simulated state observations</summary>
        <div className="grid twoColumns">
          <StateDistribution counts={m.risk_state_counts} label="Risk states" />
          <StateDistribution
            counts={m.agent_regime_counts}
            label="Agent regimes"
          />
          <StateDistribution
            counts={m.toxic_flow_state_counts}
            label="Toxic-flow states"
          />
          <StateDistribution
            counts={m.execution_quality_state_counts}
            label="Execution-quality states"
          />
        </div>
      </details>
      <p className="muted panelNote">
        Return is reported in percent; drawdown and utilization fractions are
        converted once for display. Missing markouts remain unavailable. Full
        Decimal values are preserved; chart coordinates alone use floating-point
        display values.
      </p>
    </Panel>
  );
}
