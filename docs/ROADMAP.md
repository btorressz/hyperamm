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
| 8.3.1 | LOCALLY ACCEPTED — targeted gate | Six post-merge provider/schema/static regressions resolved; observational isolation fixture-tested; A2-005 and live-provider acceptance remain open |
| 9 | IMPLEMENTED / IN REVIEW | Expanded deterministic/heuristic supervision and optional predictive ML SHADOW; separate acceptance remains pending |
| 10 | IMPLEMENTED / IN REVIEW | Deterministic production-stack simulation + bounded grid optimization; Phase 10.1 hardening and full local acceptance passed |
| 11 | IMPLEMENTED / IN REVIEW | Deterministic research vault/accounting, shared runtime/simulation ledger, simulated fees/funding, capital authority and Vault observability; local acceptance passed |
| 11.1 | ACCEPTED | High-water invariants and identity-based execution/accounting consistency hardening; local acceptance passed |
| 12 | IMPLEMENTED / IN REVIEW | Full React operator terminal, versioned observation contracts, bounded history/events, health and lineage; local acceptance passed |
| 12.1 | LINUX ACCEPTED / MACOS PENDING | Structured WebSocket cancellation, bounded subscriber/lease shutdown, reproducible test matrices and real browser/proxy acceptance; cross-platform A2-005 closure pending |
| 12.2 | LINUX ACCEPTED / MACOS & LIVE PENDING | Executable price-distance integrity, strategy precision/feasibility and effective-price depth; logical slots preserved, stronger collapse policy deferred |
| 12.3 | MERGED / LINUX ACCEPTED / MACOS PENDING | Terminal freshness, process/session integrity and bounded replay protection; prior external/soak gates remain |
| 13.1 | MERGED / LOCAL ACCEPTANCE PASSED | Shared institutional design, persistent navigation, responsive accessible shell; no backend authority changes |
| 13.2 | PARTIAL / F IMPLEMENTED / G LOCAL CHECKS / A–E PENDING | 13.2.1 execution lifecycle UX; frontend verified; one baseline backend schema gate remains |
| 13.3 | PLANNED | Agents/Vault/Analytics/Simulation/Logs/Settings UX and final acceptance; follows 13.2 review/merge |

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

Phase 9 includes Regime/Toxic Flow/Execution Quality v2, multi-horizon immutable markouts, recorded PAPER lifecycle quality, Liquidity Quality and Perp Crowding with bounded source-timestamped OI/funding observations. Coherent typed snapshots, bounded/filterable read-only APIs and terminal cards distinguish HEURISTIC, DETERMINISTIC, SIMULATED and ML SHADOW evidence.

The optional Predictive Adverse Selection classifier remains **SHADOW ONLY / NO QUOTE AUTHORITY**. Offline datasets share a canonical feature schema and explicit target/provenance; optional sklearn logistic training requires independent train/validation identity and disjoint windows. Validated JSON artifacts identify actual coefficients/schema/provenance by canonical SHA-256; no model is provided by default. Simulation can explicitly evaluate shadow predictions against mature PAPER labels. Shadow model identity is observational and cannot invalidate live quote authorization. ADVISORY/ACTIVE, automatic promotion and online training are absent; future advisory use requires separately reviewed validation, support, calibration and operator configuration.

Agents recommend. Phase 8 decides. FinalQuoteAuthorization controls execution.

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

## Phase 8 CoinGecko hardening and optional Yahoo observation — 2026-10-08

CoinGecko enabled Demo and Pro reference modes require `COINGECKO_API_KEY`. Only the exact TLS hosts `https://api.coingecko.com/api/v3` (Demo / `x-cg-demo-api-key`) and `https://pro-api.coingecko.com/api/v3` (Pro / `x-cg-pro-api-key`) receive credentials. Missing configuration or untrusted hosts become provider ERROR without a network request. Disabled mode needs no credentials. HTTP 400/401/403 are ERROR; 429, 5xx, network and decoding errors are DEGRADED with bounded retries. CoinGecko remains tertiary and cannot satisfy core quorum.

Optional Yahoo personal research observation: install `pip install -e '.[yahoo]'`; defaults are `YFINANCE_REFERENCE_ENABLED=false`, `YFINANCE_SYMBOL=ETH-USD`, `YFINANCE_STALE_AFTER_SECONDS=30`. Mapping is explicit: ETH→ETH-USD, BTC→BTC-USD; other startup markets are unavailable, not guessed. The decoded yfinance `AsyncWebSocket` fields `id`, `price`, and Unix-millisecond `time` are validated against a source-time freshness window. Replays, wrong symbols, invalid values and missing/old/future timestamps are rejected. A bounded reconnect loop cancels listener/watchdog tasks and closes sockets. Missing optional dependency is observational ERROR only.

The separately polled `GET /api/v1/references/observations` endpoint and Risk-page card expose observational health, source age, prices and available signed comparison bps. Unavailable comparisons remain null. **Yahoo is excluded from CORE, ALL, the material reference snapshot, economic version/fingerprint, quorum, outlier decisions, risk, agents, authorization, accounting and execution.** It cannot replace RedStone, Kraken or Hyperliquid evidence or authorize trades. The Phase 12 streaming contract remains unchanged.

**Licensing and acceptance:** Yahoo data is for permitted local personal/research observation only. Do not redistribute it publicly or use it for commercial trading without appropriate rights. Live CoinGecko and Yahoo connections, real schemas and reconnect acceptance remain pending. Phase 8.3.1 fixture and local command results are recorded in the roadmap; they do not establish live-provider acceptance. Historical Audit 2.0 issues A2-001–A2-005 are unchanged. No Actions files, Docker, PostgreSQL, signing changes or new trading authority. No additional oracle providers were introduced; unsupported oracle integrations remain prohibited.

## Phase 8.3.1 — Post-Merge Regression & Acceptance Closure

Acceptance recorded on **2026-10-08 (America/Los_Angeles)**. Fetched main before
editing and rechecked before delivery: `21aa5bfc00360741b6c92466d4cce6f1ee0628df`.
GitHub metadata confirms merged PR #36 is the latest relevant implementation;
its 17-file diff, Audit 2.0, reference/architecture/roadmap and backend/frontend
contracts were reviewed. Work started clean on
`phase8/8-3-1-post-merge-acceptance`. Audit Reports 1.0 and 2.0 remain byte-for-byte
unchanged; **A2-001 through A2-005 are not closed**.

### Six reported regressions — verified dispositions

| Finding | Before | Corrected behavior / evidence |
|---|---|---|
| Yahoo timestamp/version | Zero deadband treated an unchanged-price newer tick as a price change | Exact equality refreshes legitimate source time without price-version churn; replay/regression cannot refresh or recover health; actual changed price and health recovery retain version semantics |
| RedStone evidence enumeration | Test assumed every registered identity was a material row | Test uses explicit six-row `MATERIAL_PROVIDERS`; singular RedStone effective transport remains intact; Yahoo stays in observations only |
| Generated terminal schema | Shared enum added Yahoo to generated material provider types | Generator uses the six material identities; regeneration produces the existing schema exactly, with no committed schema/fixture changes |
| Phase 8 static scan | Negative scope statement contained prohibited token | Generic wording in README and three docs; restriction and scanner retained |
| Phase 9 static scan | Same four documentation matches | Existing static test passes unchanged |
| Phase 10 static scan | Same four documentation matches | Existing static test passes unchanged; no `.github/` directory |

**IMPLEMENTED:** bounded fixes above and safer stale/unhealthy Yahoo display.
No authority, reserve economics, quote budgets, risk limits, signing permissions,
provider hierarchy or infrastructure changes. No Phase 12.1 or Phase 13 work.

**TESTED WITH FIXTURES:** 33 new backend cases in
`tests/test_phase831_acceptance.py`. Source-time/version and positive material
deadband tests complement PR #36's invalid/future/stale/mapping tests. CoinGecko
tests cover official Demo/Pro headers, required configuration/no-request failure,
the exact simple-price query, redirect non-following, sanitized network/decoding
errors, stale source classification, bounded ten-poll retry schedules and owned
client shutdown. Invalid enabled configuration leaves PAPER safely HALTed when
quorum is unavailable, with no order and no manual kill mutation.

The Yahoo non-authority matrix uses actual `ReferenceService`, runtime quote
generation, `AgentSupervisor`, `RiskFirewall`, authorization, pre-transmission
checks, `OrderManager`, PAPER adapter/fills and accounting. Identical material
inputs and frozen clocks compare DISABLED, HEALTHY, DEGRADED, STALE, ERROR,
UNAVAILABLE, +50%/-50% observations, replay and connection recovery, both with
and without manual kill. Entire material snapshots (including consensus/counts,
outliers/confidence), versions/fingerprints, agent/risk/authorization decisions,
fair value, quote prices/sizes, CREATE/KEEP/REPLACE/CANCEL, fills, ledger/vault and
capital authority remain equal. Observational responses vary independently.
Real ASGI REST serialization and published terminal payloads exclude credentials;
Yahoo is present only in the observations API. Reconnect fixtures verify
resubscription and drainage of listener/watchdog/socket resources.

Nine new frontend cases cover healthy/disabled/degraded/stale/error/unavailable
display, explicit Authority NONE, response failures and rejection of Yahoo in
material terminal evidence. All original 75 cases remain. This is fixture/render
and command acceptance; no new interactive browser acceptance is claimed.

### Local command results and limitations

**LOCALLY ACCEPTED — targeted Phase 8.3.1 gate**, Python **3.12.14**, Linux,
Node **24.19.0**, npm **11.9.0**. No tests were removed, suppressed, deselected or
marked xfail to obtain these results.

| Check | Exact outcome |
|---|---|
| Clean PR #36 baseline, requested eight focused files | **163 passed, 6 failed, 0 skipped, 1 warning; 1.23s** — all six reports reproduced |
| Corrected requested eight files plus new acceptance file | **202 passed, 0 failed, 0 skipped, 1 warning; 2.14s** |
| New acceptance file alone | **33 passed, 0 failed, 0 skipped; 1.60s** |
| Full extra-enabled backend, first run | **1048 passed, 0 failed, 0 skipped, 1 warning; 53.00s** |
| Full backend after final reconciliation assertions | **1048 passed, 0 failed, 0 skipped, 1 warning; 37.65s** |
| Ten named A2-005 tests, independent run | **9 passed, 1 failed, 0 skipped, 1 warning; 2.02s** — `test_api.py::test_terminal_state_includes_market_adaptation_after_runtime_tick`, `concurrent.futures.CancelledError` |
| Separate default `.[test]` install, Yahoo absent, provider/new acceptance files | **56 passed, 0 failed, 0 skipped; 1.43s**; pip check passed |
| Complete extras install / pip check / compileall | Passed; no broken requirements |
| Real Uvicorn DEMO/PAPER startup, six read-only REST routes, graceful shutdown | Passed; health/references/observations/risk/evidence/authorization HTTP 200; Yahoo DISABLED / Authority NONE; no strategy started |
| `npm ci --cache /workspace/hyperamm/work/npm-cache` | Passed; scratch cache used after unwritable default cache |
| `npm test` | Passed, all **5 test files** |
| Explicit Node case reporter | **84 passed, 0 failed, 0 skipped** (75 existing + 9 new); 24.92s |
| `npm run typecheck` / `npm run build` | Passed; Vite 7.3.6, 145 modules, 3.27s |
| `npm audit --json` | **0 vulnerabilities** |
| Generator/schema equality and valid/unavailable fixtures | Passed; checked-in schema unchanged |
| `git diff --check`, scope/static checks | Passed; audit/dependency/lock files unchanged |

Commands from repository root (the dedicated interpreters live in `work/`):

```bash
python -m venv work/venv
work/venv/bin/python -m pip install -e 'backend[test,ml,redis,yahoo]'
cd backend
../work/venv/bin/python -m pip check
../work/venv/bin/python -m compileall -q app
../work/venv/bin/python -m pytest tests/test_phase8_provider_observations.py tests/test_phase8_references.py tests/test_phase82_redstone_http.py tests/test_phase8_authorization.py tests/test_audit_terminal_contract.py tests/test_phase8_static.py tests/test_phase9_static.py tests/test_phase10_static.py tests/test_phase831_acceptance.py -q
../work/venv/bin/python -m pytest tests/test_phase831_acceptance.py -q
../work/venv/bin/python -m pytest -q
cd ..
python -m venv work/default-venv
work/default-venv/bin/python -m pip install -e 'backend[test]'
cd backend
../work/default-venv/bin/python -m pip check
../work/default-venv/bin/python -m pytest tests/test_phase8_provider_observations.py tests/test_phase831_acceptance.py -q
cd ../frontend
npm ci --cache /workspace/hyperamm/work/npm-cache
npm test
npm run typecheck
npm run build
npm audit --json --cache /workspace/hyperamm/work/npm-cache
NODE_PATH=/workspace/hyperamm/frontend/node_modules TERMINAL_TEST_BUILD=/workspace/hyperamm/work/frontend-tests node --test --test-isolation=none --test-reporter=tap tests/terminal.test.cjs tests/audit-lineage.test.cjs tests/freshness.test.cjs tests/agents.test.cjs tests/yahoo.test.cjs
cd ..
git diff --check
```

Independent WebSocket command from repository root:

```bash
work/venv/bin/python -m pytest \
  backend/tests/test_api.py::test_terminal_state_includes_market_adaptation_after_runtime_tick \
  backend/tests/test_api.py::test_terminal_state_includes_perp_context_after_runtime_tick \
  backend/tests/test_api.py::test_phase8_terminal_serialization_and_secrets_absent \
  backend/tests/test_api.py::test_phase9_agents_api_and_terminal_state \
  backend/tests/test_audit_local_publisher.py::test_two_websockets_share_cached_observation_and_cleanup \
  backend/tests/test_audit_local_publisher.py::test_local_loopback_request_and_browser_origin_work \
  backend/tests/test_phase11_api_static.py::test_terminal_websocket_has_compact_accounting_without_full_ledger \
  backend/tests/test_phase12_websocket.py::test_websocket_sequence_compact_fields_and_disconnect \
  backend/tests/test_redis_lifespan.py::test_disabled_mode_does_not_construct_a_redis_client \
  backend/tests/test_redis_lifespan.py::test_redis_websocket_relay_and_research_keep_existing_contracts -q
```

All ten named tests ran without suppression. Full-suite passing runs do **not**
establish reproducible backend acceptance: the independent CancelledError and
the user's **999 passed / 16 failed** MacBook record remain evidence. The ten
reported failures remain the Phase 12.1 acceptance scope; this Linux run neither
reproduces all ten nor closes A2-005. **Full backend acceptance remains pending.**

Warning: upstream Starlette/httpx TestClient deprecation. Vite retains non-fatal
TanStack Query `use client` notices; no EPIPE occurred in this production build,
but Phase 12.1's reported Vite behavior remains pending. Initial sandbox-only
TestClient runs stalled and were terminated; final tests used permitted loopback
access. Dependency constraints were not changed: extras resolved Starlette 1.7.0,
FastAPI 0.143.0, httpx 0.28.1, Pydantic 2.14.0, Redis 6.4.0 (default-only install
8.1.0). No dependency root cause is claimed.

**EXTERNAL ACCEPTANCE PENDING:** actual `yfinance==1.7.0` import and its
AsyncWebSocket/subscribe/listen/close/context interfaces were inspected. Live
subscription, decoded provider messages, source freshness, reconnect and cleanup
were not verified. CoinGecko credentials are unavailable; CoinGecko and Yahoo
hosts are absent from the configured restricted network allowlist, so no live
request was attempted and no successful response is simulated. Commercial
data-use/redistribution rights, signed venue acceptance and MacBook regression
acceptance are separate outstanding gates. Yahoo's local personal/research-only
licensing restriction remains documented.

## Phase 12.1 — Backend, WebSocket & Local Runtime Reliability

**LINUX ACCEPTANCE PASSED / MACOS ACCEPTANCE PENDING.** Targeted A2-005
implementation and available-environment acceptance passed on 2026-10-08.
Cross-platform closure remains pending the user's macOS Python 3.12.14 runs.
The historical audit reports and earlier failure records are preserved.

### Preflight and before/after

Fetched current `main` at **b960f91ad580fb3ccd760e06b99d1f27cb9492df**, verified
PR #37's merge, and branched as `phase12/12-1-websocket-runtime-reliability`.
Reviewed Audit 2.0 A2-005, Phase 12 publisher/contracts/tests, architecture,
roadmap, local runtime/Redis documentation, and frontend proxy/socket/store/
validator. The initial checkout was clean; unrelated work was not changed.

The user's previous Mac baseline was **999 passed / 16 failed / 1 warning**,
including ten WebSocket teardown failures and six subsequently corrected
Phase 8.3.1 regressions. PR #37's Linux full-suite pass did not establish
repeatability: its separate ten-test run was **9 passed / 1 failed**.
This investigation reproduced current-main failures independently:

| Unchanged main check | Observed result |
| --- | --- |
| Exact ten historical tests | **9 passed, 1 failed, 0 skipped, 1 warning; 1.99s** |
| Full default installation | **1046 passed, 1 failed, 1 skipped, 1 warning; 32.93s** |
| Each historical test in its own original-main process | **7 passed / 3 failed processes**; perp-context, agent-state and nested local-client teardown failures |
| Minimal cancellation tracing of the ten tests | **9 passed, 1 failed**; unmarked `CancelledError()` escaped handler cleanup |

The isolated failure was market-adaptation terminal context exit; the full-suite
failure was nested Redis terminal context exit. Frames had already been received.
One default-only skip is optional offline ML training when sklearn is absent;
it is unrelated to WebSockets and runs with the ML extra.

### Root cause and ownership correction

Starlette `WebSocketTestSession.__exit__` sends a disconnect, calls its AnyIO
cancel scope, then reads the portal future. The previous handler cancelled raw
`asyncio.create_task` children and awaited an unshielded `asyncio.gather` in
`finally`. A trace on unchanged main caught **`CancelledError()` without AnyIO's
scope marker at websocket.py's cleanup gather (old line 73)**. Other orderings
raised the marked cancellation instead and passed. AnyIO distinguishes its own
scope cancellation from native asyncio cancellation; the unmarked exception
escapes Starlette's scope and cancels the portal future, producing
`concurrent.futures.CancelledError`. This is an application ownership/cleanup
race exposed by the TestClient implementation, rather than connection admission
or failed initial-frame establishment. Installing a different HTTP client is
unnecessary to correct it.

`backend/app/api/websocket.py` now owns send, receive and lease-loss operations
in one AnyIO task group. The first terminal condition cancels siblings, and group
exit joins them before resource release. Expected disconnect and the existing
five-second send timeout terminate the connection; unexpected errors propagate.
Native parent cancellation is preserved. Bounded, shielded cleanup releases the
lease and closes only a still-owned accepted connection, then detaches the local
subscription. No close follows an observed peer disconnect. Cleanup failure
preserves both the original failure and cleanup failure in an exception group.

`terminal_transport.py` stops admission/publication, clears cached wire, and
signals shutdown through the existing one-slot queues. The internal sentinel
never enters `phase12-v1`. Shutdown waits up to twelve seconds for handlers to
release ownership; slow sends retain their five-second budget and owned cleanup
has a six-second budget. `runtime.py` stops its one observation publisher and
signals local/relay subscribers before existing economic service shutdown, then
awaits subscriber drain. Runtime lifespans create new sessions; a stopped runtime
cannot be restarted into an old session. The existing venue reconciliation and
execution-lock ordering remain intact. `main.py` attempts infrastructure closure
even when relay closure raises.

`redis.py` makes lease shutdown shielded, bounded and idempotent under concurrent
close calls, joins renewal before one release attempt, and rejects duplicate
renewal start. Failed release still reports infrastructure degradation and relies
on the existing token TTL. Redis subscription startup uses a bounded shielded
`finally` release when admission cannot complete. Relay duplicate start is
rejected; closing joins all three relay/heartbeat workers even if subscriber
drain fails. Existing outage/reconnect, capacity, stale-cache, session/process,
sequence/time and fail-closed tests remain in force. Redis remains ephemeral
observation/resource infrastructure and has no trading authority.

The only dependency declaration addition is **`anyio>=4,<5`**, because application
code now directly uses AnyIO's structured concurrency and shielding APIs.
Existing transitive versions were retained; no dependency downgrade or httpx2
workaround was applied.

### Verified dependency matrix

Each installation used a separate Python **3.12.14** Linux virtual environment.

| Dependency | `.[test]` | `.[test,ml,redis]` | `.[test,ml,redis,yahoo]` |
| --- | --- | --- | --- |
| FastAPI | 0.143.0 | 0.143.0 | 0.143.0 |
| Starlette | 1.7.0 | 1.7.0 | 1.7.0 |
| AnyIO | 4.15.1 | 4.15.1 | 4.15.1 |
| httpx / httpcore | 0.28.1 / 1.0.9 | same | same |
| httpx2 | absent | absent | absent |
| pytest / pytest-asyncio | 8.4.2 / 0.26.0 | same | same |
| Uvicorn / websockets | 0.54.0 / 15.0.1 | same | same |
| redis / fakeredis | 8.1.0 / 2.39.0 | 6.4.0 / 2.39.0 | 6.4.0 / 2.39.0 |
| sklearn / yfinance | absent / absent | 1.9.1 / absent | 1.9.1 / 1.7.0 |

Both Redis client combinations pass. Fakeredis brings a Redis client into the
test environment, but disabled application mode never constructs an
infrastructure client or lease. Default mode does not require a running Redis
service. `pip check` and `compileall -q app` pass in every matrix environment.
The remaining single warning is upstream Starlette's httpx TestClient
deprecation. It is documented and does not imply httpx2 solves the race.
These are tested combinations, not a claim that every version in the declared
ranges has been tested or that Linux establishes macOS compatibility.

### Regression and repeatability acceptance

`backend/tests/test_phase121_websocket_reliability.py` adds **21 cases**: nested
clients closing in both orders with/without Redis, early and blocked-send
disconnect, AnyIO level cancellation with an event-gated child drain, native parent
cancellation propagation, unexpected send errors, transport disconnect without
duplicate close, accept failure, lease loss, concurrent lease release, repeated
lifespans with connected clients, post-shutdown admission rejection, unchanged
real PAPER orders/accounting/authorization under reconnect (including manual
kill), cancellation during accept with real fakeredis capacity, duplicate relay
start/identity replay, and preservation of original plus cleanup errors.
Synchronization uses events and bounded deadlines; sleeps do not make race tests
pass. Replaying the event-gated cancellation test against the original handler
fails. The accept-cancellation test additionally checks actual Redis capacity release.
Existing local-only and forwarded-header security tests remain unchanged.

| Final verification | Result |
| --- | --- |
| New regression file | **21 passed, 0 failed, 0 skipped, 1 warning** |
| Focused existing + new WebSocket files | **66 passed, 0 failed, 0 skipped, 1 warning** |
| Each of the exact ten historical tests, separately | **10/10 processes passed** |
| Ten historical tests together, ten fresh processes | **100 passed total**, no failure/timeout; normal/reverse/seeded shuffled orders |
| New regression file, ten fresh processes | **210 passed total**, no failure/timeout |
| Full default suite, three fresh processes | **1068 passed, 0 failed, 1 skipped, 1 warning per run** |
| Full extended installation | **1069 passed, 0 failed, 0 skipped, 1 warning** |
| Full complete optional installation | **1069 passed, 0 failed, 0 skipped, 1 warning** |
| Frontend locked installation / tests | **84 passed, 0 failed, 0 skipped** |
| TypeScript / production build | Passed; Vite **7.3.6**, Node **24.19.0**, npm **11.9.0** |
| Generated terminal schema equality | Passed; `phase12-v1` and committed schema unchanged |
| Historical audit bytes / scope / diff whitespace | Preserved / reviewed / passed |

No test was weakened, skipped for cancellation, or marked xfail. No automatic
rerun plugin was used. Two initial new-test fixture assertions were corrected to
seed real market evidence and respect authorization's intentional null value
under manual kill. One initial sandbox-only full-suite launch was stopped and
replaced with a proper loopback-enabled invocation; it is not counted as a pass.

### Vite EPIPE and real integration

A real Uvicorn backend and Vite frontend ran on `127.0.0.1:8000` and
`localhost:5173`, using DEMO/PAPER with testnet-order submission disabled.
The four requested REST routes (`health`, `references`, `risk`, `vault`) returned
200 through Vite. An independent websockets client completed **24 sequential
connections and two pairs of simultaneous clients**, received valid shared
session/process frames, and closed cleanly. The actual compiled frontend socket
controller, using Node's real WebSocket implementation, started before the backend,
retained its valid-frame timestamp while disconnected, then recovered only from
valid new-process evidence after a backend-process restart. Services stopped
gracefully and backend logs contained no unexpected exception.

Actual headless **Chromium 151.0.7922.173** UI acceptance also passed: five page
refreshes, three local tabs, tab closure, Uvicorn stop/start while the page remained
open, visible disconnected state with unchanged last-valid timestamp, a new-session
frame/restart notice, and a real Vite hot update of the existing socket module.
Direct inspection of the real runtime confirmed zero clients after tabs closed
and shutdown, completed publisher/venue tasks, and clean repeated lifespans.
There were no browser page exceptions. A nonfatal browser resource 404 was logged
but not identified by page-response monitoring; it is not counted as an all-clean
browser console. An initial browser harness used Promise-valued polling predicates
and failed its evidence assertion; synchronous store polling corrected the harness
and the actual checks subsequently passed.

**EPIPE was reproduced independently after A2-005 was fixed.** Vite logged
`write EPIPE` during deliberate browser refresh/remount/connection replacement,
while the backend continued delivering valid terminal frames and clients cleaned
up. Its bundled proxy writes an upgrade response and pipes the browser/upstream
sockets; close cleanup ends the partner socket, so in-flight writes to an abandoned
socket can fail. Development React StrictMode mounts/unmounts the socket effect;
the existing cleanup closes that obsolete connection. Backend absence produced
`ECONNREFUSED`; stopping/restarting or abandoning active sockets also produced
`ECONNRESET`. These are observed transport-disconnection diagnostics, separate
from the unmarked cancellation escaping TestClient cleanup. No evidence required
a frontend reconnect or proxy change: existing obsolete-socket guards, one retry
timer, bounded backoff, watchdog cleanup, invalid-frame timestamp protection and
provider freshness tests passed. Proxy logs remain enabled. An EPIPE on a stable
active connection, loss of valid recovery, leaked client, or backend exception
still requires investigation; this record does not classify every EPIPE as benign.

### Exact Linux and macOS verification

For each dependency matrix, create a separate Python 3.12 environment, install
the indicated extras, and run the same commands; do not mutate one installation
between matrix results:

```bash
cd backend
python3.12 -m venv ../work/phase121-default
source ../work/phase121-default/bin/activate
python -m pip install -e '.[test]'
python -m pip check
python -m compileall -q app
python -m pytest -q
python -m pytest -q tests/test_api.py tests/test_audit_local_publisher.py \
  tests/test_phase11_api_static.py tests/test_phase12_websocket.py \
  tests/test_redis_lifespan.py tests/test_phase121_websocket_reliability.py
```

For the user's Mac, confirm `python --version` is **3.12.14**, then use this exact
repeatability block from `backend/` in the supported virtualenv:

```bash
historical=(
  tests/test_api.py::test_terminal_state_includes_market_adaptation_after_runtime_tick
  tests/test_api.py::test_terminal_state_includes_perp_context_after_runtime_tick
  tests/test_api.py::test_phase8_terminal_serialization_and_secrets_absent
  tests/test_api.py::test_phase9_agents_api_and_terminal_state
  tests/test_audit_local_publisher.py::test_two_websockets_share_cached_observation_and_cleanup
  tests/test_audit_local_publisher.py::test_local_loopback_request_and_browser_origin_work
  tests/test_phase11_api_static.py::test_terminal_websocket_has_compact_accounting_without_full_ledger
  tests/test_phase12_websocket.py::test_websocket_sequence_compact_fields_and_disconnect
  tests/test_redis_lifespan.py::test_disabled_mode_does_not_construct_a_redis_client
  tests/test_redis_lifespan.py::test_redis_websocket_relay_and_research_keep_existing_contracts
)
for run in {1..10}; do python -m pytest -q "${historical[@]}" || break; done
for run in {1..10}; do
  python -m pytest -q tests/test_phase121_websocket_reliability.py || break
done
for run in {1..3}; do python -m pytest -q || break; done
```

Use the extended `.[test,ml,redis]` and complete `.[test,ml,redis,yahoo]` extras in
separately named environments as above. Capture versions with `python -m pip
freeze` and preserve every failed run/trace; do not count only a later green run.
In two local shells, start:

```bash
# Backend shell, from backend/ with the chosen virtualenv activated
MARKET_DATA_MODE=DEMO EXECUTION_MODE=PAPER \
ENABLE_HYPERLIQUID_TESTNET_ORDERS=false \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend shell, from frontend/
npm ci
npm test
npm run typecheck
npm run build
npm run dev
```

Visit `http://localhost:5173`; verify the four REST routes and valid terminal
frames, refresh five times, use two additional tabs and close them. Stop the
backend with Ctrl-C while one tab stays open: require disconnected/stale state
without a new valid-frame timestamp. Restart it and require valid new session/
process evidence before connected/current state returns. Check invalid payloads
and stale providers cannot become fresh merely because the socket opens. Close
all tabs and gracefully stop both services. Record backend/Vite logs and exact
versions, correlate EPIPE with deliberate closes, and report unexplained errors
while an active connection should be healthy.

**Pending:** the user's Mac full/ten-test repeatability and browser/proxy checks;
external Redis service connection/outage/reconnect/shutdown (no real Redis server
was available here). Fakeredis acceptance does not establish external Redis
acceptance. Live providers and signed exchange acceptance remain outside this
milestone. Trading mathematics, risk/kill, final authorization, signing, PAPER
settlement/accounting and the terminal schema are unchanged. A2-005's targeted
Linux correction is accepted; full cross-platform closure is not claimed.

## Phase 12.2 — AMM Core Hardening & Quote Integrity

**MERGED / FIXTURE TESTED / LINUX ACCEPTED; MACOS ACCEPTANCE PENDING;
LIVE ACCEPTANCE PENDING.** PR #39 merged at
`777b59f42273442bc3387220e9eecfd5fc2da1ad`. Dedicated implementation branch:
`phase12/12-2-amm-core-quote-hardening`. Starting main was freshly verified as
`70a13c04a69924830487c934513e39d363ae653c`, including merged PR #38.
PRs #36–#38, Audit 2.0 A2-001–A2-005, architecture, existing tests and authority
contracts were reviewed before implementation. Both historical audit files are
preserved; no historical test was weakened or marked xfail.

| Finding | Scoped implementation and verified disposition |
| --- | --- |
| A2-001 | Executable compiler distance replaces stale mathematical distance; independent final and pre-transmission fair-value distance enforcement in PAPER and guarded TESTNET. The exact 3000 / 2000-tick / .2-bps counterexample is rejected; spoofed distance and reference metadata cannot bypass it. Scoped defect closed in Linux fixture acceptance; signed/live acceptance pending. |
| A2-002 | Shared rounded minimum, per-side budget and representable curve/allocation checks; atomic current-context compilation preflight; sanitized 422 for known infeasibility. Tiny-distance matrix and extreme quantization failures are rejected; representable larger side budgets remain valid and risk-bound. Scoped defects closed in Linux acceptance; future market/venue feasibility is not promised. |
| A2-003 | Side/price counts, quantities, notionals, logical-index lineage and aggregate chart depth. Default policy is **PRESERVE LOGICAL SLOTS + OBSERVE EFFECTIVE PRICES**. Diagnostic portion accepted; whole finding remains open pending an operational reject/trim/coalesce decision. |

The new backend acceptance module has **56 cases**, including a 240-combination
matrix covering both existing AMM models (160 ordinary compilations; 80 tiny
unrepresentable configurations rejected). Tests cover rounded floor feasibility,
coarse/exact/tiny ticks, crossed or falsified quotes, current versus missing
preflight evidence, API 200/422, no partial update, NORMAL/WIDEN/REDUCE/HALT,
inventory/adaptation/agent restrictions, same-price reconciliation, cohort PAPER
fills, accounting idempotence and manual kill. Existing reference and full
execution/authorization suites continue to pass.

The 100-slot/two-price fixture has 50 slots on each side, 4.9975 base quantity
per side, 14,992.00025 BID notional and 14,992.99975 ASK notional at 2999.9/3000.1.
Observation leaves fingerprints unchanged: first reconcile creates 100 independent
slots; identical reconcile keeps all 100 IDs; changed economics and removal still
produce ordinary replacement/cancellation. Suppressed quotes are absent from
later-stage depth. Proposal totals do not assert actually resting order status.

Frontend acceptance retains all 84 historical cases and adds **11**, covering
exact decimal aggregation, equivalent tick spellings, high-precision distinct
prices, collapse and invalid/absent evidence, suppression, aggregate bars and
read-only warnings. Terminal schema equality, TypeScript and production build pass.

See [Phase 12.2 verification and Mac instructions](PHASE122_ACCEPTANCE.md) for
exact commands, versions, completed counts, initial failures and limitations.
Phase 12.1 remains **MERGED / LINUX PASSED / MACOS PENDING USER VERIFICATION**;
cross-platform A2-005 closure remains **PENDING**. No Phase 12.1 infrastructure,
Phase 12.3 freshness work, new AMM, execution permission or dashboard redesign
is introduced.

## Phase 12.3 — Frontend Freshness, Session Integrity & Replay Protection

**IMPLEMENTED / LINUX REGRESSION AND LOCAL BROWSER ACCEPTED; DRAFT PR;
MACOS ACCEPTANCE PENDING.** Based on freshly fetched main
`777b59f42273442bc3387220e9eecfd5fc2da1ad`; PRs #38 and #39 verified merged.
See [Phase 12.3 acceptance and policy](PHASE123_ACCEPTANCE.md) for exact commands,
results, limitations and reproduction evidence.

**A2-004 CLOSED in the scoped frontend acceptance.** Before editing, the original
schema/store path accepted 2001 and 2099 advancing observations and A→B→A session
replay, set `connected`, cleared errors and advanced the arrival-time watermark.
The same cases now reject without replacing accepted evidence or retiring the
active identity. Historical audit reports remain unchanged.

- Envelope acceptance requires the full generated schema, then emission age
  **≤5000 ms** and future skew **≤2000 ms**. Boundaries are inclusive. This matches
  the existing ~one-second publisher and five-second watchdog for localhost.
  Malformed types, timezones and impossible dates remain schema failures. Full
  ISO fractions are compared so microsecond regression/skew cannot hide behind
  browser millisecond truncation. No adaptive clock-skew training is used.
- Same-process sequences must strictly increase, including session changes;
  gaps are allowed and noticed. Emission times must not regress; equal instants
  and equivalent timezone offsets are allowed. A previously unseen valid process
  may reset ordering. A valid session/process transition retires prior identity.
- FIFO histories retain **64 process/session pairs** and independently **64 retired
  processes**. Process retirement blocks an unknown session from resurrecting the
  process and survives same-process session churn. Eviction is finite: emission
  age and active-process sequence/time guards remain, but an evicted process with
  fabricated fresh evidence is not authenticated or indefinitely blocked. Memory
  survives socket reconnect, not browser refresh or a new tab.
- Store acceptance returns an explicit result. Only acceptance advances snapshot,
  sequence, emission/arrival watermarks and connected state or resets retry delay.
  Handshake alone stays connecting. Rejected streams cannot renew the watchdog;
  it checks both accepted arrival time and emission age. One controller owns the
  shared store across replacements; obsolete open/message/error/close callbacks
  and repeated close events cannot create state changes or duplicate retry loops.
  Cleanup clears timers; retry remains 1.5/3/6/10 seconds, capped at 10 seconds.
- Dashboard diagnostics expose connection, envelope age, shortened identity,
  accepted time/sequence, reconnect attempts, six categorized rejection counters,
  latest error and recovery notice. Counters saturate at **65535**; rejected payloads
  are not retained. Retained disconnected/error/connecting observations are
  historical; header/risk current prices are withheld. Source ages keep advancing
  in a display-only projection; provider timestamps, source decisions, risk and authorization are not rewritten. Provider
  health is explicitly **at emission**, separate from terminal connection health;
  historical System Health loses live green indicators. Backend authorization is
  labeled the last backend authorization. Yahoo remains observational-only.

| Completed Linux acceptance | Result |
| --- | --- |
| `npm ci` (workspace cache) | Passed; declarations and lockfile unchanged |
| `npm test` | **149 passed**, 0 failed/skipped; **95 historical + 54 new** |
| Historical frontend modules separately | **95 passed**, 0 failed/skipped |
| New integrity module, three final fresh-process runs | **54 passed per run**, 0 failed/skipped |
| TypeScript / production build | Passed |
| Complete backend `.[test,ml,redis,yahoo]` | **1125 passed**, 0 failed/skipped; 1 upstream warning |
| Three required terminal/WebSocket backend modules | **26 passed**; 1 upstream warning |
| `pip check` / compileall / generated schema equality | Passed; `phase12-v1` unchanged |
| Real Uvicorn/Vite/Chromium DEMO/PAPER | Startup before backend; advancing frames; three reloads; three tabs/closure; abrupt backend loss; historical retention; new-process restart; controlled timestamp/session/process rejection; source invariance; clean final shutdown |

The browser produced zero page exceptions and zero control POSTs. Backend-absent
health/proxy failures, StrictMode early socket closure and a resource 404 are
recorded in the detailed acceptance; browser console is not claimed wholly clean.
Expected Vite disconnect EPIPE/ECONNRESET/ECONNREFUSED diagnostics remain visible.
No persistent intended-active streaming failure was observed.

No backend implementation, execution/accounting authority, AMM mathematics,
Phase 12.2 normalization, provider quorum, RiskFirewall, kill switch,
FinalQuoteAuthorization or signing rules changed. No real venue orders were sent.
No `.github`, Actions, Docker, database, new provider/agent, MAINNET or Phase 13 work.

Phase 12.1 remains **MERGED / LINUX ACCEPTED / MACOS PENDING**; cross-platform
**A2-005 remains PENDING**. Phase 12.2 remains **MERGED / LINUX ACCEPTED / MACOS
PENDING / LIVE AND SIGNED ACCEPTANCE PENDING**; the **A2-003 operational collapse
policy remains deferred**. Phase 12.3 macOS, external-provider/Redis and long-running
clock/reconnect soak acceptance remain separate environmental gates.


## Phase 13.1 — Design Foundation

**IMPLEMENTED / LINUX REGRESSION AND LOCAL BROWSER ACCEPTED / DRAFT REVIEW.**
Starting base: `68949b04edb1099828f8bf5f9deca0afe4b85e62`, fetched current main
and independently verified PRs #38, #39 and #40 merged. PR #40's merged status
supersedes the historical draft wording in the Phase 12.3 record above; historical
acceptance records and audit reports are preserved.

Dark terminal design retained with shared palette/spacing/control/table tokens,
more readable labels, semantic named panels, shared loading/error/status states,
right-aligned order-table values, consistent original SVG navigation icons and
compact responsive observation diagnostics. Superseded shell CSS was consolidated;
existing page-specific charts, controls, financial precision and data provenance
remain. Typed native hash routes support twelve pages, bookmarks, reload and
browser history. Sidebar collapse is saved; the smaller-screen drawer supports
keyboard trapping, Escape/close, focus return and an inert background. Header
kill remains immediate/sticky; historical prices and strategy/risk observations
cannot present themselves as current.

Exact implementation files, visual audit, screenshots, commands, accessibility
scope, initial failures and limitations are in [Phase 13.1 acceptance](PHASE131_ACCEPTANCE.md).
Final frontend **164 passed** (149 preserved + 15 new), 0 failed/skipped; TypeScript
and build passed. Complete Python 3.12.14 backend `.[test,ml,redis,yahoo]`: **1125
passed**, 0 failed/skipped, 1 upstream warning; focused suite **84 passed**.
`pip check`, compileall, audit/schema/dependency/integrity preservation and diff
checks passed. No backend application implementation or contract changed; the
old static Vault-navigation assertion now checks route/link/page wiring.

Actual Uvicorn/Vite/Chromium 151 DEMO/PAPER: **72 page/viewport checks** across
1920, 1440, 1366, 1024, 768 and 390px widths, no document overflow, reachable kill,
refresh/history/collapse/preferences and mobile keyboard workflows. Existing
settings unsaved/422/Reset/valid Save, simulation without deployment, Start/Kill/
confirmed Resume leaving strategy stopped all passed. Separate actual backend
stop/restart preserves accepted evidence and historical labeling; ancient and
retired-process frames reject. Zero browser page exceptions; expected resource
404/invalid-request 422 and development disconnect diagnostics are documented.
This is scoped accessibility/local browser acceptance, not full WCAG, macOS,
provider, signed venue or extended soak acceptance. **Do not merge automatically.**

## Phase 13.2 — Trading Workspace UX

**PARTIAL / 13.2F IMPLEMENTED / 13.2G LOCAL ACCEPTANCE SCOPED / A–E PENDING.**
13.2.1 starts from fetched merged main
`d11acbd24d3944d4570bd855655c3aa0dbf4625a` (PRs #41 and #42 merged).
PR #42's exact quote matching and proposal/authorization separation are preserved
and extended for competing historical slots, replacements and partial fills.
Execution now has status/side/mode-evidence filters, stable timestamp/price/size/
status sorting, exact Decimal display, expandable lifecycle details and a bounded,
read-only, session-checked execution/reconciliation event timeline. OPEN/partial,
UNKNOWN and all terminal statuses stay distinct; historical or uncertain evidence
never claims confirmed resting liquidity. PAPER is explicitly simulated and
TESTNET evidence remains guarded/incomplete. Backend execution, signing, trading
permissions and accounting are unchanged.

Verified baseline frontend **175 passed**: all 164 Phase 13.1 cases plus PR #42's
11 cases were executed. Final frontend **213 passed**, 0 failed/skipped;
typecheck/build passed. Complete existing Python 3.12.14 optional-dependency backend
suite: **1124 passed, 1 failed, 0 skipped**, one upstream warning. The pre-existing
`test_generated_terminal_schema_is_current` Decimal-pattern mismatch remains an
integration gate; no schema or test weakening is included. Real local DEMO/PAPER
Chromium: **66 main assertions + 4 supplemental assertions** across Dashboard,
Markets, Strategy, AMM Settings, Risk and Execution at 1440/768/390px, including
configuration Save/Reset/422, lineage, sticky Kill/confirmed Resume, order filters/
sorting/details, timeline, actual backend stop/restart and freshness/replay probes.
Natural PAPER fill sample remains browser acceptance pending (zero fills in scoped
probes); fill presentation/statuses are regression covered. Acceptance configuration
was restored and the strategy stopped. Full implementation, commands, results,
limitations and evidence:
[13.2.1 acceptance](PHASE1321_ACCEPTANCE.md).

**13.2A–E implementation and feature acceptance remain pending:** Dashboard command
center, Markets workspace, broader Strategy lineage workflow, AMM Settings workflow
and backend-supported preview, and broader Risk workflow. Existing-page acceptance
does not establish these redesigns. Full Phase 13.2 is not complete. Preserve
macOS, external-provider, real Redis, signed TESTNET, extended soak and existing
A2-003/A2-005 gates. No signed TESTNET orders were sent. Dedicated **13.2.1 draft
PR against main; do not merge automatically.**

## Phase 13.3 — Research & Operational UX

**PARTIAL — 13.3A/B IMPLEMENTED / LOCAL ACCEPTANCE / DRAFT REVIEW.**
Phase 13.3.1 improves the existing Agents and Vault pages on verified merged
main `616ab5b7dc1b48c2573cad5c4f41dffadc4cf1c4` (PRs #43 and #44 confirmed
merged). Six inspectable agent cards, supervisor overview, explicit recommendation/
risk/authorization/execution separation and bounded read-only agent-event filters;
capital/PnL hierarchy, backend consistency status, exact decimal ledger filters/
details and full accounting provenance. Session/process/connection transition keys,
abortable requests and market/mode/version/fingerprint checks protect ledger
attribution. REST ledger/events do not declare a terminal session ID; this is a
client safeguard, not cryptographic session binding or persistent recovery.

Frontend **262 passed**, 0 failed/skipped; TypeScript and production build pass.
Backend **1124 passed, 1 failed, 0 skipped**, one upstream warning; the known
`test_generated_terminal_schema_is_current` failure remains. Local DEMO/PAPER
Chromium acceptance and browser-only partial-economics/race fixtures are recorded
with commands, screenshots and limitations in
[Phase 13.3.1 acceptance](PHASE1331_ACCEPTANCE.md).

**13.3C–G remain pending:** Advanced Analytics, Simulation & Optimization,
Operational Logs, Settings and full feature acceptance. Twelve-route viewport
regression does not complete those features or Phase 13.2A–E. Phase 14/15,
macOS, external providers, real Redis, signed TESTNET, long-soak and unrelated
audit/schema gates remain excluded/open. No trading/accounting authority or
backend application contract changes. One draft PR; do not merge automatically.
