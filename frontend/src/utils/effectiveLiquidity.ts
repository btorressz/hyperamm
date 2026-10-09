import type { Decimalish, Quote } from "../types";

// Exact decimal grouping/sums for backend economics. Number is used only by
// charts/formatters, never to identify ticks or to authorize trading.
type Decimal = { units: bigint; scale: number };
function decimal(value: Decimalish): Decimal {
  const text = String(value);
  const match = /^(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(text);
  if (!match || text.length > 512) throw new Error("Invalid decimal evidence");
  const exponent = Number(match[3] ?? 0);
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 512)
    throw new Error("Decimal evidence outside display range");
  let units = BigInt(match[1] + (match[2] ?? ""));
  let scale = (match[2]?.length ?? 0) - exponent;
  if (scale < 0) { units *= 10n ** BigInt(-scale); scale = 0; }
  while (scale > 0 && units % 10n === 0n) { units /= 10n; scale--; }
  return { units, scale };
}
function text(d: Decimal): string {
  const raw = d.units.toString().padStart(d.scale + 1, "0");
  return d.scale ? raw.slice(0, -d.scale) + "." + raw.slice(-d.scale) : raw;
}
function add(a: Decimal, b: Decimal): Decimal {
  const scale = Math.max(a.scale, b.scale);
  return { units: a.units * 10n ** BigInt(scale - a.scale) +
    b.units * 10n ** BigInt(scale - b.scale), scale };
}
export type PriceGroup = {
  side: "BID" | "ASK";
  price: string;
  quantity: string;
  notional: string;
  level_indices: number[];
  distance_bps: Decimalish;
};
export function effectiveLiquidity(quotes: Quote[]) {
  try {
    const groups = new Map<string, PriceGroup>();
    const slots = new Set<string>();
    for (const q of quotes) {
      const price = decimal(q.price), size = decimal(q.size);
      const slot = `${q.side}:${q.level_index}`;
      if (!['BID', 'ASK'].includes(q.side) || slots.has(slot) ||
          !Number.isSafeInteger(q.level_index) || q.level_index < 0 ||
          price.units <= 0n || size.units <= 0n ||
          !Number.isFinite(Number(q.price)) || !Number.isFinite(Number(q.size)))
        throw new Error("Invalid quote ladder");
      slots.add(slot);
      const p = text(price), key = `${q.side}:${p}`;
      const group = groups.get(key) ?? { side: q.side, price: p, quantity: "0",
        notional: "0", level_indices: [], distance_bps: q.distance_bps };
      group.quantity = text(add(decimal(group.quantity), size));
      group.notional = text(add(decimal(group.notional), {
        units: price.units * size.units, scale: price.scale + size.scale }));
      group.level_indices.push(q.level_index);
      groups.set(key, group);
    }
    const depth = [...groups.values()].sort((a, b) => {
      if (a.side !== b.side) return a.side.localeCompare(b.side);
      const x = decimal(a.price), y = decimal(b.price), scale = Math.max(x.scale, y.scale);
      const diff = x.units * 10n ** BigInt(scale - x.scale) - y.units * 10n ** BigInt(scale - y.scale);
      return diff < 0n ? -1 : diff > 0n ? 1 : 0;
    });
    depth.forEach(g => g.level_indices.sort((a, b) => a - b));
    const bids = depth.filter(g => g.side === "BID"), asks = depth.filter(g => g.side === "ASK");
    if (bids.length && asks.length) {
      const bid = decimal(bids[bids.length - 1].price), ask = decimal(asks[0].price);
      const scale = Math.max(bid.scale, ask.scale);
      if (bid.units * 10n ** BigInt(scale - bid.scale) >= ask.units * 10n ** BigInt(scale - ask.scale))
        throw new Error("Crossed quote ladder");
    }
    const warnings = (["BID", "ASK"] as const).flatMap(side => {
      const logical = quotes.filter(q => q.side === side).length;
      const unique = depth.filter(g => g.side === side).length;
      return logical > unique ? [`${logical} logical ${side} slots produced ${unique} distinct executable ${side} prices. Slots are preserved.`] : [];
    });
    return { available: true, logical_slots: quotes.length, effective_bid_levels: bids.length,
      effective_ask_levels: asks.length, price_groups: depth, warnings };
  } catch {
    return { available: false, logical_slots: 0, effective_bid_levels: 0,
      effective_ask_levels: 0, price_groups: [] as PriceGroup[], warnings: [] as string[] };
  }
}
