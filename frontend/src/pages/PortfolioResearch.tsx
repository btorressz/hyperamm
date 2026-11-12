import { useState } from "react";
import { usePortfolioResearch } from "../hooks/usePortfolioResearch";
import { allocationError, decimalDisplay } from "../utils/portfolioResearch";
import { PortfolioConfiguration } from "../components/portfolio/PortfolioConfiguration";
import { PortfolioStressLab } from "../components/portfolio/PortfolioStressLab";
import { PortfolioAnalytics } from "../components/portfolio/PortfolioAnalytics";
import { PortfolioProvenance } from "../components/portfolio/PortfolioProvenance";
import {
  Panel,
  Metrics,
  StatusBanner,
  Empty,
} from "../components/TerminalPrimitives";
import "../phase14.css";
import "../phase175.css";
export function PortfolioResearch() {
  const s = usePortfolioResearch(),
    [section, setSection] = useState("Configure");
  const validation = allocationError(s.draft),
    p = s.preview;
  return (
    <div
      className="portfolioWorkspace stack"
      aria-label="Portfolio Research Terminal"
    >
      <div className="portfolioTitle">
        <div>
          <div className="eyebrow">MULTI-MARKET PAPER WORKSPACE</div>
          <h1>Portfolio Research</h1>
          <p>
            Configure hypothetical capital. Inspect native accounting. Test
            explicit modeled shocks.
          </p>
        </div>
        <span className="portfolioAuthority">RESEARCH / READ ONLY</span>
      </div>
      <StatusBanner>
        HYPOTHETICAL · PAPER ONLY · Non-custodial research without operational
        trading authority. Drafts never change active strategy, orders, balances
        or risk controls.
      </StatusBanner>
      <Panel title="Portfolio Overview" meta={`LOCAL DRAFT ${s.revision + 1}`}>
        <Metrics
          items={[
            [
              "Selected markets",
              s.draft.allocations.map((a) => a.market + "-PERP").join(" · ") ||
                "None",
            ],
            [
              "Validated initial capital",
              decimalDisplay(p?.config.budget.total_equity_quote, "USDC"),
            ],
            ["Allocated capital", decimalDisplay(p?.allocated_quote, "USDC")],
            ["Remaining reserve", decimalDisplay(p?.reserve_quote, "USDC")],
            ["Configuration", p ? "VALIDATED" : "PREVIEW REQUIRED"],
            [
              "Estimated trace eligibility",
              p?.trace_eligibility ?? "Unavailable",
            ],
          ]}
        />
        {p && (
          <p>
            Prepared workload budget: {p.workload.executed_frames} total frames
            · {p.workload.quote_level_frames} frame × quote-level units ·{" "}
            {p.workload.native_observations} retained native observations.{" "}
            {p.stress ? "Baseline and stress included." : "One execution leg."}{" "}
            Limits: {p.workload_limits?.executed_frames ?? 3000} frames,{" "}
            {p.workload_limits?.quote_level_frames ?? 24000} quote-level units,{" "}
            {p.workload_limits?.native_observations ?? 1500} native
            observations.
          </p>
        )}
      </Panel>
      <nav
        className="portfolioSections"
        aria-label="Portfolio workspace sections"
      >
        {["Configure", "Analytics", "Stress Lab", "Provenance"].map((name) => (
          <button
            key={name}
            aria-pressed={section === name}
            onClick={() => setSection(name)}
          >
            {name}
          </button>
        ))}
      </nav>
      <div className="portfolioActions panel">
        <div className="actions">
          <button
            className="primary"
            disabled={!!s.pending || !!validation || !s.catalog.data}
            onClick={() => s.submit("PREVIEW")}
          >
            Validate / Preview
          </button>
          <button disabled={!!s.pending || !p} onClick={() => s.submit("RUN")}>
            Run PAPER portfolio
          </button>
          <button
            disabled={!!s.pending || !p}
            onClick={() => s.submit("ANALYZE")}
          >
            Analyze portfolio
          </button>
          <button
            disabled={!!s.pending || !p?.stress}
            onClick={() => s.submit("STRESS")}
          >
            Run baseline + stress
          </button>
          {s.pending && <button onClick={s.invalidate}>Stop waiting</button>}
        </div>
        <p role="status" aria-live="polite">
          {s.pending
            ? "Research request in progress. No automatic retry or duplicate polling."
            : s.result
              ? "Accepted research evidence is available in Analytics."
              : p
                ? "Current configuration validated. Choose a PAPER research computation."
                : "Edit local inputs, then validate explicitly."}
        </p>
        <p className="muted">
          Stop waiting aborts the browser fetch; an admitted backend worker
          continues until completion.
        </p>
        {validation && (
          <p className="inlineError" role="alert">
            {validation}
          </p>
        )}
        {s.error && <StatusBanner tone="bad">{s.error}</StatusBanner>}
        {s.catalog.isError && (
          <StatusBanner tone="bad">
            Scenario catalog unavailable. Check the local API.{" "}
            <button onClick={() => void s.catalog.refetch()}>
              Retry catalog
            </button>
          </StatusBanner>
        )}
        {p?.trace_eligibility === "FINAL_ONLY" && (
          <StatusBanner>
            Estimated FINAL_ONLY: native retention cannot cover the full
            history. Simulation can complete, while drawdown and charts remain
            unavailable and risk may be BLOCKED. Three markets support up to 250
            frames per leg in stress comparisons.
          </StatusBanner>
        )}
      </div>
      {section === "Configure" && (
        <PortfolioConfiguration
          d={s.draft}
          edit={s.edit}
          preview={p}
          scenarios={s.catalog.data?.scenarios ?? []}
        />
      )}
      {section === "Stress Lab" && (
        <PortfolioStressLab d={s.draft} edit={s.edit} />
      )}
      {section === "Analytics" &&
        (s.result ? (
          <PortfolioAnalytics result={s.result} />
        ) : (
          <Panel title="Portfolio Analytics">
            <Empty>
              No accepted result for the current draft. Validate and run PAPER
              research. Missing financial values remain Unavailable.
            </Empty>
          </Panel>
        ))}
      {section === "Provenance" && (
        <PortfolioProvenance preview={p} result={s.result} />
      )}
    </div>
  );
}
