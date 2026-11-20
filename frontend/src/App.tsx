import { terminalEnvelopeFailure } from "./utils/terminalIntegrity";
import { displayedTerminal } from "./utils/freshness";
import { TerminalDiagnostics } from "./components/TerminalDiagnostics";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import "./styles.css";
import "./phase5.css";
import "./phase6.css";
import "./phase7.css";
import "./phase8.css";
import "./phase9.css";
import "./phase11.css";
import "./phase12.css";
import "./phase13.css";
import "./phase153.css";
import "./phase186.css";
import { usePageNavigation } from "./hooks/usePageNavigation";
import { useMobileNavigation } from "./hooks/useMobileNavigation";
import { pageHref, workspaceHref, type PageName } from "./utils/navigation";
import { Loading, StatusBanner } from "./components/TerminalPrimitives";
import { useTerminalSocket } from "./hooks/useTerminalSocket";
import { useTerminalStore } from "./stores/terminal";
import { useDisplayStore } from "./stores/display";
import { Sidebar } from "./components/Sidebar";
import { Header } from "./components/Header";
import { TerminalBoundary } from "./components/TerminalBoundary";
import { Dashboard } from "./pages/Dashboard";
import { Markets } from "./pages/Markets";
import { Strategy } from "./pages/Strategy";
import { AmmSettings } from "./pages/AmmSettings";
import { Execution } from "./pages/Execution";
import { Risk } from "./pages/Risk";
import { Agents } from "./pages/Agents";
import { Vault } from "./pages/Vault";
import { Analytics } from "./pages/Analytics";
import { Simulation } from "./pages/Simulation";
import { PortfolioResearch } from "./pages/PortfolioResearch";
import { Logs } from "./pages/Logs";
import { Settings } from "./pages/Settings";
export default function App() {
  useTerminalSocket();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 10000,
  });
  const [, setNowMs] = useState(Date.now());
  const nowMs = Date.now();
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const s = useTerminalStore(),
    t = s.terminal ? displayedTerminal(s.terminal, nowMs) : null,
    dense = useDisplayStore((d) => d.dense);
  const { page, workspace } = usePageNavigation();
  const mode = useDisplayStore(d => d.experienceMode);
  const isSimulation = page === "Simulation & Optimization";
  const mobile = useMobileNavigation();
  const compactEntry = mobile || workspace === "home" || workspace === "paper" || workspace === "results" ||
    page === "Markets" || (mode === "Institutional" && page === "Portfolio Research");
  const [simulationVisited, setSimulationVisited] = useState(false);
  useEffect(() => {
    if (isSimulation) setSimulationVisited(true);
  }, [isSimulation]);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const closeNavigation = useCallback(() => setNavigationOpen(false), []);
  const pageContent = useRef<HTMLDivElement>(null);
  const previousPage = useRef({ page, workspace });
  useEffect(() => {
    document.title = `${page} · HyperAMM`;
    if (previousPage.current.page !== page || previousPage.current.workspace !== workspace) {
      previousPage.current = { page, workspace };
      closeNavigation();
      const target = workspace === "results" ? document.getElementById("paper-results") : null;
      (target ?? pageContent.current)?.focus({ preventScroll: true });
      if (target) target.scrollIntoView({ block: "start" });
      else window.scrollTo(0, 0);
    }
  }, [page, workspace, closeNavigation]);
  useEffect(() => {
    if (!mobile) closeNavigation();
  }, [mobile, closeNavigation]);
  let content: ReactNode;
  if (workspace === "home")
    content = <section className="experienceHome stack">
      <div className="experienceIntro">
        <div>
          <h1>Start with a market</h1>
          <p>Explore perpetuals and test market making with hypothetical funds. You can review simulated performance and its evidence after each run.</p>
        </div>
      </div>
      <div className="experienceHomeLinks">
        <a href={pageHref("Markets")}><strong>Explore markets</strong><span>Find a listed Core or HIP-3 perpetual.</span></a>
        <a href={workspaceHref("paper")}><strong>Run guided research</strong><span>Choose a scenario and check its PAPER eligibility.</span></a>
        <a href={workspaceHref("results")}><strong>Review results</strong><span>See P&amp;L, costs and inventory from your current run.</span></a>
      </div>
      <p className="muted">Change Workspace mode to find advanced AMM controls, portfolio research and audit evidence.</p>
    </section>;
  else if (!t)
    content = page === 'Portfolio Research' ? <PortfolioResearch /> : page === 'Markets' ? <Markets t={null} workspace={workspace} /> : page === 'Settings' ? <Settings t={null} historical /> : isSimulation ? null : (
      <Loading title="Connecting to HyperAMM…">
        Waiting for a valid backend terminal snapshot.
      </Loading>
    );
  else {
    const historical =
      s.wsState !== "connected" ||
      !!terminalEnvelopeFailure(t.emitted_at, nowMs);
    const pages: Record<PageName, ReactNode> = {
      Dashboard: <Dashboard t={t} historical={historical} />,
      Markets: <Markets t={t} workspace={workspace} />,
      Strategy: <Strategy t={t} historical={historical} />,
      "AMM Settings": <AmmSettings t={t} />,
      Execution: <Execution key={t.session_id} t={t} historical={historical} />,
      Risk: <Risk t={t} />,
      "Supervisory Agents": <Agents key={`${t.process_id}:${t.session_id}`} t={t} historical={historical} />,
      Vault: <Vault key={`${t.process_id}:${t.session_id}`} t={t} historical={historical} />,
      Analytics: <Analytics key={`${t.process_id}:${t.session_id}`} t={t} historical={historical} />,
      "Simulation & Optimization": null,
      "Portfolio Research": <PortfolioResearch firewall={historical ? undefined : t.risk_firewall.state} />,
      Logs: <Logs key={`${t.process_id}:${t.session_id}`} t={t} historical={historical} />,
      Settings: <Settings t={t} historical={historical} />,
    };
    content = pages[page];
  }
  return (
    <div className={`app ${dense ? "dense" : ""}`} data-experience={mode.toLowerCase()}>
      <a
        className="skipLink"
        href="#page-content"
        onClick={(event) => {
          event.preventDefault();
          pageContent.current?.focus();
        }}
      >
        Skip to workspace
      </a>
      <Sidebar
        page={page}
        workspace={workspace}
        t={t}
        ws={s.wsState}
        mobile={mobile}
        open={navigationOpen}
        onClose={closeNavigation}
      />
      <main inert={mobile && navigationOpen}>
        <Header
          t={t}
          ws={s.wsState}
          navigationOpen={navigationOpen}
          onOpenNavigation={() => setNavigationOpen(true)}
        />
        {health.isError && (
          <StatusBanner tone="bad">
            Backend health endpoint unavailable.
          </StatusBanner>
        )}
        {s.payloadError && (
          <StatusBanner tone="bad">{s.payloadError}</StatusBanner>
        )}
        {s.wsState !== "connected" && t && (
          <StatusBanner>
            TERMINAL STALE · {s.wsState.toUpperCase()} · displaying last valid
            snapshot. Reconnect attempts {s.reconnectAttempts}.
          </StatusBanner>
        )}
        {s.connectionNotice && (
          <StatusBanner>{s.connectionNotice}</StatusBanner>
        )}
        {t?.market.simulated && (
          <div className="truthBanner">
            OPERATIONAL TERMINAL · DEMO MARKET DATA · simulated evidence ·{" "}
            {t.strategy.config.execution_mode === "PAPER"
              ? "PAPER / SIMULATED"
              : "GUARDED TESTNET / PARTIAL"}
          </div>
        )}
        {t?.market.stale && (
          <StatusBanner>MARKET STALE · backend feed evidence</StatusBanner>
        )}
        {t?.strategy.last_error && (
          <StatusBanner>Strategy notice: {t.strategy.last_error}</StatusBanner>
        )}
        <div className="content">
          {compactEntry ? (
            <details className="experienceDiagnostics">
              <summary>Terminal diagnostics</summary>
              <TerminalDiagnostics nowMs={nowMs} />
            </details>
          ) : <TerminalDiagnostics nowMs={nowMs} />}
          <div
            id="page-content"
            ref={pageContent}
            role="group"
            tabIndex={-1}
            aria-label={`${page} workspace`}
          >
            {(simulationVisited || isSimulation) && (
              <div hidden={!isSimulation}>
                <TerminalBoundary><Simulation active={isSimulation} workspace={isSimulation ? workspace : undefined} /></TerminalBoundary>
              </div>
            )}
            {!isSimulation && <TerminalBoundary key={page}>{content}</TerminalBoundary>}
          </div>
        </div>
      </main>
    </div>
  );
}
