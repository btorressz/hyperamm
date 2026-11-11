# Phase 16.5D — Final Acceptance, Security Hardening & Regression

**PHASE 16.5 LOCAL RESEARCH ACCEPTANCE: PASS**

This disposition covers bounded deterministic local PAPER research. It grants no live-trading, signing, source-authentication, licensing or production authority. Phase 16.6 can proceed with the external gates below remaining explicit.

## Revisions and environment

- Starting latest `main`: `ff71a8610dbbd2850f830f8595160ef74203d7d0` (merged PR #66).
- Core implementation: `26d6b6d7338731c98f9d7c95665cb23423211b81`.
- Final browser capture implementation: `975fa3a280a5667808d5b231db128e9510dc1eaa`.
- Performance harness / current-status documentation: `1f4adcfbaa083c1a6c1d0bd23402739d88efd97c`.
- Final implementation and browser network recording: `07c131615c55fbd28a2f5f19cbd7a9f52367dba2`.
- Evidence commit: `7bbe65730d725e9eb31ea35de0b7529760a2b388`. This report is a subsequent documentation commit, avoiding a self-referential evidence SHA.
- Branch: `phase16/16-5d-final-acceptance`. Draft PR only; no automatic merge.
- Executed November 11, 2026, Pacific time, in managed Linux x86-64: Python 3.12.14, Node 24.19.0, npm 11.9.0, Chromium 151.0.7922.173. Three visible logical CPUs, cgroup quota of two CPU cores, 8 GiB memory limit. See [environment](acceptance/phase165d/environment.json) and [installed Python packages](acceptance/phase165d/python-packages.log).

GitHub metadata and Git ancestry independently confirm PRs #62, #63, #64, #65 and #66 are merged. Exact merge identities are in [merged-prs.json](acceptance/phase165d/merged-prs.json). Merge status was treated as a prerequisite, not acceptance evidence.

## Gate disposition

| Gate | Status | Executed evidence |
| --- | --- | --- |
| Comparison contracts | PASS | A.1/A.2/B/C.2 focused native tests and independent serialized receipt probes |
| Same-job scenario configuration capture | PASS | Capture/result substitution, stale configuration, detached admission, canonical JSON and effective-accounting assertions |
| Historical replay provenance | PASS | Secure importer/vault reads, source versus engine-segment identities, archive and replay receipt validation |
| Quantitative metrics / accounting integrity | PASS | All 23 registry metrics compared to native owners; exact Decimal tests; missing Vault projection; modeled partial fills |
| Comparability restrictions | PASS | CONTEXT_ONLY descriptive values; INCOMPARABLE blocks rows/traces; ALIGNED and all unsupported authority/delta/ranking flags rejected |
| HTTP boundary security | PASS | Real 200/413/422/429/503/500; pre-parse chunk/body bounds, Host/Origin, storage corruption, actual serialized byte budget and no-store |
| Single-worker concurrency | PASS | Computational/metadata contenders, synchronous duplicate clicks and shared Redis admission fixture |
| Cancellation / shutdown | PASS | Cancelled waiters retain native ownership; failed detached work and shutdown finish before release |
| Operational strategy / risk isolation | PASS | Seeded orders/fills/ledger/reservations, kill enabled/disabled, signer references and selected market unchanged; independent Phase 15 consumers preserved |
| Dataset / segment isolation | PASS | Original source files unchanged; independently reset capital/inventory/orders/risk/accounting; selected segment reruns |
| Frontend TypeScript / production build / tests | PASS | Typecheck/build; 699 tests, zero failures |
| End-to-end Chromium | PASS | 21 workflow groups, zero page exceptions / unexpected console errors |
| Responsive UI | PASS | 1920, 1440, 1024, 768, 390px; automatic overflow/chart checks and actual screenshot inspection |
| Full backend regression | PASS | 2,469 passed, zero failed, one optional ML skip |
| Bounded performance / maximum gaps | PASS | Actually executed 1,000 / 4,999 historical frames, 5,000 scenario frames, 32 segments, 1,001 issues, 1,024 gaps, 250 retained points and partial-fill work |
| Genuine exchange source authenticity | BLOCKED | No independently authenticated historical recording supplied; all acceptance datasets are generated |
| Historical source licensing | BLOCKED | No independent rights evidence supplied; permitted-use labels remain assertions |
| macOS / native external acceptance | BLOCKED | Linux executor only; no independent macOS or permitted external delivery evidence |
| Actual external Redis server | NOT RUN | Existing fakeredis/Lua fixture exercised real coordination code; no external-server deployment claim |
| Live trading / signing / automatic merge | NOT RUN | Outside this local research acceptance and not performed |

## Untouched baseline and historical static failures

All application files were unchanged while the initial requested native/frontend commands ran. The starting focused backend result was **148 passed**. The complete starting backend was **2,395 passed, 3 failed, 1 skipped**. Frontend typecheck/build and **698 tests** passed. The unchanged Chromium script passed its **15 workflow groups**.

The three reproduced failures were:

- `tests/test_phase10_static.py::test_no_github_actions_or_forbidden_oracle_added`
- `tests/test_phase8_static.py::test_repository_contains_no_forbidden_oracle_provider_token`
- `tests/test_phase9_static.py::test_phase9_does_not_create_github_actions_or_forbidden_oracle`

All three reported the excluded-scope sentence in `docs/PHASE155B_ACCEPTANCE.md:195`. That sentence named a prohibited provider while stating that no such provider had been added. Review found a documentation-only match, not an implementation/provider integration. The smallest correction replaces that name with **“additional oracle providers”**. The exclusion remains explicit and is broader than the former proper name. Historical counts, limitations and claims in that document are otherwise unchanged; the untouched text remains available in the starting Git revision.

None of the three security tests changed. No test was disabled, marked expected-failure, bypassed or weakened. The three checks now pass, and the complete prescribed backend suite is genuinely green with the optional skip disclosed. Raw initial command output is preserved as [baseline-full.log](acceptance/phase165d/baseline-full.log); historical failing output remains historical, not a claim of current failure or success.

## Independent architecture and identity review

The review covered `research_replay/{comparison,quantitative,transport,contracts,runner,adapter,provenance,storage}.py`, the comparison/historical/simulation routers, simulation service/executor/engine/models/market profiles, and `main.py`. Frontend review covered `Simulation.tsx`, the comparison and replay subtrees, `HistoryChart`, `SimulationTrace`, API client, comparison types/validators, replay evidence and scoped CSS. Existing tests and A.1/A.2/B/C.1/C.2/16.4.1 acceptance evidence were read alongside the implementation. Prior C.2 390px and 1440px screenshots were opened independently before reviewing the new captures.

The authoritative flow remains:

1. Strict local HTTP request selects a scenario and an admitted historical ID/fingerprint, never a client financial result or signer/risk/account override.
2. The router captures detached operational strategy/agent/risk inputs and resolves the existing research market profile.
3. One existing `SimulationExecutor` job runs validated replay, the same-job captured scenario, and the pure quantitative projection sequentially. Modeled replay's existing baseline sensitivity also remains sequential.
4. Scenario service freezes the effective configuration, including accounting's starting-capital override and optional Vault proposal, reconstructs engine inputs from that validated capture, and binds the actual result.
5. Replay reads canonical owner-only stored evidence, adapts receipt batches, and runs independent engine state per segment. Archives bind the actual dataset/run/result metrics and retained frame sequences/timestamps.
6. Foundation reconstruction validates source/configuration identities; quantitative projection copies existing metrics/Vault fields. Transport selects one segment and bounds original traces/issues/gaps.
7. React validates display structure against the captured request, retires stale evidence and renders independent source values and frame axes.

Original historical source dataset fingerprints remain intentionally distinct from the engine's segment dataset fingerprint. The scenario dataset/result/run/capture, strategy, agent, risk, accounting/capital, execution, profile, replay result and selected archived result identities remain separately bound. Canonical reconstruction uses validated models rather than accepting arbitrary browser hash strings. Original receipt/source timestamps and sequences remain inspectable; receipt clocks do not become exchange event time or synchronize the two financial paths.

Existing and new adversarial cases reject substituted scenario results, another dataset/replay segment, modified captured accounting/execution, stale capture, forged receipts/run/archive IDs, incompatible markets and changed engine identities. An independently captured different engine is explicitly INCOMPARABLE. These checks establish consistency with retained original evidence **within the local owner trust boundary**. Content hashes and service receipts are not signatures, independent engine attestations or source authentication; a malicious owner capable of replacing data and all hashes remains outside that boundary. The local developer receipt inspector continues to label its input unauthenticated.

## Confirmed defects and focused fixes

| Finding / root cause | Correction / files |
| --- | --- |
| Simulation/accounting Decimal configuration accepted binary floats and extreme exponents. A tiny request could expand greatly in canonical fingerprinting. | Shared exact finite financial validation in `backend/app/accounting/config.py`, reused by `backend/app/simulation/config.py`. Inputs preserve exact Decimal spelling, bound text/exponents/magnitude, and reject before worker admission. This also protects the existing opt-in provenance scenario route. No normalization of valid financial outputs was added. |
| Quantitative frame-count rows plus risk counts could be rehashed consistently while disagreeing with their bound foundation side. Metric Decimal text/exponents were not bounded before hashing. | `backend/app/research_replay/quantitative.py` checks side frame identity and bounded exact wire values; all registry units/sources and unavailable semantics remain enforced. |
| Selected transport segment coverage and original receipt clocks were insufficiently cross-checked. Browser source-time validation accepted arbitrary short strings. | `backend/app/research_replay/transport.py` and `frontend/src/utils/scenarioReplayComparison.ts` bind frame/window/source identities and require valid original receipt clocks; generated scenario traces cannot acquire historical source timestamps. |
| A transient connection change could hide a completed response and then revive it when the same process/session key returned. | Permanent epoch retirement on input/session transitions in `frontend/src/components/scenario-replay-comparison/ScenarioReplayComparisonWorkspace.tsx`; actual same-session browser probe prevents resurrection. |
| A partial/immediate PAPER fill during reconciliation retired inventory/accounting authority before another submission. Correct safety checks aborted the entire research job. | `backend/app/simulation/engine.py` explicitly defers remaining quotes after a new fill; `backend/app/execution/order_manager.py` honors conservative `False` authority without submitting, and reports only completed action prefixes (including a completed replacement cancellation). Fresh authorization occurs on the next existing frame. Other authority exceptions still propagate. Previously valid checked-in fixtures remain unchanged; previously aborting paths now complete safely. |
| Historical excluded-scope wording triggered meaningful repository provider restrictions. | One factual wording substitution in `docs/PHASE155B_ACCEPTANCE.md`; unchanged static checks and historical test evidence. |

New native tests are in `backend/tests/test_phase165d_acceptance.py` (**71 cases**). Controlled dataset generation and standalone measurements are in `backend/tests/phase165d_fixtures.py` and `phase165d_performance.py`. The existing `frontend/tests/browser-phase165c2.py` adds optional D-phase workflows and component captures; its existing fixture backend admits the large synthetic dataset only under the explicit test environment flag. `frontend/tests/phase165c2-comparison.test.cjs` adds malformed clock/segment probes. README, Summary, CODEBASE and CHANGELOG correct materially stale current-status statements; historical dated reports remain intact. All other new files are the acceptance report and evidence directory.

No additional engine, endpoint, worker, queue, database, dependency manifest, provider, strategy, signer, trading authority or deployment infrastructure was introduced. No GitHub Actions or container infrastructure was added.

## Numerical, accounting and comparability evidence

All **23** displayed metric rows are copied from their documented `SimulationMetrics` or PAPER Vault owner, with units/origins validated. Existing native B tests compare every row to actual scenario and selected archived replay results across BTC/ETH/SOL. The independent [numerical probe](acceptance/phase165d/numerical_probe.py) checks retained native archives and all five missing-Vault observations; [results](acceptance/phase165d/numerical-probes.json) confirm absent values remain unavailable.

New exact-wire cases cover zero, signed zero, `0E+5`, tiny positive/negative `1E-60` values, signed PnL-like amounts and long fractional strings. Boundary cases reject floats/booleans, non-finite values and exponent expansion bombs. Count rows remain nonnegative integers. Browser tests preserve canonical uppercase exponent output, exact stored strings and focusable accessible labels; display shortening never changes underlying values. Inventory utilization and Vault capital utilization retain different metric names/owners. Unexpected units/origins and inconsistent null/availability values fail closed.

Segments independently start fresh capital, positions, orders, risk, accounting and execution state. Existing replay reset tests and new 32-segment/selection runs execute this policy. No combined historical session return, concatenated equity path or pooled capital result is generated.

CONTEXT_ONLY remains descriptive. INCOMPARABLE blocks paired rows and traces, while allowing provenance. ALIGNED remains rejected. `direct_metric_deltas_allowed`, `cross_segment_aggregation_allowed`, `matched_market_evidence_verified`, quantitative differences and strategy-ranking flags remain false. No statistical significance, profitability improvement or exchange authenticity claim is inferred from matching settings.

## HTTP, worker and operational isolation evidence

The existing endpoint retains the 65,536-byte write body cap before parsing, 1,000,000-byte serialized response budget, 5,000-frame request controls, 32 independent segments, 250 transported points per side, 100 exposed issues with omission counts and 1,024 declared gaps. Tests execute Content-Length and chunked overflow, malformed/deep JSON, strict fields, profile/input validation, corrupt/unsafe storage and invalid segment selection. The exact response-byte test accepts the actual HTTP byte length and rejects a budget one byte smaller; this verifies serialized output rather than an internal size estimate. Errors retain no-store and path-free public messages. Host/Origin checks run before oversized body parsing.

Native and Chromium requests execute real 200, 413, 422, 429, 503 and sanitized 500 behavior. The endpoint never receives raw financial archives or signer/account overrides. Private vault permissions/integrity remain owned by existing importer/storage code.

Native stress uses 20 simultaneous metadata/computational contenders, cancellation, controlled delayed futures, worker failure and shutdown. Cancelled HTTP waiters do not cancel the thread or free its capacity. Shutdown waits for actual completion. The combined comparison also runs through the existing Redis coordinator/fakeredis Lua fixture: cancellation preserves native ownership, busy admission fails, and the completed mirrored result validates against its original receipt. This is a local Redis protocol fixture, not a real Redis service deployment test.

Operational before/after tests seed actual PAPER fills/orders, running strategy state and capital reservations, with kill both enabled and disabled. Existing C.2 cases cover baseline/modeled assumptions and signer references; new cases also cover invalid evidence, worker busy, cancellation and multiple segments. Strategy, selected operational market, risk/kill, ledger/reservations/account configuration, TESTNET signer references and admitted source bytes remain unchanged. Existing Phase 15 fixture subscriptions/consumers remain on the same connection/generation and continue receiving observations. Browser authority snapshots also remain unchanged around comparison work. Explicit fixture setup of research risk assumptions is separate from the product route and does not authorize a browser risk override.

## Measured bounded performance

See [performance-results.json](acceptance/phase165d/performance-results.json) for individual runs, serialization time, actual response bytes, retained points, issue omissions, worker release and unchanged source-file assertions. Results are measured observations, not an invented SLA. Process RSS is Linux's cumulative process high-water mark, not a per-job isolated allocation; the high-gap probe runs in a separate process. Browser samples are observations in a shared managed executor, not an exclusive hardware benchmark.

| Historical / scenario frames | Segments / gaps | Worker seconds | Serialize ms | Response bytes | Process peak RSS MiB |
| --- | --- | --- | --- | --- | --- |
| 1000 / 1001 | 1 / 0 | 11.151 | 3.344 | 405,414 | 130.6 |
| 4999 / 5000 | 1 / 0 | 59.455 | 2.529 | 406,191 | 288.7 |
| 64 / 65 | 32 / 31 | 0.542 | 0.744 | 91,002 | 288.7 |
| 4 / 5 | 1 / 0 | 0.251 | 0.503 | 53,299 | 288.7 |
| 128 / 129 | 1 / 0 | 4.217 | 0.939 | 227,095 | 288.7 |
| 64 / 65 | 32 / 1024 | 0.791 | 1.692 | 222,080 | 95.1 |

The 5,000-observation vault cap makes **4,999 viable historical frames** the reachable maximum: a book/context pair is required before the first frame, after which individual component receipts may each produce another valid frame. The near-limit run also executes **5,000 scenario frames**. This distinction avoids claiming an unattainable 5,000-frame historical fixture. Both sides transport at most 250 retained original points.

Repeated segment selections 0 → 31 → 0 rerun the bounded work and reproduce the original receipt when returning to segment 0. No cache/session or second worker was introduced. The modeled case executes partial-fill assumptions and actual nonzero hypothetical fills; missing fills are never invented. A 1,001-issue fixture exposes 100 issues and reports 901 omitted; 1,024 separate declared gaps preserve 32 independent segments.

The final actual 1,000-frame browser request completed and rendered **120 retained historical points**, explicitly reporting **880 omitted**. Its recorded measurement was **12.319989 s**, **209,326 bytes**, about **32.3 MiB** sampled JS heap, and a maximum animation-frame interval of **87.9 ms** across 30 samples. The report's `chart_count` is **84 canvas elements**, not 84 distinct financial charts. These observations disclose occasional rendering delay; no responsiveness threshold or full-memory-profile claim is invented.

## Native/frontend/browser results and reproducible commands

| Check | Untouched baseline | Final |
| --- | --- | --- |
| Requested Phase 16.5 focused backend | 148 passed | 148 passed |
| New D hardening suite | Not present | 71 passed |
| Full backend | 2,395 passed, 3 failed, 1 optional skip | **2,469 passed, 0 failed, 1 optional skip** |
| Frontend tests | 698 passed | 699 passed |
| Frontend typecheck / production build | PASS | PASS |
| Existing Chromium workflow groups | 15 passed | All retained; **21 total** with D probes |

The complete suite covers the earlier scenario/optimizer/Vault, multi-market research, Phase 15 observer lifecycle, historical import/replay/execution/Studio and A/B/C integration. Stored checked-in replay fixtures and default successful research semantics remain backward compatible. Exact command outputs are preserved in `docs/acceptance/phase165d/`.

```bash
cd backend
.venv/bin/python -m pytest tests -q -rs
.venv/bin/python -m pytest tests/test_phase165c2_integration.py \
  tests/test_phase165b_quantitative.py tests/test_phase165a2_integration.py \
  tests/test_phase165a1_contracts.py tests/test_phase1641_acceptance.py -q
.venv/bin/python -m pytest tests/test_phase165d_acceptance.py -q

cd ../frontend
npm ci --cache /workspace/work/npm-cache
npm run typecheck
npm run build
npm test

cd ..
backend/.venv/bin/python frontend/tests/browser-phase165c2.py \
  --phase165d --output docs/acceptance/phase165d
PYTHONPATH=backend:backend/tests backend/.venv/bin/python \
  backend/tests/phase165d_performance.py --output work/performance-results.json
PYTHONPATH=backend backend/.venv/bin/python docs/acceptance/phase165d/numerical_probe.py
```

Use a writable local npm cache in another environment; the absolute cache path above records this executor's actual choice. No lockfile/package version was changed. Initial `npm ci` with the unwritable default cache failed; its workspace-cache retry and final install succeeded. Python test/browser dependencies were installed into the existing project-local venv; optional ML was not installed. Framework TestClient deprecation and existing Vite module/chunk-size warnings remain visible, not suppressed.

Validation attempts are kept honest: the first new-test development run exposed the confirmed boundary/receipt gaps (and one subsequently corrected out-of-range test fixture). An early performance run exposed the now-fixed reconciliation abort. A development execution fixture also initially cancelled before modeled fills could occur; final partial-fill cases use explicit cancellation timing that actually produces fills, retaining the nonzero-fill assertion. A final full invocation from the repository root failed three unrelated relative-path checks; the prescribed `backend/` invocation above then passed all 2,469. One browser rerun overlapped dependency reinstallation and hit a Vite startup refusal; another deliberately large-data probe initially used a zero component-age allowance and was correctly rejected. Those failed attempts are retained separately from final passing outputs; no checks were altered to hide them.

## Chromium workflows and screenshot review

The primary suite uses actual React/Vite, loopback FastAPI, secure admission and native PAPER engines. Fault-response and connection-state substitutions are explicitly labeled probes. All original 15 workflow groups run, covering BTC/ETH/SOL, cross-market blocking, zero/unavailable fields, modeled execution/configuration differences, independent gaps/segment reruns, 422/429/503, malformed responses, pending edits/cancellation/unmount/restart, keyboard navigation, and existing scenario/optimizer/replay/Vault flows. D adds permanent same-session retirement, three synchronous clicks, input round-trips, explicitly preconfigured risk with actual modeled fills, a 1,000-frame render, and malformed original-clock rejection.

The final run has **21 passed groups**, zero page exceptions, zero unexpected console errors, and **21 screenshots**. Expected fault/network console messages are retained and distinguished in [browser-results.json](acceptance/phase165d/browser-results.json). All failed HTTP requests were retained in `network_failures`; only explicit cancellation/restart error codes are classified expected. `unexpected_network_failures` is empty. A real backend restart retires old receipts; repeated dataset/market/frame/execution selections cannot revive them.

Actual images were opened for review: full-layout evidence, all five widths of metric panels, representative equity charts including mobile/medium/desktop, large-data metrics, incomparable state and gap/Vault evidence. Text, exact-value access, wrapping, internal metric-table scrolling, independent axes and source/authenticity caveats remain readable. Long tables intentionally scroll inside a bounded focusable region; this is not document overflow. Small static axis edges retain the chart library's native clipping behavior; exact observations remain inspectable.

Full-page captures retain the application shell and start at the top, avoiding a scrolled fixed-header artifact. Supplemental isolated `metrics-*`/`equity-*` component captures temporarily hide fixed global chrome during capture; these document component readability, not a different production layout. No application CSS redesign was necessary.

- Full layouts: [1920](acceptance/phase165d/comparison-1920.png), [1440](acceptance/phase165d/comparison-1440.png), [1024](acceptance/phase165d/comparison-1024.png), [768](acceptance/phase165d/comparison-768.png), [390](acceptance/phase165d/comparison-390.png).
- Isolated metrics: [1920](acceptance/phase165d/metrics-1920.png), [1440](acceptance/phase165d/metrics-1440.png), [1024](acceptance/phase165d/metrics-1024.png), [768](acceptance/phase165d/metrics-768.png), [390](acceptance/phase165d/metrics-390.png).
- [Large bounded comparison](acceptance/phase165d/large-comparison-1000.png), [large metrics](acceptance/phase165d/large-metrics-1440.png), [independent segment 2](acceptance/phase165d/independent-gap-segment-2.png), [market incompatibility](acceptance/phase165d/market-incomparable.png), [exact Decimal/Vault mobile](acceptance/phase165d/vault-exact-decimal-390.png).

## Remaining limitations and Phase 16.6 recommendation

No suitable authenticated historical recording, independently established rights, macOS executor, genuine external market-data environment or real exchange execution experiment was available. These remain **BLOCKED / NOT RUN**, rather than successes. Generated BTC fixtures intentionally exercise user-asserted recorded labels; labels are not proof of genuine venue data. Optional real Redis deployment and ML-training paths are not newly certified.

The single worker deliberately remains occupied during admitted work even after a browser cancels. Near-limit selection can take roughly a minute and a new segment selection reruns the calculation. Metrics/traces remain descriptive and bounded; matching hashes/settings do not prove matched economic conditions, causal PnL attribution, profitability or statistical significance. The existing process-local/owner-controlled storage boundary remains necessary; these APIs are not public multi-tenant authentication.

All required local Phase 16.5 gates have executed passing evidence, and the three historical full-suite failures are resolved accurately. **Ready to proceed to Phase 16.6 local research work.** Keep this PR draft for review and do not merge automatically. External source/licensing/macOS and any production or live-trading authorization remain separate decisions.
