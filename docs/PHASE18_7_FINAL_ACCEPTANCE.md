# Phase 18.7F final system acceptance

**Release decision — CONDITIONAL PASS for bounded local research.** The candidate is a loopback, single-operator DEMO/PAPER research terminal. Its results are hypothetical, and its public market observations carry source, namespace and freshness limits. Signing, release publication and deployment remain outside this review.

The tested application tree is merged `main` at `dd9e1488e027061a42cffd77e0761f8461de7226` ([PR #103](https://github.com/btorressz/hyperamm/pull/103)). The release candidate consists of that identical application and dependency tree plus the Phase 18.7F acceptance probe, evidence and documentation. The PR head identifies the candidate commit. PR #103's 3,976 backend, 949 frontend and 2,092 focused backend passes, 14 oracle checks, 14 Chromium groups, 39 route/mode checks, 71 viewport measurements, 26 scoped axe scans and 20 retained screenshots are historical results. Current evidence is linked below.

## Milestones and implementation scope

Reviewed the predecessor PR metadata and first-parent merge changes, the current source owners, README, CODEBASE, Summary, changelog, architecture, roadmap, three audit reports, final Audit 3 remediation, Phase 17.6 and the Phase 18 acceptance records. The route registration, settings, execution worker and source owners define current behavior wherever an older report describes a different revision.

| Milestone | Merged work and evidence |
| --- | --- |
| 17.1A–17.6, PRs #73–#80 | Native portfolio contracts, isolated BTC/ETH/SOL results, capital/risk, temporal checks, stress and integration. [Final acceptance](PHASE176_FINAL_ACCEPTANCE.md) |
| Audit 3.0, PR #84 | Local authority, evidence, lifecycle, security and accessibility remediation. [Audit report](../AUDIT_REPORT_3.0.md) · [Final remediation](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md) |
| 18.0A–B, PRs #85–#86 | Core/HIP-3 canonical identity, precision, metadata provenance and bounded read-only eligibility. [Contract acceptance](PHASE18_0B_ACCEPTANCE.md) |
| 18.1, PR #87 | Official network-qualified discovery, catalog generations, bounded transport and fail-closed capacity. [Discovery acceptance](PHASE18_1_DISCOVERY_ACCEPTANCE.md) |
| 18.2A–G, PRs #88–#89 | Generalized single-market PAPER, qualified admission, synthetic price, isolated workers and deterministic provenance. [PAPER hardening](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md) |
| 18.3A–F, PRs #90–#92 | Collateral and margin provenance, hypothetical capital and source-constrained risk research. [Risk acceptance](PHASE18_3_FINAL_ACCEPTANCE.md) |
| 18.4A–F, PRs #93–#95 | Market Eligibility, Funding/Basis and Quote Economics advisory evidence, validation and UI. [Advisory acceptance](PHASE18_4_FINAL_ACCEPTANCE.md) |
| 18.5A–F, PRs #96–#98 | Asset-aware policies for both AMMs, risk integration and optional advisory bindings. [Asset-aware acceptance](PHASE18_5_FINAL_ACCEPTANCE.md) |
| 18.6A–E and H, PRs #99–#100 | Explorer, qualified selection handoff, Starter/Pro/Institutional, public mark/funding, cache and expiry. [UI acceptance](PHASE18_6_IMPLEMENTATION_ACCEPTANCE.md) · [Public summary acceptance](PHASE18_6_HARDENING_ACCEPTANCE.md) |
| 18.6 source map, PR #101 | Updated developer source inventory. [CODEBASE](../CODEBASE.md) |
| 18.7A–C, PR #102 | Controlled comparison, market isolation and provider resilience. Shutdown publication is fenced in the existing summary owner. [A–C acceptance](PHASE18_7ABC_ACCEPTANCE.md) |
| 18.7D–E, PR #103 | Independent Decimal and authority oracles, browser matrix and Replay row-group accessibility correction. [D–E acceptance](PHASE18_7DE_ACCEPTANCE.md) |

**Reuse** the existing AMMs, risk, worker, ledger, discovery and summary SDK owners, native stream, physical Redis and browser harnesses. **Enhance** independent evidence for catalog turnover, resource use, process restart, deployment limits and dependencies. **Add** one opt-in read-only provider soak probe plus this report, runbook and compact evidence. There are no production modules, product changes, financial rebases, dependency or authority changes in this candidate.

## Financial compatibility

| Disposition | Evidence |
| --- | --- |
| Controlled equivalent, standard | 38 complete serialized admission/result pairs, byte-for-byte equal on PR #99, PR #100 and the #103 application tree. SHA-256 `83cfb57fec42efdc9f64114b7891881752da53a904300e7ad4439859445fcf55`. |
| Controlled equivalent, asset-aware | 18 complete serialized pairs, byte-for-byte equal across the same trees. SHA-256 `257c8d7ec9d510544b2d45302e3be10467f486eb4a1d53a4d63e9d06d8bf1ec9`. |
| Exactly reproduced, native | All 39 native data fingerprints and three native receipts reproduced the combined digest `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad`. The dataset and native portfolio digests also matched. |
| Historical attestation unresolved | PR #100 published standard `b564ad46f264f8b8295feb5dc59d4c44a3e97b2302769663aaf94dbd5fbce65e` and asset-aware `5fa22910e35da8655a6f99df148cc809a2d6043ba090c2ae051ba479e64cf47f`. The PR description, merge delta, history search for both digests and tracked acceptance artifacts yielded broad inputs, but neither the exact generator, fixed clocks, nor full aggregate input envelope. |
| Financial regression | None reproduced by the comparisons or independent oracles. |

The controlled generator fixes model inputs, catalog lifetime, receipt and execution clocks, 40 frames, 7/13 bps fees and two-second funding. The per-market cases exercise Core DOGE Constant Product and HIP-3 `xyz:GOLD` Concentrated Liquidity. Standard mode uses all 13 scenarios with risk off plus three with each modeled risk mode. Asset-aware covers those three scenarios in all three risk modes. Identical raw output across the three source trees checks serialization and economic equivalence for those fixed inputs. PR #100's published hashes retain their original scope and precise reproduction gap. [Capture details and complete hashes](acceptance/phase187f/compatibility.json)

The rerun used the same checked-in probe from each repository root with the tree's modules first on the path. Use the [published native Python probe](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility) with the same path. Compare stdout with `cmp` and `sha256sum`.

```bash
PYTHONPATH=backend:backend/tests python /path/to/phase187_paper_compatibility.py standard > standard.json
PYTHONPATH=backend:backend/tests python /path/to/phase187_paper_compatibility.py asset > asset.json
PYTHONPATH=backend:backend/tests python /path/to/native_probe.py > native.json
```

The focused oracle rerun independently reconciled signed cash flows, trade and fee ledger rows, frame-clock funding, realized and unrealized P&L, equity, inventory, available capital and reservations. Seven nonempty BTC/ETH/SOL subsets preserve allocation, risk class and modeled joint stress. Quote checks cover tick and size precision, side orientation, normalization, budget, uncrossed ladders and concrete authorization. Canonical market, network, DEX and generation remain bound down to metadata and expected PAPER admission. Six supervisory agents stay within existing authority, with Predictive Adverse Selection in SHADOW. Three observational advisory agents publish their own source-bound receipts and can't override the Firewall. The mixed failure regression withholds operative quote authorization and retires old advisory evidence after a catalog change. [Financial oracle](../backend/tests/test_phase187d_financial_invariants.py) · [Authority oracle](../backend/tests/test_phase187d_authority_acceptance.py) · [Portfolio oracle](../backend/tests/test_phase176_acceptance.py)

## Public provider and resource acceptance

| Gate | Phase 18.7F disposition |
| --- | --- |
| Mainnet public discovery | PASS for the measured sample. The unmodified app returned 200 AVAILABLE. |
| Mainnet mark/funding summaries | PASS for sampled BTC, ETH, SOL, DOGE, `xyz:AAOI` and `io:AAPL`. The six rows were current with mark and funding, with cache reuse on an immediate read and manual refresh. |
| Native read-only streams | PASS for the bounded public check. BTC/ETH/SOL official REST metadata, books and context plus fresh WebSocket delivery. One controlled disconnect yielded a replacement generation. The run took 24.271 s, created six subscriptions in each of two generations, ended with all three states STOPPED, and left zero owned threads, tasks and local subscribers. |
| Sustained provider | PASS for the measured catalog and summary workload over 1,801.006 s. Combined operational-owner soak remains open. |
| Deterministic failure and reconnect | PASS. Independent fixture checks cover rate limiting, malformed data, timeout, subscriber/disconnect lifecycle, in-flight draining, stale retirement, catalog turnover and bounded restart. |
| Testnet Core public context | PASS for the standalone official Core response. BTC, ETH, SOL and DOGE carried mark, oracle and funding fields. |
| Full Testnet catalog | Capacity-policy restriction. Official inventory returned 288 entries including Core. Keep the 64-namespace and 4,096-record ceilings. The app returned `CATALOG_CAPACITY` with no catalog and no namespace metadata fan-out. |

The bounded 20-second loop ran 91 cycles with 91 available catalog responses and 546/546 selected rows current with mark and funding. It used 574 Mainnet calls and 576 total calls including Testnet. The conservative estimate is 11,520 total weight and 520 peak rolling-minute weight for the instrumented calls. There were zero provider timeouts, network failures or 429 responses. The 273 namespace selections needed 184 acquisitions, with 89 reuses during the scheduled cycles. Median/maximum discovery route latency was 0.110/7.522 s and summary latency was 1.255/2.204 s. The first cycle reused all three namespace captures on an immediate read and manual refresh. The loop rejected 29 previous-generation requests with 409 and retired the last generation at shutdown.

Process peak RSS was 94,832 KiB including imports and startup. The sampled RSS increase over the first snapshot was 31,536 KiB. Sampled peaks of 7 threads and 24 retained captures returned to zero discovery threads, summary tasks and retained captures after owner shutdown. The event-loop executor drained on loop close and the process returned to one thread. Successful SDK calls completed their session close path. This sampled run bounds the observed workload and leaves longer-term memory behavior open.

The independent fake SDK soak ran 100 reconnect cycles in 10.282 s with zero residual owned resources. The controlled summary fixture ran 80 requests over 400 virtual seconds, 40 cache hits, 40 acquisitions and zero source failures. Its 6.011 s measured wait ceiling and 24-start rolling allocation are fixture results.

[Provider metrics and compact observations](acceptance/phase187f/provider-soak.json)

The summary contract accepts 1–13 unique keys, at most 3 namespace acquisitions, 24 retained captures, 15 s automatic reuse, 30 s maximum observation age, a 5 s minimum manual-refresh interval, 24 starts per rolling minute, a 6 s API wait budget and 30 s upstream 429 backoff. Discovery is capped at 64 namespaces and 4,096 records. Explorer refreshes at 20 s while visible. The current catalog, market identity, universe position and observation fingerprint remain distinct. Mark and funding carry provider units and local receipt freshness. [Source and budget matrix](PHASE18_7_ACCEPTANCE_MATRIX.md)

The documented provider budget is 1,200 request weight/minute per IP. Using the default 20 per Info request as a conservative estimate, summary starts alone can account for 480. At the discovery cap a single collection can attempt 64 metadata calls plus inventory and optional spot metadata, up to 1,320 weight on this estimate before the deadline. Advisories have their own cache, bounded concurrency and backoff, and may call current context, book and history with extra weight for returned history items. Native REST snapshots have separate metadata/book/context acquisitions, while native WebSocket generations use separate bootstrap REST and subscription budgets. Independent owners and other processes on the IP can overlap. The measured soak estimates the weight of the instrumented discovery and summary workload. Aggregate IP traffic remains unqualified. Measure complete mixed-owner demand before broader rollout. [Provider rate policy](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)

## Browser, OS and accessibility

| Platform or check | Result |
| --- | --- |
| Linux Chromium | PASS. Chrome 151.0.7922.173 passed 14 workflow groups, all 13 routes in each presentation mode (39 checks), 71 viewports, 200% zoom and zero page errors. All nine agent panels, guided and advanced PAPER, both AMMs, risk, portfolio, replay, comparisons, Vault, Logs, retained results, failed admissions and navigation/reconnect were covered. |
| Linux Playwright Firefox | NOT RUN. Playwright install failed at supported mirrors with HTTP 403. No compatible installed binary. |
| Linux Playwright WebKit | NOT RUN. A separate WebKit install also failed with HTTP 403. No compatible installed binary. |
| macOS Safari and Windows Chrome/Firefox | NOT RUN. Host unavailable. |
| Physical mobile browsers | NOT RUN. The responsive measurements use desktop viewport emulation. |
| Chromium scoped axe A/AA | PASS for automated checks. 26 scans, zero violations. Keyboard mode selection, financial-table scrolling, drawer focus containment and focus return passed. |
| Assistive technology/manual accessibility | NOT RUN. VoiceOver, NVDA and native screen-reader review require those platforms. |

Serial Chromium reruns also passed Phase 18.6 (8 groups), Phase 18.2 (36 checks), Phase 17.6 (22 groups) and the Audit 3.0 accessibility suite (32 route/viewport scans and 200% zoom, zero automated violations). The Audit 3.0 run retained 33 incomplete contrast rule results.

The scoped axe run retained nine incomplete rule results, including `th-has-data-cells` for the Replay book at 390 and 1440 px. The existing row-group header and row-header semantics from PR #103 remain intact. Confirm side-group announcements and cell associations with a screen reader. Incomplete contrast rules flagged the mobile menu glyph and a title. The scoped Chromium measurements sampled the targeted menu/title/financial labels, with a minimum measured text ratio of 8.45:1. Financial-table associations, chart alternatives, actual chart and table focus navigation, and status announcements after an error or reconnect require assisted review. [Browser matrix and manual entries](acceptance/phase187f/browser-matrix.json) · [Replay order book](../frontend/src/components/replay/ReplayOrderBook.tsx)

## Operational safety, recovery and installation

The release app started twice on loopback with DEMO/PAPER and signing disabled. Both processes returned health, a terminal WebSocket frame, risk, authorization and Vault reads and a real 10-frame local PAPER response. The second process published a fresh process identity. The first process also served a real Mainnet catalog and CURRENT BTC summary. A separate 10.583 s Chromium smoke against the unmodified app and Vite proxy rendered official Core BTC mark and funding labeled Current, with zero page errors. Both logged complete graceful shutdown after SIGTERM. A separate startup enabled native public REST and WebSocket observations with Market Explorer disabled. Both native BTC paths reached AVAILABLE, the subscriber closed, and the app shut down cleanly. Browser replay used a valid owner-only generated fixture and existing engine, and browser observations use labeled fixtures. [Process smoke](acceptance/phase187f/release-gates.json) · [Runbook](PHASE18_RELEASE_RUNBOOK.md)

The existing regression suite covers Host, peer, Origin and forwarded-header checks, request size, signing defaults, bounded admission and sanitized errors. It covers active PAPER worker and provider ownership during shutdown, rejection and recovery, stalled reads, subscriber/session cleanup and retired generations. The PR #102 guard withholds CURRENT after summary shutdown starts. The observed release model is one loopback worker, a trusted single operator and no forwarded deployment.

Physical Redis 8.0.2 passed seven checks against a disposable loopback server. The existing harness tested application health and Pub/Sub with subscriber cleanup, coordinated PAPER admission, expiring leases and heartbeat, outage admission failure and manual kill, same-process recovery and shutdown. Deterministic fakeredis cases are separate. Redis recovery in one live process does not provide durable restoration of historical orders, financial state or interrupted jobs. [Redis and recovery evidence](acceptance/phase187f/release-gates.json)

A fresh Python 3.12.14 environment installed the wheel from the baseline with all declared extras (`test,redis,ml,yahoo`) plus pytest-xdist and Playwright. `pip check` passed. Locked `npm ci`, TypeScript, the Node tests and the production build passed on Node 24.19.0/npm 11.9.0. The first frontend install hit tarball errors using the default cache path. Repeating with a clean workspace cache resolved it without changing the lockfile. The first test launch lacked loopback listen capability. The rerun used the original test command in a loopback-capable environment. A recorded range resolution identifies the tested environment. Exact future Python dependency resolution remains open. [Resolved versions](acceptance/phase187f/environment.json)

Production-only and full npm audits returned zero findings for both the installed and lockfile trees during this run. The locked development tree still contains picomatch 4.0.7 and its Vite/fdir/tinyglobby paths. The audit service did not return the historically recorded `GHSA-fc5q-39xc-vjpf` and an independent query to the advisory API was blocked on this host. The reported fixed-version tarball check returned 404 for 4.0.8. Retain the historical development advisory as open pending reconciliation. Its recorded dependency path is development-only. No package upgrade or downgrade was applied. Python dependency vulnerability assessment remains open. [Historical advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) · [Audit evidence](acceptance/phase187f/environment.json)

## Audit 3.0 remaining gates

| Finding or area | Disposition |
| --- | --- |
| A1-001 / A1-006 | PARTIAL. Guarded no-signing fixtures validate wire authorization and account for duplicate or uncertain resting exposure. **SIGNED TESTNET — NOT RUN.** Signed submission, acknowledgement, partial fills, cancels and unknown-state reconciliation require separate authorization. |
| A1-003 / A1-004 | PARTIAL. Public read-only reconnect and shutdown, fixture lifecycle and bounded provider measurements executed. Real operational SDK mode-switch, fault and shutdown soak remain open. |
| A1-009 | Bounded local boundary verified. Remote authentication, roles, TLS/proxy deployment, concurrent operators and production hosting remain outside release scope. |
| A1-016 | PARTIAL. Count-based regime, volatility and SHADOW rules retain fixture-backed numerical limits. Real cadence, model, strategy and confidence calibration remain open. |
| A1-017 | PARTIAL. Fresh Python install and exact resolved snapshot recorded. Python dependency locking and NumPy footprint policy remain open. |
| A2-003 | PARTIAL. Quantized, stable logical slots and exposure are covered by local invariants. Actual effective-price, churn and venue-cost policy remains open. |
| A2-005 | PARTIAL. Repeated Linux process and Redis teardown passed. Historical macOS and Windows lifecycle acceptance remains open. |
| Phase 16.6B | Separately gated. Durable recovery across process failure is unavailable. |
| Historical licensing | NOT RUN. Source attestation, acquisition rights and licensed historical coverage require external evidence. Validated replay receipts preserve the supplied source limitations. |
| Development advisories | OPEN. Reconcile the recorded picomatch finding with the current zero-finding npm response and unchanged locked version. |
| Alternate references | RedStone public HTTP, authenticated RedStone/CoinGecko, Yahoo observations and live Kraken quorum/soak were not independently accepted here. Handler and provider fixtures retain their bounded claims. |
| Additional external operations | Redis multi-host failover, sustained outage and version matrix, prolonged orphan/UNKNOWN backpressure, and broad frontend performance or assistive-technology acceptance remain unverified. |

[Audit 3.0 open-gate inventory](../AUDIT_REPORT_3.0.md#15-unverified-concerns-and-external-blockers) · [Historical mitigation scope](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md#remaining-limits-and-verdict)

## Final regressions

| Check | Current result |
| --- | --- |
| Full backend | 3,976 passed, 0 failed, 0 skipped, 6 warnings, 658.55 s. |
| Focused backend | 2,062 passed, 0 failed, 0 skipped, 6 warnings, 593.88 s. Includes Phase 17 and 18, provider lifecycle, Audit 3.0, guarded execution and risk checks. |
| Existing financial, authority and provider group | 155 passed, 0 failed, 0 skipped, 4 JUnit instrumentation warnings, 55.93 s. Includes the 14 financial and authority oracle checks. |
| Frontend Node tests | 949 passed, 0 failed, 0 skipped or cancelled, 59.738 s. Locked install, typecheck and Vite production build passed. |

The Node tests logged one Zustand unavailable-storage warning. The backend warnings consist of the existing Starlette/httpx deprecation, Pydantic instance-field deprecation and the negative serialization fixture. The Vite build generated the static bundle with existing TanStack directive and chunk-size warnings.

The focused backend command selected `tests/test_phase17*.py tests/test_phase18*.py tests/test_phase155*.py tests/test_audit3*.py tests/test_execution.py tests/test_phase8*.py`. The full and focused runs used two pytest-xdist workers. The dedicated oracle run selected `test_phase176_acceptance.py`, `test_phase187d*.py`, `test_phase187_provider_resilience.py` and `test_phase186h_market_summaries.py`. The 44-test provider fixture rerun recorded the existing resource properties separately.

The [regression record](acceptance/phase187f/regression.json) reports exact results and warnings. Focused cases overlap the full backend suite and are not added to its total. Browser and external results are tracked independently.

## Release readiness matrix

| Capability | Decision and scope |
| --- | --- |
| Local DEMO/PAPER terminal | PASS in the verified loopback, single-operator Linux/Chromium environment with signing disabled. |
| Core/HIP-3 read-only discovery | PASS for official Mainnet catalog coverage in the sample. Testnet remains capability-limited. |
| Actual public mark/funding summaries | PASS for sampled BTC, ETH, SOL, DOGE, `xyz:AAOI` and `io:AAPL`. The six rows were current with mark and funding, with cache reuse on an immediate read and manual refresh. |
| Sustained public-provider operation | PASS for the measured catalog and summary workload over 1,801.006 s. Combined operational-owner soak remains open. |
| Generalized single-market PAPER | PASS within qualified Core/HIP-3, synthetic price and current catalog bounds. |
| Asset-aware AMM research | PASS with operator declarations and existing risk-mode bounds. |
| Both existing AMM models | PASS for exercised fixture and browser contracts. |
| All nine agents | PASS for existing supervisory and observational roles. |
| Risk Firewall and authorization | PASS for bounded local PAPER and guarded unsigned fixtures. |
| Native BTC/ETH/SOL portfolio research | PASS for native subsets, hypothetical allocation and modeled stress. |
| Historical Replay | CONDITIONAL on valid, permitted configured datasets. Generated data exercised the actual engine. |
| Starter/Pro/Institutional UI | PASS on Linux Chromium. |
| Chromium | PASS for the exercised Linux build. |
| Firefox | NOT RUN. Binary installation blocked. |
| WebKit | NOT RUN. Binary installation blocked. |
| Native OS and mobile browsers | NOT RUN. |
| Manual accessibility | NOT RUN. |
| Physical Redis | PASS with local Redis 8.0.2. |
| Signed TESTNET | Separately gated. NOT RUN. |
| Full Testnet catalog | Capacity-policy restriction. |
| Durable recovery | Separately gated. |
| HIP-3 signed execution | OUT OF SCOPE. |
| Mainnet execution | OUT OF SCOPE. |
| Remote multi-user production | OUT OF SCOPE. |

Phase 18.7F records a bounded release decision for independent review. Follow-up work belongs in separate acceptance tasks for the remaining operational SDK lifecycle, assistive technology and native platforms, historical-source rights, Python reproducibility and dependency reconciliation, signed TESTNET and durable recovery. Multi-owner provider operation needs a measured shared-budget gate before sustained combined use. [Release runbook](PHASE18_RELEASE_RUNBOOK.md)
