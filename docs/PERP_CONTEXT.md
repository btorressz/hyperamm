# HyperAMM Phase 7 — Perpetual Market Context

Phase 7 adds Hyperliquid-native perpetual-market context before AMM construction. It is deterministic strategy context, not a new safety authority.

## Provider surfaces

The project pins `hyperliquid-python-sdk >=0.24.0,<0.25`.

Phase 7 uses the existing public `Info` lifecycle:

```text
Info.meta_and_asset_ctxs()
Info.subscribe({"type":"activeAssetCtx","coin":market}, callback)
```

The existing TESTNET execution adapter continues to use:

```text
Info.user_state(account_address)
```

for authoritative account state.

No second public WebSocket manager is created. The existing public market-data adapter owns both L2 and `activeAssetCtx` subscriptions.

## Normalized market context

`PerpMarketContext` contains:

```text
market
market_mid
provider_mid_price
mark_price
oracle_price
funding_rate
open_interest_base
open_interest_notional
mark_oracle_basis_bps
mark_mid_basis_bps
oracle_mid_basis_bps
premium
updated_at
stale
version
source
simulated
```

Raw SDK dictionaries stop at the adapter boundary.

## Market mapping

`meta_and_asset_ctxs()` is mapped by the configured universe `name`. Array position is used only after locating exactly one matching metadata entry. Missing or duplicate mappings are rejected.

## Validation

Phase 7 requires positive finite market-mid, mark and oracle prices, finite funding, non-negative finite open interest, and finite optional premium/provider mid values.

Missing or malformed required context is not converted to neutral zeros.

## Basis formulas

Signs are preserved:

```text
mark_oracle_basis_bps =
    (mark_price - oracle_price) / oracle_price * 10000

mark_mid_basis_bps =
    (mark_price - market_mid) / market_mid * 10000

oracle_mid_basis_bps =
    (oracle_price - market_mid) / market_mid * 10000
```

Basis is first-class explainability/context in Phase 7. It is not an emergency halt condition.

## Open interest

```text
open_interest_notional =
    open_interest_base * mark_price
```

Absolute open interest does not independently widen, reduce, or halt quotes in Phase 7.

## Strategy reference

Raw market fair value remains:

```text
market_fair = (best_bid + best_ask) / 2
```

Phase 7 uses default weights:

```text
mark_weight   = 0.25
oracle_weight = 0.25
mid_weight    = 0.50
```

The bounded blended reference is:

```text
blended_reference =
      market_fair * mid_weight
    + mark_price  * mark_weight
    + oracle_price * oracle_weight
```

The weights must be non-negative and `mark_weight + oracle_weight <= 1`.

## Funding normalization

HyperAMM keeps Hyperliquid's raw current `funding` value as `funding_rate`. It is not annualized.

The default deterministic normalization reference is:

```text
funding_reference_abs_rate = 0.00025
```

This is a strategy normalization scale, not a claim about annualized yield.

```text
funding_score =
    clamp(
        funding_rate / funding_reference_abs_rate,
        -1,
        +1,
    )

funding_shift_bps =
    -funding_score * max_funding_reference_shift_bps
```

The default maximum funding shift is 5 bps.

Positive funding therefore produces a small negative strategy-reference shift; negative funding produces the inverse.

## Total reference bound

After funding:

```text
candidate_reference =
    blended_reference * (1 + funding_shift_bps / 10000)

raw_shift_bps =
    (candidate_reference - market_fair) / market_fair * 10000
```

The final shift is clamped to:

```text
[-max_perp_reference_shift_bps, +max_perp_reference_shift_bps]
```

with a default of 50 bps.

This is a deterministic strategy bound. It is not the Phase 8 oracle-divergence firewall.

## Pipeline composition

```text
normalized market snapshot
        ↓
raw market fair value
        ↓
PerpMarketContext
        ↓
PerpContextPolicy
        ↓
strategy reference price
        ↓
virtual x*y=k AMM recenter
        ↓
reserve-delta sizing
        ↓
optional concentration
        ↓
Phase 5 InventoryPolicy
        ↓
Phase 6 MarketAdaptationPolicy
        ↓
deterministic risk
        ↓
KEEP / CREATE / REPLACE / CANCEL
        ↓
PAPER / guarded TESTNET
```

Phase 7 is not an after-the-fact quote mutation.

## Inventory integration

`InventoryState.position_base` remains the authoritative inventory value.

The inventory decision keeps separate:

```text
market_fair_value
reference_price
reservation_price
```

The reservation price starts from the Phase 7 strategy reference. Phase 5 hard-limit side suppression remains absolute.

Phase 6 still transforms only surviving Phase 5 quotes around the Phase 5 reservation center.

## Position context

`PerpPositionContext` exposes TESTNET observability from the same authoritative `user_state()` snapshot:

```text
signed_position_base
entry_price
leverage_type
leverage_value
liquidation_price
margin_used
position_value
unrealized_pnl
return_on_equity
```

The TESTNET adapter parses `user_state()` once and feeds both Phase 5 inventory and Phase 7 position context. Their signed positions are checked for exact consistency.

PAPER uses its existing fill-ledger position. Account-only fields remain null rather than fabricated.

## Freshness and version authority

The context service maintains a monotonic version for materially changed normalized perp state.

Duplicate identical updates refresh freshness but do not increment the version. Older updates are ignored.

When Phase 7 is enabled, stale context invalidates desired quotes and uses the existing cancellation/degraded-state path.

Final execution authority binds quotes to:

```text
inventory version
market/adaptation version
perp context version
```

A materially newer perp context rejects transmission until quotes are recomputed.

## DEMO

Explicit DEMO mode produces deterministic simulated mark/oracle/funding/OI context and sets:

```text
source = DEMO
simulated = true
```

It never presents simulated values as live Hyperliquid context.

## Phase 7 / Phase 8 boundary

Phase 7 does not add external oracle providers, oracle quorum, cross-venue verification, oracle-deviation kill switches, tiered widen/reduce/halt authority, or institutional risk-firewall expansion.

Hyperliquid native `oraclePx` is strategy context here. External oracle authority remains Phase 8.
