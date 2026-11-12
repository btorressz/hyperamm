# Phase 17.5 — Portfolio Research Terminal & Frontend Integration

Base: `d376287` (latest main / merged PR #78). Local acceptance: 2026-11-12.
Status: validation in progress; final measured gates below are updated before delivery.

## Architecture and reuse

The dedicated `#/portfolio-research` route uses the existing React 19 / TypeScript / Vite application, navigation registry, mobile drawer, terminal styling, Panel/Metrics/StatusBanner components, TanStack Query, Zustand and Lightweight Charts through `HistoryChart`. Existing Simulation, Research Vault, Historical Replay, Markets, Risk and Analytics routes remain available. No frontend dependency, engine, database, worker pool or durable job store is added.

`PortfolioResearch.tsx` owns accessible section navigation (Configure, Analytics, Stress Lab, Provenance). `PortfolioConfiguration` groups allocation, strategy and risk controls; `PortfolioStressLab` contains the six typed scenario forms; `PortfolioAnalytics` groups metrics, exposure, risk, evidence status, comparison and charts; `PortfolioProvenance` exposes expandable source identities and captured assumptions. Related small panels share files to avoid unnecessary fragmentation. The terminal is available over the local REST API when the terminal WebSocket is disconnected.

## API contracts and configuration preparation

- `POST /api/v1/portfolio-research/preview`: bounded `PortfolioDraft` with budget, allocations, common native strategy/AMM controls, baseline scenario/frame count, PAPER assumptions, risk limits/policy and optional typed stress scenario. Returns `phase175-preview-v1`, the complete validated configuration and canonical Python fingerprint, captured per-market profile/configuration identities, capital reconciliation, allocation percentages, workload and estimated trace eligibility. Unsupported drafts fail validation; no simulation or operational configuration mutation occurs.
- `POST /api/v1/portfolio-research/terminal`: `phase175-terminal-v1` request with `RUN`, `ANALYZE` or `STRESS`, exact accepted configuration/fingerprint, risk policy and stress assumptions only for STRESS. Returns a compact typed projection with original accounting/exposure/risk/temporal reports, native source/result identities, eligible chart evidence and backend comparison deltas. RUN and ANALYZE both collect native accounting once; their mode is retained. STRESS executes baseline then stress once each under the existing admission.
- Original `/run`, `/analyze` and `/stress` wire contracts, defaults and original fingerprints remain unchanged. No endpoint accepts an earlier client result, receipt, dataset or chart as authoritative native evidence. There is no chart retrieval endpoint or implied durable result history.

Preparation uses existing `StrategyConfig`, `research_strategy`, catalog-validated profiles, `ResearchVaultConfig.to_simulation`, `ComparisonConfigSnapshot`, portfolio models and workload validators. The draft cannot supply arbitrary strategy domains, metadata, receipts or administrative accounting bounds. Exact decimals are validated by existing Python constructors; JavaScript never implements the canonical financial fingerprint algorithm. Configuration snapshots are returned intact and resubmitted intact.

## Capital allocation and strategy controls

One, two or three BTC-PERP / ETH-PERP / SOL-PERP selections have positive decimal-string USDC allocations, total capital and minimum reserve. BigInt fixed-point input checks give immediate exact over-budget/reserve/precision messages; only server preparation produces authoritative reconciliation and percentages. No binary floating-point financial arithmetic is used in allocation validation or portfolio economics.

Native adaptive AMM market making supports constant-product/concentrated models, quote levels, distance, ETH-template order size/liquidity, concentration factor, inventory skew and market adaptation. Python prepares the selected native market profiles. PAPER controls expose fees, valid funding intervals and baseline/modeled-crossing latency, slippage, participation, depth and partial-fill assumptions. Returning to BASELINE resets incompatible execution controls.

## Portfolio analytics and exposure

Panels display native initial/allocated/reserve capital, equity, PnL, session loss, gross/signed net exposure, allocation and reserved-capital utilization, gross notional utilization, modeled leverage, concentration and eligible maximum drawdown. Per-market exposure preserves base-asset labels and native mark valuation. Comparison rows display Python-provided baseline/stressed values and signed eligible differences, including funding PnL and risk transitions. Missing values/differences display **Unavailable**. React does not calculate authoritative portfolio economics.

## Six modeled stress scenarios

| Scenario | Controls and constraints |
| --- | --- |
| Correlated Market Selloff | Per-market decline fractions; onset/duration; recovery profile |
| BTC-Led Volatility Shock | BTC decline; selected ETH/SOL transmission multipliers; bounded propagation lag; recovery |
| Liquidity Shock | Positive bid/ask depth multipliers ≤1 and spread multiplier 1–20 |
| Funding Stress | Nonzero per-market signed adjustments within ±0.01; enabled native accrual with an observed boundary |
| Oracle Degradation | Supported reference provider; missing/divergent mode; divergence ≤0.5; step window only |
| Concentration Stress | Adverse magnitude ≤0.8; backend selects largest validated nonzero pre-onset position; complete history required |

Shock windows and lag must fit the common captured clock. Declines, including transmitted declines, cannot exceed 0.8. The UI disables incompatible recovery modes and hides irrelevant assumption fields. Stale oracle timestamps are explicitly unsupported. Transmission coefficients are hypothetical assumptions, **not empirical correlations**. Backend model constraints remain authoritative.

## Bounded chart methodology

Validated native `NativeAccountingObservation` evidence is collected inside `execute_markets` before the detailed native response is discarded. During the same admitted computation, the terminal projection revalidates receipt/source bindings, complete sequence/UTC clock compatibility, native equity/PnL reconciliation and the original full equity-series fingerprint from portfolio drawdown. Reserve is included once. No histories are reconstructed from summaries or earlier client responses.

Complete `MODELED_ALIGNED` evidence supports native equity, session PnL and drawdown. Each leg retains at most 120 original observations: first/last points, global extrema, shock onset/end and lag context, drawdown threshold crossing neighbors, then deterministic per-bucket extrema and evenly spaced spare observations. Mandatory context exceeding 120 makes the chart explicitly unavailable. Sampling retains original sequence/timestamps and never interpolates missing histories. Full-history drawdown remains the native backend result, independent of sampling. Baseline and stressed charts use separate labeled modeled-frame panels, avoiding invented joins across independently sampled points.

Chart receipts preserve original analysis/accounting/temporal and native evidence fingerprints, full equity-series fingerprint, source count, sampled flag and a new bounded chart-projection fingerprint. Sampled charts explicitly say they are not full-resolution historical series. Exposure is presented as validated terminal observations; no unsupported exposure history is invented.

## Response and resource bounds

The existing pre-parse 65,536-byte request cap and 200,000-byte encoded response cap apply to both new endpoints. The worker bounds serialization before completing a terminal result; the HTTP boundary revalidates the typed result and returns the exact bounded JSON bytes before HTTP 200. The browser also bounds successful response bytes before JSON parsing. Oversize evidence returns HTTP 413; required evidence is never silently removed to meet the transport cap.

Existing ceilings remain three markets, 3,000 total executed frames, 24,000 frame × quote-level units, 1,500 retained native observations and existing ledger/event limits. Stress preparation and execution count **baseline plus stressed** work together. Native retention capacity is divided across selected markets/legs without raising any ceiling. No second executor admission or duplicate engine run is introduced.

Measured native resource results are recorded in `acceptance/phase175/resources.json` after running `backend/tests/phase175_resources.py` for 250, 300 and 500 frames per market per leg. Measurements include original stress response bytes, compact terminal bytes, request bytes, observation counts, full-history eligibility and blocked risk.

| Frames / market / leg | Original stress bytes | Terminal bytes | Chart points / leg | Temporal / risk |
| --- | ---: | ---: | ---: | --- |
| 250 | 176,036 | 69,998 | 120, sampled | MODELED_ALIGNED / ASSESSED HALT |
| 300 | 174,897 | 26,971 | 0 | FINAL_ONLY / BLOCKED with known HALT |
| 500 | 174,763 | 26,931 | 0 | FINAL_ONLY / BLOCKED with known HALT |

All measured requests were 23,332 bytes. The 500-frame case reaches 3,000 executed frames and 24,000 quote-level units across both legs without raising a ceiling. The complete 250-frame case retains first/last observations and the original accounting equity-series binding.

## Temporal and risk availability

| Classification | Terminal behavior |
| --- | --- |
| MODELED_ALIGNED | Eligible modeled accounting/risk/chart evidence; synthetic common clock only |
| FINAL_ONLY | Supported endpoint metrics; no complete-history drawdown or charts; risk may be BLOCKED |
| INCOMPARABLE | Explain incompatible scenario/window evidence and suppress unsupported aggregate comparisons |
| UNAVAILABLE | Explain missing/invalid evidence and do not fabricate financial output |

Three markets with both stress legs can retain complete histories through 250 frames per market per leg. Larger admitted runs can complete with FINAL_ONLY evidence. Simulation completion, accounting eligibility, risk assessment, historical verification and chart availability have separate visible statuses.

Risk panels preserve actual `PortfolioRiskReport` outcome, decision, observed checks/ceilings, reasons and source status. NORMAL/WARN/REDUCE/HALT describe post-execution hypothetical assessment. BLOCKED is incomplete required evaluation, never successful NORMAL. A known hard HALT can remain visible alongside BLOCKED. REDUCE/HALT neither cancel operational orders nor prevent PAPER orders already simulated. Historical synchronization, empirical correlation and source authentication are never inferred from modeled alignment.

## Provenance

Expandable diagnostics expose configuration version/fingerprint, market/profile/configuration identities, captured strategy/accounting/execution/shock assumptions, original bundle/analysis/result/run/dataset/accounting identities, stress scenario identity, chart-source fingerprints, temporal classification and evidence limitations. Identifiers have copy controls. Labels include HYPOTHETICAL, PAPER ONLY, RESEARCH / READ ONLY, NOT EMPIRICAL CORRELATION and HISTORICAL SYNCHRONIZATION UNVERIFIED. Fingerprints are not signatures or exchange-authenticated attestations.

## Frontend lifecycle and errors

Typed contracts live in `types/portfolioResearch.ts`; API calls use `api/client.ts`. The in-memory Zustand draft is separate from preview and accepted result. Every edit, meaningful connection/session transition, stop-waiting action and workspace unmount retires accepted evidence. Request revision/epoch/identity checks suppress stale success and failure responses. Reconnect never restores a retired preview/result. Repeated unsuccessful reconnect attempts while already disconnected do not prevent independent local REST research.

TanStack Query reads the scenario catalog and performs explicit mutations with expensive retries disabled. There is no input-triggered submission or duplicate simulation polling. AbortController stops waiting/fetching; it does not claim backend cancellation. HTTP 429 explains shared-worker occupancy; 413/422/503/500 provide sanitized guidance without reflecting raw proxy/worker errors. No result or sensitive draft persistence is introduced.

## Native and frontend regression

Final actual results and commands are recorded here before delivery:

- Focused backend: **56 passed** (`tests/test_phase175_terminal.py`).
- Full backend: **PENDING**.
- Frontend tests: **779 passed**, zero failures (`cd frontend && npm test`).
- Frontend typecheck and build: **PASS** (`npm run typecheck`, `npm run build`); existing bundle-size/React Query directive warnings remain non-fatal.
- Local HTTP integration: preview → native terminal plus existing local boundary/transport regression.

Backend coverage includes preparation/exact fingerprints, six stress modes, original-contract fingerprint compatibility, source binding, sparse/incompatible histories, deterministic bounded extrema/context sampling, one worker admission, no duplicate engine runs, response/request cap enforcement, sanitized busy/error states, local HTTP and operational state isolation. Frontend coverage includes navigation, exact allocation, six typed scenarios, authority/fingerprint guards, all risk and temporal states, unavailable charts/deltas, provenance, request identity, session transitions and sanitized errors.

## Chromium acceptance

Reproduce with installed Playwright and Chromium:

```sh
# From repository root; supply the local Python/Chromium paths if different.
python frontend/tests/browser-phase175.py --python /path/to/venv/bin/python \
  --chromium /usr/bin/chromium --output work/phase175-browser
```

The test-only offline harness supplies labeled pinned research profiles and controls transport/fault timing. Financial workflows use actual React, HTTP routes, shared worker and native PAPER engines; financial responses are not mocked. It checks desktop/tablet/mobile widths, one/two/three markets, all six stress scenarios, charts/risk/provenance, keyboard/mobile navigation, invalid capital, FINAL_ONLY preparation, actual 429, browser abort with retained worker occupancy, sanitized 500, reconnect revalidation and unchanged operational authority. Script output separates expected injected HTTP console errors from normal-workflow console/page errors. Small screenshots and the machine-readable report are copied to `docs/acceptance/phase175/` after a successful run.

Result: **PASS**, Chromium 151.0.7922.173. Fifteen workflows, zero normal-workflow console/page errors; two expected injected HTTP error console entries (429 and 500). Viewports: 1920×1080, 1440×1000, 1024×768, 768×900, 390×844. [Browser report](acceptance/phase175/browser.json), [desktop](acceptance/phase175/desktop.png), [mobile](acceptance/phase175/mobile.png).

## Bugs found and corrected

- Repeated disconnected WebSocket reconnect attempts initially retired independent REST research. Only connected-state or session/identity transitions now retire evidence; stale completions remain suppressed.
- Select controls needed explicit accessible names for exact keyboard/browser targeting; all portfolio select names are now explicit.
- Tablet comparison grids initially expanded to their minimum table width; constrained grid tracks now keep tables inside their horizontal scroll containers on tablet/mobile.
- The existing 17.1A module inventory guard was updated for the four new pure portfolio modules while preserving its forbidden-runtime/API/engine ownership checks.
- A watchdog regression fixture raced its 100 ms initial freshness window under CPU contention; it now establishes resting orders, deliberately expires the snapshot and verifies the same independent watchdog cancellation before the 60-second quote interval.
- Hidden modeled execution parameters could invalidate a return to BASELINE; switching mode resets those incompatible controls.
- Browser acceptance uses fetch-cloned bodies because Chromium can evict DevTools response bodies during terminal rendering; this changes only the test harness.
- New native test harnesses were corrected to use keyword-only engine inputs, an explicit offline metadata catalog and the existing actual-HTTP fixture contract.

## Remaining limitations and Phase 17.6 readiness

All evidence is independent-capital hypothetical PAPER modeling. There is no live portfolio execution, wallet signing, custody, durable research job history, historical exchange synchronization or measured cross-market correlation. Complete native retention remains bounded; unavailable histories and risk must remain visible. Stale oracle timestamps and unsupported exposure histories remain unavailable. Preview validates trusted research profiles, not live execution eligibility. Existing deployment/security boundaries and optional ML availability are unchanged.

Phase 17.6 can focus on independent security review, broader adversarial/soak regression and final end-to-end acceptance. This phase's local acceptance does not establish production readiness, verified venue economics or operational trading authority.

## Acceptance gates

| Gate | Result |
| --- | --- |
| Dedicated page, registry, responsive controls, BTC/ETH/SOL allocation | PASS |
| Server preparation, exact fingerprints, PAPER execution/accounting/exposure | PASS focused native tests |
| Risk classifications, six stress scenarios, native comparisons | PASS focused native tests |
| Bounded provenance-linked charts; no fabricated missing financial history | PASS focused native tests |
| Response cap, shared admission, no duplicate engine runs | PASS focused native tests |
| Existing 17.2–17.4 compatibility; operational isolation | PASS focused native tests |
| Temporal semantics, source labels, lifecycle and sanitized errors | PASS |
| Full backend / frontend test/typecheck/build | PENDING |
| Local HTTP integration | PASS focused native tests |
| Chromium and concise documentation | PASS |
