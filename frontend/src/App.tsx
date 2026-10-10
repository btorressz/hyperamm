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
import { usePageNavigation } from "./hooks/usePageNavigation";
import { useMobileNavigation } from "./hooks/useMobileNavigation";
import type { PageName } from "./utils/navigation";
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
  const page = usePageNavigation();
  const mobile = useMobileNavigation();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const closeNavigation = useCallback(() => setNavigationOpen(false), []);
  const pageContent = useRef<HTMLDivElement>(null);
  const previousPage = useRef(page);
  useEffect(() => {
    document.title = `${page} · HyperAMM`;
    if (previousPage.current !== page) {
      previousPage.current = page;
      closeNavigation();
      pageContent.current?.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }
  }, [page, closeNavigation]);
  useEffect(() => {
    if (!mobile) closeNavigation();
  }, [mobile, closeNavigation]);
  let content: ReactNode;
  if (!t)
    content = (
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
      Markets: <Markets t={t} />,
      Strategy: <Strategy t={t} historical={historical} />,
      "AMM Settings": <AmmSettings t={t} />,
      Execution: <Execution key={t.session_id} t={t} historical={historical} />,
      Risk: <Risk t={t} />,
      "Supervisory Agents": <Agents t={t} />,
      Vault: <Vault t={t} />,
      Analytics: <Analytics t={t} />,
      "Simulation & Optimization": <Simulation />,
      Logs: <Logs t={t} />,
      Settings: <Settings t={t} />,
    };
    content = pages[page];
  }
  return (
    <div className={`app ${dense ? "dense" : ""}`}>
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
            DEMO MARKET DATA · simulated evidence ·{" "}
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
          <TerminalDiagnostics nowMs={nowMs} />
          <div
            id="page-content"
            ref={pageContent}
            tabIndex={-1}
            aria-label={`${page} workspace`}
          >
            <TerminalBoundary key={page}>{content}</TerminalBoundary>
          </div>
        </div>
      </main>
    </div>
  );
}
