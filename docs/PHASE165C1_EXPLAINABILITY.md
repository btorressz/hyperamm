# Phase 16.5C.1 — Scenario vs Historical Replay Explainability Studio

**Implementation only · frontend foundation · draft PR · no native TypeScript/Node/Chromium results yet.**

Base: merged [Phase 16.5B PR #64](https://github.com/btorressz/hyperamm/pull/64), which is a pure Python quantitative comparison engine. The merged code has **no HTTP comparison endpoint**, no server-issued UI receipt transport and no frontend integration. This C.1 PR does **not** invent or silently implement one.

## ADD / ENHANCE / REUSE

- **ADD** `frontend/src/types/scenarioReplayComparison.ts`: strict Phase 16.5A/B display types for comparison provenance, metric rows, original source/runs, confidence limits, missing evidence and receipt identity.
- **ADD** `frontend/src/utils/scenarioReplayComparison.ts`: bounded read-only JSON parsing and display validation; exact unit/source registry matching `quantitative.py`; reject unsupported `ALIGNED`, live authority, direct deltas/ranking, wrong market/engine classification, invalid source/segment identity, wrong metric units/origins and coerced floating-point financial values. Decimal values remain **strings**. Browser validation is not cryptographic fingerprint verification.
- **ADD** `frontend/src/components/scenario-replay-comparison/`:
  - `ScenarioReplayComparisonWorkspace.tsx`: read-only local backend-receipt JSON inspector, source pairing state and clear C.2 integration gate.
  - `ComparisonMetrics.tsx`: independent per-side metric table grouped by PnL, fills, risk, inventory and PAPER Vault accounting. Exact values are in `title`; UI truncates long decimal fractional strings **for display only**. `0` remains available, `null` remains unavailable, and blocked comparisons have **no financial rows**.
  - `ComparisonExplainability.tsx`: independently labeled scenario and selected historical source, matching and differing config dimensions, closed backend reason codes, raw result/run fingerprints, receipt timing and license/authenticity caveats.
  - `ComparisonTraceCharts.tsx`: reusable existing `SimulationTrace` and `HistoryChart` renderer, **only if** future C.2 supplies original scenario/historical source evidence matching selected run/segment identifiers. No chart is fabricated from metric totals, and no cross-segment merging or synchronized/overlayed performance line exists.
- **ENHANCE** `frontend/src/pages/Simulation.tsx`: preserve existing scenario optimizer and Vault comparison; add three tab-like workspace views for Scenario/Optimization, Historical Replay and Scenario vs Historical. No sidebar route, duplicate simulator or operational controls.
- **ENHANCE** `frontend/tests/run.cjs`: compile the new validator and run `frontend/tests/phase165c-comparison.test.cjs`.
- **ADD** scoped `frontend/src/phase165c.css`: responsive comparison panel, stacked tablet/mobile layout, native table scrolling, keyboard focus states and dark-terminal styles.
- **REUSE** existing `Panel`, `Empty`, `Badge`, `StatusBanner`, `SimulationTrace`, `HistoryChart`, `readSegmentArchive`, terminal styling, React 19 and current state architecture.

## What C.1 already does

The new `#/simulation` workspace renders a complete **read-only receipt viewer** and source-quality explanation layout. A developer may paste **a real `phase165b-v1` backend-generated JSON receipt** (limited to 256 KB) into its local inspector. It is parsed in the browser; **no file, wallet, historical L2 observation or receipt is uploaded to the server**. The UI only validates display shape and denies unsupported financial authority. A tampered self-consistent receipt cannot be authenticated in a browser without the original server evidence.

A `CONTEXT_ONLY` receipt shows descriptive scenario and selected replay segment values **side by side**, never as a delta, normalized return, rank or profit comparison. An `INCOMPARABLE` receipt shows provenance and the reason(s) for blocking metrics. The reserved `ALIGNED` status is rejected.

Original trace charts require the **separate native SimulationResult and HistoricalReplayResult**, not contained in the 16.5B metric receipt; the C.1 chart component has explicitly typed optional source props for C.2 to supply after server verification. Without them, it clearly displays an unavailable-evidence message. The displayed value never implies complete venue history or real fills.

**No financial arithmetic or returns are computed in JS.** Existing backend metrics are displayed verbatim or visually truncated while retaining the full exact decimal string in a tooltip.

## Phase 16.5C.2: mandatory integration gates before calling this feature complete

1. Create a **bounded, local-only, read-only authenticated-by-existing-single-operator-boundary** server comparison endpoint or equivalent safe workflow that invokes the already merged `compare_quantitative_paper` using a same-job `CapturedScenarioResult` and a real validated `HistoricalReplayResult`. Do not recompute financial comparisons in JS or build a second engine.
2. Decide how to transport or retrieve paired receipts. An unconstrained client POST carrying a full 5,000-frame replay/result archive can exceed HTTP and memory limits. Prefer a safe bounded same-worker orchestration, or another explicitly documented transport respecting the current local single-slot admission, POST body limits, source/fingerprint checks and worker lifecycle.
3. Bind selected scenario and recorded dataset/replay segment identities to server-verified values and invalidate the UI on source selection changes, backend restart, aborted requests or stale responses. **Browser cancellation does not release backend worker admission.**
4. Wire the verified server `QuantitativeComparison` and original validated trace sources into `ScenarioReplayComparisonWorkspace` props; keep developer-only JSON inspection optional, do not rely on it as a production comparison workflow.
5. Verify all financial values come from the existing backend; independently reset segments remain separate; reject incompatible market/engine/strategy/report hashes.
6. Run `cd frontend && npm ci && npm run typecheck && npm run build && npm test`, then actual Chromium cases: BTC/ETH/SOL, 0 fills, missing Vault value, real supported scenario response, segmented/gapped replay, blocked market, stale responses, disabled storage 503, busy worker 429, malformed receipt and 390/768/1024/1440/1920 widths. Keep operational strategy/kill switch/signer unchanged.
7. Run backend integration/fixture and complete native regressions; ensure pre-existing static-documentation failures are reported accurately, not suppressed.

## Important safety/evidence limits

- The Phase 16.5A classification is not a statistical significance test or verified paired market data. `ALIGNED` remains unavailable.
- Scenario and historical segments may have different simulated market paths, sample intervals, starting capital, strategies, execution models, risk and funding convention. No direct numerical performance comparison is justified.
- No combined return or equity curve across historical receipt gaps; each segment's capital/risk/inventory is independently reset.
- Fingerprints identify copied evidence and can detect accidental mismatches but do not independently authenticate source licensing, exchange events, actual passive fills or execution costs.
- No Docker, GitHub Actions, K8s, new dependency, worker, market data importer, custody, signer, live order or mainnet path.
- **Native acceptance status for this C.1 PR: NOT RUN.** PR #64 was merged without native B test execution in its GitHub-only authoring workflow; do not interpret its merge as proof of a green full backend suite.

**DO NOT MERGE AUTOMATICALLY.** Codex 16.5C.2 should build from this feature branch after C.1 review/merge and document actual verification.
