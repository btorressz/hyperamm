# AMM Domain

The `amm` package is HyperAMM's mathematical liquidity foundation. It models a virtual constant-product pool and converts the resulting curve into discrete bid/ask `QuoteLevel` objects suitable for an order-book venue.

This package does **not** submit orders, read credentials, evaluate external oracle trust, or decide whether quotes are safe to execute.

## Position in the pipeline

```text
Strategy reference price
        ↓
Virtual constant-product pool
        ↓
Curve sampling / reserve deltas
        ↓
Optional concentration weights
        ↓
Tick + size normalization
        ↓
Neutral AMM quote ladder
        ↓
strategy/inventory/market adaptation
```

## Files

| File | Responsibility |
|---|---|
| `constant_product.py` | Core `x * y = k` invariant, marginal-price and virtual swap calculations. |
| `virtual_reserves.py` | Initializes virtual reserves and recenters the pool around a supplied strategy reference. |
| `liquidity_curve.py` | Samples the virtual curve and derives liquidity/reserve movement across quote levels. |
| `concentrated.py` | Applies bounded concentration weighting so more of the fixed liquidity budget can sit near the active reference range. |
| `discretizer.py` | Compiles mathematical curve output into normalized CLOB bids/asks using tick size, size precision, budgets and no-cross rules. |
| `models.py` | AMM models such as virtual pool state, curve points and quote-lineage fields. |
| `__init__.py` | Package marker. |

## Connections

- `strategy.quote_engine.QuoteEngine` is the primary consumer.
- Phase 7 supplies the strategy reference used to recenter the pool.
- Phase 5 inventory, Phase 6 market adaptation, Phase 9 agents and Phase 8 risk transform the resulting quote ladder downstream.
- `execution.OrderManager` only sees quotes after downstream authorization.

## Numerical boundary

Financial quantities are modeled with `Decimal` and explicit normalization. Keep AMM reserve/invariant calculations deterministic and separate from research-only vectorized/statistical tooling.

## Important invariant

The CLOB ladder should remain a representation of the AMM liquidity model. Quote sizes are derived from reserve movement plus configured bounded floors/weights; downstream layers should not silently replace that curve with unrelated fixed sizing.
