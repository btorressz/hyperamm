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
