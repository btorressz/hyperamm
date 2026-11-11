# Phase 16.5B — Quantitative Comparison Engine (descriptive PAPER receipts)

**Implementation draft** based on merged [PR #63](https://github.com/btorressz/hyperamm/pull/63). Phase 16.5B has **no independent native or browser acceptance yet**. Codex must run, verify and harden this code before merging.

## Architecture: ADD / REUSE / ENHANCE

- **ADD** [`research_replay/quantitative.py`](../backend/app/research_replay/quantitative.py), a pure read-only projection of existing Python `SimulationMetrics` and `VaultSnapshot` values, with immutable `phase165b-v1` Pydantic evidence contracts and a canonical output fingerprint.
- **ADD** [`test_phase165b_quantitative.py`](../backend/tests/test_phase165b_quantitative.py), native scenario/replay integration coverage using the existing A.2 `pair` fixture, private vault/importer and actual engine results.
- **REUSE** `CapturedScenarioResult`, `ScenarioProvenanceReceipt`, `ComparisonFoundation`, `capture_comparison_foundation`, `HistoricalReplayResult`, `ReplaySegmentResult.simulation_result_json`, `SimulationResult`, `SimulationMetrics` and PAPER `VaultSnapshot`.
- **ENHANCE only if needed after native tests** existing input validation; no additional worker/engine, ingestion route, reporting database, HTTP endpoint or frontend.

## Native interface

```python
from app.research_replay.quantitative import compare_quantitative_paper
receipt = compare_quantitative_paper(
    scenario=captured_scenario_result,  # phase165a2-v1 opt-in bound result
    historical=historical_replay_result,  # phase162-v1 native receipt
    segment_index=0,                      # explicit independent segment
)
```

The builder re-parses both Pydantic objects, requires the **same-job bound scenario receipt**, and invokes the existing Phase 16.5A comparison foundation. It then selectively decodes **one** historical segment's engine archive and projects existing metric fields and vault snapshots. The original source dataset fingerprint differs intentionally from the segment engine dataset fingerprint; that is validated by A.2, not overwritten in B.

### Metric registry (backend values only)

| Source | Metrics | Units/behavior |
| --- | --- | --- |
| `SimulationMetrics` | frame_count, starting/ending equity, session/realized/unrealized PnL, return %, max drawdown, fills/buy/sell, quoted/filled notional, fill activity, ending/max inventory, max inventory utilization, risk HALT fraction | Directly copied exact Decimal/integer fields; no derived cross-source metric |
| `VaultSnapshot` | fees quote, funding quote, capital utilization, reserved capital, gross exposure | Used only when an existing simulated `PAPER` Vault reports the value; missing fields remain `NOT_REPORTED` |
| `SimulationMetrics.risk_state_counts` | Existing per-frame risk-state counts | Copied per side, not subtracted, pooled or converted into hypothetical absent states |

A 0 value is `AVAILABLE`, not `NOT_REPORTED`. Null remains unavailable; quoted/inventory utilization are not substituted for capital utilization. The metrics are labeled with source and units, with no new financial calculation, annualization, exposure conversion or return normalization.

### Allowed displays

| Foundation status | Output |
| --- | --- |
| `CONTEXT_ONLY` | Two separately labeled descriptive metrics for the scenario and **one selected historical segment**, each from its existing backend receipt; no numerical performance comparison or cross-market inference |
| `INCOMPARABLE` | Provenance, reasons, segment index and `BLOCKED`, **no paired quantitative rows** |
| `ALIGNED` | Not possible under existing `phase165a1-v1`, remains reserved and rejected |

The flags `differences_available`, `cross_segment_aggregation_allowed`, `strategy_ranking_allowed`, `matched_market_evidence_verified` are literal **false** in this contract. This intentionally rules out PnL deltas, continuous cross-gap returns, combined equity, strategy ranking, profit superiority, real fill inferences and independent source certification.

Even when metrics use a common column/unit, **scenario synthetic economics and historical admitted evidence are not an aligned controlled experiment**. This release does not change that.

### Native acceptance handoff

Before merge, run (from `backend/` with existing Python 3.12/test dependencies):

```bash
python -m pytest tests/test_phase165b_quantitative.py tests/test_phase165a2_integration.py tests/test_phase165a1_contracts.py tests/test_phase1641_acceptance.py -q
python -m pytest tests -q -rs
```

Verify: BTC/ETH/SOL, same and mismatched markets, exact zero vs missing metrics, capped frames, multi-segment gaps, modeled execution, risk/agent/capital changes, tampered bound receipts, lazy segment-archive identity, 0 fills, backend vault availability, immutability, deterministic JSON/fingerprints and operational isolation.

Acceptance results must include Python and dependency versions, exact baseline/head commit SHAs, pass/fail/skip counts and any defects corrected. PR #63 reported **2,341 passed / 3 failed / 1 skipped** for its native full backend run; the three failures are documented historical static checks, **not a green test baseline**. Reproduce and report any current failures rather than suppressing them.

Phase 16.5C frontend/Explainability Studio, browser acceptance and a comparison HTTP endpoint are intentionally **not implemented** in B. Future C/D can expose this bounded receipt without extending trading authority.

**Restrictions:** no Docker, GitHub Actions, K8s, Redis worker changes, new package dependencies, operational strategy updates, signing, live order submission, historical data upload, external network requests, new simulation or replay runner, or auto merge.
