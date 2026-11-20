import { useEffect, useRef } from "react";
import type { TerminalState } from "../types";
import { useDisplayStore } from "../stores/display";
import { navigationGroups, pageHref, terminalPages, workspaceHref, type PageName, type Workspace } from "../utils/navigation";
import { NavIcon } from "./NavIcon";

export function Sidebar({
  page,
  workspace,
  t,
  ws,
  mobile,
  open,
  onClose,
}: {
  page: PageName;
  workspace?: Workspace;
  t: TerminalState | null;
  ws: string;
  mobile: boolean;
  open: boolean;
  onClose: () => void;
}) {
  const mode = useDisplayStore((d) => d.experienceMode);
  const collapsed = useDisplayStore((d) => d.sidebarCollapsed);
  const setCollapsed = useDisplayStore((d) => d.setSidebarCollapsed);
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!mobile || !open) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const controls = () =>
      Array.from(
        ref.current?.querySelectorAll<HTMLElement>(
          "a[href], button:not(:disabled)",
        ) ?? [],
      ).filter((el) => el.getClientRects().length > 0);
    (
      ref.current?.querySelector<HTMLElement>('[aria-current="page"]') ??
      controls()[0]
    )?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
      if (event.key !== "Tab") return;
      const items = controls(),
        first = items[0],
        last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", keydown);
      previousFocus?.focus();
    };
  }, [mobile, open, onClose]);
  return (
    <>
      {mobile && open && (
        <div className="navScrim" aria-hidden="true" onClick={onClose} />
      )}
      <aside
        ref={ref}
        id="terminal-navigation"
        className={`sidebar ${collapsed ? "collapsed" : ""} ${open ? "mobileOpen" : ""}`}
        role={mobile && open ? "dialog" : undefined}
        aria-modal={mobile && open ? true : undefined}
        aria-label="Terminal navigation"
        inert={mobile && !open}
      >
        <div className="brand">
          <span className="brandMark" aria-hidden="true">
            H
          </span>
          <div className="brandCopy">
            <b>HyperAMM</b>
            <small>VIRTUAL LIQUIDITY ENGINE</small>
          </div>
        </div>
        <button
          className="collapseButton"
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          aria-controls="terminal-pages"
          aria-expanded={!collapsed}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? "›" : "‹"}
        </button>
        <button
          className="mobileNavClose"
          aria-label="Close navigation"
          onClick={onClose}
        >
          Close ×
        </button>
        <nav id="terminal-pages" aria-label="Terminal pages">
          {navigationGroups(mode).map(group => <div className="experienceNavGroup" key={group.title}>
            <div className="experienceNavTitle">{group.title}</div>
            {group.items.map(item => {
              const href = item.workspace ? workspaceHref(item.workspace) : pageHref(item.name);
              const active = page === item.name && workspace === item.workspace;
              const label = item.label ?? item.name;
              const icon = terminalPages.find(entry => entry.name === item.name)!.icon;
              return <a key={href} href={href} title={label} aria-label={label}
                aria-current={active ? "page" : undefined} onClick={onClose}
                className={active ? "nav active" : "nav"}>
                <span className="navIcon"><NavIcon name={icon} /></span>
                <span className="navLabel">{label}</span>
              </a>;
            })}
          </div>)}
        </nav>
        <div className="sideFooter">
          <b>{ws.toUpperCase()}</b>
          <span>
            {t?.market.market ?? "—"} ·{" "}
            {t?.strategy.config.execution_mode ?? "—"}
          </span>
          <span>
            System {t?.system_health.status ?? "UNAVAILABLE"}
            {ws !== "connected" && t ? " · historical" : ""}
          </span>
          <small>LOCAL RESEARCH TERMINAL</small>
        </div>
      </aside>
    </>
  );
}
