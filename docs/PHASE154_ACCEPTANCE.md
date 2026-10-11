# Phase 15.4 — Market vs Research Comparison & Explainability

**IMPLEMENTED / LOCAL FIXTURE ACCEPTED. Draft PR only — do not merge.**
Phase 15 is not complete. Genuine venue acceptance remains open.

## Verified preflight and unchanged baseline

Repository `btorressz/hyperamm`. Original checkout was clean at Phase 15.1. Fetched
latest `origin/main` before editing and again before delivery; exact main:
**8d3a1e6455fbebbee74dbb1126d480935d18a068**. GitHub independently confirmed PRs
#49/#50/#51/#52 merged. Branch: `phase15/15-4-market-research-explainability`.
The checked-out baseline tree matched `08e3b36fb79e0c80dd25e3733a846af97d2a7701`.

Reviewed docs/AGENTS, CODEBASE, ROADMAP, ARCHITECTURE, SIMULATION, TERMINAL,
REFERENCE_INTEGRITY, HYPERLIQUID_INTEGRATION and Phase 14/14.6/15.1/15.2/15.3
acceptance, plus actual simulation/scenario/profile/accounting/provenance,
observer/socket/store/financial/chart and existing Chromium harness contracts.
Installed existing backend `.[test,ml,redis,yahoo]` in a workspace venv and locked
frontend `npm ci`; production dependencies/lockfile unchanged. Python 3.12.14,
SDK 0.24.0, FastAPI 0.143.0, Pydantic 2.14.0, pytest 8.4.2, Node 24.19.0 and
system Chromium/Playwright were used. Development date: October 10, 2026,
America/Los_Angeles; exact source identities/timestamps retain UTC attribution.

| Unchanged baseline check | Executed result |
| --- | --- |
| Backend pytest | **1554 passed**, 0 failed/skipped, 1 upstream warning; **82.98s** |
| Frontend Node tests | **539 passed**, 0 failed/skipped/cancelled; **25.967566745s** |
| TypeScript | PASS |
| Production build | PASS; **4.07s** |
| pip check / compileall | PASS |

These are newly executed results, not the earlier PR's reported counts. Initial
sandbox-only fetch/npm/pip attempts could not access the configured proxy; permitted
network execution resolved setup without changing network policy/TLS/proxy paths.
Connector reads temporarily recovered the exact baseline files, hash-verified against
GitHub; normal git fetch subsequently succeeded and the starting tree was clean.
No user edits were discarded. Setup/development failures are not acceptance.

## Source-derived research assumptions

Optional `ResearchMarketAssumptions` on SimulationResult preserves old required
fields and original fingerprint semantics. Extraction reads the supplied immutable
dataset's last consumed frame, not the retained trace or independently regenerated
scenario. Capture includes actual BBO/mid/spread/bps, mark/oracle/raw funding,
modeled base OI, top-five per-side prices/sizes/depth, market/profile/scenario/
dataset, frame count/sequence/time, reference source and its own fingerprint.

All thirteen scenarios × BTC/ETH/SOL are covered. Trace caps 0/1/5 do not change
assumptions. Existing SimulationService generates one dataset for each run and
shares one dataset across baseline/custom Research Vault runs; extraction therefore
agrees on both sides without changing fees/funding/PnL, fill/risk/accounting or
optimizer behavior. Existing Research Vault configuration provenance is reused.
Old results have null assumptions and display the required unavailable explanation.

A frame is not a scenario aggregate. Visible simulated size is not an AMM virtual
reserve, executable depth, fill probability or queue-priority estimate. Existing
SOL price rounding can collapse multiple modeled rows onto the same price. Those
actual rows/sizes are preserved; no economic regeneration or deduplication occurs.
Five distinct prices per side are required for numerical native/research depth
comparison, so affected SOL depth deltas remain unavailable.

## Read-only API, equations and safety

`POST /api/v1/research-market-comparison/compare` is computational only. It accepts
exact native `market` plus a compact completed research summary; no trace/strategy
program, executable method, URL, signing credential, arbitrary market, order or
configuration command. The router has no operational runtime dependency. It calls
only existing `LiveMarketStreamService.snapshot(market)`, never SDK construction,
REST refresh, live activation or simulation/optimizer execution. Response: no-store.

Strict frozen/extra-forbid contracts enforce finite bounded Decimal input, strict
simulated booleans and integer counts, bounded levels/text/hash fields, compatible
identities, BBO/spread/depth consistency and recomputed assumption/config provenance.
Original metrics are narrowed and returned unchanged as PAPER context. The shared
research middleware bounds POST bodies at **65536 bytes**, including chunked bodies,
before parsing. Validation errors expose only location/message/type, not supplied
input or exception context; service failures return a sanitized 500. Existing routes
and default DEMO/PAPER/live-disabled settings remain unchanged.

Price delta = observed − hypothetical; price difference bps = delta / hypothetical
× 10000. Spread quote delta = observed − simulated spread. Spread-bps difference
= observed spread bps − simulated spread bps; it is not relative price movement.
Funding raw subtraction is PARTIAL: native hourly rate/event time unknown versus
scenario raw rate per sampled research interval, not equivalent settled payments.
No annualization/time-window multiplication occurs. OI uses actual captured frame
base OI and is descriptive/PARTIAL; absent modeled evidence yields no delta.
Depth is top five distinct prices per side, matching base units; truncated visible
books remain labeled, and insufficient/incompatible levels yield no depth number.
All wire financial fields are Decimal strings; no financial float arithmetic.

L2 and context eligibility are independent and also require current valid native
metadata and an accepted connection boundary. Fresh L2 can compare when context is
stale; stale L2 cannot borrow fresh context. Disconnected/disabled/expired evidence
is unavailable. Retained stale values are explicitly historical. Cross-asset requests
return NOT_COMPARABLE without any numerical deltas. No missing observed value is
filled from the research column.

## Provenance, temporal integrity and completeness

Research frame time, native L2 exchange time, L2 receipt, native context receipt,
UNKNOWN context event time and comparison processing time remain distinct.
Acquisition gaps are explicit. The static paired graphic displays independently
labeled full dates/time zones, with no common timeline, fabricated offsets,
OHLCV/candles, forward filling or replay/performance attribution.

Semantic fingerprint binds contract/market, original research scenario/run/dataset/
strategy/profile/assumptions/configuration/performance, observer/generation and
accepted source identities/timestamps/values/eligibility. Processing/evaluation time,
advancing ages and diagnostic counters are excluded. Repeated identical economic
evidence retains the fingerprint; freshness/identity/material evidence changes do
not silently revive older captures.

The trust label is **STRUCTURALLY_VALIDATED_CLIENT_SUPPLIED_NOT_AUTHENTICATED**.
Client hashes and revalidated internal consistency do not prove actual server
execution. No permanent server run registry or new database is added. Research
DEMO_PROFILE metadata never inherits EXCHANGE_VERIFIED eligibility or trading
authority from observed metadata.

Completeness is deterministic across eleven supported metric rows: all supported
rows available → COMPLETE_FOR_SUPPORTED_METRICS; some → PARTIAL; none with
incompatible evidence → INSUFFICIENT; otherwise UNAVAILABLE. Raw funding/OI can
count as available while retaining PARTIAL convention warnings. Interpretation
always remains CROSS_CONTEXT_DESCRIPTIVE_ONLY. Completeness predicts neither
profitability nor real execution performance. Actual completed PAPER PnL, returns,
drawdown/fills/risk/notionals/markouts/inventory and fees/settled funding stay in a
separate hypothetical performance panel. Missing accounting provenance never
invents a preset or fee/funding assumption.

## React workflow and lifecycle

Simulation validates and retains only accepted completed individual results;
Research Vault baseline/customized sides can be selected individually. Optimizer
summaries are excluded. The independent nonpersistent store retains at most three
detached compact research summaries and one frozen comparison, preserving original
market/scenario/hash/configuration/performance. Original run/Vault objects are not
mutated. Markets adds the read-only comparison view without a second run interface.

The user selects observed BTC/ETH/SOL and a completed result, then explicitly uses
**Compare with observed market**. **Refresh observed comparison** captures only a
new current in-memory observation. No automatic rerun, optimization, apply/deploy,
trade, capital or strategy action is offered. Missing/disabled sources still show
PAPER assumptions/performance and unavailable observed values.

TanStack mutations use AbortController, synchronous request generations and
captured research run/dataset/profile, research epoch, live selection/boundary,
observer and stream generation. Selection, new result, observer/generation/reconnect
or superseding requests retire stale completions. Finished artifacts remain frozen
through later publications; workspace exit and captured-source expiry retire them
to HISTORICAL. A newer fresh tick does not renew their captured freshness. The
monotonic clock never uses an earlier render time to expire a newly accepted capture.

Desktop uses paired evidence, scoped tables and panels; tablet/mobile stack.
Tables scroll locally, hashes/numbers wrap, selectors/buttons/statuses remain
accessible, and the document has no horizontal overflow at the six required sizes.

## Final executed validation

| Check | Actual final result |
| --- | --- |
| Full backend pytest | **1649 passed**, 0 failed/skipped; **85.01s**, 1 upstream warning |
| Focused Phase 15.4 pytest | **95 passed**, 0 failed/skipped; **7.14s**, 1 upstream warning |
| Full frontend Node tests | **602 passed**, 0 failed/skipped/cancelled; **18.818051301s** |
| Focused Phase 15.4 frontend | **63 passed**, 0 failed/skipped/cancelled; **0.132114695s** |
| TypeScript | PASS |
| Production build | PASS; **3.18s** |
| pip check / compileall / diff whitespace | PASS |
| Actual Chromium | **15 workflows**, **6 viewports**, **0 page exceptions**; **28.08s** |

All 1554 original backend and 539 original frontend tests remain present. Added
95 backend and 63 frontend cases. No previous tests/schema/acceptance artifacts
were deleted, skipped, weakened, regenerated or suppressed. The legacy probabilistic
redaction assertion did not fail in these final or baseline runs; it remains an
existing open concern. One Starlette/httpx TestClient deprecation remains. Frontend
retains the existing headless Zustand storage notice, TanStack module-directive
notices and Vite main-chunk advisory (about 599 kB minified). No dependency/lock,
terminal schema, fill/AMM/risk/accounting formula or optimizer-ranking change.

Backend real seeded DEMO/PAPER isolation covers meaningful fills/positions,
resting orders/quotes, strategy running/kill states, configuration/agent/risk,
FinalQuoteAuthorization, execution/accounting/vault/ledger/reservations and service
identities through all assets, repeated/concurrent/invalid/cancelled comparisons,
source expiry and a disabled replacement observer. Authority and economic state
are byte/value/identity equivalent before and after. AST/API checks reject
operational/network authority edges and preserve existing observation GET routes.

## Chromium acceptance and artifacts

`browser-phase154.py` owns local Uvicorn/Vite process groups and real Chromium.
The test-only server retains the genuine DEMO/PAPER operational runtime and real
Phase 14 PAPER runs. Offline catalog fixtures prevent venue metadata access. Native
HTTP/WS fixtures come from existing FakeClients, actual Phase 15 normalizers and
Pydantic contracts; five distinct observed levels per side are reproducibly generated
by `phase154-fixtures.py`. The **production comparison route is exercised unchanged**,
reading the same server-owned normalized fixture snapshot as HTTP/WS.

Executed: no result/disabled capture; actual BTC run; matching explicit price,
spread, raw funding and depth; unchanged artifact through newer publication; fresh
L2/stale context; missing depth; BTC/ETH mismatch with no cross-asset delta;
actual ETH/SOL runs; navigation; observer restart during delayed POST and explicit
refresh; captured freshness expiry despite newer publication; legacy missing
assumptions; authority/research-state invariants; all six viewport/overflow checks.
Exactly three explicit individual PAPER run POSTs and comparison POSTs occurred;
no strategy/order/risk/accounting/optimizer writes. Test control routes are separate
harness requests and are not registered by the production entrypoint.

Viewports: **1920×1080, 1440×900, 1366×768, 1024×768, 768×900, 390×844**.
[Browser report](acceptance/phase154/browser-results.json),
[BTC capture](acceptance/phase154/btc-comparison-1440.png),
[legacy desktop](acceptance/phase154/comparison-1440.png) and
[legacy mobile](acceptance/phase154/comparison-390.png) are retained. Screenshots
carry **DETERMINISTIC FIXTURE ACCEPTANCE — NOT LIVE VENUE DATA**. Assertions,
not screenshots, establish executed browser acceptance.

Development checks found and corrected repeated-price SOL depth eligibility,
legacy exponent financial strings, a monotonic render-time freshness race and
incomplete time-only presentation. Earlier one-level fixtures were insufficient
for a five-level depth assertion and were replaced in the new harness with
actual backend-normalized five-level fixtures; Phase 15.3 artifacts stay intact.
Early unsuccessful setup/harness runs are not counted as passing acceptance.

## Files and reuse

Enhanced: `backend/app/simulation/models.py`, `engine.py`, `app/main.py`,
`app/api/research_vault.py`; frontend `pages/Simulation.tsx`, `pages/Markets.tsx`,
`api/client.ts`, `types/index.ts`, `tests/run.cjs`; CODEBASE and Architecture,
Simulation, Terminal, Roadmap and Reference Integrity docs.

New: backend `research_comparison/{__init__,models,assumptions,comparison,
explainability,provenance}.py`, `api/research_market_comparison.py`, four
`test_phase154_*.py` suites and `phase154_helpers.py`; frontend comparison workspace,
paired price graphic, metric table, confidence and performance components,
`useMarketResearchComparison.ts`, independent store/utility, `phase154.css`, four
Node suites/helpers, fixture generator/JSON, browser server/harness; this report
and three useful screenshots/browser report.

Reused without redesign: simulation service/shared dataset, Research Vault
provenance/presets/config, market_profiles/scenarios/metrics/executor/replay;
Phase 15 live_models/live_stream_models/live_streams/history/context and provider
integrity/mappings; existing native validation and financial constraints; React
Panel/Metrics/Badge/StatusBanner and financial formatting; live selection/socket
ownership/freshness helpers; research epoch/admission, TanStack/Zustand and existing
Node/Chromium tooling. The paired static graphic adds no chart library.

## External gates and Phase 15.5 prerequisites

**Genuine live Hyperliquid/provider acceptance: NOT RUN / BLOCKED by existing
managed destination policy.** Venue hosts are absent from the enforced allowlist;
no VPN/TCP venue grants, restriction bypass, signing credentials or automatic live
activation were used. Fixture acceptance does not establish real exchange delivery,
source-time correctness, rate limits, reconnect/cleanup/soak or redistribution rights.
Mac acceptance, permitted external collectors, real Redis, signed TESTNET, long
soak and existing unrelated audit gates remain open. No MAINNET/custody/wallet,
new oracle, Docker, database, Actions or `.github/` files are added.

Phase 15.5 retains substantive security/code review, final full regression/lifecycle
acceptance and permitted genuine external verification. Strong execution attestation
would require a future scoped run-registry design; it is not claimed here. No live
performance attribution, time-matched historical replay, optimization, execution
or deployment is delivered. **Leave the single PR as Draft and unmerged.**
