import type { MarketState, Level } from "../types";
import { finite, price, quantity, bps, percentage } from "../utils/format";
export function OrderBook({ m }: { m: MarketState }) {
  const asks = (m.book?.asks ?? []).slice(0, 7),
    bids = (m.book?.bids ?? []).slice(0, 7),
    bid = finite(m.best_bid),
    ask = finite(m.best_ask),
    mid = finite(m.mid_price),
    spread = bid !== null && ask !== null ? ask - bid : null;
  const depth = (rows: Level[]) =>
      rows.reduce((sum, row) => sum + (finite(row.size) ?? 0), 0),
    ad = depth(asks),
    bd = depth(bids),
    max = Math.max(ad, bd, 1e-12);
  const rows = (levels: Level[], side: string) => {
    let cumulative = 0;
    const result = levels.map((x, i) => {
      cumulative += Number(x.size);
      return (
        <div
          className={`bookRow ${side}`}
          key={`${side}-${i}`}
          style={{
            background: `linear-gradient(to left,${side === "bid" ? "#12342d" : "#36212a"} ${(cumulative / max) * 100}%,transparent 0)`,
          }}
        >
          <span>{price(x.price)}</span>
          <span>{quantity(x.size)}</span>
          <span>{quantity(cumulative)}</span>
        </div>
      );
    });
    return side === "ask" ? result.reverse() : result;
  };
  return (
    <section className="panel orderbook">
      <div className="panelHead">
        <b>L2 order book</b>
        <span>
          {m.simulated ? "DEMO / SIMULATED" : "Hyperliquid LIVE"} ·{" "}
          {m.stale ? "STALE" : "FRESH"}
        </span>
      </div>
      <div className="bookHeader">
        <span>Price</span>
        <span>Size</span>
        <span>Cumulative</span>
      </div>
      {rows(asks, "ask")}
      <div className="midline">
        <b>{price(m.mid_price)}</b>
        <span>
          spread {price(spread)} ·{" "}
          {bps(spread !== null && mid ? (spread / mid) * 10000 : null)}
        </span>
      </div>
      {rows(bids, "bid")}
      {!m.book && <p className="emptyEvidence">L2 evidence unavailable</p>}
      <div className="bookFooter">
        <span>Seq {m.book?.sequence ?? "—"}</span>
        <span>
          7-level imbalance {percentage(ad + bd ? (bd - ad) / (bd + ad) : null)}
        </span>
      </div>
    </section>
  );
}
