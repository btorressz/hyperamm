import { useState } from "react";
import { api } from "../api/client";
import type { TerminalState } from "../types";
import { useTerminalStore } from "../stores/terminal";
import { terminalObservationIsCurrent } from "../utils/freshness";
import { Panel, Metrics } from "./TerminalPrimitives";
import { quantity } from "../utils/format";
export function ControlActions({
  t,
  historical,
  compact = false,
}: {
  t: TerminalState;
  historical: boolean;
  compact?: boolean;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const action = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const current = () => {
    const { terminal, wsState } = useTerminalStore.getState();
    return terminalObservationIsCurrent(terminal, wsState) ? terminal : null;
  };
  return (
    <>
      <div className={`actions ${compact ? "compactActions" : ""}`}>
        <button
          className="goodBtn"
          disabled={historical || busy || t.strategy.running || t.risk.kill_switch_active}
          onClick={() => {
            const snapshot = current();
            if (snapshot && !snapshot.strategy.running && !snapshot.risk.kill_switch_active) void action(api.start);
          }}
        >
          Start
        </button>
        <button
          disabled={busy || (!historical && !t.strategy.running)}
          onClick={() => action(api.stop)}
        >
          Stop
        </button>
        <button
          className="dangerBtn"
          aria-label="Immediately activate manual kill switch"
          disabled={!historical && t.risk.kill_switch_active}
          onClick={() => action(api.kill)}
        >
          Kill
        </button>
        <button
          disabled={historical || busy || !t.risk.kill_switch_active}
          onClick={() => {
            if (current()?.risk.kill_switch_active && window.confirm("Resume through backend risk checks?") &&
                current()?.risk.kill_switch_active)
              void action(api.resume);
          }}
        >
          Resume
        </button>
      </div>
      {error && (
        <p className="inlineError" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
export function QuickStrategyControl({ t, historical }: { t: TerminalState; historical: boolean }) {
  const c = t.strategy.config;
  return (
    <Panel
      title="Strategy control"
      meta={`${historical ? "LAST SNAPSHOT · " : ""}${t.strategy.running ? "RUNNING" : "STOPPED"}`}
    >
      <Metrics
        items={[
          [
            "Execution",
            c.execution_mode === "TESTNET"
              ? "GUARDED TESTNET"
              : c.execution_mode,
          ],
          [
            "Model",
            c.amm_model === "CONSTANT_PRODUCT"
              ? "Constant product"
              : "Concentrated",
          ],
          ["Levels / side", c.levels_per_side],
          ["Inventory target", quantity(c.target_inventory_base)],
        ]}
      />
      <ControlActions t={t} historical={historical} compact />
      <p className="muted panelNote">Advanced configuration in AMM Settings.</p>
    </Panel>
  );
}
