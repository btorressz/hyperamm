import { useMemo, useState } from "react";
import type {
  TerminalLeg,
  TerminalResult,
} from "../../types/portfolioResearch";
import {
  decimalDisplay as value,
  fractionDisplay as percent,
  riskLabels,
  riskState,
} from "../../utils/portfolioResearch";
import { Panel, Metrics, Empty, StatusBanner } from "../TerminalPrimitives";
import { HistoryChart, type HistoryLine } from "../HistoryChart";
export function PortfolioRiskPanel({
  leg,
  label,
}: {
  leg: TerminalLeg;
  label: string;
}) {
  const r = leg.risk;
  return (
    <Panel title={`${label} research risk`} meta={riskState(r)}>
      <p
        className={`portfolioRisk risk${r.outcome === "BLOCKED" ? "BLOCKED" : r.decision}`}
      >
        {riskState(r)}
      </p>
      <p>
        Assessment availability: {r.outcome}.{" "}
        {r.outcome === "BLOCKED"
          ? "Required evidence or evaluation eligibility is unavailable."
          : "Post-execution hypothetical assessment completed."}
      </p>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Research limit</th>
              <th>Observed</th>
              <th>Ceiling</th>
              <th>Decision</th>
            </tr>
          </thead>
          <tbody>
            {r.checks.map((c) => (
              <tr key={c.limit}>
                <td>{riskLabels[c.limit]}</td>
                <td>{value(c.observed)}</td>
                <td>{value(c.ceiling)}</td>
                <td>{c.state}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul>
        {r.reasons.map((reason) => (
          <li key={reason}>{reason.replaceAll("_", " ")}</li>
        ))}
      </ul>
      <p>
        Source evidence: {leg.temporal.classification}. HALT means a known hard
        research condition; BLOCKED means incomplete evaluation. A known HALT
        can remain visible alongside BLOCKED.
      </p>
      <StatusBanner>
        REDUCE and HALT are post-execution research assessments. They do not
        cancel operational orders or prevent PAPER orders already simulated.
      </StatusBanner>
    </Panel>
  );
}
export function PortfolioMetrics({
  leg,
  label,
}: {
  leg: TerminalLeg;
  label: string;
}) {
  const a = leg.accounting,
    x = leg.exposure;
  return (
    <Panel title={`${label} Portfolio Analytics`} meta={a.status}>
      <Metrics
        items={[
          [
            "Initial hypothetical capital",
            value(a.initial_capital_quote, "USDC"),
          ],
          ["Allocated capital", value(a.allocated_capital_quote, "USDC")],
          ["Unallocated reserve", value(a.reserve_quote, "USDC")],
          ["Ending equity", value(a.equity_quote, "USDC")],
          ["Portfolio PnL", value(a.pnl_quote, "USDC")],
          ["Session loss", value(a.session_loss_quote, "USDC")],
          ["Gross exposure", value(x.gross_exposure_quote, "USDC")],
          ["Signed net exposure", value(x.net_exposure_quote, "USDC")],
          [
            "Capital allocation utilization",
            percent(a.capital_allocation_utilization),
          ],
          ["Gross notional utilization", percent(x.gross_notional_utilization)],
          [
            "Reserved-capital utilization",
            percent(x.reserved_capital_utilization),
          ],
          ["Modeled leverage", value(x.modeled_leverage, "×")],
          ["Market concentration", percent(x.max_inventory_concentration)],
          ["Maximum drawdown", percent(a.drawdown?.max_drawdown_fraction)],
        ]}
      />
      <div className="tableWrap">
        <table>
          <caption>
            Native per-market exposure · independent PAPER positions
          </caption>
          <thead>
            <tr>
              <th>Market</th>
              <th>Position (base asset)</th>
              <th>Mark (USDC/base)</th>
              <th>Signed exposure (USDC)</th>
              <th>Concentration</th>
            </tr>
          </thead>
          <tbody>
            {x.positions.map((p) => (
              <tr key={p.market}>
                <td>{p.market}-PERP</td>
                <td>{value(p.position_base, p.market)}</td>
                <td>{value(p.mark_price_quote)}</td>
                <td>{value(p.signed_exposure_quote)}</td>
                <td>{percent(p.gross_concentration)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
export function PortfolioResearchStatus({
  leg,
  label,
}: {
  leg: TerminalLeg;
  label: string;
}) {
  return (
    <Panel
      title={`${label} evidence status`}
      meta={leg.temporal.classification}
    >
      <Metrics
        items={[
          ["PAPER simulation", leg.status],
          ["Accounting", leg.accounting.status],
          ["Research risk", riskState(leg.risk)],
          ["Chart evidence", leg.charts.status],
          ["Historical synchronization", "UNVERIFIED"],
        ]}
      />
      <p>
        {
          {
            MODELED_ALIGNED:
              "Complete observations share a synthetic modeled clock; eligible accounting, risk and chart evidence is available.",
            FINAL_ONLY:
              "Terminal metrics may be supported. Incomplete native retention prevents complete-history drawdown and charts.",
            INCOMPARABLE:
              "Market scenarios or windows are incompatible. Unsupported aggregate comparisons are suppressed.",
            UNAVAILABLE:
              "Required native evidence is missing or invalid. Unsupported financial output is unavailable.",
          }[leg.temporal.classification]
        }
      </p>
      <p>
        {leg.temporal.reasons.map((s) => s.replaceAll("_", " ")).join(" · ")}
      </p>
    </Panel>
  );
}
export function PortfolioEquityChart({
  leg,
  label,
  metric,
}: {
  leg: TerminalLeg;
  label: string;
  metric: "equity_quote" | "pnl_quote" | "drawdown_fraction";
}) {
  const c = leg.charts;
  const points = useMemo(() => c.points.map((p) => ({ ...p })), [c.points]);
  const lines = useMemo<HistoryLine[]>(
    () => [
      {
        key: metric,
        label: `${label} modeled ${metric === "equity_quote" ? "equity" : metric === "pnl_quote" ? "session PnL" : "drawdown"}`,
        color: label === "Baseline" ? "#4cd4a1" : "#f0b76b",
        unit: metric === "drawdown_fraction" ? undefined : "USDC",
        percent: metric === "drawdown_fraction",
      },
    ],
    [metric, label],
  );
  return (
    <Panel
      title={lines[0].label}
      meta={
        c.status === "AVAILABLE"
          ? `${c.points.length} of ${c.source_count} observations`
          : "UNAVAILABLE"
      }
    >
      {c.status === "AVAILABLE" ? (
        <>
          <HistoryChart
            points={points}
            lines={lines}
            axis="frame"
            fitKey={c.evidence_fingerprint}
          />
          <p>
            {c.sampled
              ? "Deterministically sampled native observations; not a full-resolution historical series."
              : "Complete modeled native observations."}{" "}
            Original sequence and UTC timestamps are retained. Historical
            synchronization is unverified.
          </p>
        </>
      ) : (
        <Empty>
          Chart Unavailable · {c.reason.replaceAll("_", " ")}. No points are
          reconstructed from terminal summaries.
        </Empty>
      )}
    </Panel>
  );
}
const metricLabels: Record<string, string> = {
  equity_quote: "Portfolio equity",
  pnl_quote: "Portfolio PnL",
  gross_exposure_quote: "Gross exposure",
  net_exposure_quote: "Net exposure",
  max_inventory_concentration: "Market concentration",
  capital_allocation_utilization: "Capital allocation utilization",
  gross_notional_utilization: "Gross notional utilization",
  reserved_capital_utilization: "Reserved-capital utilization",
  modeled_leverage: "Modeled leverage",
  funding_quote: "Funding PnL",
  max_drawdown_fraction: "Maximum drawdown",
  session_loss_quote: "Session loss",
};
export function PortfolioStressComparison({
  result,
}: {
  result: TerminalResult;
}) {
  const metrics = result.metrics;
  if (!metrics) return null;
  return (
    <Panel
      title="Baseline versus stressed comparison"
      meta={metrics.temporal_classification}
    >
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th>Baseline</th>
              <th>Stressed</th>
              <th>Difference</th>
            </tr>
          </thead>
          <tbody>
            {metrics.comparisons.map((m) => {
              const fractional = /concentration|utilization|drawdown/.test(
                  m.metric,
                ),
                format = (v: string | null) =>
                  fractional
                    ? percent(v)
                    : value(v, m.metric === "modeled_leverage" ? "×" : "USDC");
              return (
                <tr key={m.metric}>
                  <td>
                    {metricLabels[m.metric] ?? m.metric.replaceAll("_", " ")}
                  </td>
                  <td>{format(m.baseline)}</td>
                  <td>{format(m.stressed)}</td>
                  <td>
                    {m.status === "COMPARABLE"
                      ? (m.difference &&
                        /^[0-9]/.test(m.difference) &&
                        /[1-9]/.test(m.difference)
                          ? "+"
                          : "") + format(m.difference)
                      : "Unavailable"}
                  </td>
                </tr>
              );
            })}
            <tr>
              <td>Risk decision</td>
              <td>{riskState(result.baseline.risk)}</td>
              <td>
                {result.stressed
                  ? riskState(result.stressed.risk)
                  : "Unavailable"}
              </td>
              <td>
                {result.risk_transition?.transition ?? "Unavailable"} ·{" "}
                {result.risk_transition?.status}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        Differences are reported by Python only when metric evidence is
        comparable. No expected returns, forecasts or probabilities are
        inferred.
      </p>
    </Panel>
  );
}
export function PortfolioAnalytics({ result }: { result: TerminalResult }) {
  const [metric, setMetric] = useState<
    "equity_quote" | "pnl_quote" | "drawdown_fraction"
  >("equity_quote");
  return (
    <div className="stack">
      <PortfolioStressComparison result={result} />
      <div className={result.stressed ? "portfolioComparison" : "stack"}>
        {[result.baseline, ...(result.stressed ? [result.stressed] : [])].map(
          (leg, i) => (
            <div className="stack" key={i}>
              <PortfolioResearchStatus
                leg={leg}
                label={i ? "Stressed" : "Baseline"}
              />
              <PortfolioMetrics leg={leg} label={i ? "Stressed" : "Baseline"} />
              <PortfolioRiskPanel
                leg={leg}
                label={i ? "Stressed" : "Baseline"}
              />
            </div>
          ),
        )}
      </div>
      <label>
        Chart metric
        <select
          aria-label="Chart metric"
          value={metric}
          onChange={(e) => setMetric(e.target.value as typeof metric)}
        >
          <option value="equity_quote">Modeled equity</option>
          <option value="pnl_quote">Modeled session PnL</option>
          <option value="drawdown_fraction">Modeled drawdown</option>
        </select>
      </label>
      <div className={result.stressed ? "portfolioComparison" : "stack"}>
        <PortfolioEquityChart
          leg={result.baseline}
          label="Baseline"
          metric={metric}
        />
        {result.stressed && (
          <PortfolioEquityChart
            leg={result.stressed}
            label="Stressed"
            metric={metric}
          />
        )}
      </div>
    </div>
  );
}
