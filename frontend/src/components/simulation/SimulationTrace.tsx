import type { SimulationResult } from "../../types";
import { HistoryChart, type HistoryLine } from "../HistoryChart";
import { Panel, Empty } from "../TerminalPrimitives";
import { traceFrames } from "../../utils/simulationResearch";
const views: Array<[string, HistoryLine[]]> = [
  [
    "Simulated equity",
    [{ key: "equity", label: "Equity", color: "#4cd4a1", unit: "quote" }],
  ],
  [
    "Simulated session PnL",
    [
      {
        key: "session_pnl",
        label: "Session PnL",
        color: "#4cd4a1",
        unit: "quote",
        signed: true,
      },
    ],
  ],
  [
    "Market / perpetual references",
    [
      { key: "mid", label: "Mid", color: "#77aaff", unit: "quote / base" },
      { key: "mark", label: "Mark", color: "#b69aff", unit: "quote / base" },
      {
        key: "oracle",
        label: "Oracle",
        color: "#e8b968",
        unit: "quote / base",
      },
    ],
  ],
  [
    "Simulated inventory",
    [
      {
        key: "inventory_base",
        label: "Inventory",
        color: "#b69aff",
        unit: "base",
        signed: true,
      },
    ],
  ],
  [
    "Simulated drawdown",
    [
      {
        key: "drawdown_pct",
        label: "Drawdown",
        color: "#f0788a",
        percent: true,
      },
    ],
  ],
  [
    "Quote & order activity",
    [
      {
        key: "desired_quote_count",
        label: "Desired",
        color: "#819bbc",
        unit: "count",
      },
      {
        key: "agent_quote_count",
        label: "Agent",
        color: "#b69aff",
        unit: "count",
      },
      {
        key: "authorized_quote_count",
        label: "Authorized",
        color: "#4cd4a1",
        unit: "count",
      },
      {
        key: "open_order_count",
        label: "Open orders",
        color: "#77aaff",
        unit: "count",
      },
    ],
  ],
];
export function SimulationTrace({ result }: { result: SimulationResult }) {
  const points = traceFrames(result.trace);
  return (
    <section aria-label="Simulation trace">
      <h2>Explore simulated frames</h2>
      <p className="muted">
        {points.length} returned trace points shown · requested cap 250 ·{" "}
        {result.metrics.frame_count} simulated frames. Frame index is
        display-only; original backend sequences and timestamps remain
        inspectable. Same-second frames stay distinct; missing values are gaps.
        Separate research runs never concatenate.
      </p>
      {!points.length ? (
        <Empty>No trace points were returned for this run.</Empty>
      ) : (
        <>
          <div className="grid twoColumns">
            {views.map(([title, lines]) => (
              <Panel key={title} title={title} meta="SIMULATED FRAME INDEX">
                <HistoryChart
                  points={points}
                  lines={lines}
                  axis="frame"
                  fitKey={result.run_fingerprint}
                />
              </Panel>
            ))}
          </div>
          <Panel
            title="Frame state evidence"
            meta="Observed states; no causal attribution"
          >
            <details className="researchInset">
              <summary>Inspect risk and regime transitions</summary>
              <div
                className="tableWrap"
                tabIndex={0}
                aria-label="Simulated frame states"
              >
                <table>
                  <thead>
                    <tr>
                      <th>Frame</th>
                      <th>Original timestamp</th>
                      <th>Risk</th>
                      <th>Agent regime</th>
                      <th>Toxic flow</th>
                      <th>Execution quality</th>
                      <th>Reference confidence</th>
                      <th>Fills</th>
                    </tr>
                  </thead>
                  <tbody>
                    {points.map((p) => (
                      <tr key={p.sequence}>
                        <td>{p.sequence}</td>
                        <td>{p.timestamp}</td>
                        <td>{p.risk_state ?? "Unavailable"}</td>
                        <td>{p.agent_regime ?? "Unavailable"}</td>
                        <td>{p.toxic_flow_state ?? "Unavailable"}</td>
                        <td>{p.execution_quality_state ?? "Unavailable"}</td>
                        <td>{p.reference_confidence ?? "Unavailable"}</td>
                        <td>{p.fill_count ?? "Unavailable"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </Panel>
        </>
      )}
    </section>
  );
}
