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
  { name: "Portfolio Research", slug: "portfolio-research", icon: "research" },
  { name: "Logs", slug: "logs", icon: "logs" },
  { name: "Settings", slug: "settings", icon: "controls" },
] as const;

export type PageName = (typeof terminalPages)[number]["name"];
export const experienceModes = ["Starter", "Pro", "Institutional"] as const;
export type ExperienceMode = (typeof experienceModes)[number];

const workspaces = {
  home: ["Dashboard", "home"],
  paper: ["Simulation & Optimization", "paper"],
  results: ["Simulation & Optimization", "paper-results"],
  replay: ["Simulation & Optimization", "replay"],
  scenarioComparison: ["Simulation & Optimization", "scenario-comparison"],
  marketComparison: ["Markets", "comparison"],
} as const satisfies Record<string, [PageName, string]>;
export type Workspace = keyof typeof workspaces;

export function workspaceHref(workspace: Workspace): string {
  const [page, slug] = workspaces[workspace];
  return `${pageHref(page)}/${slug}`;
}

export function workspaceFromHash(hash: string): Workspace | undefined {
  return (Object.keys(workspaces) as Workspace[]).find(workspace => workspaceHref(workspace) === hash);
}

export function pageFromHash(hash: string): PageName {
  const workspace = workspaceFromHash(hash);
  return workspace ? workspaces[workspace][0] :
    terminalPages.find(p => `#/${p.slug}` === hash)?.name ?? "Dashboard";
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
  if (workspaceFromHash(window.location.hash)) return;
  const canonical = pageHref(pageFromHash(window.location.hash));
  if (window.location.hash !== canonical)
    window.history.replaceState(window.history.state, "", canonical);
}

interface NavItem {
  name: PageName;
  label?: string;
  workspace?: Workspace;
}
interface NavGroup {
  title: string;
  items: NavItem[];
}
const modeGroups: Record<ExperienceMode, NavGroup[]> = {
  Starter: [{ title: "Get started", items: [
    { name: "Dashboard", label: "Home", workspace: "home" },
    { name: "Markets", label: "Market Explorer" },
    { name: "Simulation & Optimization", label: "Guided Research", workspace: "paper" },
    { name: "Simulation & Optimization", label: "Results", workspace: "results" },
    { name: "Settings", label: "Help / Settings" },
  ] }],
  Pro: [
    { title: "Strategy & AMM", items: [
      { name: "Dashboard" }, { name: "Markets" }, { name: "Strategy" }, { name: "AMM Settings" },
      { name: "Execution" }, { name: "Risk" },
    ] },
    { title: "Agents & research", items: [
      { name: "Supervisory Agents" }, { name: "Simulation & Optimization" },
      { name: "Simulation & Optimization", label: "PAPER & Advisory Agents", workspace: "paper" },
      { name: "Simulation & Optimization", label: "Historical Replay", workspace: "replay" },
      { name: "Simulation & Optimization", label: "Scenario vs Historical", workspace: "scenarioComparison" },
      { name: "Markets", label: "Market vs Research", workspace: "marketComparison" },
      { name: "Analytics" },
    ] },
  ],
  Institutional: [
    { title: "Portfolio & controls", items: [
      { name: "Portfolio Research" }, { name: "Risk" }, { name: "Execution", label: "Execution evidence" },
      { name: "Vault" }, { name: "Analytics" }, { name: "Logs", label: "Audit logs" },
    ] },
    { title: "Research evidence", items: [
      { name: "Simulation & Optimization", label: "PAPER & Advisory Agents", workspace: "paper" },
      { name: "Simulation & Optimization", label: "Historical Replay", workspace: "replay" },
      { name: "Simulation & Optimization", label: "Scenario vs Historical", workspace: "scenarioComparison" },
      { name: "Markets", label: "Market vs Research", workspace: "marketComparison" },
    ] },
  ],
};

export function navigationGroups(mode: ExperienceMode): NavGroup[] {
  const groups = modeGroups[mode];
  const primary = new Set(groups.flatMap(group => group.items.filter(item => !item.workspace).map(item => item.name)));
  return [...groups, {
    title: "More workspaces", items: terminalPages.filter(page => !primary.has(page.name)).map(({ name }) => ({ name })),
  }];
}
