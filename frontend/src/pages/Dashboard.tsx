import { useQuery } from "@tanstack/react-query";
import { useDisplayStore } from "../stores/display";
import { generalizedDiscoveryQuery, useGeneralizedMarketSelection, useResearchMarketStore } from "../stores/researchMarkets";
import { useResearchVaultStore } from "../stores/researchVault";
import { marketCatalogDeadline, marketUniverseKey, matchesMarketResearchHandoff } from "../utils/marketUniverse";
import { pageHref, workspaceHref } from "../utils/navigation";
import { ObservedMarketSummary } from "../components/markets/ObservedMarketSummary";
import { useTerminalStore } from "../stores/terminal";
import type { TerminalState } from "../types";
import { TerminalKpis } from "../components/TerminalKpis";
import { PriceLiquidityChart } from "../components/PriceLiquidityChart";
import { OrderBook } from "../components/OrderBook";
import { QuickStrategyControl } from "../components/QuickStrategyControl";
import { LiquidityDistributionChart } from "../components/LiquidityDistributionChart";
import { StrategyAttribution } from "../components/StrategyAttribution";
import { InventorySkewChart } from "../components/InventorySkewChart";
import { RecentExecution } from "../components/RecentExecution";
import { SystemHealth } from "../components/SystemHealth";
import { Panel, Metrics } from "../components/TerminalPrimitives";
import { bps, fingerprint, number } from "../utils/format";
export function Dashboard({
  t,
  historical = false,
}: {
  t: TerminalState;
  historical?: boolean;
}) {
  const pro = useDisplayStore(state => state.experienceMode) === "Pro";
  const a = t.agents;
  const current = useTerminalStore((s) => s.wsState === "connected");
  return (
    <>
      <div className="operatorTitle">
        <div>
          <span className="eyebrow">OPERATOR OVERVIEW</span>
          <h1>Liquidity terminal</h1>
        </div>
        <span className="sessionLabel">
          {t.market.mode} ·{" "}
          {t.strategy.config.execution_mode === "PAPER"
            ? "PAPER / SIMULATED"
            : "GUARDED TESTNET"}{" "}
          · {current ? "current session" : "historical snapshot"}
        </span>
      </div>
      {pro && <ProResearchOverview t={t} historical={historical} />}
      <div className="dashboardTop">
        <PriceLiquidityChart t={t} />
        <OrderBook m={t.market} />
        <QuickStrategyControl t={t} />
      </div>
      <TerminalKpis t={t} />
      <div className="dashboardSecondary">
        <LiquidityDistributionChart t={t} />
        <StrategyAttribution t={t} />
        <InventorySkewChart t={t} />
      </div>
      <div className="dashboardBottom">
        <Panel title="Supervisory agents" meta="Phase 9 · recommendations">
          <Metrics
            items={[
              ["Regime", a.regime?.state ?? "Unavailable"],
              ["Toxic flow", a.toxic_flow?.state ?? "Unavailable"],
              [
                "Execution quality",
                a.execution_quality?.state ?? "Unavailable",
              ],
              [
                "Supervisor spread",
                number(a.supervisor?.spread_multiplier) + "×",
              ],
            ]}
          />
        </Panel>
        <RecentExecution t={t} historical={historical} />
        <SystemHealth t={t} compact />
      </div>
    </>
  );
}

function ProResearchOverview({ t, historical }: { t: TerminalState; historical: boolean }) {
  const discovery = useQuery(generalizedDiscoveryQuery);
  const catalog = discovery.data;
  const handoff = useGeneralizedMarketSelection(state => state.handoff);
  const nativeMarket = useResearchMarketStore(state => state.selectedResearchMarket);
  const researchPreset = useResearchVaultStore(state => state.useForResearch ? state.preset?.name : undefined);
  const recordIndex = catalog?.catalog?.records.findIndex(record => handoff
    ? marketUniverseKey(record.identity) === handoff.key
    : record.identity.dex === "" && record.identity.instrument_name === nativeMarket) ?? -1;
  const market = catalog?.catalog?.records[recordIndex];
  const decision = catalog?.eligibility[recordIndex];
  const active = !discovery.isError && Date.now() < marketCatalogDeadline(catalog) &&
    (!handoff || matchesMarketResearchHandoff(catalog, handoff));
  const config = t.strategy.config;
  const agents = t.agents;
  return <Panel title="Pro research overview" className="modeOverview">
    <div className="modeOverviewGrid">
      <section>
        <h3>Market & research</h3>
        <Metrics items={[
          ["Operational market", `${t.market.market}-PERP · ${t.market.mode}${historical ? " · last snapshot" : ""}`],
          ["Research market", handoff ? handoff.key.split(":").slice(-2).filter(Boolean).join(":") : `${nativeMarket} · Core`],
          ["Research configuration", handoff ? "Generalized PAPER · local inputs" : researchPreset ?? "Native defaults"],
        ]} />
        {market && decision && catalog?.catalog_fingerprint && <ObservedMarketSummary active={active && decision.discovery_eligible}
          scope={{ network: catalog.network, catalogFingerprint: catalog.catalog_fingerprint, markets: [{
            key: marketUniverseKey(market.identity), metadataFingerprint: decision.metadata_fingerprint,
            universeIndex: market.universe_index, listed: market.listed,
          }] }}
        />}
        <a href={pageHref("Markets")}>Market Explorer</a>
      </section>
      <section>
        <h3>AMM configuration</h3>
        <Metrics items={[
          ["Active model", config.amm_model === "CONCENTRATED" ? "Concentrated Liquidity" : "Constant Product"],
          ["Maximum quote distance", bps(config.max_distance_bps)],
          ["Inventory skew", config.inventory_skew_enabled ? "Enabled" : "Disabled"],
          ["Volatility adaptation", config.market_adaptation_enabled ? "Enabled" : "Disabled"],
        ]} />
        <a href={pageHref("AMM Settings")}>AMM settings</a>
        <a href={workspaceHref("paper")}>Asset-aware PAPER controls</a>
      </section>
      <section>
        <h3>Agent intelligence</h3>
        <dl className="overviewEvidence">
          <div><dt>Regime</dt><dd>{agents.regime?.state ?? "Unavailable"}</dd></div>
          <div><dt>Toxic flow</dt><dd>{agents.toxic_flow?.state ?? "Unavailable"}</dd></div>
          <div><dt>Execution quality</dt><dd>{agents.execution_quality?.state ?? "Unavailable"}</dd></div>
          <div><dt>Liquidity quality</dt><dd>{agents.liquidity_quality?.state ?? "Unavailable"}</dd></div>
          <div><dt>Perp crowding</dt><dd>{agents.perp_crowding?.state ?? "Unavailable"}</dd></div>
          <div><dt>Adverse selection · shadow</dt><dd>{agents.predictive_adverse_selection?.state ?? "Unavailable"}</dd></div>
          <div><dt>{historical ? "Last evidence" : "Terminal evidence"}</dt><dd><code title={agents.agent_fingerprint}>{fingerprint(agents.agent_fingerprint)}</code></dd></div>
        </dl>
        <a href={pageHref("Supervisory Agents")}>Supervisory evidence</a>
      </section>
      <section>
        <h3>Research workspaces</h3>
        <a href={workspaceHref("paper")}>Generalized PAPER & advisory evidence</a>
        <p className="muted">Market Eligibility, Funding/Basis and Quote Economics evaluate a selected market or PAPER run.</p>
        <a href={workspaceHref("replay")}>Historical Replay</a>
        <a href={workspaceHref("scenarioComparison")}>Scenario vs historical</a>
        <a href={workspaceHref("marketComparison")}>Market vs research</a>
      </section>
    </div>
  </Panel>;
}
