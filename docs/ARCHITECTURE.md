# HyperAMM Architecture

HyperAMM is a virtual-liquidity compiler. It does **not** create or settle against an on-chain constant-product pool. AMM mathematics produces a deterministic liquidity curve; that curve is sampled, normalized and compiled into discrete CLOB quotes.

```text
Hyperliquid public API / explicit demo feed
                 ↓
       market-data adapter
                 ↓
       normalized market state
      BBO · L2 · freshness · mode
                 ↓
          fair-value engine
        fair = (bid + ask) / 2
                 ↓
          virtual AMM core
              x · y = k
                 ↓
         liquidity policy
  constant-product / concentrated
                 ↓
       liquidity discretizer
    price ticks · size precision
                 ↓
        CLOB quote compiler
          bids / asks / size
                 ↓
      deterministic risk checks
 freshness · size · notional · distance
                 ↓
        quote reconciliation
     KEEP/CREATE/REPLACE/CANCEL
                 ↓
         execution adapter
     PAPER (default) / TESTNET
```

## Boundaries

`market_data/` owns Hyperliquid payload parsing and stale/monotonic state. `amm/` contains pure deterministic financial math. `strategy/` owns fair value, configuration and quote generation. `risk/` is an authority boundary that can stop quotes regardless of strategy intent. `execution/` is the only layer allowed to transmit an order, which prevents AMM math from gaining signing authority.

The React terminal consumes Pydantic-normalized REST/WebSocket state only. It never receives private keys, seed phrases or raw SDK objects.

## Runtime

`HyperAmmRuntime` composes services without merging their responsibilities. A strategy refresh reads one normalized snapshot, computes fair value, recenters virtual reserves while preserving `k`, builds quotes, applies risk validation, and reconciles against currently resting strategy orders. PAPER fills are deterministic touch/cross simulations and are explicitly labeled `SIMULATED PAPER FILL`.

## Phase 4.1 execution safety

The sizing path is now explicitly:

```text
fair-value reserve state → constant-product curve → incremental reserve movement
→ AMM-derived sizing → optional concentration weighting → per-side budget scaling
→ CLOB tick/size normalization → risk → serialized execution
```

Strategy intent (`running`) is separate from `quote_health`:

| State | Meaning |
|---|---|
| NO_QUOTES | Stopped; a valid desired ladder may be displayed as a preview only |
| HEALTHY | Enabled, validated, reconciled strategy quotes |
| DEGRADED | Bad feed, generation/risk failure, or venue reconciliation failure; desired ladder and fair value cleared and strategy orders cancelled |
| HALTED | Kill latch active, including cancellation that could not be confirmed |

Missing/non-finite/non-positive/crossed BBO, invalid mid, stale timestamps and any
non-CONNECTED feed state invalidate quoting. Invalid LIVE payloads explicitly
publish degraded state. Freshness uses the exchange timestamp, not just receipt
time. A strategy refresh and the market listener both fail closed; while enabled,
a safety check runs at most one second apart between quote cycles even when the
configured quote interval is long. Venue/network work can delay a check while
it holds the execution lock. HTTP SDK calls have a ten-second timeout.

Transient degradation preserves enabled intent and can recover on the next
valid quote cycle, provided the kill latch is inactive and execution/risk checks
pass. Manual kill disables intent. Resume clears the latch only after successful
cancellation and **does not start the strategy**. A cancellation failure clears
the desired ladder, reports `cancellation unconfirmed`, and latches HALTED;
it does not claim the venue has no orders. Explicit operator recovery is required.

One shared `asyncio.Lock` serializes generation/reconciliation, order creates,
replacements and cancellations, cancel-all, market-driven paper mutations,
venue updates, kill completion and execution-adapter/configuration changes.
Kill revokes authority before waiting for the lock, then cancels after in-flight
work finishes. Authority and fresh market state are checked before each create,
again inside the TESTNET adapter after SDK setup, and after reconciliation.
Signed worker-thread calls finish before a cancelled waiter releases the lock.
Consequently successful kill completion is a cancellation barrier: an older
reconciliation cannot subsequently leave a newly transmitted order active.

The terminal displays quote health and the existing strategy error banner.
TESTNET order history exposes venue status and fill quantities; the terminal
payload also includes the last venue reconciliation timestamp and error.
PAPER retains its existing `SIMULATED PAPER FILL` labeling and remains the default.


## Phase 5 inventory-aware strategy layer

The accepted Phase 4.1 AMM path remains intact. Phase 5 is a strategy transform:

```text
normalized market state
        ↓
fair value
        ↓
virtual x*y=k AMM
        ↓
reserve-delta liquidity
        ↓
optional concentration
        ↓
neutral QuoteLevel ladder
        ↓
normalized InventoryState
        ↓
InventoryPolicy
  reservation-price shift
  side-size multipliers
  hard-limit suppression
        ↓
deterministic risk
        ↓
KEEP / CREATE / REPLACE / CANCEL
        ↓
PAPER / guarded TESTNET
```

PAPER position is the signed sum of actual simulated fills: BID fills add base and ASK fills subtract base. Resting, cancelled, rejected, and unknown orders do not create PAPER inventory.

TESTNET position comes from the official Hyperliquid SDK account-state path (`Info.user_state(account_address)`) and normalizes the configured market's signed `assetPositions[].position.szi`. Position refresh occurs before TESTNET quote generation and during venue reconciliation. Missing/stale state, malformed state, reconciliation errors, or UNKNOWN economic exposure invalidate inventory-aware execution instead of assuming zero.

Generated decisions bind to an inventory version. Final transmission authority verifies that the current version still matches the version used to generate the ladder. Fill/venue events wake the existing strategy loop; they do not introduce a second execution lock or reconciliation system.


## Phase 6 market-adaptation layer

Phase 6 adds one deterministic transform after Phase 5 and before risk:

```text
normalized market state
        ↓
fair value
        ↓
virtual x*y=k AMM
        ↓
reserve-delta sizing
        ↓
optional concentration
        ↓
Phase 5 InventoryPolicy
  reservation center
  inventory size skew
  hard-limit suppression
        ↓
Phase 6 MarketAdaptationPolicy
  rolling mid-price volatility
  top-N L2 imbalance
  widening-only spread multiplier
  bounded variable-liquidity reduction
        ↓
deterministic risk on FINAL prices/sizes/distance/notional
        ↓
KEEP / CREATE / REPLACE / CANCEL
        ↓
PAPER / guarded TESTNET
```

`MarketPriceHistory` is bounded in memory and accepts only fresh normalized snapshots with a positive finite mid price and unique sequence/timestamp identity. Replays do not inflate volatility samples. History is cleared when market/feed mode changes.

Phase 6 uses the Phase 5 reservation price as its strategy center without overwriting either fair value or reservation price. The existing Phase 5 hard-limit side suppression happens first; because Phase 6 only transforms the surviving quote list, it cannot re-enable a forbidden side.

The runtime binds final quotes to both the Phase 5 inventory version and the Phase 6 market-history version. Final execution authority refreshes the normalized market snapshot and rejects transmission if either material dependency changed after quote generation. The existing shared execution lock remains the serialization boundary.

Startup volatility warmup is not a failure: if fewer than the configured minimum observations exist, realized volatility is `None`, the regime is `WARMING_UP`, and all Phase 6 spread/size multipliers are neutral. Invalid book state or invalid/non-finite Phase 6 math after that point follows the existing invalidation/cancel semantics.


## Phase 7 perpetual strategy-reference layer

Phase 7 inserts one deterministic context decision before AMM construction:

```text
normalized market snapshot
        ↓
raw market fair value
        ↓
normalized PerpMarketContext
        ↓
PerpContextPolicy
        ↓
bounded strategy reference
        ↓
virtual AMM recenter
        ↓
reserve-delta sizing / concentration
        ↓
Phase 5 inventory
        ↓
Phase 6 market adaptation
        ↓
existing deterministic risk/reconciliation/execution
```

The existing public Hyperliquid `Info` client owns both `l2Book` and `activeAssetCtx` subscriptions. `meta_and_asset_ctxs()` is used for bootstrap and maps by universe name. No second public WebSocket lifecycle is introduced.

Final execution authority binds the generated ladder to inventory, market/adaptation, and perp-context versions. Stale or materially changed perp context cannot transmit an old decision. Phase 7 does not add Phase 8 oracle-firewall authority.


## Phase 8 reference integrity and final risk authority

Phase 8 is intentionally downstream of all strategy transforms:

```text
Hyperliquid normalized market/perp state
        ↓
Phase 7 strategy reference
        ↓
AMM / reserve-delta sizing / concentration
        ↓
Phase 5 inventory authority
        ↓
Phase 6 market adaptation
        ↓
desired strategy quotes
        ↓
normalized reference evidence
        ├── RedStone primary oracle
        ├── Hyperliquid native oracle
        ├── Kraken exchange BBO midpoint
        ├── CoinGecko aggregate reference
        ├── Hyperliquid L2 midpoint
        └── Hyperliquid mark
        ↓
ReferenceConsensus + signed deviation matrix
        ↓
projected exposure / PnL / liquidation evidence
        ↓
RiskFirewall
 NORMAL / WIDEN / REDUCE / HALT
        ↓
authorized quote ladder
        ↓
existing validate_quotes()
        ↓
FinalQuoteAuthorization
        ↓
existing reconciliation + execution adapters
```

Provider networking remains in `references/`. The firewall does not know HTTP/WebSocket payload formats. Raw external payloads are normalized before they can influence risk authority.

Phase 8 uses the existing execution lock; no second lock hierarchy is introduced. Provider tasks only update their own normalized evidence and wake the existing strategy loop on material changes. CREATE/REPLACE actions still pass through `OrderManager` and the same execution adapters.

Automatic risk HALT does not set the manual kill latch. It produces an empty authorized ladder and uses existing reconciliation to cancel resting strategy orders. Recovery requires deterministic hysteresis and consecutive healthy confirmations. Manual kill still disables strategy intent and cannot be cleared by automatic firewall recovery.

Immediately before transmission, authority rechecks market/adaptation, inventory, perp, reference and risk versions plus the current authorized quote fingerprint. Stale authorization is rejected before the execution adapter is allowed to submit an order.
