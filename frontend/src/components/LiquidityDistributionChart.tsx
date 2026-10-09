import { useState } from "react";
import type { TerminalState, Quote } from "../types";
import { finite, number, quantity } from "../utils/format";
import { Panel, Empty } from "./TerminalPrimitives";
import { effectiveLiquidity } from "../utils/effectiveLiquidity";
import { EffectiveLiquidity } from "./EffectiveLiquidity";
export function QuoteDistribution({
  quotes,
  x = "price",
}: {
  quotes: Quote[];
  x?: "price" | "distance_bps";
}) {
  const depth = effectiveLiquidity(quotes);
  if (!depth.available) return <Empty>Effective liquidity unavailable: invalid quote evidence.</Empty>;
  const points = depth.price_groups
    .map((q) => ({ q, x: finite(q[x]), y: finite(q.quantity) }))
    .filter(
      (p): p is { q: typeof depth.price_groups[number]; x: number; y: number } =>
        p.x !== null && p.y !== null,
    );
  if (!points.length) return <Empty>No quote evidence for this stage.</Empty>;
  const lo = Math.min(...points.map((p) => p.x)),
    hi = Math.max(...points.map((p) => p.x)),
    max = Math.max(...points.map((p) => p.y)),
    px = (v: number) => 50 + ((v - lo) / (hi - lo || 1)) * 610,
    py = (v: number) => 170 - (v / (max || 1)) * 130;
  return (
    <div className="distribution">
      <svg
        viewBox="0 0 710 215"
        role="img"
        aria-label={`Aggregate quote size at executable tick against ${x === "price" ? "price" : "distance in basis points"}`}
      >
        <line x1="50" x2="665" y1="170" y2="170" stroke="#32485e" />
        <line x1="50" x2="50" y1="30" y2="170" stroke="#32485e" />
        {[0, 0.5, 1].map((r) => (
          <g key={r}>
            <line
              x1="50"
              x2="665"
              y1={py(max * r)}
              y2={py(max * r)}
              stroke="#182c3e"
            />
            <text x="5" y={py(max * r) + 4}>
              {quantity(max * r)}
            </text>
          </g>
        ))}
        {points.map(({ q, x: pos, y }) => (
          <g key={`${q.side}-${q.price}`}>
            <title>
              {`${q.side} levels ${q.level_indices.join(", ")}: ${number(pos)} / aggregate size ${quantity(y)} / notional ${q.notional}`}
            </title>
            <rect
              x={
                px(pos) +
                (x === "distance_bps" ? (q.side === "BID" ? -6 : 1) : -5)
              }
              y={py(y)}
              width={x === "distance_bps" ? 5 : 10}
              height={170 - py(y)}
              rx="2"
              fill={q.side === "BID" ? "#35c99a" : "#ee7485"}
            />
          </g>
        ))}
        <text x="50" y="193">
          {number(lo)}
        </text>
        <text x="610" y="193">
          {number(hi)}
        </text>
        <text x="295" y="211">
          {x === "price" ? "Price" : "Distance (bps)"} →
        </text>
      </svg>
      <div className="chartLegend">
        <span className="bidText">● BID</span>
        <span className="askText">● ASK</span>
        <span>Aggregate size in base units · one bar per side and executable tick</span>
      </div>
    </div>
  );
}
export function LiquidityDistributionChart({ t }: { t: TerminalState }) {
  const [stage, setStage] = useState("Authorized");
  const quotes =
    stage === "Neutral AMM"
      ? t.strategy_quotes
          .filter((q) => q.neutral_price != null && q.neutral_size != null)
          .map((q) => ({
            ...q,
            price: q.neutral_price!,
            size: q.neutral_size!,
          }))
      : stage === "Strategy"
        ? t.strategy_quotes
        : t.authorized_quotes;
  return (
    <Panel title="AMM liquidity distribution" meta={stage}>
      <div className="segmented chartToolbar">
        {["Neutral AMM", "Strategy", "Authorized"].map((s) => (
          <button
            key={s}
            disabled={
              s === "Neutral AMM" &&
              !t.strategy_quotes.some((q) => q.neutral_price != null)
            }
            aria-pressed={s === stage}
            onClick={() => setStage(s)}
          >
            {s}
          </button>
        ))}
      </div>
      <QuoteDistribution quotes={quotes} />
      <EffectiveLiquidity quotes={quotes} configured={t.strategy.config.levels_per_side} stage={stage} />
      <p className="muted panelNote">
        Neutral AMM lineage shows tick-normalized CLOB quotes, separate from
        mathematical curve sampling. It covers retained strategy levels;
        upstream suppressed levels are unavailable.
      </p>
    </Panel>
  );
}
