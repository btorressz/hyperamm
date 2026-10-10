# Phase 14.6 — Validated BTC/ETH/SOL perpetual research selection

Implemented and locally accepted on Linux, October 10, 2026. Delivery is one
draft PR; **do not merge**. Live exchange metadata acceptance remains blocked
by the cloud HTTP allowlist and is explicitly not claimed. All browser research
uses honestly labeled DEMO profiles and actual isolated PAPER computation.

## Preflight and scope

- Repository: `btorressz/hyperamm`; fetched current `origin/main` and independently
  confirmed GitHub PR #48 merged. Exact base:
  **762803ae996137c4f6ec45ca724b6b57f113e361**.
- Original checkout clean; requested branch
  `phase14/14-6-perp-market-selection` created from fetched main.
- Read CODEBASE, ROADMAP, ARCHITECTURE, SIMULATION, ACCOUNTING,
  PHASE14_ACCEPTANCE, and docs/AGENTS. Inspected SDK integration, scenarios,
  Research Vault proposals/presets, engine/service/executor/optimizer, risk/final
  validation and Vault/Simulation request lifecycle.
- Initial proxy connection failed under sandbox-only networking; authorized
  network execution resolved fetch and dependency installation. No network policy
  bypass or credential inspection was used. npm cache lives under workspace work.
- Python 3.12.14, SDK 0.24.0 (dependency range unchanged), FastAPI 0.143.0,
  Pydantic 2.14.0, pytest 8.4.2; Node 24.19.0. Installed existing
  `.[test,ml,redis,yahoo]` and locked `npm ci` before editing.
- Independently executed unchanged-base backend: **1185 passed**, 0 failed or
  skipped, 1 upstream warning, 43.13s. Frontend: **410 passed**, 0 failed/skipped/
  cancelled, 15.07s; TypeScript and production build passed. Historical baseline
  reports were not substituted for this execution.

Scope is one selected native perpetual per isolated PAPER request, exactly
BTC/ETH/SOL. No simultaneous engines, batch/portfolio trading, HIP-3, arbitrary
symbols, spot, new signing authority, wallet/accounts, provider replacement,
AMM formula rewrite, Docker, database, GitHub Actions or `.github/` additions.

## Implementation and contracts

The technical contract is documented in
[SIMULATION](SIMULATION.md#phase-146--validated-single-native-perpetual-research-selection)
and the source map in [CODEBASE](../CODEBASE.md).

| Area | Delivered |
| --- | --- |
| Catalog | Frozen strict metadata/profile models; exactly BTC/ETH/SOL; native universe-derived indices; listing/source/time/age/eligibility; versioned economic fingerprints |
| Official SDK | `Info.meta(dex="")`, `skip_ws=True`, timeout 5s; supplied empty supported initialization maps avoid implicit spot/HIP-3 metadata calls; owned HTTP-session cleanup |
| Lifecycle | Lifespan-owned single synchronous worker; shared concurrent refresh; 300s immutable snapshot cache; cancellation retains actual task; finite SDK timeout; no collector/refresh loop |
| Metadata validation | Missing/duplicate/malformed identities, invalid/missing precision, boolean/string precisions, malformed delisting, spot/HIP-3/native incompatibility reject |
| Eligibility | Successful SDK response alone supplies EXCHANGE_VERIFIED; valid delisted/missing market remains UNAVAILABLE; outage can use labeled pinned DEMO only in server DEMO/PAPER |
| Price and size | Decimal floor quantities; per-price five-significant-figure and `6 - szDecimals` restrictions with integer exception; outward price rounding cannot increase quote size or notional |
| Calibration | Version phase146-v1; hypothetical BTC 60000 / ETH 3000 / SOL 150 anchors; base reserves and quote-sizing adjusted from source pool reference; risk/base inventory limits unchanged |
| Scenarios | Opt-in proportional legacy shape/spread/depth calibration, all 13 scenarios; rounded book/BBO/mark/oracle, matching market/time/sequence and dataset identity; legacy path preserved |
| APIs | GET research-markets; optional strict research_market on existing run/optimize/compare; extra fields rejected; server profile resolved before worker admission |
| Research | Existing service/engine/optimizer/one-slot executor and PAPER accounting; one market per grid; comparison shares one profile/strategy/dataset |
| Provenance | Returned market/profile version/fingerprint/source/status plus existing dataset/strategy/run/engine evidence; observation age excluded from deterministic identity |
| React | Shared ETH-default in-memory preference/catalog/profile/selection generation; selector/details in existing Vault studio and Simulation; loading/unavailable/retry/DEMO/verified states |
| Async evidence | Captured detached profile plus selection/connection generation; mismatch/retired completion rejection; original labels on completed results; historical notices after reconnection |
| Vault | Existing accounting components preserved; operational ETH shown separately from selected simulated market; accounting drafts/presets survive market switch but approval retires |

## Exact executed regression

Commands used the isolated Python venv and workspace npm cache:

```bash
cd backend
python -m pip install -e '.[test,ml,redis,yahoo]'
python -m pip check
python -m compileall -q app
python -m pytest -q

cd frontend
npm ci --cache /workspace/work/npm-cache
npm test
npm run typecheck
npm run build
```

| Check | Actual result |
| --- | --- |
| Final complete backend | **1281 passed**, 0 failed/skipped, 1 warning, 53.74s; all 1185 existing cases preserved + 96 new |
| New selected-market backend suite | 96 passed, 0 failed/skipped, 1 warning, 4.75s |
| Corrected legacy API + selected-market suite | 117 passed, 0 failed/skipped, 1 warning, 5.44s |
| Final complete frontend | **454 passed**, 0 failed/skipped/cancelled, 20.52s; all 410 existing cases preserved + 44 new |
| TypeScript / production build | Passed; final Vite build 3.15s |
| Pip check / compileall / git diff checks | Passed |
| Real Chromium | **72 route/viewport checks + 11 recorded workflow groups**, zero page exceptions or document overflow |

Backend warning is upstream Starlette/httpx TestClient deprecation. Frontend
retains existing headless Zustand storage notices, TanStack `use client` notices
and Vite main-chunk advisory (~536 kB, ~141 kB gzip). These are not failed checks.
No test was removed, weakened, suppressed or skipped. The historical generated
terminal-schema mismatch did not reproduce; schema files were not regenerated.

Development attempts are not final acceptance: npm initially tried an unavailable
home cache and was rerun with workspace cache; a badge tone mismatch was corrected.
First full regression found an extra `market_profile=None` worker argument on
legacy optimization; the API now sends the argument only for selected requests,
and the original test passes unchanged. Initial browser harness fixes addressed
ambiguous region/control labels and a result reset on navigation. Final acceptance
was rerun cleanly after those fixes and the final styling/session notices.
Final process inspection also found npm-spawned Vite children surviving their
parent harness processes. The harness now owns separate process groups and
terminates the full groups; acceptance was rerun from fresh services and final
inspection confirmed no acceptance backend or Vite process remained.

## Isolation and economics evidence

The new real-runtime fixture preserves exact before/after strategy/agent/risk
configuration, running state, kill latch, FinalQuoteAuthorization, OrderManager
and AccountingService identities/config/snapshot/reservations, ledger entries/
fingerprint, execution adapter, orders/fills/quotes and TESTNET eligibility.
Catalog/run/comparison/optimization are tested for each market. Invalid selectors,
protected optimization identity and unavailable/delisted markets fail closed.
Inadequate research capital produces actual HALT/no orders. A LIVE/TESTNET source
strategy is copied and forced to DEMO/PAPER without changing its originals.

39 asset/scenario combinations verify deterministic prices, book/perp identities,
precision, frame ordering and fingerprints. Native fixtures deliberately place
assets at unusual universe indices to prevent hardcoded index assumptions.
Cancellation/cache tests demonstrate single-flight ownership and retired verified
eligibility after outages. SDK tests verify native calls, timeout, no WebSocket
and session cleanup. Frontend tests cover exact catalog bounds, fake verification
rejection, detached captures, all three selections, unavailable state, restart/
connection retirement, profile refresh, original result labels and no strategy write.

Actual browser BTC FLASH_MOVE (30 frames, legacy accounting) yielded 2 fills and
30 NORMAL frames; ETH QUIET had 0 fills and 30 NORMAL frames. SOL FLASH_MOVE had
0 fills, 17 HALT and 13 NORMAL frames under unchanged limits. These are observed
research outcomes, not fabricated successes or performance promises. High-Cost
Stress comparison shared exactly one BTC dataset and strategy; only taker-fee
assumptions changed. Controlled comparison deltas remain backend-calculated.

## Real browser acceptance and compact evidence

`frontend/tests/browser-phase146.py` starts owned local Uvicorn/Vite processes,
uses actual `/usr/bin/chromium` through Playwright in America/Los_Angeles, and
shuts both services down. Explicit environment:

```text
MARKET_DATA_MODE=DEMO
EXECUTION_MODE=PAPER
ENABLE_HYPERLIQUID_TESTNET_ORDERS=false
```

Workflows exercise BTC/ETH/SOL metadata/precision/scenarios/trace/provenance,
completed BTC labels after ETH selection, High-Cost Stress customization and
same-market comparison, actual bounded Inventory optimizer for all assets,
delayed actual BTC response during SOL switch, actual backend stop/restart/
revalidation, unavailable metadata with disabled fallback, and a delayed catalog
selection race. Delayed/unavailable browser responses are clearly identified as
browser fixtures; all run/comparison/optimization economics use the real backend.

All twelve application routes were checked at 1920×1080, 1440×900, 1366×768,
1024×768, 768×900 and 390×844. The browser made 14 POST requests, exclusively
to preview/comparison/run/optimization. It issued zero strategy/trading mutations.
Operational ETH configuration, orders, stopped strategy, kill switch, ledger and
TESTNET eligibility remained unchanged before restart. Restart creates its normal
new process/session genesis; after restart the unchanged configuration, orders,
ledger version and signing eligibility were checked independently.

- [Compact workflow/provenance/viewport report](acceptance/phase146/browser-results.json)
- [Actual BTC result with operational ETH header](acceptance/phase146/btc-simulation-1440.png)
- [Actual desktop Vault selector/studio](acceptance/phase146/btc-vault-1440.png)
- [Actual mobile Vault selector](acceptance/phase146/btc-vault-390.png)

Only three useful real Chromium viewport screenshots and a compact report are
committed. No full traces, browser caches, install logs, secrets or AI screenshots
are committed. All older acceptance folders remain intact.

## Limitations and remaining gates

An actual official SDK metadata request returned ProxyError in this environment;
`api.hyperliquid.xyz` is outside the configured HTTP allowlist. Live native
metadata acceptance is therefore **not performed**, and neither fixtures nor
browser evidence are claimed exchange-verified. The official integration is
tested through explicit SDK/native fixtures and fails to honest DEMO profiles
in the actual browser. A network-permitted live check remains a separate gate.

Profiles are code-versioned hypothetical research assumptions; metadata age is
reported at retrieval. Integer prices and per-price precision are enforced but
there is no universal venue tick. Fixed risk/inventory limits can HALT SOL or
reject infeasible source strategy calibration. No current-price calibration,
production margin/fees/funding, profitability guarantee, durable result storage,
cross-market accounting or multi-market execution is implied.

Future multi-market work requires independent engines/feed lifecycles, explicit
capital allocation, isolated/reconciled orders and accounting, cross-market risk
and new acceptance. HIP-3, spot and Phase 15 remain excluded. Existing unfinished
Phase 13.2A–E, macOS/external provider/Redis/signed TESTNET/soak and historical
audit gates remain open. **One draft PR; leave unmerged.**
