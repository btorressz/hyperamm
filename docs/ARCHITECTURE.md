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
