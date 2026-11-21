# Phase 18.7D–E acceptance

The merged `main` baseline is `4d444b6080e65f2154c5099645b3b90bfaac1dd4`. GitHub marks PR #102 merged. Its diff adds the A–C compatibility and resilience tests and withholds market observations when the summary owner starts shutting down. The bounded provider evidence, 64-namespace Testnet discovery limit and exact historical hash qualification carry forward. [PR #102](https://github.com/btorressz/hyperamm/pull/102) · [A–C acceptance](PHASE18_7ABC_ACCEPTANCE.md)

## Scope and test plan

| Priority | Evidence used in this review |
| --- | --- |
| REUSE | Both existing AMMs, quote and risk implementations, runtime and isolated `SimulationExecutor`, the Phase 11 ledger, all nine agents, the Phase 17 native portfolio pipeline and existing Decimal oracles. Rerun the existing focused backend, frontend Node validators and browser suites. |
| ENHANCE | Extend the Phase 17.6 independent oracle from three selections to all seven nonempty native subsets. Share Phase 18.6's fixture lifecycle, workflow assertions, measurements and axe scans across browser engines. Keep Chrome settings and CDP inside Chromium branches. |
| ADD | Two focused D suites for financial reconciliation and mixed advisory/operational outcomes. Add the E harness for the route × presentation matrix, native Replay and Portfolio, applied asset policy, keyboard behavior, responsive evidence and recovery. Compose the existing qualified discovery and native fixture applications. |

The review followed the operational and research ownership mapping in the repository, checked the Phase 17 and Phase 18 merge history through #102, and reused Audit 3.0 authority and accessibility fixtures. [Source map](../CODEBASE.md) · [Audit 3.0](../AUDIT_REPORT_3.0.md) · [Final remediation](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md) · [Roadmap](ROADMAP.md)

## D — Financial and authority checks

| Gate | Disposition and evidence |
| --- | --- |
| Constant Product and Concentrated Liquidity | **PASS** on local fixtures. Existing invariant and normalization tests cover reserve product, marginal prices, side orientation, reserve-delta weight and size, concentration distribution and edges, extreme references, narrow ticks and feasible minimum quantities. The new suite executes 40-frame Core DOGE Constant Product and HIP-3 `xyz:GOLD` Concentrated runs under each of three risk paths. [AMM tests](../backend/tests/test_amm.py) · [Precision and authority tests](../backend/tests/test_phase122_amm_hardening.py) · [Integrated oracle](../backend/tests/test_phase187d_financial_invariants.py) |
| Quote proposals and final ladders | **PASS**. Capture strategy proposals and the ladders supplied to actual `authorize`. Check side orientation and monotonicity, uncrossed prices, positive size quanta, supported price precision, minimum notional, independent distance from midpoint and slot preservation. The raw reducing side can grow within the configured inventory multiplier. The final qualified PAPER budget is one configured liquidity budget per side, at most twice that total across both sides. Existing tests exercise soft/hard inventory, volatility and funding-reference adaptations. [Integrated oracle](../backend/tests/test_phase187d_financial_invariants.py) · [Inventory](../backend/tests/test_phase5_inventory.py) · [Volatility](../backend/tests/test_phase6_market_adaptation.py) · [Funding reference](../backend/tests/test_phase7_perp_context.py) |
| PAPER accounting | **PASS**. Join each fill to one trade row and one fee row. Independently compute signed execution cash flow, fee schedules at 7/13 bps, and two-second funding from each matching scenario observation and preceding booked inventory. Reconcile cumulative cash, carried cost basis, signed inventory, charges, mark-to-market equity, P&L, available capital and the complete hash chain. The oracle uses 65-digit Decimal arithmetic with a `1e-18` absolute tolerance for native rounding. Existing accounting cases check partial fills, reversals, closeouts, depleted capital, reservation overlap, duplicates and atomic ledger failure. [Integrated oracle](../backend/tests/test_phase187d_financial_invariants.py) · [Accounting](../backend/tests/test_phase11_accounting.py) · [Fees and funding](../backend/tests/test_phase11_fees_funding.py) · [Ledger](../backend/tests/test_phase11_ledger.py) |
| Asset-aware and modeled risk | **PASS** on default, hypothetical and source-constrained PAPER fixtures. Qualified market and catalog identity, denomination and margin mode, initial and maintenance margin, headroom, leverage, concentration, resting/projected exposure, haircuts, price/funding/fee stress, fail-closed HALT and expiry run through the existing boundaries. Public references remain observations. Phase 18.3 risk uses hypothetical capital and carries its source limitations. [Phase 18.2G](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md) · [Phase 18.3](PHASE18_3_FINAL_ACCEPTANCE.md) · [Phase 18.5](PHASE18_5_FINAL_ACCEPTANCE.md) |
| Six supervisory agents | **PASS** on deterministic local evidence. Regime, Toxic Flow, Execution Quality, Liquidity Quality and Perp Crowding remain bounded by upstream prices/sizes, confidence and available evidence under the existing supervisor. Predictive Adverse Selection remains SHADOW. Its model and freshness changes preserve material quote authority. Source-time, unsupported-state, warmup, missing evidence and per-agent error fixtures ran under the original policies. [Agent expansion](../backend/tests/test_agent_expansion.py) · [Runtime](../backend/tests/test_phase9_runtime.py) · [Audit freshness](../backend/tests/test_audit3_security_evidence.py) |
| Three observational advisories | **PASS**. Market Eligibility, Funding/Basis and Quote Economics retain read-only authority, distinct source limits and confidence, qualified catalog binding, expiring receipts and independent failures. In the new test Funding/Basis reports a provider error while Quote Economics retains a mature result from the matching PAPER receipt. Catalog replacement retires the old receipt. Separately, a Perp Crowding exception and a lost operational quorum leave the Firewall in HALT with no quote authorization or resting orders. [Phase 18.4](PHASE18_4_FINAL_ACCEPTANCE.md) · [Mixed authority fixture](../backend/tests/test_phase187d_authority_acceptance.py) |
| Firewall, kill and concrete execution | **PASS** for deterministic PAPER and guarded no-signing TESTNET fixtures. Existing checks cover manual kill, automatic HALT, capital and hard inventory limits, stale context, missing references and authorization, market/side/size mismatch, changed authority fingerprints, invalid precision, partial fill reservations, unknown exposure, uncertain cancels, reconciliation failure and shutdown barriers. The SDK-shaped fixture counts allowed and denied transmissions without a wallet or venue session. [Firewall](../backend/tests/test_phase8_risk_firewall.py) · [Runtime authority](../backend/tests/test_phase8_runtime.py) · [Execution](../backend/tests/test_execution.py) |
| Research isolation | **PASS** within the combined fixtures. The mixed run captures strategy and AMM configuration, operational market, agent and risk settings, kill, quotes and authorization, resting orders/fills, vault and ledger, TESTNET flag, and adapter, signing and listener references before research. Standard and asset-aware runs, risk lookup, advisory failure and catalog replacement preserve that state. The runtime fixture has no passive feed loop. Existing observer, Replay, portfolio, and worker suites exercise failed admission, passive marks, provider shutdown, stress and cancellation with a server-owned admission. [Mixed authority fixture](../backend/tests/test_phase187d_authority_acceptance.py) · [Read-only streams](../backend/tests/test_phase152_runtime_isolation.py) · [Portfolio isolation](../backend/tests/test_phase173_isolation.py) · [Provider resilience](../backend/tests/test_phase187_provider_resilience.py) |
| Native portfolio | **PASS**. All seven native subsets were reconciled using accepted native receipts. Initial capital equals allocations plus reserve. Equity includes reserve once. P&L is ending equity minus initial capital and reconciles to native net contributions plus the rounding residual. Signed/gross exposure, allocation utilization and drawdown use native values and the complete eligible observations. Existing exposure, risk, temporal and stress suites exercise concentration, modeled leverage, fees and funding, unavailable histories and all six supported stress types. [Seven-subset oracle](../backend/tests/test_phase176_acceptance.py) · [Phase 17.6](PHASE176_FINAL_ACCEPTANCE.md) |
| Financial and source integrity | **PASS** on retained backend and TypeScript cases. Foreign receipts, modified dataset identities, forged or inconsistent fingerprints, money/fees/funding, source counts, duplicate identities, modified decisions and chart extrema remain rejected by the respective typed validators. Tests include rehashed inconsistent reports. Fingerprints bind integrity and lineage. Independent source authentication, synchronized exchange histories, empirical correlation, live netting, cross-DEX collateral and verified liquidation remain outside the modeled portfolio evidence. [Terminal backend](../backend/tests/test_phase176_acceptance.py) · [Portfolio frontend](../frontend/tests/phase175-portfolio.test.cjs) · [PAPER frontend](../frontend/tests/phase182-generalized-paper.test.cjs) |
| Signed venue | **SIGNED TESTNET — NOT RUN**. The Audit 3.0 controlled venue submission and reconciliation gate remains open. This task used disabled signing and deterministic adapters. [Audit 3.0 external gates](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md#remaining-limits-and-verdict) |

## Historical compatibility

| Capture | This run | Published reference |
| --- | --- | --- |
| Standard Generalized PAPER | **PASS** for 38 byte-identical admission/result pairs in PR #99, PR #100 and merged `main`. Controlled SHA-256 `83cfb57fec42efdc9f64114b7891881752da53a904300e7ad4439859445fcf55`. | **BLOCKED** exact reproduction of `b564ad46f264f8b8295feb5dc59d4c44a3e97b2302769663aaf94dbd5fbce65e`. |
| Asset-aware Generalized PAPER | **PASS** for 18 byte-identical pairs on the same trees. Controlled SHA-256 `257c8d7ec9d510544b2d45302e3be10467f486eb4a1d53a4d63e9d06d8bf1ec9`. | **BLOCKED** exact reproduction of `5fa22910e35da8655a6f99df148cc809a2d6043ba090c2ae051ba479e64cf47f`. |
| Native BTC/ETH/SOL and portfolio | **PASS**. Reproduced `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad`, including 39 native dataset fingerprints, fills, ledgers, AMM and risk outputs, and three native receipts. | Matches the published Phase 18.2G oracle. |

The controlled PAPER probe runs the historical application code with identical inputs and fixed admission and worker clocks in each tree. It compares entire serialized receipts and results. The PR #100 merge contents, description, discussion and hash history do not provide the original capture generator and exact serialized input envelope. The controlled evidence supports financial compatibility under its inputs. Exact attestation of the two original hashes remains open. [Compatibility probe](../backend/tests/phase187_paper_compatibility.py) · [Native reproduction](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility) · [PR #100](https://github.com/btorressz/hyperamm/pull/100)

## E — Browser, workflows and accessibility

The browser harness runs on Debian 13 with Playwright 1.62.0 and the repository's Chromium executable. Explorer and Replay use deterministic provider and recorded-data fixtures. PAPER and all native portfolio results come from the existing application endpoints, source validators and shared local worker.

| Environment | Disposition |
| --- | --- |
| Chromium 151.0.7922.173 | **PASS** for the Linux fixture matrix. 14 workflow groups, 39 route-and-mode checks, 71 viewport measurements and actual 200% browser zoom. Zero page errors. [Measured results](acceptance/phase187de/browser-results.json) |
| Playwright Firefox | **NOT RUN**. The Playwright 1.62.0 Firefox v1538 archive is absent locally and the configured download endpoints returned HTTP 403 `Domain forbidden`. |
| Playwright WebKit | **NOT RUN**. The WebKit v2336 archive is absent locally and the configured download endpoints returned HTTP 403 `Domain forbidden`. |
| Native Safari/macOS, Windows and mobile browsers | **NOT RUN**. This workspace supplies a Linux host. Responsive viewport tests use Chromium. |
| VoiceOver, NVDA or other manual screen reader | **NOT RUN**. No interactive assistive-technology setup was available. The automated accessibility results cover their measured rules and states. |

The 13 canonical routes in the matrix are `dashboard`, `markets`, `strategy`, `amm-settings`, `execution`, `risk`, `agents`, `vault`, `analytics`, `simulation`, `portfolio-research`, `logs` and `settings`. Direct URL and reload checks assert visible workspace content and the matching active navigation link in Starter, Pro and Institutional. Browser history checks verify back/forward, focus and top-of-workspace scrolling. Deep links cover guided PAPER, retained results, Replay and market comparison. [Browser harness](../frontend/tests/browser-phase187.py)

| Workspace | Exercised evidence |
| --- | --- |
| Starter | Core and HIP-3 search, pagination, feed latency/expiry and missing observation state. A qualified handoff passes the selected identity while leaving the synthetic price blank. The original local PAPER worker runs once across presentation switches and retains the accepted result. |
| Pro | Both accepted AMM controls, supervisory and research advisory views, simulated quote cohorts, observed funding and qualified asset-aware PAPER. Historical Replay executes generated history and renders the actual segment results. The legacy harnesses exercise the native scenario and comparison workflows. |
| Institutional | Native BTC/ETH/SOL validation and analytics, risk evidence, earnings/cost units and configuration provenance using accepted native receipts. The portfolio regression exercises native Stress Lab and the operational logs, Vault, Execution and Risk links. |
| Financial rendering | Small decimal marks, missing fields, negative reported funding and provider previous-day comparison render with their provider receipt times and declared units. PAPER results surface P&L, simulated fees, funding, inventory and risk state separately. The TypeScript and portfolio suites exercise exact capital, unavailability and provenance. |
| Responsive and keyboard | `390×844`, `768×900`, `1024×768`, `1440×1000`, `1920×1080`, and `668×390` landscape for the newly captured workspaces. Horizontal scrolling is checked at document level and by keyboard in the Risk evidence table. Drawer focus cycles on Tab and Shift+Tab and returns on Escape. Buttons support Enter and Space. Chromium uses its page zoom control for actual 200% zoom. |

The predecessor workflow and the new Chromium matrix exercise a catalog conflict, stale and late observations and the return from page and mode changes during an admitted PAPER request. The worker still owns the admitted run. The new harness observes a real HTTP 422 and injects 429, 500, 503 and 504 plus a transport interruption. Failed admissions and results retire, the Run button disables, and manual eligibility and retry recover. The WebSocket probe observes a loading Risk workspace, an available read-only Explorer and the return of current Risk evidence after reconnect. The Replay and portfolio regression harnesses supply process-restart and worker contention evidence.

### Accessibility measurements

Axe-core 4.11.1 ran 26 scoped WCAG 2.0/2.1 A/AA scans in the D–E harness and 32 route/viewport scans plus a zoom scan in the Audit 3.0 harness. Both runs reported zero automated violations. The D–E scan returned seven contrast and two table-header review entries. Computed contrast for the sampled market labels, navigation and Risk status was at least 8.44:1. Axe still requests manual review of the Replay table after the explicit header fix. The browser verified its scoped headers and the presence of both sides' data rows. Audit 3.0 returned 33 contrast review entries and measured at least 6.71:1 in its sampled text. Risk evidence and recent agent events were reachable using Tab and scrollable with arrow keys. At 200% zoom Chromium reduced the 1,440-pixel CSS viewport to 720 pixels with no document overflow. The navigation drawer remained operable at that zoom. Manual assistive-technology review remains open. [Browser results](acceptance/phase187de/browser-results.json)

### Reviewed browser screenshots

The 20 retained captures show the fixture label, operational DEMO context, and the actual local research or observation state. Desktop captures are 1,440×1,000 and mobile captures are 390×844. Market prices and historical recordings shown in these captures come from fixtures.

| Workspace | Desktop | Mobile |
| --- | --- | --- |
| Market Explorer | [Desktop](acceptance/phase187de/market-explorer-1440.png) | [Mobile](acceptance/phase187de/market-explorer-cards-390.png) |
| Starter | [Desktop](acceptance/phase187de/starter-1440.png) | [Mobile](acceptance/phase187de/starter-390.png) |
| Pro | [Desktop](acceptance/phase187de/pro-1440.png) | [Mobile](acceptance/phase187de/pro-390.png) |
| Institutional | [Desktop](acceptance/phase187de/institutional-1440.png) | [Mobile](acceptance/phase187de/institutional-390.png) |
| Supervisory Agents | [Desktop](acceptance/phase187de/supervisory-agents-1440.png) | [Mobile](acceptance/phase187de/supervisory-agents-390.png) |
| Asset-aware PAPER | [Desktop](acceptance/phase187de/asset-aware-paper-1440.png) | [Mobile](acceptance/phase187de/asset-aware-paper-390.png) |
| Risk Firewall | [Desktop](acceptance/phase187de/risk-firewall-1440.png) | [Mobile](acceptance/phase187de/risk-firewall-390.png) |
| Portfolio Research | [Desktop](acceptance/phase187de/portfolio-research-1440.png) | [Mobile](acceptance/phase187de/portfolio-research-390.png) |
| Historical Replay | [Desktop](acceptance/phase187de/historical-replay-1440.png) | [Mobile](acceptance/phase187de/historical-replay-390.png) |
| Portfolio provenance | [Desktop](acceptance/phase187de/portfolio-provenance-1440.png) | [Mobile](acceptance/phase187de/portfolio-provenance-390.png) |

## Reproduced defect and targeted fix

Axe marked the retained Replay order book for manual table review at 390 and 1440 pixels. In the rendered table, Asks and Bids were unscoped headers inside one table body. Each side now has a row group and a scoped group header. Price, size and order count are scoped column headers. The browser checks both groups and their associated data cells after a real fixture replay. [Replay order book](../frontend/src/components/replay/ReplayOrderBook.tsx) · [Browser assertion](../frontend/tests/browser-phase187.py)

## Regression totals

| Suite | Result |
| --- | --- |
| Full backend | **3,976 passed**, zero failures or skips, six existing warnings, 515.90 seconds. Python 3.12.14 with test, ML, Yahoo and Redis extras and two pytest-xdist workers. |
| Focused existing backend | **2,092 passed**, zero failures or skips, six existing warnings, 294.99 seconds. Includes Portfolio, Phase 18, AMM, execution, Firewall, agent, accounting and Audit 3.0 cases. |
| D additions and expanded oracle | **14 passed**, zero failures or skips, one existing warning, 20.78 seconds. This includes six integrated financial runs, one mixed authority case and the seven native subsets. |
| Frontend | Locked install, typecheck, **949 Node tests** and production build passed. Zero test failures, skips or cancellations. Node 24.19.0 and npm 11.9.0. Vite retained the TanStack directive and bundle-size warnings. |
| Chromium D–E | **14 workflow groups passed**, an additional real 200% zoom check, 39 route-and-mode checks, 71 viewport measurements, and 26 axe scans with zero violations. |
| Chromium 18.6 | **8 workflow groups passed**, plus Chromium 200% zoom, 35 viewport measurements and 14 axe scans. |
| Chromium 18.2 | **36 reported checks passed** across standard PAPER, risk, advisory and asset-aware browser paths, including qualified receipt and expiry checks. |
| Chromium 16.4.1 | **16 workflows passed** in the isolated rerun, with zero page or unexpected console errors. The first run timed out waiting for the browser's post-restart optimizer request. The same three-frame Balanced request returned HTTP 200 in 0.46 s against the fixture API, and the unchanged browser runner then passed in 26.78 s. |
| Chromium 16.5C.2 | **15 default workflows passed** in 25.86 s, with zero unexpected console or network errors. |
| Chromium 17.6 | **22 workflows passed**, 60 native engine invocations, five measured viewports, zero page or unexpected console errors. Official metadata loader reported `EXCHANGE_VERIFIED` for BTC, ETH and SOL. Native runs used local PAPER. |
| Chromium Audit 3.0 | **32 route/viewport scans and actual 200% zoom passed** with the qualified discovery fixture, zero automated violations, page errors or console errors. A preliminary launch with discovery disabled returned two expected catalog 503s and failed the harness console assertion. The fixture rerun used the original console assertion. |

## Reproduction

Run from the repository root with Python 3.12, the backend dependencies and optional test dependencies, Playwright, axe-core 4.11.1 and Node. The browser runners reuse ports 5173 and 8000, so run them serially.

```bash
(cd backend && python -m pytest -q -rs --tb=short)
(cd backend && python -m pytest -q -rs --tb=short \
  tests/test_phase17*.py tests/test_phase18*.py tests/test_amm.py tests/test_execution.py \
  tests/test_phase122_amm_hardening.py tests/test_phase[89]*.py tests/test_agent_expansion.py \
  tests/test_phase11*.py tests/test_audit3*.py)
(cd frontend && npm ci && npm run typecheck && npm test && npm run build)

python frontend/tests/browser-phase187.py --engine chromium --python /path/to/backend-python \
  --axe /path/to/axe.min.js --output work/phase187de/chromium
python frontend/tests/browser-phase186.py --python /path/to/backend-python \
  --axe /path/to/axe.min.js --output work/phase187de/legacy-186
python frontend/tests/browser-phase182.py --python /path/to/backend-python \
  --axe /path/to/axe.min.js --output work/phase187de/legacy-182
for phase in 1641 165c2 176; do
  python "frontend/tests/browser-phase$phase.py" --python /path/to/backend-python \
    --output "work/phase187de/legacy-$phase"
done
python -m playwright install firefox webkit
for engine in firefox webkit; do
  python frontend/tests/browser-phase187.py --engine "$engine" --python /path/to/backend-python \
    --axe /path/to/axe.min.js --output "work/phase187de/$engine"
done
```

For `browser-audit3-accessibility.py`, start Vite on port 5173 and run `browser-phase182:fixture_app` with Uvicorn `--factory --app-dir ../frontend/tests --host 127.0.0.1 --port 8000` from `backend/`. Use `MARKET_DATA_MODE=DEMO`, `EXECUTION_MODE=PAPER`, `ENABLE_HYPERLIQUID_TESTNET_ORDERS=false`, `LIVE_OBSERVATIONS_ENABLED=false`, `LIVE_STREAMS_ENABLED=false` and `REDIS_ENABLED=false`. Run the audit from the root with `--axe /path/to/axe.min.js --output work/phase187de/audit3`. The harness changes and restores an AMM setting and briefly starts and stops the isolated DEMO strategy to capture retained evidence.

The historical parity command uses the same `phase187_paper_compatibility.py` probe on the PR #99 merge `1b9804146a8de82e7432e18493591385b0f4bb0c`, the PR #100 merge `06a5b0f97372ae0656eef26753730f11e512f4c3` and this PR's merged baseline. Set `PYTHONPATH` to that tree's `backend:backend/tests` and compare the `standard` and `asset` stdout captures independently with `cmp` and `sha256sum`. [Prior reproduction commands](PHASE18_7ABC_ACCEPTANCE.md#regression-commands-and-evidence)

## D–E acceptance decision

**18.7D — CONDITIONAL.** Financial invariants, source bindings, research isolation and deterministic execution-authority checks passed within the local scope. The two PR #100 exact hashes and signed TESTNET remain open.

**18.7E — CONDITIONAL.** Linux Chromium workflows, responsive layouts, keyboard and automated WCAG checks passed. Alternate engines, native platforms and manual assistive technology still require independent evidence.

## Phase 18.7F handoff

- Obtain the PR #100 original generator and serialized input envelope, or record independent acceptance of the controlled three-tree comparison with the exact hash qualification intact.
- Complete Firefox and WebKit coverage on a host with the supported binaries, and native OS, mobile browser and assistive-technology checks on the supported platform combinations.
- Evaluate signed TESTNET submission, fills/cancels and reconciliation in the controlled venue workflow with the required operator approval. The full Testnet universe remains subject to the existing 64-namespace policy.
- Own the sustained public-provider, operational reconnect and shutdown, recovery/soak, venue and rollout gates from Audit 3.0. [Acceptance matrix](PHASE18_7_ACCEPTANCE_MATRIX.md) · [Audit 3.0 external gates](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md#remaining-limits-and-verdict)
