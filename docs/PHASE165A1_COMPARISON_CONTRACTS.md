# Phase 16.5A.1 — Scenario / Historical Replay Comparison Contracts

**Status: implementation draft, awaiting Codex 16.5A.2 integration and native acceptance.** Based on the merged [Phase 16.4.1](PHASE1641_ACCEPTANCE.md) foundation, including its three unchanged backend static documentation failures. This phase does **not** introduce a new HTTP route, calculator, execution worker or UI.

## Ownership / boundaries

- **REUSE** `SimulationResult`, `HistoricalReplayResult`, `ReplaySegmentResult`, `StrategyConfig`, `AgentConfig`, `RiskFirewallConfig`, `SimulationConfig`, market-profile identity and `stable_fingerprint`.
- **ADD** [`backend/app/research_replay/comparison.py`](../backend/app/research_replay/comparison.py): frozen evidence contracts, normalized configuration snapshots, deterministic provenance checks and reason-code classification. [`backend/tests/test_phase165a1_contracts.py`](../backend/tests/test_phase165a1_contracts.py) supplies focused real-engine PAPER fixtures.
- **DO NOT** compute PnL, returns, risk or fill-count deltas in this phase; add another simulator, authorizer, wallet signer, market feed, historic collector, import API, database or frontend view.

## Contract interface

```python
from app.research_replay.comparison import (
    ScenarioInputCapture,
    capture_comparison_foundation,
)

scenario_inputs = ScenarioInputCapture(
    strategy=effective_research_strategy,  # DE﻿MO / PAPER, after any market-profile scaling
    agents=admitted_agent_configuration,
    risk=admitted_risk_configuration,
    simulation=admitted_simulation_configuration,
    market_profile=admitted_market_profile_or_none,
)

foundation = capture_comparison_foundation(
    scenario=scenario_result,             # real SimulationResult
    scenario_inputs=scenario_inputs,      # captured at same research admission
    historical=historical_replay_result,   # real HistoricalReplayResult
    segment_index=0,                     # one segment, never full replay aggregation
)
```

The API is pure and intentionally not connected to the live runtime. `ScenarioInputCapture` must contain **effective** admission-time copies, not mutable state read after the scenario. `ComparisonConfigSnapshot` freezes an exact canonical JSON copy of strategy, agents, risk, simulation and optional market profile. Separate fingerprints identify strategy, agents, risk, accounting configuration including capital, execution assumptions, simulation display controls and research market profile. These are *configuration* fingerprints, not capital or accounting ledger identities.

`ComparisonSide` retains the source dataset fingerprint, **distinct** engine/segment dataset fingerprint, run/result identity, market, engine version, frame count, source kind and bounded receipt/trace window. Scenario time coverage is only labeled complete when **all** original frames are actually present in the trace; a truncated or disabled trace yields `UNKNOWN`. Historical start/end are the selected segment's original receipt times, not a verified continuous venue session.

The builder revalidates both existing Pydantic results. It cross-checks the scenario's strategy fingerprint, execution fingerprint, market profile, capital, dataset, scenario name and frame count; the historical selected segment's archived strategy, execution, research profile and starting equity against the frozen server capture. Phase 16.4.1 already binds replay archive metrics, traces and per-segment identity. No independent SHA verification of source provenance or exchange authentication is claimed.

## Classification / comparability policy

| Status | Rule in this version | Permitted result |
| --- | --- | --- |
| `INCOMPARABLE` | Different market or simulation engine version | Identity/provenance and explicit hard reasons; **no** performance comparison |
| `CONTEXT_ONLY` | Same market and engine, regardless of aligned/differing other settings | Show separate descriptive results and differences with caveats; **no** direct numerical performance inference |
| `ALIGNED` | **Reserved** for a later explicitly verified *paired economic evidence* lineage contract | **Not emitted or accepted** by Phase 16.5A.1; matching settings or timestamps alone are insufficient |

Reasons are a closed enum: strategy, agents, risk, accounting, execution assumptions, market profile, simulation controls, market/engine mismatch, distinct evidence, unverified scenario input-capture, temporal uncertainty, segment resets, and source/license trust limits. Aligned/differing *configuration dimensions* are returned independently of the overall status; they must not be interpreted as equal source data.

**Why `ALIGNED` is unavailable now:** ordinary deterministic scenario runs generate separate market datasets, while historical replay consumes admitted observation evidence. Existing `SimulationResult` does not cryptographically attest the separate agent/risk input snapshots. Even if the configured strategy, market, capital and model match, inputs do not prove the same price path, source, timestamps, funding conventions or sample coverage. Returning an apparently valid PnL delta would be misleading.

`ComparisonFoundation` is frozen and reproducibly fingerprinted; the model refuses a forged `ALIGNED` claim. Its `direct_metric_deltas_allowed`, `matched_market_evidence_verified`, `cross_segment_aggregation_allowed` flags are **always false**. No capital, equity, return, simulated fill, risk or funding aggregation exists in this foundation.

## Acceptance tasks for Codex 16.5A.2

1. Run actual native focused tests and correct contract/build failures. Example from `backend/`:

   `python -m pytest tests/test_phase165a1_contracts.py tests/test_phase1641_acceptance.py tests/test_phase162_replay.py -q`

2. **Bind scenario input capture atomically** to the same existing one-slot research job, reusing current `SimulationService`, executor and API admission. Do not query current runtime inputs after computation. Consider a read-only, bounded response attachment if needed. Scenario side agent/risk snapshots are not engine-attested in existing receipts; preserve that limitation unless a verifiable replayable capture is added with backward compatibility.
3. Use native serialized scenario and historical results from BTC/ETH/SOL, captured config/model differences, hard market/engine mismatch, full vs short traces, multiple segments, source/license assertions and 0 fills. No data/network-dependent testing necessary.
4. Use regression tests to verify no writes to operational strategy, account, signer, risk, live SDK subscriptions, historical vault or PAPER ledger. Keep the existing worker and baseline behavior.
5. Do not create a Phase 16.5 comparison API or frontend until contracts are validated. Phase 16.5B may *display* individual metrics after 16.5A.2, but cannot derive directly comparable PnL deltas without a separately documented valid experimental design.
6. Report exact test failures and unchanged baseline static documentation failures; do not suppress or claim green without evidence.

**Current acceptance:** code and tests added through connected GitHub only. Native Python, full backend pytest, frontend and Chromium were **not run** for this A.1 implementation. This document is not proof of acceptance.
