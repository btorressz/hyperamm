import type { TerminalState } from "../types";
import { Panel, Metrics } from "./TerminalPrimitives";
import { bps, number, percentage } from "../utils/format";
export function StrategyAttribution({ t }: { t: TerminalState }) {
  const m = t.market_adaptation,
    a = t.agents.supervisor,
    r = t.risk_firewall.decision;
  const mult = (x: unknown) => number(x) + "×";
  return (
    <Panel title="Strategy transformation" meta="Current backend factors">
      <Metrics
        items={[
          ["Perp reference shift", bps(t.perp_context?.reference_shift_bps)],
          ["Inventory skew", bps(t.inventory?.price_skew_bps)],
          ["Volatility score", number(m?.volatility_score)],
          ["Book imbalance", percentage(m?.book_imbalance)],
          [
            "Market spread / size",
            mult(m?.spread_multiplier) +
              " / " +
              mult(m?.global_size_multiplier),
          ],
          ["Agent spread", mult(a?.spread_multiplier)],
          [
            "Agent BID / ASK",
            mult(a?.bid_size_multiplier) + " / " + mult(a?.ask_size_multiplier),
          ],
          [
            "Risk spread / size",
            mult(r?.spread_multiplier) + " / " + mult(r?.size_multiplier),
          ],
        ]}
      />
      <p className="muted panelNote">
        Multiplicative policies; values are not additive spread contributions.
      </p>
    </Panel>
  );
}
