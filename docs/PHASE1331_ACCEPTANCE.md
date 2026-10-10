# Phase 13.3.1 — Agents & Research Vault acceptance

Local Linux acceptance on October 9, 2026 (America/Los_Angeles). Scope is
**13.3A + 13.3B only**, one unmerged draft PR. Phase 13.3 is not fully complete.

## Verified preflight

Fetched current `origin/main` before editing and rechecked it before PR preparation:
`616ab5b7dc1b48c2573cad5c4f41dffadc4cf1c4`. PR #43 is merged at
`50f6ab9b42cbd72f905b2ffc319f0ea90b7252c4`; PR #44 is merged at the base SHA.
Working branch: `phase13/13-3-1-agents-vault-ux`; main was not modified.

Inspected CODEBASE.md, ROADMAP, ARCHITECTURE, AGENTS, ACCOUNTING, existing Agents/
Vault components, API routes, agent models/evidence/telemetry, terminal contracts,
store/freshness, quote lineage, shared chart/history and UI/test infrastructure.
The user-mentioned recording, dashboard image and conceptual mockup were not
available among uploaded assets. Existing actual frontend/theme and real local
screenshots were used; inaccessible assets were not reviewed.

Sandbox network/subprocess restrictions initially prevented Git fetch and esbuild
installation. The supported approved execution completed the fetch and cached
`npm ci --offline --cache /workspace/.hyperamm/npm-cache`. No dependency manifests
or lockfiles changed. A duplicate sandbox static-test attempt stalled; automatic
review rejected stopping a PID without sufficient identity proof. It was left
untouched; completed validation below ran independently with subprocess access.

## Implementation

Agents keeps the existing architecture and adds a supervisor overview, available/
missing/degraded counts, all six tailored cards and native keyboard-accessible
expandable details. Regime observations are separate from buy/sell instructions;
missing/unsupported markouts are not zero toxicity, side scores require reported
sample support, and horizon counts are not independent fills. PAPER execution
measurements remain simulated and missing venue latencies stay unavailable.
Single OI evidence cannot establish a trend. ML SHADOW is visibly observational,
with no quote/execution authority; inference support is not validated accuracy.
Backend reasons, reported states, evidence versions, matching input provenance,
source timestamps and optional model identities remain inspectable.

Recommendation, RiskFirewall evaluation, FinalQuoteAuthorization and execution
observations are distinct. Declared agent version/fingerprint bindings can be
inspected; exact per-agent downstream causal attribution is explicitly unavailable.
Agent event selection and manual refresh consume existing read-only APIs; current
responses are bounded to 100 and backend retention to 250. Disconnected display
uses at most 20 retained terminal events, labeled historical. No extra event service
or continual polling was added. The compact Dashboard AgentPanel remains its
default; the Agents route selects the detailed workspace.

Vault groups backend capital and PnL without calculating economics in React.
Quote/base units are explicit; exact Decimal strings and tiny values are preserved.
Capital, PAPER assumptions, partial TESTNET evidence, high-water/position details,
reported consistency status and provenance are readable. Ledger event/side/source/
simulation filters preserve newest-first source sequence order. No optional
financial sorter was added. Native row details preserve every economic identity,
delta, running balance, cumulative value and full fingerprint. Loading/API failure,
known unavailable economics, empty PAPER and filtered-empty states remain distinct.
The TESTNET empty state does not imply full accounting. No repair/money movement
or strategy controls are added.

Reused: Badge, TerminalPrimitives, existing format/exactDecimal utilities, API
client, accepted terminal store and unchanged Analytics SessionCharts/history.
New components: AgentDetails, AgentAuthoritySummary, AgentEvents,
AccountingConsistency and AccountingProvenance. New helpers: useResearchSession,
researchEvidence and scoped phase1331.css. Existing Agents, AgentPanel, Vault,
VaultSummary, PnlBreakdown and AccountingLedger are enhanced. The existing backend
static read-only UI test follows the relocated consistency component and the new
session-keyed Vault mount; route/custody assertions remain intact.

## Session and provenance safeguards

Both page mounts and queries bind `process_id` and `session_id`. A client connection
epoch increments synchronously on accepted store identity/connection transitions,
including disconnected/reconnected transitions batched by React. Requests consume
TanStack Query AbortSignal and check current session/epoch/fresh envelope again
when responses arrive. No previous-session placeholder is used; obsolete queries
are removed with `gcTime: 0`. Ledger queries also bind mode, market, version and
fingerprint. Responses must match request-time and latest accepted terminal values;
rendering checks provenance again. A fingerprint change starts a new matching
request; unavailable/stale accounting hides current ledger rows. Ledger requests
are triggered by evidence changes, not extra periodic polling.

Wire limitation: neither REST events nor ledger declares a terminal session ID.
Client checks and exact ledger matching reduce races but cannot cryptographically
bind the HTTP observation to a backend session. Equal genesis fingerprints are
not independent session proof. Fingerprints do not provide durable multi-session
recovery. Fresh terminal transport does not renew source/accounting evidence;
reported source freshness, timestamps, accounting health and historical page
labels remain distinct. No backend schema or authority change is claimed.

## Exact commands and results

Frontend (Node 24.19.0; installed package lock):

```bash
cd frontend
npm ci --offline --cache /workspace/.hyperamm/npm-cache
npm test
npm run typecheck
npm run build
```

Baseline before edits: **213 passed, 0 failed/skipped**, typecheck/build exit 0.
A diagnostic run of unchanged baseline files with per-file Node isolation also
passed 213; it is not counted as extra cases. Final: **262 passed, 0 failed/skipped**
(49 new cases), typecheck/build exit 0. Coverage includes six agent presentations,
missing/warmup/insufficient/degraded/error evidence, non-authority, side support,
bounded event filtering, exact decimals, all ledger filters and source order,
read-only details/consistency/provenance, and deferred-response mismatches across
session/process/version/hash/disconnect/stale/future transitions. All existing
terminal freshness/replay/watchdog/navigation/quote/execution/effective-liquidity
regressions still run. Existing non-failing TanStack `use client` build warnings
and server-rendered Zustand storage notice remain.

Backend (Python 3.12.14; existing virtualenv):

```bash
cd backend
/workspace/.hyperamm/venv/bin/python -m pip install -e '.[test,ml,redis,yahoo]'
/workspace/.hyperamm/venv/bin/python -m pip check
/workspace/.hyperamm/venv/bin/python -m compileall -q app
/workspace/.hyperamm/venv/bin/python -m pytest -q
```

Dependency check and compileall pass. Baseline **1124 passed, 1 failed, 0 skipped**,
one upstream Starlette/httpx warning (59.31s). Final **1124 passed, 1 failed,
0 skipped**, one upstream warning (85.70s). The unchanged failure is
`test_generated_terminal_schema_is_current`: generated Pydantic Decimal patterns
differ from committed schema. No schema regeneration or test weakening occurred.
An intermediate final run had **1123 passed, 2 failed** because the old static UI
custody token scan also rejected the explanatory phrase “not deposited TVL.”
That phrase was changed to mathematical liquidity versus financial balances;
the unchanged custody guard passes in the final full suite. This frontend change
does not fix the generated-schema integration gate.

Raw logs: [baseline frontend](acceptance/phase1331/baseline-frontend-results.txt),
[frontend](acceptance/phase1331/frontend-results.txt),
[typecheck](acceptance/phase1331/typecheck-results.txt),
[build](acceptance/phase1331/build-results.txt),
[backend baseline](acceptance/phase1331/backend-baseline.txt),
[final backend](acceptance/phase1331/backend-results.txt).

## Actual browser acceptance

Local Uvicorn + Vite + system Chromium, Playwright, America/Los_Angeles timezone:

```bash
cd backend
MARKET_DATA_MODE=DEMO EXECUTION_MODE=PAPER \
ENABLE_HYPERLIQUID_TESTNET_ORDERS=false \
/workspace/.hyperamm/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Separate process:
cd frontend
npm run dev -- --host 127.0.0.1
# From repository root, dedicated backend PID only:
/workspace/.hyperamm/venv/bin/python frontend/tests/browser-phase1331.py \
  --output /workspace/work/phase1331 --backend-pid <dedicated-uvicorn-pid>
# Fixture-only completion can reuse the persisted live acceptance report:
/workspace/.hyperamm/venv/bin/python frontend/tests/browser-phase1331.py \
  --output /workspace/work/phase1331 --fixtures-only
```

**72 live route/viewport checks + 19 recorded workflows, zero page exceptions.**
All twelve routes were checked at **1920, 1440, 1366, 1024, 768 and 390px** with
no document overflow. Agents keyboard expand/collapse, event selection, shadow
non-authority, Vault capital/PnL, existing chart canvases, empty PAPER ledger and
full provenance access pass. Actual dedicated Uvicorn stop shows historical
Agents/Vault and hides current ledger; actual restart presents a new identity
and new matching ledger evidence.

Browser-only deterministic terminal/HTTP fixtures cover populated six-agent
states/reasons, event filtering/empty/loading/error, stale in-flight events after
session change, exact tiny decimal ledger rows, keyboard details/full fingerprints,
four ledger filters/combined empty states, populated ledger detail/scroll access
at all six widths, API errors, ledger/version mismatch, stale ledger request across
process/session replacement with identical material ledger provenance, DIVERGED
consistency and TESTNET partial unavailable equity/PnL/complete fill accounting.
Fixtures never wrote ledger entries or generated economic transactions on the
backend. Strategy remained stopped; no signed TESTNET or other venue orders sent.

Initial harness attempts found duplicate locator matches, an API scenario that
reused a cached same-document page, and a Playwright routed-WebSocket close
callback payload incompatibility. Locators, explicit fixture reloads and task
ownership were corrected; final fixture run passes and reuses the completed live
report. These were harness issues, not suppressed product test failures. Reported
console diagnostics are favicon 404 and expected development WebSocket close
before handshake during navigation/restart; zero page exceptions does not mean
zero console diagnostics. The stopped default DEMO session naturally has no agent
cycle outputs or economic rows, so populated states use isolated browser fixtures.

[Machine-readable browser report](acceptance/phase1331/browser-results.json).
Screenshots: [live Agents 1440](acceptance/phase1331/agents-1440.png),
[live Vault 1440](acceptance/phase1331/vault-1440.png),
[browser-fixture ledger 1440](acceptance/phase1331/vault-ledger-fixture-1440.png),
[browser-fixture ledger 390](acceptance/phase1331/vault-ledger-fixture-390.png).

## Remaining gates

No Phase 13.3C–G, Phase 14/15 or Phase 13.2A–E completion. Twelve-route viewport
regression is not full future feature acceptance or WCAG certification. macOS,
external providers, real Redis, signed TESTNET, long-soak, unrelated audit and
schema-generation gates remain open. Research ledger/events remain in-memory and
bounded; TESTNET economics are partial. No persistent notebooks/projects,
collaboration, custody, database, Docker, Actions, signing changes, new agents,
ML promotion, accounting formula changes or public deployment. Draft PR only;
**do not merge automatically**.
