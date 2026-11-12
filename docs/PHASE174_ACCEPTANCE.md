# Phase 17.4 — Portfolio Stress & Scenario Intelligence

Base: `d0a9d4a`, latest fetched `main`, including [PR #77](https://github.com/btorressz/hyperamm/pull/77). Backend-only, deterministic, hypothetical BTC/ETH/SOL PAPER research. Independent architecture/correctness/security review remains the draft PR review gate; no automatic merge.

## Implementation decisions

- **REUSE:** native `SimulationEngine`, `generate_scenario`, market profiles/precision, reference fallback, PAPER fill/execution assumptions, fee/funding accounting, existing portfolio accounting/exposure/risk/temporal validators and the lifespan-owned single research worker.
- **ENHANCE:** additive stress contracts in `models.py`; stress operation in portfolio/simulation services and executor allowlist; private trusted-dataset orchestration; bounded aggregation; one `/stress` endpoint. Existing `/run`, `/analyze`, contracts, defaults and fingerprint algorithms are unchanged.
- **ADD:** `portfolio_research/scenarios.py` (joint definitions/transforms/validation), `stress.py` (two-leg coordination and provenance verification), `metrics.py` (eligible comparisons), seven focused test files, shared fixtures and `phase174_resources.py`.

No second engine/worker, operational firewall or accounting change, queue, database, Docker, deployment workflow, frontend dashboard, wallet signing or TESTNET expansion.

## Request and scenarios

`POST /api/v1/portfolio-research/stress` accepts only the existing validated `config`, `config_fingerprint`, optional `risk_policy`, and a `scenario`. No client result, dataset or authoritative receipt is accepted. Assumptions are frozen, extras forbidden, amounts exact bounded Decimal strings/integers (never floats/booleans/nonfinite values), markets unique/canonical BTC → ETH → SOL. Every portfolio market uses the same baseline scenario and frame count; a selected subset may be shocked.

`scenario` contains `contract_version="phase174-stress-v1"`, `scenario_type`, `selected_markets`, zero-based `onset_frame`, `duration_frames`, `recovery_profile`, and `assumptions`. The hypothetical clock is the existing 2026-01-01 UTC one-second generator clock. Onset plus duration plus any lag must fit the captured window. The numeric shock is full strength at onset. `STEP_WINDOW` restores baseline inputs after the declared window; `LINEAR_TO_BASELINE` decays linearly to zero at its last frame and requires at least two frames. These are modeling conventions, not calibrated market estimates or recommended defaults.

| Type | Explicit assumptions and transformation |
| --- | --- |
| `CORRELATED_SELLOFF` | `price_shocks`: exactly one `{market, decline_fraction}` for each selected market; fractions `(0, 0.8]`, common onset/window. Price down is modeled co-movement, not measured correlation. |
| `BTC_LED_VOLATILITY` | `btc_decline_fraction`, required `eth_transmission`/`sol_transmission` for the selected receiving markets; multipliers `(0, 5]`, transmitted decline at most 0.8. Optional `propagation_lag_frames` 0–300 delays receivers. BTC may be an explicitly modeled exogenous origin when the portfolio contains only ETH/SOL. |
| `LIQUIDITY_SHOCK` | `bid_depth_multiplier` and `ask_depth_multiplier` `(0, 1]`, `spread_multiplier` `[1, 20]`. Scale native book depth and distance from midpoint, following existing scenario conventions. Captured latency/cancel delay/slippage/depth participation remain active in the original engine. Zero depth after precision normalization is rejected. |
| `FUNDING_STRESS` | `funding_shocks`: exactly one `{market, adjustment}` per selected market, signed nonzero adjustment in `[-0.01, 0.01]`. Duration/window creates deterministic observations. Requires enabled native funding accounting and a nonzero adjustment at an observed accrual boundary; an initializing first observation or fully recovered final observation does not count. Native rate direction and inventory determine whether funding is a debit or credit. |
| `ORACLE_DEGRADATION` | `reference_source` (`redstone`, `kraken`, `coingecko`); `reference_mode=MISSING` removes that source, or `DIVERGENT` multiplies its existing price by `1 + reference_divergence_fraction` in `(0, 0.5]`. Native consensus/confidence/fallback/risk behavior decides the result. A missing source cannot be diverged. |
| `CONCENTRATION_STRESS` | `concentration_decline_fraction` `(0, 0.8]`; complete baseline position histories required. Select the **whole portfolio's** largest absolute native position × mark immediately before onset; ties BTC → ETH → SOL. Reject zero gross evidence or a target outside selected markets. Price moves down against longs, up against shorts. |

No irrelevant parameter is silently ignored. Matrix-based/empirical correlations and stale source timestamps are unsupported and rejected. The existing `SimulationReferencePrices` contract has no observation timestamps, so missing/divergent source degradation is supported without inventing stale/authenticated observations.

## Execution, evidence and accounting

One allowlisted `stress_portfolio_research` admission owns both sequential legs. Baseline runs use the original scenario path. Native full outputs pass existing `PortfolioMarketExecution` validation (capture, native accounting, fills/orders, ledger chain, source and identities), then project bounded receipts and observations. Concentration selects from the accepted pre-onset evidence, including its sequence, market order and native evidence fingerprints.

Canonical baseline datasets are generated separately; transformations operate on detached validated models. Books, BBO/midpoint, precision-normalized mark/oracle, reference inputs and derived perp bases/notional/premium are rebuilt consistently. Identity, sequence, one-second clock, positive finite prices, sorted uncrossed books and native size precision are revalidated. Baseline data is never changed in place. Stressed datasets pass only through a private service method, absent from public input schemas and the executor allowlist; there is no network, runtime lookup or nested admission.

The existing engine creates fresh PAPER state for each run. For concentration, both runs replay exactly the same pre-onset inputs; native pre-onset accounting observations must match before comparison is returned. Existing inventory is neither scaled nor injected. Subsequent genuine native fills can change inventory. Capital allocations, reserve, strategies, agents, market profiles, fees, execution assumptions and both risk policies remain identical between legs.

Portfolio equity includes native market equity and unallocated USDC reserve once; PnL is equity minus shared starting capital. Native fee/funding accounting is not replayed or deducted again. `funding_quote` is **signed native funding PnL**, added in native PnL reconciliation. Changing funding may also change later quotes/fills via native risk policy; a funding delta alone need not explain the entire portfolio PnL delta. Native 28-digit accounting and its disclosed rounding residual are preserved; comparison arithmetic uses bounded high precision. The stress flow/validation fixes its native Decimal context for deterministic direct callers too.

Eleven comparisons expose baseline, stressed, signed stressed-minus-baseline difference and per-metric eligibility: equity, PnL, gross/net exposure, maximum gross market concentration, reserved-capital utilization, modeled leverage, gross-notional utilization, capital-allocation utilization, funding PnL and maximum portfolio drawdown. Per-market contributions/positions/execution metrics remain available on each leg. No percentage-change denominator, expected return, probability or performance ranking is invented.

## Temporal, risk and provenance

The existing 17.3H temporal rules apply independently to both legs, then cross-leg scenario, market, engine, clock, window, configuration and policy identities must agree:

- `MODELED_ALIGNED`: both have complete compatible histories; portfolio drawdown uses each combined native equity curve including reserve, never sums individual drawdown percentages.
- `FINAL_ONLY`: compatible endpoints with configured retained suffixes; terminal differences may be available, drawdown unavailable, research risk blocked for missing critical history.
- `INCOMPARABLE` / `UNAVAILABLE`: economic/clock mismatch or invalid evidence; no comparison deltas or unconditional assessed transition.

Research transitions preserve baseline/stressed outcomes and decisions. `NORMAL -> WARN`, `WARN -> REDUCE`, `REDUCE -> HALT`, direct jumps and improvements are supported. Only two assessed, comparable reports produce an assessed transition. Missing critical evidence gives `BLOCKED` even if a leg retains a known HALT breach. These are post-execution assessments and never claim to have prevented earlier PAPER orders.

The final `evidence_fingerprint` binds the canonical request, original portfolio identity, stress version/type/timing/magnitudes/transmission, profile/capture/execution/accounting/funding/risk evidence, both dataset/run/full-result identities, temporal classifications and metric eligibility. Dataset source identity includes the stress fingerprint even when tick rounding hides an economic change. Result validation regenerates deterministic expected dataset fingerprints and recomputes comparisons/bindings, rejecting substitution and rehashed inconsistent claims.

`cross_market_correlation=null`, `empirical_correlation_verified=false`, `historical_market_synchronization_verified=false`, `source_authenticated=false`, `authority=NONE` remain explicit. Fingerprints are consistency checks, not signatures, exchange authentication or independent attestations of omitted histories. Concentration candidate observations are same-job native projections bound to the baseline evidence digest, not a new external trust root.

## Resource constraints

All existing limits are preserved and validated **across baseline plus stress**, including configured ledger/event capacities. Requests are rejected rather than silently editing captured settings.

| Resource | Combined bound |
| --- | ---: |
| Markets | 3 |
| Executed frames | 3,000 |
| Frames × levels per side | 24,000 |
| Retained native observations | 1,500 |
| Configured ledger entries | 30,000 |
| Configured accounting events | 750 |
| HTTP request / response bytes | 65,536 / 200,000 |

For three markets with complete histories this permits 250 frames per market **per leg**. For three markets, captured accounting retention must explicitly fit at most 5,000 ledger entries and 125 accounting events per market per leg when distributed equally; earlier defaults are not silently reduced. HTTP remains local-only, no-store, with existing pre-parsing body limits, sanitized errors, busy response and exact bounded response serialization inside the worker and at transport.

Fresh-process native measurements (`cd backend && PYTHONPATH=.:tests python tests/phase174_resources.py --case <case>`), on this cloud environment. Wall time includes complete worker computation/validation/serialization; peak RSS is the whole fresh process, not incremental allocations. Other validation processes were active; these are observed resource measurements, not latency guarantees.

| Case | Combined frames | Quote units | Retained | Worker seconds | Peak RSS MiB | Request / response bytes | Temporal / risk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| BTC ×1,500 per leg | 3,000 | 24,000 | 1,500 | 44.887 | 200.68 | 8,642 / 71,077 | FINAL_ONLY / BLOCKED |
| BTC/ETH ×750 per leg | 3,000 | 24,000 | 1,500 | 62.784 | 173.09 | 15,943 / 123,597 | FINAL_ONLY / BLOCKED |
| BTC/ETH/SOL ×500 per leg | 3,000 | 24,000 | 1,500 | 45.779 | 162.29 | 23,246 / 174,390 | FINAL_ONLY / BLOCKED |
| Complete BTC/ETH/SOL ×250 per leg | 1,500 | 12,000 | 1,500 | 23.729 | 112.57 | 23,246 / 175,668 | MODELED_ALIGNED / ASSESSED |
| Modeled liquidity, three ×500 per leg | 3,000 | 24,000 | 1,500 | 39.219 | 164.04 | 23,164 / 174,656 | FINAL_ONLY / BLOCKED |

All workers released on completion and shut down normally. Three-market cases also reached the combined configured 30,000 ledger / 750 event capacities. Modeled liquidity retained 1,000 ms order latency, 2,000 ms cancellation latency, 1 bps slippage, depth sensitivity and 0.25 participation. Complete histories produced two 250-observation portfolio drawdown curves from the 1,500 total market observations; suffix-only histories produced no drawdown. Limits were not raised.

## Native validation and isolation

Focused tests cover all six transforms × all seven nonempty market selections, native execution, canonical reorder/repeatability, bounded exact input rejection, precision, windows/lags/recovery, funding signs/fees, baseline preservation, concentration inventory, native reference fallback, incomplete/missing/substituted frames, unavailable metrics, risk transitions, changed/forged identities, shared admission, failure cleanup, cancellation/shutdown and actual local uvicorn security.

HTTP isolation checks retain an existing operational order and verify unchanged orders/fills, native balances/ledger/accounting identity, kill switch, authorization, settings/signing references, market history and listeners; operational adapter entry points fail the test if invoked. Optional Redis coordination retains one lease for the complete operation and fails closed when unavailable. No live provider or signed wallet request is used.

Final native acceptance commands run from `backend/` (older AST isolation tests require its relative `app/` paths):

| Check | Actual result |
| --- | --- |
| Phase 17.4 focused tests | 183 passed, included in the combined focused run below |
| Phase 17.1A / 17.2 / 17.3 / 17.3H regressions | 443 passed, included below |
| `python -m pytest -q tests/test_phase171a* tests/test_phase172* tests/test_phase173* tests/test_phase174*` | **626 passed** in 357.82 s |
| Full backend `python -m pytest -q` | **3,146 passed, 1 optional ML skip**, 511.78 s |
| Frontend `npm run typecheck` and `npm run build` | PASS |
| Frontend `npm test` | **717 passed**, zero failures/skips |
| Actual FastAPI/uvicorn HTTP | All six scenarios; typed receipts, local host/origin/forwarding guards, 64 KiB body rejection, sanitized errors and Redis-unavailable 503: PASS |
| Near-limit native workload/worker release | All five reported configurations: PASS |

Acceptance gates: **PASS** for all six scenarios, validated joint assumptions, actual native execution, baseline/inventory/accounting isolation, eligible financial/exposure/drawdown comparisons, incomplete-evidence blocking, research risk transitions, correlation separation, deterministic identities/tampering rejection, single admission and lifecycle, operational/HTTP/resource isolation, API compatibility, backend/frontend regressions and documentation. Independent PR review remains pending.

Known warnings: existing Starlette/httpx TestClient deprecation and the intentional malformed-model serializer warning in the substitution rejection test. Frontend build retains its existing dependency directive/chunk-size notices. No warning was suppressed to obtain acceptance.

## Bugs found and fixed; deferred work

The original 17.1A package-file isolation allowlist required the three new modules to be added; all prohibitions on runtime/API/engine/worker ownership remain. Stress-specific hardening includes exact transmission bounds independent of ambient precision, rejecting mismatched windows and irrelevant assumptions, counting both retention capacities, requiring native funding boundaries, checking the entire portfolio for concentration selection, verifying identical pre-onset accounting and rejecting assumption/dataset substitution. Native accounting/engine behavior required no compatibility fix.

Stale source timestamps, fitted/matrix correlations, authenticated historical joint stress, cross-margin/netting/borrowing, dynamic allocation changes, durable cancellation/recovery and operational risk enforcement remain deferred. All six central scenarios are implemented. Phase 17.5 can consume the typed bounded `/stress` receipt with explicit eligibility, signed deltas, assumptions and non-operational labels; no frontend terminal is added here.
