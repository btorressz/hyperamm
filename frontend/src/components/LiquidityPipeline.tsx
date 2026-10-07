import { useState } from "react";
import type { TerminalState, Quote } from "../types";
import { price, quantity, bps, number, fingerprint } from "../utils/format";
import { Panel, Empty } from "./TerminalPrimitives";
export function LiquidityPipeline({ t }: { t: TerminalState }) {
  const [selected, setSelected] = useState("");
  const all = new Map<string, Quote>();
  for (const q of [
    ...t.strategy_quotes,
    ...t.agent_quotes,
    ...t.authorized_quotes,
  ])
    all.set(`${q.side}:${q.level_index}`, q);
  const key = all.has(selected) ? selected : all.keys().next().value,
    q = key ? all.get(key) : undefined;
  if (!q)
    return (
      <Panel title="Liquidity pipeline" meta="Backend lineage">
        <Empty>
          No quote lineage yet. Start or refresh the strategy preview.
        </Empty>
      </Panel>
    );
  const match = (quotes: Quote[]) =>
      quotes.find((x) => x.side === q.side && x.level_index === q.level_index),
    strategy = match(t.strategy_quotes),
    agent = match(t.agent_quotes),
    final = match(t.authorized_quotes),
    resting = t.orders.find(
      (o) =>
        o.side === q.side &&
        o.level_index === q.level_index &&
        ["OPEN", "PARTIALLY_FILLED"].includes(o.status),
    );
  const stages: Array<[string, unknown, unknown, string]> = [
    ["Raw AMM", q.neutral_price, q.neutral_size, "Retained lineage"],
    [
      "Inventory",
      q.pre_market_adaptation_price ?? q.inventory_adjusted_price,
      q.pre_market_adaptation_size,
      t.inventory?.hard_limit_state ?? "Unavailable",
    ],
    [
      "Market adaptation",
      strategy?.price,
      strategy?.size,
      number(q.market_spread_multiplier) +
        "× spread / " +
        number(q.market_size_multiplier) +
        "× size",
    ],
    [
      "Perp context",
      q.perp_reference_price,
      null,
      "Reference applied before AMM generation",
    ],
    [
      "Supervisory agents",
      agent?.price,
      agent?.size,
      agent
        ? "SURVIVED · " +
          number(q.agent_spread_multiplier) +
          "× / " +
          number(q.agent_size_multiplier) +
          "×"
        : "SUPPRESSED / UNAVAILABLE",
    ],
    [
      "Risk",
      q.pre_risk_price,
      q.pre_risk_size,
      "Input · " +
        t.risk_firewall.state +
        " · " +
        number(q.risk_spread_multiplier) +
        "× / " +
        number(q.risk_size_multiplier) +
        "×",
    ],
    [
      "Final authorized",
      final?.price,
      final?.size,
      final ? "SURVIVED · " + final.state : "SUPPRESSED / BLOCKED",
    ],
    [
      "Resting CLOB",
      resting?.price,
      resting?.size,
      resting?.status ?? "NOT RESTING",
    ],
  ];
  return (
    <Panel title="Liquidity pipeline" meta="Read-only transformation evidence">
      <div className="pipelineIntro">
        <label>
          Quote level{" "}
          <select
            aria-label="Quote lineage level"
            value={key}
            onChange={(e) => setSelected(e.target.value)}
          >
            {[...all].map(([k, v]) => (
              <option key={k} value={k}>
                {v.side} · Level {v.level_index}
              </option>
            ))}
          </select>
        </label>
        <span>
          Final distance {bps(final?.distance_bps)} · authorization{" "}
          {fingerprint(final?.authorization_fingerprint)}
        </span>
      </div>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Stage</th>
              <th>Price / reference</th>
              <th>Size</th>
              <th>State / factors</th>
            </tr>
          </thead>
          <tbody>
            {stages.map(([label, p, size, status], i) => (
              <tr key={label}>
                <td>
                  <span className="stageNumber">{i + 1}</span>
                  {label}
                </td>
                <td>{price(p)}</td>
                <td>{quantity(size)}</td>
                <td>{status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted panelNote">
        Perp context supplies the AMM reference upstream. Missing stages stay
        unavailable; suppressed levels are not reconstructed.
      </p>
    </Panel>
  );
}
