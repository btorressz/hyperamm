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
