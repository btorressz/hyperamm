import type { TerminalState, TerminalHistory, HistoryRange } from "../types";
import { useTerminalHistory } from "../hooks/useTerminalHistory";
import { useDisplayStore } from "../stores/display";
import { HistoryChart, type HistoryLine } from "../components/HistoryChart";
import {
  Panel,
  Metrics,
  Empty,
  StatusBanner,
} from "../components/TerminalPrimitives";
import { Badge } from "../components/Badge";
import { StateDistribution } from "../components/StateDistribution";
import { accountingValue, evidenceTime } from "../utils/researchEvidence";
import {
  effectiveRange,
  historyRanges,
  observationCounts,
} from "../utils/terminalHistory";
import "../phase1331.css";
import "../phase1332.css";
const equityLines: HistoryLine[] = [
  { key: "equity", label: "Equity", color: "#4cd4a1", unit: "quote" },
  { key: "peak_equity", label: "Peak equity", color: "#819bbc", unit: "quote" },
];
const pnlLines: HistoryLine[] = [
  {
    key: "net_pnl",
    label: "Net PnL",
    color: "#4cd4a1",
    unit: "quote",
    signed: true,
  },
];
const exposureLines: HistoryLine[] = [
  {
    key: "position_base",
    label: "Position",
    color: "#b69aff",
    unit: "base",
    signed: true,
  },
];
const drawdownLines: HistoryLine[] = [
  { key: "drawdown_pct", label: "Drawdown", color: "#f0788a", percent: true },
  {
    key: "capital_utilization",
    label: "Capital utilization",
    color: "#e8b968",
    percent: true,
  },
];
type HistoryView = ReturnType<typeof useTerminalHistory>;
export function HistoryRangeSelector({
  preference,
  available,
  onChange,
  disabled = false,
}: {
  preference: HistoryRange;
  available?: HistoryRange[];
  onChange: (r: HistoryRange) => void;
  disabled?: boolean;
}) {
  return (
    <div className="historyRanges" role="group" aria-label="History range">
      {historyRanges.map((r) => (
        <button
          type="button"
          key={r}
          aria-pressed={effectiveRange(preference, available) === r}
          disabled={disabled || (r !== "session" && !available?.includes(r))}
          title={
            r !== "session" && !available?.includes(r)
              ? "Backend has not retained the full range yet"
              : "Query backend retained observations"
          }
          onClick={() => onChange(r)}
        >
          {r === "session" ? "SESSION" : r.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
function ChartViews({ h }: { h: HistoryView }) {
  const data = h.data;
  return (
    <>
      {h.historical && (
        <StatusBanner>
          Historical session charts · retained browser evidence only. Current
          history requests are paused until a fresh connected terminal session.
        </StatusBanner>
      )}
      {h.isError && (
        <p className="inlineError" role="alert">
          History unavailable: {h.error?.message}
          <button
            type="button"
            disabled={h.historical}
            onClick={() => void h.refetch()}
          >
            Retry history
          </button>
        </p>
      )}
      {!data ? (
        !h.isError && (
          <Empty>
            {h.historical
              ? "Current session history unavailable while disconnected."
              : "Loading session observations…"}
          </Empty>
        )
      ) : (
        <>
          <HistoryMetadata data={data} />
          <div className="grid twoColumns">
            {(
              [
                ["Equity & high-water mark", equityLines],
                ["Net PnL", pnlLines],
                ["Inventory exposure", exposureLines],
                ["Drawdown & capital utilization", drawdownLines],
              ] as [string, HistoryLine[]][]
            ).map(([title, lines]) => (
              <Panel key={title} title={title} meta="Backend observation time">
                <HistoryChart
                  points={data.points}
                  fitKey={`${data.session_id}:${data.range}`}
                  lines={lines}
                />
              </Panel>
            ))}
          </div>
        </>
      )}
    </>
  );
}
export function HistoryMetadata({ data }: { data: TerminalHistory }) {
  return (
    <div className="historyMetadata">
      <p>
        In-memory session · {data.retained_points} observations ·{" "}
        {Math.round(data.retained_seconds)} seconds retained ·{" "}
        {data.points.length} returned samples · {data.range.toUpperCase()}
      </p>
      <details>
        <summary>Inspect retention and session identity</summary>
        <dl className="researchDetails">
          <div>
            <dt>Session</dt>
            <dd>{data.session_id}</dd>
          </div>
          <div>
            <dt>Retained oldest / latest</dt>
            <dd>
              {evidenceTime(data.oldest_at)}
              <br />
              {evidenceTime(data.latest_at)}
            </dd>
          </div>
        </dl>
        <p>
          Server-side ranges end at the latest retained observation, not the
          browser clock. Bounded responses may be sampled across the retained
          span. Missing evidence creates gaps. This is not permanent account
          history.
        </p>
      </details>
    </div>
  );
}
// Vault preserves its session-default view and shares the same safeguards/lifecycle.
export function SessionCharts() {
  const h = useTerminalHistory();
  return <ChartViews h={h} />;
}
export function AnalyticsOverview({
  t,
  historical = false,
}: {
  t: TerminalState;
  historical?: boolean;
}) {
  const v = t.vault;
  const value = (x: unknown, unit: string) => {
    const s = accountingValue(x, unit === "%");
    return s === "Unavailable" || unit === "%" ? s : `${s} ${unit}`;
  };
  return (
    <Panel
      title={`Session overview · ${v.market}`}
      meta={
        <Badge tone={historical || v.stale || v.error ? "warn" : "blue"}>
          {historical ? "HISTORICAL" : "RUNTIME OBSERVATIONS"} · {v.mode} ·{" "}
          {v.accounting_complete}
        </Badge>
      }
    >
      <Metrics
        items={[
          ["Current equity", value(v.equity_quote, "quote")],
          ["Session net PnL", value(v.session_pnl_quote, "quote")],
          ["Current drawdown", value(v.drawdown_pct, "%")],
          ["Capital utilization", value(v.capital_utilization, "%")],
          ["Inventory exposure", value(v.position_base, "base")],
          ["Fill count", t.execution_summary.fill_count ?? "Unavailable"],
          [
            "Filled notional",
            value(t.execution_summary.filled_notional, "quote"),
          ],
          [
            "Execution quality",
            t.agents.execution_quality?.state ?? "Unavailable",
          ],
          ["Market data mode", t.market.mode],
          ["Accounting mode", `${v.mode} · ${v.accounting_complete}`],
        ]}
      />
      <p className="muted panelNote">
        {v.simulated
          ? "PAPER economics are simulated."
          : "TESTNET accounting may be partial; unsupported metrics remain unavailable."}{" "}
        Signed inventory is base position; equity and capital are separate from
        virtual AMM reserves.
      </p>
      <p className="muted panelNote">
        Terminal emission: {evidenceTime(t.emitted_at)} · Accounting
        observation: {evidenceTime(v.updated_at)} ·{" "}
        {v.error
          ? "ERROR"
          : v.stale
            ? "STALE"
            : "backend reports usable accounting"}
      </p>
    </Panel>
  );
}
export function ExecutionQualitySummary({ t }: { t: TerminalState }) {
  const e = t.agents.execution_quality?.metrics,
    tox = t.agents.toxic_flow?.metrics;
  const bps = (x: unknown) => {
    const v = accountingValue(x);
    return v === "Unavailable" ? v : v + " bps";
  };
  return (
    <Panel
      title="Execution-quality evidence"
      meta={
        t.vault.simulated
          ? "SIMULATED PAPER EVIDENCE"
          : "AVAILABLE VENUE EVIDENCE"
      }
    >
      <Metrics
        items={[
          ["Fill count", t.execution_summary.fill_count ?? "Unavailable"],
          [
            "Filled notional (quote)",
            accountingValue(t.execution_summary.filled_notional),
          ],
          ["Spread capture", bps(e?.average_spread_capture_bps)],
          [
            "Mature markout",
            bps(
              tox && tox.matured_fills > 0
                ? e?.average_mature_markout_bps
                : null,
            ),
          ],
          [
            "Adverse fill rate",
            accountingValue(
              tox && tox.matured_fills > 0 ? tox.adverse_fill_rate : null,
              true,
            ),
          ],
          [
            "Reconciliation churn",
            accountingValue(e?.reconciliation_churn_ratio, true),
          ],
          ["Pending markouts", tox?.pending_markouts ?? "Unavailable"],
        ]}
      />
      <details className="researchInset">
        <summary>How to interpret execution metrics</summary>
        <dl className="researchDetails">
          <div>
            <dt>Fill count / filled notional</dt>
            <dd>
              Backend observed fills and their quote-currency notional; not an
              equity or profitability measure.
            </dd>
          </div>
          <div>
            <dt>Spread capture</dt>
            <dd>
              Signed fill-price capture versus the eligible reference bound at
              fill time, in basis points. Positive is favorable.
            </dd>
          </div>
          <div>
            <dt>Mature markout / adverse fill rate</dt>
            <dd>
              Signed post-fill price movement after the eligible horizon, and
              the adverse share of matured fills. Pending fills are not
              completed markouts; missing support stays unavailable.
            </dd>
          </div>
          <div>
            <dt>Reconciliation churn</dt>
            <dd>
              (REPLACE + CANCEL) / max(1, CREATE + REPLACE + CANCEL). KEEP
              observations do not dilute churn.
            </dd>
          </div>
        </dl>
        <p className="muted">
          Deterministic PAPER outcomes do not establish venue queue priority,
          latency or future profitability. These are observations, not trading
          recommendations.
        </p>
      </details>
    </Panel>
  );
}
export function Analytics({
  t,
  historical = false,
}: {
  t: TerminalState;
  historical?: boolean;
}) {
  const preference = useDisplayStore((s) => s.defaultRange),
    setRange = useDisplayStore((s) => s.setDefaultRange);
  // Session query supplies authoritative retention metadata even when the chosen range is unavailable.
  const metadata = useTerminalHistory("session"),
    range = effectiveRange(preference, metadata.data?.available_ranges),
    selected = useTerminalHistory(range);
  const h = range === "session" ? metadata : selected;
  return (
    <div className="researchWorkspace analyticsPage stack">
      <div className="researchPageTitle">
        <div>
          <h1>Session analytics</h1>
          <p className="muted">
            Performance, exposure and execution evidence · read-only research
          </p>
        </div>
        <Badge tone="blue">
          {t.market.mode} · {t.vault.mode}
        </Badge>
      </div>
      {historical && (
        <StatusBanner>
          Historical analytics · last accepted terminal snapshot. Values are not
          current account performance.
        </StatusBanner>
      )}
      {!historical && (t.vault.stale || t.vault.error) && (
        <StatusBanner>
          Accounting evidence is {t.vault.error ? "in error" : "stale"};
          last-known values do not establish current capital authority.
        </StatusBanner>
      )}
      <AnalyticsOverview t={t} historical={historical} />
      <section aria-label="Session research charts">
        <div className="researchPageTitle">
          <h2>Retained session observations</h2>
          <HistoryRangeSelector
            preference={preference}
            available={metadata.data?.available_ranges}
            onChange={setRange}
            disabled={metadata.historical}
          />
        </div>
        {range !== preference && (
          <p className="muted">
            Saved preference {preference.toUpperCase()} is not fully retained.
            Showing SESSION until the backend range becomes available.
          </p>
        )}
        <ChartViews h={h} />
      </section>
      <ExecutionQualitySummary t={t} />
      <Panel
        title="Retained observation distributions"
        meta="Returned sample counts"
      >
        <div className="grid twoColumns">
          <StateDistribution
            counts={observationCounts(h.data?.points ?? [], "risk_state")}
            label="Risk states"
          />
          <StateDistribution
            counts={observationCounts(h.data?.points ?? [], "agent_regime")}
            label="Agent regimes"
          />
        </div>
      </Panel>
    </div>
  );
}
