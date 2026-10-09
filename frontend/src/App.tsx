import { displayedTerminal } from "./utils/freshness";
import { TerminalDiagnostics } from "./components/TerminalDiagnostics";
import { useEffect, useState, type ReactNode } from "react";
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
  const [page, setPage] = useState("Dashboard");
  let content: ReactNode;
  if (!t)
    content = (
      <div className="loading panel">
        <h2>Connecting to HyperAMM…</h2>
        <p>Waiting for a valid backend terminal snapshot.</p>
      </div>
    );
  else {
    const pages: Record<string, ReactNode> = {
      Dashboard: <Dashboard t={t} />,
      Markets: <Markets t={t} />,
      Strategy: <Strategy t={t} />,
      "AMM Settings": <AmmSettings t={t} />,
      Execution: <Execution t={t} />,
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
      <Sidebar page={page} setPage={setPage} t={t} ws={s.wsState} />
      <main>
        <Header t={t} ws={s.wsState} />
        {health.isError && (
          <div className="alert" role="alert">
            Backend health endpoint unavailable.
          </div>
        )}
        {s.payloadError && (
          <div className="alert dangerText" role="alert">
            {s.payloadError}
          </div>
        )}
        {s.wsState !== "connected" && t && (
          <div className="alert" role="status">
            TERMINAL STALE · {s.wsState.toUpperCase()} · displaying last valid
            snapshot. Reconnect attempts {s.reconnectAttempts}.
          </div>
        )}
        {s.connectionNotice && (
          <div className="alert" role="status">
            {s.connectionNotice}
          </div>
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
          <div className="alert">MARKET STALE · backend feed evidence</div>
        )}
        {t?.strategy.last_error && (
          <div className="alert">Strategy notice: {t.strategy.last_error}</div>
        )}
        <div className="content">
          <TerminalDiagnostics nowMs={nowMs} />
          <TerminalBoundary key={page}>{content}</TerminalBoundary>
        </div>
      </main>
    </div>
  );
}
