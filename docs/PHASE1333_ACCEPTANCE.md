# Phase 13.3.3 — Operational Logs, Settings & final research UX acceptance

Local Linux acceptance on **October 9, 2026 (America/Los_Angeles)**. Scope:
**13.3E + 13.3F + scoped 13.3G**, completing the six-page research/operations
workspace. Dedicated draft PR; **do not merge automatically**. This report does
not establish production, macOS, external-provider, Redis or signed TESTNET readiness.

## Verified preflight

Exact base/HEAD before application edits:
**`fc8c6303f4ac0114d11b1a6b1f2da30a55e7b315`**.
Current origin/main was fetched and rechecked immediately before delivery.
PR #43 merged at `50f6ab9b42cbd72f905b2ffc319f0ea90b7252c4`;
#44 at `616ab5b7dc1b48c2573cad5c4f41dffadc4cf1c4`;
#45 at `8085c5810ce72169f63a0a6c3a0619741b518852`;
#46 at the exact base above. GitHub connector metadata independently verified all four.
Working tree was clean before implementation; branch:
`phase13/13-3-3-logs-settings-final-ux`.

The provisioned checkout initially preceded these merges. The process sandbox
could not reach the configured proxy or launch Node's esbuild subprocess.
Current text sources were first obtained through the GitHub connector and verified
by Git blob/tree/commit SHA; ordinary Git fetch then succeeded with approved
execution outside that sandbox. A refetch and targeted restoration of fourteen
absent prior acceptance images completed the checkout. No prior evidence was
deleted and no remote history was rewritten. Automatic review rejected a broad
forced checkout; the subsequent restoration only targeted verified absent images
after a clean-tree check.

Read CODEBASE, ROADMAP, ARCHITECTURE, TERMINAL, PHASE1331_ACCEPTANCE and
PHASE1332_ACCEPTANCE; inspected repository structure, actual Logs/Settings,
event retention/query/order, terminal stores, session/epoch/freshness guards,
reference evidence and existing browser harnesses. No backend application,
generated schema, dependency manifest or lockfile changed.

Baseline: **310 frontend passed, 0 failed/skipped**; TypeScript/build passed.
Installing the requested backend extras resolved three initial collection errors
for missing fakeredis. Complete installed baseline: **1124 passed, 1 failed,
0 skipped**, one warning, 37.58s. The sole failure is the unchanged
`test_generated_terminal_schema_is_current` Pydantic Decimal schema mismatch.

## Operational Logs — 13.3E

- Existing GET-only `/terminal/events`, categories, IDs, original records,
  newest-first backend ordering and retention are preserved. UI selects
  **100 / 200 / 500** requested events. Returned, matching and simulated-loaded
  counts are separate from the maximum 500 retained records; total retained-store
  count is explicitly unavailable. Selected-category counts never claim to count
  other categories.
- Case-insensitive trimmed search examines only loaded message/category/states/
  reference/event ID/version. Search is component-local and is neither persisted
  nor exported. Clear search and Reset filters are explicit; the latter resets
  category/search/display order while preserving the requested bound.
- Newest-first displays the response position unchanged. Oldest-first uses actual
  timestamp comparison, including sub-millisecond fractions, with original
  response position as the tie-breaker. Event IDs never fabricate chronology.
  Both paths leave original records/order immutable.
- Native expansion buttons expose full ID, original timestamp, category, previous/
  new state, full message, reference, version and simulated flag. Preview messages
  truncate at 160 characters; full text remains available. React rows use event ID.
  Null, unavailable and version zero remain distinct. A missing state does not
  create an invented transition.
- Neutral category badges do not turn RISK into an invented severity. SIMULATED
  follows the event flag; PAPER and signed TESTNET execution are not inferred.
  Explanations distinguish subsystem observations from actual order/fill evidence.
  Tables scroll within focusable, named regions on narrow screens.
- Loading, successful backend-empty, filtered-empty, malformed/incompatible
  response and HTTP failure are distinct. Failed requests do not become empty
  successful searches. Retry is explicit; prior successful data is not displayed
  as a new successful response after an error.

### Session and request identity

Reuses `useResearchSession`'s synchronous connection epoch and `sessionCurrent`.
Query identity includes **process/session/epoch/category/requested limit**.
Requests consume AbortSignal, check identity before and after awaiting, and validate
the returned session, ordering/capacity, bound, category, unique IDs and record types.
Polling stays at five seconds only while the accepted terminal is current; retry
and focus refetch are disabled and inactive query GC is zero.

Mounted Logs may freeze its last accepted response as **HISTORICAL**, only for the
same process/session/category/limit. It does not start historical REST requests.
Reconnect discards the prior-epoch local response until a new accepted request
completes. Process/session replacement remounts Logs; stale completions cannot seed
the replacement. Changing category/limit while disconnected cannot reuse another
selection's local evidence. There is no durable browser event archive.

The REST response declares a **session ID but no authenticated process ID**.
Client process/epoch checks are attribution safeguards, not cryptographic server
identity or proof of complete venue history. Export also checks identity at click
time and checks the connection epoch for current evidence.

### Bounded JSON export

The action is **Export loaded events (bounded session evidence)**. It exports only
the currently selected loaded records in the selected display order, retaining
original declared field names and null values. Metadata includes generation time,
client-observed process/session, requested category/limit, loaded/exported counts,
maximum retention, backend/display ordering and CURRENT/HISTORICAL display state.

An explicit field allowlist excludes arbitrary extra record/response fields,
internal diagnostics, browser storage and unrelated app state. Search text is
excluded. No backend export endpoint or sample exports are committed. A temporary
download Blob URL is revoked after use. Existing backend diagnostic sanitization
already redacts credential-shaped values and provider URLs; the UI additionally
asks users to review operational messages/references before sharing. It does not
claim arbitrary free text is guaranteed free of sensitive information.

## Settings — 13.3F

- Layout and Charts groups expose Comfortable/Dense, Expanded/Collapsed sidebar,
  SESSION/1M/5M/15M/1H and 100/300/600/1000 observations. The existing
  `hyperamm-display-v1` persistence key remains. Only those four fields persist.
  Hydration validates types/allowed values and excludes unowned fields/functions.
  Unsupported values use documented defaults; malformed JSON leaves safe defaults.
- Feedback checks owned persisted values before claiming a local save; unavailable
  storage is described as applying preferences to the page without persistence.
  These are browser-only preferences, not shared authenticated profiles or backend
  trading configuration.
- **Reset display preferences** requires an inline confirmation naming all four
  defaults: **false density / false sidebar collapse / session / 600**.
  Sidebar collapse is included. Cancel preserves preferences. Reset uses one
  Zustand action, writes only owned display fields and leaves unrelated browser
  storage, terminal/market, ledger, risk/kill, strategy and simulation state intact.
- A saved range remains saved while Analytics temporarily displays SESSION if
  server retention cannot support it. Reset/refresh leaves Analytics, Vault and
  Sidebar functional. Settings also works before the first accepted terminal
  snapshot; local controls stay editable while backend evidence is unavailable.
- Read-only runtime values use accepted terminal market/execution modes, TESTNET
  eligibility, reference-firewall flag, contract, sequence, process/session/emission,
  transport state and reconnect attempts. Missing Redis/environment configuration
  is unavailable. No raw environment, private key or signing controls exist.
  TESTNET eligibility does not establish authenticated account/order acceptance.
- Separate authority metrics distinguish transport, market integrity, consensus,
  RiskFirewall, FinalQuoteAuthorization, manual KILL and accounting consistency.
  Manual KILL is distinct from risk HALT; SHADOW remains observational.
  Supported deployment stays loopback, one local operator and one backend worker.

### Health and provider limitations

SystemHealth preserves every backend-reported subsystem status/reason. Its current
label now requires matching process/session and a fresh accepted envelope, in
addition to connected transport. Disconnected, expired or mismatched evidence is
HISTORICAL and cannot produce a green current-health badge. No underlying
WebSocket sequencing or quote/risk decision changed.

ProviderHealthSummary uses only actual `t.references.evidence` records. Roles use
the actual IDs: RedStone primary external oracle, Hyperliquid oraclePx native oracle,
Kraken independent exchange and CoinGecko tertiary aggregate. Reported midpoint/
mark evidence remains separately described as comparison evidence. Unknown roles
remain unavailable. Missing records do not imply configured/enabled providers.
Yahoo is excluded from the terminal's authoritative reference contract; no Yahoo
poller or phantom row is added, and its separate research-only authority is NONE.

Exact reported prices, source and observation timestamps, advancing age, reported
stale/healthy state, transport/quality, status and error remain inspectable.
Source freshness is **backend-reported at emission**, not renewed by a fresh
WebSocket envelope. Provider freshness budgets are not exposed, so no new
client-authoritative freshness cutoff is invented. Historical source evidence
does not claim current freshness. The shared existing TerminalDiagnostics panel
above Settings supplies last accepted frame, envelope age, reconnects and
stale/future/replay/schema/order/time rejection counts without a second calculation.

## Reused and new implementation

Reuses React, TanStack Query, Zustand, Badge, TerminalPrimitives, TerminalDiagnostics,
EventTimeline, SystemHealth, useResearchSession, terminal/display stores,
researchEvidence, terminalIntegrity, current display projection and exact financial
formatting. Existing styles.css, phase13.css and research styles remain; phase1333.css
is scoped to Logs/Settings. No new chart/framework package or global page redesign.

New component: `components/settings/ProviderHealthSummary.tsx`.
New hook: `hooks/useTerminalEvents.ts`.
New helper: `utils/terminalEventView.ts`.
New style: `phase1333.css`.
EventDetails remains in the existing EventTimeline; filters/export and preference
controls remain in their existing pages rather than creating another management
system. New focused Node and optional Chromium harnesses are registered/retained.

## Commands and exact automated results

```bash
cd frontend
npm ci --offline --cache /workspace/.hyperamm/npm-cache
npm test
npm run typecheck
npm run build

cd ../backend
/workspace/.hyperamm/venv/bin/python -m pip install -e '.[test,ml,redis,yahoo]'
/workspace/.hyperamm/venv/bin/python -m pip check
/workspace/.hyperamm/venv/bin/python -m compileall -q app
/workspace/.hyperamm/venv/bin/python -m pytest -q
/workspace/.hyperamm/venv/bin/python -m pytest -q \
  tests/test_phase10_api.py tests/test_phase10_executor.py \
  tests/test_phase10_simulation.py tests/test_phase10_optimizer.py \
  tests/test_phase11_accounting.py tests/test_phase11_simulation.py \
  tests/test_phase12_terminal.py tests/test_phase12_websocket.py \
  tests/test_phase8_risk_firewall.py
```

Node 24.19.0 / Python 3.12.14. Final frontend **376 passed, 0 failed/skipped**:
all prior 310 plus **66 new** cases. TypeScript and production build exit 0.
Final complete backend **1124 passed, 1 failed, 0 skipped**, one warning, 62.59s.
Focused backend **182 passed, 0 failed/skipped**, one warning, 40.24s.
Pip check, compileall and diff whitespace checks pass. The sole known schema
failure remains unchanged; no generated-schema correction, suppression or test
weakening was attempted. Build retains non-failing TanStack client-directive notices
and a main-chunk size advisory (~506 kB).

[Concise actual test/workflow summaries](acceptance/phase1333/results.md).
Large command dumps, actual research responses and intermediate failed runs stay
in ignored work/. Four representative images are committed; old acceptance
directories remain untouched.

## Browser and six-page integration — 13.3G

Actual local Uvicorn and Vite, system Chromium via Playwright, timezone
America/Los_Angeles. Runtime: MARKET_DATA_MODE=DEMO, EXECUTION_MODE=PAPER,
ENABLE_HYPERLIQUID_TESTNET_ORDERS=false. Strategy stays stopped; real research is
isolated PAPER simulation, with no venue orders or real credentials.

```bash
# From repository root, with dedicated local backend/frontend already running:
/workspace/.hyperamm/venv/bin/python frontend/tests/browser-phase1331.py \
  --output work/browser-phase1331-regression
/workspace/.hyperamm/venv/bin/python frontend/tests/browser-phase1332.py \
  --output work/browser-phase1332-regression
/workspace/.hyperamm/venv/bin/python frontend/tests/browser-phase1333.py \
  --output work/browser-phase1333 --backend-pid <dedicated-demo-backend-pid>
# Retry only isolated fixtures against the saved successful live report:
/workspace/.hyperamm/venv/bin/python frontend/tests/browser-phase1333.py \
  --output work/browser-phase1333 --fixtures-only
```

| Harness | Route/viewport checks | Workflows | Page exceptions |
| --- | ---: | ---: | ---: |
| Agents / Vault regression | 72 | 17 | 0 |
| Analytics / Simulation regression | 72 | 25 | 0 |
| Logs / Settings final acceptance | 72 | 19 | 0 |
| **Total** | **216** | **61** | **0** |

Each route matrix covers all twelve active routes at six widths. Final 1333 and
1332 sizes are exactly **1920×1080, 1440×900, 1366×768, 1024×768, 768×900,
390×844**; the older Agents/Vault harness also exercises six widths at height 900.
No document-level horizontal overflow; table regions retain their own horizontal
scroll. Browser workflows, rather than screenshots alone, verify functionality:

| Workspace | Verified evidence/workflows |
| --- | --- |
| Supervisory Agents | Six cards/Supervisor, unavailable/warmup/degraded evidence, SHADOW authority, keyboard details, filters/errors and retired requests. |
| Research Vault | Backend-owned exact economics/provenance, economic fingerprints, ledger filters/details/consistency, partial TESTNET fixtures, old-session rejection and shared charts. |
| Analytics | Four charts, server retention/range controls, unavailable saved-range fallback, once-only percent conversion, real gaps, returned-observation distributions, historical labels and chart cleanup. |
| Simulation & Optimization | Actual catalog, frame validation, preserved presets, captured/single request, capacity/HTTP errors, real PAPER run and grid, six frame-index traces, candidate comparison/null scores and full fingerprints. |
| Logs | Categories/search/reset/order/keyboard expansion; loaded JSON download validated; 500-row bound; empty/error/malformed/retired responses; real restart and process/session/connection-epoch races. |
| Settings | Four preferences and refresh/reset/cancel; saved-range compatibility; current/read-only runtime; provider unavailable/stale/error/source-time evidence; historical health and initial/disconnected editable preferences. |

The six specified cross-page transitions pass. Desktop Sidebar collapse and mobile
drawer keyboard dismissal remain functional. Actual backend stop/restart freezes
mounted Logs as historical, removes current-health styling, allows browser edits
and switches to a new process/session without prior-session evidence. Synthetic
stale/future/malformed/replayed frames exercise the existing rejection store.
Disconnected Logs makes zero event requests across an entire five-second interval.
Historical export is labeled; arbitrary response diagnostics/storage are excluded.
Settings changes/reset preserve strategy configuration, manual kill, orders and
ledger evidence. New Logs/Settings workflows issue **zero mutation requests**;
1332 issues only existing isolated research POSTs.

Development runs exposed an existing Vault chart-readiness race; the older harness
now waits for chart canvases before retaining its original assertion. An initial
Analytics/Simulation optimization wait timed out; a subsequent complete run passes
all 25 workflows. New-harness corrections included explicit accessible select names,
Zustand window-storage setup, expansion-state expectations after filtering, the
actual setTerminal method and independent copies of reference fixtures. Failed
runs are not counted as acceptance; no economic/optimizer logic changed.

## Representative screenshots

- [Actual DEMO/PAPER Logs, 1440](acceptance/phase1333/logs-live-1440.png).
- [Actual DEMO/PAPER Settings, 1440](acceptance/phase1333/settings-live-1440.png).
- [Browser-only Logs long/null/simulated fixture, 390](acceptance/phase1333/logs-fixture-390.png).
- [Browser-only historical/stale-provider Settings fixture, 390](acceptance/phase1333/settings-fixture-390.png).

Live stopped-strategy screenshots correctly show unavailable reference evidence
where the backend has not reported it. Fixture screenshots are synthetic browser
states, not signed fills, account authentication or actual external-provider activity.

## Final status and remaining gates

**13.3A–G: IMPLEMENTED / LOCAL ACCEPTANCE**, for the scoped frontend research/
operations workspace. Prior Agents/Vault/Analytics/Simulation features are preserved
and interactively regression checked, not redesigned. Terminal contract, backend
economics, AMM, signing, risk/firewall/final authorization, accounting/reconciliation,
ML SHADOW authority and simulation/optimizer calculations remain unchanged.

Still open: macOS local acceptance, real external-provider and live source/oracle
integrity, real Redis integration, signed TESTNET acceptance, extended soak,
known terminal schema-generation failure, other unresolved audits including A2-003/
A2-005, and independently unfinished **Phase 13.2A–E**. Phase 14/15 is not started.
Local viewport checks are not WCAG certification, durable audit storage, complete
venue history, external acceptance or production readiness.

No database, persistent logs, Docker, Actions/.github, authentication/accounts,
wallet/private-key management, new oracle provider, new strategy/agent, public
deployment, automatic candidate deployment or trading mutation was added.

## Complete changed-file list

See the exact inventory below; no generated exports or raw research payloads:

```text
CODEBASE.md
docs/PHASE1333_ACCEPTANCE.md
docs/ROADMAP.md
docs/acceptance/phase1333/logs-fixture-390.png
docs/acceptance/phase1333/logs-live-1440.png
docs/acceptance/phase1333/results.md
docs/acceptance/phase1333/settings-fixture-390.png
docs/acceptance/phase1333/settings-live-1440.png
frontend/src/App.tsx
frontend/src/api/client.ts
frontend/src/components/EventTimeline.tsx
frontend/src/components/SystemHealth.tsx
frontend/src/components/settings/ProviderHealthSummary.tsx
frontend/src/hooks/useTerminalEvents.ts
frontend/src/pages/Logs.tsx
frontend/src/pages/Settings.tsx
frontend/src/phase1333.css
frontend/src/stores/display.ts
frontend/src/utils/terminalEventView.ts
frontend/tests/browser-phase1331.py
frontend/tests/browser-phase1333.py
frontend/tests/logs-settings.test.cjs
frontend/tests/run.cjs
```
