# Strategy Domain

The `strategy` package turns normalized market/perpetual state and the neutral AMM ladder into the strategy's pre-agent quote proposal.

It composes Phases 5–7 around the AMM core but does not own final risk authorization or venue transmission.

## Position in the pipeline

```text
Normalized market + perp context
        ↓
Fair value / bounded perp reference
        ↓
AMM neutral ladder
        ↓
Inventory policy
        ↓
Volatility + L2 imbalance adaptation
        ↓
BASE STRATEGY QUOTES
        ↓
agents → references/risk → execution
```

## Files

| File | Responsibility |
|---|---|
| `models.py` | `StrategyConfig`, execution/data modes, strategy state and validated configuration. |
| `fair_value.py` | Computes the normalized market fair value from valid market state. |
| `inventory.py` | Phase 5 inventory state, reservation-price skew, side-size skew and hard-limit side suppression. |
| `market_adaptation.py` | Phase 6 bounded realized-volatility and top-N L2 imbalance decisions; widening/reduction transforms only. |
| `perp_policy.py` | Phase 7 bounded mark/oracle/funding-based perpetual strategy reference. |
| `quote_engine.py` | Composes fair value, virtual AMM, inventory, perp context and market adaptation into the pre-agent ladder. |
| `__init__.py` | Package marker. |

## Quote-engine stages

`QuoteEngine` exposes progressively richer generation methods:

- `generate()`: neutral accepted AMM ladder.
- `generate_at_reference()`: AMM recentered at an explicit trusted strategy reference.
- `generate_inventory_aware()`: Phase 5 inventory transform.
- `generate_market_adaptive()`: inventory + Phase 6 adaptation.
- `generate_perp_market_adaptive()`: Phase 7 reference + inventory + Phase 6 adaptation used by the current runtime/simulator.

Quote-lineage fields are retained so the terminal can explain how price/size changed without recomputing strategy math in TypeScript.

## Connections

- Reads normalized state from `market_data`.
- Calls `amm` for the mathematical ladder.
- Produces `strategy_quotes` consumed by `agents`.
- Does not call execution adapters.
- Phase 8 risk remains downstream and can further widen/reduce/halt.
- Phase 10 simulation reuses the same `QuoteEngine`.

## Authority boundary

Strategy proposes liquidity; it does not authorize transmission. Hard inventory suppression is an upstream safety constraint that later strategy/agent layers must not restore.
