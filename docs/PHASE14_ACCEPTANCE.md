# Phase 14 — Customizable Research Vault acceptance

Implemented Phase 14.1–14.5 with Linux local acceptance. **Draft PR; do not merge.**
Research remains non-custodial, local-first, deterministic PAPER/DEMO. No active
strategy/accounting/risk/order authority is configured by this feature.

## Verified preflight

- Repository `btorressz/hyperamm`, branch `phase14/customizable-research-vault`.
- Fresh `git fetch origin main`; base **bf547ad889d0e549b8d67beb966323614f2a5c27**.
  GitHub connector independently reported that latest merge and merged PRs.
- Original working tree clean. Merge history confirms #43 `50f6ab9`, #44
  `616ab5b`, #45 `8085c58`, #46 `fc8c630`, #47 `bf547ad`.
- Reviewed CODEBASE, ROADMAP, ARCHITECTURE, SIMULATION, ACCOUNTING and all three
  PHASE1331/1332/1333 acceptance reports; inspected simulation API/service/engine/
  executor/optimizer, AccountingConfig/authority and existing Vault/Simulation.
- Python 3.12.14 in isolated `/workspace/work/venv`; installed `.[test,ml,redis,yahoo]`.
  FastAPI 0.143.0, Pydantic 2.14.0, pytest 8.4.2. Node 24.19.0; locked npm ci.
- Sandbox-only network initially could not reach the configured proxy; authorized
  network execution completed fetch/install/test loopback needs. An initial
  overlapping unsuccessful npm install interrupted TypeScript library files;
  reinstall completed before baseline typecheck/build and all final validation.
- Unchanged base was independently tested from a clean git-archive checkout.
  Baseline backend **1125 passed, 0 failed/skipped, 1 warning, 57.72s**. Frontend
  **376 passed, 0 failed/skipped, 26.52s**, typecheck/build passed after reinstall.
- The historical `test_generated_terminal_schema_is_current` Pydantic Decimal
  mismatch did **not reproduce** on this unchanged base with installed versions.
  Neither the schema nor its test was changed, weakened, skipped or suppressed.
  Historical acceptance reports remain intact; this does not erase their results.

## Milestones and implementation

| Milestone | Delivered and locally verified |
| --- | --- |
| 14.1 Contracts | Narrow frozen/extra-forbid Decimal config, reused accounting field metadata, strict flags/integer intervals, bounded financial values, one initial-capital source, deterministic schema-bound fingerprint |
| 14.2 Presets/preview | Three Python-owned v1 presets, read-only catalog, computational preview, exact configuration comparison, warnings/limitations/provenance; no PnL forecast |
| 14.3 Vault studio | Existing capital/PnL/consistency/charts/ledger/provenance retained; separate preset/editor/preview components; exact Decimal strings and percentage movement, local draft/reset/selection, outdated validation and response retirement |
| 14.4 Integration | Optional backward-compatible simulation/optimization research proposal; existing PAPER engine/accounting/optimizer; one-worker controlled baseline/custom comparison; actual metrics and reused trace/candidate components |
| 14.5 Acceptance | Injection/malformed/nonfinite/payload tests, runtime invariant checks, worker cancellation/admission, existing Redis-wrapper compatibility, frontend regressions, actual Chromium workflows/restart and six-viewport all-route smoke |

Contract, exact preset values, API examples, comparison method and client lifecycle
are documented in [SIMULATION](SIMULATION.md#phase-14--customizable-research-vault)
and [ACCOUNTING](ACCOUNTING.md#phase-14-research-integration).

### Backend APIs and provenance

`GET /api/v1/research-vault/presets`, `POST /api/v1/research-vault/preview`,
`POST /api/v1/research-vault/compare`. The existing run/optimize APIs accept optional
`research: {config, selected_preset_id}`. Every run validates again; submitted
preview fingerprints never grant authority. Research requests may supply only
simulation frame/trace controls alongside research; ambiguous accounting/capital/
fill-model settings reject. Legacy requests retain their defaults.

Only initial equity, hypothetical fee flags/rates, funding flag/interval and
utilization fraction are editable. Accounting administrative defaults are server
owned; starting equity is mapped explicitly into both isolated models, and the
existing engine override is preserved. Financial metadata reuses AccountingConfig.
NaN/Infinity, negative/out-of-bounds values, unknown/nested/protected settings,
unsupported intervals and preset IDs reject. POST bodies are limited to 64 KiB,
including chunked bodies. Errors expose locations/types/messages without input or
exception context, including nonstandard nonfinite JSON literals.

Presets are Conservative Capital (50000, 35%, fees 1/3 bps), Balanced Research
(100000, 75%, fees 1/3), High-Cost Stress (100000, 75%, fees 10/25, funding every
60s). Other presets disable funding and report 3600s. All version 1. No preset
implies real safety or profit. Schema is `phase14-v1`; equivalent Decimal encodings
normalize without rounding before existing stable-fingerprint serialization.

Preview compares to the selected preset, or explicitly identified Balanced
baseline if no preset is selected. It derives only initial equity × utilization;
this is a hypothetical ceiling, never venue margin or allocated capital. Funding
uses scenario rates and existing sampled position/mark semantics; enabled funding
may yield no payments in a short dataset.

Comparison captures strategy, agent and risk inputs synchronously once, forces
PAPER/DEMO on copies, generates one dataset and runs two sequential fresh engine
states through the existing one-worker operation. Bounds: 2–1000 frames per run,
0–500 trace points; frontend trace cap 250. The optional existing Redis admission
wrapper permits this operation, with no new queue, worker or research persistence.
Cancellation cannot release admission before actual computation finishes.

Both SimulationResults retain engine/run/dataset/strategy provenance, with
configuration fingerprints and preset/schema versions added. Custom-minus-baseline
PnL/equity/drawdown/fill/inventory-risk/halt deltas come from actual metrics;
fees/funding and ending capital utilization use actual VaultSnapshots. Missing
Vault evidence yields null. Risk-state counts are reported separately; starting
capital changes carry interpretation limitations. `max_inventory_utilization`
remains the inventory-risk metric, distinct from ending capital utilization.

### Frontend workflow and reuse

New ResearchConfiguration/ResearchPresets/ResearchPreview components append a
clearly separated studio to Vault; nothing replaces authoritative accounting.
A dedicated in-memory Zustand store holds preset, draft/version, last validated
config/fingerprint, preview and explicit research selection. Decimal strings stay
strings; percentage movement is text-based, once. Funding intervals remain whole
integer seconds. No preference persistence, terminal-state mutation or strategy
write is added.

Preview request, draft and synchronous connection generations reject slow edits,
preset switches, obsolete navigation responses, double clicks and batched
reconnects. A restart invalidates validation while preserving the draft. Last
preview remains visibly outdated; new validation retires old approval while it is
pending. Simulation captures detached selected settings and connection generation
at submission; responses with obsolete connection/config identity reject. Results
retain captured inputs when controls change. Browser abort/navigation never claims
server work stopped.

SimulationPanel, SimulationTrace and CandidateComparison remain the metrics,
trace and optimizer views. New ResearchComparison renders actual paired results,
financial deltas, risk counts, provenance and nullable economics. Existing
useResearchSession, terminal store, Badge, Panel/StatusBanner, TanStack Query,
exactDecimal/accountingValue and institutional styles are reused. VaultSummary,
PnlBreakdown, AccountingLedger, AccountingConsistency/Provenance and SessionCharts
stay intact. Optimization presets retain their original independent grids and
ranking; no deploy button or execution permission is added.

## Isolation evidence

Focused fixture tests use a real unstarted runtime to freeze background evidence
for exact before/after equality. Preset/preview, legacy/custom run, optimizer and
comparison preserve StrategyConfig, AgentConfig, RiskFirewallConfig, strategy
running state, kill latch, FinalQuoteAuthorization, OrderManager identity/state,
quotes/open orders/fills, AccountingService identity/config/snapshot (including
reservations), ledger entries/fingerprint and TESTNET eligibility. TESTNET/LIVE
source strategy configuration is copied and forced to PAPER/DEMO without changing
its originals. Inadequate customized capital yields actual HALT and no orders.

Real browser observations before restart independently compare strategy config,
stopped running state, manual kill, orders, ledger version/fingerprint and TESTNET
eligibility. These remain unchanged. Restart changes process/session genesis by
its existing semantics; the acceptance does not mislabel that as a research ledger
mutation. Exactly 14 UI POSTs in the recorded workflow target preview, comparison,
run or optimization; no trading/configuration mutations. There are no private keys,
venue signed orders, wallet features, accounting-formula changes, risk/final-
authorization edits, ML promotion, provider additions or custody paths.

## Executed validation

```bash
cd frontend
npm ci
npm test
npm run typecheck
npm run build

cd backend
python -m pip install -e '.[test,ml,redis,yahoo]'
python -m pip check
python -m compileall -q app
python -m pytest -q
```

Actual Python commands used the isolated Python 3.12 venv above. See concise
[results](acceptance/phase14/results.md) for final counts/durations. Frontend final:
**410 passed, 0 failed/skipped/cancelled, 17.05s** (376 existing + 34 new).
TypeScript and production build pass. Build retains existing non-failing TanStack
`use client` notices and main chunk advisory (~527 kB, ~139 kB gzip).
Backend final: **1185 passed, 0 failed/skipped** (1125 existing + 60 new), one
upstream Starlette `httpx` TestClient deprecation warning. Pip check/compileall and
diff checks pass. There were no test/schema changes to suppress known failures.

Focused research/API/accounting run: **85 passed**, 0 failures/skips, one warning,
8.75s, before the additional Redis-wrapper comparison test. Full final includes
that test and all existing fee/funding idempotency, ledger/high-water/reservation,
execution/accounting consistency and authorization regressions.

## Real browser acceptance

Dedicated local Uvicorn `127.0.0.1:8000` with MARKET_DATA_MODE=DEMO,
EXECUTION_MODE=PAPER, ENABLE_HYPERLIQUID_TESTNET_ORDERS=false, and local Vite
`127.0.0.1:5173`; real `/usr/bin/chromium` via Playwright, Los Angeles timezone.

```bash
python frontend/tests/browser-phase14.py --backend-pid <dedicated-uvicorn-pid> --python <venv-python>
```

Recorded **72 route/viewport checks + 13 workflows**, **0 page exceptions**:
all twelve routes at 1920×1080, 1440×900, 1366×768, 1024×768, 768×900, 390×844;
no document overflow. Detailed Vault/Simulation acceptance covers preset switching,
exact capital/fees/funding/utilization, valid preview/fingerprint and stale inputs,
negative/malformed/out-of-bound values and forbidden fields, actual FLASH_MOVE
run and trace, actual same-dataset comparison, Inventory grid under selected
research accounting, Vault→Simulation→Vault continuity, delayed/malformed preview
fixtures and real backend stop/restart/revalidation/new run. Fixture responses are
explicitly browser-only; all run/comparison/optimization results use actual backend.

A low-capital browser draft correctly produced HALT/no fills in a development
probe; the final fill-inspection workflow explicitly uses sufficient hypothetical
capital. Initial harness fixes included the funding selector accessible label,
canonical preview trailing zeros, Vite HMR duplicate module identity during dynamic
inspection (fresh Vite process), and Playwright argument syntax. These development
attempts are not counted as successful acceptance. Expected 422, restart connection
errors and development proxy diagnostics are not claimed absent.

A separate final capture saves a concise real 30-frame comparison summary rather
than full traces. Both runs use the same dataset and eight fills; custom fees are
2.017083872 quote and funding -0.001541282267475 quote. These are observed PAPER
values, not profitability forecasts.

Evidence:

- [Browser check/workflow report](acceptance/phase14/browser-results.json)
- [Small actual comparison summary](acceptance/phase14/comparison-summary.json)
- [Actual desktop Vault studio](acceptance/phase14/vault-live-1440.png)
- [Actual desktop baseline/custom comparison](acceptance/phase14/simulation-live-1440.png)
- [Actual mobile Vault studio](acceptance/phase14/vault-live-390.png)

Three useful Chromium screenshots only; previous acceptance evidence preserved.
No generated AI screenshots, archives, browser caches, credentials or large raw
simulation results are committed. Dedicated acceptance backends were shut down.

## Remaining limitations and gates

Local acceptance covers this research feature; it does not certify profitability,
production margin, venue fees/funding, live fills, durable storage or blockchain
proofs. Deterministic crossing fills retain existing queue/latency/hidden-liquidity/
stochastic-fill limitations. Funding rates are sampled per research interval.
Metrics use existing accounting arithmetic; no formulas or default runtime
semantics were revised. Existing Redis support remains optional and is fixture-
tested here, not real external Redis acceptance. REST preview has no authenticated
terminal process identity; client generations protect attribution, not cryptographic
provenance. No new authentication/account system is introduced.

macOS, real external providers/source integrity, real Redis, signed TESTNET,
long soak, unrelated A2-003/A2-005 and incomplete Phase 13.2A–E gates remain open.
The historical schema mismatch should still be assessed in environments where it
reproduces. Phase 15 is untouched. **Create one detailed draft PR and leave it
unmerged.**
