# Phase 16.5A.2 — Comparison Provenance Integration & Native Acceptance

Native acceptance performed November 11, 2026, using the existing HyperAMM backend. This is an integration and contract-hardening change. It adds no quantitative comparison engine, frontend, market ingestion, execution authority or research scheduler.

## Revision and environment

- Repository: `btorressz/hyperamm`.
- Initial/latest fetched `main`: `9d60af3` (merge of PR #62, containing A.1 commit `5cc44b1`). The initial checkout was older; it was updated before installation, baseline execution or implementation.
- Focused branch: `phase16/16-5a2-comparison-provenance`, created from `origin/main`.
- Final implementation commit tested: `2ee5086c6effb2ec9fa91d34d03b05d8d5d2061f`. Subsequent changes in this PR only record acceptance and update the two documents listed below. The draft PR records its final branch-head commit separately, avoiding a self-referential documentation hash.
- Python 3.12.14; Pydantic 2.14.3; pytest 8.4.2; pytest-asyncio 0.26.0; FastAPI 0.162.4; Redis client 6.4.0; fakeredis 2.40.0.
- Existing dependencies installed in `backend/.venv` using `python3.12 -m venv backend/.venv` and `backend/.venv/bin/python -m pip install -e 'backend[test,redis]'` from the repository root. `python -m pip check` reported **No broken requirements found**.
- No new dependencies, deployment infrastructure or CI configuration.

## Exact changed files

| File | Change |
| --- | --- |
| `backend/app/simulation/service.py` | Validate/adapt effective inputs; resolve Vault and accounting capital; freeze canonical capture; execute the existing engine from those inputs; optionally return the bound receipt. |
| `backend/app/simulation/executor.py` | Deep-copy inputs at existing one-slot admission, including direct executor callers. Preserve shielding, completion callback, cancellation and shutdown. |
| `backend/app/api/simulation.py` | Strict opt-in `include_comparison_provenance` on the existing scenario route; attach Vault provenance in the worker before hashing. |
| `backend/app/research_replay/comparison.py` | Reuse A.1 snapshots/sides/foundation; add minimal frozen scenario receipt/response contracts; verify strict normalized captures, profile identity, comparison claims and historical request/segment evidence. |
| `backend/tests/test_phase165a2_integration.py` | 70 native integration, compatibility, corruption, concurrency and isolation cases. |
| `docs/PHASE165A2_ACCEPTANCE.md` | This acceptance record. |
| `docs/PHASE165A1_COMPARISON_CONTRACTS.md` | Document the integrated opt-in handoff, stronger validation and unchanged evidence limits. |
| `CHANGELOG.md` | Concise unreleased A.2 entry. |

The existing engine, optimizer, historical runner/storage/importer/adapter, PAPER execution, firewall, accounting, model fingerprint utilities and frontend are reused. Existing A.1 tests and historical result wire contracts are unchanged.

## Untouched native baseline

The following ran on `9d60af3` before any repository changes:

```bash
cd backend
.venv/bin/python -m pip check
.venv/bin/python -m pytest \
  tests/test_phase165a1_contracts.py \
  tests/test_phase1641_acceptance.py \
  tests/test_phase162_replay.py \
  tests/test_phase163_execution.py -q
.venv/bin/python -m pytest tests -q -rs
```

| Baseline | Actual result |
| --- | --- |
| Dependency validation | PASS; no broken requirements |
| Focused predecessor suites | **210 passed**, one warning, 37.26 seconds |
| Entire backend | **2,271 passed, 3 failed, 1 skipped**, one warning, 111.01 seconds |

The baseline full suite was not green. All three failures are static documentation checks whose only reported hit is the existing `docs/PHASE155B_ACCEPTANCE.md`:

- `tests/test_phase10_static.py::test_no_github_actions_or_forbidden_oracle_added`
- `tests/test_phase8_static.py::test_repository_contains_no_forbidden_oracle_provider_token`
- `tests/test_phase9_static.py::test_phase9_does_not_create_github_actions_or_forbidden_oracle`

Those files/assertions were not altered or suppressed. The optional skip is `tests/test_agent_expansion.py:406`, whose optional ML dependency is absent. The warning is the installed Starlette/httpx TestClient deprecation. No additional dependency was introduced to hide either.

## Capture lifecycle and evidence limits

1. The existing HTTP route resolves the selected read-only research market profile, then copies operational strategy, agents and risk without an intervening await. No runtime object, signer, operational accounting service or order manager enters the worker.
2. The existing local executor detaches the complete input payload when its one-slot admission succeeds. The Redis coordinator continues to use its existing lease and result mirror; there is no new operation, queue or pool.
3. Inside `SimulationService.run_scenario`, research proposals are copied/revalidated and converted using the existing Vault configuration. Strategy is validated and normalized using the existing market adapter and forced to DEMO/PAPER.
4. Effective simulation accounting includes the engine's override of `accounting.paper_initial_equity_quote` with `simulation.initial_equity_quote`. Capturing both consistently prevents attesting an unused accounting default as the effective starting capital.
5. `ScenarioInputCapture` revalidates and detaches all five existing configuration domains. `ComparisonConfigSnapshot` freezes their complete normalized canonical JSON and existing per-domain fingerprints before dataset generation and computation.
6. Engine inputs are reconstructed from that immutable snapshot. The existing deterministic generator and `SimulationEngine.run` consume exactly those captured inputs. No live configuration is read after completion.
7. If requested, Vault provenance is attached before the result is hashed. `ScenarioProvenanceReceipt` binds the requested scenario/frame count, captured snapshot, engine version, dataset/run identities and full native result hash. Its own fingerprint covers all receipt fields. `CapturedScenarioResult` validates the result against that receipt.
8. Comparison assembly accepts `scenario_provenance=receipt`, verifies the result binding and derives the scenario capture from it. An additional supplied `scenario_inputs` must equal the bound snapshot. Legacy caller-only captures remain supported at their original evidence strength.

The receipt and canonical snapshot are immutable Pydantic evidence. The existing `SimulationResult` remains mutable for compatibility; any mutation is detected when its original receipt is verified or its wrapper is reparsed. The wrapper does not claim deep immutability of existing result lists or metrics.

**This is service binding, not independent engine authentication or a cryptographic signature.** `input_capture_engine_attested=false` and `SCENARIO_INPUT_CAPTURE_NOT_ENGINE_ATTESTED` remain explicit. A legacy caller-only capture cannot independently prove agent/risk inputs. Rewriting a complete archive and all of its hashes together does not establish authenticity. There is no secret attestation key or persisted trusted receipt registry.

## Identified defects and hardening

The initial focused contracts compiled and passed natively; no import/test-fixture repair to A.1 was needed. Integration exposed or confirmed these gaps:

- Scenario results had no same-job effective configuration receipt; post-run caller captures could substitute agents/risk without an independent binding. The opt-in service receipt now detects substitutions against the original admitted receipt.
- Local executor inputs could alias mutable objects supplied by direct callers. Admission now deep-copies them; occupied-worker tests mutate the originals before service capture and verify the original admitted values.
- Simulation accounting capital may differ from its configured default before the engine overrides it. Capture now resolves this effective value first, without changing engine economics or mutating the caller's configuration.
- Existing operational Strategy/Risk validators can ignore unknown fields or coerce values. Capture validation now requires complete normalized JSON, strict existing model validation and closed fields. Unexpected fields/types, coerced booleans, financial floats and invalid `model_copy` payloads fail closed.
- A supplied profile fingerprint was previously treated as a label. Capture now reconstructs existing semantic profile identity from metadata, version and fixed reference anchor and checks market/precision compatibility.
- A self-consistent comparison hash could otherwise cover false classification/dimension/reason claims. Deserialization now derives them from the actual sides and preserves required limitations; `ALIGNED` is still rejected.
- Rehashed historical requests could otherwise diverge from captured accounting, frame/trace controls, precision or metadata. Assembly checks them against the captured simulation/profile and checks original dataset identity against provenance.
- A substituted selected segment dataset could otherwise be rehashed together with its archive. The existing adapter now reconstructs the engine dataset from retained segment receipts and verifies that fingerprint. The original historical dataset fingerprint remains intentionally different from the engine segment fingerprint.

All fingerprint arithmetic uses the existing canonical utilities and Python Decimal. Execution settings retain their existing exact Decimal rules. Accounting, execution and display/retention fingerprints remain separate.

## Native integration matrix

Each comparison generated by the integration helpers is serialized with `model_dump_json` and revalidated with `ComparisonFoundation.model_validate_json`. Native historical archives, snapshots and the opt-in wrapper/receipt are also round-tripped. Secure historical admission uses the existing explicit importer and private vault, followed by the real `SimulationService.replay_history`; scenarios use the real `SimulationService.run_scenario` and engine.

| Requested acceptance case | Disposition / observed behavior |
| --- | --- |
| BTC scenario / BTC replay | PASS — `CONTEXT_ONLY`; same configuration dimensions can match; original/segment dataset identities differ. |
| ETH scenario / ETH replay | PASS — same behavior; real serialized engine/replay results. |
| SOL scenario / SOL replay | PASS — same behavior; real serialized engine/replay results. |
| BTC scenario / ETH replay | PASS — `INCOMPARABLE`, `MARKET_MISMATCH`. |
| Matching strategy, differing risk | PASS — `RISK_MISMATCH`; no direct deltas. |
| Matching market, differing agents | PASS — `AGENTS_MISMATCH`; strategy may still match. |
| Differing capital/accounting | PASS — fees, funding, utilization and starting capital captured; `ACCOUNTING_MISMATCH`. |
| Baseline scenario / modeled replay | PASS — existing latency/depth execution assumptions preserved; `EXECUTION_MISMATCH`. |
| Matching/differing profiles | PASS — exact profile matches; changed metadata identity reported; inconsistent profile hashes/markets rejected. |
| Explicit gaps / independent segments | PASS — gap and observer-generation cases; selected segment window/index retained; each segment starts with its own capital. |
| Zero hypothetical fills | PASS — default historical runs preserve zero-fill output; no invented metrics. |
| Complete scenario trace | PASS — `TRACE_COMPLETE` only with every increasing timestamp/sequence retained. |
| Truncated scenario trace | PASS — window `UNKNOWN`. |
| Disabled scenario trace | PASS — window `UNKNOWN`; zero trace-capacity case covered too. |
| Forged scenario capture | PASS — agent/risk/control/capital substitutions rejected against the original receipt; malformed snapshots and invalid copied models rejected. |
| Forged historical result/segment | PASS — corrupted archives/identities rejected, including rehashed request/accounting/precision/origin/segment substitutions. |
| Altered engine version | PASS — bound archive rejected; legacy unbound version mismatch classified `INCOMPARABLE`. |
| Configuration changes while occupied | PASS — HTTP and direct-worker cases preserve admitted inputs; cancelled waiters retain admission until completion. |

All valid foundations keep `direct_metric_deltas_allowed=false`, `cross_segment_aggregation_allowed=false` and `matched_market_evidence_verified=false`. No combined PnL/equity, ranking or financial delta between scenario and historical evidence was added.

Recorded-native labels in these controlled generated fixtures are user assertions. These tests prove actual local services and serialized results, not genuine exchange recording, independent licensing, continuous historical coverage, verified context source event time, real passive fills or paired market conditions. Complete scenario traces and historical receipt windows do not establish temporal alignment. No market data was fetched for acceptance.

## Worker, API and operational isolation

- **PASS:** No extra executor operation, thread pool or queue. Existing busy admission rejects scenario, replay, optimization and catalog work while occupied. Cancelled HTTP waiters do not release capacity early; shutdown waits for actual completion and terminates the existing pool.
- **PASS:** Existing Redis coordinator mirrors the complete bound wrapper and retains its existing job/result lifecycle.
- **PASS:** Existing default HTTP result equals the opt-in wrapper's `result` for BTC/ETH/SOL, both with and without custom Vault proposals. Strict boolean opt-in rejects strings. Existing scenario, optimizer, market-profile and Vault tests remain applicable.
- **PASS:** TESTNET/LIVE strategy configuration is copied/adapted to selected DEMO/PAPER research before capture; operational input objects remain unchanged.
- **PASS:** Seeded operational PAPER fills/ledger/orders, reservations, selected strategy market, agent/risk configuration, kill-switch states, execution identity and TESTNET signer configuration remain unchanged. Exact before/after tests use manually refreshed operational state with `strategy.running=true`, both with and without the kill switch; they do not claim a continuously running real venue strategy.
- **PASS:** Active Phase 15 SDK fixture subscriptions, connection generation, handles, snapshots and subscriber queues remain intact and continue receiving observations after research.
- **PASS:** Admitted historical file contents remain byte-identical during provenance assembly/HTTP scenario work.

No raw historical dataset export, operational write, signing call, auto-deployment or comparison endpoint was introduced.

## Final native regression

Final commands and completed native results are recorded below. The full suite is **NOT GREEN** because the same three baseline documentation checks still fail; there are no newly failing backend tests. Frontend files are untouched; npm/typecheck/build/frontend tests and Chromium are **NOT RUN for A.2**, as this phase adds no frontend behavior and the request does not require a new browser suite.

| Gate | Final result |
| --- | --- |
| New A.2 integration cases | PASS — 70 native cases, included in focused/full runs. |
| A.1 plus A.2 contract/integration run | PASS — 81 passed, one warning, 6.97 seconds. |
| Required focused predecessor suites plus A.2 | PASS — **280 passed**, one warning, 42.04 seconds. |
| Scenario/executor/accounting/Vault/profile compatibility run | PASS — **277 passed**, one warning, 17.39 seconds; before the final five historical substitution cases were added. The full final run includes those cases too. |
| Entire final backend | **FAIL — 2,341 passed, 3 failed, 1 skipped**, one warning, 115.88 seconds. All three failures match the untouched baseline. |
| Full-suite baseline failure comparison | PASS — the same three identifiers listed above and the same sole documentation hit; 70 additional passes, no new failures. The optional skip and warning are unchanged. |
| `git diff --check` | PASS. |
| Frontend / Chromium | NOT RUN — untouched frontend and no new comparison UI. |
| Independent scenario engine attestation | BLOCKED / explicitly limited — existing result does not independently authenticate every input; receipt does not claim otherwise. |
| `ALIGNED` / direct financial deltas | BLOCKED by absent paired economic evidence; reserved future design, never emitted. |
| Phase 16.5B provenance handoff | PASS for original service-bound scenario receipts and independent replay segments; a full comparison API and UI are NOT RUN / out of scope. |

The final focused command, from the repository root:

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_phase165a2_integration.py \
  backend/tests/test_phase165a1_contracts.py \
  backend/tests/test_phase1641_acceptance.py \
  backend/tests/test_phase162_replay.py \
  backend/tests/test_phase163_execution.py -q
```

The compatibility command used `backend/.venv/bin/python -m pytest` with `test_phase10_api.py`, `test_phase10_executor.py`, `test_phase10_simulation.py`, `test_phase11_simulation.py`, `test_phase14_research_vault.py`, `test_phase146_research_markets.py` and `test_phase165a2_integration.py`, all under `backend/tests/`, followed by `-q`. Final full regression uses `.venv/bin/python -m pytest tests -q -rs` from `backend/`.

Phase 16.5B should consume the original bound scenario receipt, revalidate it alongside the result, and select individual historical replay segments. Matching configuration remains context only. It must not infer paired timestamps, direct performance deltas, aggregation across gaps or trading authority. Full-suite baseline failures remain visible for repository owners; this PR is draft and must not be merged automatically.
