import { useTerminalStore } from "../stores/terminal";
import type { TerminalState } from "../types";
import { TerminalKpis } from "../components/TerminalKpis";
import { PriceLiquidityChart } from "../components/PriceLiquidityChart";
import { OrderBook } from "../components/OrderBook";
import { QuickStrategyControl } from "../components/QuickStrategyControl";
import { LiquidityDistributionChart } from "../components/LiquidityDistributionChart";
import { StrategyAttribution } from "../components/StrategyAttribution";
import { InventorySkewChart } from "../components/InventorySkewChart";
import { RecentExecution } from "../components/RecentExecution";
import { SystemHealth } from "../components/SystemHealth";
import { Panel, Metrics } from "../components/TerminalPrimitives";
import { number } from "../utils/format";
export function Dashboard({ t }: { t: TerminalState }) {
  const a = t.agents;
  const current = useTerminalStore(s => s.wsState === "connected");
  return (
    <>
      <div className="operatorTitle">
        <div>
          <span className="eyebrow">OPERATOR OVERVIEW</span>
          <h1>Liquidity terminal</h1>
        </div>
        <span className="sessionLabel">
          {t.market.mode} ·{" "}
          {t.strategy.config.execution_mode === "PAPER"
            ? "PAPER / SIMULATED"
            : "GUARDED TESTNET"}{" "}
          · {current ? "current session" : "historical snapshot"}
        </span>
      </div>
      <div className="dashboardTop">
        <PriceLiquidityChart t={t} />
        <OrderBook m={t.market} />
        <QuickStrategyControl t={t} />
      </div>
      <TerminalKpis t={t} />
      <div className="dashboardSecondary">
        <LiquidityDistributionChart t={t} />
        <StrategyAttribution t={t} />
        <InventorySkewChart t={t} />
      </div>
      <div className="dashboardBottom">
        <Panel title="Supervisory agents" meta="Phase 9 · recommendations">
          <Metrics
            items={[
              ["Regime", a.regime?.state ?? "Unavailable"],
              ["Toxic flow", a.toxic_flow?.state ?? "Unavailable"],
              [
                "Execution quality",
                a.execution_quality?.state ?? "Unavailable",
              ],
              [
                "Supervisor spread",
                number(a.supervisor?.spread_multiplier) + "×",
              ],
            ]}
          />
        </Panel>
        <RecentExecution t={t} />
        <SystemHealth t={t} compact />
      </div>
    </>
  );
}
