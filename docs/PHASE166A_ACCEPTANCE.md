# Phase 16.6A.2 — Native profiling, integration and performance acceptance

**PHASE 16.6A LOCAL PAPER RESEARCH ACCEPTANCE: PASS.** The measured retention optimization is accepted with the maximum-gap tradeoff and measurement limits below. Merge remains manual.

## Revisions and environment

Latest `main` at task start was `0662dd77345ee55f973a65d232ea8e2cc07ee6b5`, the merge of PR #68. Ancestry was verified after fetching `origin/main`. The branch is `phase16/16-6a2-native-performance`. The untouched pre-optimization checkout is `8b7d144a2f7ab51185ef608030619ad23bc345e6` (Phase 16.5D); the untouched optimized checkout is `0662dd77345ee55f973a65d232ea8e2cc07ee6b5`.

Execution took place November 11, 2026, Pacific time, on managed Linux x86-64, Python 3.12.14, Node 24.19.0, npm 11.9.0 and Chromium 151.0.7922.173. Three logical CPUs were visible, with a cgroup quota of two cores and 8 GiB memory. Exact environment, dependency versions, lockfile digest and unchanged engine/accounting/execution source digests are in [environment.json](acceptance/phase166a/environment.json) and the frozen dependency list in that JSON.

All datasets are deterministic generated PAPER fixtures. Recorded-source labels in older fixtures remain user assertions. This acceptance cannot establish genuine exchange authenticity, licensing, macOS delivery, venue fill calibration or trading authority.

## Untouched initial acceptance

Before any repository source changes:

- Prescribed five-file backend suite: **145 passed**, one Starlette/httpx deprecation warning.
- Full backend: **2,475 passed, one failed, one skipped** in 161.80 seconds. The skip is optional scikit-learn training, not a research-path failure.
- Frontend `npm ci`, typecheck, production build and **704 tests passed**. The first dependency installation failed because npm's default home cache was unwritable; the retry used the existing workspace cache and the unchanged lockfile. The build retained its existing chunk-size warning and tests retained the existing unavailable browser-storage warning.
- Unchanged native Chromium harness with `--phase165d`: **21 workflow groups passed** at 1920/1440/1024/768/390px; zero page exceptions, unexpected console errors or unexpected network failures.
- Unchanged Phase 16.6A.1 profiler: all four intended top-level stages were observed. The suspected retained-reference problem did **not** reproduce for its existing lazy-import call paths. Its 128-frame sample ran alongside initial validation and is diagnostic only, excluded from comparable timing distributions.

The sole full-suite failure was `test_generated_terminal_schema_is_current`. Pydantic 2.13.5 emits implicit Decimal regex patterns that the prior evidence environment's Pydantic 2.14.3 did not emit. Exactly 27 pattern entries differed, solely in composed `inventory` and `perp_context` observation wrappers. The committed terminal schema, domain output and financial evidence did not change. The generator now strips only numeric-schema-derived patterns from detached composed properties. Domain definitions retain exact Decimal formats and bounds. The generated contract now equals the committed schema, and all three terminal-contract tests pass. No expected schema or test assertion was weakened.

## Reuse, fixes and scope

The existing SimulationEngine, SimulationService, single-slot SimulationExecutor, replay adapter/storage/contracts, quantitative/foundation validators, PAPER accounting, risk authorization and Lightweight Charts remain the owners of behavior. The Phase 16.6A.1 archive/index/memoization implementation is retained. Final implementation snapshot: `c606900` (a separate acceptance/evidence commit follows).

The profiler now patches defining attributes and already-imported application aliases, verifies every expected stage count (including modeled baselines and all segments), rejects missing/failed stages, records inclusive nesting, and optionally runs cProfile inside the existing admitted executor thread. Context-managed instrumentation restores all original methods on success and failure. Standalone fixtures check worker release and shutdown, byte budget, unchanged source files and removed temporary storage. No instrumentation is installed in production.

Focused tests extend archive parity to all-market disconnected segments and exercise cancellation inside an actual replay/scenario engine frame. The existing Chromium harness gains direct mounted HistoryChart lifecycle/hover and lookup measurements, plus repeated segment-selection checks.

The 1,000-frame cProfile diagnostic identified `OrderHistory.prune` at 5.84 inclusive seconds of the 25.39-second instrumented job, including 5.80 million read-only fill-pin checks. The smallest measured candidate adds an early return when the entire closed set is within its existing retention allowance. The eligible unpinned subset cannot be larger, so the original algorithm's deletion slice is necessarily empty in this case. Above that bound, the original algorithm is untouched. Event observation still occurs before pruning; active orders, protected rows, eviction ordering and capacity semantics remain unchanged. Production pin predicates were reviewed: PAPER uses read-only fill membership and guarded TESTNET uses read-only verification/accounting sets. No signing or venue action is added.

A legacy-algorithm oracle compares every retained row, closed-row order, active/recent projection and observer callback across limits 1/3/1000, pinned/unpinned rows and randomized lifecycle transitions. Complete original outputs also remain equal. The candidate is accepted only after final matched timing and regression checks; its clean benchmark worktree is `c606900`.

The direct React probe also found a committed stale hover: new points reported `1101` while the first React commit still rendered the previous `1001` readout. A later chart event concealed it. HistoryChart now binds formatted hover to the memoized points/lines/axis/fit-key revision and hides mismatched hover synchronously, before passive effects. The probe observes real committed DOM through React Profiler and rejects stale data/labels at every tested revision; a valid fresh crosshair event may restore the current value. The change preserves indexed lookup and coordinate memoization.

## Exact deterministic and financial parity

The unchanged [parity harness](../backend/tests/phase166a_parity.py) ran in separate clean revision processes with the same interpreter/dependencies. [parity.json](acceptance/phase166a/parity.json) is the compact **16-case equality matrix**: complete generated case objects compared equal before projection; paired case-object digests and original canonical archive/scenario/replay/selected-receipt hashes remain auditable. The digest algorithm and recorded revisions are explicit; neither financial normalization nor tolerance is applied.

Twelve cases cover BTC, ETH and SOL, each with complete/gapped histories and baseline/modeled execution. Every case independently validates canonical archive bytes and stored archive fingerprints. The evidence compares SHA-256 of complete serialized scenario captures, complete replay results, every original modeled/baseline archive string, and every selected-segment quantitative receipt. Each case-object digest additionally binds original source/engine dataset, scenario/segment run and full replay fingerprints; the unchanged script regenerates those fields. Three further admitted-worker cases retain complete baseline/modeled archives with nonzero fills for BTC/ETH/SOL under explicitly disabled research-only reference risk. A sixteenth case exercises an actual admitted two-segment modeled partial-fill comparison worker, with original response/receipt identities and all metric rows.

Complete output equality covers retained equity, PnL, realized/unrealized values, returns, drawdown, inventory, fills, fees, funding, utilization, risk counts, execution assumptions, configuration/source provenance, trace ordering and independent segment resets. These are full evidence comparisons, not selected metric tolerances. No canonical fingerprint algorithm or Decimal arithmetic changed; no non-economic metadata exception was needed.

The original archive path performed `canonical_json(result)` followed by `stable_fingerprint(json.loads(archive))`. The optimized path performs one JSON-mode model dump and derives both the same canonical JSON and the same existing fingerprint from it. Existing Pydantic archive parsing and identity validators still run independently. Microbenchmarks alternate old/new operation order, assert exact wire/hash equality on every iteration and report all samples separately from worker benchmarks.

## Measurement procedure

Small workloads use the same Phase 16.6A profiling file against clean application checkouts with `--no-instrument`: 128 and 250 frames receive five independent jobs each; 1,000 frames receives three. Scenario/historical counts are equal, retained/transported trace cap is 120, and all configuration/source/request evidence is identical between revisions. The first admitted job in each process is labeled process/thread cold; later jobs are process/thread warm. Neither filesystem caches nor CPU caches were flushed. Each job constructs fresh service/engine state; no research-result cache exists.

Boundary workloads reuse the **unchanged** Phase 16.5D harness through `phase166a_near_limit.py`. Its limits, fixture construction and admission remain authoritative: 1,000/1,001 and 4,999/5,000 historical/scenario frames, 64 frames over 32 independent segments, missing observations, 128-frame modeled crossing and the 1,024-gap case. Each revision receives three fresh process runs. The minimal identical observer retains original result fingerprints; its tuple append/field-read overhead is inside reported worker time. Within each process the first case is cold and subsequent cases are warm. The two harnesses use different trace/configuration settings, so their 1,000-frame timings are deliberately separate.

Benchmark processes run serially, without simultaneous browser/test/profile workloads. The baseline/foundation order reverses on alternating small workloads and boundary repetitions. The measured retention candidate is then run in a third clean checkout using the same interpreter/dependency snapshot, machine/cgroup limits, inputs, common measurement harness and run counts. All earlier baseline/foundation samples are retained; final-candidate runs follow those trials chronologically, so thermal/host-load drift cannot be ruled out. Individual samples, medians, minima, maxima, variation, source identities, response bytes, cumulative RSS and worker release are retained. An exploratory boundary run without fingerprint retention was excluded; interrupted measurements were discarded. Profiling runs are separate and excluded from comparative worker timing.

Linux `ru_maxrss` is a cumulative process high-water mark including imports, fixture setup and earlier jobs. It is neither an independent per-job allocation peak nor a subtraction-based memory saving. Headless browser heap and animation intervals are observations with separate limitations.

## Measured results

All times below are recorded serial admitted-worker measurements. Positive reductions mean lower observed medians versus Phase 16.5D, not hardware-independent guarantees. [benchmarks.json](acceptance/phase166a/benchmarks.json) consolidates **all nine workloads and three revisions**, with configuration, exact SHAs, every original wall-time sample, run counts, min/median/max, cumulative RSS, bytes, repeated-segment-selection times and compact identity checks. No replay/result objects or frame dumps are retained.

| Historical / scenario workload | n per revision | Baseline median [min–max] | Foundation median [min–max] | Final median [min–max] | Reduction vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| 128 / 128; trace 120 | 5 | 1.127s [1.087–1.251] | 1.147s [1.056–1.289] | 1.050s [1.026–1.123] | +6.8% |
| 250 / 250; trace 120 | 5 | 2.398s [2.320–2.446] | 2.368s [2.311–2.414] | 2.183s [1.982–2.292] | +9.0% |
| 1,000 / 1,000; trace 120 | 3 | 12.400s [12.009–12.536] | 12.125s [12.120–12.148] | 11.118s [10.534–11.260] | +10.3% |
| 1,000 / 1,001; trace 250 | 3 | 12.568s [12.054–14.261] | 12.568s [12.230–12.904] | 10.724s [10.350–10.761] | +14.7% |
| 4,999 / 5,000; trace 250 | 3 | 68.603s [68.268–77.417] | 69.041s [68.634–71.550] | 59.373s [57.354–60.579] | +13.5% |
| 64 / 65; 32 segments | 3 | 0.614s [0.606–0.629] | 0.557s [0.543–0.584] | 0.536s [0.527–0.577] | +12.7% |
| 4 / 5; 1,001 issues | 3 | 0.299s [0.278–0.300] | 0.277s [0.272–0.288] | 0.265s [0.251–0.294] | +11.4% |
| 128 / 129; modeled fills | 3 | 5.485s [4.811–5.697] | 4.813s [4.603–4.854] | 4.603s [4.550–4.736] | +16.1% |
| 64 / 65; 32 segments, 1,024 gaps | 3 | 0.867s [0.838–0.910] | 0.878s [0.773–1.090] | 0.912s [0.890–1.050] | -5.3% |

The foundation alone did not establish a material bulk-worker latency improvement: its 1,000/1,001 median was effectively unchanged, and its near-limit median was 0.6% slower. The final profile-guided retention change has lower bulk medians with non-overlapping baseline/final ranges for the 1,000- and 4,999-frame cases. These observed improvements support retaining the four-line fast path, with chronological run order and host variation disclosed above.

The maximum-gap stress case is **5.3% slower by observed median**, a 45.5ms increase, with overlapping ranges and a 1.050s maximum. It remains bounded and correct; no faster gap-processing claim is made. Its gap adapter/validation work is unchanged. The observed small stress-case tradeoff is retained against the measured 1.8s/9.2s bulk median reductions and unchanged financial/retention evidence, rather than hiding the slower case or weakening validation.

Every paired workload retained the same response bytes and original fingerprints, released its single worker and preserved source files. Boundary responses were 405,414 bytes (1,000), 406,191 (near limit), 91,002 (32 segments), 53,299 (1,001 issues), 227,095 (modeled, 42 historical fills), and 222,080 (1,024 gaps), all below 1,000,000 bytes. Final near-limit cumulative process RSS was approximately 303MiB, essentially the same as the matched baseline. No peak-memory saving is established.

### Validated stage instrumentation and remaining bottlenecks

[profiling.json](acceptance/phase166a/profiling.json) retains stage durations/counts for every original diagnostic run, patched call sites, alternating archive microbenchmark summaries and top-10 bottleneck rows before/after the retention change. Full per-function cProfile listings and per-call arrays can be locally regenerated with the unchanged [profiler](../backend/tests/phase166a_profile.py); they are not committed. Every expected stage was measured; empty arrays/failed stages cannot produce MEASURED. The real two-segment modeled test observes five engine calls and four archives, and verifies restoration, unchanged application source hashes, worker shutdown and temporary-file cleanup. A separately loaded quantitative foundation alias is explicitly observed and restored.

Final diagnostic samples (seconds, **inclusive and overlapping**):

| Stage | 128 frames, timers only | 1,000 frames, cProfile | 128 modeled, cProfile | 64 frames / 32 segments, cProfile |
| --- | ---: | ---: | ---: | ---: |
| Total admitted worker | 1.03645 | 20.61176 | 10.54928 | 1.08432 |
| Replay | 0.36252 | 5.67992 | 9.02914 | 0.42511 |
| Scenario | 0.56553 | 14.00856 | 1.08481 | 0.51246 |
| Engine calls (nested in replay/scenario) | 0.83210 | 18.13425 | 9.70182 | 0.73821 |
| Secure dataset read/validation | 0.01842 | 0.46671 | 0.05993 | 0.05353 |
| Adapter preparation | 0.00301 | 0.04054 | 0.00480 | 0.00526 |
| Segment dataset construction (also selected-evidence reconstruction) | 0.01114 | 0.31859 | 0.02681 | 0.01063 |
| Archive serialization | 0.00293 | 0.00700 | 0.06327 | 0.01566 |
| Quantitative receipt | 0.09388 | 0.87535 | 0.39271 | 0.13279 |
| Foundation (nested in receipt) | 0.05906 | 0.60392 | 0.24399 | 0.07980 |
| Trace projection | 0.00914 | 0.04118 | 0.03370 | 0.00900 |

Do not add these columns: engine and archive work belongs to replay/scenario; foundation belongs to the receipt; dataset reconstruction occurs inside validated comparison work too. Total worker includes detached input admission, lazy imports, response construction/validation, serialized byte-budget checks and scheduling. Timers/patch wrappers add overhead. cProfile adds substantial overhead: its final 1,000-frame sample is 20.61s versus the uninstrumented 11.12s median, and is excluded from latency distributions.

Within comparable cProfile diagnostics, `OrderHistory.prune` fell from 5.8394s to 2.3175s while retaining 6,796 invocations. Read-only pin checks fell from **5,795,396 to 2,398,396**. The engine still dominates: 18.13 inclusive seconds of the 20.61-second diagnostic. Remaining costs include reconciliation (5.23s), agent supervision (4.21s), quote generation (3.63s), execution-quality lifecycle processing (2.51s), and bounded retention above its allowance. These times overlap. Funding/fees, inventory/accounting snapshots, risk/final authorization, metric collection and retained trace paths remain covered by output parity and native tests and can be inspected in regenerated full profiles; no authority, financial ordering or archive validator was removed. Modeled replay still computes its baseline and modeled engines sequentially from independent initial state.

Final 1,000-frame diagnostic top 10 application functions by inclusive cumulative time (orchestration represented above is excluded; parent/callee rows overlap):

| Function | Calls | Self seconds | Cumulative seconds |
| --- | ---: | ---: | ---: |
| `app/execution/order_manager.py:reconcile` | 2,000 | 0.0100 | 5.2286 |
| `app/execution/order_manager.py:reconcile_locked` | 2,000 | 0.0490 | 5.2125 |
| `app/agents/supervisor.py:evaluate` | 2,000 | 0.0556 | 4.2144 |
| `app/strategy/quote_engine.py:generate_perp_market_adaptive` | 2,000 | 0.0431 | 3.6299 |
| `app/agents/execution_quality.py:evaluate` | 2,000 | 0.0672 | 2.5097 |
| `app/execution/fills.py:record` | 6,796 | 0.0192 | 2.4462 |
| `app/execution/paper.py:cancel_orders` | 3,396 | 0.0124 | 2.4010 |
| `app/execution/fills.py:prune` | 6,796 | 0.6679 | 2.3175 |
| `app/risk/authorization.py:fingerprint` | 11,400 | 0.0322 | 2.3041 |
| `app/risk/authorization.py:_canonical` | 1,088,000 | 0.9344 | 1.9883 |

The final 128-frame archive microbenchmark's 30 alternating iterations measured median legacy round-trip **2.574ms** versus single-payload **2.272ms**, with exact wire/hash equality on every iteration. This characterizes archive work only. It does not explain a multi-second engine gain or establish a total-worker memory saving.

### Original native verification and failure/fix facts

The first expanded Chromium attempt completed the existing workflows, repeated segment selection and semantic chart probes, then failed the new isolated-page console assertion. Importing a development CSS module started Vite HMR from the fulfilled fixture-document origin; Chromium blocked that development websocket under its local-network policy. The fixture now injects the already-built production stylesheet instead. The strict console assertion remained, and the full expanded harness subsequently passed. This Markdown preserves the failed-attempt/root-cause facts; transient development-websocket output is not committed.

Original accepted backend verification: **240 focused tests passed** in 74.61s; **2,490 full tests passed, zero failed, one optional ML skip**, one existing Starlette/httpx deprecation warning, in 148.75s. Final frontend dependency installation, typecheck, production build and **704 tests passed**. The existing bundle-size and test browser-storage warnings are recorded here and in the compact validation manifest. No assertion was disabled or weakened. Final browser results and gate disposition follow below.


## Original browser evidence and independent gate disposition

The final native harness passed **23 workflow groups** in 73.972 seconds, at 1920/1440/1024/768/390px, with no page exceptions, unexpected console errors or unexpected network failures. Deliberate HTTP errors/cancellation/backend-restart failures remain labeled in the raw report. The isolated chart probe also has zero console errors. [browser.json](acceptance/phase166a/browser.json) retains the 23 workflow names, viewport results, zero unexpected-error counters, utility timing batches, React commit count, animation/heap observations and cleanup counters. Full request/response transcripts and individual React commits can be regenerated with the unchanged [native browser harness](../frontend/tests/browser-phase165c2.py) and [chart probe](../frontend/tests/phase166a_chart.py).

Real canvas/mouse/React checks cover same-second microsecond frame identity, exact hover timestamps, updated points in the same run, replaced line labels, time/frame axes, zero/positive/negative PnL, unavailable/null gaps, live history, independent reused segment sequences, reset, unmount and remount. The first new-data commit contains the default readout instead of the prior `1001`; a fresh chart event then shows the correct `1101`. The original failing commit rendered `Equity: 1001 quote` while the new second-point value was `1101`; the accepted probe records no such stale commit. These critical failure facts are preserved here; no duplicate DOM transcript is committed.

Actual Chromium utility measurements on 250 observations used 30 alternating-order batches, checksum consumption and per-key reference equality with the legacy lookup. Legacy batches contain 1,000 lookups; indexed batches contain 100,000 so timer quantization does not become a false zero-latency claim. Normalized observed averages were approximately **0.400µs → 0.008µs per frame-key lookup** and **78.450µs → 0.017µs per time-key lookup**. Time-index construction had a 0.100ms median; frame-index construction was below the browser timer's resolution. These are amortized utility measurements, not end-to-end crosshair-event latency or a rendering-speed guarantee.

React Profiler recorded **128 commits across the scripted isolated-chart interactions**, including many real mouse moves and source revisions. This is an observation, not a before/after React throughput claim. Native creation/cleanup observations ended at zero fixture canvases and **60 ResizeObservers created / 60 disconnected**; those observers include library internals and do not mean 60 charts. The full app also ran its actual 1,000-frame, bounded 120-point chart workflow. Raw heap/frame samples are retained; no allocation/leak or frame-rate guarantee is inferred from one short headless run.

Four original native-run screenshots are retained unchanged: [desktop 1440px metrics](acceptance/phase166a/metrics-1440.png), [mobile 390px metrics](acceptance/phase166a/metrics-390.png), [exact hover](acceptance/phase166a/history-chart-hover.png), and [independent gap segment](acceptance/phase166a/independent-gap-segment-2.png). Their byte digests are in the browser manifest; all screenshot references there resolve to retained files. Original inspection also covered equity at all five widths. Mobile distinguishes zero/unavailable without document overflow. Existing Lightweight Charts edge-tick cropping in some narrow panels remains a known limitation; pan/reset and exact observation/hover inspection remain available. Redundant widths can be regenerated; no PNG was cropped, rewritten or fabricated for cleanup.

| Gate | Status | Evidence |
| --- | --- | --- |
| Backend archive byte/fingerprint parity | PASS | Exact original canonical archives and complete replay hashes across clean revisions |
| Baseline/modeled PAPER equivalence | PASS | Baseline/modeled archives, all-market nonzero fills, full outputs and original identities |
| BTC/ETH/SOL replay regression | PASS | Sixteen independent parity cases and native regression |
| Scenario deterministic output parity | PASS | Complete serialized captured scenario hashes, repeated paired jobs |
| Historical segment identity | PASS | Gapped fixtures, 32-segment boundary jobs, selected-segment reruns |
| Comparison provenance integrity | PASS | Complete original receipts/identities, source versus engine identity and adversarial validators |
| Numerical/accounting integrity | PASS | Full typed evidence equality; original metrics/Vault/fills/fees/funding/inventory/risk retained |
| Profiling instrumentation validity | PASS | Expected call counts, retained alias observation, failure rejection, restoration and worker-thread profiling |
| Comparable before/after benchmarks | PASS | Clean revisions, frozen environment/inputs/procedure, repeated samples and disclosed chronological limits |
| Frontend chart semantic equivalence | PASS | Original index parity plus direct committed-DOM/lifecycle/mouse checks |
| Frontend TypeScript/build/tests | PASS | 704 tests; unchanged lockfile installation, typecheck and build |
| Chromium integration | PASS | 23 workflow groups, five widths, actual screenshots and strict isolated-chart console checks |
| Single worker/cancellation isolation | PASS | Busy contenders, actual frame-stage cancellation, failed work and active shutdown; original admission retained |
| Operational trading isolation | PASS | Seeded strategy/market/risk/kill/order/ledger/reservation/signer/subscription fixtures unchanged |
| Full backend regression | PASS | 2,490 passed, zero failed, one optional ML skip |
| Demonstrated performance improvement | MEASURED | Bulk medians improved 10.3%–14.7%; maximum-gap median 5.3% slower; no peak-memory saving |

Worker concurrency remains one admitted sequential computation. New cancellation tests gate the actual third replay/scenario engine frame, cancel its waiter, reject another request and keep shutdown waiting until native work finishes. Existing tests additionally cover failed/corrupted inputs, repeated selection, Redis/Lua coordination and independently seeded operational state. The browser verifies restart/session retirement and preserved active authority/subscriptions. No persistent cache, new worker/service/database, alternative engine, trading path, market provider or signing capability is introduced.

## Recommendation and external gates

**Accept Phase 16.6A.2 for bounded deterministic local PAPER research.** Exact output parity, measured scan reduction, repeated bulk-worker latency improvements and full native/browser regression justify retaining the narrow optimization. Phase 16.6B local research planning can proceed with this measured baseline. Further work should profile the remaining bounded retention, lifecycle/agent, quote-generation and validation costs; it must keep current financial ordering, independent modeled engines and provenance checks.

Genuine exchange source authenticity, independent licensing/rights evidence and independent macOS/native external delivery remain **BLOCKED external acceptance gates**, inherited from Phase 16.5D. An actual external Redis server was **NOT RUN** (existing fakeredis/Lua coordination tests passed). Venue fill/latency calibration, real-trading performance and commercial deployment readiness are not established by generated fixtures. Live submission, signing and automatic merge were not performed. These gates do not convert this local PAPER acceptance into operational trading authority.

## Evidence footprint and cleanup verification

This Markdown is the authoritative acceptance summary. Cleanup is a follow-up on existing draft PR #69; implementation, focused tests, parity/profile/near-limit/browser scripts and architecture are unchanged. The original evidence snapshot is Git commit `05d1218894a59d88dab841a91bf9d2dc6f916851`.

Six small machine-readable manifests remain because independent reproduction needs more than a prose percentage:

- [benchmarks.json](acceptance/phase166a/benchmarks.json): all wall-time samples permit independent recomputation of every median/range, including **13.5% near-limit improvement and 5.3% maximum-gap slowdown**; configuration, revision SHAs, RSS/bytes and selection reruns preserve comparability.
- [parity.json](acceptance/phase166a/parity.json): the 16-case equality/digest matrix lets regenerated canonical archive and complete-case hashes be compared exactly, without committing financial result objects.
- [profiling.json](acceptance/phase166a/profiling.json): counts, inclusive stage observations, call sites and top-N rows explain the bottleneck and instrumentation validity. Full cProfile remains locally regenerable.
- [environment.json](acceptance/phase166a/environment.json): frozen Python packages, npm lockfile digest, runtime/cgroup limits and source/harness hashes identify the measured environment and inputs.
- [browser.json](acceptance/phase166a/browser.json): workflow/viewport outcomes, compact measurements and hashes of four retained original PNGs; no references to deleted screenshots.
- [validation-results.json](acceptance/phase166a/validation-results.json): original acceptance and cleanup execution are labeled separately; historical PASS does not imply a cleanup rerun.

The three full benchmark outputs, duplicate parity outputs, full function/DOM/browser transcripts, superseded summary and all terminal/npm/build logs are removed. All nine benchmark workloads and all original wall-time samples are retained; no favorable-only filtering is applied. Initial native failure, npm cache retry, stale-hover commit, Vite fixture failure and warning facts remain above. No artifact service, CI workflow, container or LFS is added.

Cleanup checks executed November 11, 2026, Pacific time: **243 focused backend tests passed** (the original 240 selection plus three terminal-schema contract tests), zero failures, one existing Starlette/httpx warning, in 80.83s. Frontend **typecheck/build and all 704 tests passed**. Fresh standalone parity runs on baseline and final application code compare all 16 complete cases equal and match every retained case digest. Six JSON files parse; every retained benchmark wall-time/RSS/byte sample and recomputed min/median/max matches the original projection; all Markdown/screenshot links and four original PNG hashes validate; `git diff --check` passes. Implementation/test paths have zero diff against the pre-cleanup head.

Exact focused/frontend commands (using the recorded Python environment and existing unchanged-lockfile Node dependencies):

```bash
cd backend
python -m pytest tests/test_phase166a_archive.py tests/test_phase166a_profile.py \
  tests/test_phase166a_retention.py tests/test_phase165d_acceptance.py \
  tests/test_phase165c2_integration.py tests/test_phase165b_quantitative.py \
  tests/test_phase165a2_integration.py tests/test_phase165a1_contracts.py \
  tests/test_phase1641_acceptance.py tests/test_audit_terminal_contract.py -q
cd ../frontend
npm run typecheck
npm run build
npm test
```

Full backend, Chromium, long benchmarks, complete cProfile and `npm ci` are **NOT RUN again for this evidence-only cleanup**; their original accepted results above are historical. The existing deprecation, production chunk-size and Node browser-storage warnings remain. Raw cleanup logs stay in local `work/`, not in the PR.

## Reproduction

Use the Python version and installed versions recorded above; retain the repository npm lockfile. From the working branch root, with `BASE` and `OPT` pointing to clean worktrees of the exact revisions:

```bash
git worktree add --detach work/baseline-165d 8b7d144a2f7ab51185ef608030619ad23bc345e6
git worktree add --detach work/optimized-166a 0662dd77345ee55f973a65d232ea8e2cc07ee6b5
git worktree add --detach work/final-166a c60690093a60e95dac5fdac2bb98c98e143b59f8
# In separate processes for each checkout, substituting its absolute path:
PYTHONPATH="$BASE/backend:$BASE/backend/tests:$PWD/backend/tests" \
  python backend/tests/phase166a_parity.py --output work/baseline-parity.json
PYTHONPATH="$BASE/backend:$BASE/backend/tests:$PWD/backend/tests" \
  python backend/tests/phase166a_profile.py --frames 128 --runs 5 --no-instrument --output work/baseline-128.json
PYTHONPATH="$BASE/backend:$BASE/backend/tests:$PWD/backend/tests" \
  python backend/tests/phase166a_near_limit.py --output work/baseline-boundary.json
# Repeat identically for OPT; repeat boundary three times and use 250/5, 1000/3.
# Diagnostics on the working branch, separate from timing trials:
PYTHONPATH=backend:backend/tests python backend/tests/phase166a_profile.py \
  --frames 128 --cprofile --output work/stages-128.json
```

The profiling/parity entry points live on this branch and import application modules from the selected clean checkout. Both historical fixture files and the boundary harness are identical in all three revisions; source digests are recorded. Repeat final-candidate commands against a clean worktree at `c606900`, preserving the same settings. Its production change is the bounded no-op retention-scan fast path; the engine, accounting, risk, replay archive and comparison implementations are unchanged.

Use `work/` for generated raw outputs; do not copy them back into `docs/acceptance/phase166a/`. To independently audit the compact parity matrix after running the two parity commands above:

```python
import hashlib, json
from pathlib import Path
baseline = json.loads(Path("work/baseline-parity.json").read_text())["cases"]
final = json.loads(Path("work/final-parity.json").read_text())["cases"]
manifest = json.loads(Path("docs/acceptance/phase166a/parity.json").read_text())["cases"]
assert baseline == final and len(final) == len(manifest) == 16
for original, row in zip(final, manifest):
    wire = json.dumps(original, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert hashlib.sha256(wire.encode()).hexdigest() == row["baseline_case_sha256"] == row["optimized_case_sha256"]
```

For full profiling, run `phase166a_profile.py --cprofile` separately for `--frames 1000`, `--frames 128 --modeled`, and `--frames 64 --segments 32`; use timer-only `--frames 128` too. For browser regeneration (existing dependencies and Chromium), run from the repository root:

```bash
python frontend/tests/browser-phase165c2.py --python "$(command -v python)" \
  --phase165d --phase166a --output work/browser166a
```
