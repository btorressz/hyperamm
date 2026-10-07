import { useState } from "react";
import type { TerminalState } from "../types";
const nav = [
  ["Dashboard", "active"],
  ["Markets", "active"],
  ["Strategy", "active"],
  ["AMM Settings", "active"],
  ["Execution", "active"],
  ["Risk", "active"],
  ["Supervisory Agents", "active"],
  ['Vault','active'],
  ["Analytics", "active"],
  ["Simulation & Optimization", "active"],
  ["Logs", "active"],
  ["Settings", "active"],
];
const icons = ["◈", "▥", "⌁", "⚙", "⇄", "◇", "◎", "▣", "▤", "◷", "≡", "⋮"];
export function Sidebar({
  page,
  setPage,
  t,
  ws,
}: {
  page: string;
  setPage: (p: string) => void;
  t: TerminalState | null;
  ws: string;
}) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="brand">
        <span className="brandMark">H</span>
        <div className="brandCopy">
          <b>HyperAMM</b>
          <small>VIRTUAL LIQUIDITY ENGINE</small>
        </div>
      </div>
      <button
        className="collapseButton"
        aria-label="Toggle navigation width"
        aria-expanded={!collapsed}
        onClick={() => setCollapsed((v) => !v)}
      >
        {collapsed ? "›" : "‹"}
      </button>
      <nav aria-label="Terminal pages">
        {nav.map(([name], i) => (
          <button
            key={name}
            title={name}
            aria-label={name}
            aria-current={page === name ? "page" : undefined}
            onClick={() => setPage(name)}
            className={page === name ? "nav active" : "nav"}
          >
            <span className="navIcon" aria-hidden="true">
              {icons[i]}
            </span>
            <span className="navLabel">{name}</span>
          </button>
        ))}
      </nav>
      <div className="sideFooter">
        <b>{ws.toUpperCase()}</b>
        <span>
          {t?.market.market ?? "—"} · {t?.strategy.config.execution_mode ?? "—"}
        </span>
        <span>System {t?.system_health.status ?? "UNAVAILABLE"}</span>
        <small>Phase 12 · IMPLEMENTED / IN REVIEW</small>
      </div>
    </aside>
  );
}
