# HyperAMM Roadmap

| Phase | Status | Scope |
|---|---|---|
| 1 | COMPLETE | Hyperliquid normalized market data, explicit demo feed, paper execution, guarded optional testnet adapter |
| 2 | COMPLETE | Virtual constant-product AMM, invariant/swap math, virtual reserve initialization and recentering |
| 3 | COMPLETE | AMM curve sampling → tick/size-normalized CLOB quote compiler + deterministic quote reconciliation |
| 4 | COMPLETE | Concentrated-liquidity policy with normalized weighting and tested concentration-factor behavior |
| 5 | PLANNED | Inventory-aware quoting |
| 6 | PLANNED | Volatility + book-imbalance adaptation |
| 7 | PLANNED | Perpetual vAMM context |
| 8 | PLANNED | Oracle protection + institutional risk firewall |
| 9 | PLANNED | Regime / toxic-flow / execution-quality supervisory agents |
| 10 | PLANNED | Strategy optimization + simulation |
| 11 | PLANNED | Vault/accounting |
| 12 | PLANNED | Expanded production-grade React terminal |

## Phase 5 extension points

Phase 5 can be added without changing execution authority. An inventory policy can transform desired bid/ask prices and sizes after fair-value/AMM generation but before risk validation. `StrategyConfig`, `QuoteEngine`, typed `QuoteLevel`, and the reconciliation layer already expose the necessary seams. The risk layer remains downstream and non-bypassable.
