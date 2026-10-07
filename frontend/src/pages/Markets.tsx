import type { TerminalState } from "../types";
import { OrderBook } from "../components/OrderBook";
import { PriceLiquidityChart } from "../components/PriceLiquidityChart";
import { ReferenceSourcesPanel } from "../components/RiskFirewallPanel";
import { Panel, Metrics } from "../components/TerminalPrimitives";
import {
  price,
  quantity,
  number,
  percentage,
  bps,
  timestamp,
} from "../utils/format";
export function Markets({ t }: { t: TerminalState }) {
  const p = t.perp_context,
    m = t.market;
  return (
    <div className="stack">
      <h1>Market microstructure</h1>
      <div className="grid marketColumns">
        <PriceLiquidityChart t={t} />
        <OrderBook m={m} />
      </div>
      <Panel
        title="Venue & perpetual context"
        meta={`${m.mode} · ${m.connection_state} · ${m.stale ? "STALE" : "FRESH"}`}
      >
        <Metrics
          items={[
            ["Best BID", price(m.best_bid)],
            ["Best ASK", price(m.best_ask)],
            ["Mid", price(m.mid_price)],
            ["Fair value", price(t.fair_value)],
            ["Mark", price(p?.mark_price)],
            ["HL Oracle", price(p?.oracle_price)],
            ["Consensus", price(t.reference_consensus?.consensus_price)],
            ["Funding", percentage(p?.funding_rate, 4)],
            ["Open interest (base)", quantity(p?.open_interest_base)],
            ["Open interest (notional)", number(p?.open_interest_notional)],
            ["Mark / oracle basis", bps(p?.mark_oracle_basis_bps)],
            ["Mark / mid basis", bps(p?.mark_mid_basis_bps)],
            [
              "Realized volatility",
              percentage(t.market_adaptation?.realized_volatility),
            ],
            ["Book imbalance", percentage(t.market_adaptation?.book_imbalance)],
            ["Feed update", timestamp(m.latest_valid_update)],
            ["Perp update", timestamp(p?.updated_at)],
          ]}
        />
      </Panel>
      <ReferenceSourcesPanel t={t} />
    </div>
  );
}
