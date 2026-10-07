# Market Data Domain

The `market_data` package owns normalized market observations and perpetual context used by strategy, risk, agents, accounting marks and terminal observability.

It is the first evidence layer in the live pipeline.

## Files

| File | Responsibility |
|---|---|
| `models.py` | Normalized market/book/level contracts, data mode, timestamps, freshness and sequence metadata. |
| `hyperliquid.py` | Hyperliquid public market-data adapter and normalization logic. |
| `mock.py` | Deterministic DEMO data source used for local development/tests; it remains explicitly simulated. |
| `service.py` | Starts/stops the selected adapter, accepts ordered updates, exposes the current snapshot and notifies runtime listeners. |
| `history.py` | Bounded unique normalized midpoint history used by Phase 6 volatility and agent research signals. |
| `perp_context.py` | Normalizes mark, oracle, funding, open interest and account-position context; includes deterministic DEMO context. |
| `__init__.py` | Package marker. |

## Connections

```text
Hyperliquid / DEMO
      ↓
MarketDataService
      ├──→ Strategy fair value + AMM
      ├──→ MarketPriceHistory → Phase 6 + agents
      ├──→ PerpContextService → Phase 7
      ├──→ ReferenceService (HL mid/mark/oracle evidence)
      ├──→ Risk freshness/version checks
      └──→ Terminal / API observability
```

The runtime installs listeners so new market/perpetual evidence wakes strategy recomputation. Invalid/stale evidence is handled fail-closed by the runtime rather than silently substituting DEMO values into LIVE mode.

## Ordering and freshness

Market history accepts unique monotonic observations and rejects stale/invalid/non-positive prices. Exchange sequence/timestamps remain distinct from local observation/terminal timestamps.

## Safety boundary

This package supplies normalized evidence only. It does not decide position sizing, risk posture or whether an order may be transmitted.
