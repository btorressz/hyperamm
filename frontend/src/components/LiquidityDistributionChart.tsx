import { useState } from "react";
import type { TerminalState, Quote } from "../types";
import { finite, number, quantity } from "../utils/format";
import { Panel, Empty } from "./TerminalPrimitives";
export function QuoteDistribution({
  quotes,
  x = "price",
}: {
  quotes: Quote[];
  x?: "price" | "distance_bps";
}) {
  const points = quotes
    .map((q) => ({ q, x: finite(q[x]), y: finite(q.size) }))
    .filter(
      (p): p is { q: Quote; x: number; y: number } =>
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
        aria-label={`Backend quote size against ${x === "price" ? "price" : "distance in basis points"}`}
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
          <g key={`${q.side}-${q.level_index}`}>
            <title>
              {q.side} L{q.level_index}: {number(pos)} / size {quantity(y)}
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
        <span>Size in base units · backend quote evidence</span>
      </div>
    </div>
  );
}
export function LiquidityDistributionChart({ t }: { t: TerminalState }) {
  const [stage, setStage] = useState("Authorized");
  const quotes =
    stage === "Raw AMM"
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
        {["Raw AMM", "Strategy", "Authorized"].map((s) => (
          <button
            key={s}
            disabled={
              s === "Raw AMM" &&
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
      <p className="muted panelNote">
        Raw lineage covers retained strategy levels; upstream suppressed levels
        are unavailable.
      </p>
    </Panel>
  );
}
