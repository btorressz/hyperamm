import type { TerminalState } from "../types";
import { QuoteDistribution } from "./LiquidityDistributionChart";
import { Panel, Metrics } from "./TerminalPrimitives";
import { quantity, price, percentage, number } from "../utils/format";
export function InventorySkewChart({ t }: { t: TerminalState }) {
  const i = t.inventory;
  return (
    <Panel title="Inventory skew" meta={i?.hard_limit_state ?? "No evidence"}>
      <QuoteDistribution quotes={t.authorized_quotes} x="distance_bps" />
      <Metrics
        items={[
          ["Position", quantity(i?.position_base)],
          ["Target", quantity(i?.target_base)],
          ["Ratio", percentage(i?.inventory_ratio)],
          ["Reservation", price(i?.reservation_price)],
          ["BID multiplier", number(i?.bid_size_multiplier) + "×"],
          ["ASK multiplier", number(i?.ask_size_multiplier) + "×"],
        ]}
      />
    </Panel>
  );
}
