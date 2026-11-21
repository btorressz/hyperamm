# Phase 18.7F final system acceptance

**Local release candidate — PASS.** This decision applies to a single Linux operator using the loopback DEMO/PAPER terminal and its bounded research workloads. Independent review remains open. External venue, platform and recovery decisions are listed individually below. [Release runbook](PHASE18_RELEASE_RUNBOOK.md) · [Gate evidence](acceptance/phase187f/release-gates.json)

## Baseline and predecessor review

The branch `phase18/18-7f-final-release-acceptance` starts at the merged PR #103 commit `dd9e1488e027061a42cffd77e0761f8461de7226`, verified against `origin/main`. The candidate uses the same production source as that merge. PR #103's 3,976 backend passes, 949 frontend passes, 2,092 focused existing passes, 14 oracle cases, 14 Chromium workflow groups, 39 route/mode checks, 71 viewport measurements, 26 axe scans and 20 captures are historical observations. Fresh outcomes appear below. The earlier PR #104 catalog-only and local acceptance evidence is preserved at its original revision. [PR #103](https://github.com/btorressz/hyperamm/pull/103) · [D–E acceptance](PHASE18_7DE_ACCEPTANCE.md) · [Earlier PR #104 evidence](https://github.com/btorressz/hyperamm/tree/78b68b4b1fbe7b232a6ca55364128e28e847c1e8/docs/acceptance/phase187f)

| Merged predecessors | Implemented behavior and evidence reconciled |
| --- | --- |
| #73–#80 · Phase 17 | Native portfolio contracts, isolated BTC/ETH/SOL PAPER, exact capital and reserve, temporal evidence and risk, six stresses, terminal projection and Phase 17.6 independent acceptance. [Phase 17.6](PHASE176_FINAL_ACCEPTANCE.md) |
| #84 · Audit 3 | Runtime preflight, native precision, receipt freshness, simulation provenance, liquidity stress feasibility, Replay recovery, accessibility and dependency findings. [Final remediation](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md) |
| #85–#87 · 18.0–18.1 | Canonical network/venue/class/DEX identity, qualified eligibility and read-only discovery with a bounded, complete catalog. [Discovery acceptance](PHASE18_1_DISCOVERY_ACCEPTANCE.md) |
| #88–#89 · 18.2–18.2G | Single-market Generalized PAPER, explicit synthetic price, catalog/receipt integrity, precision, isolated worker and native financial baselines. [PAPER hardening](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md) |
| #90–#92 · 18.3 | Collateral denomination and margin mode, hypothetical and source-constrained risk, liquidation/stress limitations and fail-closed financial source binding. [Risk acceptance](PHASE18_3_FINAL_ACCEPTANCE.md) |
| #93–#95 · 18.4 | Quote Economics, Funding/Basis and Market Eligibility in the observational advisory coordinator. [Advisory acceptance](PHASE18_4_FINAL_ACCEPTANCE.md) |
| #96–#98 · 18.5 | Explicit asset-family policy, bounded controls and both existing AMMs under qualified PAPER. [Asset-aware acceptance](PHASE18_5_FINAL_ACCEPTANCE.md) |
| #99 · 18.6A–E | Starter, Pro and Institutional workspaces, all 13 routes and qualified Explorer-to-PAPER handoff. [Implementation acceptance](PHASE18_6_IMPLEMENTATION_ACCEPTANCE.md) |
| #100 · 18.6H | Actual Core/HIP-3 market summaries, namespace batching, expiry, source labels and UX hardening. [Hardening acceptance](PHASE18_6_HARDENING_ACCEPTANCE.md) |
| #101 | Current developer source and trust-boundary map. [CODEBASE](../CODEBASE.md) |
| #102 · 18.7A–C | Fixed-clock capture, source/market and provider regressions, in-flight summary shutdown correction and Testnet cap disposition. [A–C acceptance](PHASE18_7ABC_ACCEPTANCE.md) |
| #103 · 18.7D–E | Decimal and concrete authorization oracles, all seven native portfolio selections, browser engine selection and Replay row-group semantics. [D–E acceptance](PHASE18_7DE_ACCEPTANCE.md) |

The source review followed the merge diffs, current entry points, owners and their tests through architecture, the current project references and the three original audit reports. [Architecture](ARCHITECTURE.md) · [README](../README.md) · [Summary](../Summary.md) · [Changelog](../CHANGELOG.md) · [Roadmap](ROADMAP.md) · [Audit 1](../AUDIT_REPORT_1.0.md) · [Audit 2](../AUDIT_REPORT_2.0.md) · [Audit 3](../AUDIT_REPORT_3.0.md)

| Priority | Candidate change |
| --- | --- |
| REUSE · 70% | Existing AMMs, strategy, agents, Risk Firewall, final authorization, execution, accounting, market-data owners, worker, portfolio, Replay and browser/Redis/financial probes. |
| ENHANCE · 20% | Test-only dependency remediation for the reproduced pytest audit finding, current documentation and release instructions. All changes are confined to verification, test tooling and documentation. |
| ADD · 10% | Mixed-owner measurement extends the existing opt-in Phase 18.7F provider probe. Add the compact evidence, this report and the release runbook. Zero new production modules. |

## F1 · Financial and authority acceptance

**CONDITIONAL**. The candidate, PR #102 and the PR #99 and #100 merged trees ran the same `phase187_paper_compatibility.py` capture. Both capture files matched with `cmp`. Each uses 40 frames, 7/13 bps fees, two-second funding, a fixed receipt/admission clock, 60-second catalog validity, Core DOGE and HIP-3 `xyz:GOLD` fixtures. The probe covers full admission and result serialization under default, hypothetical and source-constrained risk. [Probe](../backend/tests/phase187_paper_compatibility.py) · [Compatibility evidence](acceptance/phase187f/compatibility.json)

| Evidence category | Pairs | SHA-256 |
| --- | ---: | --- |
| Controlled equivalent · standard | 38 | `83cfb57fec42efdc9f64114b7891881752da53a904300e7ad4439859445fcf55` |
| Controlled equivalent · asset-aware | 18 | `257c8d7ec9d510544b2d45302e3be10467f486eb4a1d53a4d63e9d06d8bf1ec9` |
| Historical attestation limitation · PR #100 standard | 38 | `b564ad46f264f8b8295feb5dc59d4c44a3e97b2302769663aaf94dbd5fbce65e` |
| Historical attestation limitation · PR #100 asset-aware | 18 | `5fa22910e35da8655a6f99df148cc809a2d6043ba090c2ae051ba479e64cf47f` |
| Exactly reproduced · native combined | 39 datasets and three captured markets | `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad` |

The PR #100 description and both implementation commits, tracked history and checked-in acceptance artifacts and GitHub discussion were checked for the original generator and exact serialized input envelope. The discussion has zero entries and the artifacts provide broad inputs, captured counts and published hashes. The exact clock, validation envelope and aggregate serialization are unavailable. The controlled comparison therefore establishes equivalent behavior under the fixed input envelope. The two original aggregate hashes remain historical attestations with exact reproduction open. Financial outputs were taken from the historical and candidate trees. [PR #100](https://github.com/btorressz/hyperamm/pull/100) · [Published hash record](PHASE18_6_HARDENING_ACCEPTANCE.md#verification)

The published native probe reproduced dataset matrix `e97b675557f104e1ad2bfe3713133db88c20dbc2eece9e71a3d7ed4467f05abe`, portfolio reconciliation `e51a1579d079429ed6ee123e120a7d46bc38f4ebd73e7c90283ff97ab53c9417` and the combined digest. The run reconciles fees, funding, inventory, native result/receipt and order, ledger, AMM and risk fingerprints. The Decimal oracles independently cover both AMMs, quoted and authorized fills, realized and unrealized P&L, equity, reservations and native allocations and stress. [Native reproduction](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility) · [Financial oracle](../backend/tests/test_phase187d_financial_invariants.py) · [Portfolio oracle](../backend/tests/test_phase176_acceptance.py)

Regime, Toxic Flow, Execution Quality, Liquidity Quality and Perp Crowding remain bounded supervisory agents. Predictive Adverse Selection stays in SHADOW. Advisory Quote Economics, Funding/Basis and Market Eligibility have read-only authority. The qualified native and Core/HIP-3 regressions verify separate receipt, source, market and generation identity, authority preservation during partial advisory failure, Firewall HALT and concrete `FinalQuoteAuthorization` before reconciliation. Native portfolio allocation remains restricted to BTC/ETH/SOL. No financial or authority regression was reproduced. [Authority oracle](../backend/tests/test_phase187d_authority_acceptance.py) · [Market matrix](../backend/tests/test_phase187_market_regression.py)

## F2 · Public provider and resource acceptance

**CONDITIONAL**. An earlier execution on the same production tree in PR #104 covered only discovery and summaries. It completed 1,801.006 seconds, made 574 Mainnet calls, measured a 520-weight rolling-minute peak, and rejected 29 retired generations. The mixed-owner run below adds concurrent advisory and native observations. [Earlier run evidence](https://github.com/btorressz/hyperamm/blob/78b68b4b1fbe7b232a6ca55364128e28e847c1e8/docs/acceptance/phase187f/provider-soak.json)

Fresh official Mainnet discovery returned HTTP 200, 11 namespaces and 568 records. The same public path verified Core BTC, ETH, SOL, DOGE and discovery-selected HIP-3 `xyz:AAOI` and `io:AAPL`. The summary receipts carry qualified identity, catalog and metadata bindings, provider quote/base mark, hourly funding and local receipt age. The upstream context carries no independently verified event time. These observations remain separate from explicit synthetic PAPER inputs. [Provider evidence and normalized receipts](acceptance/phase187f/provider-soak.json)

The actual workload ran **1,800.000 seconds** at a nominal 20-second cadence and recorded 90 polls. It saw 27 catalog generations and 77 complete six-row summary polls. An immediate repeat reused the same observation receipts. Catalog-bound requests returned 13 HTTP 409 responses during generation transitions. The separately run native point check received BTC/ETH/SOL L2 and active-asset context, completed one controlled reconnect in a 21.807-second run and cleaned up its owned SDK resources. The sustained run controlled a disconnect from generation 1 and reacquired fresh native evidence in generation 2. All three markets were simultaneously fresh at 36/90 sampled polls, with 54 polls without complete live freshness and 27 SDK generation starts overall. This is conditional sustained availability. The run does not establish the cause of every stream gap. After consolidating both scopes into the existing runner, an 85.001-second mixed check and a catalog-only point check passed and returned the expected cleanup and Testnet cap evidence.

| Provider owner | Starts | Info weight | Maximum call seconds | Transport outcomes |
| --- | --- | --- | --- | --- |
| advisory | 3 | 43 | 0.7179 | SUCCESS 3 |
| discovery | 351 | 7020 | 2.252 | SUCCESS 351 |
| native_sdk | 144 | 1368 | 1.69 | SUCCESS 144 |
| summaries | 189 | 3780 | 2.2211 | SUCCESS 189 |

Combined measured Info weight was **12,211** across **687** starts and at most **779 per rolling minute**. The workload retained up to 24 summary captures in its samples. Peak sampled RSS was 125,512 KiB, 48,120 KiB above the pre-lifespan sample. The separately reported process peak RSS was 125,884 KiB. The RSS difference measures the combined app workload and instrumentation. Samples reached 11 OS threads, 5 in-loop tasks and 6 SDK subscriptions. Shutdown released all counted SDK sessions/handles, native and discovery worker threads, summary tasks and cached captures. No fresh native components remained. The offline fixture separately covers queued local stream consumers and late callback retirement. [Time series, transport outcomes, latency and cleanup](acceptance/phase187f/provider-soak.json)

The deterministic summary/provider suite exercised 1–13 keys, three simultaneous namespace acquisitions, 24 retained captures, 15-second reuse, 30-second receipt age, five-second manual refresh minimum, 24 starts per rolling minute, six-second request wait and 30-second HTTP 429 backoff. It exercised timeouts, partial and malformed payloads, auth/source substitutions, canceled waiters, stale generation retirement and in-flight summary shutdown. The Explorer uses a 20-second refresh while visible. Discovery retains the 64-namespace and 4,096-record cap. The separate OFFLINE SDK fixture soak ran for **30.2374 seconds**, completed 284 cycles with queue peak 8, retained 32 history points per market and left zero SDK resources, consumers, owner threads or tasks. [Summary tests](../backend/tests/test_phase186h_market_summaries.py) · [Provider resilience](../backend/tests/test_phase187_provider_resilience.py) · [Existing offline runner](../backend/tests/phase155b_soak_runner.py)

**Shared IP budget.** The summary owner may start 24 acquisitions per rolling minute, or 480 weight. Core and each discovery namespace cost one metadata request. An inventory of 64 namespaces plus inventory and spot metadata can imply 66 × 20 = 1,320 weight within the collection deadline if responses are fast enough. At the observed 11 namespaces a complete refresh used 260 weight. Advisory current context and history use ordinary Info weights, with per-history response pagination weight and low-weight L2. An observed three-operation advisory used 43 weight. Native REST needs metadata, L2 and context for each requested market. The native socket's bootstrap and reconnect can also request this data. A bootstrap for three markets typically starts with 20 + 3 × 2 + 20 = 46 Info weight before recovery retries. Six WS subscriptions per open native client and outbound socket maintenance are tracked separately from REST weights. No shared limiter exists across these owners and independently issued requests can exceed the documented 1,200 IP weight/minute. The probe uses a lower voluntary stop ceiling for its aggregate Info traffic. This supports the measured workload and leaves arbitrary combined traffic unaccepted. The Phase 17.6 browser run also issued its separate native metadata lookup during the soak. That call is outside the probe's counters. Ambient IP traffic was not measured. [Provider rate policy](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits) · [Discovery owner](../backend/app/market_data/market_universe_discovery.py) · [Summary owner](../backend/app/market_data/market_summaries.py)

**Testnet.** An official Testnet inventory response contained 288 entries including Core. Catalog admission returned HTTP 503 with `CATALOG_CAPACITY` and zero records. The inventory failed before DEX fan-out. A direct official Testnet Core context separately supplied matched BTC, ETH and SOL mark, oracle and funding observations. Keep the 64-namespace policy from PR #102. A Core response does not qualify a full Testnet catalog or a catalog-backed summary. [A–C capacity decision](PHASE18_7ABC_ACCEPTANCE.md#testnet-capacity-decision)

| Provider gate | Decision |
| --- | --- |
| Mainnet Core/HIP-3 discovery | **PASS** · actual official Mainnet application route. |
| Mainnet mark and funding | **PASS** · six qualified current rows with observed marks and rates in actual repeated summary responses. |
| Mainnet native stream | **PASS** · point-in-time fresh native REST/WS and controlled reacquisition. See sustained recovery measurements. |
| Sustained provider operation | **CONDITIONAL** · selected bounded public read-only workload. |
| Deterministic resilience | **PASS** · limits, rejection, stale retirement, retry and shutdown fixtures. |
| Testnet Core context | **PASS** · direct public observation. |
| Full Testnet catalog | **BLOCKED** · existing capacity policy enforced before partial publication. |

## F3 · Browser, platform and accessibility acceptance

**CONDITIONAL**. The Phase 18.7 harness shares the existing Phase 18.6 runner with engine selection. Chromium uses native CDP zoom. Alternate-engine launches followed the supported Playwright install path. Firefox and WebKit downloads returned 403 on the supplied CDNs and harness launches reported missing matching executables. Both checks are **BLOCKED**. Native Safari requires a separate run on its own platform. Native Safari/macOS, Windows browsers, physical mobile browsers, VoiceOver and NVDA are **NOT RUN**. Browser viewport emulation remains evidence for layout only. [Browser matrix](acceptance/phase187f/browser-matrix.json)

Fresh Chromium 151 on Linux passed 14 workflow groups, 39 route/mode checks, 71 viewport measurements and a real 200% zoom check in 115.298 seconds. The route/mode matrix covered canonical navigation, refresh and back/forward. The separate harnesses exercised Explorer, standard and asset-aware PAPER, three advisories, all seven native subsets through financial fixtures, native portfolio and Replay/Comparison with local data. Axe-core reported zero automated violations in 26 scoped scans and zero in the separate Audit 3.0 scan set of 32 route/viewports plus zoom. The Phase 18.7 scans surfaced seven contrast and two Replay table review entries. Sampled text minimums were 8.45:1 and 6.71:1 for the two harnesses. The first two Chromium attempts using Playwright 1.65.2 timed out on the Replay button and active navigation after reload, respectively. The isolated Replay workflow and the full matrix passed with the Phase 18.7D–E Playwright 1.62.0 version. The first Audit 3.0 startup timed out while the frontend install was also running. The serial rerun passed. An unchanged later run passed all 16 legacy Replay workflows. Browser captures were kept as scratch verification material. [Browser evidence](acceptance/phase187f/browser-matrix.json)

Review of remaining automated manual items covers the ask/bid row groups and scoped order-book columns, financial tables with bounded horizontal scrolling, sampled contrast, chart text alternatives and keyboard. Replay exposes named price series, current frame prices in text and a keyboard-reachable order book. The retained book's two `<tbody>` groups each have a scoped `rowgroup` label and three scoped column headers. The workflow checks the tab order, focus containment and return, risk-table scrolling and explicit submission, retirement and recovery statuses. The diagnostic or rendered status uses the existing polite live region for Replay and comparison outcomes. Actual assistive-technology announcement and chart exploration are separately pending. [Order-book semantics](../frontend/src/components/replay/ReplayOrderBook.tsx) · [Replay price labels](../frontend/src/components/replay/ReplayMarketChart.tsx) · [Research status regions](../frontend/src/components/research/ResearchRunStatus.tsx)

## F4 · Operational safety and recovery

**PASS** for the bounded local safety and in-process recovery scope. Two isolated Uvicorn processes used loopback and one worker. Both delivered DEMO/PAPER terminal WebSockets, rejected Host, Origin and forwarding headers, returned 413 for oversized requests and 422 with sanitized validation, and closed connected terminal sockets with 1012 on graceful shutdown. The second process produced new process and session identities. The production lifespan's shutdown, summary generation retirement, subscriber/SDK/worker cleanup, canceled PAPER waiters, admission contention, source expiry and manual-kill preservation are covered by scoped application and deterministic tests. The PR #102 summary shutdown correction and PR #103 Replay row-group fix remain in the verified tree. [Operational evidence](acceptance/phase187f/release-gates.json)

A physical Redis **8.0.2** instance on loopback passed seven checks in **0.47 seconds** with redis-py 6.4.0. Tests covered PING and health, shared Pub/Sub terminal identity and subscriber cleanup, real coordinated PAPER admission, Lua capacity/lease release, TTL cache and heartbeat, outage rejection, recovery preserving manual kill and application shutdown. Fakeredis remains fixture evidence in the wider suite. Redis process recovery verifies current-process cooperation. Backend restart retires the old session. There is no durable restoration protocol for interrupted research, operational orders, fills, positions, accounting state or kill state. [Physical Redis harness](../backend/tests/phase155a_redis_acceptance.py)

**SIGNED TESTNET — NOT RUN.** The no-signing fixtures verified native wire normalization, concrete authorization, unknown-order and fail-closed behavior. The candidate leaves live observations independent and signing disabled. Operator authorization, dedicated Testnet credentials and real venue acknowledgment/reconciliation require a separate gate. HIP-3 signing, Mainnet trading and remote multi-user operation are outside the release scope. [Operator-controlled TESTNET prerequisites](PHASE18_RELEASE_RUNBOOK.md#operator-controlled-signed-testnet-gate)

## F5 · Installation, dependency and release smoke

**PASS**. A fresh Python 3.12.14 environment installed the checkout's wheel with test, Redis, ML and Yahoo extras. `pip check` passed. Node 24.19.0/npm 11.9.0 installed the locked frontend dependencies, typechecked and built the Vite production bundle. Exact dependency versions and lockfile hash are recorded. The Python manifest allows range resolution and build dependency changes, so this run does not establish deterministic Python installation. [Environment evidence](acceptance/phase187f/environment.json)

The unmodified runtime wheel's loopback startup used `MARKET_DATA_MODE=DEMO`, `EXECUTION_MODE=PAPER`, `ENABLE_HYPERLIQUID_TESTNET_ORDERS=false`, `MARKET_UNIVERSE_ENABLED=true`, and `MARKET_UNIVERSE_NETWORK=MAINNET`. Health, terminal socket, risk and final-authorization endpoints, agents, Vault and Logs passed. Real local 12-frame PAPER workers returned simulated receipts for Constant Product and Concentrated Liquidity. The sustained read-only workstream exercised actual discovery and summaries from the same app owners with public native observations independently enabled. A separate smoke against the production Vite assets passed all three modes, Risk, Vault, Logs, and an actual local PAPER request with zero page errors. Earlier PR #104 evidence also verifies the unmodified browser rendering sampled official BTC mark and funding and a separately enabled native observer. The browser fixtures use actual local workers and cover all three modes, guided and asset-aware PAPER, the native portfolio and Replay with admitted test data. [Smoke results](acceptance/phase187f/release-gates.json)

| Tool check | Result |
| --- | --- |
| Locked `npm audit --omit=dev` | Zero findings in the production tree. |
| Locked `npm audit` | Zero findings including development dependencies. Vite remains 7.3.8 and picomatch remains 4.0.7. GitHub has withdrawn `GHSA-fc5q-39xc-vjpf`. [Withdrawal record](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) |
| Installed Python dependency scan | The original environment scan returned 14 entries for two packages, representing six unique pip advisories and one unique pytest advisory after deduplication. pip 25.0.1 was the venv bootstrap tool. pytest 8.4.2 was test-only and affected by `GHSA-6w46-j5rx-g56g`. The fresh candidate used pip 26.3, pytest 9.1.1 and pytest-asyncio 1.5.0, and the resolved Python scan reported zero findings. Pytest 9.2 was first tried and reproduced teardown errors on Starlette `State` fixtures when its revised `MonkeyPatch` restored dynamic attributes. The compatible `>=9.0.3,<9.2` test-only range includes the upstream security fix and avoids that fixture incompatibility. The pytest-asyncio range now permits pytest 9. The local HyperAMM package is outside the package index. The scan covers the installed third-party distributions. [Pytest advisory](https://github.com/advisories/GHSA-6w46-j5rx-g56g) |

## Audit 3.0 finding reconciliation

| Audit finding | Disposition and evidence boundary |
| --- | --- |
| A1-001 · SDK wire requests not bound to final authorization | **PARTIAL**. Concrete native quote membership and wire-equivalent checks pass locally. Signed CREATE/KEEP/REPLACE/CANCEL and adverse reconciliation are open. |
| A1-006 · Duplicate resting slot exposure undercounted | **PARTIAL**. Native exposure, duplicate/orphan, partial and uncertain-order fixtures pass. Actual venue duplicate/orphan, partial-fill and cancel/submit races are open. |
| A1-003 · No demonstrated public SDK reconnect loop | **PARTIAL**. Actual read-only native reconnect and deterministic operational recovery checked. Operational live feed fault and mode-switch soak remains open. |
| A1-004 · Teardown drops Info without socket disconnect | **PARTIAL**. Local shutdown and scope-bounded read-only SDK closure exercised. Repeated operational mode changes and cross-platform teardown under actual faults remain open. |
| A1-009 · Local APIs lack remote operator authorization/admission | **PARTIAL**. Loopback peer, authority headers, write caps and local fail-closed behavior pass. Remote authentication, RBAC, TLS/proxy and operator identity are outside scope. |
| A1-016 · Quant scores need sampling/numeric calibration | **PARTIAL**. Guarded finite arithmetic and SHADOW behavior are tested. Empirical cadence, thresholds, strategy performance and model calibration remain open. |
| A1-017 · Unused NumPy and compatibility duplication | **PARTIAL**. Fresh resolved installs and inventories captured. Dependency policy and deterministic Python resolution remain open. |
| A2-003 · Collapsed ticks lack effective-price/operational policy | **PARTIAL**. Exact quantities, executable price, stable slot identities and exposure pass. Venue cost, cancel/churn and consolidation policy remain open. |
| A2-005 · Normal declared test-extra teardown failure | **PARTIAL**. Local Linux lifespan and physical Redis pass in the exercised configurations. Native macOS and Windows lifecycle remains open. |
| Phase 16.6B · Durable job lifecycle and recovery | **BLOCKED**. Fresh session after restart demonstrated. Interrupted research and financial recovery needs a separately designed and verified protocol. |
| Historical authentication and licensing | **NOT RUN**. Fixture and local content integrity and provenance pass. Original source authenticity and usage rights remain unverified. |
| Alternate reference sources | **NOT RUN** for prolonged public RedStone, CoinGecko, Yahoo and live Kraken quorum. Existing fixture scope carries forward. |
| Redis operational matrix | **NOT RUN** for multi-host failover, extended outages, and other versions/platforms. |
| Historical picomatch development advisory | **Withdrawn upstream**. The locked dev/production audits and advisory status are recorded above. |

The exact historical descriptions and qualified closures remain in Audit 3.0 and PR #84. [Audit 3.0](../AUDIT_REPORT_3.0.md) · [Remediation acceptance](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md)

## Exact regression and reproduction record

| Check | Executed result |
| --- | --- |
| Merged backend with existing pinned major test range | 3,976 passed, 0 failed, 0 skipped, 0 errors, 5 warnings in 921.89 s |
| Release candidate backend | 3,976 passed, 0 failed, 0 skipped, 0 errors, 5 warnings in 774.01 s |
| Focused Phase 17, Phase 18, native observers and Audit/authority suites | 2,049 passed, 0 failed, 0 skipped, 0 errors, 5 warnings in 582.59 s |
| Focused D–E economic/authority cases | 14 cases included in the focused and full runs. Seven qualified PAPER/authority cases and seven native portfolio subset cases. |
| Frontend Node tests | 949 passed, 0 failed, 0 skipped in 31.49 s |
| Locked install / typecheck / production build | PASS · 3.993 s / 14.590 s / 17.707 s wall. |
| Frontend tool notices | 15 TanStack client directive notices and 1 bundle-size notice. Test output includes test storage notices. |

Focused reruns and oracle cases overlap the full suite and are reported separately. Browser workflows and axe counts are not counted as Node tests. Tests and tools ran against the local release candidate on Debian 13 x86-64. The environment, exact commands, elapsed values, warnings and classified skips are linked below. [Regression evidence](acceptance/phase187f/regression.json) · [Reproduction runbook](PHASE18_RELEASE_RUNBOOK.md#reproduce-release-verification)

<a id="release-readiness-matrix"></a>

## F6 · Readiness matrix and rollout decision

| Capability | Decision | Evidence scope |
| --- | --- | --- |
| Local DEMO/PAPER terminal | **PASS** | Single operator, one worker, loopback Linux and isolated release smoke. |
| Core/HIP-3 read-only discovery | **PASS** | Fresh actual Mainnet application catalog. Separate Testnet cap. |
| Actual mark/funding summaries | **PASS** | Fresh local-receipt Core and HIP-3 mark/funding observations. |
| Sustained provider operation | **CONDITIONAL** | 30-minute target exercised. See reconnect gaps and shared IP scope. |
| Generalized single-market PAPER | **PASS** | 38 controlled pairs plus qualified admission, precision and local workflow. |
| Asset-aware PAPER | **PASS** | 18 controlled pairs plus asset policy, source-constrained risk and browser receipt. |
| Constant Product and Concentrated Liquidity | **PASS** | Real local PAPER smoke and independent financial oracles. |
| All nine agents | **PASS** | Six supervisory including SHADOW and three observational advisory agents. |
| Risk Firewall and final authorization | **PASS** | Decimal, actual local fail-closed checks and concrete no-signing authority. |
| Native BTC/ETH/SOL portfolio | **PASS** | Published digest, 39 fingerprinted datasets, seven subsets and modeled stress. |
| Historical Replay | **PASS** | Generated admitted fixtures and content provenance. Source authenticity/licensing remain open. |
| Starter/Pro/Institutional | **PASS** | All 13 routes in each presentation mode. |
| Chromium on Linux | **PASS** | Executed workflows, responsive checks and actual CDP zoom. |
| Playwright Firefox on Linux | **BLOCKED** | Supported binary download was denied. |
| Playwright WebKit on Linux | **BLOCKED** | Supported binary download was denied. |
| Native macOS/Safari, Windows browsers and physical mobile browsers | **NOT RUN** | See per-platform outcomes in browser evidence. |
| Manual accessibility with assistive technology | **NOT RUN** | Local semantics, contrast and keyboard checked. VoiceOver and NVDA remain open. |
| Physical Redis | **PASS** | Loopback Redis 8.0.2, ephemeral coordination and recovery. |
| Signed TESTNET | **NOT RUN** | Operator-controlled authorization and actual venue reconciliation are separate. |
| Full Testnet catalog | **BLOCKED** | 288 namespace entries exceed the enforced cap of 64. |
| Durable recovery | **BLOCKED** | Requires a separately designed persistence and recovery protocol. |
| HIP-3 signed execution | **OUT OF SCOPE** | No expanded trading authority. |
| Mainnet execution | **OUT OF SCOPE** | Public Mainnet evidence is read-only. |
| Remote multi-user production | **OUT OF SCOPE** | Local peer and Origin/Host boundary. Remote admission and security require separate design. |

**Phase 18 disposition — PASS for bounded local research.** Public observations are time-bounded and lose eligibility when stale. The acceptance gate for sustained operation considers observed service degradation and aggregate traffic limits. Follow-up milestones are operational provider/reconnect acceptance under representative shared traffic, alternate-browser/native platform and assistive-technology sessions, deterministic Python packaging, operator-controlled signed TESTNET reconciliation, authenticated historical source review and separately designed durable recovery. Review the exact original PR #100 input envelope and generator if they become available. [Runbook and rollback](PHASE18_RELEASE_RUNBOOK.md) · [Consolidated gates](PHASE18_7_ACCEPTANCE_MATRIX.md)
