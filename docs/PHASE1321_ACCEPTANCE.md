# Phase 13.2.1 — execution lifecycle UX & workspace acceptance

Acceptance date: October 9, 2026 (America/Los_Angeles). Dedicated draft against
`main`; do not merge automatically. Fetched base before any edit:
`d11acbd24d3944d4570bd855655c3aa0dbf4625a` (merged PR #42, on merged PR #41).

## Scope and implementation

13.2F is implemented. Execution has client-side status, side and mode-evidence
filters, stable ascending/descending timestamp/price/size/status sorting, and
native expandable details. Details show client/venue IDs, reported and normalized
status, exact filled quantity, source, full creation/update timestamps, session,
all matching latest-cycle actions, venue reconciliation timestamp and error.
Missing values remain unavailable; missing sort values stay last both ways.
Decimal display and comparison preserve wire precision, including scientific
notation, without converting financial strings to floating point.

OPEN and PARTIALLY_FILLED are retained status evidence, UNKNOWN requires
verification, and FILLED/CANCELLED/REPLACED/REJECTED remain historical. Unknown
status strings are treated as UNKNOWN. Historical/disconnected/expired snapshots
are labeled historical on Execution and the Dashboard execution summary; Strategy
quote evidence also receives the historical flag. No status claims confirmed
resting venue liquidity. Details stay associated with order identity as rows
update; session changes reset execution controls.

PR #42's proposal/authorized separation and exact side/level/price/size matching
are preserved. An older exact OPEN match cannot override a newer slot record;
duplicate active/uncertain slot histories and missing timestamps stay uncertain.
Latest partial fills can match original order quantity after replacement history;
closed exact records stay historical even when newer prices differ.

Execution's read-only timeline polls the existing authoritative EXECUTION event
endpoint, requests at most 200 events, checks response session identity and pauses
while the snapshot is historical. It shows backend order transitions and
reconciliation events; it does not construct a synthetic fill ledger. Loading,
empty and request-error states are explicit. Existing backend active/recent order
and fill bounds are unchanged. Narrow tables scroll within the panel and preserve
readable column widths; order tables can receive keyboard focus.

PAPER fills are explicitly simulated; TESTNET fill history remains unavailable.
The order payload lacks an execution-mode field. The mode-evidence filter uses
explicit PAPER fill source or TESTNET venue ID, otherwise UNKNOWN; it never
borrows current strategy configuration to classify old/uncertain records. A venue
ID alone is labeled retained evidence, not resting confirmation. No backend
application, reconciliation, signing, permission, accounting, strategy or schema
implementation changed. No Docker, PostgreSQL, GitHub Actions or 13.3 work added.

## Regression execution

Before editing, `npm ci` with the workspace cache, `npm test`, `npm run typecheck`
and `npm run build` succeeded: **175 frontend cases**, 0 failed/skipped. This
independently executes all **164 Phase 13.1 cases plus PR #42's 11 definitions**.
The initial default-cache installation failed because `/home/agent/.npm` was
unwritable; using `/workspace/.hyperamm/npm-cache` resolved installation.

Final frontend: **213 passed**, 0 failed/skipped (175 preserved + 38 added).
Typecheck and production build passed. New tests exercise all seven statuses,
unrecognized/missing/empty evidence, historical views, each filter, combined
filters, stable sorts in both directions, missing-value placement, decimal
precision, details/action identity, competing slot histories, partial fills,
scientific wire values and timeline loading/error/empty/provenance/session bounds.
The existing runner executes individual definitions on Node 24.19.0.
[Baseline frontend results](acceptance/phase1321/baseline-frontend-results.txt),
[frontend results](acceptance/phase1321/frontend-results.txt),
[typecheck](acceptance/phase1321/typecheck-results.txt), and
[build](acceptance/phase1321/build-results.txt) are retained. An added SSR
error-cache test initially retried on mount; disabling retries for that fixture
corrected its setup. The real browser timeline error check passed independently.

Complete backend in the existing **Python 3.12.14** environment with
`.[test,ml,redis,yahoo]`: **1124 passed, 1 failed, 0 skipped**, one upstream
Starlette/httpx deprecation warning. Failure:
`tests/test_audit_terminal_contract.py::test_generated_terminal_schema_is_current`.
Generated inline Decimal string patterns differ from the committed schema. The
failure was present before frontend edits (Pydantic 2.13.5), and repeated with
Pydantic 2.12.5, including a fresh complete suite. No schema regeneration or test
weakening is included. The optional dependencies initially lacked fakeredis,
which caused three collection errors; installing declared extras resolved them.
`pip check` passed. Backend results are [retained here](acceptance/phase1321/backend-results.txt).
This is a remaining integration gate, not a clean backend acceptance claim.

Commands executed:

```bash
cd frontend
npm ci --cache /workspace/.hyperamm/npm-cache
npm test
npm run typecheck
npm run build
cd ../backend
/workspace/.hyperamm/venv/bin/python -m pip install -e '.[test,ml,redis,yahoo]'
/workspace/.hyperamm/venv/bin/python -m pytest -q
```

## Real local browser acceptance

Actual loopback Uvicorn + Vite + headless Chromium + DEMO/PAPER. The main run
passed **66 assertions**, including all six requested pages at **1440, 768 and
390px**: navigation/rendering, no document overflow, reachable kill, and live
Dashboard/Markets canvases. Existing config unsaved/Reset, real invalid-save 422
preserving inputs, valid Save and restoring configuration passed. Strategy Start
produced real lifecycle records and all three quote stages. Execution side/mode
filters, empty status-filter result, exact ascending price sort, expanded details,
authoritative timeline and simulated event labeling passed.

Kill remained sticky; dismissed Resume preserved kill; confirmed Resume left
strategy stopped. Actual backend termination rendered retained historical
execution and paused event polling. A new tab displayed initial loading. Restart
installed a new process/session, cleared old orders, and preserved bookmark
reload. Browser-side probes through the real store acceptance method rejected a
duplicate sequence, ancient/future envelopes, and a retired-process copy even
with a fresh timestamp. These adverse-frame probes are explicitly injected copies,
not new authoritative venue evidence. Zero page exceptions in the main run.
Expected responses: one config 422 and two Vite proxy health 500s while the backend
was deliberately stopped. [Full assertions](acceptance/phase1321/browser-results.json).

Four supplemental assertions verified narrower-table scrolling reaches expanded
order details, no overflow with real records, desktop expanded capture and a
fault-injected read-only timeline 503 error presentation.
[Supplement](acceptance/phase1321/browser-supplement.json).

The first browser script stopped at an implicit select-label lookup. Explicit
accessible names were added, then the complete main run passed. Another run under
concurrent regression load timed out waiting for a fresh envelope; the UI correctly
showed historical/stale evidence. The isolated complete run passed; this does not
constitute extended load/soak acceptance.

An exploratory PAPER-fill configuration initially violated the existing
liquidity/base-size constraint and correctly received 422. Valid 40-second and then 12-second tighter-quote
probes produced no natural fill; zero-fill rendering stayed explicit. Configuration
was restored and the strategy stopped. A real natural PAPER fill sample remains
browser acceptance pending; no forced/synthetic fill was presented as real.
[Probe result](acceptance/phase1321/browser-fill-probe.json). Fill-state rendering and all seven
statuses have regression coverage; live venue fills remain pending.

Screenshots: [Dashboard desktop](acceptance/phase1321/dashboard-1440.png),
[Markets narrow](acceptance/phase1321/markets-390.png),
[Execution desktop](acceptance/phase1321/execution-details-1440.png), and
[Execution narrow](acceptance/phase1321/execution-details-390.png).

## Outstanding acceptance

13.2A–E remain pending: Dashboard command-center redesign, Markets workspace,
broader Strategy lineage workflow, AMM Settings workflow/backend-supported preview,
and broader Risk workflow. Existing-page smoke/control checks above are verified;
they do not accept unimplemented 13.2A–E features. 13.2G local UX checks are scoped
acceptance, with the backend schema gate still failing. Full Phase 13.2 is not
complete.

Preserve pending macOS, external-provider acceptance, real Redis, signed TESTNET,
extended soak and previously recorded A2-003/A2-005 gates. No signed TESTNET orders
were sent; no venue fill/partial-fill acceptance is claimed. Every status has
frontend regression coverage, but non-PAPER venue states remain browser acceptance
pending. Phase 13.3 and later features remain out of scope.
