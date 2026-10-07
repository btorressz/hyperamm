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
| 8 | IN REVIEW | Multi-source reference integrity + deterministic institutional risk firewall implemented; acceptance validation pending |
| 9 | IMPLEMENTED / IN REVIEW | Deterministic regime / toxic-flow / execution-quality supervisory agents merged; separate acceptance remains pending |
| 10 | IMPLEMENTED / IN REVIEW | Deterministic production-stack simulation + bounded grid optimization; Phase 10.1 hardening and full local acceptance passed |
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


## Phase 8 — IN REVIEW

Implemented scope includes provider-independent price evidence; RedStone primary external oracle support; Hyperliquid native oracle/mark/mid reuse; Kraken WebSocket v2 BBO exchange reference; CoinGecko REST aggregate reference; provider health/freshness/versioning; deterministic quorum, outlier handling and signed deviation matrix; projected resting/desired exposure; liquidation distance; fill-derived PAPER PnL; TESTNET equity/drawdown when authoritative account values exist; NORMAL/WIDEN/REDUCE/HALT risk states; hysteresis and recovery confirmations; bounded event logging; deterministic SHA-256 evidence/quote/risk fingerprints; FinalQuoteAuthorization; pre-transmission version/fingerprint checks; REST/WebSocket observability; and focused Phase 8 adversarial tests.

Phase 6 and Phase 7 remain IN REVIEW because their exact full acceptance evidence is still outstanding. Phase 8 must also remain IN REVIEW until the complete Python 3.12 backend suite, FastAPI endpoint checks, frontend typecheck/build, and repository diff/static validation pass. Validation is local/manual; no repository workflow is introduced.

### Phase 8.2 — transport resilience, IN REVIEW

RedStone retains one provider identity and one consensus vote. Authenticated Live WebSocket remains primary; a no-key Python/httpx public cache transport polls every 10 seconds with a separate 30-second freshness threshold. Fresh HTTP evidence remains usable but caps confidence at DEGRADED, preserving the existing firewall's REDUCE posture. Transport failover/recovery advances reference and FinalQuoteAuthorization provenance even at the same price. The API and existing terminal row expose effective transport and FALLBACK quality.

On 2026-10-05, the production public HTTP attempt was blocked by the execution environment's HTTP CONNECT proxy (`403 Forbidden` / `httpx.ProxyError`); no real ETH observation was received. Offline deterministic acceptance does not satisfy external-provider acceptance. Phase 8 remains IN REVIEW because external-provider acceptance is still outstanding. That upstream acceptance does not block Phase 9 implementation; Phase 9 is IN DEVELOPMENT and remains subordinate to Phase 8 authority.

Offline acceptance on Python 3.12.14: **287 passed, 1 warning in 2.38s**, preserving all 223 existing tests and adding 64 transport/provenance cases. Uvicorn startup and graceful shutdown passed; `/api/v1/health`, `/api/v1/references`, `/api/v1/risk`, `/api/v1/risk/evidence`, and `/api/v1/risk/authorization` each returned HTTP 200 in DEMO/PAPER mode. A deterministic FastAPI test separately verifies PUBLIC_HTTP serialization. Frontend `npm run typecheck` and `npm run build` exited 0 (109 modules, 2.25s); `git diff --check` passed. The backend warning is upstream Starlette/httpx deprecation; the frontend reports non-failing TanStack Query `use client` directive warnings. No real orders were transmitted.


## Phase 9 — IMPLEMENTED / IN REVIEW

Phase 9 implementation adds deterministic Regime, Toxic-Flow and Execution-Quality agents plus a conservative AgentSupervisor between Phase 6 strategy quotes and the Phase 8 firewall. Agents can only widen, reduce size or trim existing levels; they cannot execute, restore Phase 5-suppressed sides, clear the manual kill switch or weaken Phase 8.

The runtime uses one reference snapshot for agent evidence and the downstream Phase 8 firewall. Post-agent candidate quotes are the quotes used for Phase 8 projected-exposure evaluation. FinalQuoteAuthorization binds the agent version and material fingerprint, and stale agent authority rejects CREATE/REPLACE before transmission.

Phase 9 also adds bounded fill/reconciliation telemetry, simulated PAPER markouts, explicit TESTNET fill-data limitations, read-only agent APIs, terminal/frontend explainability and focused regression/static tests.

Phase 8 remains IN REVIEW. Phase 9 must not be promoted to COMPLETE until the full Python 3.12 backend suite, FastAPI/API/WebSocket checks, frontend typecheck/build and repository static acceptance pass. No GitHub Actions workflow is introduced.


## Phase 10 — IMPLEMENTED / IN REVIEW

Phase 10 adds an offline deterministic research framework around the actual HyperAMM strategy instead of a parallel toy strategy.

Implemented scope on this branch includes:

- dedicated `app/simulation/` package
- validated immutable scenario/replay frames and datasets
- deterministic scenario clock
- backward-compatible clock injection for PAPER order/fill timestamps
- built-in deterministic market/perp/reference scenarios
- simulated RedStone / Hyperliquid oracle / Kraken / CoinGecko / HL mid / HL mark evidence through the existing `ReferenceConsensusPolicy`
- frame-by-frame reuse of `MarketPriceHistory`, `QuoteEngine`, Phase 5 inventory, Phase 6 adaptation, Phase 7 perp policy, Phase 9 `AgentSupervisor`, Phase 8 `RiskFirewall`, `authorize()`, `OrderManager`, `reconcile_quotes()` and `PaperExecutionAdapter`
- Decimal PnL/equity/drawdown/inventory/execution/risk/agent metrics
- bounded trace and deterministic run fingerprint
- deterministic grid search with explicit strategy/agent allowlists and immutable safety settings
- BASELINE, training/validation separation, transparent objective components and stable tie-breaking
- bounded offline simulation APIs
- focused Simulation & Optimization frontend with no auto-apply/deploy action
- Phase 10 scenario/engine/optimizer/API/static tests

Phase 10.1 acceptance passed on 2026-10-06 (America/Los_Angeles): Python
3.12.14, **407 passed, 1 warning in 8.91s**. The warning is upstream
Starlette/httpx deprecation. Real Uvicorn startup, all eight required REST
checks, terminal WebSocket state and graceful lifespan shutdown passed in
DEMO/PAPER mode. Uvicorn re-raised SIGTERM after complete shutdown (process
return code -15). Frontend typecheck and build exited 0; Vite transformed 115
modules and built in 2.49s, with non-failing TanStack Query directive warnings.
`git diff --check` passed.

Hardening includes a lifespan-owned, single-slot research thread with a private
asyncio loop per job, immediate HTTP 429 overflow rejection, cancellation-safe
admission, failure cleanup and explicit pool shutdown. Tests deterministically
prove live-loop responsiveness and detached runtime configuration. Candidate
rejections only catch ValidationError/ValueError; unexpected errors propagate.
Engine version `phase10.1-v1` is code-owned, result-visible and fingerprint-bound;
API version spoofing receives HTTP 422.

The requested Phase 10 build/acceptance gates are closed; code review remains.
Phase 8 remains IN REVIEW for its separate external-provider acceptance. Phase 9
remains IMPLEMENTED / IN REVIEW. Phase 11 remains PLANNED.
