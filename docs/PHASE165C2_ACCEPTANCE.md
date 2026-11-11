# Phase 16.5C.2 — Scenario/Historical Comparison Integration & UI Hardening

## Revision and scope

- Base: `756954ad6efbc9e8ad5ee75a18ce80f619a3c1af` (`main`, merged PR #65).
- PR #65 merge was verified through local Git ancestry and GitHub metadata. PR #64 is also in that ancestry.
- Final implementation/evidence commit: `453ef8b6fd10fe097bb2300ff1b5190a7b817e5c`. This report is a subsequent documentation commit so the implementation identifier is exact and non-self-referential.
- Branch: `phase16/16-5c2-comparison-integration`.
- Validation: November 11, 2026. Local Linux, Python 3.12.14, Node 24.19.0, Chromium 151.0.7922.173, actual React/Vite and loopback FastAPI.
- All browser evidence is generated. BTC fixtures intentionally carry user-asserted recorded-native labels to exercise that contract; ETH/SOL fixtures carry synthetic labels. No genuine exchange recording, independently verified license or real execution acceptance is claimed.

## Acceptance gates

| Gate | Status | Actual evidence |
| --- | --- | --- |
| Latest base / predecessor | PASS | Exact base and merged #65 verified |
| Initial focused backend baseline | PASS | 114 passed |
| Initial C.1 frontend compilation | FAIL, corrected | TS1005 at `scenarioReplayComparison.ts:86`; typecheck/build/tests could not compile |
| C.1 frontend after syntax correction, before integration | PASS | Typecheck/build and 693 tests |
| Bounded comparison HTTP integration | PASS | 34 new native integration cases; actual browser POST workflow |
| Requested final focused backend command | PASS | 148 passed |
| Focused regression plus importer/storage boundary | PASS | 282 passed |
| Entire backend suite | FAIL — same three base documentation defects | 2,395 passed, 3 failed, 1 optional skip; exact base was 2,361 passed, same 3 failed, 1 skip |
| Frontend install/typecheck/build | PASS | `npm ci`, `npm run typecheck`, `npm run build` |
| Frontend tests | PASS | 698 passed, 0 failed |
| Actual Chromium integration | PASS | 15 grouped workflows; nine real screenshots; no page errors/unexpected console errors |
| Responsive checks | PASS | 1920, 1440, 1024, 768 and 390px; no document overflow |
| Worker concurrency / cancellation | PASS | HTTP 429, responsive health, capacity retained after cancellation/unmount |
| Operational authority / accounting / storage / signer isolation | PASS | Seeded native before/after comparisons, kill enabled/disabled, baseline/modeled runs, Phase 15 subscriptions; browser authority snapshots |
| Source authentication / licensing / live exchange history | NOT RUN | No suitable authentic recording supplied; these claims remain explicitly unverified |
| Automatic merge/deployment | NOT RUN | Draft PR only; no automatic merge |

Machine-readable summaries: [validation-results.json](acceptance/phase165c2/validation-results.json) and [browser-results.json](acceptance/phase165c2/browser-results.json).

## Native baseline and defects corrected

The initial shell had no pytest. Dependencies were installed into `backend/.venv` using the repository extras. The first npm install could not write its default home cache; `npm ci --cache ../work/npm-cache` succeeded without changing package versions or the lockfile.

Before implementation, the requested backend focused command passed 114 cases. The original C.1 TypeScript had an extra closing parenthesis in time coverage validation. Once that syntax defect was corrected, typecheck, build and all 693 existing frontend tests passed.

Actual native/Chromium integration then exposed compatibility defects that a manually pasted receipt could hide:

- Backend Decimal output includes canonical exponent strings such as `0E+5`. Display validation now accepts bounded canonical backend notation and reuses text-only exact Decimal expansion; the original wire value remains available to keyboard/screen-reader inspection. Lowercase noncanonical exponent fixtures, floats, non-finite values, wrong units and forged authority remain rejected.
- Whole-second and fractional-second timestamps cannot be compared as ordinary strings. The existing microsecond-aware `receiptTime` helper is reused, including ETH's distinct sub-millisecond receipts.
- Research Vault request serialization initially made default accounting fields look like explicit forbidden overrides. The request serializer preserves the actual supplied simulation controls when a proposal owns accounting; repeated service and response validation succeeds without weakening that ownership rule.
- Catalog/provenance reads could compete for the single worker when changing workspaces. Provenance reads wait for catalog completion. Both existing replay and comparison metadata queries retry only busy errors, at most three retries, 500ms apart. Computational POSTs are never retried automatically.
- An initial API import of storage exceptions violated the existing historical filesystem boundary test. Storage error translation now lives inside `research_replay/transport.py` and exposes a public path-free contract error; the unchanged boundary test passes.

No tests were disabled, changed to artificial expected failures or weakened to accommodate the integration.

## Backend architecture and transport

The only new route is:

```text
POST /api/v1/research-comparison/scenario-historical
```

The thin router captures detached operational strategy/agent/risk inputs and resolves the existing research market profile. Browser inputs cannot replace those domains or supply serialized financial results, account state or signer configuration. It invokes only the existing lifespan-owned executor's new allowlisted `compare_scenario_historical` operation.

Within that one job, `SimulationService` calls the existing validated historical replay service, executes the scenario with `include_comparison_provenance=True`, and passes the resulting `CapturedScenarioResult` plus `HistoricalReplayResult` into the existing `compare_quantitative_paper`. That function revalidates source receipts, captures a `ComparisonFoundation` and emits the unchanged verified `phase165b-v1` receipt. No second engine, calculator, scheduler, background executor, database, persistent result session or new cache was added.

The native worker's existing shield and completion callback retain admission until computation actually completes. The same operation automatically uses the existing optional Redis coordinator when configured. It never calls `execute()` recursively. Historical segments remain separate fresh engine states, including modeled execution's existing baseline sensitivity runs.

### Limits

| Item | Bound |
| --- | --- |
| Request body, including chunked bodies | Existing 65,536 bytes before parsing |
| Scenario frames | Strict integer 2–5,000, within simulation `max_frames` |
| Historical frames | Existing strict integer 2–5,000; evidence exceeding selection limits is rejected |
| Markets | BTC, ETH, SOL |
| Segment index / count | 0–31 / at most 32 |
| Original trace points transported | 0–250 per side; normal UI requests 120 |
| Replay issues transported | First 100, with omitted count; rejection issues also capped at 100 |
| Declared gaps | Existing maximum 1,024 |
| Successful JSON response | 1,000,000 bytes, checked inside the admitted worker |
| Browser response reader | 1,000,000 bytes before JSON parsing, including chunked bodies |

The server-generated `phase165c2-v1` envelope contains the captured request/fingerprint, unchanged quantitative receipt, all bounded nonfinancial segment identities/reset reasons/receipt windows, selection policy, original dataset provenance/gaps, issue omissions and capped original trace projections. It never contains `simulation_result_json`, baseline archives, full historical replay objects or retained L2 observations.

Only one segment's quantitative receipt is returned. Selecting another segment uses documented `RERUN_SELECTED_SEGMENT`: rerun the bounded validated request and return that segment's independently verified receipt. This avoids transporting every archive or introducing persistent sessions. A new run may capture changed operational configuration; the returned captured request/configuration makes that visible.

### Identity and classification

The existing A/B validation remains authoritative for strategy, agents, risk, accounting/capital, execution, engine version and market profile; same-job scenario provenance and result/capture identity; original historical dataset, selected engine dataset/run/result archive and replay result fingerprints; and retained receipt coverage, gaps and resets.

The original dataset fingerprint intentionally differs from the engine's segment dataset fingerprint. Native tests assert that distinction. Selected trace projections bind both run/dataset/result-archive identity and original sequence/timestamp evidence.

`CONTEXT_ONLY` shows independently reported backend metrics. Matching configuration does not establish a controlled economic/statistical experiment or causal PnL explanation. `INCOMPARABLE` returns no paired financial rows, risk counts or trace points. `ALIGNED` stays unavailable. Direct metric deltas, cross-segment aggregation, verified matched economic evidence and strategy ranking remain false. No combined historical return, stitched equity or superiority claim was introduced.

### HTTP/security behavior

- 200: bounded validated server receipt and selected evidence.
- 422: malformed/coercible controls, forged financial input fields, unsupported market/profile, changed dataset fingerprint, incomplete economics, corrupt stored dataset, unavailable segment, tampered source/result identity or response budget violation.
- 429: existing authoritative shared research worker busy.
- 503: unconfigured/unsafe/inaccessible comparison storage or unavailable admission.
- 500: sanitized internal failure without private paths, signing material, stack traces or provider payloads.
- 413: existing pre-parsing oversized body protection.

Existing loopback peer, Host, Origin, CORS/request-size and no-store controls remain in force. Other historical routes preserve their previous error-status behavior. The route has no order placement, strategy start, kill reset, operational risk/configuration update, ledger mutation, reservation, signing or live subscription authority.

## React integration and lifecycle

The existing C.1 workspace, metric groups, explainability and chart components are enhanced. Existing market selector, dataset summaries/selector, provenance, replay assumptions, React Query, validated Research Vault store and Lightweight Charts remain their owners. There is no second importer or duplicate historical replay form.

Users select scenario, research market, scenario frames, admitted dataset, bounded replay policy/precision and baseline/modeled execution. An existing Vault-validated proposal may supply accounting independently to both paths. Captured request metadata accompanies the result. The developer JSON inspector remains optional, local and explicitly unauthenticated.

A synchronous busy ref prevents repeated admission from one mounted workspace. An epoch, captured input identity and backend process/session/connection identity guard completions and retained results. Changing controls permanently retires the prior result, including changing a value back. Switching datasets/markets during a pending request cannot relabel its eventual receipt. Unmount aborts the HTTP waiter and discards its response; it does not claim that the backend stopped. A remount starts without a result. Backend restart retires prior displays and revalidates catalog/provenance against the retained dataset fingerprint.

Metrics retain exact backend Decimal strings, missing values as unavailable and actual zero fill counts as zero. Formatting is text-only. Full original strings have focusable accessible labels/tooltips. Independent headers, unit/source labels, compact mobile tables and wrapped fingerprint/configuration disclosures support small screens. No financial differences are calculated in React, and inventory exposure is never substituted for capital utilization.

## Trace and provenance evidence

The bounded envelope projects original scenario and selected archive points only after backend receipt validation. It preserves sequence, engine timestamp, equity, PnL, inventory, drawdown, state evidence and original selected historical receipt/source timestamps with assertion flags. No raw source payload is returned. Missing/unrequested/blocked/limited traces have explicit omission reasons and omitted-frame counts.

The plots reuse `SimulationTrace`/`HistoryChart` with memoized trace-frame projection. They have independent frame axes and starting capital, with original timestamps available in inspection. Scenario timestamps are generated. Historical evaluation times follow receipt clocks; context/source labels are not promoted to exchange authentication. Only a selected independent segment is rendered; there is no concatenation across gaps, synchronized timeline, invented path from aggregate totals or imputed price continuity. Prefix truncation of retained original points is explicitly reported.

## Native and browser evidence

Commands actually executed:

```bash
cd backend
python -m pytest tests/test_phase165c2_integration.py \
  tests/test_phase165b_quantitative.py tests/test_phase165a2_integration.py \
  tests/test_phase165a1_contracts.py tests/test_phase1641_acceptance.py -q
# 148 passed
python -m pytest tests/test_phase165c2_integration.py \
  tests/test_phase165b_quantitative.py tests/test_phase165a2_integration.py \
  tests/test_phase165a1_contracts.py tests/test_phase1641_acceptance.py \
  tests/test_phase161b_importers.py -q
# 282 passed
python -m pytest tests -q -rs
# 2,395 passed / 3 reproduced base failures / 1 optional skip

cd ../frontend
npm ci --cache ../work/npm-cache
npm run typecheck
npm run build
npm test
# 698 passed

cd ..
backend/.venv/bin/python frontend/tests/browser-phase165c2.py
# PASS: 15 grouped actual-local workflows
```

The 34 new integration tests cover BTC/ETH/SOL baseline/modeled HTTP receipts, exact zero and unavailable values, gaps/observer generations and selected segments, market blocking, forged inputs, configuration bounds, changed source fingerprints, missing economics, request/response budgets, corrupt/unsafe storage, explicit trace omissions, seeded capital/order/ledger/signer isolation with kill on/off, concurrent admission/cancellation, sanitized failures, tampered scenario/replay receipts and active Phase 15 subscription preservation. The reused A/B focused tests cover individual strategy/agent/risk/capital/execution differences and deeper provenance substitution cases.

Chromium uses the existing Phase 16.4.1 fixture backend, actual importer/storage, FastAPI routes and PAPER engines. The primary workflow never mocks comparison responses. One separate explicitly labeled malformed-response fault probe checks fail-closed UI behavior. Real missing-economics 422, occupied-worker 429 and disabled-storage 503 cases use the backend. The script records all mutating request paths, before/after operational authority, browser errors, viewports and screenshots. Expected fault status/network console messages are retained and separately distinguished from unexpected errors.

Screenshots:

- [BTC context and original traces](acceptance/phase165c2/btc-context-and-traces-1440.png)
- [1920px](acceptance/phase165c2/comparison-1920.png), [1440px](acceptance/phase165c2/comparison-1440.png), [1024px](acceptance/phase165c2/comparison-1024.png), [768px](acceptance/phase165c2/comparison-768.png), [390px](acceptance/phase165c2/comparison-390.png)
- [Independent segment 2 after a declared gap](acceptance/phase165c2/independent-gap-segment-2.png)
- [Market mismatch blocks financial evidence](acceptance/phase165c2/market-incomparable.png)
- [Vault proposal and exact long Decimal at 390px](acceptance/phase165c2/vault-exact-decimal-390.png)

The browser also runs the existing Historical Replay Studio, scenario simulation, bounded optimizer and Vault validation/selection workflow. Keyboard form traversal, native disclosures, focusable exact values, hash wrapping, chart resizing and document width pass. Chromium reported zero page exceptions and zero unexpected console errors.

## Remaining failures, limitations and Phase 16.5D readiness

The exact untouched base was checked out separately and its complete suite executed before identifying these as pre-existing:

- `tests/test_phase10_static.py::test_no_github_actions_or_forbidden_oracle_added`
- `tests/test_phase8_static.py::test_repository_contains_no_forbidden_oracle_provider_token`
- `tests/test_phase9_static.py::test_phase9_does_not_create_github_actions_or_forbidden_oracle`

All three report the existing Phase 15.5B acceptance document. See the recorded [base](acceptance/phase165c2/baseline-full-backend.txt) and [final](acceptance/phase165c2/final-full-backend.txt) summaries. The optional ML test is skipped because its optional dependency is not installed. No additional native failures remain. The full suite is **not green**. Summary files intentionally record failing test names/counts without copying unrelated offending documentation content into new scanned evidence files; original complete logs remain in `work/`.

Vite reports existing module-directive/chunk-size warnings; builds succeed. Pytest reports the installed framework's TestClient deprecation warning. No frontend dependency or lockfile change was needed.

There is no authentic historical recording, source licensing attestation, matched economic/time experiment, calibrated fill claim, macOS acceptance or live-trading certification here. Browser structural validation relies on the backend's source receipt checks and does not independently authenticate hashes. Segment selection reruns bounded work and may be expensive near frame limits. Metadata can remain busy after bounded retries; explicit catalog retry is available.

The local C.2 integration, isolation, native focused and browser gates pass and are ready for Phase 16.5D review. Repository-wide green status remains blocked by the reproduced documentation defects, and future matched-data/source-authentication work remains unverified. Keep the PR draft for review; do not merge automatically.
