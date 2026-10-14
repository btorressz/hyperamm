# Changelog

All notable merged changes to **HyperAMM** are documented here, in reverse chronological order. This is a retrospective change history, not a declaration that all features are production-ready.

The history covers **all 53 merged pull requests (#1–#53)** and the separately committed README contributors update through **2026-10-13**. Dates are the **GitHub merge/commit dates in UTC**, which can differ by a day from U.S. Pacific local dates. Each PR heading links to the original pull request. Items under **Added**, **Changed**, **Fixed**, **Security**, **Tests**, and **Docs** describe the changes made at that point in history; later entries may supersede earlier behavior.

## Project status and release boundaries

- The repository began this recorded PR history at **Phase 4.1**; earlier Phase 1–4 foundation is not reconstructed from PR titles.
- **Phases 15.1–15.4 are merged and locally/fixture accepted. Phase 15.5 remains planned** as of this changelog; no Phase 16/17 implementation is claimed.
- HyperAMM defaults to **DEMO/PAPER**, with live public observation opt-in. Phase 15 market intelligence and research comparisons do not authorize execution.
- Local fixture and Chromium acceptance **do not establish real Hyperliquid connectivity, U.S. access permission, market-data licensing, commercial deployment readiness, or real-trading performance**. Historical audit findings and environment-dependent gates are detailed in the phase acceptance and audit documents.
- The current supported research/observation universe is **BTC-PERP, ETH-PERP, SOL-PERP**; existing operational strategy authority remains separate.

## 2026-10-13

### Documentation — Contributors section (direct commit, outside a PR)
- **Docs:** Added the HyperAMM contributors section to the root README, identifying project creator/lead developer and contributor links.
- **Scope:** Documentation only; no runtime or API change. [Commit `7f0595a`](https://github.com/btorressz/hyperamm/commit/7f0595ae5f199834c0c531f38cb1f7994a115270).

## 2026-10-11

### [#53 — Phase 15.4: Market vs Research Comparison & Explainability](https://github.com/btorressz/hyperamm/pull/53)
- **Added:** Strict, versioned research assumptions captured from the **actual last consumed simulated dataset frame**: midpoint, BBO, spread, mark/oracle, funding, modeled OI and bounded synthetic depth.
- **Added:** Read-only `POST /api/v1/research-market-comparison/compare`; Decimal observed-minus-hypothetical calculations, partial/unavailable metric eligibility, deterministic completeness and independent provenance.
- **Added:** An explicit Markets comparison workspace showing native observed evidence beside completed Phase 14 PAPER research and **hypothetical** PnL; frozen comparisons, refresh controls and market/research selection retirement.
- **Security:** Bounded request, sanitized errors, no network refresh, no automatic optimization or execution. Client-supplied research fingerprints remain **structurally validated, not authenticated proof of execution**.
- **Tests:** Reported **1,649 backend / 602 frontend tests passing**, TypeScript/build passing, and 15 Chromium workflows across six viewports using fixtures. Genuine venue acceptance remains open.

### [#52 — Phase 15.3: BTC/ETH/SOL Live Markets Terminal UX](https://github.com/btorressz/hyperamm/pull/52)
- **Added:** Independent Live Market Intelligence view with BTC/ETH/SOL selector, L2 book, source-time price history, mark/oracle/funding/OI, spread, provider status and connection diagnostics.
- **Changed:** Markets remains accessible without an operational terminal snapshot; the original Operational Market view and trading/research selection are preserved.
- **Fixed:** Browser-side observer/generation/sequence retirement, stale-data presentation, reconnect and resynchronization controls.
- **Tests:** Reported **1,554 backend / 539 frontend tests passing** and 13 Chromium workflows across six viewport sizes with normalized offline fixtures.

### [#51 — Phase 15.2: Live Streams, Integrity & Provider Health](https://github.com/btorressz/hyperamm/pull/51)
- **Added:** Independent read-only official Hyperliquid SDK WebSocket observer with six BTC/ETH/SOL L2 and perpetual-context subscriptions, bounded history and browser-stream endpoints.
- **Added:** Provider mapping/health contracts, observer identity, connection generations, source freshness, REST book bootstrap, and rejected/replayed-event diagnostics.
- **Security:** Queue/subscriber capacity, bounded reconnect/shutdown, and isolation from operational orders, risk, authorization and accounting; external RedStone/Kraken/CoinGecko/Yahoo collectors remain disabled for this observational path.
- **Tests:** Reported **1,548 backend / 458 frontend tests passing**; real venue delivery not verified.

## 2026-10-10

### [#50 — Phase 15.1: Read-Only Hyperliquid Market Observation & APIs](https://github.com/btorressz/hyperamm/pull/50)
- **Added:** Opt-in, independent official SDK REST observations for BTC/ETH/SOL native L2 and perpetual contexts; typed overview/snapshot GET APIs and strict Decimal/source-time normalization.
- **Security:** Bounded concurrency, cache, timeouts, native symbol/metadata validation and explicit disabled/partial/stale states; no wallet signature or strategy-market mutation.
- **Tests:** Fixture acceptance recorded, with full regression and externally permitted live acceptance not yet fully closed at this PR.

### [#49 — Phase 14.6: Validated BTC/ETH/SOL PAPER Research Selection](https://github.com/btorressz/hyperamm/pull/49)
- **Added:** Market-specific native-perpetual research catalog, metadata provenance and shared Vault/Simulation selector for BTC, ETH and SOL.
- **Fixed:** BTC/SOL no longer inherit ETH price scale or accidentally borrow the operational market; market/profile fingerprints bind isolated PAPER requests.
- **Security:** Research selection does not switch active trading, execution, risk or accounting state.

### [#48 — Phase 14: Customizable Research Vault & PAPER Integration](https://github.com/btorressz/hyperamm/pull/48)
- **Added:** Research Vault accounting presets, validated custom drafts, configuration preview/fingerprints and isolated PAPER run/optimizer integration.
- **Added:** Controlled baseline-vs-customized comparison over shared deterministic datasets; separate fees, funding, capital, drawdown and result provenance.
- **Changed:** Existing Vault's authoritative accounting views remain intact; user-selected research assumptions never automatically promote to trading settings.

### [#47 — Phase 13.3.3: Logs, Settings & UX Acceptance](https://github.com/btorressz/hyperamm/pull/47)
- **Enhanced:** Bounded, filterable session-aware operational Logs with event identity and preserved backend history semantics.
- **Enhanced:** Settings separates local browser preferences from read-only runtime configuration/diagnostics.
- **Tests:** Browser and regression acceptance for the research/operations pages, without changing execution authority.

### [#46 — Phase 13.3.2: Analytics & Simulation Studio](https://github.com/btorressz/hyperamm/pull/46)
- **Enhanced:** Session Analytics with retention/range controls, unit-aware charts, source/sequence inspection and truthful gaps.
- **Enhanced:** Simulation and bounded grid optimization UX with captured-request identity, trace exploration, candidate comparison and explicit PAPER labels.
- **Fixed:** Older async responses and refreshes are prevented from replacing newer research evidence or gratuitously resetting chart inspection.

### [#45 — Phase 13.3.1: Agent Intelligence & Vault UX](https://github.com/btorressz/hyperamm/pull/45)
- **Enhanced:** Agent intelligence dashboard with supervisor/agent states, observations, recommendations, reasons, sample support and missing-evidence handling.
- **Enhanced:** Vault evidence and ledger inspection with terminal process/session, ledger version and fingerprint consistency checks.
- **Security:** Read-only display cannot confer agent, risk, order or accounting authority.

### [#44 — Root CODEBASE.md Architecture Guide](https://github.com/btorressz/hyperamm/pull/44)
- **Docs:** Added file-by-file backend/frontend inventory, data flow and authority boundaries; mapped API/WebSocket wiring, optional dependencies, tests and deployment limits.
- **Scope:** Documentation only.

### [#43 — Phase 13.2.1: Execution Lifecycle UX & Acceptance](https://github.com/btorressz/hyperamm/pull/43)
- **Enhanced:** Execution lifecycle filtering, exact-Decimal sorting, expandable order details and bounded reconciliation/execution timeline.
- **Fixed:** Retired, duplicated and superseded slot/quote evidence is labeled historical or uncertain instead of implying a current authorized resting order.
- **Tests:** Expanded React workspace and quote-lifecycle acceptance while leaving backend order logic unchanged.

### [#42 — Phase 13.2 Partial: Quote-Ladder Execution Integrity](https://github.com/btorressz/hyperamm/pull/42)
- **Fixed:** Removed misleading blanket `FILLED ? PAPER_FILLED : RESTING` display mapping; now distinguishes proposed, authorized, retained, uncertain and historical quote/order evidence using executable price/size matching.
- **Tests:** Added targeted regression cases; this PR was explicitly a **partial** Phase 13.2 implementation.

## 2026-10-09

### [#41 — Phase 13.1: Institutional Design & Navigation](https://github.com/btorressz/hyperamm/pull/41)
- **Added:** Consistent dark institutional terminal styling, persistent hash-based navigation across twelve pages, collapsible sidebar and accessible mobile navigation.
- **Fixed:** Refresh, deep-link and browser back/forward routing while preserving existing financial and trading behavior.

### [#40 — Phase 12.3: Frontend Freshness & Session Replay Protection](https://github.com/btorressz/hyperamm/pull/40)
- **Security:** Rejects out-of-window timestamps, old-session A→B→A replays and invalid terminal frames before they renew connection status or replace current evidence.
- **Fixed:** Accepted-frame ordering, backend restart recovery and historical/disconnected diagnostics; preserves the existing terminal wire schema.

### [#39 — Phase 12.2: AMM Quote & Liquidity Hardening](https://github.com/btorressz/hyperamm/pull/39)
- **Fixed:** Quote distance checks now use normalized executable prices rather than raw curve distance; rejects coarse-tick excursions and configurations that cannot fund executable quote floors.
- **Enhanced:** Tick-grouped effective-liquidity diagnostics with cumulative depth and explicit virtual-versus-executable liquidity semantics.
- **Tests:** Numerical/tick and quote-authority regressions; existing risk/final authorization remains authoritative.

### [#38 — Phase 12.1: WebSocket & Runtime Reliability](https://github.com/btorressz/hyperamm/pull/38)
- **Fixed:** Terminal WebSocket structured cancellation, TestClient teardown errors, owned send/disconnect tasks and bounded subscriber cleanup.
- **Enhanced:** Runtime lifecycle/shutdown regression coverage; macOS-specific and real-infrastructure acceptance remained separate gates.

### [#37 — Phase 8.3.1: Provider Post-Merge Regression Closure](https://github.com/btorressz/hyperamm/pull/37)
- **Fixed:** Six regressions after optional Yahoo reference work, including timestamp/deadband identity, provider enumeration, generated-schema exposure and documentation static-scan behavior.
- **Security:** Yahoo remains observational only, outside reference quorum, material authority and execution.

### [#36 — Phase 8: CoinGecko Security & Optional Yahoo Observations](https://github.com/btorressz/hyperamm/pull/36)
- **Security:** CoinGecko Demo/Pro requires configured keys and verified HTTPS hosts; correct authenticated headers, sanitized errors and bounded retry behavior.
- **Added:** Optional Yahoo WebSocket research observations, separately surfaced through read-only diagnostics, without becoming risk/authorization/reference-consensus input.
- **Tests:** Provider configuration, transport, source timestamp and non-authority regressions; genuine external provider acceptance remained pending.

## 2026-10-08

### [#35 — Audit 2.0: Full-System Readiness Review](https://github.com/btorressz/hyperamm/pull/35)
- **Docs/Audit:** Added `AUDIT_REPORT_2.0.md` with a fresh review of authority, agents/ML shadow research, runtime, browser/API behavior, Audit 1.0 dispositions and outstanding MVP gates.
- **Scope:** **Audit only; no findings fixed by this PR.** Recorded environment-sensitive TestClient/Redis shutdown issues and unresolved acceptance requirements.

### [#34 — Advanced Agents & Predictive Shadow Intelligence](https://github.com/btorressz/hyperamm/pull/34)
- **Enhanced:** Regime, Toxic Flow and Execution Quality agents with expanded bounded market context, markout horizons and PAPER lifecycle evidence.
- **Added:** Liquidity Quality and Perpetual Crowding agents; optional offline logistic-model training and typed feature/model provenance.
- **Security:** ML output remains **SHADOW/observational**, never active trading authority; final quote/risk/firewall gates remain downstream.

### [#33 — Audit 1.0 Post-Remediation Status](https://github.com/btorressz/hyperamm/pull/33)
- **Docs/Audit:** Updated the historical audit with verified finding dispositions, PR lineage and remaining external/system acceptance needs without erasing original findings.
- **Clarified:** Partial closure of transport, signed TESTNET, local-only security, empirical calibration and dependency-review matters is not full production acceptance.

### [#32 — Redis Observational Operational Health](https://github.com/btorressz/hyperamm/pull/32)
- **Added:** Read-only operational visibility into optional Redis connection/admission/health state.
- **Security:** Redis diagnostics remain observational and do not grant execution or account authority.

### [#31 — Optional Redis Distribution & Coordination](https://github.com/btorressz/hyperamm/pull/31)
- **Added:** Optional ephemeral Redis Pub/Sub terminal relay, TTL latest-snapshot cache, shared bounded WebSocket/research admission and worker heartbeat.
- **Enhanced:** Lease renewal/expiry, fail-closed infrastructure behavior and detached PAPER research status mirroring, while retaining one authoritative runtime and one local research worker.
- **Docs:** Added Redis design/configuration guidance. No durable database or distributed trading authority.

### [#30 — Audit 1.0 Informational Closeout](https://github.com/btorressz/hyperamm/pull/30)
- **Docs:** Explained virtual-reserve/liquidity-budget semantics, offline scientific-computing boundary, non-custodial in-memory accounting limits and different provenance fingerprint scopes.
- **Scope:** Documentation/acknowledgment of A1-024–A1-027, not new runtime features.

### [#29 — A1-023: Public Diagnostic Sanitization](https://github.com/btorressz/hyperamm/pull/29)
- **Security:** Centralized redaction of Bearer/Basic credentials, labeled secrets and provider URLs before public-text truncation.
- **Enhanced:** Sanitize outward diagnostic copies across terminal, risk, reference, agent, accounting and related APIs without changing canonical domain hashes.

### [#28 — A1-022: Freshness & Provenance](https://github.com/btorressz/hyperamm/pull/28)
- **Fixed:** Terminal publication now ages retained market, perpetual and reference observations at emission time; stale evidence cannot regain freshness simply because a new terminal frame was published.
- **Enhanced:** Transport-specific freshness budgets and transparent stale/source-time UI labels without recomputing economic consensus.

### [#27 — A1-020/021: Chart Ordering & Authorization Lineage](https://github.com/btorressz/hyperamm/pull/27)
- **Fixed:** Merge delayed history responses with newer live observations using sequence watermarks, preserving history identity, chart range and inspection viewport.
- **Enhanced:** Quote-ladder/authorization UI binds executable slots to authorized ladder and final-envelope lineage; missing/inconsistent proofs remain explicit.

## 2026-10-07

### [#26 — A1-019/018: Serialized Runtime Lifecycle & Documentation](https://github.com/btorressz/hyperamm/pull/26)
- **Fixed:** Lifecycle/config transitions use dedicated lock ordering, captured transport identities and atomic authority publication; old callbacks cannot revive retired economic state.
- **Security:** Partial startup, cancellation and cleanup uncertainty fail closed; kill/cancel functions remain available.
- **Docs:** Refreshed lifecycle/architecture records.

### [#25 — A1-017: NumPy Retention & Compatibility Review](https://github.com/btorressz/hyperamm/pull/25)
- **Docs:** Recorded the deliberate decision to **retain** direct `numpy>=2.1,<3` for potential future quant research and a compatibility-surface review.
- **Clarified:** Unused dependency removal was **deferred**, not completed; the final PR did not remove NumPy or change runtime functionality.

### [#24 — A1-016: Quantitative Sampling Hardening](https://github.com/btorressz/hyperamm/pull/24)
- **Fixed:** Safe Decimal-to-float boundaries and overflow/underflow checks for Phase 6 RMS log-return volatility calculations.
- **Enhanced:** Explicit `PER_ACCEPTED_OBSERVATION` sampling units shared by adaptation, agents and simulation; no false calendar-time/annualized interpretation.
- **Tests:** Numerical extreme, boundary, warmup and cadence regression cases.

### [#23 — A1-015: Optimizer Validation Provenance](https://github.com/btorressz/hyperamm/pull/23)
- **Added:** Training/validation dataset identities, overlap/independent-holdout classification and candidate provenance.
- **Fixed:** Unexpected runtime errors propagate rather than being mislabeled as ordinary invalid candidates.

### [#22 — A1-014/013: Execution Quality Economics & Agent Failure Policy](https://github.com/btorressz/hyperamm/pull/22)
- **Fixed:** Runtime and simulation PAPER fills bind the available accepted consensus/reference at fill time; markout evidence includes source provenance.
- **Changed:** Churn denominator uses order-changing cycles, and GOOD execution quality requires mature markout evidence.
- **Clarified:** Optional agent failures produce neutral/ERROR evidence; risk/firewall/final authorization remain authoritative.

### [#21 — A1-011/012: Read-Only Observations & Terminal Recovery](https://github.com/btorressz/hyperamm/pull/21)
- **Fixed:** Read-side AMM/market/perpetual APIs no longer trigger hidden runtime refreshes or mutate authoritative state.
- **Enhanced:** Terminal invalid-frame handling retains last valid evidence and supports stale/reconnect recovery.

### [#20 — A1-009/010: Local Deployment & Terminal Publisher](https://github.com/btorressz/hyperamm/pull/20)
- **Security:** Added local single-operator/worker boundary, loopback Host/peer/Origin checks and rejection of unsupported remote/public binding; CORS is explicitly not authentication.
- **Added:** Single versioned terminal publisher, latest-only bounded fanout and controlled WebSocket subscribers.

### [#19 — A1-008/007: Source Timestamps & Immutable Markouts](https://github.com/btorressz/hyperamm/pull/19)
- **Fixed:** Provider deadband handling preserves the actual retained-price source timestamp and rejects replay; receipt time cannot masquerade as exchange time.
- **Fixed:** Mature fill markouts freeze observation identity, reference and timestamp instead of changing when bounded history rolls forward.

### [#18 — A1-005/006: Execution History & Duplicate Reconciliation](https://github.com/btorressz/hyperamm/pull/18)
- **Fixed:** Bounded closed-order/fill history and incremental accounting/agent consumption replace growing lifetime rescans.
- **Fixed:** Detect duplicate resting order slots and prevent ambiguous order overwrite in reconciliation and risk.

### [#17 — A1-002/003/004: Market Identity & SDK Lifecycle](https://github.com/btorressz/hyperamm/pull/17)
- **Fixed:** Market material identity advances for same-time changed depth/BBO, preventing authorization against obsolete books.
- **Enhanced:** Hyperliquid WebSocket reconnect supervision, resubscription/freshness recovery and explicit SDK cleanup/thread ownership; live-network verification remains separate.

### [#16 — A1-001: Venue-Normalized Final Authorization](https://github.com/btorressz/hyperamm/pull/16)
- **Security:** Quote price/size normalization moves inside trusted final authorization so risk/capital checks bind the economics actually sent to the SDK.
- **Fixed:** Side-aware Decimal rounding, concrete request membership, serialization/idempotence and guarded TESTNET order authority.

### [#15 — Audit 1.0: Review of Phases 1–12](https://github.com/btorressz/hyperamm/pull/15)
- **Docs/Audit:** Added `AUDIT_REPORT_1.0.md` assessing AMM math, risk, agents, exchange integration, simulation, accounting, terminal, security and readiness.
- **Scope:** Original findings and recommendations only; individual fixes followed in later PRs.

### [#14 — Phase 12: React Trading & Liquidity Terminal](https://github.com/btorressz/hyperamm/pull/14)
- **Added:** Twelve-page React operator terminal with `phase12-v1` snapshots, market/AMM visualizations, strategy, execution, risk, agents, Vault, analytics, simulation, logs and settings.
- **Added:** Session history/events, health and quote-stage lineage over typed REST/WebSocket contracts.
- **Security:** Preserved upstream quote/risk/execution and accounting authority.

### [#13 — Phase 11.1: Accounting High-Water & Fill Reconciliation](https://github.com/btorressz/hyperamm/pull/13)
- **Fixed:** Equity peaks update after committed PAPER fill/fee/funding changes, not only mark updates.
- **Security:** Reconcile executed fills against immutable ledger identities and expose divergence; inconsistent accounting blocks CREATE/REPLACE while cancellation remains allowed.

### [#12 — Phase 11: Deterministic Vault & Accounting](https://github.com/btorressz/hyperamm/pull/12)
- **Added:** Average-cost PAPER accounting, immutable idempotent ledger, fees/funding, equity, drawdown, capital reservations and Vault APIs/UI.
- **Security:** Bind accounting version/fingerprint to final quote authorization; TESTNET unsupported cash/economic fields remain explicit PARTIAL/UNAVAILABLE.

### [#11 — Phase 10.1: Isolated Simulation Worker & Provenance](https://github.com/btorressz/hyperamm/pull/11)
- **Fixed:** Move deterministic scenario and optimizer work from FastAPI's operational event loop to one lifespan-owned worker/private event loop.
- **Security:** Bounded research admission (429 on concurrent work), cancellation-safe slot retention and worker shutdown; code-owned simulation version/fingerprints.

## 2026-10-06

### [#10 — Phase 10: Deterministic Simulation & Optimization](https://github.com/btorressz/hyperamm/pull/10)
- **Added:** Offline deterministic market scenarios, isolated PAPER strategy/risk/agent/AMM runs, simulated execution/fills and performance trace.
- **Added:** Bounded strategy/agent grid optimization with training/validation scoring and dataset/run provenance.
- **Status:** Original PR flagged incomplete environment-specific acceptance; subsequent PRs hardened provenance and worker isolation.

### [#9 — Phase 9: Supervisory Agents](https://github.com/btorressz/hyperamm/pull/9)
- **Added:** Deterministic Regime, Toxic Flow/Adverse Selection and Execution Quality agents plus conservative supervisor.
- **Enhanced:** Bounded agent quote adaptation, fill/markout telemetry, agent event APIs and frontend observability.
- **Security:** Agent fingerprints bind into final authorization; agents cannot bypass the risk firewall or invent unsupported TESTNET fill quality.

## 2026-10-05

### [#8 — Phase 8.2: RedStone Public HTTP Fallback](https://github.com/btorressz/hyperamm/pull/8)
- **Added:** No-key public HTTP fallback under the **same RedStone provider identity**, with separate freshness budget and bounded polling/backoff.
- **Fixed:** One consensus vote across RedStone Live WS and HTTP fallback; fresh Live transport takes precedence.

### [#7 — Acceptance Fixture Fixes](https://github.com/btorressz/hyperamm/pull/7)
- **Tests:** Updated legacy generation/adaptation failure injection and perpetual-timestamp fixtures to match the current quote pipeline.
- **Scope:** No production-code change; restored intended failure/recovery regression coverage.

### [#6 — Phase 8.1: RedStone Live Protocol Fix](https://github.com/btorressz/hyperamm/pull/6)
- **Fixed:** RedStone subscription payload, enabled configuration checks and live price-protocol handling.
- **Security:** Kept consensus, provider trust roles and final authorization unchanged.

### [#5 — Phase 8: Reference Integrity & Institutional Risk Firewall](https://github.com/btorressz/hyperamm/pull/5)
- **Added:** RedStone primary, native Hyperliquid oracle/mark/L2, Kraken and CoinGecko reference evidence with source health, freshness and provenance.
- **Added:** Reference integrity, deterministic consensus/risk firewall and final quote authorization binding to market, agent/risk and reference evidence.
- **Status:** Initial PR noted incomplete environment-specific acceptance; later work expanded and hardened providers.

### [#4 — Phase 7: Perpetual Context & vAMM Reference Pricing](https://github.com/btorressz/hyperamm/pull/4)
- **Added:** Native mark/oracle/funding/OI, signed basis metrics and perpetual position/margin context from official SDK normalization.
- **Enhanced:** Perpetual-aware fair-value/reference pricing and versioned freshness checks without changing earlier AMM or execution authority.

### [#3 — Phase 6: Volatility & Book-Imbalance Adaptation](https://github.com/btorressz/hyperamm/pull/3)
- **Added:** Bounded unique price history, realized volatility, L2 depth imbalance, warmup and deterministic spread/size adaptation.
- **Security:** Replay/out-of-order filtering and bounded multipliers preserve risk/execution limits.

### [#2 — Phase 5: Inventory-Aware Quotes](https://github.com/btorressz/hyperamm/pull/2)
- **Added:** Signed inventory state/policy, reservation-price and size skews, soft/hard inventory protections.
- **Security:** PAPER position derives from fills; TESTNET must use authoritative account state and fail closed if uncertain.

## 2026-10-04

### [#1 — Phase 4.1: AMM Sizing & Fail-Closed Execution](https://github.com/btorressz/hyperamm/pull/1)
- **Fixed:** Incremental constant-product reserve movement determines CLOB sizing; concentrated-liquidity curves preserve per-side quote budgets/minimums.
- **Security:** Unsafe generation/market/risk conditions cancel resting strategy orders; serialized reconciliation, kill-state handling and guarded TESTNET partial-fill/unknown-state reconciliation.
- **Foundation:** Establishes the first merged PR in this changelog; earlier project development is outside the reviewed PR range.

---

## Historical audits and acceptance

For deeper investigation, consult [Audit 1.0](AUDIT_REPORT_1.0.md), [Audit 2.0](AUDIT_REPORT_2.0.md), [architecture](docs/ARCHITECTURE.md), [development roadmap](docs/ROADMAP.md), and Phase 15 acceptance reports ([15.1](docs/PHASE151_ACCEPTANCE.md), [15.2](docs/PHASE152_ACCEPTANCE.md), [15.3](docs/PHASE153_ACCEPTANCE.md), [15.4](docs/PHASE154_ACCEPTANCE.md)). PR bodies contain their contemporaneous tests, limitations and implementation detail. **A merged PR is not by itself proof of production, signing, market-data licensing or external-network acceptance.**
