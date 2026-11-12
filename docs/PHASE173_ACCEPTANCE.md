# Phase 17.3 — Shared Capital & Portfolio Risk Firewall

Starting revision: latest fetched `main`, `4c29d4f09422d9e6049a3814a4d135802f6ba24b`, the merge of [PR #75](https://github.com/btorressz/hyperamm/pull/75). Reviewed its PR description, `PHASE172_ACCEPTANCE.md`, compact validation JSON, and the 17.1A contracts/acceptance before implementation. Prior acceptance counts are historical evidence, not this change's results.

## Requirements and implementation

The supplied requirements call for a complete backend shared-capital research layer over independent BTC/ETH/SOL PAPER runs: exact budget/reserve reconciliation, native accounting, eligible equity/PnL/session loss, exposure/concentration, explicit utilization/leverage, deterministic portfolio risk, temporal eligibility, provenance, bounded single-worker execution, adversarial/security/regression/resource acceptance, and one draft PR. Trading, signing, cross-margin, concurrent execution, a new engine/worker/database, queues, Docker, CI and React portfolio pages are excluded.

| Breakdown | Implementation |
| --- | --- |
| REUSE | Existing immutable portfolio configuration/allocation/provenance; comparison captures and native scenario receipts; sequential orchestration; SimulationService/Engine and single SimulationExecutor; market profiles; AccountingService outputs, `mark_position`, `pnl_breakdown`, `drawdown`; fingerprint utilities; optional Redis lease coordination; local security/body middleware |
| ENHANCE | Portfolio models with separate versioned analysis contracts; optional orchestration evidence projection; service/aggregation coordination and self-validation; one allowlisted simulation service operation; existing API router; exports; exact package allowlist in the historical isolation test |
| ADD | `portfolio_research/{accounting,exposure,risk,temporal}.py`; seven focused test files, reused native fixture extension and resource harness; this report |

The accounting engine, native simulation result, single-market execution economics, operational firewall/authorization and Redis implementation remain unchanged. No new dependency or frontend source is introduced.

## Native evidence architecture

```text
Local boundary / existing body limit / typed config + fingerprint + risk policy
  → one existing local worker admission and optional Redis lease
    → canonical BTC → ETH → SOL (selected markets only)
      → existing run_scenario, once per market
      → existing PortfolioMarketExecution validates full native evidence
      → unchanged Phase 17.2 compact receipt
      → bounded native accounting observations, before full result disposal
    → explicit temporal classification
    → capital/economics reconciliation and complete-history drawdown if eligible
    → exposure, reservations and research risk assessment
    → self-validated, bounded phase173-analysis-v1 receipt
  → typed response revalidation / exact bounded JSON / no-store
```

Each internal observation contains only native frame sequence/time, equity, session PnL, position and mark. Collection checks native receipt/result binding, source/market identity, complete terminal PAPER accounting, metrics agreement, native PnL reconciliation, captured base/price precision, trace equity/PnL consistency and endpoint agreement. Terminal marks/timestamps must match the original representative dataset frame. Full results, orders, fills and ledger rows are discarded per market; no second simulation or reconstruction from HTTP receipts occurs.

At most the already admitted 1,500 retained native trace observations are projected across markets. A complete bounded portfolio curve is constructed transiently only for eligible histories. Transport contains its digest/count, peak, ending and maximum drawdown, not the raw curve. Missing values are never filled forward or replaced by zero.

## Shared hypothetical accounting

The independent-capital model is USDC only. The example reconciles exactly: 40,000 BTC + 35,000 ETH + 20,000 SOL + 5,000 unexecuted reserve = 100,000. Reconciliation reuses validated allocations and verifies one contribution per selected market. There is no shared inventory, reserve duplication, ledger mutation or borrowing.

For supported endpoints, equity = sum(native market equity) + reserve; signed PnL = equity − original shared capital; session loss = max(0, −PnL). Original per-market realized/unrealized PnL, fees and funding remain individually visible. Fees/funding are already in native equity and are never deducted again.

Native accounting uses its existing 28-digit Decimal arithmetic. Reconciliation calls the existing accounting functions at that precision and preserves the exact returned financial values. Aggregate sums/subtraction use an 80-digit local context; `native_rounding_residual_quote` explicitly reconciles portfolio PnL with the sum of native net PnL. It is a disclosed native arithmetic residual, not an invented fee/funding adjustment. Repeating ratios use 50 significant digits, rounded half-even to at most 60 fractional places, within the existing financial observation contract. No binary float financial arithmetic is used.

## Temporal methodology

`phase173-temporal-v1` defines `DETERMINISTIC_SCENARIO_UTC_1S_V1`: original scenario start `2026-01-01T00:00:00Z`, sequences 1…N, one-second observations, no gaps/resets. Each retained suffix must have exactly the configured length, consecutive expected sequence/time and a matching terminal dataset frame. Engine version, scenario and complete reference window must agree across markets; matching timestamps alone do not establish eligibility.

| Classification | Accounting and risk eligibility |
| --- | --- |
| MODELED_ALIGNED | All native traces complete on the defined common clock; terminal economics and full portfolio drawdown supported |
| FINAL_ONLY | Valid configured suffixes, disabled traces or zero retention; same engine/scenario/window endpoints support independent terminal reconciliation only; drawdown unavailable and risk BLOCKED |
| INCOMPARABLE | Different engines, scenarios or observation windows; per-market evidence retained, aggregate economics/exposure/concentration unavailable; risk BLOCKED |
| UNAVAILABLE | Missing expected observations or invalid sequence/time; aggregate economics/exposure/concentration unavailable; risk BLOCKED |

Missing/corrupt mandatory financial evidence is rejected with sanitized 422; invalid temporal evidence can instead return a typed unavailable assessment. No cross-gap/reset or cross-window aggregate is accepted. `historical_market_synchronization_verified` is permanently false. There is no historical source authentication, licensing verification or exchange synchronization claim.

For MODELED_ALIGNED histories, portfolio equity is constructed at each common observation with the reserve included once. Peak starts at the original shared capital and follows the portfolio series. Existing `drawdown` semantics give `(peak − equity) / peak`; the report retains terminal drawdown and the largest observed fraction. Individual market drawdown percentages are never combined. Nonpositive equity cannot produce finite modeled leverage; a positive portfolio peak is required for drawdown.

## Exposure, utilization and risk

`phase173-exposure-v1` validates explicit base-market/USDC units, captured market-profile precision and native valuation identity. Signed exposure = filled position base × native mark; gross = sum(abs(signed)); net = sum(signed). Concentration = abs(market exposure)/gross; a supported flat portfolio has zero concentration. Ineligible portfolios have null aggregate and concentration values. Position exposure remains separate from native reservations and unavailable pending-order exposure.

| Metric | Definition and interpretation |
| --- | --- |
| Capital allocation utilization | Allocated initial capital / total initial budget; allocation, not margin |
| Gross notional utilization | Gross filled-position exposure / positive supported portfolio equity |
| Modeled leverage | Same explicitly named ratio as gross notional utilization; null for missing/nonpositive/incomparable equity |
| Reserved-capital utilization | Sum(validated native reserved capital) / positive supported portfolio equity; null if any reservation is missing |
| `max_capital_utilization` check | Uses reserved-capital utilization, matching existing native simulated capital reservation concepts |

Reservations include the native reservation model's existing/proposed quotes. No order reserve is inferred from missing HTTP order history. None of these ratios represents actual Hyperliquid margin, liquidation or withdrawable capital.

`phase173-risk-v1` reuses all seven `PortfolioRiskLimits`: gross, absolute net, concentration, reserved-capital utilization, leverage, session loss and maximum portfolio drawdown. The explicit scope is terminal limits plus full-history maximum drawdown, not every historical exposure/reservation state and not in-simulation order prevention.

Default policy: warning at 0.8 × limit, reduction at 0.95 × limit, hard breach at the positive limit itself. Configuration requires `0 < warning < reduction < 1`. NORMAL is below warning, WARN reaches warning, REDUCE reaches reduction, HALT reaches/exceeds the hard limit. With a zero drawdown ceiling, zero drawdown is NORMAL and any positive drawdown HALTs. Checks and reasons use a fixed seven-limit order; the most severe known check wins.

Every required check must be available for an ASSESSED outcome. Otherwise outcome is BLOCKED, compliance is false, and decision is null unless a known hard breach independently warrants HALT. Missing drawdown never produces unconditional NORMAL. `risk_compliant` is true only for complete ASSESSED NORMAL/WARN results. This is a post-execution research acceptance flag; REDUCE/HALT/BLOCKED cannot accept the result as compliant and cannot alter already executed PAPER orders.

## Provenance and validation

Separate versions are `phase173-analysis-v1`, `phase173-accounting-v1`, `phase173-exposure-v1`, `phase173-temporal-v1` and `phase173-risk-v1`. The original byte-equivalent Phase 17.2 execution bundle is nested under `execution`. Its original configuration, market receipt, full-result/run/dataset, accounting/ledger/profile and execution-assumption identities remain intact.

New hashes bind the complete execution bundle, allocation/reserve, native observation identities, engine/scenario clock, valuation times, economic contributions, metrics, methods/limitations, risk limits/policy and decisions. Canonical market order makes reordered valid requests identical. Wire validation reconstructs temporal eligibility, terminal accounting/exposure and risk decisions, checks source bindings and rechecks all nested fingerprints, including copied frozen instances.

The omitted native curve/full results cannot be independently reconstructed or rehashed from HTTP. Their original hashes, curve digest and native-derived drawdown summary are same-job service evidence, not signatures or independent attestations. No route accepts these projections as client accounting authority.

## API, worker and operational isolation

`POST /api/v1/portfolio-research/analyze` accepts `PortfolioAnalysisRequest`: unchanged configuration/fingerprint plus optional `risk_policy`. Extra fields, submitted results, forged fingerprints, invalid thresholds and workload overflow fail validation. `/run` still returns the original Phase 17.2 contract.

The existing local Host/Origin/peer/forwarded-header boundary and 65,536-byte request bound apply before parsing/admission. Results use typed OpenAPI contracts, exact JSON byte bounds and `Cache-Control: no-store`. Sanitized 413/422/429/503/500 cases and real production-uvicorn loopback success/outage behavior are exercised. Response budget stays 200,000 bytes, enforced inside the worker and at HTTP return, including exact-cap/one-byte-over tests.

Exactly one pool submission covers the entire analysis, with no nested admission, retry or queue. Competition in both directions covers ordinary simulation, optimizer, replay, scenario/historical comparison, Research Vault comparison, 17.2 run and 17.3 analysis. Cancellation retains the real worker and optional Redis lease; shutdown waits; failures release capacity after computation actually ends. Fakeredis/Lua validates optional coordination, including outage and cancellation behavior; it is not physical Redis acceptance.

Operational before/after checks preserve selected market/strategy, agents/risk/kill switch/authorization, orders/fills, accounting/ledger/reservations, market history/listeners, settings identity and TESTNET enabled/signing references, including an actual research HALT. New modules have no operational runtime or order/signing authority. No networking permissions are expanded.

## Native validation and resources

Final command results and cold-process measurements are recorded below after execution. Raw logs/temporary data remain ignored in `work/`; no historical acceptance report is rewritten.

Environment: Python 3.12.14; FastAPI 0.142.2; Pydantic 2.13.5; pytest 8.4.2; httpx 0.28.1; fakeredis 2.40.0; NumPy 2.5.3; Node 24.19.0/npm 11.9.0. Used the existing prepared `/workspace/.hyperamm/venv/bin/python`; dependency consistency passes. Manifests/lockfile remain unchanged.

| Executed command/check | Result |
| --- | --- |
| Original five 17.1A + five 17.2 focused suites | 205 passed; 68.92 s; final full regression includes these again |
| Seven requested `tests/test_phase173_*.py` files, `-q -rs` | 161 passed, 0 failed/skipped; 74.75 s |
| `cd backend; /workspace/.hyperamm/venv/bin/python -m pytest tests -q -rs` | 2,886 passed, 0 failed, 1 optional ML skip; 303.52 s |
| `cd frontend; npm ci --cache ../work/npm-cache` | PASS; lockfile unchanged |
| `npm run typecheck` / `npm run build` | PASS / PASS |
| `npm test` | 717 passed, 0 failed/skipped; 16.608 s |
| Real FastAPI/production-uvicorn security, response bounds and Redis outage | PASS in focused/full suites |
| Typed OpenAPI `/run` and `/analyze` request/response contracts | PASS; old/new types remain separate |
| `git diff --check`; unchanged core engine/accounting/firewall/coordination/frontend | PASS |

The full backend skip is the existing optional missing `sklearn` at `test_agent_expansion.py:406`. Existing Starlette TestClient/httpx deprecation and frontend React Query directive/chunk-size notices remain visible. No warning or failing case was disabled. An initial full regression was interrupted to correct incomparable concentration eligibility; the complete final run above was restarted after the fix.

Reproduce the exact focused invocation from `backend/`:

```bash
/workspace/.hyperamm/venv/bin/python -m pytest \
  tests/test_phase173_accounting.py tests/test_phase173_exposure.py \
  tests/test_phase173_risk.py tests/test_phase173_temporal.py \
  tests/test_phase173_provenance.py tests/test_phase173_integration.py \
  tests/test_phase173_isolation.py -q -rs
```

| Workload | Frames | Native observations | Portfolio observations | Worker s | Peak RSS MiB | Response bytes | Exposure ms | Risk ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC ×3,000 | 3,000 | 1,500 | 0 | 25.1587 | 110.98 | 28,675 | 12.917 | 26.823 |
| BTC/ETH ×1,500 | 3,000 | 1,500 | 0 | 53.0322 | 92.68 | 50,911 | 26.151 | 48.353 |
| BTC/ETH/SOL ×1,000 | 3,000 | 1,500 | 0 | 36.8026 | 84.41 | 72,283 | 38.780 | 71.253 |
| BTC/ETH/SOL ×500, complete | 1,500 | 1,500 | 500 | 18.5448 | 74.04 | 72,751 | 39.567 | 82.426 |
| BTC/ETH/SOL ×1,000, modeled execution | 3,000 | 1,500 | 0 | 24.9164 | 83.27 | 72,380 | 38.710 | 73.186 |

All cases retain exactly 1,500 original native observations without increasing any limit. The complete case is MODELED_ALIGNED/ASSESSED with 500 portfolio observations; the four larger suffix cases are FINAL_ONLY/BLOCKED with no claimed portfolio drawdown. Every worker released capacity and shut down.

Bounds remain 1–3 markets, 3,000 total frames, 24,000 frame × quote-level units, 1,500 retained native traces, 30,000 configured ledger entries, 750 configured events, 65,536 request bytes and 200,000 response bytes. No limit was raised to obtain acceptance.

Resource reproduction from repository root, using the prepared interpreter:

```bash
for case in one two three aligned modeled; do
  PYTHONPATH=backend:backend/tests /workspace/.hyperamm/venv/bin/python \
    backend/tests/phase173_resources.py --case "$case"
done
```

Each sample is a fresh process with an actual existing worker. Peak RSS includes setup/imports and is the process high-water mark; worker elapsed includes native runs, projection, repeated validation and serialization. Exposure/risk timings accumulate those functions' invocations inside admission, including receipt validation. One sample per workload is a resource observation, not an SLA or causal performance comparison. Every sample revalidates the full typed response, recovers admission and shuts down. The complete-history case demonstrates a correct bounded drawdown path; larger sparse jobs deliberately remain FINAL_ONLY/BLOCKED.

## Adversarial findings and fixes

- An initial repeating concentration ratio exceeded the reused financial observation exponent bound. Ratios now have an explicit bounded precision policy; small repeating ratios and low ambient precision have dedicated tests.
- Native nested spread/accounting validators depend on the engine's Decimal precision. Analysis assembly/receipt validation establish the native 28-digit context before exact portfolio arithmetic, preserving original economics under a caller's smaller context.
- Initial new test helpers flattened typed nested evidence before sealing and therefore hashed different serialization. Helpers now retain the typed native models; no production validator was weakened. A test mark was corrected to an actually valid native price precision.
- Final review found concentration shares still populated across incomparable histories. Shares now become null with the other unsupported aggregates. Engine clock identity is explicitly checked too.
- Native evidence adversaries cover missing accounting, unknown equity, missing/out-of-order/duplicate/discontinuous/reset traces, foreign markets/units/source timestamps, altered marks/positions/results, forged risk/configuration identities, zero/nonpositive denominators, fees/funding, full/partial allocations and all selection/order combinations.
- The historical isolation test's exact eight-file package allowlist was extended for the four requested modules while retaining all forbidden-authority scans. No old test or safeguard was disabled.

## Gates, limitations and Phase 17.4 readiness

| Gate | Result |
| --- | --- |
| 17.1A and 17.2 compatibility, original configuration/market fingerprints | PASS |
| Exact shared capital, reserve, native accounting, no duplicate fees/funding | PASS |
| Signed/gross/net exposure, concentration, explicit utilization and modeled leverage | PASS where eligible; unavailable values fail closed |
| Session loss and complete modeled portfolio drawdown | PASS on supported endpoints/complete aligned histories |
| Temporal eligibility, incompatible/missing evidence and tamper rejection | PASS |
| NORMAL/WARN/REDUCE/HALT and missing-critical-evidence BLOCKED | PASS |
| Versioned accounting/risk provenance and deterministic market order | PASS |
| Research-only decisions, operational/signing isolation | PASS |
| One admission, contention, cancellation/shutdown/failure, optional coordination | PASS |
| Local HTTP/security, request/response bounds, native backend/frontend suites | PASS |
| Native resource ceilings and complete bounded drawdown path | PASS; five fresh processes, including complete aligned native history |
| Correlated stress intelligence | Deferred 17.4 |
| React portfolio terminal / browser acceptance | Deferred 17.5 / 17.5–17.6 |
| Authenticated historical synchronization / physical Redis | Separate external gates |
| Durable lifecycle/restart recovery | Deferred 16.6B |

Correlated stress intelligence remains 17.4; the React portfolio terminal remains 17.5 and browser acceptance 17.5–17.6. No screenshot is required for this backend-only change. Authenticated historical synchronization and physical Redis remain separate external gates; durable restart/recovery remains 16.6B. There is no actual cross-margin portfolio, pending-order exposure estimate, historical per-frame reservation risk series, live control authority or altered PAPER execution history.

**Phase 17.4 readiness: PASS for the supported hypothetical shared-capital accounting and post-execution research risk foundation, including a correct bounded complete-history drawdown path.** This acceptance grants no live trading, historical synchronization or merge authority.
