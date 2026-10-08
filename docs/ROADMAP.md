# HyperAMM Roadmap

| Phase | Status | Scope |
|---|---|---|
| 1 | COMPLETE | Hyperliquid normalized market data, explicit demo feed, paper execution, guarded optional testnet adapter |
| 2 | COMPLETE | Virtual constant-product AMM, invariant/swap math, virtual reserve initialization and recentering |
| 3 | COMPLETE | AMM curve sampling → tick/size-normalized CLOB quote compiler + deterministic quote reconciliation |
| 4 | COMPLETE | Concentrated-liquidity policy with normalized weighting and tested concentration-factor behavior |
| 4.1 | COMPLETE | Phase 1–4 Acceptance & Hardening: AMM-derived sizes, fail-closed quotes, serialized execution/kill, TESTNET venue reconciliation |
| 5 | COMPLETE | Inventory-aware quoting with bounded price/size skew, authoritative inventory state, hard-limit side suppression, API/UI visibility, and acceptance coverage |
| 6 | IN REVIEW | Deterministic realized-volatility and top-N L2 market adaptation implemented; local commands have passed; substantive review/live calibration remain |
| 7 | IN REVIEW | Hyperliquid-native perp context and bounded vAMM reference pricing implemented; local commands have passed; substantive review/live calibration remain |
| 8 | IN REVIEW | Multi-source reference integrity + deterministic risk firewall implemented; local fixtures passed, external-provider acceptance pending |
| 9 | IMPLEMENTED / IN REVIEW | Deterministic regime / toxic-flow / execution-quality supervisory agents merged; separate acceptance remains pending |
| 10 | IMPLEMENTED / IN REVIEW | Deterministic production-stack simulation + bounded grid optimization; Phase 10.1 hardening and full local acceptance passed |
| 11 | IMPLEMENTED / IN REVIEW | Deterministic research vault/accounting, shared runtime/simulation ledger, simulated fees/funding, capital authority and Vault observability; local acceptance passed |
| 11.1 | ACCEPTED | High-water invariants and identity-based execution/accounting consistency hardening; local acceptance passed |
| 12 | IMPLEMENTED / IN REVIEW | Full React operator terminal, versioned observation contracts, bounded history/events, health and lineage; local acceptance passed |

## Phase 6 extension points

Phase 6 composes after the completed inventory policy. `MarketPriceHistory` provides bounded normalized mid-price observations; `MarketAdaptationPolicy` transforms Phase 5 quotes using deterministic volatility and top-N L2 imbalance before the unchanged downstream risk/reconciliation authority. Phase 7 consumes the resulting strategy seams, but funding, mark/oracle basis, open interest and perpetual context are not part of Phase 6.

Current review as of 2026-10-07: phases 1–12 are implemented. Historical local
acceptance records below do not establish live/provider acceptance or production
readiness. See [Audit 1.0](../AUDIT_REPORT_1.0.md) for remaining authority,
provider and operational findings. Recent hardening closed A1-018 through A1-023;
A1-024 through A1-027 are informational design boundaries documented without new
runtime authority or roadmap phase work.

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

Historical Phase 5 acceptance: Python 3.12 / Node 24: full backend suite, FastAPI startup/health, frontend typecheck/build, and diff/static validation all pass. Phase 6 was unstarted at that milestone; it is now implemented / in review.


## Phase 6 — IN REVIEW

Implemented scope includes bounded unique market history, RMS log-return realized volatility, explicit neutral warmup, bounded volatility scoring, top-N base-size L2 imbalance, widening-only spread adaptation around the Phase 5 reservation center, bounded global/side variable-liquidity reduction, market/adaptation version authority, normalized REST/WebSocket state, grouped frontend controls, explainability metadata, and focused Phase 6 tests.

The earlier local-command gate has been superseded by subsequent local acceptance and Audit 1.0 verification. Phase 6 remains IN REVIEW for substantive findings and live calibration; local commands alone do not close that review. No GitHub Actions workflow is part of Phase 6.


## Phase 7 — IN REVIEW

Implemented scope includes normalized Hyperliquid mark/oracle/funding/open-interest context, deterministic DEMO context, signed basis and OI-notional calculations, bounded market/mark/oracle reference weighting, bounded funding bias, total reference-shift clamping, AMM recentering before reserve-delta sizing, Phase 5/6 composition, shared TESTNET user-state position context, perp freshness/version authority, normalized REST/WebSocket state, frontend controls/panels, and focused Phase 7 tests.

Historical command-blocked wording is superseded: local Python 3.12/backend and frontend checks subsequently passed, including Audit 1.0 verification. Phases 6 and 7 remain IN REVIEW for substantive audit and live/calibration issues, not because local commands are still blocked. No GitHub Actions workflow is part of either phase.


## Phase 8 — IN REVIEW

Implemented scope includes provider-independent price evidence; RedStone primary external oracle support; Hyperliquid native oracle/mark/mid reuse; Kraken WebSocket v2 BBO exchange reference; CoinGecko REST aggregate reference; provider health/freshness/versioning; deterministic quorum, outlier handling and signed deviation matrix; projected resting/desired exposure; liquidation distance; fill-derived PAPER PnL; TESTNET equity/drawdown when authoritative account values exist; NORMAL/WIDEN/REDUCE/HALT risk states; hysteresis and recovery confirmations; bounded event logging; deterministic SHA-256 evidence/quote/risk fingerprints; FinalQuoteAuthorization; pre-transmission version/fingerprint checks; REST/WebSocket observability; and focused Phase 8 adversarial tests.

Phases 6–8 remain IN REVIEW. Subsequent local checks supersede the earlier command-blocked acceptance notes; external-provider acceptance and unresolved authority findings remain distinct. Validation is local/manual; no repository workflow is introduced.

### Phase 8.2 — transport resilience, IN REVIEW

RedStone retains one provider identity and one consensus vote. Authenticated Live WebSocket remains primary; a no-key Python/httpx public cache transport polls every 10 seconds with a separate 30-second freshness threshold. Fresh HTTP evidence remains usable but caps confidence at DEGRADED, preserving the existing firewall's REDUCE posture. Transport failover/recovery advances reference and FinalQuoteAuthorization provenance even at the same price. The API and existing terminal row expose effective transport and FALLBACK quality.

On 2026-10-05, the production public HTTP attempt was blocked by the execution environment's HTTP CONNECT proxy (`403 Forbidden` / `httpx.ProxyError`); no real ETH observation was received. Offline deterministic acceptance does not satisfy external-provider acceptance. Phase 8 remains IN REVIEW because external-provider acceptance is still outstanding. That upstream acceptance does not block Phase 9 implementation; Phase 9 is now IMPLEMENTED / IN REVIEW and remains subordinate to Phase 8 authority.

Historical Phase 8.2 offline acceptance (2026-10-05) on Python 3.12.14: **287 passed, 1 warning in 2.38s**, preserving all 223 existing tests and adding 64 transport/provenance cases. Uvicorn startup and graceful shutdown passed; `/api/v1/health`, `/api/v1/references`, `/api/v1/risk`, `/api/v1/risk/evidence`, and `/api/v1/risk/authorization` each returned HTTP 200 in DEMO/PAPER mode. A deterministic FastAPI test separately verifies PUBLIC_HTTP serialization. Frontend `npm run typecheck` and `npm run build` exited 0 (109 modules, 2.25s); `git diff --check` passed. The backend warning is upstream Starlette/httpx deprecation; the frontend reports non-failing TanStack Query `use client` directive warnings. No real orders were transmitted.


## Phase 9 — IMPLEMENTED / IN REVIEW

Phase 9 implementation adds deterministic Regime, Toxic-Flow and Execution-Quality agents plus a conservative AgentSupervisor between Phase 6 strategy quotes and the Phase 8 firewall. Agents can only widen, reduce size or trim existing levels; they cannot execute, restore Phase 5-suppressed sides, clear the manual kill switch or weaken Phase 8.

The runtime uses one reference snapshot for agent evidence and the downstream Phase 8 firewall. Post-agent candidate quotes are the quotes used for Phase 8 projected-exposure evaluation. FinalQuoteAuthorization binds the agent version and material fingerprint, and stale agent authority rejects CREATE/REPLACE before transmission.

Phase 9 also adds bounded fill/reconciliation telemetry, simulated PAPER markouts, explicit TESTNET fill-data limitations, read-only agent APIs, terminal/frontend explainability and focused regression/static tests.

Phase 8 remains IN REVIEW for external-provider acceptance. Historical Phase 9 local build/test gates have subsequently passed; Phase 9 remains IMPLEMENTED / IN REVIEW for substantive authority/provider review. Local commands alone do not promote it to COMPLETE. No GitHub Actions workflow is introduced.


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
remains IMPLEMENTED / IN REVIEW. Phase 11 was PLANNED at Phase 10.1 acceptance.


## Phase 11 — IMPLEMENTED / IN REVIEW

Phase 11 implements the dedicated Decimal accounting domain, immutable append-only
idempotent ledger, one shared average-cost position/PnL formula, simulated PAPER
fee/funding accounting, research settled capital, equity/peak/drawdown, full-notional
simulated capital reservation, accounting provenance and stale-state execution
binding. Runtime PAPER inventory and Phase 10 simulation use AccountingService;
Phase 8 consumes its vault-derived PnlDrawdown and capital sufficiency input.
FinalQuoteAuthorization binds accounting version/fingerprint, checked before
CREATE/REPLACE. Cancellation remains possible when accounting fails.

TESTNET exposes only existing authoritative position/account fields and labels
completeness PARTIAL; missing cash, realized PnL, fees, funding payments and capital
availability remain null. Market/execution/data-mode transitions isolate research
sessions under the serialized execution lock. No public reset or money movement
endpoint is added. The active Vault page shows metrics, bounded ledger and
provenance with PAPER/SIMULATED and TESTNET/PARTIAL source labels.

Historical local acceptance at merge on 2026-10-06 (America/Los_Angeles):

- Fresh Python 3.12.14 virtualenv and editable backend/test installation succeeded.
- Full backend suite: **492 passed, 1 warning in 10.05s** (407 existing tests plus
  85 Phase 11 cases). Warning: upstream Starlette/httpx TestClient deprecation.
- Real Uvicorn DEMO/PAPER startup: all eight requested REST endpoints and the
  optional accounting-position endpoint returned HTTP 200. Ledger invalid limits
  returned HTTP 422. Application startup and graceful shutdown completed;
  Uvicorn re-raised SIGTERM after shutdown (process return code -15).
- Real terminal WebSocket: vault, compact accounting, matching provenance, <=20
  notices and existing terminal fields passed. No ledger history is streamed.
- `npm install` succeeded using the local package cache. Frontend typecheck and
  build exited 0; Vite 7.3.6 transformed 120 modules and built in 1.87s. Non-failing
  TanStack Query `use client` directive warnings remain.
- React server-render acceptance passed for PAPER metrics/ledger, TESTNET/PARTIAL
  unavailable values and the active Vault sidebar. This is a rendering check,
  not a live signed TESTNET or browser visual acceptance claim.
- `git diff --check` passed. No repository workflow, additional oracle, mainnet,
  custody, deposits, withdrawals, transfers/bridging or Phase 12 work was added.

See [Accounting](ACCOUNTING.md) for formulas, identities, research funding sampling,
HALT_WHEN_FULL retention, version semantics and limitations. Phase 11 is ready for
review, not marked COMPLETE. Phase 8 and Phase 9 keep their existing review status.
Phase 12 was PLANNED at this historical Phase 11 acceptance; it is now IMPLEMENTED / IN REVIEW (see below). No signed live TESTNET orders were transmitted.

## Phase 11.1 — ACCEPTED (local hardening acceptance)

PAPER high-water equity now observes every committed fill+fee batch, funding
accrual and mark. Snapshot validation enforces peak >= equity and COMPLETE
authority requires execution/accounting consistency. Runtime and simulation use
the same service and identity/economic evidence reconciliation. Divergence changes
accounting provenance, makes capital authority UNAVAILABLE and blocks CREATE/REPLACE
while preserving cancellation. Internal reconciliation books safe pending evidence
only; it never clears a latched failure or replays behind newer mark/funding
evidence. No public accounting mutation endpoint was added.

Acceptance on 2026-10-06 (America/Los_Angeles), starting main
`c7854ebc2d3e60173667904b7afd21ce02c75446`:

- Fresh Python **3.12.14** virtualenv; editable backend/test installation succeeded.
- Full pytest: **517 passed, 1 warning in 17.10s** (all 492 existing cases retained,
  plus 25 hardening cases). Upstream Starlette/httpx TestClient deprecation warning.
- Real Uvicorn: all nine required REST endpoints returned **HTTP 200**; consistency
  and Decimal serialization passed; reset/replay/rebuild requests returned **404**.
- Real `/ws/terminal`: compact consistency, matching accounting provenance,
  existing terminal fields and bounded notices passed; no full ledger stream.
- Frontend `npm install`, typecheck and build exited **0**; Vite **7.3.7** transformed
  **120 modules**, built in **3.15s**. Non-failing TanStack Query `use client`
  directive warnings remain.
- Chromium: live PAPER CONSISTENT green indicator passed; controlled WebSocket
  DIVERGED danger/count and TESTNET/PARTIAL unavailable states passed; **0 page errors**.
- `git diff --check` exited **0**. Existing accounting formulas, ledger retention
  and atomic append, Phase 8 authority, Phase 10 research and TESTNET truth remain.

Phase 11 stays **IMPLEMENTED / IN REVIEW**, with Phase 11.1 build/hardening accepted
and closed locally. This does not declare production readiness or start Phase 12.
No persistence, custody, money movement, mainnet execution, additional oracle providers or GitHub Actions
were added.


## Phase 12 — IMPLEMENTED / IN REVIEW

Starting main: `ef41168657b4d635c0cf4961689dfa1b73e18ae3`, the merged
Phase 11.1 accounting-hardening revision. The initial workspace was behind at
`c7854eb`; GitHub main and the missing Git objects were independently verified
before implementation on `phase-12-terminal`.

Adds the `phase12-v1` normalized TerminalSnapshot, process-wide observation
sequence, UTC emission timestamp, pre-agent/post-agent/authorized quotes,
read-only health aggregation, bounded current-session chart history and structured
events. All twelve terminal pages are active: Dashboard, Markets, Strategy,
AMM Settings, Execution, Risk, Supervisory Agents, Vault, Analytics, Simulation &
Optimization, Logs and Settings. React charts display retained backend stages
and timestamps; exact lineage is qualified by Audit 1.0 A1-021; no trading or accounting formulas were added to React.

Historical local acceptance at merge on 2026-10-06 (America/Los_Angeles):

- Fresh Python **3.12.14** virtualenv and editable `.[test]` installation passed.
- Full suite: **546 passed, 1 warning in 16.30s**. All 517 prior cases retained;
  29 Phase 12 cases cover contracts, process sequencing, bounds/filters, history
  ordering, future-evidence exclusion, redaction, authority isolation, TESTNET
  truth, API validation and actual WebSocket frames/disconnect.
- Real Uvicorn: fourteen required/context REST endpoints returned **HTTP 200**;
  invalid terminal queries returned **422**. Existing PAPER start/stop/kill/resume
  controls passed. Startup and graceful shutdown were checked.
- Real `/ws/terminal`: three frames, sequences **23 / 25 / 27**, contract
  **phase12-v1**, aware UTC timestamps, matching accounting fingerprints, Phase
  8/9/11 state and compact payloads (**96123 / 96198 / 96205 bytes** in the
  JSON acceptance measurement). No full ledger or terminal history was streamed.
- `npm install`, frontend typecheck and build exited **0**. Vite **7.3.6**,
  **139 modules**, final build **1.98s**. Charts/React/query chunks separate the production bundle;
  non-failing upstream TanStack Query directive warnings remain.
- Chromium: all twelve pages rendered with **0 page errors**; no document
  horizontal overflow at 1600, 1200, 900, 600 or 390 pixels. Dirty edits survived
  WebSocket frames, server validation/reset, immediate kill/confirmed resume,
  malformed/out-of-order payload visibility, recovery, terminal staleness and
  controlled TESTNET fill-history-unavailable state passed.
- `git diff --check` exited **0**. No trading-core domain module was modified.

The inherited Phase 11.1 roadmap contained a forbidden-provider name in a
negative scope statement, causing three existing static scans to fail. That
sentence now uses generic scope wording; no prior test was removed or weakened.

Phase 12 local implementation and acceptance are complete for review. The full
Phase 1–12 implementation roadmap is present; separate Phase 8 external-provider
acceptance, Phase 9 review and prior review statuses are preserved. This does not
claim the entire roadmap is fully accepted/COMPLETE or a production launch.
History/events are in-memory, current-session only; durable 24h statistics,
TESTNET normalized fills, custody/money movement and autonomous optimization
deployment remain outside scope. No signed TESTNET order or repository workflow
was added. See [Terminal](TERMINAL.md) for contracts, limits and truth boundaries.

## Audit 1.0 — A1-019 / A1-018 local validation (2026-10-07)

A1-019 serializes configuration transport transitions with captured identities,
staged construction/publication, retired callback gating and an explicit failed
state requiring runtime restart. A1-018 refreshes current documentation while
preserving historical merge acceptance above. See [Architecture](ARCHITECTURE.md#a1-019-serialized-configuration-lifecycle)
for exact ordering, recovery and failure semantics.

- Python 3.12.14 full backend suite: **851 passed, 1 warning in 20.17s**.
- Focused integration/runtime configuration suite: **94 passed in 3.43s**;
  19 new lifecycle regression cases extend the existing test architecture.
- `git diff --check` passed. The warning remains upstream Starlette/httpx
  TestClient deprecation. No frontend/schema changes warranted a new frontend
  build; previous frontend/browser records remain historical evidence.
- No signed TESTNET orders or mainnet operations were performed. External-provider
  acceptance and remaining audit findings are not closed by this local result.
