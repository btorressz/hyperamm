# Phase 13.3.2 — Analytics & Simulation/Optimization acceptance

Local Linux acceptance on **October 9, 2026 (America/Los_Angeles)**. Scope is
**13.3C + 13.3D**, delivered in one dedicated draft PR, unmerged. Full Phase 13.3,
Logs, Settings, Phase 13.2A–E and external acceptance are not completed here.

## Preflight and baseline

Fetched current `origin/main` and independently read the GitHub branch/PR metadata.
Exact base: **`8085c5810ce72169f63a0a6c3a0619741b518852`**.
Initial checkout was clean; work uses `phase13/13-3-2-analytics-simulation-ux`,
not main. Verified merged PR #43 (`50f6ab9b42cbd72f905b2ffc319f0ea90b7252c4`),
#44 (`616ab5b7dc1b48c2573cad5c4f41dffadc4cf1c4`) and #45 (base SHA).
Read CODEBASE, ROADMAP, ARCHITECTURE, SIMULATION and PHASE1331_ACCEPTANCE;
inspected actual history, research request/response, metric, scoring, scenario,
accounting, session/freshness and shared component contracts. Reused patterns from
`browser-phase131.py` and `browser-phase1331.py`.

The recording and conceptual visual references mentioned in the request were not
attached/accessible. Existing implemented styling and actual local Chromium were
used; those external references were not inspected. No new charting framework,
backend application code, terminal schema, package manifest or lockfile changed.

Baseline before application edits: **262 frontend passed, 0 failed/skipped**;
TypeScript and build passed. Full Python 3.12.14 suite with `test,ml,redis,yahoo`:
**1124 passed, 1 failed, 0 skipped**, one upstream warning, 38.46s.
The failure is `test_generated_terminal_schema_is_current`, the existing inline
Pydantic Decimal schema-pattern difference. No schema regeneration, test weakening,
skipping or suppression was performed.

## Analytics implementation

- Session overview uses backend vault `equity_quote`, **`session_pnl_quote`**,
  drawdown, utilization and signed base inventory plus execution-summary fills /
  filled notional, execution quality and market/accounting modes. Current net PnL
  is not substituted for session PnL. No capital/reserve/equity arithmetic is added.
  Exact Decimal strings and unavailable TESTNET economics remain inspectable.
- Four retained research views remain: equity / peak equity, reported net PnL,
  signed base exposure, drawdown / capital utilization. PnL and inventory use
  green/red baseline plots with a zero reference. Quote/base/percentage units,
  legends, exact-value crosshair readouts, keyboard reset and observation tables
  make the charts interpretable without inventing separate realized/unrealized
  history series.
- SESSION / 1M / 5M / 15M / 1H query actual backend ranges. A session query supplies
  authoritative metadata. Backend `available_ranges` requires retained span
  >= range seconds minus one; unavailable controls are disabled. A saved default
  that is not fully retained temporarily displays SESSION, without overwriting the
  preference. The preferred range becomes effective when available. Size changes
  are part of query identity; no client time filter pretends to extend retention.
- Metadata separates `retained_points` / `retained_seconds` from returned bounded
  samples and exposes session, oldest/latest times. Backend ranges end at the latest
  retained point. Distributions count the **returned samples**, not unsampled total
  retention, trading duration or causal strategy outcomes.
- Fill/notional, spread capture, mature markout, adverse rate and action-based churn
  have expandable explanations. Mature support is required; pending fills are not
  complete markouts and unavailable ratios stay unavailable. PAPER execution
  evidence is simulated, and TESTNET completeness remains explicit.

## Shared history, lifecycle and Vault compatibility

`useTerminalHistory` reuses `useResearchSession`'s synchronous connection epoch.
Query keys include client process ID, terminal session ID, epoch, range and size;
GET consumes AbortSignal, checks the session before/after awaiting, validates the
response session/range and requested point bound, and checks accepted envelope
freshness at completion. Retired/reconnected requests cannot seed current charts.
Analytics now has the same process/session keyed mount and historical prop pattern
as Vault. Last accepted same-identity/range/size history may freeze as **historical**
while disconnected; a replacement identity cannot reuse it. New-session data,
range changes, size changes and errors never use a previous-session placeholder.

REST history **does declare session ID but does not declare process ID**. Client
process/epoch checks do not create server-side or cryptographic process binding.
This is a local attribution safeguard, not authenticated durable provenance.

`HistoryChart` now reconciles added/removed/changed series instead of permanently
capturing initial `lines`. Height / axis changes recreate the chart and clean old
observers. ResizeObserver tracks width; unmount removes the chart and observers.
Fit occurs on first usable evidence or a new fit identity, not every polling update;
keyboard Reset view is explicit. Finite coordinate checks include scaling overflow.
Terminal compaction keeps the existing first-per-sequence identity and latest
sequence per second bucket, bounded to 1000; timestamps are sorted for the library.
Tooltips use that same compaction. Invalid timestamp points cannot crash plotting.

Lightweight Charts skips whitespace when rendering lines, so whitespace alone can
bridge missing evidence. Plotting splits **contiguous finite segments** into separate
series and retains whitespace time coordinates. Tests assert that no segment crosses
a missing value and that removed/config-changed segments are cleaned up. No economic
value is imputed. Exact economic values remain in tables/readouts; floating point is
used solely for plot coordinates. A chart with no finite metrics says unavailable.

Vault keeps `SessionCharts()` with its session default and all existing accounting
consistency/provenance components, mounts and protections. Preserved tests, live
Vault chart mounts at all six viewports, actual Analytics restart, history-race
fixtures and a direct real-chart resize/config/unmount probe cover shared behavior.
Agents and Vault were not redesigned again.

## Simulation workflow and result mapping

Uses the actual scenario catalog (13 supported scenarios at this base), with backend
descriptions. Preserves Balanced (8 candidates), Inventory (4) and AdverseFlow (8)
grids and explains the varied groups, training / validation scenarios, request cap
32, backend hard cap 128 and top five. Missing required catalog scenarios disable
the preset action rather than sending unsupported scenarios.

UI input is a whole number **2–1000** frames; invalid/blank/fractional input is
explained and cannot submit. Standalone requests keep `max_frames=frames`,
`record_trace=true`, `trace_max_points=250`. Grid requests preserve the existing
`min(frames,250)` per scenario. Backend validation remains authoritative; no
allowlist, objective, immutable safety field or computational bound was modified.

A synchronous request gate prevents the double-click window and enforces one local
research submission. Each accepted request captures scenario, frames and preset.
Controls may change to configure the next request; busy text and completed headers
use the captured request/result, not current controls. Generation identity retires
responses on unmount, and old completion cannot release a newer request's gate.
No fabricated progress percentage or assertion that browser cancellation kills the
backend worker is added. Existing 429 message is reused; 422, 503, unexpected 500
and network failure have actionable messages.

Metrics group exact reported quote equity/PnL, return, maximum drawdown and base
inventory, with execution, realized/unrealized, inventory/risk, order lifecycle and
state evidence expandable. Backend **`return_pct` already means percent**; it gets
only the `%` suffix. Drawdown, utilization, fill activity, adverse rates, churn and
HALT fractions are multiplied once for display. Basis points remain basis points;
null scores/markouts/rates are not zero.

Six independent trace views map actual bounded response fields:

| View | Backend fields | Display units |
| --- | --- | --- |
| Simulated equity | `equity` | quote |
| Simulated session PnL | `session_pnl` | quote, signed |
| Market/perpetual reference | `mid`, `mark`, `oracle` | quote / base |
| Simulated inventory | `inventory_base` | base, signed |
| Simulated drawdown | `drawdown_pct` | fractional input to percent display |
| Quote/order activity | `desired_quote_count`, `agent_quote_count`, `authorized_quote_count`, `open_order_count` | count |

Frame-state details preserve original timestamp, sequence, risk, regime, toxic-flow,
execution quality, reference confidence and fills. Trace normalization orders unique
safe backend **sequences**, retaining the first duplicate identity, with a UI/request
cap 250. A display-only **simulated frame index** is supplied to the chart and tick /
crosshair formatter; it is not wall-clock time. Same-second distinct frames remain
separate. Missing/nonfinite values create gaps, invalid timestamp strings remain
inspectable without discarding valid frame identity, and empty/single-point traces
are handled. Separate runs replace data under a run fingerprint; they never join
live history or each other's performance series.

Backend limitations are displayed with full engine/run/dataset/strategy identities.
The UI additionally explains queue, hidden liquidity, latency, stochastic fills,
execution-quality and future-profitability limits. No persistent research vault,
notebook, saved strategy or deployment action is introduced.

## Candidate comparison

Baseline plus the first five returned candidates retain backend ranking; no frontend scoring or
reranking formula. Shows training score, validation score, reported training-score
delta against baseline, requested/valid/rejected counts and objective context.
Two native selectors compare candidates' reported updates, aggregates, per-scenario
performance, score components, run identities and baseline deltas. Strategy / agent
parameter groups keep original keys and exact values separate. A baseline label
never implies unreported parameter defaults. Missing validation/deltas remain
Unavailable; rejection reasons are inspectable and not successful candidate rows.
Full fingerprints and objective/training/validation provenance are expandable.
Validation is evaluation-only, not guaranteed future out-of-sample profitability.

## Commands and exact results

Frontend (Node 24.19.0, unchanged dependency lock):

```bash
cd frontend
npm ci --offline --cache /workspace/.hyperamm/npm-cache
npm test
npm run typecheck
npm run build
```

**310 passed, 0 failed/skipped**: all previous 262 plus **48 new** regressions.
TypeScript/build exit 0. New coverage exercises range preferences/availability,
session/process/connection/stale/future/range/size completion guards, sequence /
second-bucket identity, missing/nonfinite/overflow coordinates, once-only percentages,
series reconciliation/segment cleanup, retained sample counts, exact financial units,
markout support, frame validation, request admission/retirement, trace identities /
bounds, candidate order/parameters/nulls/rejections and research HTTP errors.
The Node CommonJS compilation loads the installed ESM chart implementation for
these tests; CSS/render/lifecycle are checked in Chromium. No historical test is
replaced or weakened. Existing non-failing build directive warnings and Node
server-rendered Zustand storage notices remain.

Backend (Python 3.12.14; unchanged application):

```bash
cd backend
/workspace/.hyperamm/venv/bin/python -m pip install -e '.[test,ml,redis,yahoo]'
/workspace/.hyperamm/venv/bin/python -m pip check
/workspace/.hyperamm/venv/bin/python -m compileall -q app
/workspace/.hyperamm/venv/bin/python -m pytest -q
/workspace/.hyperamm/venv/bin/python -m pytest -q \
  tests/test_phase10_api.py tests/test_phase10_executor.py \
  tests/test_phase10_simulation.py tests/test_phase10_optimizer.py \
  tests/test_phase11_accounting.py tests/test_phase11_simulation.py \
  tests/test_phase12_terminal.py tests/test_phase12_websocket.py
```

`pip check` / compileall pass. Final complete suite **1124 passed, 1 failed,
0 skipped**, one upstream Starlette/httpx warning, 34.90s. Focused suite
**173 passed, 0 failed/skipped**, one warning, 14.60s. The single unchanged generated
schema failure remains an integration gate. Backend economic behavior did not change.

[Baseline frontend](acceptance/phase1332/baseline-frontend.txt),
[baseline backend](acceptance/phase1332/baseline-backend.txt),
[frontend](acceptance/phase1332/frontend-results.txt),
[typecheck](acceptance/phase1332/typecheck-results.txt),
[build](acceptance/phase1332/build-results.txt),
[complete backend](acceptance/phase1332/backend-results.txt),
[focused backend](acceptance/phase1332/backend-focused.txt).

## Actual Chromium acceptance

Local system Chromium with Playwright and separate loopback Uvicorn/Vite:

```bash
cd backend
MARKET_DATA_MODE=DEMO EXECUTION_MODE=PAPER \
ENABLE_HYPERLIQUID_TESTNET_ORDERS=false \
/workspace/.hyperamm/venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
# Separate process:
cd frontend
npm run dev -- --host 127.0.0.1
# From repo root, use only the dedicated acceptance Uvicorn PID:
/workspace/.hyperamm/venv/bin/python frontend/tests/browser-phase1332.py \
  --output work/phase1332/browser --backend-pid <dedicated-pid>
# Reuse recorded live results for fixture/lifecycle completion:
/workspace/.hyperamm/venv/bin/python frontend/tests/browser-phase1332.py \
  --output work/phase1332/browser --fixtures-only
```

**72 live route/viewport checks + 26 recorded workflows; zero browser page
exceptions.** Twelve active routes at **1920×1080, 1440×900, 1366×768, 1024×768,
768×900, 390×844**, with no document overflow. Both populated research pages
also receive all six viewport checks. Actual Analytics range query/persisted default,
four charts, keyboard explanations, Vault charts, scenario description, invalid
input, fingerprints and comparison selectors pass. Actual isolated FLASH_MOVE
runs 80 frames with **8 PAPER fills**, and Balanced optimization runs 20 frames
per scenario. These are backend outputs, not fabricated financial evidence.

Active configuration, stopped strategy, kill state, ledger version and terminal
orders were compared before/after research and result inspection; unchanged.
All observed POSTs are `/simulation/run` or `/simulation/optimize`, with zero
other mutation requests. No signed TESTNET/MAINNET order was sent. Actual dedicated
backend stop/restart freezes historical Analytics evidence, then mounts new-session
history without old identity. The acceptance replacement backend exits cleanly.

Browser-only fixtures cover backend-unavailable ranges, saved unavailable preference,
size queries, missing equity, 5% drawdown / 25% utilization, retained distribution
counts, suspended history across process/session replacement, history error/retry,
disconnected historical charts, busy duplicate prevention, controls changed while
pending, same-second trace frames, missing/nonfinite trace values, invalid timestamps,
Inventory preset, null validation/deltas, rejected candidate reasons, 422/429/503/500 /
network messages, and unmounted completion retirement. A real mounted HistoryChart
probe changes series config/height/width, uses keyboard Reset and asserts all its
ResizeObservers are released on unmount. Fixtures change browser responses only;
they do not book backend economics or send venue orders.

Harness corrections during development included null-safe loading waits, explicit
select labels, Vite ESM/CommonJS import handling, library-owned observer accounting
and routed-WebSocket close callback incompatibility. A focused percentage-format
assertion caught the percent-suffix spacing; it was corrected. Final browser runs
reuse the completed live report and pass the full fixture/lifecycle suite. The
only recorded live console diagnostic is a favicon 404; that is distinct from page
exceptions. Initial fixture close-callback diagnostics were eliminated in the final
harness. This is local feature/viewport acceptance, not full WCAG certification.

[Machine-readable final browser report](acceptance/phase1332/browser-results.json),
[raw live simulation](acceptance/phase1332/live-simulation-result.json),
[raw live optimization](acceptance/phase1332/live-optimization-result.json).

Desktop screenshots were refreshed against final source using fresh actual
FLASH_MOVE/80-frame and Balanced/20-frame responses; the top-five display cap
was asserted again. [Final capture probe](acceptance/phase1332/final-capture-results.json).

Actual implementation screenshots (Chromium, America/Los_Angeles):

- [Live Analytics, 1440px](acceptance/phase1332/analytics-live-1440.png).
- [Live Simulation and candidate comparison, 1440px](acceptance/phase1332/simulation-live-1440.png).
- [Browser-fixture Analytics with gaps, 390px](acceptance/phase1332/analytics-fixture-390.png).
- [Browser-fixture Simulation/null validation/rejection, 390px](acceptance/phase1332/simulation-fixture-390.png).

## Reuse, additions and remaining gates

Reuses Badge, TerminalPrimitives, Zustand display/terminal, TanStack Query, API
client, accountingValue/exactDecimal/evidenceTime, useResearchSession, SessionCharts,
SimulationPanel and Lightweight Charts. Reuses phase13/phase1331 palette and layout.
New: `StateDistribution`, `simulation/SimulationTrace`,
`simulation/CandidateComparison`, `simulationResearch.ts`, `phase1332.css`, focused
Node regressions and the optional Chromium harness. Range/overview/execution helpers
remain in Analytics instead of creating an unnecessary component tree.

**13.3C and 13.3D: IMPLEMENTED / LOCAL ACCEPTANCE.** 13.3E/F and full 13.3G remain
pending. macOS, real external providers/Redis, signed TESTNET, extended soak,
unrelated audit gates and the generated-schema issue remain open. Client/chart
checks do not authenticate server process identity. In-memory observations and
results are not durable research history. PAPER crossing does not establish real
venue economics or future profit. No trading authority, signing, agent/risk/scoring,
AMM/accounting formula, Logs/Settings enhancement, new infrastructure, database,
Docker, GitHub Actions, `.github/`, provider, public hosting or automatic deployment
change. **One draft PR only; do not merge automatically.**
