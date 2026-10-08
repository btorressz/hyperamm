import type { TerminalState } from "../types";
import { useTerminalHistory } from "../hooks/useTerminalHistory";
import { HistoryChart, type HistoryLine } from "../components/HistoryChart";
import { Panel, Metrics, Empty } from "../components/TerminalPrimitives";
import { money, percentage, bps, quantity } from "../utils/format";
const equityLines: HistoryLine[] = [
  { key: "equity", label: "Equity", color: "#4cd4a1" },
  { key: "peak_equity", label: "Peak equity", color: "#819bbc" },
];
const pnlLines: HistoryLine[] = [
  { key: "net_pnl", label: "Session net PnL", color: "#77aaff" },
];
const exposureLines: HistoryLine[] = [
  { key: "position_base", label: "Position base", color: "#b69aff" },
];
const drawdownLines: HistoryLine[] = [
  { key: "drawdown_pct", label: "Drawdown fraction", color: "#f0788a" },
  {
    key: "capital_utilization",
    label: "Capital utilization fraction",
    color: "#e8b968",
  },
];
export function SessionCharts() {
  const h = useTerminalHistory();
  return (
    <>
      {h.isError ? (
        <p className="inlineError" role="alert">
          History unavailable: {String(h.error)}
        </p>
      ) : h.isPending ? (
        <Empty>Loading session observations…</Empty>
      ) : (
        <>
          <p className="muted">
            In-memory session · {h.data.retained_points} observations ·{" "}
            {Math.round(h.data.retained_seconds)} seconds retained. Missing
            evidence creates gaps.
          </p>
          <div className="grid twoColumns">
            {[
              ["Equity & high-water mark", equityLines],
              ["Net PnL", pnlLines],
              ["Inventory exposure", exposureLines],
              ["Drawdown & capital utilization", drawdownLines],
            ].map(([title, lines]) => (
              <Panel
                key={String(title)}
                title={String(title)}
                meta="Backend observation time"
              >
                <HistoryChart
                  points={h.data.points}
                  fitKey={`${h.data.session_id}:${h.data.range}`}
                  lines={lines as HistoryLine[]}
                />
              </Panel>
            ))}
          </div>
        </>
      )}
    </>
  );
}
export function Analytics({ t }: { t: TerminalState }) {
  const h = useTerminalHistory(),
    e = t.agents.execution_quality?.metrics,
    tox = t.agents.toxic_flow?.metrics;
  const distribution = (key: "risk_state" | "agent_regime") => {
    const counts = new Map<string, number>();
    for (const p of h.data?.points ?? []) {
      const state = p[key];
      if (state) counts.set(state, (counts.get(state) ?? 0) + 1);
    }
    return (
      [...counts].map(([k, v]) => `${k}: ${v}`).join(" · ") || "No observations"
    );
  };
  return (
    <div className="stack">
      <h1>Session analytics</h1>
      <p className="sessionLabel">
        LIVE SESSION METRICS · {t.market.mode} ·{" "}
        {t.vault.simulated ? "SIMULATED" : ""} {t.vault.mode}
      </p>
      <SessionCharts />
      <Panel
        title="Execution & liquidity metrics"
        meta="Offline simulation metrics remain separate"
      >
        <Metrics
          items={[
            ["Net PnL", money(t.vault.net_pnl_quote)],
            ["Current drawdown", percentage(t.vault.drawdown_pct)],
            ["Current exposure", quantity(t.vault.position_base)],
            ["Fill count", t.execution_summary.fill_count ?? "Unavailable"],
            ["Filled notional", money(t.execution_summary.filled_notional)],
            ["Spread capture", bps(e?.average_spread_capture_bps)],
            ["Mature markout", bps(e?.average_mature_markout_bps)],
            [
              "Adverse fill rate",
              tox && tox.matured_fills > 0
                ? percentage(tox.adverse_fill_rate)
                : "Unavailable",
            ],
            ["Reconciliation churn", percentage(e?.reconciliation_churn_ratio)],
          ]}
        />
      </Panel>
      <Panel
        title="Retained observation distributions"
        meta="Sample counts; not trading decisions"
      >
        <Metrics
          items={[
            ["Risk states", distribution("risk_state")],
            ["Agent regimes", distribution("agent_regime")],
          ]}
        />
      </Panel>
    </div>
  );
}
