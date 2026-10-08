import type { TerminalState } from "../types";
import { QuickStrategyControl } from "../components/QuickStrategyControl";
import { LiquidityPipeline } from "../components/LiquidityPipeline";
import { QuoteLadder } from "../components/QuoteLadder";
import { InventoryPanel } from "../components/InventoryPanel";
import { MarketAdaptationPanel } from "../components/MarketAdaptationPanel";
import { PerpContextPanel } from "../components/PerpContextPanel";
import { Panel, Metrics } from "../components/TerminalPrimitives";
import { number, price, fingerprint } from "../utils/format";
export function Strategy({ t }: { t: TerminalState }) {
  return (
    <div className="stack">
      <div className="grid twoColumns">
        <QuickStrategyControl t={t} />
        <Panel
          title="Current virtual pool & authorization"
          meta={t.strategy.quote_health}
        >
          <Metrics
            items={[
              ["AMM model", t.strategy.config.amm_model],
              [
                "Strategy reference",
                price(t.perp_context?.strategy_reference_price),
              ],
              ["Virtual base", number(t.pool?.reserve_base)],
              ["Virtual quote", number(t.pool?.reserve_quote)],
              ["Invariant k", number(t.pool?.k)],
              [
                "Final authorization",
                t.risk_authorization.authorized ? "AUTHORIZED" : "BLOCKED",
              ],
              [
                "Final authorization envelope",
                fingerprint(t.risk_authorization.authorization_fingerprint),
              ],
            ]}
          />
        </Panel>
      </div>
      <LiquidityPipeline t={t} />
      <div className="grid twoColumns">
        <InventoryPanel t={t} />
        <MarketAdaptationPanel t={t} />
      </div>
      <PerpContextPanel t={t} />
      {[
        ["Pre-agent strategy", t.strategy_quotes],
        ["Post-agent", t.agent_quotes],
        ["Final authorized", t.authorized_quotes],
      ].map(([label, quotes]) => (
        <div key={String(label)}>
          <h2>{String(label)}</h2>
          <QuoteLadder quotes={quotes as typeof t.quotes} orders={t.orders} />
        </div>
      ))}
    </div>
  );
}
