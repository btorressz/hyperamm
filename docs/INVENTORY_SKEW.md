# HyperAMM Phase 5 — Inventory Skew

Phase 5 adds deterministic inventory-aware market making without changing the accepted Phase 4.1 AMM invariant, liquidity curve, risk authority, or reconciliation path.

## Signed inventory

HyperAMM uses signed base inventory:

- BID economic fills increase base inventory.
- ASK economic fills decrease base inventory.
- Positive deviation is long relative to target.
- Negative deviation is short relative to target.

PAPER inventory is derived from the existing fill ledger. OPEN, CANCELLED, REJECTED, and UNKNOWN orders are not inventory.

TESTNET inventory is authoritative account state normalized from the configured market in Hyperliquid `Info.user_state(account_address)`. The strategy never substitutes zero when authoritative inventory is unavailable.

## Target, soft limit, and hard limit

`target_inventory_base` is the desired signed position.

`soft_inventory_limit_base` defines the normal-skew scale. With `d = position - target`:

```text
inventory_ratio = d / soft_inventory_limit_base
r = clamp(inventory_ratio, -1, 1)
```

The unclamped ratio is retained for monitoring; `r` is the bounded input to normal price/size skew.

`hard_inventory_limit_base` is a deterministic safety bound around target. It is separate from the soft limit:

- `d >= hard_limit`: BID quotes are suppressed; inventory-reducing ASK quotes may continue.
- `d <= -hard_limit`: ASK quotes are suppressed; inventory-reducing BID quotes may continue.

Hard-limit suppression remains active even when normal inventory skew is disabled.

## Reservation price

Fair value remains the market-derived state. Phase 5 computes a separate strategy reservation price:

```text
price_skew_bps = -r * max_inventory_price_skew_bps
reservation_price = fair_value * (1 + price_skew_bps / 10000)
```

A long position shifts the reservation price down. A short position shifts it up.

The neutral AMM ladder is transformed by the bounded reservation/fair-value factor, then normal tick normalization is applied. Final bids are constrained below fair value and asks above fair value, and the ladder must remain uncrossed.

## Side-size skew

Phase 5 applies one bounded multiplier to each side:

```text
bid_multiplier = clamp(1 - inventory_size_skew_strength * r, min_multiplier, max_multiplier)
ask_multiplier = clamp(1 + inventory_size_skew_strength * r, min_multiplier, max_multiplier)
```

Because each level on a side receives the same multiplier, the Phase 4.1 AMM-derived within-side profile remains intact apart from deterministic size rounding. Downstream max-order-size, aggregate-notional, and quote-distance risk checks remain authoritative.

## Freshness and execution safety

PAPER state is local and deterministic.

For TESTNET, account state is refreshed at strategy start, before inventory-aware quote generation, and during the existing venue reconciliation loop. A configurable `inventory_stale_after_seconds` bound prevents indefinite cached use.

Missing, stale, malformed, or economically uncertain TESTNET inventory fails closed. UNKNOWN venue exposure and unresolved reconciliation errors make inventory state unsafe; desired quotes are invalidated and strategy orders are cancelled under the existing Phase 4.1 semantics.

A monotonic inventory version is attached to the runtime decision. Final execution authority checks reject transmission if the inventory version has changed since quote generation.

## Fill-driven requoting

PAPER fills update the fill-derived inventory version and wake the existing strategy loop. TESTNET user-fill/order events already wake authoritative venue reconciliation; reconciliation refreshes position state and wakes the strategy loop. Requoting continues to use the existing KEEP / CREATE / REPLACE / CANCEL system and the shared execution lock.

## API and terminal

`GET /api/v1/positions` returns normalized inventory state plus reservation price, effective ratio, side-size multipliers, and hard-limit state.

`/ws/terminal` includes the same normalized inventory block. Raw Hyperliquid account payloads are never exposed.

The React terminal adds Inventory & Skew metrics, a compact hard-limit gauge, grouped strategy controls, and quote-level neutral/final explainability metadata.

## Scope boundary

Phase 5 does not add volatility models, order-book imbalance, funding adaptation, perp basis, external oracles, optimization solvers, AI/LLM agents, or mainnet execution. Those remain later roadmap work.
