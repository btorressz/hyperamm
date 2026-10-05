# HyperAMM Roadmap

| Phase | Status | Scope |
|---|---|---|
| 1 | COMPLETE | Hyperliquid normalized market data, explicit demo feed, paper execution, guarded optional testnet adapter |
| 2 | COMPLETE | Virtual constant-product AMM, invariant/swap math, virtual reserve initialization and recentering |
| 3 | COMPLETE | AMM curve sampling → tick/size-normalized CLOB quote compiler + deterministic quote reconciliation |
| 4 | COMPLETE | Concentrated-liquidity policy with normalized weighting and tested concentration-factor behavior |
| 4.1 | COMPLETE | Phase 1–4 Acceptance & Hardening: AMM-derived sizes, fail-closed quotes, serialized execution/kill, TESTNET venue reconciliation |
| 5 | COMPLETE | Inventory-aware quoting with bounded price/size skew, authoritative inventory state, hard-limit side suppression, API/UI visibility, and acceptance coverage |
| 6 | PLANNED | Volatility + book-imbalance adaptation |
| 7 | PLANNED | Perpetual vAMM context |
| 8 | PLANNED | Oracle protection + institutional risk firewall |
| 9 | PLANNED | Regime / toxic-flow / execution-quality supervisory agents |
| 10 | PLANNED | Strategy optimization + simulation |
| 11 | PLANNED | Vault/accounting |
| 12 | PLANNED | Expanded production-grade React terminal |

## Phase 5 extension points

Phase 5 can be added without changing execution authority. An inventory policy can transform desired bid/ask prices and sizes after fair-value/AMM generation but before risk validation. `StrategyConfig`, `QuoteEngine`, typed `QuoteLevel`, and the reconciliation layer already expose the necessary seams. The risk layer remains downstream and non-bypassable.

## Phase 4.1 — COMPLETE

Phase 1–4 Acceptance & Hardening validated on 2026-10-04:

- Python 3.12.14, installed editable backend with test dependencies.
- `pytest`: **88 passed, 1 warning in 1.59s** (upstream Starlette/httpx deprecation).
- `npm install` completed; `npm run typecheck`: exit 0.
- `npm run build`: exit 0, 101 modules transformed, built in 1.97s.
  Vite reported non-failing TanStack Query `use client` directive warnings.
- FastAPI/Uvicorn startup: `/api/v1/health` HTTP 200 in DEMO mode;
  application startup and graceful shutdown completed.
- Existing 32 tests preserved; 56 additional regression cases cover reserve-delta
  sizing, budgets, concentration, fail-closed recovery, kill races, uncertain SDK
  transmissions, and mocked venue reconciliation.

This passes the local acceptance gate and provides the foundation for subsequent
Phases 5–8. None of those phases has started. Live signed Hyperliquid TESTNET
behavior remains opt-in and was not exercised; see the integration limitations.


## Phase 5 — COMPLETE

Implemented scope includes normalized PAPER/TESTNET inventory state, configurable target/soft/hard bounds, bounded deterministic reservation-price and side-size skew, hard-limit side suppression, inventory-version authority checks, the positions/terminal API surface, frontend controls/gauge/explainability, and focused Phase 5 acceptance tests.

Acceptance verified on Python 3.12 / Node 24: full backend suite, FastAPI startup/health, frontend typecheck/build, and diff/static validation all pass. Phase 6 remains unstarted.
