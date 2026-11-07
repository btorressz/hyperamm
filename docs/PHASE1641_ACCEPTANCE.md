# Phase 16.4.1 — Historical Replay Studio acceptance and hardening

## Disposition

**Fixture acceptance: PASS. Full backend regression: FAIL / NOT GREEN. Unconditional owner acceptance: NOT READY.**

Native compilation, focused tests, production build and actual Chromium acceptance ran successfully. The full tree still has three static documentation failures, reproduced on an untouched latest-main worktree. No introduced failing test was found. This report supports review of the hardening changes; it does not waive those failures or establish genuine historical-market acceptance.

- Review date: 2026-11-07.
- Starting main: `baef856a3322c922acc1cc2a6db86572100295a7`.
- PR #60 is merged: merge commit `505572a1d349464f6ec52b9a04af1d2b70a9428c`, implementation head `85d3ad25192b7c5494fce004a6cea2588406ff42`.
- Final implementation and test-source commit: `ae79b389963705da6db146763d5a00e6c3ac9dc9`. The following documentation/evidence commit records these results without changing application code.
- Branch: `phase16/16-4-1-replay-acceptance`. Draft PR only; no automatic merge.

## Gates

| Gate | Disposition | Evidence / limits |
| --- | --- | --- |
| Merged implementation review | PASS | Reviewed the historical API, contracts, importer/storage/validation, adapter/runner/summary/provenance, simulation/executor/service/engine, research/PAPER execution and the complete replay frontend, surrounding Simulation/App/chart/trace integration and prior reports. |
| Native dependency and startup baseline | PASS | Python 3.12.14 venv, declared `[test,redis]` extras, clean `pip check`; lockfile-based npm install. Real Uvicorn/FastAPI lifespan startup, replay routes, shutdown and restart exercised by Chromium harness. |
| Focused native replay regression | PASS | **348 passed**, zero failures/skips; [JUnit](acceptance/phase1641/focused.xml). Includes Phase 16.1A–16.4 tests and 13 new acceptance cases. |
| Frontend contracts and native serialization | PASS | Actual serialized Pydantic BTC/ETH/SOL receipts reproduce from the existing engine. Source fingerprint differs from segment fingerprints; primary/baseline archives retain independent run identities. Legacy Phase 16.2 serialized receipt still round-trips unchanged in native tests. |
| Controlled end-to-end research | PASS | Existing Python importer → private storage → summary/provenance HTTP → React selection → real replay POST → chart/L2/timeline → per-segment PAPER metrics/trace/comparison. Generated synthetic and user-asserted recorded labels, gaps, generation changes, missing economics and zero fills covered. |
| Operational isolation and authorization | PASS | Existing seeded tests with kill switch OFF/ON, actual PAPER fills/orders/capital reservations, ledger, inventory, signer identity/configuration and risk snapshot; active Phase 15 SDK fixture subscriptions and consumer queues survive HTTP replay and accept subsequent callbacks. See isolation detail below. |
| Request lifecycle and navigation | PASS | StrictMode, delayed provenance, selected dataset/model edits during replay, rapid repeated submissions, unmount/remount, removed catalog entries, service failure/restart and disconnected terminal. Admitted worker ownership survives cancelled waiters in existing native tests. |
| Historical presentation and bounds | PASS | Microsecond receipt ordering, separate segment charts, retained L2 sizes/order/truncation, missing metrics, backend Decimal PnL/deltas; 4,999 viable frames and 32 segments natively; 5,000-coordinate/200-row frontend bound. |
| HTTP/security/error behavior | PASS | Actual 200, invalid/structured 422, shared-slot 429, storage/admission 503, sanitized 500, empty/corrupt/private-permission vaults, identity mismatch, Host/Origin/body protection, malformed/oversized frontend evidence. Existing peer/framing/security suites remain in full regression. |
| Actual Chromium | PASS — FIXTURES | **16 workflows**, five widths, no page exceptions or unexpected console errors. [Machine report](acceptance/phase1641/browser-results.json). These are generated-data screenshots, not exchange acceptance. |
| Full native backend suite | **FAIL — NOT GREEN** | **2,260 passed, 3 failed, 1 skipped**. Untouched baseline: **2,247 passed, 3 failed, 1 skipped**. Same three pre-existing documentation failures; no tests suppressed or assertions weakened. |
| TypeScript / production build / frontend tests | PASS | Strict TypeScript compile and Vite build; **685 tests passed, zero failed/skipped**. Dependency `use client` and bundle-size warnings remain warnings. |
| Genuine venue recording, licensing/authentication | NOT RUN | No genuine market archive or independently verified permission supplied. Deliberately outside fixture acceptance; no wallet, signer or exchange-order use. |
| Optional physical Redis daemon / ML training | NOT RUN | No `redis-server` executable or optional `sklearn` installed. Declared Redis/fakeredis/Lua and coordination/lifespan tests did run in the full suite; the one optional ML test is skipped. |

## Defects and fixes

1. **A valid archive hash did not bind the archive to its declared segment.** The native segment validator checked content hashes and comparison deltas but could accept a self-consistent archive whose primary run/dataset/metrics/trace belonged elsewhere. It now parses the existing `SimulationResult` model, checks segment/run identity, frame count, equity/PnL/fills and trace sequence/timestamp membership, and rejects a modeled archive substituted for its independent baseline. Archive strings have the same 16,000,000-character bound already used by the UI. No stored field names or fingerprints changed.
2. **Frontend validation was incomplete.** Existing tests primarily rejected a few hand-written malformed objects. Guards now check provenance hashes/counts/source flags, normalized request bounds/policies, captured PAPER configuration, segment totals, retained component/receipt shape, selected archive metrics/trace and baseline identity. Settings are bound to the captured request. Financial equality uses exact decimal spelling normalization; financial deltas remain backend-calculated. The selected segment alone is decoded. The browser is a display guard, not independent cryptographic verification or an accounting engine.
3. **Sub-millisecond receipts were collapsed by `Date.parse`.** Native Pydantic timestamps retain six fractional digits, while JavaScript date parsing truncates them to milliseconds. Catalog coverage and frame chronology could reject valid microsecond observations. Receipt comparison now preserves microseconds using integer time keys; a generated ETH receipt has four distinct frames within one JavaScript millisecond. Chart x coordinates retain original sequence identity.
4. **Dataset changes during a job could strand provenance behind a cached busy response.** Provenance queries now wait for this workspace's pending replay, retain immutable fingerprint-keyed successful provenance, and offer explicit retry after failure. Catalog identity changes retire retained results, and submission requires current, successful provenance/catalog state. Epoch checks discard late results after dataset/model edits or unmount. Query promises remain shared across StrictMode remounts: aborting an admitted metadata HTTP waiter would not release its worker slot.
5. **Untrusted evidence could allocate/render unnecessary work.** Historical HTTP JSON is byte-bounded before parsing, including chunked bodies (64,000,000 bytes; error details 64,000). Error banners whitelist fixed issue/field labels rather than echo arbitrary server strings. Archived strings have per-archive and aggregate budgets. Historical chart points are memoized; trace charts mount when their disclosure opens; observation tables disclose a 200-row display limit while retaining all supplied chart coordinates. The trace cap label now reflects the caller's actual cap instead of always saying 250.

## Changes

- Backend: `backend/app/research_replay/contracts.py` enhances the existing receipt validator. No second engine, worker, data service or execution path.
- Native acceptance: `backend/tests/phase1641_fixtures.py`, `backend/tests/test_phase1641_acceptance.py` use existing test fixtures, importer/storage, engine, HTTP and stream-service patterns.
- Frontend request/types/validation: `frontend/src/api/client.ts`, `frontend/src/types/replay.ts`, `frontend/src/utils/replayEvidence.ts`.
- Lifecycle/presentation: `frontend/src/components/replay/HistoricalReplayWorkspace.tsx`, `ReplayMarketChart.tsx`, `ReplayPerformance.tsx`, existing `frontend/src/components/HistoryChart.tsx` and `frontend/src/components/simulation/SimulationTrace.tsx`.
- Frontend tests: `frontend/tests/phase164-replay.test.cjs`, `phase1641-native.test.cjs`, `fixtures/phase1641-native.json`, `run.cjs`.
- Browser: `frontend/tests/browser-phase1641.py`, `frontend/tests/phase1641_browser_backend.py` reuse Phase 15 process ownership, Playwright, actual app and test-only fixture backend patterns. Fixture controls never register in the production entrypoint.
- Documentation: this report, `CHANGELOG.md`, and evidence under `docs/acceptance/phase1641/`. README, CODEBASE, Summary, lockfiles and unrelated acceptance reports are untouched.

## Environment and commands

[Exact versions](acceptance/phase1641/versions.json): Python **3.12.14**, Node **24.19.0**, npm **11.9.0**, TypeScript **5.9.3**, Vite **7.3.6**, Chromium **151.0.7922.173**, Playwright **1.62.0**. Backend dependencies were installed into the project venv. The preinstalled system Python supplies the browser harness; Uvicorn uses the project venv.

Commands below are relative to the repository root unless a subshell says otherwise. Initial `npm ci` failed because the default home cache was unwritable; repeating with a workspace cache succeeded, without changing the lockfile. Native commands were first run before backend changes, then repeated on the final implementation.

```bash
git fetch origin main
git switch -c phase16/16-4-1-replay-acceptance origin/main
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e 'backend[test,redis]'
backend/.venv/bin/python -m pip check
(cd frontend && npm ci)
(cd frontend && npm ci --cache /workspace/hyperamm/work/npm-cache)
(cd frontend && npm run typecheck)
(cd frontend && npm run build)
(cd frontend && npm test)

backend/.venv/bin/python -m pytest \
  backend/tests/test_phase164_catalog.py backend/tests/test_phase163_execution.py \
  backend/tests/test_phase162_replay.py backend/tests/test_phase161b_importers.py \
  backend/tests/test_phase161a_contracts.py -q

backend/.venv/bin/python -m pytest \
  backend/tests/test_phase1641_acceptance.py backend/tests/test_phase164_catalog.py \
  backend/tests/test_phase163_execution.py backend/tests/test_phase162_replay.py \
  backend/tests/test_phase161b_importers.py backend/tests/test_phase161a_contracts.py \
  -q --durations=3 -o junit_family=legacy \
  --junitxml=docs/acceptance/phase1641/focused.xml

(cd backend && .venv/bin/python -I -c \
  'import app.research_replay.models, app.research_replay.contracts, app.research_replay.importers, app.research_replay.storage, app.research_replay.runner; print("standalone installed-package imports PASS")')
(cd backend && .venv/bin/python -m pytest tests -q -rs)
python3 frontend/tests/browser-phase1641.py

git worktree add --detach work/phase1641/baseline baef856a3322c922acc1cc2a6db86572100295a7
(cd work/phase1641/baseline/backend && \
  /workspace/hyperamm/backend/.venv/bin/python -m pytest tests -q -rs)
backend/.venv/bin/python -m pytest \
  backend/tests/test_phase9_static.py backend/tests/test_phase8_static.py \
  backend/tests/test_phase10_static.py -q
git diff --check
```

The Chromium harness owns loopback Uvicorn (`127.0.0.1:8000`) and Vite (`127.0.0.1:5173`) and shuts them down in `finally`. It runs DEMO/PAPER with live observation, exchange orders and Redis disabled, and an offline research market catalog. It uses a fresh private fixture directory per run and preserves it across its actual backend restart. Browser fetches are observed, not replaced by mock responses.

## Baseline and regression results

Retained command output (trailing whitespace normalized): [untouched baseline](acceptance/phase1641/baseline-backend.txt), [final backend](acceptance/phase1641/final-backend.txt), [focused backend](acceptance/phase1641/focused-backend.txt), [frontend compile/build/tests](acceptance/phase1641/frontend.txt), and [standalone imports](acceptance/phase1641/standalone-imports.txt). [Machine-readable summary](acceptance/phase1641/test-results.json) records the disposition and counts.

| Run | Passed | Failed | Skipped | Meaning |
| --- | ---: | ---: | ---: | --- |
| Initial focused merged implementation | 335 | 0 | 0 | Actual pre-fix native baseline |
| Initial frontend | 657 | 0 | 0 | Actual pre-fix npm suite |
| Untouched `baef856` full backend | 2,247 | 3 | 1 | Separate detached worktree, same venv/dependencies |
| Final focused historical suite | 348 | 0 | 0 | Includes 13 new native acceptance cases |
| Final full backend | 2,260 | 3 | 1 | **NOT GREEN**; 13 additional passing cases |
| Final frontend | 685 | 0 | 0 | 28 additional passing frontend cases |

The same failures on both trees are:

- `tests/test_phase10_static.py::test_no_github_actions_or_forbidden_oracle_added`
- `tests/test_phase8_static.py::test_repository_contains_no_forbidden_oracle_provider_token`
- `tests/test_phase9_static.py::test_phase9_does_not_create_github_actions_or_forbidden_oracle`

A final targeted run after adding this report and the retained logs confirmed **3 failed, 15 passed**, with the same single unchanged document named by each failure. All identify unchanged `docs/PHASE155B_ACCEPTANCE.md`. It was not edited to make tests green. The optional ML skip is `tests/test_agent_expansion.py:406` (`sklearn` unavailable). The Starlette/httpx deprecation warning occurs on both baseline and final runs. TypeScript has no errors. Vite completes successfully with dependency directive warnings and a 640.57 kB main chunk warning; neither was treated as a functional failure.

## Isolation, economics and bounded performance

The Phase 16.2/16.3 seeded isolation tests execute through the original `SimulationExecutor` and copy current strategy/agent/risk settings. Before/after checks include operational configuration/market, strategy running state, resting orders/quotes, existing fills, ledger entries/fingerprint, accounting identity/configuration, reservations, inventory, authorization, kill-switch state, TESTNET enablement and signer identity/configuration. Both kill-switch states run across BTC/ETH/SOL, including rejected forged requests. The additional HTTP stream isolation test keeps the real Phase 15 service running with deterministic SDK callbacks and three subscribed consumer queues; replay preserves the connection/handles/generation/evidence/queues and subsequent callbacks still reach consumers.

Default historical inputs lack external reference evidence: the existing risk firewall can HALT all quotes. Zero fills and unavailable markout/capture values are correct evidence. A separate **explicit test-only** configuration disables the reference firewall before capturing the runtime state and supplies synthetic moving books, then runs actual HTTP modeled execution with latency, slippage, retained depth, participation and partial fractions. FinalQuoteAuthorization and accounting still run. Positive hypothetical fills, consistent accounting and Decimal baseline deltas are checked; before/after operational state is equal. This does not change production risk defaults or calibrate real fills.

The maximum admitted dataset has 5,000 component observations. One complete initial batch plus one new component per subsequent receipt yields **4,999 viable frames**, the reachable maximum under that vault cap; the request still accepts a 5,000-frame ceiling. The modeled-plus-baseline stress receipt is **6,091,256 bytes**, below the browser response budget, and took **28.61 seconds** in the final focused run. The 32-independent-segment modeled receipt is **504,155 bytes**. JUnit records the byte/frame properties. These are specific fixture measurements, not latency guarantees for every strategy/configuration.

A separate frontend regression supplies 5,000 chart coordinates and verifies all identities remain while the observation table renders only 200 rows plus its header. Segment archives stay lazy; unopened trace charts do not mount. No cross-gap equity/return is aggregated, no financial fill/PnL delta is recomputed in JavaScript, and L2/context source/receipt times retain their original semantics.

## Chromium evidence

[Browser report](acceptance/phase1641/browser-results.json) contains all 16 workflows, HTTP mutation paths, expected console messages, viewport measurements and screenshot names. Desktop/tablet/mobile widths **1920, 1440, 1024, 768 and 390** passed overflow checks and actual chart resizing. Controls have accessible labels used by the browser suite. No new dependency or charting library was added.

- [1920px modeled segmented fixture](acceptance/phase1641/fixture-modeled-gap-1920.png)
- [1440px](acceptance/phase1641/fixture-modeled-gap-1440.png), [1024px](acceptance/phase1641/fixture-modeled-gap-1024.png), [768px](acceptance/phase1641/fixture-modeled-gap-768.png), [390px](acceptance/phase1641/fixture-modeled-gap-390.png)
- [Positive partial PAPER fills — explicit fixture setup](acceptance/phase1641/fixture-positive-partial-fills.png)
- [Missing-economics 422](acceptance/phase1641/fixture-missing-economics-422.png), [worker-busy 429](acceptance/phase1641/fixture-worker-busy-429.png), [disabled storage 503](acceptance/phase1641/fixture-disabled-503.png)

Expected console entries are the intentionally refused terminal WebSocket, exercised 422/429/503 responses, Vite's 500 when the backend is deliberately stopped, and a favicon 404. Page exceptions and unexpected console errors are empty. Original scenario simulation, bounded optimization and Research Vault navigation run against their actual APIs after terminal reconnection. No browser mutation request targets operational trading or configuration endpoints.

## Remaining limits and owner decision

Recorded-native labels, permitted use and timestamps remain user assertions. Content hashes establish consistency, not an authenticated exchange source or a malicious-owner security boundary. Fixtures and screenshots establish neither real market delivery, source licensing, passive queue priority, calibrated latency/fills, profitability, continuous coverage nor real settlement. The browser does not independently recompute cryptographic archive hashes; the private backend validates the authoritative Pydantic receipt and archive hashes.

No importer/upload/wallet/signing/live-order endpoint, raw dataset download, worker, database, scheduler, container, CI workflow, state manager or portfolio accounting engine was added. Real Redis-daemon acceptance and optional ML training were not run. No actual exchange trading, funded account or genuine recording acceptance is claimed.

**Owner decision:** the controlled historical research workflows and hardening are validated, but Phase 16.4.1 remains a draft and is **not unconditionally acceptance-ready** while the full backend suite has three failures. Review the reproduced baseline failures and the stated source-trust limits explicitly; do not interpret this report as permission to merge automatically.
