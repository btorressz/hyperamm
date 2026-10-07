import type { TerminalState, HistoryRange } from "../types";
import { useDisplayStore } from "../stores/display";
import { useTerminalStore } from "../stores/terminal";
import { SystemHealth } from "../components/SystemHealth";
import { Panel, Metrics } from "../components/TerminalPrimitives";
export function Settings({ t }: { t: TerminalState }) {
  const d = useDisplayStore(),
    s = useTerminalStore();
  return (
    <div className="stack">
      <h1>Settings & diagnostics</h1>
      <Panel title="Display preferences" meta="Saved in this browser">
        <div className="formGrid">
          <label>
            Layout density
            <select
              value={d.dense ? "dense" : "comfortable"}
              onChange={(e) => d.setDense(e.target.value === "dense")}
            >
              <option value="comfortable">Comfortable</option>
              <option value="dense">Dense</option>
            </select>
          </label>
          <label>
            Default chart range
            <select
              value={d.defaultRange}
              onChange={(e) =>
                d.setDefaultRange(e.target.value as HistoryRange)
              }
            >
              {["session", "1m", "5m", "15m", "1h"].map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </label>
          <label>
            History view size
            <select
              value={d.historySize}
              onChange={(e) => d.setHistorySize(Number(e.target.value))}
            >
              {[100, 300, 600, 1000].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </label>
        </div>
        <p className="muted panelNote">
          Unavailable ranges stay disabled until enough session history exists.
        </p>
      </Panel>
      <Panel title="Runtime diagnostics" meta="Safe public state">
        <Metrics
          items={[
            [
              "Market / execution",
              `${t.market.mode} / ${t.strategy.config.execution_mode}`,
            ],
            [
              "Signed TESTNET enabled",
              t.diagnostics.testnet_enabled ? "ENABLED" : "DISABLED",
            ],
            [
              "RedStone transport",
              t.references?.evidence.REDSTONE?.transport ?? "Unavailable",
            ],
            ["Contract", t.contract_version],
            ["Last sequence", t.sequence],
            ["WebSocket", s.wsState.toUpperCase()],
            ["Reconnect attempts", s.reconnectAttempts],
            [
              "Firewall",
              t.diagnostics.reference_firewall_enabled ? "ENABLED" : "DISABLED",
            ],
          ]}
        />
      </Panel>
      <SystemHealth t={t} />
    </div>
  );
}
