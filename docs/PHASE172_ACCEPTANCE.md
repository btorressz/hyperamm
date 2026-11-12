# Phase 17.2 — Isolated Multi-Market PAPER Simulation

Base: latest merged main `d7105ccea9675bc0725458260d520e9e637394a8` (PRs #73/#74). This implementation executes independent scenario research, with no portfolio-wide economics or operational trading authority.

## Requirements and architecture

The supplied Phase 17.2 requirements call for one, two or three BTC/ETH/SOL markets, exact independent capital, captured market-specific settings, deterministic sequential execution, full native evidence validation, one shared admission, bounded local JSON, fail-closed errors and native regression. Phase 17.3 owns coherent portfolio accounting/shared-capital risk; 17.4 owns correlated stress; 17.5 owns the terminal; 17.5–17.6 owns browser acceptance. Phase 16.6B durable lifecycle remains deferred.

Reviewed the requested portfolio, simulation, replay/comparison, accounting, risk, infrastructure and API modules; predecessor contract/acceptance documents; and `docs/ROADMAP.md`. The original standalone Phase 16–17 roadmap is absent from this checkout/upload. Its scope is recorded in the supplied request and the Phase 17.1A contract document, which cites original pages 10–11. No claim of directly inspecting that unavailable original is made.

| Breakdown | Reused or changed |
| --- | --- |
| REUSE unchanged | `PortfolioResearchConfig`, allocation arithmetic and configuration provenance; `ComparisonConfigSnapshot`, `ScenarioInputCapture`, `ScenarioProvenanceReceipt`, `CapturedScenarioResult`; `SimulationEngine`, deterministic scenarios, market profiles, Research Vault conversion, native SimulationResult/metrics/assumptions; accounting services/ledger/funding, agents and firewall; optional Redis coordination; local security/body middleware and application lifespan |
| ENHANCE | `simulation/service.py`: allowlisted delegation, opt-in preservation of captured strategy, generated-dataset identity check; `simulation/executor.py`: one allowlist entry; `portfolio_research/models.py`: distinct execution request, internal native evidence, market receipt and executed bundle; portfolio constants/exports; `main.py`: router registration |
| ADD | `portfolio_research/orchestration.py`, `service.py`, `aggregation.py`; `api/portfolio_research.py`; five focused test suites, fixture extension and a small explicit resource harness; this report |

Existing types/functions were identified before implementation. No accounting or risk formula, fingerprint algorithm, simulation engine implementation, worker pool, queue, storage service or operational adapter is duplicated. `simulation/models.py`, the engine and frontend source remain unchanged.

Flow:

```text
LocalOnlyBoundary → existing 65,536-byte body bound → typed request
  → existing optional Redis lease → existing single research worker
    → request/config/provenance revalidation and canonical order
    → BTC run_scenario → validate full native evidence → compact receipt
    → ETH run_scenario → validate full native evidence → compact receipt
    → SOL run_scenario → validate full native evidence → compact receipt
    → validate complete bundle → serialize and enforce 200,000-byte bound
  → revalidate response → return the exact bounded JSON bytes, no-store
```

Unselected markets are skipped. No child calls `execute()`. Only compact receipts remain between markets; full dataset/result objects are released after their iteration. The coordinator consumes explicit captures and has no operational runtime dependency.

## API and contracts

`POST {settings.api_prefix}/portfolio-research/run` (default `/api/v1/portfolio-research/run`) accepts `PortfolioResearchRunRequest`:

- `config`: complete existing `PortfolioResearchConfig`, including budget, allocations, scenarios/canonical five-domain captures and static risk limits.
- `config_fingerprint`: `config.fingerprint()`, verified against the 17.1A canonical identity.
- Extra fields, including client result objects, are rejected. Existing PAPER/DEMO, no-authority and source restrictions apply.

Python callers construct `PortfolioResearchRunRequest(config=config, config_fingerprint=config.fingerprint())`. A runnable native example is `backend/tests/phase172_fixtures.py:request_for`; it extends the accepted 17.1A fixture builders. There is no new operational configuration lookup or implicit Research Vault override. Vault proposals can still be converted with existing `ResearchVaultConfig.to_simulation()` before capture.

Response is `PortfolioExecutedResult`, version `phase172-executed-v1`: canonical config and fingerprint, selected market tuple, complete market receipts, exact unallocated reserve, `COMPLETED`/`VALIDATED`, PAPER/simulated/read-only/no-authority flags, explicit limitations and bundle fingerprint. Each receipt includes:

- Existing scenario provenance with captured strategy/agent/risk/accounting/execution/controls/profile domain hashes, requested scenario/frames, original dataset/run/full-result hashes and engine version.
- Original native metrics, native PAPER Vault snapshot, representative market assumptions and typed execution assumptions; no financial values are recomputed.
- Native accounting fingerprint; retained ledger suffix fingerprint/count (at most the existing 500 rows), original retained trace count and receipt fingerprint.

The full native result is validated before projection: receipt/result agreement, captured input equality, scenario/frame/market identity, exact capital, complete PAPER accounting, native accounting fingerprint, retained ledger head/hash links, and fill/order markets. A re-bound foreign-market accounting snapshot is rejected independently of its full-result hash. `run_scenario` verifies the result's dataset fingerprint against the dataset actually generated in that job.

Wire receipts independently revalidate their native nested contracts, matching scenario/profile/dataset/execution/accounting/capital identities, complete selected-market set, canonical order, reserve and hashes. Hashes detect altered evidence; they are not signatures. The omitted full result cannot be reconstructed or independently rehashed from a projection. Its original hash remains distinct from the projection/bundle hashes. No endpoint accepts a projected receipt as authoritative execution evidence.

The existing `PortfolioResearchResult` retains `NOT_EXECUTED` placeholder semantics. No version migration reinterprets old evidence.

| HTTP | Meaning |
| --- | --- |
| 200 | All selected markets completed with validated bounded receipts |
| 413 | Existing request-byte bound or new response-byte bound exceeded |
| 422 | Invalid configuration/fingerprint, workload budget or native evidence |
| 429 | Existing worker busy/shutting down |
| 503 | Optional research coordination unavailable |
| 500 | Sanitized internal computation/serialization failure |

Responses/errors use `Cache-Control: no-store`; existing global sanitized validation and local Host/Origin/peer/forwarded-header policies remain active. Serialization happens inside the admission and again at the HTTP boundary using the same bounded encoder. Exact encoded-byte boundary tests cover acceptance at the cap and 413 one byte below the output size. There is no unguarded subsequent FastAPI serialization.

## Isolation, capital and determinism

`SimulationEngine` retains only `network_access=False`. Its `run()` creates a separate clock, PAPER adapter, order manager, history, telemetry, agent supervisor, firewall, metrics, quotes, inventory/accounting and trace. Native tests retain actual objects and prove distinct ownership, nonzero fills/funding, full-output equality with fresh standalone runs, and detached receipts after poisoning a retained market's accounting state. Outputs include orders, fills, pending cancellation deadlines, traces, inventory and accounting evidence in these comparisons. This proves run-local state rather than relying on labels alone.

Captured AMM settings are preserved exactly. The new explicit `preserve_captured_strategy` scenario option skips operational market adaptation; the existing capture validator still requires matching supported profiles and DEMO/PAPER strategy. Native coverage includes a concentrated pool with a deliberately non-anchor reserve ratio that normal adaptation would overwrite. Scenario/agent/risk/simulation/accounting/profile snapshots are reconstructed from the immutable validated capture; effective receipt equality rejects substituted/default inputs.

Exact 17.1A Decimal allocations become independent engine/accounting starting balances: BTC 40,000, ETH 35,000, SOL 20,000 USDC, with 5,000 reserve unexecuted. No float capital arithmetic, shared cash, borrowed inventory or active shared account is introduced. Tests cover all seven nonempty market combinations and all six three-market request permutations. Reordered inputs produce identical complete bundles; repeated identical runs preserve original per-market hashes.

Market profiles retain their source labels, precision and profile hashes. Generated scenario datasets and original representative timestamps remain market-specific; similar synthetic timestamps establish no verified exchange-event synchronization. No historical dataset reference or authenticated source is fabricated.

Operational before/after snapshots cover selected strategy/market, agent/risk settings, kill switch, authorization, orders/fills, ledger/accounting/reservations, execution adapter, TESTNET enabled/signing authority references, market history/listeners and settings identity. No operational account, wallet setting, observer, historical file or Research Vault is passed into or modified by portfolio execution. Existing native single-market/TESTNET/risk regressions remain required.

## Admission, failures and recovery

One allowlisted operation occupies the existing local worker and, when enabled, one Redis lease. Native tests block execution at ETH and verify BTC/ETH/SOL sequential calls with exactly one pool submission; every competing research operation is denied. Both directions are covered for ordinary simulation, optimizer, Historical Replay, Scenario/Historical Comparison and Research Vault comparison. HTTP competition also exercises genuine 429 responses through the router.

Request cancellation shields the active worker. Admitted markets continue; shutdown closes further admission and waits for actual completion. Tests prove local and coordinated cancellation ownership, lease retention/release, shutdown waiting, mid-market failure, no automatic retry and successful later admission. Existing Redis code is unchanged; fakeredis/Lua evidence proves compatibility, not physical Redis service acceptance.

Validation/profile/capture failures are rejected before computation. Injected generation, engine, wrong-dataset, accounting and fingerprint failures stop at ETH without running SOL or returning a partial 200. Bundle/serialization failures after all markets also fail closed. Errors omit private test paths and raw exceptions. Worker release follows actual completion/failure. There is no resume, durable recovery, authoritative cancellation, queue or per-frame progress.

## Resource bounds and observations

| Bound | Enforcement |
| --- | --- |
| Selected markets | 1–3 existing BTC/ETH/SOL identities |
| Per-market frames | Existing 2–5,000 contract retained; execution also obeys total budget |
| Total executed frames | 3,000 across all selected markets |
| Quote work | Sum of frames × configured levels per side ≤24,000; two-sided potential quote count ≤48,000 |
| Retained trace points | Sum of min(frames, configured trace retention) for enabled traces ≤1,500 |
| Configured ledger capacities | Sum ≤30,000, existing HALT_WHEN_FULL policy retained |
| Configured event capacities | Sum ≤750; existing firewall/agent histories remain bounded |
| Request | Existing pre-parse 65,536 bytes, including chunked requests |
| Response | 200,000 UTF-8 JSON bytes; original traces/orders/fills/ledger rows omitted |

Budget violations reject captures; controls are never silently truncated or rewritten. The total frame budget is below the accepted single-market 5,000-frame ceiling, and quote work prevents three wide 50-level workloads from bypassing it. Three 5,000-frame simulations are not admitted. Full native result histories retain existing internal bounds; results are projected before the next market. There is no timeout-based early admission release or universal latency guarantee.

Four cold process observations, serial after the full regression and frontend commands, using `phase172_near_limit.py` and the real `SimulationExecutor`. All use FLASH_MOVE, exact assigned capital and 120 retained trace points per market. Wide ladders retain native strategy feasibility. Modeled execution enables latency, delayed cancellation, slippage, depth sensitivity and partial participation.

| Workload | Total frames | Frame × levels | Worker seconds | Response bytes | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| BTC/ETH/SOL ×1,000, 8 levels | 3,000 | 24,000 | 32.7948 | 63,115 | 69.05 |
| BTC ×3,000, 8 levels | 3,000 | 24,000 | 23.6374 | 22,384 | 104.29 |
| BTC/ETH/SOL ×160, 50 levels | 480 | 24,000 | 4.7600 | 63,587 | 56.34 |
| BTC/ETH/SOL ×1,000, modeled | 3,000 | 24,000 | 20.5351 | 63,203 | 69.07 |

Every output independently roundtrips through the executed contract, preserves original result hashes, releases admission and shuts down. Native fill counts respectively: `[2,8,0]`, `[2]`, `[81,7,1]`, `[2,15,0]`; ledger versions: `[4,16,0]`, `[4]`, `[162,14,2]`, `[4,30,0]`. Risk limits can suppress trading without invalidating completed scenario research. These workloads do not fill the 30,000-entry retention allowance. One sample per case is a resource observation, not a distribution, SLA or causal speedup claim. Linux RSS includes imports/setup and is each fresh process's cumulative high-water mark.

Reproduce from repository root (use the prepared interpreter):

```bash
for case in three single wide modeled; do
  PYTHONPATH=backend:backend/tests work/venv/bin/python backend/tests/phase172_near_limit.py --case "$case"
done
```

Original fingerprints, environment and compact results are retained in [validation-results.json](acceptance/phase172/validation-results.json). Raw logs/JSON remain ignored under `work/`. No screenshots, raw profiler dumps or redundant large artifacts are committed.

## Validation

Prepared Python 3.12.14 virtualenv with the existing backend `[test,redis]` extras; Node 24.19.0/npm 11.9.0. Existing manifests/lockfile are unchanged. Environment details are in the compact JSON.

| Command/check | Actual result |
| --- | --- |
| Existing five Phase 17.1A suites, untouched main worktree | PASS: 115 passed; 12.64 s |
| Existing five Phase 17.1A suites, final branch | PASS: 115 passed; 9.83 s |
| Five Phase 17.2 focused suites, final branch | PASS: 90 passed, 0 failed/skipped; 51.52 s |
| `cd backend; ../work/venv/bin/python -m pytest tests -q -rs` | PASS: 2,725 passed, 0 failed, 1 optional ML skip; 211.23 s |
| `cd frontend; npm ci --cache ../work/npm-cache` | PASS; lockfile unchanged |
| `npm run typecheck` / `npm run build` | PASS / PASS |
| `npm test` | PASS: 717 passed, 0 failed/skipped; 15.140 s |
| Four explicit near-limit native worker processes | PASS; exact observations above |
| `git diff --check`; unchanged frontend/engine/accounting/risk/coordination comparison | PASS |
| Dependency consistency (`python -m pip check`) | PASS |

Backend runs report one existing Starlette TestClient/httpx deprecation warning; the optional ML skip is missing `sklearn`. Frontend build reports existing dependency `use client`/chunk-size warnings; none is suppressed or changes success status.

Focused commands, from `backend`:

```bash
../work/venv/bin/python -m pytest tests/test_phase171a_contracts.py \
  tests/test_phase171a_allocation.py tests/test_phase171a_provenance.py \
  tests/test_phase171a_isolation.py tests/test_phase171a_hardening.py -q -rs
../work/venv/bin/python -m pytest tests/test_phase172_orchestration.py \
  tests/test_phase172_market_isolation.py tests/test_phase172_provenance.py \
  tests/test_phase172_worker.py tests/test_phase172_api.py -q -rs
```

The focused suite includes actual production-uvicorn loopback success/security/body-bound and unavailable-coordination cases, in addition to native TestClient and worker tests. Initial new tests reported 23 passed/2 failed (native Fill-source validation and incorrect test kill-switch setup); both were corrected before the 86-case intermediate pass and final 90-case pass. The initial branch compatibility run reported 114 passed/1 failed because of the old exact five-file package assertion; its scope extension is explained below. The initial system interpreter lacked pytest, so all reported acceptance runs use the prepared virtualenv. No failing case was disabled or hidden.

## Bugs and compatibility

1. Normal market adaptation would overwrite already captured custom AMM reserves. Added the explicit captured-strategy path and exact effective snapshot comparison; single-market defaults remain unchanged.
2. Initial new validation incorrectly expected a `simulated` field on native Fill dictionaries. Corrected it to the existing baseline/modeled PAPER source contract; native modeled fills/funding pass.
3. The Phase 17.1A static package-list assertion encoded the historical five-file contract-only package. Extended its exact allowlist to the three required orchestration modules while retaining every forbidden runtime/API/engine-construction/task-creation scan. No test was disabled; placeholder and purity protections remain.
4. Added the generated dataset identity check at the captured scenario boundary and fail-closed semantic accounting validation before projection. Error messages and transport stay bounded.

## Gates and deferred work

Phase 17.3 can build on independent validated receipts and exact allocations; coherent portfolio accounting, temporal compatibility and shared-capital research risk are not established by these independent runs. Correlated stress, React portfolio pages/charts and browser acceptance remain later work. Physical Redis remains a separate external gate; durable restart recovery remains Phase 16.6B.


| Gate | Status / evidence |
| --- | --- |
| Phase 17.1A compatibility; unchanged NOT_EXECUTED semantics | PASS |
| One-, two-, three-market PAPER execution; all combinations | PASS |
| One shared admission; canonical BTC/ETH/SOL order | PASS |
| Independent engine/agent/risk state; orders/fills/inventory | PASS |
| Independent funding/accounting; exact allocations and reserve | PASS |
| Market-specific captures/source provenance; deterministic original hashes | PASS |
| Incomplete-result rejection; failures and later admission | PASS |
| Competing operations; local/coordinated cancellation and shutdown | PASS |
| Operational trading/observer/settings isolation | PASS |
| Workload and request/response bounds; actual FastAPI/uvicorn HTTP | PASS |
| Focused and full backend regression; frontend compatibility | PASS |
| Compact acceptance evidence | PASS |
| Portfolio economics/shared-capital risk (17.3) | NOT RUN — deferred |
| Correlated stress (17.4); React terminal (17.5) | NOT RUN — deferred |
| New full browser acceptance (17.5–17.6) | NOT RUN — no UI changes |
| Physical Redis service | BLOCKED — no redis-server executable; separate external gate |
| Durable lifecycle/restart recovery (16.6B) | NOT RUN — deferred |
