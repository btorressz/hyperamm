# Phase 16.6C.2 — Local integration, deployment and UI acceptance

## Scope and revisions

Local Linux, single-operator DEMO/PAPER acceptance against latest `main`,
`538ab4abad1f1fbee185420617216ef45f42ad13` (merged PR #70). Branch:
`phase16/16-6c2-local-integration`. No merged Phase 16.6B was found in this ancestry.
Implementation revision and final gate counts are recorded in the compact
[validation summary](acceptance/phase166c/validation-results.json).

Environment: November 11, 2026 (Pacific), managed Linux x86-64; Python 3.12.14,
Node 24.19.0, npm 11.9.0, Chromium 151.0.7922.173; React 19.3.0,
TypeScript 5.9.3, Vite 7.3.6, FastAPI 0.162.4, uvicorn 0.54.0 and Pydantic 2.14.3. Python dependencies were
installed in a local virtual environment using the existing `[test,redis]` extras;
Playwright drives the existing browser harness. No product dependency was added.
All historical data is generated locally and explicitly admitted through the
existing importer and private storage. Recorded-native labels remain assertions.

## Implementation and ownership

Reused: FastAPI/lifespan, SimulationService, SimulationExecutor, optional
CoordinatedSimulationExecutor, historical contracts/importer/storage, Comparison
Studio, Replay Studio, React Query, PAPER accounting, provenance validators,
Lightweight Charts, shared status/diagnostics/workload components and scoped CSS.
No new production backend service, route, scheduler, queue, progress API or financial
calculation was introduced.

Enhanced:

- `HistoricalReplayWorkspace.tsx`: include existing process/session/connection
  identity in metadata keys and response guards; permanently retire old evidence,
  hide financial charts/archives immediately on mismatched identity, and retain a
  truthful retired state after pending input changes.
- `ScenarioReplayComparisonWorkspace.tsx`: retain retired status when an input or
  connection changes during a pending request, even before a receipt exists.
- `ResearchRunStatus.tsx` and both submission labels: awaiting a response does not
  establish worker ownership. No claimed frame progress, ETA or cancellation.
- `phase164.css`: share the existing flex container with Comparison Studio; its
  reused replay controls previously stacked without desktop spacing.
- `researchStatus.ts`: internal-failure guidance includes checking local backend
  availability because the existing Vite proxy returns HTTP 500 on connection refusal.
- `api/client.ts`: interrupted HTTP response streams are connection errors;
  malformed JSON/UTF-8 is invalid evidence; actual byte-budget violations retain
  size guidance. Previously all three were incorrectly reported as size failures.

Added/enhanced tests: nine production-uvicorn HTTP/configuration cases in
`backend/tests/test_phase166c2_local_integration.py`; three additional native Node
cases in `phase166c1-research-ux.test.cjs`; `--phase166c` and a focused helper within
`browser-phase165c2.py`. The existing fixture backend gains opt-in generated large/
long-identifier evidence and a test-only engine-failure control. These controls are
never mounted by `app.main:app`. Six PNGs and one compact JSON summary accompany
this Markdown; raw test logs, response bodies and network streams remain uncommitted.

## Initial native baseline (before production fixes)

| Command | Actual initial result |
| --- | --- |
| `cd frontend; npm ci` | Failed: default home cache unwritable; unchanged lockfile installed with workspace `--cache`, 27 packages |
| `npm run typecheck` / `npm run build` | Initial attempts lacked `tsc` after failed install; both passed after environment preparation; Vite build 2.81 s |
| `npm test` | Initial attempt lacked compiler; prepared unchanged baseline: **710 passed, 0 failed/skipped**, 14.901 s |
| `cd backend; python -m pytest tests -q -rs` | System interpreter lacked pytest; prepared unchanged backend: **2,490 passed, 1 skipped**, 146.04 s |
| Existing Chromium harness | **15 workflow groups passed**, 28.847 s, five widths, no page errors/unexpected console/network failures |

The optional ML training skip is missing scikit-learn. Existing React Query
`use client` bundling notices, Vite chunk-size warning and Starlette/httpx
TestClient deprecation remain visible; none was suppressed or made a new dependency.
The unchanged backend baseline ran before any backend production change (none was needed).

## Real backend connectivity and security

Production `python -m uvicorn app.main:app --host 127.0.0.1 --port <local-port>`
was started as a separate process for native HTTP checks. All six requested routes
were exercised: `/api/v1/health`, historical `datasets`, `dataset-summaries`,
`provenance`, `run`, and `/api/v1/research-comparison/scenario-historical`.
The browser uses real React/Vite on 127.0.0.1:5173, whose existing `/api` and `/ws`
proxy targets 127.0.0.1:8000. The browser fixture harness wraps the actual FastAPI
application and engines; only deterministic metadata, fixture admission, delay and
explicit fault setup are controlled. Successful research responses are not mocked.

Real admitted summaries/provenance bind dataset, fingerprint, market and source.
Invalid identity and incomplete economics return 422; malformed responses fail
closed. Research leaves operational strategy/authority unchanged. Unrelated Host,
Origin, localhost Origin ports and forwarding headers return 403 over actual HTTP.
Existing native boundary tests also exercise non-loopback peers. No frontend
financial calculation, fallback historical dataset or storage mutation was added.

## Historical storage configuration

| Case | Actual result |
| --- | --- |
| `HISTORICAL_REPLAY_ROOT` unset | Startup/health available; historical metadata returns **503** |
| Private root with no datasets | **200**, empty IDs/summaries; browser shows zero datasets and disabled submission |
| Private root with admitted fixtures | **200**, discoverable exact identity/provenance and valid PAPER results |
| Nonexistent directory | Startup available; storage read fails closed (**503**) |
| Symlink, unsafe permissions or inaccessible root | Read fails closed (**422/503**, existing contract), no private paths in response |
| Dataset removed after successful catalog | Catalog becomes empty, old replay request **422** |
| Wrong fingerprint / corrupt stored provenance | **422**, no prior catalog/result substituted |
| Restored valid operator-owned fixture | Catalog and manual replay recover |

Only test-owned temporary directories/files were provisioned. The browser cannot
create, download, upload, delete or repair an archive. Trusted absolute path,
no-symlink and owner-only requirements remain enforced; trusted ancestors remain
an operator provisioning responsibility.

## Redis configuration

| Mode | Actual process-level result |
| --- | --- |
| Disabled | Starts; health says `DISABLED`; actual historical and comparison requests succeed |
| Optional/unreachable, research coordination off | Starts; health says `DEGRADED`; local historical metadata and simulation remain available |
| Optional/unreachable, coordination on | Starts degraded; research metadata/simulation admission **503**, no unsafe fallback |
| Required/unreachable | Startup exits before service availability |
| Physical local Redis | **BLOCKED**: no `redis-server` executable and 127.0.0.1:6379 refused connection; no service installed |

Existing native fakeredis/Lua tests validate coordinated leases, cancellation,
heartbeat expiry, ownership, recovery and result/status identity. They do not count
as physical Redis integration. Existing Redis status/result mirrors are expiring
observations, not durable jobs or browser progress. Health reports last known
infrastructure observations and is not an authoritative per-job progress endpoint.

## Startup, shutdown, ownership and recovery

Production startup and graceful SIGTERM shutdown complete the existing lifespan.
This uvicorn version re-raises SIGTERM after cleanup: the new harness checks the
shutdown-complete marker plus the documented successful/signal exit codes.
Unsupported multi-worker configuration fails startup.

Actual Chromium cases open the browser before backend startup, stop/restart after
completed replay/comparison, kill the backend during admitted replay/comparison,
refresh during replay, unmount comparison during work, edit inputs while pending,
and reconnect. Old charts/receipts are hidden, late responses cannot restore old
evidence, and recovery requires an explicit new submission. Three synchronous
replay clicks admit one request. Existing tests confirm comparison duplicate guards.

The existing native worker tests hold execution inside real historical/scenario
engine frames: cancelling a waiter keeps the slot busy, shutdown closes admission
and waits for actual completion, and worker threads finish. These deterministic
native checks cover busy-worker shutdown; process death is not presented as
successful cancellation, durable recovery or automatic resubmission.

## UI status, diagnostics and workload

Idle has no submitted-result banner. Running means awaiting a validated response.
Complete follows existing response validation. Input/dataset/market/vault/segment/
session/connection changes retire affected evidence. Error has bounded guidance.
`role=status`, polite live announcements and named diagnostic alerts are exercised.

Browser tests use actual FastAPI **413** body-limit rejection, **422** incomplete
economics, **429** occupied worker, **503** unavailable storage, and **500** from a
labeled test-only engine exception caught by the production route. The injected
exception contains a private-looking path/token/traceback marker; none reaches the
UI. Native Node tests additionally exercise real HTTP responses through the actual
API client, including a deliberately truncated 200 stream and malformed 200 JSON.
Supplemental malformed-receipt and same-session connection-state probes are labeled;
they do not replace real request/restart cases.

Preflight uses an admitted **1,001-observation** fixture and ceilings **2, 128, 999,
1,000, 4,999, 5,000**, plus invalid 1/5,001. BTC/ETH/SOL, synthetic/user-asserted
recorded sources, baseline/modeled execution, unknown coverage, declared gaps,
multiple segments, independent scenario/historical frame edits and changed sources
are covered by native/browser cases. A 5,000 ceiling over 1,001 observations is not
promised as 5,000 viable frames. Observation counts imply neither fills nor profit;
gap counts imply no exact segment count. No benchmark time becomes an ETA.

Existing Replay frame/segment navigation, books, charts, PAPER metrics and modeled
baseline comparison work. Comparison retains CONTEXT_ONLY descriptive evidence,
blocks metrics/charts for INCOMPARABLE, displays unavailable metrics/traces without
imputation, reruns selected independent segments and captures validated Vault
accounting. No rankings, performance deltas or cross-gap returns are introduced.

## Responsive/accessibility and screenshots

Both workspaces were checked at **1920, 1440, 1024, 768 and 390 px**. No document
horizontal overflow; charts resize; native controls remain keyboard accessible;
long admitted identifiers and exact decimals fit/wrap. Scoped dark styling is
retained. Native role checks and browser keyboard navigation supplement visual
review; this is not a claim of a full assistive-technology audit.

The six actual Chromium captures below were visually inspected for readability,
clipping, overflow, source/status wording and charts after transitions. Component
captures hide fixed global chrome only; they do not alter research content.

- [Desktop historical preflight](acceptance/phase166c/historical-preflight-1440.png)
- [Desktop completed comparison](acceptance/phase166c/comparison-complete-1440.png)
- [390 px workload preview](acceptance/phase166c/mobile-preflight-390.png)
- [390 px diagnostic](acceptance/phase166c/research-diagnostic-390.png)
- [Large admitted workload warning](acceptance/phase166c/large-workload-warning.png)
- [Validated completed replay](acceptance/phase166c/research-complete.png)

## Final verification and reproduction

Activate a Python 3.12 environment with `pip install -e 'backend[test,redis]'` and
Playwright installed for acceptance. Use the repository's existing backend/frontend
startup commands from [the runbook](PHASE166C1_RELEASE_UX.md).

```bash
cd frontend
npm ci --cache ../work/npm-cache
npm run typecheck
npm run build
npm test
cd ../backend
python -m pytest tests -q -rs
python -m pytest tests/test_phase166c2_local_integration.py -q -rs
cd ..
python frontend/tests/browser-phase165c2.py --phase166c \
  --python "$(command -v python)" --chromium /usr/bin/chromium \
  --output work/browser166c
```

Ports 5173/8000 must be free for Chromium. Its existing fixture server is loopback
only; run the production application separately for ordinary use. Keep generated
logs/JSON in `work/`; retain only the six representative PNGs in acceptance docs.

| Final check | Actual result |
| --- | --- |
| `npm ci`, native TypeScript | **PASS**, unchanged lockfile; 27 packages |
| Production build | **PASS**, 2.63 s; existing bundle notices/warning retained |
| Frontend full suite | **713 passed, 0 failed/skipped**, 15.050 s |
| Backend full suite | **2,499 passed, 0 failed, 1 optional ML skip**, 161.83 s |
| Focused replay/comparison/performance/worker/Redis/provenance/Vault suite | **477 passed**, 81.57 s |
| New production-uvicorn HTTP/configuration cases | **9 passed**, 11.63 s |
| Chromium `--phase166c` | **19 workflow groups passed**, 60.398 s; zero page errors/unexpected console/network failures |
| Workload label/value text contrast | Minimum **8.51:1** |

The compact [validation summary](acceptance/phase166c/validation-results.json)
records independent gates and implementation SHA `e2931e6d494ebea665cfa874f6dcccb333d49c79`.

## Defects, limitations and disposition

Confirmed fixes: stale Historical Replay financial displays after backend/session
change; missed same-process disconnect retirement; pending requests falling back
to idle after invalidation; pending labels asserting worker activity; interrupted
response bodies misclassified as size failures; missing-backend HTTP 500 guidance; Comparison Studio controls missing their reused
desktop flex-container styling.
No backend lifecycle or financial-contract defect required production changes.

Harness corrections were retained transparently: workspace dependency caches,
uvicorn SIGTERM semantics, reading only needed Chromium response bodies, handling
an empty interrupted-response body in the test observer, and allowing the expected
413 console entry. During development the new real-stream test failed with
`size` instead of `connection` before the API-client fix. No assertions or existing
tests were disabled.

Local gate disposition is recorded independently in the compact summary. Physical
Redis remains BLOCKED. macOS, real authenticated exchange history/licensing,
venue-calibrated fills, TESTNET/live trading and public multi-user deployment are
NOT RUN or separate external gates. Browser cancellation cannot establish that an
admitted job stopped. Phase 16.6D may build on the accepted local research behavior;
these external gates and manual review remain open. Merge is manual.

## Independent acceptance gates

| Gate | Disposition |
| --- | --- |
| native typescript | **PASS** |
| frontend production build | **PASS** |
| frontend test suite | **PASS** |
| backend test suite | **PASS** |
| real fastapi integration | **PASS** |
| historical vault configured unconfigured | **PASS** |
| redis disabled optional unavailable | **PASS** |
| redis required unavailable fail closed | **PASS** |
| startup shutdown lifecycle | **PASS** |
| shared worker status messaging | **PASS** |
| error diagnostic accuracy | **PASS** |
| large dataset preflight | **PASS** |
| stale evidence retirement | **PASS** |
| historical replay studio | **PASS** |
| comparison studio | **PASS** |
| chromium browser workflows | **PASS** |
| responsive accessibility review | **PASS** |
| real screenshot evidence | **PASS** |
| compact markdown acceptance report | **PASS** |
| physical redis integration | **BLOCKED** |
| genuine exchange source authentication | **NOT RUN** |
| live trading authorization | **NOT RUN** |
| macos acceptance | **NOT RUN** |

**Final disposition: local PAPER integration/UX acceptance PASS.** Physical Redis is independently BLOCKED and external gates are NOT RUN. Ready for a Phase 16.6D local research handoff after manual review; no automatic merge or trading authorization.
