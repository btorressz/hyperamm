# Phase 17.6 — Final Portfolio Research Acceptance, Security & Regression

Base: latest `main`, `9a87191f9f78207114453fc0e6eb9c52ad336c9f` (merged PR #79).
Acceptance date: 2026-11-12 (America/Los_Angeles).
Status: **PASS for local hypothetical PAPER research acceptance.** Exact executed results and external limitations are recorded below.

## Prerequisite review and initial gap assessment

Reviewed merged GitHub PR metadata/descriptions #73–#79, their checked-in acceptance reports, portfolio contracts/provenance/configuration/allocation/orchestration/accounting/exposure/temporal/risk/scenario/stress/metrics/preview/terminal/chart implementations, API boundaries, native SimulationService/Executor/Engine integration, React forms/store/hooks/validation/analytics, and previous browser/resource harnesses.

| PR | Phase | Review conclusion |
| --- | --- | --- |
| #73 | 17.1A | Immutable capital/configuration foundation; originally unexecuted tests were explicitly deferred. |
| #74 | 17.1A.5 | Native acceptance, nested-model revalidation, exact decimal canonicalization and isolation. |
| #75 | 17.2 | Sequential isolated native PAPER markets within one admission; compact original receipts. |
| #76 | 17.3 | Shared hypothetical capital, native economics/exposure, eligibility and post-execution risk. |
| #77 | 17.3H | Financial timeline revalidation, source-bound risk and explicit unverified correlation. |
| #78 | 17.4 | Six real dataset transformations followed by native baseline/stress execution. |
| #79 | 17.5 | React workspace, authoritative preview, compact terminal and bounded charts. Browser count discrepancy confirmed. |

Before changes: the architecture already covered the requested financial and authority boundaries. Acceptance gaps were an all-route adversarial matrix, terminal projection consistency checks, explicit final worker contention/cancellation checks, actual configured catalog/browser integration, five recorded viewport checks and fresh resource measurements. No evidence justified another engine, worker, queue, strategy or database.

## Architecture and changes

React local draft → server-authoritative preview/catalog profiles → immutable configuration/fingerprint → one shared research admission → BTC/ETH/SOL sequential native PAPER execution → validated accounting/temporal/exposure/risk → optional transformed stress leg → compact source-bound terminal/chart projection. The native histories are validated before disposal; HTTP contains bounded receipts and sampled original observations.

**REUSE:** Phase 17.1–17.5 contracts, SimulationEngine/Executor, accounting/PnL/funding/fees, risk thresholds, dataset transformations, catalog/SDK, local security middleware, React/Query/Zustand/HistoryChart and existing tests.

**ENHANCE:** compact terminal validation now binds accounting/exposure/risk/configuration identities, market identities, original chart clocks, source counts, terminal values and retained global drawdown extrema. Terminal stress metric values/eligibility and risk transitions are recomputed with the existing comparison functions. The compact projection adapts its already-bound source header to the unchanged native comparator contract; original risk-only report callers remain supported. Frontend validation rejects inconsistent endpoints, retention metadata, duplicate markets and risk policies before storing results. Original wire fields, configuration fingerprints, `/run`, `/analyze`, `/stress`, risk formulas and limits are unchanged; risk availability/decision aggregation is shared with terminal validation.

**ADD:** focused Phase 17.6 adversarial/native/catalog/lifecycle cases; eight frontend substitution regressions, a compact native two-market terminal fixture, and a failed-validation lifecycle regression; actual configured catalog Chromium harness; cold-process resource harness; compact final evidence and this report. No production module or frontend component is added.

## Bugs found and fixed

1. The browser accepted changed chart endpoint equity/PnL, incorrect first sequence/source count/sample flag, duplicate market sources and a substituted risk policy/decision. Eight new cases reproduced acceptance before the frontend guard was extended.
2. Compact backend terminal validation bound chart fingerprints but omitted several cross-report source links, original per-sequence timestamps and retained drawdown maxima/ending values. Resealed internally inconsistent projections are now rejected. Risk availability/decision/compliance is also checked against the original seven checks through shared aggregation semantics. Original same-job native computation remains authoritative.
3. Compact terminal stress results accepted a resealed, arithmetically coherent comparison unrelated to the leg's native metrics, or an inconsistent risk transition. Two independently reproduced failing cases now reuse native comparison recomputation to reject those substitutions.
4. A refused validation request after an accepted preview left the old preview usable and Run enabled. Actual Chromium and a failing store regression reproduced this. Current-request failures now clear preview/result, preserving stale-token rejection and requiring explicit successful validation before another run.
5. Documentation discrepancy: #79 described 15 workflows/five viewports; committed `phase175/browser.json` contains **14 workflow entries/four measured viewports**. Its browser began at 1440×1000 but omitted that size from the measurement loop. This is an evidence-count defect; no responsive functional defect was inferred. Phase 17.6 records actual array lengths and measures all five sizes across all four sections.

Hashes remain consistency bindings, not signatures. An attacker who controls all source evidence and hashes cannot be authenticated by these projections. Requests cannot supply results, receipts, charts, datasets or authoritative decisions; the backend always executes native research.

## Accounting, economic correctness and risk

Independent one-market BTC, two-market ETH/SOL and three-market BTC/ETH/SOL oracles use native receipts and Decimal arithmetic. They reconcile total capital = allocations + reserve; equity = reserve + sum(native equity); PnL = equity − initial; native realized + unrealized − fees + funding at native 28-digit precision; exact portfolio rounding residual; gross/signed net exposure; allocation utilization; session loss; and full-history drawdown from every original aligned observation, including initial capital in the peak.

Existing focused suites independently cover reserved-capital utilization, positive-equity modeled leverage, signed position × native mark, concentration, missing/duplicate market accounting, corrupted native ledger/fees/funding/marks, invalid monetary precision, incompatible windows and incomplete histories. Nonpositive equity leaves leverage/utilization unavailable. Reserve is included once, fees are not deducted twice, and unavailable evidence supplies no fabricated portfolio metric.

All seven configured limits retain deterministic NORMAL/WARN/REDUCE/HALT thresholds, inclusive hard bounds and simultaneous breach ordering. Missing critical economics/history yields BLOCKED; a known HALT survives alongside BLOCKED. Research decisions are hypothetical and post-execution; they do not enforce operational trading limits or prevent orders already simulated.

## Six stress scenarios and temporal/provenance integrity

CORRELATED_SELLOFF, BTC_LED_VOLATILITY, LIQUIDITY_SHOCK, FUNDING_STRESS, ORACLE_DEGRADATION and CONCENTRATION_STRESS run real baseline/transformed datasets through the native PAPER engine. Existing scenario suites verify canonical market order, shock bounds/lag/recovery, unchanged baselines, changed native dataset/result identities, concentration replay prefix, fee/funding/mark effects, eligible metric differences and risk transitions. The final Chromium workflow executes each scenario through local HTTP.

Complete modeled common clocks permit MODELED_ALIGNED accounting/drawdown/charts. FINAL_ONLY retains supported endpoints with unavailable drawdown/charts and BLOCKED risk. INCOMPARABLE/UNAVAILABLE suppress unsupported aggregate comparisons. Matching modeled clocks never establish historical synchronization.

`cross_market_correlation = null`; `empirical_correlation_verified = false`; `historical_market_synchronization_verified = false`; `source_authenticated = false` remain enforced in the original analysis/stress contracts. Catalog metadata verification describes instrument metadata only. It does not authenticate modeled performance, datasets or correlation. Compact terminal projections continue carrying limitations and original source identities without claiming historical attestation.

## Security and native API integration

The final all-route matrix exercises `/preview`, `/run`, `/analyze`, `/stress`, `/terminal`: forged result/receipt/chart/risk/source fields fail before admission; malformed/nonfinite JSON is sanitized; hostile Host/Origin/forwarding headers and nonlocal peers fail before body handling; fixed/chunked oversize bodies fail at 65,537 bytes. Prior suites cover forged configuration/profile/domain fingerprints, invalid modes/markets/Decimals, nested model bypass, source/result/observation substitutions, altered comparisons/decisions, exact response bounds and sanitized 413/422/429/503/500 failures.

The existing 65,536-byte request and 200,000-byte response limits remain unchanged. Bounded serialization occurs before successful worker completion and HTTP 200. Public errors contain no private paths, signing references, credentials or raw tracebacks. Responses remain no-store. Native FastAPI and actual uvicorn/Chromium integration both execute the accepted configuration through the real worker and engine.

## Operational authority isolation

Native predecessor/final suites preserve strategy/selected market, agents, risk firewall, kill switch, orders/fills/quotes, ledger/balances, native reservations, listener/subscription references, TESTNET settings and signing/execution object references. Existing native guards fail if operational adapters are invoked. Chromium captures before/after operational configuration, risk/kill switch, orders/fills, accounting configuration/cash/position/reservations/fees/funding/ledger, TESTNET enablement, signing/execution references and market listeners. They must remain equal across representative RUN/ANALYZE/STRESS/failure/cancellation workflows.

No production research path gains operational submit/cancel/signing authority. A no-research control reproduced passive demo-mark changes and different textual spellings of Decimal zero. Browser financial snapshots therefore compare exact values with canonical zero, retaining position/PnL/cash/reservation/ledger fields while excluding the changing observed mark. Demo market feeds continue their existing observations; operational controls and financial authority must remain unchanged.

## Actual configured local research catalog

The Phase 17.6 browser backend restores the production `HyperliquidMetadataCatalog` before the real application lifespan starts. It does not replace the catalog with test profiles. Catalog GET and authoritative preview bind BTC/ETH/SOL profile fingerprints; all financial workflows retain the normal resolver/SDK integration. A separate actual loader probe records metadata status/source and eligibility.

Invalid/duplicate/non-integer metadata tests exercise the real catalog class with deliberately bad loader inputs: DEMO/PAPER fallback is explicitly DEMO_PROFILE; strict mode yields UNAVAILABLE and rejects resolution. These controlled negative tests are separate from the actual configured integration. No external exchange is required for offline financial regression; metadata availability never authorizes trading.

## Worker concurrency, cancellation and shutdown

There remains one nonqueued worker. New native RUN/ANALYZE/STRESS jobs reject all nine competing operations (portfolio RUN/ANALYZE/STRESS/terminal, Simulation, Optimizer, Historical Replay, Scenario/Historical Comparison, Research Vault comparison). Cancellation retains admission until actual native completion; shutdown waits and rejects further work. Original suites verify both-direction contention, exactly one pool submission/optional Redis lease, no duplicate engine runs, failure release without retry, coordinated cancellation and unavailable Redis behavior. Browser cancellation retains occupancy and a subsequent real HTTP request receives 429. Explicit validation recovers after errors; automatic expensive retries remain disabled.

Redis/Lua coordination is covered using fakeredis. Physical Redis service certification and Phase 16.6B durable lifecycle/restart recovery remain separately tracked external work, outside this research-only final acceptance.

## Charts, browser, responsive layout and accessibility

Native sampling retains at most 120 original observations per leg, requires complete eligible histories, preserves endpoints/global financial extrema/onset/recovery/drawdown threshold crossings, and rejects material context that cannot fit. It never interpolates missing points or joins incompatible histories. Backend maximum drawdown uses the complete history; sampled series are labeled modeled observations, never full-resolution historical performance.

Component/native cases cover MODELED_ALIGNED, FINAL_ONLY, INCOMPARABLE, UNAVAILABLE, BLOCKED and known HALT, including missing drawdown as Unavailable. Chromium executes the supported financial workflows, real retention-boundary FINAL_ONLY stress, explicit input/result retirement, 429, injected sanitized 500, refused-fetch recovery and session revalidation. It checks direct navigation, chart metric selection, provenance, exact decimal allocations, mobile drawer keyboard controls, visible focus, form labels, disabled invalid forms and page overflow.

Final browser arrays and screenshots are linked below once the final run completes. The five required sizes are 1920×1080, 1440×1000, 1024×768, 768×900 and 390×844; each is measured across Configure, Analytics, Stress Lab and Provenance. These are targeted accessibility checks, not a complete WCAG certification or screen-reader audit.

## Resource limits and measurements

Unchanged limits: three markets; 3,000 combined executed frames; 24,000 frame × quote-level units; 1,500 retained native observations; 30,000 configured ledger entries; 750 accounting events; 65,536 request bytes; 200,000 response bytes. Baseline and stress share these totals.

The final harness ran seven serial fresh subprocesses: BTC×3,000, BTC/ETH×1,500, BTC/ETH/SOL×1,000, complete three-market×500, and three-market baseline+stress at 250/300/500 frames per market per leg. It records wall duration, process peak RSS, exact serialized request/response bytes, actual retained native traces, native invocation count, chart counts and worker/thread release. Profile fixtures are intentionally offline for reproducible resource workloads; actual configured catalog validation is recorded separately. Some measurements run alongside regression processes on shared cloud CPUs, so observed duration/RSS is not an SLA or a historical comparison benchmark.

## Regression and reproduction

Use Python 3.12 with backend test/redis extras and Playwright, Node 24, and the existing Chromium executable. No Docker or CI is added.

```bash
cd backend
python -m pytest -q tests/test_phase17*.py
python -m pytest -q
PYTHONPATH=tests python tests/phase176_resources.py
cd ../frontend
npm ci
npm run typecheck
npm run build
npm test
cd ..
.venv/bin/python frontend/tests/browser-phase176.py --output work/phase176-browser
```

Raw logs, failed development attempts and full simulation histories remain under ignored `work/`; only compact summaries/screenshots are committed. Development fixture mistakes (typed chart construction, reselected allocation defaults and a browser error-text assertion) were corrected without weakening production assertions or financial gates. The first final focused run also caught five comparator interface failures introduced while reusing native comparisons. The compact projection now supplies a small adapter to the unchanged comparator, preserving existing risk-only report callers; the failed assertions were retained and rerun. Existing dependency/build warnings are disclosed with final counts below.

## Executed results and final gate decision

**Final decision: PASS for the bounded, hypothetical, local PAPER research scope of Phase 17.** All required local financial/security/isolation gates pass after the recorded fixes. Physical Redis and durable recovery remain separate external gates; this is not live or production execution acceptance.

| Native regression | Actual result |
| --- | --- |
| Initial predecessor Phase 17 baseline | 682 passed; 797.16 s; 2 existing warnings |
| Initial full backend baseline | 3,202 passed, 1 optional ML skip; 1,084.52 s; 2 existing warnings |
| Corrected comparator + new acceptance targeted run | 109 passed; 14.02 s |
| Final complete Phase 17 focused run | **782 passed**, zero failures/skips; 437.477 s; 2 warnings |
| New Phase 17.6 cases within final run | **100 passed** |
| Final full backend | **3,302 passed, 1 optional skip**, zero failures; 580.041 s; 4 warnings |
| Frontend npm ci / typecheck / production build | PASS / PASS / PASS; manifest and lockfile unchanged |
| Final frontend tests | **788 passed**, zero failures/skips |
| Dependency consistency / whitespace | PASS / PASS |

Final phase counts: 17.1A/17.1A.5: 115, 17.2: 90, 17.3: 161, 17.3H: 77, 17.4: 183, 17.5: 56, 17.6: 100. The original five comparator failures were corrected without deleting tests or weakening assertions. The final clean focused and full runs both include those same cases.

The optional skip is `tests.test_agent_expansion.test_offline_training_optional_import_and_real_coefficient_export`: could not import 'sklearn': No module named 'sklearn'. Existing Starlette/httpx TestClient deprecation and the deliberately malformed concentration-selection serialization warning remain visible. JUnit recording can also emit existing `record_property` compatibility warnings. Frontend retains React Query `use client` bundling notices and the existing Vite large-chunk notice. No warning filters, assertions, test exclusions or workload limits were weakened.

**Chromium 151.0.7922.173: PASS — 19 recorded workflow entries, five measured viewports, 20 section/layout checks, 58 native engine invocations, zero normal console/page errors, three explicitly injected fault console entries (429/refused fetch/500), unchanged operational authority.** Every normal terminal action checks the exact native engine count, and both leg charts stay bounded. Actual configured catalog metadata was EXCHANGE_VERIFIED via OFFICIAL_SDK_NATIVE_META for BTC/ETH/SOL; preview captured the matching profile fingerprints.

Evidence: [browser summary](acceptance/phase176/browser.json), [native/frontend regression summary](acceptance/phase176/regression.json), [versions](acceptance/phase176/versions.json), [reproduced baseline projection gaps](acceptance/phase176/verified-gaps.json), [desktop](acceptance/phase176/desktop.png), [mobile](acceptance/phase176/mobile.png).

| Markets | Frames/market/leg | Legs | Worker s | Peak RSS MiB | Request bytes | Response bytes | Native retained | Chart points baseline/stress | Evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| BTC | 3000 | 1 | 63.9963 | 163.09 | 8,047 | 8,932 | 1,500 | 0/0 | FINAL_ONLY / BLOCKED |
| BTC/ETH | 1500 | 1 | 111.6221 | 144.44 | 15,312 | 11,384 | 1,500 | 0/0 | FINAL_ONLY / BLOCKED |
| BTC/ETH/SOL | 1000 | 1 | 62.3176 | 129.48 | 22,578 | 13,552 | 1,500 | 0/0 | FINAL_ONLY / BLOCKED |
| BTC/ETH/SOL | 500 | 1 | 35.1448 | 122.31 | 22,572 | 33,086 | 1,500 | 120/0 | MODELED_ALIGNED / ASSESSED |
| BTC/ETH/SOL | 250 | 2 | 40.2263 | 149.97 | 23,332 | 69,998 | 1,500 | 120/120 | MODELED_ALIGNED / ASSESSED |
| BTC/ETH/SOL | 300 | 2 | 52.2054 | 161.54 | 23,332 | 26,971 | 1,500 | 0/0 | FINAL_ONLY / BLOCKED |
| BTC/ETH/SOL | 500 | 2 | 119.8868 | 200.24 | 23,332 | 26,931 | 1,500 | 0/0 | FINAL_ONLY / BLOCKED |

All seven workloads released their admission and stopped worker threads. Complete three-market histories support backend drawdown and sampled charts; larger suffix histories report FINAL_ONLY/BLOCKED with no chart points. Peak RSS includes Python/test-harness imports and the native workload. These samples do not exhaust every configured ledger/event slot or prove a hard RSS ceiling. [Machine-readable workload measurements](acceptance/phase176/resources.json).

| Phase scope | Completion |
| --- | --- |
| 17.1A / 17.1A.5 contracts, allocation, provenance, native hardening | PASS |
| 17.2 isolated native multi-market execution | PASS |
| 17.3 shared hypothetical capital/accounting/exposure/risk | PASS |
| 17.3H financial timelines, risk availability and trust boundaries | PASS |
| 17.4 six modeled native stress scenarios and comparisons | PASS |
| 17.5 React workspace, bounded native terminal/charts | PASS |
| 17.6 independent local final acceptance and regression | PASS |

| Final acceptance gate | Result |
| --- | --- |
| Phase 17.1–17.5 compatibility | PASS |
| Exact hypothetical capital accounting | PASS |
| Portfolio exposure and concentration | PASS |
| Risk NORMAL/WARN/REDUCE/HALT/BLOCKED | PASS |
| All six native stress scenarios | PASS |
| Deterministic provenance and fingerprints | PASS |
| Temporal/economic eligibility | PASS |
| Bounded chart correctness | PASS |
| Server-authoritative preview | PASS |
| No forged authoritative results | PASS |
| Original API backward compatibility | PASS |
| Operational isolation | PASS |
| Shared-worker concurrency/lifecycle, including fakeredis/Lua coordination | PASS |
| Request/response resource limits | PASS |
| Frontend Portfolio Research workflows | PASS |
| Responsive/accessible targeted Chromium acceptance | PASS |
| Browser evidence count reconciliation | PASS — prior 14/four; final 19/five |
| Actual configured research-catalog validation | PASS — official loader, three verified eligible profiles |
| Focused Phase 17.6 tests | PASS — 100 cases |
| Full backend regression | PASS — 3,302 passed / one optional ML skip |
| Full frontend regression | PASS — 788 passed; typecheck/build pass |
| Final documentation | PASS |
| Separate physical Redis service acceptance | BLOCKED — no redis-server executable; fakeredis is not physical certification |
| Separate Phase 16.6B durable lifecycle/recovery | NOT RUN — outside Phase 17.6 scope |


## Remaining limits

No authenticated historical exchange performance, empirical correlation accuracy, live authorization, cross-margin/liquidation model, historical per-frame exposure/reservation enforcement, pending-order exposure, durable research jobs, physical Redis certification or production execution readiness is established. Missing/divergent oracle references follow native fallback; historical stale-reference timestamp modeling remains outside the native scenario contract. Successful local research acceptance does not expand these boundaries.
