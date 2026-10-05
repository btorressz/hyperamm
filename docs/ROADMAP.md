# HyperAMM Roadmap

| Phase | Status | Scope |
|---|---|---|
| 1 | COMPLETE | Hyperliquid normalized market data, explicit demo feed, paper execution, guarded optional testnet adapter |
| 2 | COMPLETE | Virtual constant-product AMM, invariant/swap math, virtual reserve initialization and recentering |
| 3 | COMPLETE | AMM curve sampling → tick/size-normalized CLOB quote compiler + deterministic quote reconciliation |
| 4 | COMPLETE | Concentrated-liquidity policy with normalized weighting and tested concentration-factor behavior |
| 4.1 | COMPLETE | Phase 1–4 Acceptance & Hardening: AMM-derived sizes, fail-closed quotes, serialized execution/kill, TESTNET venue reconciliation |
| 5 | COMPLETE | Inventory-aware quoting with bounded price/size skew, authoritative inventory state, hard-limit side suppression, API/UI visibility, and acceptance coverage |
| 6 | IN REVIEW | Deterministic realized-volatility and top-N L2 market adaptation implemented; acceptance validation pending |
| 7 | IN REVIEW | Hyperliquid-native perp context and bounded vAMM reference pricing implemented; acceptance validation pending |
| 8 | PLANNED | Oracle protection + institutional risk firewall |
| 9 | PLANNED | Regime / toxic-flow / execution-quality supervisory agents |
| 10 | PLANNED | Strategy optimization + simulation |
| 11 | PLANNED | Vault/accounting |
| 12 | PLANNED | Expanded production-grade React terminal |

## Phase 6 extension points

Phase 6 composes after the completed inventory policy. `MarketPriceHistory` provides bounded normalized mid-price observations; `MarketAdaptationPolicy` transforms Phase 5 quotes using deterministic volatility and top-N L2 imbalance before the unchanged downstream risk/reconciliation authority. Phase 7 may consume the resulting strategy seams later, but funding, mark/oracle basis, open interest and perpetual context are not part of Phase 6.

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


## Phase 6 — IN REVIEW

Implemented scope includes bounded unique market history, RMS log-return realized volatility, explicit neutral warmup, bounded volatility scoring, top-N base-size L2 imbalance, widening-only spread adaptation around the Phase 5 reservation center, bounded global/side variable-liquidity reduction, market/adaptation version authority, normalized REST/WebSocket state, grouped frontend controls, explainability metadata, and focused Phase 6 tests.

Phase 6 should be promoted to COMPLETE only after the explicit local Python 3.12 backend suite, FastAPI health/API checks, frontend typecheck/build, and `git diff --check` pass. No GitHub Actions workflow is part of Phase 6.


## Phase 7 — IN REVIEW

Implemented scope includes normalized Hyperliquid mark/oracle/funding/open-interest context, deterministic DEMO context, signed basis and OI-notional calculations, bounded market/mark/oracle reference weighting, bounded funding bias, total reference-shift clamping, AMM recentering before reserve-delta sizing, Phase 5/6 composition, shared TESTNET user-state position context, perp freshness/version authority, normalized REST/WebSocket state, frontend controls/panels, and focused Phase 7 tests.

Phase 6 remains IN REVIEW because its exact Python 3.12/full frontend acceptance evidence is still outstanding in this environment. Phase 7 must also remain IN REVIEW until the complete Phase 6 prerequisite and Phase 7 acceptance commands pass. No GitHub Actions workflow is part of either phase.
