# Phase 17.3H — Portfolio Risk & Temporal Evidence Hardening

Base: `4b309f97d6778c96916b16439be8e1f91a10950f`, latest fetched `main`, merging [PR #76](https://github.com/btorressz/hyperamm/pull/76). Reviewed its implementation, PR description and [17.3 acceptance](PHASE173_ACCEPTANCE.md). Prior acceptance counts are historical; the results below are from this branch.

## Three findings and changes

1. **Complete histories and resource bounds.** The existing 1,500-observation cap already permits BTC/ETH/SOL ×500 complete native frames. These support `MODELED_ALIGNED` and portfolio drawdown computed from the combined native equity series, with reserve included once and initial capital in the running peak. Valid configured suffixes in larger jobs remain `FINAL_ONLY`: terminal accounting is supported, portfolio drawdown is unavailable, and risk is `BLOCKED`. Missing expected observations, duplicates, reordered/discontinuous/reset sequences and altered timestamps cannot establish alignment. No observations are fabricated, interpolated or forward-filled.

   Temporal consumption previously checked sequence/time and source pointers but did not repeat financial projection checks. It now revalidates exact receipt/evidence types, native initial-equity-plus-PnL consistency and terminal equity/PnL/position/mark. Relabeled foreign observations and inconsistent financial substitutions are rejected. Clock contracts reject contradictory retention/completeness claims, even with recomputed hashes. Collection still validates the full native result before disposal; accounting arithmetic is unchanged.

2. **Research risk firewall.** Existing inclusive thresholds and severity ordering are preserved: NORMAL below warning, WARN at warning, REDUCE at reduction, HALT at a positive hard ceiling. A zero drawdown ceiling HALTs only on positive drawdown. All seven critical checks must be available for `ASSESSED`; otherwise `BLOCKED`, compliance false, decision null unless a known hard breach warrants HALT. Known WARN/REDUCE checks remain visible without becoming unconditional decisions on incomplete evidence.

   The standalone evaluator previously accepted separately valid reports without checking their cross-report identities and could accept missing equity/PnL if the seven check values were supplied. It now rejects mismatched configuration/accounting/exposure/temporal bindings and blocks missing critical equity/PnL. Taking absolute net exposure previously rounded under ambient Decimal precision; `copy_abs()` preserves the exact value and threshold classification.

   Decisions are **post-execution hypothetical research assessments**. REDUCE/HALT cannot modify operational orders, kill switches, authorizations, balances or TESTNET signing. They do not prevent previously simulated PAPER orders. Native HTTP tests exercise both REDUCE and HALT while preserving an existing operational order, accounting/ledger, kill switch, authorization, observers/listeners, settings and signing references; operational adapter methods fail the test if called.

3. **Modeled temporal provenance and correlation.** `MODELED_ALIGNED` means a complete common deterministic scenario clock, not authenticated historical market synchronization. Matching synthetic timestamps never establish empirical correlation. `historical_market_synchronization_verified` remains false throughout. Temporal receipts now explicitly expose `cross_market_correlation = null` and `empirical_correlation_verified = false`; non-null calculations and forged synchronization/source-authentication/attestation claims are rejected. No correlation engine or stress scenario is added.

   **Phase 17.4 must explicitly declare synthetic shock/correlation assumptions unless validated overlapping historical datasets are supplied.** Timestamp matching alone cannot upgrade scenario evidence into synchronized historical data.

## Scope and compatibility

REUSE the existing portfolio accounting/exposure/allocation, provenance, native simulator, sequential orchestration, single research worker, optional Redis coordination and local HTTP/security infrastructure. ENHANCE only existing portfolio models, temporal/risk validators, regression fixtures and the resource harness. ADD one hardening test file and this report; update README/CHANGELOG. No production module, engine, worker, queue, database, frontend feature, operational firewall, signing or native accounting change.

17.1A configuration and 17.2 `/run` identities are unchanged. The 17.3 analysis fingerprint includes the new explicit correlation fields and expanded limitations; it must be regenerated from native evidence. Old analysis hashes are not silently upgraded. No endpoint accepts client-supplied analysis, receipts or financial observations as execution authority.

Fingerprints bind same-job evidence, not signatures, source authentication or independent engine attestation. The omitted native histories cannot be reconstructed or independently authenticated from HTTP summaries. Rehashing an entirely fabricated, internally consistent history does not establish real provenance. There is no new historical trust root in this phase.

## Unchanged bounds

| Resource | Bound |
| --- | ---: |
| Selected markets | 1–3 BTC/ETH/SOL |
| Total executed frames | 3,000 |
| Sum(frames × levels per side) | 24,000 |
| Total retained native trace observations | 1,500 |
| Total configured ledger/event entries | 30,000 / 750 |
| HTTP request / encoded JSON response | 65,536 / 200,000 bytes |

No limit is raised or capture silently rewritten to obtain eligibility. Boundary tests cover complete 500 ×3, 501 ×3 with retained suffixes, 1,000 ×3 at the frame/quote/trace caps, and 160 ×3 ×50-level wide ladders. Over-budget complete 501 ×3, 1,001 ×3, 1,000 ×3 ×9 levels and 161 ×3 ×50 levels are rejected before HTTP worker admission. Existing suites cover exact response-byte boundaries, body limits, contention, cancellation, shutdown and optional Redis lease isolation.

## Native validation

Environment: Python 3.12.14, pytest 8.4.2, FastAPI 0.162.5, Starlette 1.10.0, Pydantic 2.14.3, httpx 0.28.1, fakeredis 2.40.0, NumPy 2.5.4; Node 24.19.0/npm 11.9.0. Installed existing backend `[test,redis]` extras in ignored `work/venv`, frontend dependencies with `npm ci --cache ../work/npm-cache`. Manifests and lockfile unchanged; `pip check` passes.

| Executed check | Actual final result |
| --- | --- |
| Focused 17.1A / 17.2 / 17.3 / 17.3H suites | **443 passed**, 0 failed/skipped; 177.98 s (115 / 90 / 161 / 77 tests) |
| Full backend `pytest tests -q -rs` with JUnit output in ignored `work/` | **2,963 passed, 1 skipped**, 0 failed; 328.43 s |
| Frontend `npm run typecheck` / `npm run build` | PASS / PASS; production bundle built in 3.42 s |
| Frontend `npm test` | **717 passed**, 0 failed/skipped; 14.981 s |
| Operational REDUCE/HALT isolation, single admission, contention, cancellation/shutdown, HTTP byte/security bounds | PASS in focused/full suites |
| Dependency consistency / diff whitespace / unchanged restricted production paths and limits | PASS |

Full-suite skip: existing optional ML test at `tests/test_agent_expansion.py:406`, missing `sklearn`. The three warnings are the existing Starlette/httpx deprecation and two existing `record_property` tests warning about the JUnit xunit2 format. Frontend React Query directive/chunk-size notices remain visible. No failing test or warning was disabled.

Initial development runs reported 65 passed/6 failed (new fixtures assumed validation before direct worker submission and used the wrong adapter method), then 440 passed/3 failed (wide-ladder liquidity setup and exact decimal strings). Corrected those fixtures without changing their assertions or weakening production validators; targeted recheck: 6 passed, 71 deselected, 4.32 s. All cases are included in both final successful runs. Existing risk tests now explicitly relink their synthetic accounting/exposure/configuration fixtures after changing metrics or limits; their original decision assertions remain.

Raw logs, JUnit and measurements remain ignored under `work/`; no screenshots or large JSON artifacts are committed.

Five fresh processes ran serially after the full regression, using the existing `SimulationExecutor` and FLASH_MOVE scenarios. Every case retained exactly 1,500 native observations, independently roundtripped the typed JSON response, released admission and shut down.

| Workload | Total frames / quote work | Native / portfolio observations | Worker s | Peak RSS MiB | Response bytes | Temporal / risk |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTC ×3,000 | 3,000 / 24,000 | 1,500 / 0 | 24.0152 | 112.43 | 29,105 | FINAL_ONLY / BLOCKED |
| BTC/ETH ×1,500 | 3,000 / 24,000 | 1,500 / 0 | 47.6262 | 94.90 | 51,341 | FINAL_ONLY / BLOCKED |
| BTC/ETH/SOL ×1,000 | 3,000 / 24,000 | 1,500 / 0 | 35.2817 | 84.18 | 72,713 | FINAL_ONLY / BLOCKED |
| BTC/ETH/SOL ×500 complete | 1,500 / 12,000 | 1,500 / 500 | 17.0353 | 74.40 | 73,181 | MODELED_ALIGNED / ASSESSED |
| BTC/ETH/SOL ×1,000 modeled execution | 3,000 / 24,000 | 1,500 / 0 | 21.5393 | 84.07 | 72,810 | FINAL_ONLY / BLOCKED |

All five resource checks pass. The aligned case validates 500 portfolio observations; all four larger cases have no portfolio drawdown and remain noncompliant/BLOCKED. Modeled execution reuses existing latency, delayed cancellation, slippage, depth and participation assumptions. RSS is the Linux process high-water mark including setup/imports; each workload has one sample. These runs do not fill the entire configured ledger/event allowance, prove a hard RSS ceiling or establish a latency SLA.

Reproduce from the repository root:

```bash
cd backend
../work/venv/bin/python -m pytest tests/test_phase171a_*.py tests/test_phase172_*.py tests/test_phase173_*.py tests/test_phase173h_*.py -q -rs --junitxml=../work/portfolio-focused-final.xml
../work/venv/bin/python -m pytest tests -q -rs --junitxml=../work/backend-full.xml
cd ../frontend
npm run typecheck
npm run build
npm test
cd ..
for case in one two three aligned modeled; do
  PYTHONPATH=backend:backend/tests work/venv/bin/python backend/tests/phase173_resources.py --case "$case"
done
```

## Remaining limitations and Phase 17.4 readiness

Risk covers terminal limits plus complete-history maximum portfolio drawdown, not a historical per-frame exposure/reservation firewall. Independent-capital PAPER runs do not model cross-margin, borrowing, venue margin/liquidation or available pending-order exposure. Resource samples are observations, not memory/latency SLAs. Optional fakeredis/Lua checks do not certify a physical Redis service; durable restart/recovery remains deferred.

**Phase 17.4 readiness: PASS for the bounded hypothetical accounting and post-execution research-risk foundation.** All requested regression, hardening, frontend, resource and operational-isolation checks pass, subject to the explicit optional ML skip and limitations above. Phase 17.4 must declare synthetic shock/correlation assumptions unless validated overlapping historical datasets are supplied. Stress scenarios remain unimplemented. This acceptance grants no historical synchronization, empirical correlation, execution authority or automatic merge.
