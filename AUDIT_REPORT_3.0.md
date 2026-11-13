# HyperAMM — Audit Report 3.0: Full System, Security, Correctness & Market Readiness

## 1. Executive Summary

**Audited repository:** `btorressz/hyperamm`, main commit **`bac4225da3d678c262b0815e4fe5025cbf4c4bca`** (Phase 17.6, PR #80). Audit date: **2026-11-12, America/Los_Angeles**; execution timestamps span November 12–13 UTC. This is an independent audit-only change. Production source, tests, dependencies, lockfiles, configuration and both previous reports are unchanged. No signing was activated and no live or TESTNET orders were submitted.

**Verdict: CONDITIONAL for bounded local research and PAPER use; BLOCKED for production/live execution and broad-market/HIP-3 claims.** The mathematical compiler, final economic authorization, isolated research engine and evidence-retirement contracts have substantial executable support. They do not establish venue lifecycle acceptance, durable financial recovery, calibrated predictive performance or remote operator security.

**No CRITICAL issue was established. Eight new findings were confirmed: one HIGH, six MEDIUM and one LOW.** The HIGH finding is the installed Vite 7.3.6 dependency's published advisory, including a Windows-specific command-injection condition; this Linux audit did not demonstrate that exploit or a HIGH trading-authorization defect. The MEDIUM findings concern modeled-fill classification, stale-context configuration errors, stale SHADOW features, HIP-3 precision classification, stress-preview feasibility and Kraken heartbeat handling. Accessibility and narrow financial tables form the LOW finding. See section 14 for exact scope and reproductions.

**Nine previous findings remain unresolved as PARTIAL:** seven A1 findings (001, 003, 004, 006, 009, 016, 017) and two A2 findings (003, 005). Across all 32 prior IDs, 23 are CLOSED within their original scope, including five explicitly acknowledged policy/design boundaries; nine are PARTIAL. No original finding was established as wholly OPEN or REGRESSED. CLOSED does not convert an acknowledged limitation into production capability.

Fresh execution produced **3,302 backend passes, one optional-ML skip and two warnings; 788 frontend passes; successful typecheck and production build**. Twenty fresh normal-install lifecycle subprocesses passed all 560 checks. Current repository Chromium harnesses passed 19 portfolio workflows and 21 replay/comparison workflows; an older replay harness failed because it no longer selects the required tab. That failure is recorded, not repaired or counted as a pass. An additional route audit covered 13 pages at two widths. All **118 historical acceptance screenshots** were decoded and visually inspected in contact-sheet overviews; representative images received larger inspection. Overview inspection cannot establish small-text correctness or accessibility. Current browser accessibility checks confirmed defects.

Actual external evidence includes a short read-only Hyperliquid BTC/ETH/SOL REST/WebSocket/reconnect/cleanup pass, a fresh Kraken ETH/USD observation, and seven physical Redis checks against Redis 7.4.11. RedStone HTTP was blocked by a proxy error. RedStone Live, keyed CoinGecko, Yahoo acceptance, macOS, long-running transport/failover soak, signed TESTNET and production were not accepted.

The principal barriers to broader markets are explicit three-market contracts, unqualified instrument identities, metadata-loader restrictions, the builder-perpetual precision defect, USDC-only portfolio accounting, fixed synthetic profiles and provider mappings, and unaccepted venue/risk calibration. Raising an enum or discovering metadata would not discharge those barriers.

## 2. Audit Baseline and Methodology

### Baseline and environment

`origin/main` was fetched before branching, and GitHub's remote main SHA was checked independently with `git ls-remote`. The branch `audit/report-3-0` starts at the SHA above; main's commit timestamp is `2026-11-12T16:23:01-08:00`. All source references and results below refer to that frozen baseline, not a future main.

| Item | Observed audit environment |
|---|---|
| Host | Linux 6.18.57, x86_64; local isolated processes, no Docker |
| Python / install | CPython 3.12.14; fresh editable `backend[test,redis]` virtualenv and a separate fresh `backend[test]` virtualenv |
| Key Python dependencies | official `hyperliquid-python-sdk` 0.24.0; FastAPI 0.162.5; Starlette 1.10.0; Pydantic 2.14.3; httpx 0.28.1; pytest 8.4.2; pytest-asyncio 0.26.0; websocket-client 1.9.2; websockets 15.0.1; NumPy 2.5.4 |
| Redis clients / fixtures | redis 6.4.0 with explicit redis extra; normal test install resolved redis 8.1.0 through fakeredis 2.40.0; physical server 7.4.11 built in scratch |
| Frontend | Node 24.19.0; npm 11.9.0; clean `npm ci`; React/react-dom 19.3.0; TypeScript 5.9.3; Vite 7.3.6; Zustand 5.0.15; TanStack Query 5.104.1; lightweight-charts 5.2.1 |
| Browser | Chromium 151.0.7922.173 through installed Playwright; scratch axe-core 4.14.0 |
| Optional tools | sklearn/offline training and Yahoo extras not installed; no signing credentials used |

Python dependencies are range-resolved rather than a committed fully resolved environment lock. Version records matter: a later clean install can differ. Frontend lockfile was honored and unchanged. Browser/test fixtures used private scratch directories and explicit generated-source labels. Operational browser checks used DEMO data, PAPER execution, signing disabled and references/Redis disabled unless the particular acceptance runner enabled them.

### Inventory and inspection coverage

The baseline has **913 tracked files**. A full tracked-file inventory recorded byte counts, hashes and line counts; Python files were AST-parsed and their definitions indexed. Backend application inventory: 170 Python files plus 12 local README files, 21,800 lines in that tree. Frontend source: 171 files (103 TSX, 46 TS, 21 CSS, one JSON), 24,893 lines. Backend tests/helpers/fixtures: 136 files, including 115 test modules, 23,325 lines. Frontend tests: 76 files. Documentation: 326 files, including 62 Markdown and 120 PNG files; 118 PNGs are acceptance screenshots.

The review combined repository-wide content/identity searches and inventory, source tracing of each subsystem's entry points and trust boundaries, direct inspection of financial and lifecycle implementations, both prior reports including their remediation addenda, configuration/manifests/fixtures, native tests, independent counterexamples, browser execution and actual image pixels. `README.md`, `CODEBASE.md`, `Summary.md`, `CHANGELOG.md`, module READMEs and phase acceptance documents were compared with current source. Automatic inventory is file coverage, not proof that every branch is correct; no formal verification, branch-coverage percentage or exhaustive vulnerability guarantee is claimed.

Evidence is distinguished throughout:

| Label | Meaning |
|---|---|
| Source / native test | Current implementation inspected or current repository tests executed |
| Counterexample | Audit-created scratch assertion reproduces current undesirable behavior |
| Fixture browser / SDK | Real local engine/browser/client with explicitly fabricated upstream records or fault injection |
| Public read-only | Actual unauthenticated provider traffic, no signing or orders |
| Physical Redis | Actual server process and real network/client behavior |
| Historical | Existing acceptance document/image; not a current execution result |
| NOT RUN / BLOCKED | No successful acceptance; reason stated |

Scratch scripts, logs, dependency installations and new screenshots live under ignored `work/`; they are not part of the commit. The report embeds the six code counterexamples and exact runner commands so its core evidence does not depend on uncommitted artifacts. Historic screenshot links point to unchanged tracked images. Tests count assertions executed under their own fixtures, not independent real-world financial experiments.

## 3. Repository-Wide Architecture

| Area / current source | What executes and authority boundary | Verification and remaining boundary |
|---|---|---|
| `backend/app/main.py`, `config.py`, `dependencies.py`, `runtime.py` | FastAPI lifespan owns one runtime; serialized transitions own market/reference/Redis/terminal resources. Settings separate DEMO/LIVE data from PAPER/guarded TESTNET execution. | API/lifecycle/isolation suites and current browser controls. Single-process local deployment; distributed Redis coordination does not reconstruct financial state. |
| `market_data/`, `references/` | Material market snapshots, bounded history, perp policy and role-aware reference consensus feed strategy. Later read-only multi-market streams have separate bounded transport ownership. | Material identities and timestamps are stronger than price-history dedup. External-provider health/availability remains independently significant. |
| `amm/`, `strategy/` | Decimal virtual reserves and incremental reserve-delta curves compile to logical CLOB slots; inventory, adaptation and perp/reference transforms produce candidates. | Native/adversarial tests and independent invariant checks. Base-quantity budget is not collateral TVL; quantitative thresholds are not calibrated guarantees. |
| `agents/`, `research/ml/` | Six evidence-driven agents; supervisor can widen/reduce permitted candidates. Predictive model is SHADOW, with no quote authority. Offline training is optional. | Tests cover conservative transforms/provenance. Stale SHADOW features and modeled-fill classification are confirmed new defects. |
| `risk/`, `execution/`, capital/vault portions of runtime | Final normalized economics, capital reservation, fingerprints and concrete request membership precede runtime-managed creation. Unknown/cancel failure halts replacements. | Fixture wire normalization and races tested; no signed venue acceptance. Internal classes are Python interfaces, not an authorization sandbox against arbitrary code execution. |
| `accounting/` | Signed inventory, average cost, realized/unrealized PnL, fees, funding and bounded append-only in-memory ledger; atomic idempotent fill ingestion. | Native accounting tests. Partial TESTNET evidence and restart loss remain explicit; not custody or external cash-flow reconciliation. |
| `simulation/`, `research/` | Fresh isolated domain stack per deterministic run; bounded optimizer, explicit candidate allowlist and dataset identities. | Same quote/risk/accounting code executes. Synthetic crossing/latency assumptions are not venue queue calibration. |
| `research_replay/`, `research_comparison/` | Private content-identified historical catalog, source/receipt/segment contracts, native replay and comparison eligibility. | Current generated-fixture browser and native tests. Provenance integrity is not authentication or licensing of original market history. |
| `portfolio_research/` | Exact shared allocation, sequential native per-market engines, accounting aggregation, temporal classes, six real input stresses, bounded terminal charts. | Source/engine provenance and conservative incomplete-history behavior verified; arbitrary shock feasibility has a gap. |
| `infrastructure/` | Shared research worker, Redis optional health/cache/leases/PubSub, local HTTP/WebSocket boundary, bounded transport diagnostics. | Native/fakeredis and current physical Redis tests. No remote authentication, durable worker receipts or financial recovery. |
| `terminal/`, `api/` | Cached canonical observation, bounded fanout and process/session identities; explicit mutating controls and read-only research endpoints. | Observational GETs and research isolation tested. One running research job can occupy the local worker until actual completion. |
| `frontend/src/api`, `hooks`, `stores`, `types`, `utils` | Strict runtime validation, source-age/session retirement, request ownership and stale-result suppression; browser does not sign or normalize authoritative orders. | 788 native tests plus real Chromium. Session retirement is bounded local memory, not authenticated replay protection. |
| `frontend/src/pages`, `components` | 13 routed pages; replay/optimizer, Research Vault and market-comparison tools nested in relevant workspaces. | All routes exercised at desktop/mobile widths. Missing language, contrast, focusable overflow and dense mobile financial tables remain. |

Authority flow is market/reference evidence → AMM/inventory/adaptation → optional supervisory restriction → risk/firewall → venue normalization → independent final limits/capital authorization → concrete request membership → adapter. Research runs create isolated copies and never receive the operational signer. Terminal publication observes this state; it does not become authority merely because a socket frame is fresh.

Architecture debt includes separate operational and multi-market transport implementations, repeated canonical-fingerprint/contract validation code across domains, tightly coordinated runtime state, and a broad frontend root subscription. The duplication has different identity/version contracts; a casual consolidation could break provenance. No measured financial bypass was established from that debt.

## 4. Audit 1.0 Findings Crosswalk

Original terminology and severities below are preserved from [Audit 1.0](AUDIT_REPORT_1.0.md), including `HIGH-MEDIUM` and `MEDIUM / HARDENING`; these are not silently converted to A3 severity labels. `CLOSED (acknowledged)` means the originally requested policy/documentation treatment exists, not that the limitation disappeared. Current test names refer to suites rerun in the full backend/frontend executions in section 16.

| ID / original severity | Original problem | Current implementation | Current evidence | Disposition | Specific remaining work |
|---|---|---|---|---|---|
| A1-001 / HIGH | SDK wire requests not bound to final authorization | `execution/hyperliquid.py::normalize_order_request`, order manager and runtime authorize normalized economics, concrete ladder membership and wire round-trip equality. | `test_phase8_authorization.py`, `test_phase122_amm_hardening.py`, execution tests; current independent final-price inspection. | **PARTIAL** | Code repair supported for supported native markets; actual signed TESTNET CREATE/REPLACE/cancel, partial-fill and uncertainty acceptance remains NOT RUN. A3-004 is a separate broader-market precision limitation. |
| A1-002 / HIGH-MEDIUM | Changed equal-sequence L2 evades authority identity | `market_data/service.py::_accept` maintains monotonic material identity separately from chart sampling/dedup. | Integration/provenance/authorization tests cover changed content at equal exchange sequence/time and old authority rejection. | **CLOSED** | No original defect reproduced; continue material-content identity regression coverage. |
| A1-003 / HIGH-MEDIUM | No demonstrated public SDK reconnect loop | `market_data/hyperliquid.py` owns reconnect/resubscribe/health/fresh recovery; newer `live_streams.py` has separately owned generations and subscriptions. | Native reconnect tests; actual short multi-market public reconnect pass in section 16. This is not a soak of every operational-adapter transition. | **PARTIAL** | Long-running operational adapter disconnect/resubscription/freshness and stop/switch soak under real network faults. |
| A1-004 / HIGH-MEDIUM | Teardown drops Info without socket disconnect | Operational adapter retains owned Info through disconnect; live-stream client disconnects and bounds cleanup. | Native lifecycle/SDK cleanup tests; public multi-market runner ended with zero owned threads/tasks/subscribers. | **PARTIAL** | Repeated real operational mode switches, exceptional start and shutdown soak across supported platforms. Short acceptance does not establish leak absence indefinitely. |
| A1-005 / HIGH-MEDIUM | Unbounded execution history and rescanning | `execution/fills.py`, `order_manager.py`, incremental runtime/accounting ingestion keep 1,000 closed orders and 1,000 acknowledged fills; active/unknown/pending evidence is pinned. | Execution/history/incremental-accounting tests rerun. | **CLOSED** | Original closed-history defect repaired. Authoritative uncertain items deliberately cannot be silently evicted; persistent uncertainty still needs operator resolution. |
| A1-006 / HIGH-MEDIUM | Duplicate resting slot exposure undercounted | Order manager groups all resting orders, cancels surplus/unmanaged orders; risk sums remaining standing quantities and uses safe replacement maxima. | Duplicate/orphan/unknown/cancel-race native tests. | **PARTIAL** | Actual signed venue duplicate/orphan, partial-fill and cancel/submit-race acceptance. |
| A1-007 / MEDIUM / HARDENING | Matured markout changes after history eviction | `agents/evidence.py` freezes the first eligible maturity observation/value; missed evicted horizons remain unavailable. | Agent telemetry/quality tests rerun. | **CLOSED** | No original defect established now. Horizons share fills and are not independent samples. |
| A1-008 / MEDIUM / HARDENING | Deadband refreshes old price timestamp | Reference `EvidenceState` retains an exact price/source-time pair and separates receive time/semantic versions. | `test_phase8_provider_observations.py` and RedStone/provider tests. | **CLOSED** | Upstream-native time availability still limits assurance, as documented. |
| A1-009 / HIGH-MEDIUM | Local APIs lack remote operator authorization/admission | `deployment.py::LocalOnlyBoundary` validates peer, Host, Origin, forwarded/duplicate headers; research body/worker budgets enforced. | Native local-boundary/body-limit tests and real browser 413/429 checks. | **PARTIAL** | Remote authentication/roles/TLS/proxy/secrets/operator audit identity are absent. Local-only use is the supported boundary; no remote deployment acceptance. |
| A1-010 / MEDIUM / HARDENING | Every reader repeats work/advances sequence | Runtime/terminal publisher builds one cached canonical observation, one-slot client queues, 32-client cap. | `test_audit_local_publisher.py`, websocket tests. | **CLOSED** | No original defect reproduced; slow clients receive bounded current observations rather than a lossless event log. |
| A1-011 / MEDIUM / HARDENING | GET refreshes trading/accounting state | Runtime getters return observational copies; tick/feed/lifecycle paths own mutation. | `test_audit_read_observations.py`, accounting/runtime and research-isolation tests. | **CLOSED** | A3-002 is a mutating PUT error, not this getter defect. |
| A1-012 / MEDIUM / HARDENING | Shallow frontend validation/open malformed streams stall | Derived terminal schema, strict nested validation, callback ownership and valid-frame watchdog. | Backend contract tests and frontend validation/recovery tests; current routes error-free. | **CLOSED** | No authenticated remote-channel claim. A2-004's later freshness scope also reviewed below. |
| A1-013 / MEDIUM / HARDENING | Optional ERROR neutrality relaxes prior caution | Agent models/supervisor explicitly implement per-evaluation conservative transforms and soft optional failure; prior advice is not latched. | `test_phase9_agents.py`, expansion tests and documented policy. | **CLOSED (acknowledged)** | This remains unsuitable for treating an optional agent as a mandatory independent safety interlock. No such stronger authority is claimed. |
| A1-014 / MEDIUM / HARDENING | Quality labels depend on cadence/optimistic reference | Evidence captures fill-time consensus; mature markouts required for GOOD; churn excludes KEEP dilution. | Execution-quality and evidence tests rerun. | **CLOSED** | PAPER quality remains model-dependent, not proof of real queue performance. Modeled classification defect A3-001 is separately confirmed. |
| A1-015 / MEDIUM / HARDENING | Optimizer validation labels lack enforced holdouts | `simulation/optimizer.py` and dataset contracts label reused/overlapping validation and reject false independent-holdout claims; unexpected engine failures propagate. | `test_phase10_optimizer.py`, scenario/API/static suites. | **CLOSED** | True out-of-sample economic validation remains an external research requirement, not a code claim. |
| A1-016 / MEDIUM / HARDENING | Quant scores need sampling/numeric calibration | Shared count-based estimator has bounded finite/numerical guards and documented per-accepted-observation units. | `test_phase6_market_adaptation.py`, agent tests with extreme values. | **PARTIAL** | Cadence sensitivity, thresholds and heuristic confidence need empirical calibration; these are not annualized volatility or calibrated regime probabilities. |
| A1-017 / MEDIUM / HARDENING | Unused NumPy and compatibility duplication | `backend/pyproject.toml` still deliberately declares NumPy; optional offline ML imports remain isolated. Compatibility review documented, removal deferred. | Source/import/manifests inspection and clean installs. | **PARTIAL** | Resolve intentional unused-direct-dependency policy and reproducible Python dependency resolution in a reviewed change; do not claim PR #25 removed NumPy. |
| A1-018 / MEDIUM / HARDENING | Current docs mix obsolete capability/history | Current root summaries include research/local boundaries and later phase addenda; original narrow twelve-page/authority repair exists. | Current docs compared with routes and phase acceptance. | **CLOSED** | Ongoing stale API/version prose and old browser entry points are maintenance debt, listed in section 20; old historical screenshots are not current acceptance. |
| A1-019 / MEDIUM / HARDENING | Transport config transition not serialized | Runtime lifecycle lock captures old resources, stages replacement, atomically publishes success and gates recovery on explicit failure/restart. | Lifecycle, config-transition and failure tests. | **CLOSED** | No original transition-authority race reproduced. A3-002 preserves state but mishandles one preflight error. |
| A1-020 / MEDIUM / HARDENING | Late history response overwrites new live points | Frontend history merges session/watermark and preserves newer live points; chart ownership/resizing bounded. | Frontend history/store/chart tests and browser restart/retirement workflows. | **CLOSED** | Bounded current-session chart is not durable market history. |
| A1-021 / MEDIUM / HARDENING | Per-quote fingerprint unsupported by backend | Explicit ladder/envelope membership provides provenance without a circular hash; UI distinguishes recommendation/risk/final authorization/execution. | Backend/TS lineage contracts and current Agent/Execution views. | **CLOSED** | Semantic identity is not a full source archive or a fill-level causal attribution. |
| A1-022 / MEDIUM / HARDENING | Fresh envelope labels retained stale sources healthy | Observational emission recomputes source ages/health and suppresses stale history metrics using copies. | Source-aging tests and frontend freshness/session suites. | **CLOSED** | Transport, decision and underlying source freshness remain distinct; A3-003 exposes an independently callable SHADOW feature gap. |
| A1-023 / MEDIUM / HARDENING | Redaction leaves credential suffix | Complete credential/scheme sanitization precedes truncation; selected outward diagnostics are copied/redacted. | Diagnostic sanitization, provider and API fault tests including current injected private-engine failures. | **CLOSED** | No actual secret leak established. This is not a formal all-channel credential audit. |
| A1-024 / INFORMATIONAL | k normalized away from executable budget | AMM reserve-delta shape normalized to explicit per-side base quantity; effective-liquidity UI explains budgets. | AMM tests, source and independent invariant sweep. | **CLOSED (acknowledged)** | Intentional model semantics; do not treat virtual reserves as deposited collateral. |
| A1-025 / INFORMATIONAL | Scientific tools belong in optional offline research | Optional offline ML artifact/training path; operational agents do not import sklearn for online fitting. | Import-boundary/static tests and optional skip. | **CLOSED (acknowledged)** | Optional training was NOT RUN here; no online-learning or predictive-performance acceptance. |
| A1-026 / INFORMATIONAL | Research vault/partial TESTNET not durable custody | Accounting/vault labels remain noncustodial and in-memory; venue evidence partial. | Accounting/source, Phase 16.6B limitation documents. | **CLOSED (acknowledged)** | Durable operational lifecycle/recovery remains BLOCKED, explicitly separate from closure of truthful scope labeling. |
| A1-027 / INFORMATIONAL | Semantic fingerprints are not full archives | Identity scopes are explicit; historical/research receipts add bounded content provenance without claiming raw signed market archives. | Provenance/tamper suites, source models and docs. | **CLOSED (acknowledged)** | Fingerprints do not authenticate upstream truth, dependency environment or original capture ownership. |

## 5. Audit 2.0 Findings Crosswalk

All five original severities are **MEDIUM / HARDENING**. The original [Audit 2.0](AUDIT_REPORT_2.0.md) remains unchanged.

| ID / original problem | Original severity | Current implementation | Current independent/current-test evidence | Disposition | Remaining work |
|---|---|---|---|---|---|
| A2-001 — Raw distance metadata bypass after tick rounding | MEDIUM / HARDENING | `amm/discretizer.py` recomputes executable distance from normalized price; `strategy/quote_engine.py`, `risk/limits.py` and final authorization independently check actual prices against the validated fair. | Reran 56 Phase 12.2 hardening tests within a 92-pass focused set. Cases cover coarse ticks, tiny/large fair, neutral transforms, inventory/agent modifications and final PAPER/TESTNET fixture normalization. Independent 1,000-case sweep checks actual final distance. | **CLOSED** | Supported native paths verified without signing. No proof of unsupported market normalization; A3-004 is separate. |
| A2-002 — Schema accepts economically/numerically uncompileable config | MEDIUM / HARDENING | `strategy/models.py::StrategyConfig`, `amm/numeric.py`, reserve initialization/sampling and runtime config preflight use Decimal guards and rounded-up quantity floors. Feasibility is checked before publishing configuration. | Rounded floor, tiny `1e-26`/large values, extreme reserve and representability cases; native 240-case compile/rejection grid; API atomic 422 tests; independent sweep. | **CLOSED** within original numerical/economic scope | Static validation cannot guarantee all future fair/venue conditions. Stale perp-context exception produces a separate 500 (A3-002), without changing the old config. |
| A2-003 — Collapsed ticks lack effective-price/operational policy | MEDIUM / HARDENING | Same side/index logical slots deliberately remain separate; diagnostics and frontend aggregate executable quantities using exact Decimal/BigInt-safe handling. Authorization/reconciliation preserve stable slot identities. | Native adversarial 100-slot/two-price case: 100 CREATE then 100 KEEP, not artificial REPLACE; 4.9975 base exposure per side; budgets/floors checked. Frontend displays effective ticks and concentration. | **PARTIAL** | No exposure defect reproduced; explicit operational cost, cancel/churn and duplicate-price policy remains deferred in Phase 12.2 acceptance. Do not silently consolidate orders in this audit. |
| A2-004 — Arrival-time freshness and session replay edges | MEDIUM / HARDENING | `frontend/src/utils/validateTerminal.ts` and terminal store/hook validate full fractional timestamps, 5 s age/2 s future bounds, monotonic process sequence, current session and bounded retired identities. | Current frontend tests reject stale/future/duplicate/regressive/retired/cross-process frames and demonstrate legitimate reconnect/new-process recovery; history/market observation paths also validated. | **CLOSED** for scoped local client | Retired memory has finite FIFO capacity (64 process/session pairs and 64 process identities) and resets on reload; not cryptographic anti-replay or remote authentication. |
| A2-005 — Normal declared test-extra teardown failure | MEDIUM / HARDENING | Async cancellation, application/Redis lifespan, websocket worker and lease ownership reviewed; supported Linux stack tears down successfully. | Fresh `backend[test]` install; 20 independent subprocesses, each 28 focused lifecycle tests, **560 passes** total; full `test,redis` run also passed. No original failure reproduced in this environment. | **PARTIAL** | Historical macOS acceptance remains explicitly pending; neither one Linux run nor repeated same-platform runs closes cross-platform/intermittent conditions. |

### Mandatory A2 adversarial conclusions

The compiler's checked quantity is now `abs(executable_price / validated_fair - 1) * 10000`, not caller-supplied distance metadata. Final normalization can remove an infeasible level or reject a request, but cannot preserve permission solely because its old metadata said it was close enough. Bid rounding down and ask rounding up are independently rechecked. Native tests include adversarial neutral/inventory/agent paths and mocked SDK requests; none constitutes signed TESTNET acceptance.

Rounded minimum size is charged before distributing variable quantity. A config exactly at rounded floor may correctly produce uniform levels; a budget below the sum of floors is rejected. Numerical context/guard checks reject impossible precision rather than relying on Decimal exceptions during an active tick. Preflight uses current usable market evidence and has documented static limitations when no such evidence exists. It does not promise feasibility under every future price, provider failure or unsupported venue rule.

Collapsed-price slots remain distinct financial requests, and standing duplicates must all contribute exposure. Stable identities avoid gratuitous reconciliation churn; they do not erase venue message/fee/cancellation cost. The latter is why A2-003 remains PARTIAL despite improved charts and passing arithmetic tests.


## 6. A3-A — AMM Mathematics and CLOB Compiler

`amm/constant_product.py` implements positive virtual reserves and `x*y=k`; swap/recenter operations preserve invariant within bounded Decimal context. Recenter uses square-root reserve relationships. Concentrated range sampling in `liquidity_curve.py` derives incremental reserve movements, not the erroneous cumulative deltas that would overweight outer levels. Concentration reshapes the normalized profile; it is not a claim of on-chain concentrated-liquidity custody.

`amm/discretizer.py` orders BID descending and ASK ascending, rounds executable prices and sizes in the safe direction, allocates per-side base-quantity budgets, reserves each rounded minimum size, rejects invalid/crossed ladders and recomputes executable distance. `amm/numeric.py` centralizes guarded Decimal context/representability; quote-engine and limits checks do not rely on metadata alone. Logical side/level identity survives equal prices. The risk engine separately validates actual economics after transforms and venue normalization.

An independent seeded sweep executed **1,000 cases**: 514 concentrated and 486 constant-product cases; reserve scales `1e-50` through `1e100`; fair prices approximately `1e-12` through `1e12`; 1/2/8/20/50 levels; distances 0.001/0.2/100/2500 bps; tick/fair ratios `1e-8`, `1e-4`, 0.01 and 0.25. Assertions checked invariant relative error ≤`1e-24`, positive ordered uncrossed prices, actual executable-distance identity, per-side budgets and unique logical identities. These 1,000 cases compiled successfully; this sweep did not itself assert the configured final risk-distance ceiling. The separate native risk/grid checks add rejected infeasible cases, extreme floors, tiny fairs and API rejection paths.

No new AMM formula, budget, crossing or supported-native final-distance defect was established. Continuous virtual curves necessarily become discontinuous at executable ticks; discrete price collapse is expected and explicitly diagnosed. Quantity normalization makes k cancel from profile scale at fixed budget. A1-024 is therefore an intentional semantic boundary, not hidden extra collateral. A2-003's operational duplicate-price policy remains outstanding. Broad-market execution precision has a confirmed separate defect, A3-004.

## 7. A3-B — Hyperliquid SDK and Market Data

### Native market and transport integrity

The official SDK is used, but the application adds its own lifecycle, parsing, provenance and admission controls. Operational `market_data/hyperliquid.py` and the later read-only `live_streams.py`/`live_observations.py` are distinct implementations. Source timestamps, receive timestamps and internal generation/material versions have different meanings. Material content changes cannot hide behind a deduplicated chart sample. LIVE exchange time regression is rejected; stream generation ownership prevents late old-client callbacks from becoming current evidence.

The multi-market path bounds wire payloads, parsed nesting/node counts, ingress, per-subscriber delivery and subscriptions; one client handles six BTC/ETH/SOL book/context subscriptions. Subscriber capacity is 16. The older operational SDK bridge still merits load profiling: its event-loop callback/queue behavior is not the same as the newer bounded-ingress implementation. No actual unbounded-growth incident was measured in this audit, so that remains a concern rather than a confirmed leak.

Metadata loader `hyperliquid_metadata.py` validates the SDK response, native precision and requested markets. It deliberately excludes namespaced/non-native identities and separates `EXCHANGE_VERIFIED` from `DEMO_PROFILE` and unavailable states. Perpetual context uses the matching native universe, mark/oracle/funding/open-interest fields and freshness checks. An exchange-verified precision profile is not signed order permission, historical authenticity or a guarantee that a market is economically calibrated.

### Reference integrity and actual acceptance

Consensus is role-aware: one RedStone public HTTP fallback is one degraded identity, not a fabricated independent oracle vote. Prices and timestamps remain paired through deadbands; outliers/conflicts and stale providers do not become healthy merely because their transports received a packet. Market-specific binding restrictions prevent reusing an ETH external reference on another operational market. Live optional mappings cover only explicitly supported symbols; missing keys are unavailable, not silently successful.

A current public read-only runner accepted actual Hyperliquid SDK metadata, REST L2/perp context and both WebSocket channels for BTC/ETH/SOL, controlled reconnect, fresh recovery and clean termination in 31.772 s. Twelve subscription creations represent six initial plus six reconnect subscriptions, not twelve simultaneous market channels. No owned threads/tasks/subscribers remained. This is short public multi-market observation evidence, not operational mode-switch soak or signed execution acceptance.

A direct Kraken ETH/USD run accepted a fresh BBO. Separately, a valid heartbeat fixture degraded a still-fresh Kraken observation: **A3-007**. Public RedStone HTTP returned a transport `ProxyError`; no price was accepted. RedStone Live and keyed CoinGecko were NOT RUN for absent endpoint/key configuration; Yahoo acceptance was NOT RUN. Existing fixture tests for these parsers do not close those external gates.

Builder-deployed perpetuals use namespaced identities and SDK index offsets above 100,000. The adapter currently selects spot price precision by `asset >= 10000`, misclassifying them: **A3-004**. Native BTC/ETH/SOL observation acceptance does not generalize to those markets. See section 13.

## 8. A3-C — Supervisory Agents and Predictive SHADOW

| Agent | Actual computation/contract | Reliability interpretation |
|---|---|---|
| Regime | Existing guarded per-observation volatility, bounded momentum/dislocation/context signals; explicit state priority and sample sufficiency. | Heuristic confidence is evidence sufficiency/score scaling, not calibrated likelihood of a future regime. |
| Toxic Flow | First eligible frozen markouts, adverse-side measures and persistence from bounded fill evidence. | 1/5/15-second horizons can share the same fill; maturity/sample count is not independent statistical evidence. |
| Execution Quality | Fill-time reference/capture, lifecycle/churn, mature quality outcomes. | KEEP does not dilute churn. PAPER outcomes retain execution-model limitations; modeled telemetry classification is defective in A3-001. |
| Liquidity Quality | Bounded L2 depth, spread, imbalance, thinness and instability. | Descriptive book evidence cannot infer hidden liquidity or queue position. |
| Perp Crowding | Funding/basis and distinct open-interest observations, with availability/freshness semantics. | One OI value does not establish a trend; heuristic thresholds require calibration. |
| Predictive Adverse Selection | Immutable optional artifact, feature schema/classification, deterministic logistic inference and sample/confidence support. | **SHADOW only**, `affects_quotes=False`; stale required features are accepted by its callable feature/inference path (A3-003). |

Supervisor combination restricts the upstream candidate: widening spreads, reducing permitted sizes and pruning existing levels. It cannot restore a removed side, increase authority, clear kill, modify signer settings or bypass final limits. Inventory's deliberate position-reducing side sizing occurs earlier under hard exposure/capital limits; it should not be confused with an agent authority increase. Version/fingerprint fields bind declared material decision inputs, not every raw telemetry field or the entire source tree.

Optional agent ERROR resets to neutral advice per evaluation. Losing yesterday's cautious recommendation can therefore relax today's candidate relative to yesterday, while remaining conservative relative to today's upstream candidate. This is the acknowledged A1-013 policy, not a newly discovered escape from risk. Required safety behavior belongs to risk/firewall, not an undocumented assumption that all agents latch caution.

Offline research builds temporally ordered features/labels, checks classification/market/artifact schemas, and distinguishes reused/overlapping datasets. No profitable out-of-sample performance, calibration or leakage-free real-market training corpus was established. The optional sklearn coefficient-export test skipped because sklearn was absent. Source-level no-future-timestamp checks do not imply freshness: a one-day-old book with `perp_stale=True` still produced READY/PREDICTED in the audit counterexample. A modeled PAPER fill is also incorrectly labeled nonsimulated in agent telemetry and rejected by the simulated ML dataset builder. Both defects need repair before trusting those research labels; neither promotes SHADOW into quote authority.

## 9. A3-D — Execution, Reconciliation, Capital and Risk

### Execution and uncertainty

Baseline PAPER deterministically fills crossing orders at the limit under explicit optimistic assumptions. MODELED_CROSSING adds configured latency, finite visible depth, shared per-book depth consumption, partial fills, slippage and cancellation latency; pre-acknowledgment states remain uncertain. It still lacks validated real queue priority/hidden liquidity and is labeled hypothetical. Actual modeled fill generation was exercised, not inferred from a source string; its downstream agent classification fails (A3-001).

TESTNET requires the explicit enable flag, exact testnet endpoint and key. Runtime-managed order requests are normalized conservatively before final structural/economic checks; concrete requests must match authorized slots and SDK float/wire round trips. Alo requests and uncertainty handling are covered by fixtures. UNKNOWN is registered before wire transmission; lost acknowledgments, failed cancel verification, unmanaged duplicates and uncertain position evidence halt new replacements. Cancels must complete before a replacement's exposure can be treated as removed.

All actual standing duplicates contribute remaining exposure; desired and cancel-before-create replacement maxima avoid both undercounting duplicates and blindly double-counting a single safe replacement. Active/uncertain orders are not discarded to enforce a display-history bound. Fill identity is idempotent; conflicting reuse is rejected. Native suites cover lost acknowledgment, duplicate fills/orders, partial execution, out-of-order/unknown state, stale authorizations and kill behavior. These are local/SDK-fixture executions, not successful venue transactions.

### Capital, final authorization and accounting

The risk/firewall path checks executable prices, side ordering/crossing, distance, size/notional, remaining inventory/exposure, freshness, kill state, configuration/evidence versions and reservation identity. Authorization binds the final quote ladder and concrete request membership; the adapter repeats the boundary checks. No path in the supported runtime API was established that accepts an economic create outside final permission. Manually instantiating internal Python adapters is not a public authenticated endpoint and is not a claim of protection against arbitrary host code execution.

Kill is independent of research/Redis health; resume does not automatically start trading. The actual browser sequence Start → Kill → confirmed Resume ended stopped. Failed/uncertain cancellation cannot be converted into an assumed empty book for fresh orders.

Accounting uses signed base positions and average cost, realizes only closing quantity on reductions/reversals, applies fees/funding to cash, and computes equity as cash plus unrealized PnL. Trade-plus-fee ledger application is atomic, repeated identical fill identity is idempotent and conflicting evidence fails. Funding is interval/idempotency controlled; positive-rate long funding pays under the declared convention. Fees are nonnegative in the current contract, so rebate accounting is unsupported rather than silently modeled. Ledger saturation halts further ingestion instead of dropping financial evidence.

No new accounting sign, reversal, fee/funding, reservation or final-authorization defect was established. This is bounded research accounting: TESTNET fill evidence is partial, external account movements are not fully attributed, all financial state is not durably recoverable, and a research vault is not custody. A1-001/A1-006 therefore remain PARTIAL and production remains blocked.

## 10. A3-E — Simulation, Replay and Portfolio Research

### Native engine, optimizer and isolation

Research creates a fresh isolated runtime/domain stack, deep-copies admitted inputs and permits only explicit research configuration fields. It cannot switch operational execution mode, enable signing, alter manual kill or mutate the running strategy. The shared `ThreadPoolExecutor` has one admitted computation and no unbounded waiting queue. HTTP cancellation cancels the waiter, not a running native engine: capacity remains occupied until actual completion. Nested portfolio legs reuse the same admission rather than recursively acquiring another worker. Shutdown waits for owned work. Native and current process-interruption browser tests support these contracts.

Deterministic fingerprints and seeded datasets are meaningful within a declared engine/schema/environment. They are not a full dependency lock or proof of economic realism. Optimizer overlap/reused validation is labeled; unexpected engine exceptions are sanitized at APIs and retain server-side failure semantics. The browser exercised actual engine 422/429/413/503 and injected sanitized 500 paths without accepting substituted evidence.

### Historical storage, provenance and comparisons

Historical catalog access uses POSIX file-descriptor traversal with `O_NOFOLLOW`, owner-private roots, regular/single-link checks, bounded reads, unchanged-stat verification, pinned file locks and atomic staged/fsynced content-identified publication. Catalog capacity is bounded at 256 datasets. Canonical content, source declarations, receipts and segment clocks are validated. Those controls resist local path substitution and partial publication; the owning user can still intentionally supply false history. A user assertion is not exchange authentication, immutability against the owner or licensing verification.

Replay reuses the native engine with explicit source versus receipt/as-of time, gap segments and independent resets. Gaps are not interpolated into invented continuous history. Baseline/modeled PAPER assumptions are captured separately; comparisons expose ineligible metrics and source/config/engine mismatches. Current browser fixtures are generated records with user-asserted recorded labels, explicitly **not authenticated exchange history**. Source fingerprint consistency/tamper rejection is tested; real historical performance acceptance is not inferred from it.

### Shared-capital portfolio and temporal classes

Portfolio contracts support BTC/ETH/SOL only, exact up-to-18-place shared capital and allocations (bounded at `1e12`), one reserve subtraction and context-80 allocation arithmetic. Native per-market accounting still has its declared Decimal precision. Engines run sequentially and produce captured native receipts; aggregation does not manufacture fills or inject positions into an engine. Currency/collateral is USDC under the current contract.

| Temporal class | Meaning and allowed interpretation |
|---|---|
| `MODELED_ALIGNED` | Complete compatible native modeled clock/history. Eligible modeled equity/PnL/drawdown projections; **not empirical historical correlation**. |
| `FINAL_ONLY` | Final accounting exists but full compatible history is not retained. No fabricated temporal drawdown/chart conclusions. |
| `INCOMPARABLE` | Incompatible scenario/engine/clock/source assumptions prevent the claimed comparison. |
| `UNAVAILABLE` | Invalid or missing evidence cannot support the result. |

Limits include three markets, 3,000 total executed frames, 24,000 frame×quote-level work, **1,500 retained native observations shared across all legs**, 30,000 ledger entries, 750 events, 65,536 request bytes and 200,000 response bytes. Chart projections cap at 120 points per leg and preserve selected extrema/onset/threshold evidence; they do not backfill missing native history. Risk uses complete native history rather than treating a downsampled chart as the full risk path. A known HALT survives an aggregate BLOCKED assessment.

### Stress and measured boundaries

All six configured stress types (`CORRELATED_SELLOFF`, `BTC_LED_VOLATILITY`, `LIQUIDITY_SHOCK`, `FUNDING_STRESS`, `ORACLE_DEGRADATION`, `CONCENTRATION_STRESS`) transform actual native dataset/context inputs and rerun baseline/stressed legs. Concentration derives from a pre-onset nonzero native position, not an injected synthetic holding. Correlation/source-authentication fields do not invent empirical evidence; empirical correlation stays unavailable when source/time assumptions do not support it. Baseline preservation and source/assumption fingerprints are tested. A positive-but-subquantum SOL depth multiplier passes preview yet produces zero-sized invalid transformed levels after baseline work: **A3-005**.

Current cold subprocess measurements (not latency guarantees):

| Workload | Wall / peak RSS | Output / retained history | Correct result / cleanup |
|---|---|---|---|
| BTC/ETH/SOL, 500 frames each, one leg | 18.3322 s / 121.45 MiB | 33,086 response bytes; 1,500 observations; three native runs | `MODELED_ALIGNED`, risk ASSESSED, 120 baseline chart points; worker released and threads stopped |
| BTC/ETH/SOL, 300 frames each, two legs | 25.8532 s / 158.68 MiB | 26,971 response bytes; 1,800 executed but 1,500 retained observations; six native runs | `FINAL_ONLY`, risk BLOCKED, zero baseline/stressed chart points; worker released and threads stopped |

This audit measured these two cases and browser workloads, not every performance-runner case or multi-user production capacity. CPU cost is material but bounded by admission; a cancelled browser request does not reclaim already-running CPU work. Durable lifecycle/recovery in Phase 16.6B remains incomplete despite truthful manual-rerun/session-retirement UI.

## 11. A3-F — Frontend, Accessibility and Screenshot Audit

### Pages, controls and financial interpretation

All 13 routed pages were opened against the current application at 1440×1000 and 390×844 CSS viewports. The following includes source inspection of their shared controls/stores and nested workspaces. `Planned.tsx` is unused legacy source, not a fourteenth active product page.

| Page / nested workspace | Current behavior and evidence | UX/readability assessment |
|---|---|---|
| Dashboard | Mode/source/health, risk, operational controls, inventory and charts; current desktop image inspected. | Risk is visible and actions explicit. Persistent diagnostics above content add substantial mobile height. |
| Markets / live observation / research comparison | Source-separated live books/context/history and research profiles; three-market validation and stale-result retirement. | Profile versus observed data labeling is useful. Narrow table formatting and two-decimal legacy displays are not a general low-price-market presentation contract. |
| Strategy | Server-validated draft/dirty-state controls, explicit start/stop and changes. | Input errors preserve draft intent. A3-002 exposes a generic server error for one stale-context update. |
| AMM Settings | Curve/budget/concentration controls, effective liquidity and collapsed-tick explanation. | Distinguishes logical levels from executable ticks. Quantity versus collateral still requires operator understanding. |
| Execution | Active/uncertain/closed orders, PAPER fills, reconciliation and provenance. | Horizontal internal tables and long IDs require keyboard-accessible panning; historical mobile image shows strong wrapping/large retained-record area. |
| Risk | Firewall conditions, limit/gauge details, authorization and action summaries. | Small low-contrast gauge labels; mobile prices break over several lines. A3-006 affects this safety-relevant reading experience. |
| Supervisory Agents | Six cards, evidence sufficiency, authority separation, bounded event list. | SHADOW and unavailable states are explicit. Long 390-pixel page and tiny neutral badges hinder scanning; event scroller lacks focus access. |
| Vault / Research Vault | Operational noncustodial capital and isolated preset/accounting proposals. | Research versus operational proposals are distinguished. Exact long decimals verified by current browser; mobile vertical density remains high. |
| Analytics | Accounting/PnL, fee/funding and bounded chart/ledger evidence. | Labels avoid describing session charts as full exchange history. Dense summary/ledger needs experienced interpretation. |
| Simulation & Optimization | Scenario workbench, bounded optimizer, Historical Replay tab and comparison workspaces. | Running/error/retired states tested. Old replay harness misses the current tab entry, a test-maintenance defect. |
| Historical Replay / comparisons (nested) | Source catalog/provenance, segments/frames, execution model and comparison eligibility. | Current five-width workflow verified; unavailable/incomparable results remain unavailable, no substituted metrics. |
| Portfolio Research | Configure/Analytics/Stress Lab/Provenance sections; exact allocation, worker preview and bounded native charts. | Current five-width workflows passed; blocked temporal charts correctly absent. Mobile diagnostics/sections cause substantial scrolling. |
| Logs | Bounded read-only retained events and explicit unavailable evidence. | Does not imply permanent audit retention. Long messages/identities require usable internal overflow. |
| Settings | Runtime/provider/lifecycle diagnostics and deliberate local controls. | Source mode and missing-provider states shown. No remote-user account/security management capability is implemented. |

Forms and selectors in the 26 route-viewports had **zero unlabeled input/select controls** in the audit scan. Mobile navigation has Escape/focus/ownership handling; native disclosures and keyboard navigation were exercised in the repository replay harness. No document-level horizontal overflow, browser page exception or normal console error occurred in the route sweep. Those results do not establish complete WCAG conformance, screen-reader acceptance or absence of internal clipping.

### Confirmed accessibility and layout limitations

axe WCAG 2 A/AA checks reported `html-has-lang` in all 26 route-viewports, `color-contrast` in six (22 node occurrences), and `scrollable-region-focusable` in seven (10 node occurrences). These are repeated occurrences, not 39 distinct independent bugs. Several automated checks remained incomplete and require human interpretation; no all-accessibility PASS is claimed. A3-006 records the missing document language, small text contrast below 4.5:1 and keyboard-inaccessible overflow. Representative current Risk mobile values wrap currency digits into fragments, reducing comparability even with no whole-document overflow.

Financial authority uses server Decimal values and string-safe/exact client allocation logic; display conversion to JavaScript Number is not order authorization. The portfolio exact-capital workflow exercised 18-place values. Legacy generic two-decimal price formatting is acceptable for demonstrated high-price native profiles but insufficient evidence for arbitrary low-price markets; do not expand compatibility based on its appearance. Charts are bounded, clean up owned instances and resize; units and source labels are present, but no screen-reader chart-equivalence study was performed.

For nontechnical retail users the terminology, diagnostic-first mobile layout and long dense cards impose substantial interpretation cost; usability is CONDITIONAL, not validated by a user study. Experienced individual traders can inspect PAPER risk/execution with clear source labels but must respect hypothetical fills and incomplete venue evidence. Advanced research/operators receive strong provenance/ineligibility detail and exact allocation controls; the density is more useful to that audience, while the confirmed contrast/focus defects still apply.

Historical image inventory and current browser acceptance are detailed in section 17. All historical acceptance images received actual overview pixel inspection; their dates/phases are not substituted for current rendering.

## 12. A3-G — Infrastructure, Security and Performance

### Local trust and resource boundaries

`deployment.py::LocalOnlyBoundary` restricts real peer/Host/Origin, rejects untrusted forwarded and duplicate framing/security headers, and addresses loopback DNS-rebinding assumptions. The ASGI test-client exception is scoped to the test peer, not a public bypass. WebSocket origin/peer checks complement HTTP guards. There is no authenticated remote operator model; trusting loopback is a deliberate local deployment boundary, not a substitute for remote authorization.

Mutating/research requests have 64 KiB body/framing limits, bounded parsing and sanitized outward errors. Actual browser 413/429/error cases were rerun. Research responses are bounded and marked non-cacheable; private injected engine/proxy text did not become trusted frontend evidence. Configuration/signer values are excluded from research candidate allowlists. No exposed secret or research route that mutates operational financial state was established in the reviewed paths. This was not a dedicated credential-history scanner or penetration test against an externally deployed service.

FastAPI lifespan owns cancellation, subscriptions, worker release, Redis health and terminal publisher teardown. Cancellation is shielded where the running worker must remain counted. Physical Redis failure does not clear manual kill or imply empty financial state. Single-worker startup/deployment assumptions are documented; Redis leases are coordination/cache availability evidence, not financial authority or durable receipts.

### Physical Redis and Phase 16.6B

The audit built official Redis 7.4.11 in ignored scratch and ran the repository physical acceptance runner. Seven checks passed: connected PING health; two PubSub-backed WebSocket clients and release; actual coordinated PAPER research worker; TTL/cache/Lua single admission and release/heartbeat expiry; server termination causing degraded 503 while kill still works; server restart restoring connectivity without clearing kill; clean application shutdown. This is actual local Linux Redis evidence, not fakeredis and not a historical claimed PASS.

Earlier acceptance documents that marked physical Redis BLOCKED are superseded **only for those newly exercised local cases**. Multi-host failover, long outages, version/platform matrix and production Redis operations were not certified. Phase 16.6B's durable lifecycle/recovery remains **BLOCKED**: process-local runtime orders/fills/ledger/research receipts are not a durable restart protocol, and frontend retirement/manual rerun is not backend recovery. No recovery capability is inferred from Redis reconnect.

### Bounded growth, performance and dependencies

Terminal fanout, research workload/chart/response budgets, historical catalog and closed execution history are bounded. Financial active/uncertain evidence is pinned rather than erased. The newer public stream bounds ingress/fanout; the older operational callback bridge needs dedicated pressure/soak evidence. Portfolio cold measurements in section 10 show tens of seconds at admitted limits and successful worker/thread release, not uncontrolled multi-job execution. Whole-app Zustand subscriptions and a periodic clock can rerender large operational pages; no profiler demonstrated a correctness failure, so optimization is optional debt rather than a new financial bug.

The production frontend build succeeded but retained TanStack `"use client"` directive warnings and a large-chunk warning. Main application JS was 726.72 kB minified / 195.68 kB gzip; charts 169.81 / 54.93 kB; query 47.16 / 14.45 kB; CSS 59.39 / 11.85 kB. No browser navigation latency SLA was measured. Splitting the bundle is maintenance/performance work, not a reason to suppress the warning.

`npm audit` reported one vulnerable direct package, Vite 7.3.6, with five advisories and aggregate HIGH severity. The Windows-specific HIGH advisory is A3-008; additional non-Windows dev-server conditions are explicitly scoped there. No dependency/lockfile was changed. No Python vulnerability scanner result is claimed; range-resolved dependency reproducibility and the optional scientific footprint remain A1-017 debt.

## 13. A3-H — Full Market-Universe and HIP-3 Readiness

**Current validated scope is BTC/ETH/SOL native-perpetual observation/research, not the entire Hyperliquid universe. HIP-3 compatibility is BLOCKED.** Operational config accepts a string, which is not proof that every string has supported metadata, execution permissions, references or accounting. Unsupported identity must remain unavailable rather than falling back to a generic 3,000-price DEMO path and being called live integration.

The following source inventory groups files that share the same identity dependency. Paths inside a cell are individual relevant files; grouped rows do not imply that the other files implement namespace support.

| Source files / functions or contracts | Current market dependency / class | Failure if generalized incorrectly; required verification |
|---|---|---|
| `backend/app/config.py`; `strategy/models.py::StrategyConfig`; `runtime.py` config transition | Startup operational market/external binding and raw strategy market string; **authority/calibration** restriction. | A changed string can outstrip provider/economic support. Verify metadata, enabled permissions, limits and current reference bindings before any additional operational market claim. |
| `market_data/hyperliquid_metadata.py` loader; `live_models.py::LiveMarketId` | Explicit BTC/ETH/SOL, native dex only, namespace/special-name rejection, native size precision; **hardcoded research/data-model** restriction. | Removing a whitelist alone can corrupt universe/index/context association. Verify namespaced instrument tuple, dex, collateral and metadata revision; reject delisted/unsupported entries explicitly. |
| `market_data/live_streams.py`; `live_observations.py` | Fixed accepted native identities and six subscriptions, bounded client/subscriber capacity; **data/resource** restriction. | More instruments can violate admission/fanout/context budgets. Verify real per-instrument stream identity, ordering, reconnect and capacity rather than reusing native channel assumptions. |
| `market_data/hyperliquid.py`; `market_data/perp_context.py` | Operational SDK market subscription and matching mark/oracle/funding/OI context; **SDK/context** dependency. | Namespaced or mismatched contexts must not authorize quotes. Verify actual SDK context and source-time semantics, failure/delisting behavior and clean lifecycle. |
| `execution/hyperliquid.py::normalize_order_request`, account/position reconciliation | Index ≥10,000 treated as spot; SDK Info defaults native perp dex; **precision/asset identity safety blocker** (A3-004). | HIP-3 perp index 110,000 receives spot precision. Require explicit instrument class/metadata and dex-aware account/position identity plus wire/venue validation before claiming compatibility. |
| `execution/order_manager.py`; `agents/evidence.py`; `agents/execution_quality.py` | Unqualified market strings, default ETH telemetry/capture-unit assumptions; **data identity** limitation. | Cross-namespace/collateral evidence can collide or be mislabeled. Verify fully qualified fill/order/evidence membership and market-specific units. |
| `amm/discretizer.py`; `strategy/quote_engine.py`; `risk/limits.py` | Generic arithmetic given correct tick, size, fair and budgets; **parameter/authority** dependency. | Mathematical genericity does not supply correct venue metadata or market risk limits. Verify extreme low-price precision, minimum order size/notional and final normalization for each claimed class. |
| `market_data/mock.py`; `simulation/scenarios.py` | Generic DEMO adapter starts around ETH-like 3,000 price; scenarios have fixed synthetic depth/price assumptions; **simulation/calibration** restriction. | A symbol label alone cannot turn synthetic prices into market-specific evidence. Preserve DEMO labels and verify every profile/scenario calibration. |
| `simulation/market_profiles.py`; `simulation/engine.py`; `simulation/service.py`; `research_strategy` profile construction | Exactly BTC/ETH/SOL; anchors 60,000/3,000/150 and size decimals 5/4/2; hypothetical strategy scaling; **hardcoded research** restriction. | Anchor-based scaling is not external liquidity/risk calibration. Native inventory limits are not automatically generalized by quote-size scaling. Verify actual metadata, reserve/size floors, inventory and capital economics. |
| `references/live_provider_mappings.py`; `references/yahoo.py`; `references/service.py` | Explicit native/external symbols, operational startup bindings; Yahoo BTC/ETH only, SOL unavailable; optional external mode constrained; **provider/security** restriction. | Reusing ETH/USD/BTC mappings for another instrument substitutes evidence. Verify native source symbol, units, timestamps and actual provider acceptance; no keyless success claim. |
| `research_replay/models.py`; `importers.py`; `runner.py`; `comparison.py`; `quantitative.py` | Native `LiveMarketId`, BTC/ETH/SOL display mapping and captured native profile precision; **historical/data-model** restriction. | Namespaced sources could be mislabeled/comparable under an incomplete identity. Verify source, namespace, precision, collateral, segment clocks and provenance before comparison. |
| `research_comparison/assumptions.py` and comparison contracts | Explicit uppercase native tuple and source/scenario/profile match; **research compatibility** restriction. | More labels do not establish equivalent clocks/economics. Keep incomparable/unavailable classifications until identities and units are validated. |
| `portfolio_research/models.py`; `terminal_models.py`; `accounting.py`; `exposure.py`; `scenarios.py`; `stress.py` | BTC/ETH/SOL tuple, deterministic market tie-breaks, USDC accounting, shared allocations, three-market and workload budgets; **collateral/resource safety blocker**. | Cross-collateral/margin/settlement values cannot be summed as one USDC ledger. Verify currency conversion/settlement contract, per-market exposure/limits and total workload; current code does not supply these capabilities. |
| `frontend/src/types/index.ts`; `types/replay.ts`; `types/portfolioResearch.ts`; `api/client.ts` | Three-market unions/path whitelist and native financial schemas; **frontend contract** restriction. | Backend expansion alone would be rejected or misrendered by client validation. Verify unknown identities fail closed and units remain exact. |
| `stores/liveMarkets.ts`; `stores/researchMarkets.ts`; `utils/liveMarketEvidence.ts`; `researchMarkets.ts`; `replayEvidence.ts`; `portfolioResearch.ts`; `scenarioReplayComparison.ts` | Three-market stores/validation, current-source ownership, market-specific selection; **identity/retirement** restriction. | Late or cross-market results could attach to the wrong view if weakened. Preserve market/source/session ownership under any future contract change. |
| `components/markets/LiveMarketsView.tsx`, `LiveMarketOrderBook.tsx`, `LiveMarketHistory.tsx`, `LiveProviderStatus.tsx`, `ResearchMarketSelector.tsx`, `ResearchMarketDetails.tsx` | Fixed market options, native price/size formatting and source labels; **UX/precision** limitation. | Verify very small/large numbers and fully qualified labels before claiming broader usable observation. |
| `components/replay/HistoricalReplayWorkspace.tsx`, `ReplayControls.tsx`, `ReplayOrderBook.tsx`; research-comparison and scenario-replay-comparison components | Supported native market controls, source/assumption comparison labels; **research UI** restriction. | Maintain ineligible metrics and unambiguous source identities; do not substitute unsupported market defaults. |
| `pages/PortfolioResearch.tsx`; `components/portfolio/PortfolioConfiguration.tsx`, `PortfolioStressLab.tsx`, `PortfolioAnalytics.tsx` | Native three-market allocations, USDC labels and bounded temporal sections; **capital/UI** restriction. | More checkboxes would not validate another collateral or expand workload safely. Verify exact capital units, limits and server/UI compatibility. |
| `App.tsx`; `AccountingLedger.tsx`; `EventTimeline.tsx`; `HistoryChart.tsx`; `RecentExecution.tsx`; `settings/ProviderHealthSummary.tsx`; `simulation/CandidateComparison.tsx`, `SimulationTrace.tsx`; comparison metric/chart/explainability components | Operational display/currency defaults and native evidence terminology; **presentation** dependency. | Legacy two-decimal prices and unqualified base/USDC labels may hide low-price or cross-collateral differences. These displays are not execution permission. |

The installed SDK itself supports `perp_dexs` and builder offsets (`110000 + dex_offset`); the application does not therefore inherit safe HIP-3 support. A3-004 is a concrete pure-normalization counterexample even though current supported selectors and native loader normally exclude that route. No new listing, permission or generalized feature is proposed here. The table records existing blockers and verification prerequisites for claims, not authorization to expand scope.

## 14. Confirmed New Findings (A3-001 onward)

Severity reflects the demonstrated defect and affected use, with external advisory applicability stated separately. No finding below asserts a signed trade, empirical loss or exploit that was not executed. The six Python counterexamples are embedded after the finding tables; their assertions deliberately describe current defective behavior and all six passed.

| ID | Severity | Confirmed defect |
|---|---|---|
| A3-001 | MEDIUM | Modeled PAPER telemetry loses simulated classification |
| A3-002 | MEDIUM | Stale perp context turns valid config PUT into HTTP 500 |
| A3-003 | MEDIUM | SHADOW inference accepts explicitly stale features |
| A3-004 | MEDIUM | Builder perpetual indices select spot price precision |
| A3-005 | MEDIUM | Preview accepts subquantum SOL shock that native stress rejects |
| A3-006 | LOW | Language, contrast, keyboard overflow and narrow financial readability defects |
| A3-007 | MEDIUM | Valid Kraken heartbeat degrades a fresh reference |
| A3-008 | HIGH, conditional advisory | Locked Vite 7.3.6 has published affected development-server exposure |

### A3-001 — Modeled PAPER fills lose their simulated classification

| Required field | Confirmed evidence |
|---|---|
| Severity / subsystem | **MEDIUM** — PAPER execution → agent telemetry → predictive research provenance |
| Exact files / functions | `backend/app/execution/paper.py::_modeled_fill` (line 78) and `_fill`; `backend/app/agents/evidence.py::AgentTelemetryStore.observe_fill` (classification at line 150); `backend/app/research/ml/dataset.py::build_dataset`. |
| Preconditions | MODELED_CROSSING PAPER execution produces a genuine crossing fill; the ordinary telemetry callback observes it. |
| Reproduction | Embedded `test_actual_modeled_paper_fill_becomes_nonsimulated_telemetry`: actual modeled ETH BID at 3001 for 0.1 crosses the mock ask; read telemetry, then pass it to `build_dataset(..., simulated=True)`. |
| Expected | A hypothetical PAPER fill remains explicitly simulated throughout telemetry and simulated-dataset validation. |
| Actual | Source begins `HYPOTHETICAL MODELED PAPER FILL`, but telemetry sets `simulated=False`; simulated ML dataset construction rejects it with classification mismatch. |
| Root cause | Telemetry recognizes only `fill.source.startswith("SIMULATED")`. The newer modeled fill uses a different textual prefix. Mode classification is coupled to display text. |
| Impact | Research evidence is mislabeled as nonsimulated and legitimate modeled PAPER training evidence is unusable in the correctly classified dataset path. It is not evidence of live execution; native accounting separately retains simulated classification. |
| Bounded remediation | Carry an explicit execution/evidence mode or shared classification contract through fills and telemetry; cover baseline and modeled PAPER plus nonsimulated venue evidence. Add an end-to-end modeled-fill-to-dataset regression without relaxing dataset checks. |
| Readiness blocks | **Local PAPER:** conditional research-label defect, no order-authority escape. **TESTNET:** no demonstrated signed-path defect. **Broad markets / production:** provenance acceptance blocked wherever these telemetry labels are relied on. |

### A3-002 — A valid strategy update with stale perp context returns HTTP 500

| Required field | Confirmed evidence |
|---|---|
| Severity / subsystem | **MEDIUM** — strategy configuration API / runtime feasibility preflight |
| Exact files / functions | `backend/app/runtime.py::HyperAmmRuntime.update_config` (lines 859–889); `backend/app/strategy/perp_policy.py::PerpContextPolicy.decision`; `backend/app/api/strategy.py::put_strategy`. |
| Preconditions | A usable current market snapshot exists, perp context is enabled and an existing context is stale. An otherwise valid same-market configuration is PUT. |
| Reproduction | Embedded `test_stale_perp_config_update_returns_500_and_preserves_state`: use real route/runtime, age existing context 60 seconds and PUT a valid concentration factor of 9. |
| Expected | Deliberate API rejection/unavailable-context response (e.g. typed 422/503), or an explicitly defined safe static-preflight policy, before operational mutation. |
| Actual | HTTP **500**, body `Internal Server Error`; configuration remains byte-equivalent and lifecycle remains READY. |
| Root cause | `PerpContextPolicy.decision` executes outside the `try` that converts generation `ValueError` into `StrategyFeasibilityError`; the route only handles that typed feasibility exception. |
| Impact | Normal stale-feed conditions turn valid operator edits into opaque server errors. State remains protected; no invalid configuration or order bypass was demonstrated. |
| Bounded remediation | Include context-policy failures in the explicit preflight error contract, preserving atomic configuration behavior and source-unavailable semantics. Test stale/missing/fresh context and unchanged state. |
| Readiness blocks | **Local PAPER / TESTNET:** conditional operational configuration reliability. **Broad markets / production:** robust configuration acceptance remains incomplete; no signed financial escape established. |

### A3-003 — Predictive SHADOW inference accepts explicitly stale required features

| Required field | Confirmed evidence |
|---|---|
| Severity / subsystem | **MEDIUM** — agent feature freshness / predictive research correctness |
| Exact files / functions | `backend/app/agents/ml_features.py::build_feature_vector` (line 51); `backend/app/agents/predictive_adverse_selection.py::PredictiveAdverseSelectionAgent.evaluate` (line 41). |
| Preconditions | A schema-valid artifact and otherwise sufficient evidence exist, but `perp_stale=True` and the book timestamp is one day before the evidence observation. |
| Reproduction | Embedded `test_predictive_shadow_accepts_explicitly_stale_features` uses the repository's existing artifact/evidence fixture and actual feature/inference classes. |
| Expected | Required stale feature evidence yields an unavailable/insufficient inference with explicit reasons. |
| Actual | Feature vector accepted; result READY / PREDICTED; BID adverse probability `0.7310585786300049`. `affects_quotes` correctly remains false. |
| Root cause | Feature boundary rejects missing values and future timestamps but has no maximum-age check and ignores explicit perp-stale status. Evaluation checks artifact/classification/sample support, not this freshness condition. |
| Impact | Research/UI inference may appear ready despite obsolete inputs. Current SHADOW separation prevents direct quote changes; no promotion or calibrated predictive performance is implied. |
| Bounded remediation | Define required-feature freshness relative to evidence time and apply it at the callable feature/inference boundary, consistently with offline as-of rules; preserve unavailable reasons and SHADOW authority. Test stale book/perp/reference and legitimate fresh recovery. |
| Readiness blocks | **Local PAPER / TESTNET:** no direct execution block from SHADOW, but inference integrity is conditional. **Broad markets / production:** predictive-reliance claims blocked until freshness and calibration acceptance. |

### A3-004 — Builder perpetual asset indices receive spot price precision

| Required field | Confirmed evidence |
|---|---|
| Severity / subsystem | **MEDIUM** — venue normalization / HIP-3 compatibility safety gate |
| Exact files / functions | `backend/app/execution/hyperliquid.py::HyperliquidTestnetExecutionAdapter.normalize_order_request` (line 79); installed SDK `hyperliquid.info.Info` builder-perpetual asset mapping. |
| Preconditions | An instrument mapped to builder-perpetual asset index 110000 with size decimals 2 reaches the pure normalizer. Current three-market/native loader normally excludes it; this is a demonstrated compatibility-path defect, not current HIP-3 permission. |
| Reproduction | Embedded `test_builder_perpetual_is_classified_as_spot_for_price_precision` stubs only SDK metadata and calls the production normalization method for `audit:TEST`, BID 0.00123456, size 1. No Exchange or transmission is invoked. |
| Expected | Perpetual precision uses the perpetual decimal budget: `6 - szDecimals`, i.e. four fractional decimal places here; safe BID rounding would yield 0.0012 (or reject unsupported instrument class). |
| Actual | Adapter returns **0.001234**, six fractional places, from the spot decimal budget `8 - 2`. |
| Root cause | `max_decimals = 8 if asset >= 10_000 else 6` treats every high index as spot, although SDK builder perpetual indices start at 110000. Asset magnitude does not uniquely identify instrument class. |
| Impact | Claimed HIP-3 support would send invalidly normalized economics or fail venue acceptance. Native BTC/ETH/SOL behavior was not shown defective; current selector restrictions reduce reachability. |
| Bounded remediation | Derive class/precision from explicit validated instrument metadata; fail closed for unsupported namespace/class. Add native-perp, spot and builder-perp normalization/wire cases before any broader compatibility claim. |
| Readiness blocks | **Local native PAPER / native TESTNET:** no demonstrated effect. **Broad markets / HIP-3:** **BLOCKED**. **Production:** unsupported-class execution cannot be approved. |

### A3-005 — Stress preview accepts an unrepresentable SOL liquidity shock

| Required field | Confirmed evidence |
|---|---|
| Severity / subsystem | **MEDIUM** — portfolio stress validation / worker feasibility |
| Exact files / functions | `backend/app/portfolio_research/models.py::PortfolioShockAssumptions` (line 649); `preview.py::prepare`; `scenarios.py::_transform_dataset` (line 93); `stress.py::_execute_stress` (line 79). |
| Preconditions | SOL selected with native size precision 2; LIQUIDITY_SHOCK uses bid/ask depth multipliers `0.000001` and spread multiplier 3. Positive bounded assumptions satisfy schema. |
| Reproduction | Embedded `test_preview_accepts_subquantum_sol_depth_shock_then_native_stress_rejects`: preview succeeds, then invoke the actual native stress service with the prepared request. |
| Expected | An infeasible transformed-depth request is rejected during preview/admission with a clear market/precision reason, or preview truthfully marks the unresolved feasibility condition. |
| Actual | Preview accepts; baseline engines execute; transformation quantizes depth to zero and `SimulationFrame` validation rejects positive-size fields. No stress result is returned. |
| Root cause | Schema bounds multiplier above zero but does not check its product against market quantity quantum; preview validates workload/contracts, while transformed-dataset construction occurs after baseline execution. |
| Impact | An advertised admissible request consumes the shared worker and fails deterministically instead of producing the requested research result. Native default stresses still pass; no operational liquidity/order mutation occurs. |
| Bounded remediation | Validate transformed depth feasibility against captured profile precision before expensive work, retaining exact quantization. Do not silently invent minimum liquidity. Test threshold-adjacent SOL/BTC/ETH and explicit unsupported cases. |
| Readiness blocks | **Local PAPER / TESTNET:** isolated research only. **Stress research:** CONDITIONAL for admitted custom shocks. **Broad-market / production research claims:** precision-feasibility acceptance incomplete. |

### A3-006 — Missing language, low-contrast small text and inaccessible overflow

| Required field | Confirmed evidence |
|---|---|
| Severity / subsystem | **LOW** — frontend accessibility and financial readability |
| Exact files / functions | `frontend/index.html:1`; `frontend/src/styles.css` (`.riskHero small`, `.tableWrap`, `.panelHead span` affecting neutral agent badges); `frontend/src/phase5.css` (`.gaugeLabels`, `.inventoryState small`); `frontend/src/phase7.css` (`.perpPositionHead span`); `frontend/src/components/RiskFirewallPanel.tsx` table wrapper (line 44); `frontend/src/components/agents/AgentEvents.tsx` event list (line 10). |
| Preconditions | Current ordinary DEMO/PAPER page at desktop/mobile widths; assistive technology, small-text reading or keyboard-only overflow navigation. |
| Reproduction | Run current app, visit all 13 routes at 1440×1000 and 390×844, inject axe-core and run WCAG 2 A/AA. Inspect Risk at 390 px, Tab through overflowing risk tables/agent event list. Inspect root HTML and computed foreground/background/font size. |
| Expected | Declared document language; normal small text contrast at least 4.5:1; focusable/named scroll regions or reachable content; legible comparable financial values at narrow widths. |
| Actual | Missing `lang` in all 26 route-viewports; contrast violations in six (22 nodes); scroll-focus violations in seven (10 nodes). Examples: risk label ~10.83 px, `#61778b` on `#0a1420`, ratio 3.98; gauge 8 px `#596f83`, ratio 3.55; inventory label 8 px ratio 3.92; perp position heading 8 px ratio 4.20. Current Risk mobile currency values break into digit fragments. |
| Root cause | Root markup omits language, shared small muted text falls below contrast thresholds, and overflow wrappers/lists lack keyboard focusability. Narrow table cells permit hard financial-value wrapping. |
| Impact | Reduced screen-reader pronunciation, keyboard access and readability of financial/risk evidence. No document overflow or backend authorization defect was established. |
| Bounded remediation | Declare correct language; adjust existing text styles/size/contrast; make existing scroll regions semantically named and keyboard reachable; preserve financial tokens with usable table minimum widths. Recheck contrast, zoom and keyboard traversal at current widths. |
| Readiness blocks | **PAPER / TESTNET operator UI:** CONDITIONAL for accessible use. **Broad markets:** price formatting/width acceptance needed. **Production UX:** accessibility acceptance incomplete; no legal conformance conclusion claimed. |

### A3-007 — A normal Kraken heartbeat degrades a fresh valid reference

| Required field | Confirmed evidence |
|---|---|
| Severity / subsystem | **MEDIUM** — external reference transport/consensus availability |
| Exact files / functions | `backend/app/references/providers.py::KrakenProvider._run` (line 396), `normalize` (line 380), `ingest` and provider EvidenceState. |
| Preconditions | Kraken subscription receives a valid fresh ticker, then its documented `{"channel":"heartbeat"}` control message while the ticker remains within its stale threshold. |
| Reproduction | Embedded `test_kraken_healthy_fresh_ticker_is_degraded_by_valid_heartbeat` drives the actual async transport loop with those two frames; wait until both processed and inspect snapshot. |
| Expected | Heartbeat maintains transport liveness without fabricating price freshness or degrading a still-fresh valid ticker. |
| Actual | Fresh price 3000.5 remains, `stale=False`, but status becomes DEGRADED / unhealthy with `invalid Kraken update: unknown Kraken message type`. |
| Root cause | The loop filters subscription acknowledgments only; all other control frames enter ticker normalization, which rejects any non-ticker channel and changes health. |
| Impact | Normal quiet-market control traffic can remove a valid reference vote, trigger quorum degradation/HALT and cause avoidable availability/churn. It does not relax risk limits or invent a healthy stale price. Actual live ticker acceptance does not itself exercise this quiet-heartbeat sequence. |
| Bounded remediation | Explicitly distinguish documented heartbeat/status/acknowledgment control frames from price updates. Do not advance price/source time on heartbeats; continue rejecting malformed/unknown market data. Test quiet periods, stale transition and ticker recovery. |
| Readiness blocks | **Local PAPER / TESTNET with Kraken references:** CONDITIONAL availability. **Broader markets / production:** reference-health acceptance incomplete. |

Kraken documents automatic quiet-period heartbeat frames in its [WebSocket v2 heartbeat contract](https://docs.kraken.com/api/docs/websocket-v2/heartbeat/). The audit reproduction is deterministic fixture transport evidence, not an assertion that a particular production socket experienced a HALT.

### A3-008 — Locked Vite dependency includes published HIGH conditional exposure

| Required field | Confirmed evidence |
|---|---|
| Severity / subsystem | **HIGH (upstream advisory; conditional applicability)** — frontend development dependency/security |
| Exact files / functions | `frontend/package-lock.json` Vite 7.3.6; `frontend/package.json` Vite range; Vite's bundled `launch-editor` / development-server editor middleware. |
| Preconditions | For the HIGH advisory, affected Vite/launch-editor runs on **Windows**, with access to the vulnerable development-server editor path and crafted file arguments. Additional advisories have their own nondefault dev-server/path/editor conditions. This host is Linux. |
| Reproduction | Clean `npm ci`, `npm ls vite`, then `npm audit --json --prefix frontend`: Vite 7.3.6 installed; one vulnerable direct package, five advisories, aggregate HIGH, fix available. Compare pinned version with the advisory affected range `>=7.0.0 <=7.3.6`. No exploit payload was sent. |
| Expected | Reviewed dependency lock resolves a patched version and supported development setup is not exposed to these known advisories. |
| Actual | Lock reproducibly installs an affected version. HIGH advisory [GHSA-587h-7wmj-h5pm](https://github.com/advisories/GHSA-587h-7wmj-h5pm) describes a Windows `fs.existsSync()` bypass in launch-editor; patched Vite 7.3.7 is available. |
| Root cause | A newer patched package is allowed by the manifest range but the committed lock predates the patch; `npm ci` honors that lock. |
| Impact | Published command-execution risk under the advisory's Windows/editor conditions; no Linux RCE or exploitable production static bundle was demonstrated. The affected development setup needs remediation rather than an unqualified dependency-security PASS. |
| Bounded remediation | In a separate reviewed change, update Vite and lock to a patched compatible release, rerun clean install/typecheck/build/browser tests and audit, and verify supported dev-server exposure. No dependency mutation belongs in this audit-only PR. |
| Readiness blocks | **Local PAPER/backend:** no demonstrated financial defect. **Windows frontend development:** blocked until patched/conditions resolved. **TESTNET / broad markets:** not an asset-specific defect. **Production security:** dependency acceptance conditional; compiled-static exploit not established. |

The other reported advisories are [GHSA-698v-4r3x-3vcv](https://github.com/advisories/GHSA-698v-4r3x-3vcv) (Windows `%` escaping), [GHSA-r825-w8mm-5pxw](https://github.com/advisories/GHSA-r825-w8mm-5pxw) (editor CLI flag interpretation), [GHSA-9jrq-w75r-8gcw](https://github.com/advisories/GHSA-9jrq-w75r-8gcw) (cross-origin custom middleware), and [GHSA-rq7h-c2jc-7f22](https://github.com/advisories/GHSA-rq7h-c2jc-7f22) (non-Windows dev-server `fs.allow` bypass when project import paths match readable absolute host paths). The latter is relevant to Linux only under its stated path/exposure conditions; no qualifying project import or file exfiltration was established. Registry/advisory data was consulted during this audit; these are not inferred solely from a package age.

### Embedded code counterexamples

On the audited SHA, install the declared backend test dependencies, save the following as an ignored scratch test file, and run from repository root:

```bash
PYTHONPATH=backend:backend/tests python -m pytest -q -s work/audit3/probes_test.py
```

Actual result in the audit virtualenv: **6 passed, 1 upstream Starlette/httpx warning in 1.15 s**. The scratch harness initially expected a different validation-error phrase for the SOL failure; that assertion was corrected to inspect the actual `size` error location. No repository test or production assertion was changed. The code below includes that corrected assertion.

```python
"""Audit counterexamples: assertions record observed defects, not desired fixes."""
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import Settings
from app.runtime import HyperAmmRuntime
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.perp_context import demo_perp_context
from app.execution.models import OrderRequest
from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
from app.execution.paper import PaperExecutionAdapter
from app.execution.research import PaperExecutionAssumptions
from app.agents.evidence import AgentTelemetryStore
from app.agents.config import AgentConfig
from app.agents.predictive_adverse_selection import PredictiveAdverseSelectionAgent
from app.agents.ml_features import build_feature_vector
from test_agent_expansion import feature_evidence, artifact, T0


def test_builder_perpetual_is_classified_as_spot_for_price_precision():
    info=SimpleNamespace(name_to_asset=lambda _:110000,asset_to_sz_decimals={110000:2})
    req=OrderRequest(client_order_id='audit-only',market='audit:TEST',side='BID',price=D('.00123456'),size=D('1'))
    result=HyperliquidTestnetExecutionAdapter.normalize_order_request(SimpleNamespace(info=info),req)
    assert result.price == D('.001234')
    assert result.price != result.price.quantize(D('.0001'))
    print('HIP3 price',result.price,'native-perp valid rounding',D('.0012'))


def test_stale_perp_config_update_returns_500_and_preserves_state():
    from app.api.strategy import router
    from app.dependencies import runtime
    rt=HyperAmmRuntime(Settings(_env_file=None))
    app=FastAPI(); app.include_router(router,prefix='/api/v1')
    app.dependency_overrides[runtime]=lambda:rt
    with TestClient(app,raise_server_exceptions=False) as client:
        snap=MockMarketDataAdapter().snapshot_for(0)
        client.portal.call(rt.market._accept,snap)
        ctx=demo_perp_context(snap).model_copy(update={'updated_at':snap.latest_valid_update-timedelta(seconds=60)})
        rt.perp_context_service._context=ctx
        before=rt.config.model_dump(mode='json')
        response=client.put('/api/v1/strategy',json=before | {'concentration_factor':'9'})
        assert response.status_code==500
        assert rt.config.model_dump(mode='json')==before
        assert rt.lifecycle_state=='READY'
        print('stale-perp config HTTP',response.status_code,response.text)


@pytest.mark.asyncio
async def test_actual_modeled_paper_fill_becomes_nonsimulated_telemetry():
    telem=AgentTelemetryStore()
    adapter=PaperExecutionAdapter(clock=lambda:T0,assumptions=PaperExecutionAssumptions(mode='MODELED_CROSSING'))
    adapter.on_fill=lambda fill:telem.observe_fill(fill,None)
    snap=MockMarketDataAdapter().snapshot_for(0)
    snap.book.timestamp=T0
    adapter.update_market(snap,evidence_at=T0,evidence_key='audit-book')
    await adapter.submit_orders([OrderRequest(client_order_id='audit-modeled',market='ETH',side='BID',price=D('3001'),size=D('.1'))])
    assert len(telem.fills(10))==1
    fill=telem.fills(10)[0]
    assert fill.source.startswith('HYPOTHETICAL MODELED PAPER FILL')
    assert fill.simulated is False
    from app.research.ml.dataset import build_dataset
    from app.market_data.history import MarketObservation
    with pytest.raises(ValueError,match='classification mismatch'):
        build_dataset(market='ETH',evidence=[feature_evidence()],fills=[fill],
            observations=[MarketObservation(sequence=1,timestamp=T0+timedelta(seconds=5),mid_price=D('3002'))],
            source_fingerprint='a'*64,simulated=True)
    print('modeled PAPER fill telemetry simulated=',fill.simulated,'dataset rejects PAPER classification')


def test_predictive_shadow_accepts_explicitly_stale_features():
    agent=PredictiveAdverseSelectionAgent(AgentConfig())
    agent.install_artifact(artifact())
    evidence=feature_evidence(perp_stale=True,book_timestamp=T0-timedelta(days=1))
    build_feature_vector(evidence,'BID')
    result=agent.evaluate(evidence)
    assert result.health.value=='READY' and result.state.value=='PREDICTED'
    assert result.affects_quotes is False
    print('stale features:',result.health,result.state,'probability=',result.metrics.bid_adverse_probability)


@pytest.mark.asyncio
async def test_preview_accepts_subquantum_sol_depth_shock_then_native_stress_rejects():
    from test_phase175_terminal import draft,profiles
    from phase174_fixtures import request_for
    from app.portfolio_research.preview import prepare
    from app.portfolio_research.models import PortfolioStressRequest
    from app.simulation.service import SimulationService
    scenario=request_for('LIQUIDITY_SHOCK',markets=('SOL',),assumptions={
        'bid_depth_multiplier':'0.000001','ask_depth_multiplier':'0.000001','spread_multiplier':'3'}).scenario
    prepared=prepare(draft(markets=('SOL',),stress=scenario),profiles())
    request=PortfolioStressRequest(config=prepared.config,config_fingerprint=prepared.config_fingerprint,scenario=scenario)
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as rejected:
        await SimulationService().stress_portfolio_research(request=request)
    assert any('size' in e['loc'] for e in rejected.value.errors())
    print('SOL sub-quantum shock: preview accepted; native stress rejected zero quantized depth')


@pytest.mark.asyncio
async def test_kraken_healthy_fresh_ticker_is_degraded_by_valid_heartbeat():
    import asyncio,json
    from app.references.providers import KrakenProvider
    from app.market_data.models import utcnow
    processed=asyncio.Event()
    class Connection:
        async def __aenter__(self): return self
        async def __aexit__(self,*_): pass
        async def send(self,_): pass
        def __aiter__(self): return self.messages()
        async def messages(self):
            yield json.dumps({'channel':'ticker','data':[{'symbol':'ETH/USD','bid':3000,'ask':3001,'timestamp':utcnow().isoformat()}]})
            assert provider.snapshot().healthy
            yield json.dumps({'channel':'heartbeat'})
            processed.set()
            await asyncio.Event().wait()
    provider=KrakenProvider(market='ETH',enabled=True,symbol='ETH/USD',stale_after_seconds=5,websocket_factory=lambda _:Connection())
    try:
        await provider.start(); await asyncio.wait_for(processed.wait(),2)
        result=provider.snapshot()
        assert result.status.value=='DEGRADED' and not result.healthy and not result.stale
        assert result.price==D('3000.5') and 'unknown Kraken message type' in result.error
        print('valid Kraken heartbeat ->',result.status,'stale=',result.stale,'error=',result.error)
    finally:await provider.stop()
```

## 15. Unverified Concerns and External Blockers

These are not additional confirmed A3 bugs. The distinction prevents fixture success or plausible risk from being reported as observed external failure.

| Concern / acceptance gate | Status and specific missing evidence |
|---|---|
| Signed TESTNET CREATE/KEEP/REPLACE/CANCEL, duplicate/orphan reconciliation, partial fills and uncertain positions | **NOT RUN**, explicitly outside audit authorization. No signing enabled; A1-001/A1-006 remain PARTIAL. |
| Actual production/live execution | **BLOCKED** by durable recovery, remote security/operational model, venue acceptance and economic calibration. No real orders attempted. |
| Operational SDK pressure and repeated mode-switch/network-fault soak | **UNVERIFIED** beyond source/native tests; newer multi-market short public reconnect passed. Do not transfer that pass to every older bridge lifecycle or long-duration resource behavior. |
| RedStone public HTTP | **BLOCKED in this environment:** actual ProxyError and no accepted price. Fixture parser tests pass separately. |
| RedStone Live / CoinGecko | **NOT RUN:** configured endpoint/key or Demo/Pro key unavailable. No fake credentials or provider PASS. |
| Yahoo optional live acceptance | **NOT RUN:** optional extra not installed; no successful external response claimed. Explicit symbol/market limitations remain. |
| Kraken quiet control traffic | Confirmed fixture defect A3-007; actual fresh ticker accepted, but live long-duration/reference-quorum acceptance remains unverified. |
| Authenticated historical exchange dataset | **NOT RUN:** current browser catalog is generated/user-asserted fixture evidence, not authenticated original history. Hash validation cannot establish upstream truth. |
| Optional sklearn training and real predictive calibration | **NOT RUN:** optional test skipped without sklearn. Heuristic confidence and SHADOW probabilities have no new empirical calibration acceptance. |
| macOS/Windows runtime lifecycle | **NOT RUN:** Linux-only host. Twenty fresh Linux repeats do not close A2-005 across platforms. Windows exploit not executed. |
| Redis multi-host failover / sustained outage / broad version matrix | **NOT RUN:** local 7.4.11 checks passed; no production Redis infrastructure was available or claimed. |
| Phase 16.6B durable lifecycle/recovery | **BLOCKED:** no durable financial state/research-receipt recovery protocol. Cache/lease reconnect and manual browser rerun are different capabilities. |
| Collapsed-price venue cost policy | **PARTIAL A2-003:** arithmetic/visual truth supported; explicit operational message/cancel policy and actual venue cost acceptance deferred. |
| Very long-lived active/UNKNOWN evidence | Correctly pinned, not evicted. Dedicated sustained orphan-resolution/backpressure acceptance remains unverified; no measured unbounded leak is claimed. |
| Frontend performance and comprehensive assistive-technology testing | No profiling SLA/user study/screen-reader matrix. Root subscriptions/bundle size/dense mobile layouts are debt; confirmed accessibility findings are scoped to actual checks. |
| Python dependency vulnerability assessment | No dedicated vulnerability-scanner result; clean install/test success does not establish absence of advisories. A1-017 reproducibility policy remains partial. |

## 16. Native Test Results

All totals below are **new executions at the audited SHA**, even where they match Phase 17.6 historical counts. Full/focused suites overlap; do not sum them into a unique-test total. Logs were retained in ignored scratch during the audit.

| Execution | Actual result | Classification / limits |
|---|---|---|
| Fresh `pip install -e './backend[test,redis]'` and frontend `npm ci --prefix frontend` | Both succeeded; manifests/lock unchanged | Resolved Python versions recorded in section 2; no optional ML/Yahoo extras. |
| From `backend`: `../work/audit3/venv/bin/python -m pytest -q` | **3,302 passed, 1 skipped, 2 warnings, 623.79 s** | Entire native backend suite, not signed/provider certification. |
| `npm run typecheck --prefix frontend` | **PASS**, exit 0 | TypeScript validation. |
| `npm run build --prefix frontend` | **PASS**, exit 0, Vite build 2.47 s | TanStack directive and large-chunk warnings retained; no warning suppressed. |
| `npm test --prefix frontend` | **788 passed, 0 failed, 0 skipped**, 15.446 s | Node/native frontend tests. |
| Focused backend: `test_phase122_amm_hardening.py test_amm.py test_strategy_risk.py test_phase8_authorization.py` | **92 passed, 1 warning, 1.65 s** | Includes 56 Phase 12.2 A2 adversarial tests; no actual TESTNET transmission. |
| Fresh normal `backend[test]`; 20 fresh subprocesses of `test_redis_lifespan.py test_phase12_websocket.py test_phase121_websocket_reliability.py` | **20/20 successful; 28 passes and 1 deprecation warning per run; 560 checks; 158.482 s aggregate** | Normal-extra redis 8.1.0; Linux. Full extra run uses redis 6.4.0. Original teardown failure not reproduced here; A2-005 still PARTIAL. |
| Independent AMM sweep | **1,000 cases PASS** | Seed 300; actual harness below; not a statistical proof or final-risk authorization test. |
| Six independent defect counterexamples | **6 passed, 1 warning, 1.15 s** | Passing assertions record defective actual behavior; see section 14. |
| Physical Redis runner | **PASS, 7 checks, 0.34 s**, Redis 7.4.11 | Actual server, local DEMO/PAPER only. |
| Public Hyperliquid read-only runner | **PASS, 31.772 s**, BTC/ETH/SOL REST/context/WS/reconnect/cleanup | Actual public traffic; no signing, no operational mode-switch soak. |
| Direct optional reference probes | Kraken ETH/USD **HEALTHY**, fresh accepted BBO; RedStone public **DEGRADED ProxyError** | Only Kraken ticker acceptance succeeded. RedStone Live/CoinGecko/Yahoo NOT RUN. |
| `npm audit --json --prefix frontend` | Exit **1**, one vulnerable package / HIGH aggregate / five advisories | Expected vulnerability finding, **not a clean audit**. A3-008; no auto-fix. |

The backend skip was `test_agent_expansion.py::test_offline_training_optional_import_and_real_coefficient_export`, due to missing optional sklearn. Warnings were (1) Starlette's httpx TestClient deprecation recommending future httpx2 migration and (2) a Pydantic serialization warning for deliberately corrupted `ConcentrationSelection` in `test_phase174_provenance.py::test_resealed_tampering_still_rejected[selection]`. The second is associated with an intentional tamper case that passes rejection; it is not concealed as zero warnings. No undeclared httpx2 was added.

Reproducible repository-runner commands (run from root unless `cd` shown; substitute your fresh interpreter):

```bash
python -m venv work/audit3/venv
work/audit3/venv/bin/pip install -e './backend[test,redis]'
npm ci --prefix frontend
(cd backend && ../work/audit3/venv/bin/python -m pytest -q)
npm run typecheck --prefix frontend
npm run build --prefix frontend
npm test --prefix frontend

PYTHONPATH=backend work/audit3/venv/bin/python backend/tests/phase155a_redis_acceptance.py \
  --redis-server /path/to/redis-server --output work/audit3/physical-redis.json
work/audit3/venv/bin/python backend/tests/phase155b_live_readonly_acceptance.py \
  --allow-public-network --seconds 30 --reconnect --output work/audit3/live-provider.json
(cd backend && PYTHONPATH=tests ../work/audit3/venv/bin/python tests/phase176_resources.py --case 3)
(cd backend && PYTHONPATH=tests ../work/audit3/venv/bin/python tests/phase176_resources.py --case 5)
```

Independent AMM sweep, executable with `PYTHONPATH=backend`:

```python
from decimal import Decimal as D
from random import Random
from collections import Counter
from app.amm.models import AmmModel
from app.amm.virtual_reserves import initialize_virtual_pool,recenter_pool
from app.amm.discretizer import compile_quotes
from app.amm.numeric import executable_distance

r=Random(300)
counts=Counter()
for _ in range(1000):
    fair=D(r.randint(100,999))/100 * D(10)**r.randint(-12,12)
    base=D(10)**r.randint(-50,100)
    pool=recenter_pool(initialize_virtual_pool(base,base*fair),fair)
    levels=r.choice([1,2,8,20,50]); model=r.choice(list(AmmModel))
    distance=D(r.choice(['.001','.2','100','2500']))
    tick=fair*D(r.choice(['1e-8','1e-4','.01','.25']))
    quotes=compile_quotes(pool,fair,model,levels,distance,D(5),tick,4,
                          concentration_factor=D(8),base_order_size=D('.05'))
    assert abs(pool.reserve_base*pool.reserve_quote-pool.k)<=pool.k*D('1e-24')
    assert len({(q.side,q.level_index) for q in quotes})==len(quotes)==levels*2
    assert all(q.price>0 and q.size>0 and q.distance_bps==executable_distance(q.price,fair) for q in quotes)
    assert all(sum((q.size for q in quotes if q.side==side),D(0))<=5 for side in ('BID','ASK'))
    bids=[q.price for q in quotes if q.side=='BID']; asks=[q.price for q in quotes if q.side=='ASK']
    assert bids==sorted(bids,reverse=True) and asks==sorted(asks) and max(bids)<fair<min(asks)
    counts[model.value]+=1
print('1000 seeded independent AMM invariant/ordering/distance/budget cases PASS',dict(counts))
```

## 17. Browser/Screenshot Acceptance

### Current Chromium execution

| Runner / scope | Actual outcome | Financial/source and failure semantics |
|---|---|---|
| Existing `frontend/tests/browser-phase176.py` | **PASS: 19 workflows, five viewports, 20 section checks, 58 native engine invocations**; zero page/normal console errors; three expected injected-fault console entries | Real configured SDK catalog and native portfolio/stress engines, exact 18-place allocation, 1/2/3 markets, all six stresses, incomplete 300-frame/two-leg `FINAL_ONLY` with blocked temporal charts/known HALT, cancellation/busy/failure/restart retirement; operational authority changed fields empty. |
| Existing `browser-phase165c2.py --phase166c --phase166d` | **PASS: 21 workflow entries**, five viewports; zero page errors and zero **unexpected** console/network failures; 59.97 s | Generated/user-asserted source fixtures, actual native replay/comparison/Scenario/Vault engines; 43 recorded mutating research requests. 61 console entries and 51 network failures are retained expected startup/process-death/fault/cancellation evidence, not reported as zero total errors. |
| Existing older `browser-phase1641.py` | **FAIL**, first Historical Replay heading wait; zero completed workflows, zero page errors, 18.956 s | Harness opens current Simulation default Scenario tab but never selects Historical Replay. Four fixture WebSocket 403 diagnostics also recorded. This is an obsolete harness entry point, not proof the workspace is absent; newer harness selects it and passes. No test changed or weakened. |
| Additional current route/axe sweep | **COMPLETE: 13 routes × two viewports = 26**, zero page/console errors, zero document horizontal overflow, zero unlabeled inputs/selects | Actual DEMO/PAPER app; Start/Kill/Resume workflow performed; accessibility **not passed** (A3-006). No live/signed orders. |

Repository harness commands used:

```bash
python frontend/tests/browser-phase176.py \
  --python /absolute/path/to/work/audit3/venv/bin/python --output work/audit3/browser176
python frontend/tests/browser-phase165c2.py \
  --python /absolute/path/to/work/audit3/venv/bin/python \
  --phase166c --phase166d --output work/audit3/browser166
python frontend/tests/browser-phase1641.py \
  --python /absolute/path/to/work/audit3/venv/bin/python --output work/audit3/browser1641
```

Five-width current acceptance used 1920/1440/1024/768/390 CSS widths; portfolio viewport heights vary by runner, replay used 1080/900/768/900/844. These are browser settings, not full-page PNG heights. New route sweep produced 26 images, portfolio two and replay six (**34 new screenshots**), retained only in scratch. Current portfolio desktop/mobile, Dashboard desktop, Risk mobile, Agents mobile and replay mobile-preflight pixels received direct larger-image inspection; tall images may be viewer-scaled. The current Risk mobile issue and axe results support A3-006; no claim that every new screenshot was read pixel-for-pixel at native zoom is made.

### Historical screenshot method and matrix

There were **118 accessible acceptance PNGs**, zero JPEG/WebP acceptance images and zero decode failures. Every one appeared in an actually viewed six-image contact sheet (20 sheets total). Thus **118/118 were inventoried, decoded and visually inspected at overview scale; zero NOT INSPECTED**. Representative execution mobile and later portfolio images were also inspected at larger scale. Many captures are several thousand pixels tall (some above 15,000); overview legibility is limited. `OV` below means overview pixel inspection, **not** a full-text/contrast/layout certification. Lack of an overview defect is not a PASS of small print. Phase/date records identify historical evidence; no independently verified capture date is inferred from file modification times.

The matrix separates image dimensions from viewport. `wNNN` means filename/harness width evidence; viewport height is unrecorded here unless stated. `unknown` means neither filename nor recorded matrix establishes viewport; the image's width alone is not used to invent a viewport. A full-page image's height is document capture height. Severity `—` means no new confirmed finding established from that overview alone; historic mobile density is observation, with current actionable defects recorded separately in A3-006.

| # / Screenshot | Page or workspace | Viewport evidence | Image pixels (W×H) | Evidence phase | Pixel finding / inspection | Severity |
|---|---|---|---|---|---|---|
| 001 [dashboard-1440.png](docs/acceptance/phase1321/dashboard-1440.png) | Dashboard | w1440; h unknown | 1440×2078 | phase1321 | OV; no specific defect established at overview scale | — |
| 002 [execution-details-1440.png](docs/acceptance/phase1321/execution-details-1440.png) | Execution | w1440; h unknown | 1440×2700 | phase1321 | OV; no specific defect established at overview scale | — |
| 003 [execution-details-390.png](docs/acceptance/phase1321/execution-details-390.png) | Execution | w390; h unknown | 390×3407 | phase1321 | OV + larger view; wrapped IDs/values and tall history; historical only | — |
| 004 [markets-390.png](docs/acceptance/phase1321/markets-390.png) | Markets | w390; h unknown | 390×3061 | phase1321 | OV; dense mobile layout; small text requires larger review | — |
| 005 [agents-1440.png](docs/acceptance/phase1331/agents-1440.png) | Agents | w1440; h unknown | 1440×4459 | phase1331 | OV; no specific defect established at overview scale | — |
| 006 [vault-1440.png](docs/acceptance/phase1331/vault-1440.png) | Vault | w1440; h unknown | 1440×3153 | phase1331 | OV; no specific defect established at overview scale | — |
| 007 [vault-ledger-fixture-1440.png](docs/acceptance/phase1331/vault-ledger-fixture-1440.png) | Vault | w1440; h unknown | 1440×3653 | phase1331 | OV; no specific defect established at overview scale | — |
| 008 [vault-ledger-fixture-390.png](docs/acceptance/phase1331/vault-ledger-fixture-390.png) | Vault | w390; h unknown | 390×6109 | phase1331 | OV; dense mobile layout; small text requires larger review | — |
| 009 [analytics-fixture-390.png](docs/acceptance/phase1332/analytics-fixture-390.png) | Analytics | w390; h unknown | 390×4673 | phase1332 | OV; dense mobile layout; small text requires larger review | — |
| 010 [analytics-live-1440.png](docs/acceptance/phase1332/analytics-live-1440.png) | Analytics | w1440; h unknown | 1440×2358 | phase1332 | OV; no specific defect established at overview scale | — |
| 011 [simulation-fixture-390.png](docs/acceptance/phase1332/simulation-fixture-390.png) | Simulation | w390; h unknown | 390×11617 | phase1332 | OV; dense mobile layout; small text requires larger review | — |
| 012 [simulation-live-1440.png](docs/acceptance/phase1332/simulation-live-1440.png) | Simulation | w1440; h unknown | 1440×5584 | phase1332 | OV; no specific defect established at overview scale | — |
| 013 [logs-fixture-390.png](docs/acceptance/phase1333/logs-fixture-390.png) | Logs | w390; h unknown | 366×1807 | phase1333 | OV; dense mobile layout; small text requires larger review | — |
| 014 [logs-live-1440.png](docs/acceptance/phase1333/logs-live-1440.png) | Logs | w1440; h unknown | 1440×900 | phase1333 | OV; no specific defect established at overview scale | — |
| 015 [settings-fixture-390.png](docs/acceptance/phase1333/settings-fixture-390.png) | Settings | w390; h unknown | 366×3668 | phase1333 | OV; dense mobile layout; small text requires larger review | — |
| 016 [settings-live-1440.png](docs/acceptance/phase1333/settings-live-1440.png) | Settings | w1440; h unknown | 1440×2561 | phase1333 | OV; no specific defect established at overview scale | — |
| 017 [simulation-live-1440.png](docs/acceptance/phase14/simulation-live-1440.png) | Simulation | w1440; h unknown | 1180×1456 | phase14 | OV; no specific defect established at overview scale | — |
| 018 [vault-live-1440.png](docs/acceptance/phase14/vault-live-1440.png) | Vault | w1440; h unknown | 1180×1433 | phase14 | OV; no specific defect established at overview scale | — |
| 019 [vault-live-390.png](docs/acceptance/phase14/vault-live-390.png) | Vault | w390; h unknown | 366×2742 | phase14 | OV; dense mobile layout; small text requires larger review | — |
| 020 [btc-simulation-1440.png](docs/acceptance/phase146/btc-simulation-1440.png) | Simulation | w1440; h unknown | 1440×900 | phase146 | OV; no specific defect established at overview scale | — |
| 021 [btc-vault-1440.png](docs/acceptance/phase146/btc-vault-1440.png) | Vault | w1440; h unknown | 1440×900 | phase146 | OV; no specific defect established at overview scale | — |
| 022 [btc-vault-390.png](docs/acceptance/phase146/btc-vault-390.png) | Vault | w390; h unknown | 390×844 | phase146 | OV; dense mobile layout; small text requires larger review | — |
| 023 [btc-1440.png](docs/acceptance/phase153/btc-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase153 | OV; no specific defect established at overview scale | — |
| 024 [disabled-1440.png](docs/acceptance/phase153/disabled-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase153 | OV; no specific defect established at overview scale | — |
| 025 [eth-1440.png](docs/acceptance/phase153/eth-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase153 | OV; no specific defect established at overview scale | — |
| 026 [mobile-390.png](docs/acceptance/phase153/mobile-390.png) | Markets / live observation | w390; h unknown | 390×844 | phase153 | OV; dense mobile layout; small text requires larger review | — |
| 027 [reconnect-1440.png](docs/acceptance/phase153/reconnect-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase153 | OV; no specific defect established at overview scale | — |
| 028 [sol-1440.png](docs/acceptance/phase153/sol-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase153 | OV; no specific defect established at overview scale | — |
| 029 [btc-comparison-1440.png](docs/acceptance/phase154/btc-comparison-1440.png) | Replay / comparison | w1440; h unknown | 1440×900 | phase154 | OV; no specific defect established at overview scale | — |
| 030 [comparison-1440.png](docs/acceptance/phase154/comparison-1440.png) | Replay / comparison | w1440; h unknown | 1440×900 | phase154 | OV; no specific defect established at overview scale | — |
| 031 [comparison-390.png](docs/acceptance/phase154/comparison-390.png) | Replay / comparison | w390; h unknown | 390×844 | phase154 | OV; dense mobile layout; small text requires larger review | — |
| 032 [btc-comparison-1440.png](docs/acceptance/phase155a/btc-comparison-1440.png) | Replay / comparison | w1440; h unknown | 1440×900 | phase155a | OV; no specific defect established at overview scale | — |
| 033 [comparison-1440.png](docs/acceptance/phase155a/comparison-1440.png) | Replay / comparison | w1440; h unknown | 1440×900 | phase155a | OV; no specific defect established at overview scale | — |
| 034 [comparison-390.png](docs/acceptance/phase155a/comparison-390.png) | Replay / comparison | w390; h unknown | 390×844 | phase155a | OV; dense mobile layout; small text requires larger review | — |
| 035 [live-markets-1440.png](docs/acceptance/phase155a/live-markets-1440.png) | Markets | w1440; h unknown | 1440×3150 | phase155a | OV; no specific defect established at overview scale | — |
| 036 [market-comparison-1440.png](docs/acceptance/phase155a/market-comparison-1440.png) | Replay / comparison | w1440; h unknown | 1440×5087 | phase155a | OV; no specific defect established at overview scale | — |
| 037 [market-comparison-390.png](docs/acceptance/phase155a/market-comparison-390.png) | Replay / comparison | w390; h unknown | 390×8063 | phase155a | OV; dense mobile layout; small text requires larger review | — |
| 038 [simulation-1440.png](docs/acceptance/phase155a/simulation-1440.png) | Simulation | w1440; h unknown | 1440×1766 | phase155a | OV; no specific defect established at overview scale | — |
| 039 [stale-evidence-1440.png](docs/acceptance/phase155a/stale-evidence-1440.png) | Replay / comparison | w1440; h unknown | 1440×5087 | phase155a | OV; no specific defect established at overview scale | — |
| 040 [fixture-btc-overview-desktop.png](docs/acceptance/phase155b/fixture-btc-overview-desktop.png) | Markets / live observation | unknown | 1440×3031 | phase155b | OV; no specific defect established at overview scale | — |
| 041 [fixture-degraded-provider-desktop.png](docs/acceptance/phase155b/fixture-degraded-provider-desktop.png) | Markets / live observation | unknown | 1440×3031 | phase155b | OV; no specific defect established at overview scale | — |
| 042 [fixture-disconnected-desktop.png](docs/acceptance/phase155b/fixture-disconnected-desktop.png) | Markets / live observation | unknown | 1440×2776 | phase155b | OV; no specific defect established at overview scale | — |
| 043 [fixture-eth-orderbook-desktop.png](docs/acceptance/phase155b/fixture-eth-orderbook-desktop.png) | Markets / live observation | unknown | 1440×3031 | phase155b | OV; no specific defect established at overview scale | — |
| 044 [fixture-live-intelligence-mobile.png](docs/acceptance/phase155b/fixture-live-intelligence-mobile.png) | Markets / live observation | unknown | 390×5003 | phase155b | OV; dense mobile layout; small text requires larger review | — |
| 045 [fixture-sol-perpetual-desktop.png](docs/acceptance/phase155b/fixture-sol-perpetual-desktop.png) | Markets / live observation | unknown | 1440×3031 | phase155b | OV; no specific defect established at overview scale | — |
| 046 [btc-comparison-1440.png](docs/acceptance/phase155b/regression/btc-comparison-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase155b / regression | OV; no specific defect established at overview scale | — |
| 047 [comparison-1440.png](docs/acceptance/phase155b/regression/comparison-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase155b / regression | OV; no specific defect established at overview scale | — |
| 048 [comparison-390.png](docs/acceptance/phase155b/regression/comparison-390.png) | Markets / live observation | w390; h unknown | 390×844 | phase155b / regression | OV; dense mobile layout; small text requires larger review | — |
| 049 [live-markets-1440.png](docs/acceptance/phase155b/regression/live-markets-1440.png) | Markets | w1440; h unknown | 1440×3150 | phase155b / regression | OV; no specific defect established at overview scale | — |
| 050 [market-comparison-1440.png](docs/acceptance/phase155b/regression/market-comparison-1440.png) | Markets / live observation | w1440; h unknown | 1440×5087 | phase155b / regression | OV; no specific defect established at overview scale | — |
| 051 [market-comparison-390.png](docs/acceptance/phase155b/regression/market-comparison-390.png) | Markets / live observation | w390; h unknown | 390×8063 | phase155b / regression | OV; dense mobile layout; small text requires larger review | — |
| 052 [simulation-1440.png](docs/acceptance/phase155b/regression/simulation-1440.png) | Simulation | w1440; h unknown | 1440×1766 | phase155b / regression | OV; no specific defect established at overview scale | — |
| 053 [stale-evidence-1440.png](docs/acceptance/phase155b/regression/stale-evidence-1440.png) | Markets / live observation | w1440; h unknown | 1440×5087 | phase155b / regression | OV; no specific defect established at overview scale | — |
| 054 [btc-1440.png](docs/acceptance/phase155b/terminal-independence/btc-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase155b / terminal-independence | OV; no specific defect established at overview scale | — |
| 055 [disabled-1440.png](docs/acceptance/phase155b/terminal-independence/disabled-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase155b / terminal-independence | OV; no specific defect established at overview scale | — |
| 056 [eth-1440.png](docs/acceptance/phase155b/terminal-independence/eth-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase155b / terminal-independence | OV; no specific defect established at overview scale | — |
| 057 [mobile-390.png](docs/acceptance/phase155b/terminal-independence/mobile-390.png) | Markets / live observation | w390; h unknown | 390×844 | phase155b / terminal-independence | OV; dense mobile layout; small text requires larger review | — |
| 058 [reconnect-1440.png](docs/acceptance/phase155b/terminal-independence/reconnect-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase155b / terminal-independence | OV; no specific defect established at overview scale | — |
| 059 [sol-1440.png](docs/acceptance/phase155b/terminal-independence/sol-1440.png) | Markets / live observation | w1440; h unknown | 1440×900 | phase155b / terminal-independence | OV; no specific defect established at overview scale | — |
| 060 [fixture-disabled-503.png](docs/acceptance/phase1641/fixture-disabled-503.png) | Replay / comparison | unknown | 1440×2660 | phase1641 | OV; no specific defect established at overview scale | — |
| 061 [fixture-missing-economics-422.png](docs/acceptance/phase1641/fixture-missing-economics-422.png) | Replay / comparison | unknown | 1440×3048 | phase1641 | OV; no specific defect established at overview scale | — |
| 062 [fixture-modeled-gap-1024.png](docs/acceptance/phase1641/fixture-modeled-gap-1024.png) | Replay / comparison | w1024; h unknown | 1024×8675 | phase1641 | OV; no specific defect established at overview scale | — |
| 063 [fixture-modeled-gap-1440.png](docs/acceptance/phase1641/fixture-modeled-gap-1440.png) | Replay / comparison | w1440; h unknown | 1440×6521 | phase1641 | OV; no specific defect established at overview scale | — |
| 064 [fixture-modeled-gap-1920.png](docs/acceptance/phase1641/fixture-modeled-gap-1920.png) | Replay / comparison | w1920; h unknown | 1920×6283 | phase1641 | OV; no specific defect established at overview scale | — |
| 065 [fixture-modeled-gap-390.png](docs/acceptance/phase1641/fixture-modeled-gap-390.png) | Replay / comparison | w390; h unknown | 390×12472 | phase1641 | OV; dense mobile layout; small text requires larger review | — |
| 066 [fixture-modeled-gap-768.png](docs/acceptance/phase1641/fixture-modeled-gap-768.png) | Replay / comparison | w768; h unknown | 768×10567 | phase1641 | OV; no specific defect established at overview scale | — |
| 067 [fixture-positive-partial-fills.png](docs/acceptance/phase1641/fixture-positive-partial-fills.png) | Replay / comparison | unknown | 1440×5045 | phase1641 | OV; no specific defect established at overview scale | — |
| 068 [fixture-worker-busy-429.png](docs/acceptance/phase1641/fixture-worker-busy-429.png) | Replay / comparison | unknown | 1440×2913 | phase1641 | OV; no specific defect established at overview scale | — |
| 069 [btc-context-and-traces-1440.png](docs/acceptance/phase165c2/btc-context-and-traces-1440.png) | Replay / comparison | w1440; h unknown | 1440×8872 | phase165c2 | OV; no specific defect established at overview scale | — |
| 070 [comparison-1024.png](docs/acceptance/phase165c2/comparison-1024.png) | Replay / comparison | w1024; h unknown | 1024×9589 | phase165c2 | OV; no specific defect established at overview scale | — |
| 071 [comparison-1440.png](docs/acceptance/phase165c2/comparison-1440.png) | Replay / comparison | w1440; h unknown | 1440×8872 | phase165c2 | OV; no specific defect established at overview scale | — |
| 072 [comparison-1920.png](docs/acceptance/phase165c2/comparison-1920.png) | Replay / comparison | w1920; h unknown | 1920×8651 | phase165c2 | OV; no specific defect established at overview scale | — |
| 073 [comparison-390.png](docs/acceptance/phase165c2/comparison-390.png) | Replay / comparison | w390; h unknown | 390×15768 | phase165c2 | OV; dense mobile layout; small text requires larger review | — |
| 074 [comparison-768.png](docs/acceptance/phase165c2/comparison-768.png) | Replay / comparison | w768; h unknown | 768×13512 | phase165c2 | OV; no specific defect established at overview scale | — |
| 075 [independent-gap-segment-2.png](docs/acceptance/phase165c2/independent-gap-segment-2.png) | Replay / comparison | unknown | 1440×8400 | phase165c2 | OV; no specific defect established at overview scale | — |
| 076 [market-incomparable.png](docs/acceptance/phase165c2/market-incomparable.png) | Replay / comparison | unknown | 1440×4589 | phase165c2 | OV; no specific defect established at overview scale | — |
| 077 [vault-exact-decimal-390.png](docs/acceptance/phase165c2/vault-exact-decimal-390.png) | Vault | w390; h unknown | 390×14616 | phase165c2 | OV; dense mobile layout; small text requires larger review | — |
| 078 [btc-context-and-traces-1440.png](docs/acceptance/phase165d/btc-context-and-traces-1440.png) | Replay / comparison | w1440; h unknown | 1440×8872 | phase165d | OV; no specific defect established at overview scale | — |
| 079 [comparison-1024.png](docs/acceptance/phase165d/comparison-1024.png) | Replay / comparison | w1024; h unknown | 1024×9589 | phase165d | OV; no specific defect established at overview scale | — |
| 080 [comparison-1440.png](docs/acceptance/phase165d/comparison-1440.png) | Replay / comparison | w1440; h unknown | 1440×8872 | phase165d | OV; no specific defect established at overview scale | — |
| 081 [comparison-1920.png](docs/acceptance/phase165d/comparison-1920.png) | Replay / comparison | w1920; h unknown | 1920×8651 | phase165d | OV; no specific defect established at overview scale | — |
| 082 [comparison-390.png](docs/acceptance/phase165d/comparison-390.png) | Replay / comparison | w390; h unknown | 390×15768 | phase165d | OV; dense mobile layout; small text requires larger review | — |
| 083 [comparison-768.png](docs/acceptance/phase165d/comparison-768.png) | Replay / comparison | w768; h unknown | 768×13512 | phase165d | OV; no specific defect established at overview scale | — |
| 084 [equity-1024.png](docs/acceptance/phase165d/equity-1024.png) | Replay / comparison | w1024; h unknown | 353×436 | phase165d | OV; no specific defect established at overview scale | — |
| 085 [equity-1440.png](docs/acceptance/phase165d/equity-1440.png) | Replay / comparison | w1440; h unknown | 540×430 | phase165d | OV; no specific defect established at overview scale | — |
| 086 [equity-1920.png](docs/acceptance/phase165d/equity-1920.png) | Replay / comparison | w1920; h unknown | 780×430 | phase165d | OV; no specific defect established at overview scale | — |
| 087 [equity-390.png](docs/acceptance/phase165d/equity-390.png) | Replay / comparison | w390; h unknown | 320×436 | phase165d | OV; dense mobile layout; small text requires larger review | — |
| 088 [equity-768.png](docs/acceptance/phase165d/equity-768.png) | Replay / comparison | w768; h unknown | 490×430 | phase165d | OV; no specific defect established at overview scale | — |
| 089 [independent-gap-segment-2.png](docs/acceptance/phase165d/independent-gap-segment-2.png) | Replay / comparison | unknown | 1440×8400 | phase165d | OV; no specific defect established at overview scale | — |
| 090 [large-comparison-1000.png](docs/acceptance/phase165d/large-comparison-1000.png) | Replay / comparison | unknown (1000 denotes workload) | 1440×8395 | phase165d | OV; no specific defect established at overview scale | — |
| 091 [large-metrics-1440.png](docs/acceptance/phase165d/large-metrics-1440.png) | Replay / comparison | w1440; h unknown | 1180×753 | phase165d | OV; no specific defect established at overview scale | — |
| 092 [market-incomparable.png](docs/acceptance/phase165d/market-incomparable.png) | Replay / comparison | unknown | 1440×4589 | phase165d | OV; no specific defect established at overview scale | — |
| 093 [metrics-1024.png](docs/acceptance/phase165d/metrics-1024.png) | Replay / comparison | w1024; h unknown | 806×1133 | phase165d | OV; no specific defect established at overview scale | — |
| 094 [metrics-1440.png](docs/acceptance/phase165d/metrics-1440.png) | Replay / comparison | w1440; h unknown | 1180×1113 | phase165d | OV; no specific defect established at overview scale | — |
| 095 [metrics-1920.png](docs/acceptance/phase165d/metrics-1920.png) | Replay / comparison | w1920; h unknown | 1660×1112 | phase165d | OV; no specific defect established at overview scale | — |
| 096 [metrics-390.png](docs/acceptance/phase165d/metrics-390.png) | Replay / comparison | w390; h unknown | 366×1188 | phase165d | OV; dense mobile layout; small text requires larger review | — |
| 097 [metrics-768.png](docs/acceptance/phase165d/metrics-768.png) | Replay / comparison | w768; h unknown | 550×1180 | phase165d | OV; no specific defect established at overview scale | — |
| 098 [vault-exact-decimal-390.png](docs/acceptance/phase165d/vault-exact-decimal-390.png) | Vault | w390; h unknown | 390×14616 | phase165d | OV; dense mobile layout; small text requires larger review | — |
| 099 [history-chart-hover.png](docs/acceptance/phase166a/history-chart-hover.png) | Replay / comparison | unknown | 1440×900 | phase166a | OV; no specific defect established at overview scale | — |
| 100 [independent-gap-segment-2.png](docs/acceptance/phase166a/independent-gap-segment-2.png) | Replay / comparison | unknown | 1440×8400 | phase166a | OV; no specific defect established at overview scale | — |
| 101 [metrics-1440.png](docs/acceptance/phase166a/metrics-1440.png) | Replay / comparison | w1440; h unknown | 1180×1113 | phase166a | OV; no specific defect established at overview scale | — |
| 102 [metrics-390.png](docs/acceptance/phase166a/metrics-390.png) | Replay / comparison | w390; h unknown | 366×1188 | phase166a | OV; dense mobile layout; small text requires larger review | — |
| 103 [comparison-complete-1440.png](docs/acceptance/phase166c/comparison-complete-1440.png) | Replay / comparison | w1440; h unknown | 1440×900 | phase166c | OV; no specific defect established at overview scale | — |
| 104 [historical-preflight-1440.png](docs/acceptance/phase166c/historical-preflight-1440.png) | Replay / comparison | w1440; h unknown | 1180×1422 | phase166c | OV; no specific defect established at overview scale | — |
| 105 [large-workload-warning.png](docs/acceptance/phase166c/large-workload-warning.png) | Replay / comparison | unknown | 1180×282 | phase166c | OV; no specific defect established at overview scale | — |
| 106 [mobile-preflight-390.png](docs/acceptance/phase166c/mobile-preflight-390.png) | Replay / comparison | w390; h unknown | 366×603 | phase166c | OV; dense mobile layout; small text requires larger review | — |
| 107 [research-complete.png](docs/acceptance/phase166c/research-complete.png) | Replay / comparison | unknown | 1180×3281 | phase166c | OV; no specific defect established at overview scale | — |
| 108 [research-diagnostic-390.png](docs/acceptance/phase166c/research-diagnostic-390.png) | Replay / comparison | w390; h unknown | 366×132 | phase166c | OV; dense mobile layout; small text requires larger review | — |
| 109 [comparison-complete-1440.png](docs/acceptance/phase166d/comparison-complete-1440.png) | Replay / comparison | w1440; h unknown | 1440×900 | phase166d | OV; no specific defect established at overview scale | — |
| 110 [historical-preflight-1440.png](docs/acceptance/phase166d/historical-preflight-1440.png) | Replay / comparison | w1440; h unknown | 1180×1422 | phase166d | OV; no specific defect established at overview scale | — |
| 111 [large-workload-warning.png](docs/acceptance/phase166d/large-workload-warning.png) | Replay / comparison | unknown | 1180×282 | phase166d | OV; no specific defect established at overview scale | — |
| 112 [mobile-preflight-390.png](docs/acceptance/phase166d/mobile-preflight-390.png) | Replay / comparison | w390; h unknown | 366×603 | phase166d | OV; dense mobile layout; small text requires larger review | — |
| 113 [research-complete.png](docs/acceptance/phase166d/research-complete.png) | Replay / comparison | unknown | 1180×3281 | phase166d | OV; no specific defect established at overview scale | — |
| 114 [research-diagnostic-390.png](docs/acceptance/phase166d/research-diagnostic-390.png) | Replay / comparison | w390; h unknown | 366×132 | phase166d | OV; dense mobile layout; small text requires larger review | — |
| 115 [desktop.png](docs/acceptance/phase175/desktop.png) | Portfolio Research | 1440×1000 | 1440×3604 | phase175 | OV; explicit research/temporal sections; historical only | — |
| 116 [mobile.png](docs/acceptance/phase175/mobile.png) | Portfolio Research | 390×844 | 390×8563 | phase175 | OV; explicit research/temporal sections; historical only | — |
| 117 [desktop.png](docs/acceptance/phase176/desktop.png) | Portfolio Research | 1440×1000 | 1440×3604 | phase176 | OV; explicit research/temporal sections; historical only | — |
| 118 [mobile.png](docs/acceptance/phase176/mobile.png) | Portfolio Research | 390×844 | 390×4209 | phase176 | OV; explicit research/temporal sections; historical only | — |

Current/historical comparison: the diagnostic/source/mode shell, exact-decimal research values and explicit unavailable/incomparable sections remain recognizable. Later portfolio images and current rendering both preserve blocked-chart truth. Historical execution mobile shows wrapped IDs/currency and a tall retained-record area; current mobile Risk/Agents still show density/readability constraints. Those visual observations support bounded UX remediation, not an assertion that an old screenshot proves current engine state or that the historical TESTNET/live labels certify a trade.

## 18. Subsystem Grades

Grades assess engineering in the documented local/research scope. **A** = strong evidence and bounded contracts; **B** = sound with specific defects/acceptance gaps; **C** = material reliability/usability/calibration limitations; **D/F** = inadequate/failing for the claimed scope. Plus/minus refinements are used within A–F. External acceptance is stated separately; test count alone does not determine the grade.

| Subsystem | Grade | Evidence and limit |
|---|---|---|
| AMM mathematics | A- | Invariants/reserve deltas/concentration and independent 1,000 cases; not a formal proof of every Decimal domain. |
| CLOB quote compiler | A- | Final executable-distance/floor/budget checks; same-price policy A2-003 still partial. |
| Strategy and inventory | B+ | Conservative hard-limit integration and tested skew; stale-context PUT error A3-002. |
| Market adaptation | B | Bounded/numerically guarded observation-based estimator; empirical cadence/threshold calibration pending. |
| Hyperliquid integration | B- | Official SDK, native observation acceptance and guarded wire fixtures; HIP-3 precision defect and no signed lifecycle acceptance. |
| Market-data/reference integrity | B | Strong material/time/source contracts; Kraken control defect, RedStone external blocker and limited public soak. |
| Supervisory agents | B+ | Explicit optional policy and conservative composition/provenance; heuristic confidence and telemetry classification defect. |
| Predictive research | C+ | SHADOW separation/artifact boundaries sound; stale features, modeled classification and absent empirical/optional-training acceptance. |
| Risk and final authorization | A- | Independent executable economics, concrete membership, unknown-exposure/capital guards; venue evidence pending. |
| Execution and reconciliation | B+ | Thorough duplicate/cancel/uncertainty fixture coverage; PAPER assumptions and actual venue lifecycle unresolved. |
| Accounting | A- | Atomic/idempotent signed accounting, fees/funding/bounds; research scope, partial venue ledger and no durable recovery. |
| Simulation | A- | Deterministic isolated native engine and bounded optimizer; modeled economic realism remains a qualification. |
| Historical replay | B+ | Strong local file/provenance/segment contracts and current workflows; no authenticated original exchange history. |
| Portfolio research | B+ | Exact shared allocation/native receipts and conservative temporal classes; custom stress feasibility gap. |
| Backend APIs | B+ | Local boundary, typed contracts and error/body/worker budgets; one reproducible generic config 500. |
| Frontend UX/accessibility | C+ | Strong provenance/retirement/exact allocation; confirmed language/contrast/overflow defects, dense mobile financial tables. |
| Redis/lifecycle | B+ | Physical local failure/recovery and 20 fresh lifecycle repeats; macOS, distributed failover and durable recovery absent. |
| Security | B- | Clear local trust/resource/signing boundaries; conditional HIGH dependency advisory and no remote auth/durability certification. |
| Testing | A- | Broad native, adversarial, browser, physical and public evidence; optional skip, platform gaps and obsolete harness recorded. |
| Documentation | B | Rich phase/identity/limitation records; stale legacy API/version prose and historical acceptance can be misread without addenda. |
| Overall research readiness | B+ | Defensible bounded local research baseline with explicit ineligibility; fix confirmed evidence/feasibility/UX defects before stronger reliance. |

## 19. Readiness Matrix

`PASS` applies only to the stated exercised scope. `CONDITIONAL` permits qualified supported use while named defects/acceptance conditions remain. `BLOCKED` means evidence/architecture cannot support the requested readiness claim. `NOT RUN` means external execution was not attempted/accepted; it is not a pass.

| Readiness category | Audit decision | What was established / limiting condition |
|---|---|---|
| Core AMM correctness | **PASS** within guarded domain | Current native/adversarial and independent invariant/ordering/budget checks; no new formula defect established. |
| Local PAPER operation | **CONDITIONAL** | Supported configurations and kill/final-risk behavior execute; A3-001 telemetry, A3-002 edits, A3-007 references and UI defects limit reliance. Hypothetical execution only. |
| Historical replay research | **CONDITIONAL** | Native/current browser fixtures and provenance pass; authentic history and economic calibration not accepted. Old harness fails independently. |
| Portfolio research | **CONDITIONAL** | Exact/native bounded contracts and temporal guards pass; source assumptions and A3-005 remain. |
| Stress testing | **CONDITIONAL** | Six native stresses/browser workflows pass; arbitrary positive shock assumptions can be unrepresentable (A3-005). |
| Current BTC/ETH/SOL market observation | **PASS** for short public native observation | Actual REST/L2/perp/WS/reconnect/cleanup accepted; no long soak, all-reference acceptance or execution permission. |
| Wider Hyperliquid market compatibility | **BLOCKED** | Three-market contracts/calibration, identity/collateral/resource assumptions and unsupported-class precision. |
| HIP-3 compatibility | **BLOCKED** | Namespace/dex/asset/accounting support unaccepted; concrete A3-004 defect. |
| Agent decision integrity | **CONDITIONAL** | Conservative authority supported; optional failure policy, stale SHADOW features and modeled evidence classification limit research integrity. |
| Financial accounting integrity | **CONDITIONAL** | Bounded isolated PAPER accounting tests pass; partial venue evidence, unsupported external movements and durable recovery absent. |
| API/local security | **CONDITIONAL** | Local boundary/body/error/admission tests pass; dependency advisory and config error remain; no remote authentication claim. |
| Frontend usability | **CONDITIONAL** | Current desktop/mobile workflows and stale-state rejection pass; confirmed accessibility/readability defects and no retail/screen-reader study. |
| Physical Redis integration | **PASS** for exercised local Linux scope | Seven actual Redis 7.4.11 checks; failover/long-duration/other-platform acceptance NOT RUN. |
| Durable lifecycle/recovery | **BLOCKED** | Phase 16.6B durable financial/order/receipt reconstruction remains incomplete. |
| Signed TESTNET execution | **NOT RUN** | No signing/orders authorized or attempted; fixture correctness alone does not authorize serious venue reliance. |
| Production/live execution | **BLOCKED** | Signed lifecycle, durable recovery, remote operational security, calibration and dependency acceptance incomplete. |

## 20. Prioritized Remediation Roadmap

This list contains existing defects, reliability/maintenance debt and required acceptance only. It does not authorize implementation, new markets, new agents or trading expansion. Scope estimates are qualitative engineering effort, not commitments: **S** localized change/check, **M** coordinated subsystem change, **L** substantial acceptance/recovery/security work. Mandatory means required before the corresponding claim/use, not that every item blocks ordinary isolated research.

| Priority / requirement | Existing issue and bounded outcome | Affected files / scope | Required versus optional |
|---|---|---|---|
| **P0** | **No CRITICAL or demonstrated active high-severity financial-authority escape was established.** Do not invent a P0 trading change. | No production code change proposed by this audit. | Maintain current local/signing restrictions. |
| **P1** | Patch conditional HIGH dependency exposure A3-008; clean install/audit/build/browser acceptance on supported systems. | `frontend/package.json`, `package-lock.json`; **S** plus Windows/dev-server verification. | Mandatory before relying on affected Windows development setup or claiming dependency acceptance. |
| **P1** | Restore modeled-fill evidence classification A3-001; reject stale SHADOW features A3-003 without promoting authority. | `execution/paper.py`, `agents/evidence.py`, `ml_features.py`, predictive agent and dataset regression; **M**. | Mandatory for truthful modeled predictive evidence/inference claims. |
| **P1** | Correct Kraken heartbeat/control handling A3-007, preserving source-age semantics and unknown-data rejection. | `references/providers.py`; **S** plus quiet-period/quorum acceptance. | Mandatory before reference-availability reliance. |
| **P1** | Fix unsupported builder-perp precision classification A3-004 or explicitly fail closed; retain native restrictions. | `execution/hyperliquid.py`, metadata contract/tests; **M**. | Mandatory before any wider/HIP-3 compatibility assertion; no market expansion requested. |
| **P1** | Complete original A1-001/A1-006 signed lifecycle and A1-003/A1-004 real operational network-fault/mode-switch soak under separate authorization. | Execution, order manager, operational market adapter and acceptance runners; **M–L**. | Mandatory before serious signed venue reliance; NOT performed in this audit. |
| **P1** | Diagnose/accept A2-005 on the historically affected platform and supported dependency matrix. | Redis/WebSocket lifespan/TestClient ownership and dependency policy; **M**. | Mandatory for unqualified lifecycle acceptance; preserve current tests. |
| **P1** | Resolve remote-security/durable-recovery gates before any production claim. | `deployment.py`, runtime/execution/accounting/infrastructure and Phase 16.6B contracts; **L**. | Mandatory **if** claiming remote/production operation; not a request to add remote deployment or custody here. |
| **P2** | Return deliberate preflight error for stale perp context A3-002 while preserving atomic state. | `runtime.py`, `api/strategy.py`, perp policy tests; **S**. | Mandatory for robust supported configuration behavior. |
| **P2** | Reject/qualify unrepresentable shock depth before baseline work A3-005. | Portfolio models/preview/scenarios/stress; **M**. | Mandatory for advertised custom stress feasibility; no invented depth. |
| **P2** | Repair A3-006 language/contrast/focusable overflow and narrow financial tokens; verify keyboard/zoom/mobile. | HTML, existing CSS, RiskFirewallPanel/AgentEvents/table wrappers; **S–M**. | Mandatory for accessible operator-UI acceptance. |
| **P2** | Settle deferred A2-003 effective-price/cost policy with stable identity, budgets and actual venue constraints. | Discretizer/diagnostics/reconciler/authorization and liquidity visualization; **M**. | Mandatory before claiming efficient many-level coarse-tick operation; do not silently consolidate. |
| **P2** | Complete A1-016 cadence/threshold/confidence calibration with representative data and declared units. | `strategy/market_adaptation.py`, agent quantitative inputs/research acceptance; **M**. | Mandatory for stronger quantitative/live confidence claims, not proof the guarded arithmetic is broken. |
| **P2** | Operational ingress/subscription and Redis sustained-outage/failover/resource soak. | Operational SDK bridge, `live_streams.py`, Redis/lifecycle runners; **M**. | Required for sustained operational claims; no measured memory leak invented. |
| **P3** | Update old replay browser tab entry; reconcile stale legacy API/phase/version summaries and acceptance status. | `frontend/tests/browser-phase1641.py`, root/backend/module docs, older phase references; **S**. | Required test/documentation maintenance; preserve historical result records. |
| **P3** | Resolve A1-017 NumPy retention and Python resolved-dependency policy explicitly. | `backend/pyproject.toml`, dependency documentation; **S–M**. | Deferred policy decision, not assumed permission for dependency edits here. |
| **P3** | Profile before optimizing root subscriptions, repeated contract/hash work or large JS chunk. | `App.tsx`, stores, fingerprint helpers, bundle configuration; **M**. | Optional maintenance unless measurements establish an actual performance requirement. Preserve provenance byte compatibility. |

## 21. Final Verdict

HyperAMM has a defensible engineering baseline for **bounded local, explicitly hypothetical PAPER and research workflows**, with strong mathematical/economic guards, isolated native research execution, explicit source/temporal ineligibility and broad current regression evidence. That baseline remains **CONDITIONAL**, because the confirmed provenance, freshness, reference-control, configuration, stress-feasibility and accessibility defects affect truthful use of existing capabilities.

No CRITICAL defect or HIGH signed-trading-authority defect was established. The one confirmed HIGH is a published conditional development-dependency advisory and requires a separate patch. Nine previous findings remain PARTIAL, with acceptance/policy boundaries stated rather than inferred closed from modified code or passing test totals.

**Do not describe this audit as production authorization, authenticated historical-performance validation, calibrated predictive performance, full-universe compatibility or signed TESTNET acceptance.** Wider-market/HIP-3 and production/live readiness remain BLOCKED; durable lifecycle/recovery remains BLOCKED; signed TESTNET was NOT RUN. This report is the sole intended committed change, with both prior audits preserved.
