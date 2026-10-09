// One route registry for native links, location state and page rendering.
export const terminalPages = [
  { name: "Dashboard", slug: "dashboard", icon: "overview" },
  { name: "Markets", slug: "markets", icon: "markets" },
  { name: "Strategy", slug: "strategy", icon: "strategy" },
  { name: "AMM Settings", slug: "amm-settings", icon: "controls" },
  { name: "Execution", slug: "execution", icon: "execution" },
  { name: "Risk", slug: "risk", icon: "risk" },
  { name: "Supervisory Agents", slug: "agents", icon: "agents" },
  { name: "Vault", slug: "vault", icon: "vault" },
  { name: "Analytics", slug: "analytics", icon: "analytics" },
  { name: "Simulation & Optimization", slug: "simulation", icon: "research" },
  { name: "Logs", slug: "logs", icon: "logs" },
  { name: "Settings", slug: "settings", icon: "controls" },
] as const;

export type PageName = (typeof terminalPages)[number]["name"];
export function pageFromHash(hash: string): PageName {
  return terminalPages.find((p) => `#/${p.slug}` === hash)?.name ?? "Dashboard";
}
export function pageHref(page: PageName): string {
  return `#/${terminalPages.find((p) => p.name === page)!.slug}`;
}
export function subscribeNavigation(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}
// Invalid/empty hashes replace the current entry; never add a history loop.
export function normalizePageHash(): void {
  const canonical = pageHref(pageFromHash(window.location.hash));
  if (window.location.hash !== canonical)
    window.history.replaceState(window.history.state, "", canonical);
}
