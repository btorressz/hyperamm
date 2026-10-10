import type { Quote, Order } from "../types";
import { quoteEvidence, type QuoteStage } from "../utils/quoteEvidence";
import { price, quantity, bps, number } from "../utils/format";

export function QuoteLadder({ quotes, orders, stage = "STRATEGY", historical = false }: {
  quotes: Quote[];
  orders: Order[];
  stage?: QuoteStage;
  historical?: boolean;
}) {
  return (
    <section className="panel quotePanel">
      <div className="panelHead">
        <b>AMM Quote Ladder</b>
        <span>{stage} · quote evidence is not venue confirmation</span>
      </div>
      <div className="tableWrap">
        <table>
          <thead><tr>
            <th>Level</th><th>Side</th><th>Price</th><th>Size</th><th>Distance</th>
            <th>Inventory</th><th>Market</th><th>Agents</th><th>Risk</th><th>Order evidence</th>
          </tr></thead>
          <tbody>
            {quotes.map((q) => {
              const evidence = quoteEvidence(q, orders, stage, historical);
              return (
                <tr key={q.side + ":" + q.level_index}>
                  <td>{q.level_index + 1}</td>
                  <td className={q.side === "BID" ? "bidText" : "askText"}>{q.side}</td>
                  <td title={q.neutral_price != null
                    ? "Fair " + price(q.market_fair_value) + " · Perp ref " + price(q.perp_reference_price) +
                      " · AMM " + price(q.neutral_price) + " · Inventory " +
                      price(q.inventory_adjusted_price) + " · Pre-risk " + price(q.pre_risk_price)
                    : undefined}>{price(q.price)}</td>
                  <td title={q.pre_risk_size != null ? "Pre-risk " + quantity(q.pre_risk_size) :
                    q.neutral_size != null ? "Neutral AMM size " + quantity(q.neutral_size) : undefined}>
                    {quantity(q.size)}
                  </td>
                  <td>{bps(q.distance_bps)}</td>
                  <td><span className="statePill" title={q.inventory_intent ?? undefined}>
                    {q.inventory_effect ?? "NEUTRAL"}</span></td>
                  <td><span className="statePill" title={q.pre_market_adaptation_price != null
                    ? "Pre-market " + price(q.pre_market_adaptation_price) + " / " +
                      quantity(q.pre_market_adaptation_size) : undefined}>
                    {q.volatility_effect ?? "NEUTRAL"} · {q.market_spread_multiplier != null ?
                      number(q.market_spread_multiplier) + "x" : "—"}
                  </span></td>
                  <td><span className="statePill" title={q.pre_agent_price != null
                    ? "Pre-agent " + price(q.pre_agent_price) + " / " + quantity(q.pre_agent_size)
                    : undefined}>{q.agent_regime ?? "—"} · {q.agent_spread_multiplier != null ?
                      number(q.agent_spread_multiplier) + "x" : "—"}
                  </span></td>
                  <td><span className="statePill" title={q.pre_risk_price != null
                    ? "Pre-risk " + price(q.pre_risk_price) + " / " + quantity(q.pre_risk_size)
                    : undefined}>{q.risk_state ?? "—"} · {q.risk_spread_multiplier != null ?
                      number(q.risk_spread_multiplier) + "x" : "—"}
                  </span></td>
                  <td><span className="statePill" title={evidence.orderId ?? undefined}>
                    {evidence.label}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted panelNote">
        Proposal stages are not resting orders. Authorized quotes are matched to retained
        order evidence by side, level, price and size; an unmatched quote is not a fill
        or a confirmed open order. Current venue status requires separate reconciliation evidence.
      </p>
    </section>
  );
}
