# Audit 3.0 — Security & Data-Evidence Hardening

Base: `c05ab0b` (latest `main` when fetched). Validation recorded 2026-11-13 on Linux, Python 3.12.14, Node 24.19.0 and npm 11.9.0. `AUDIT_REPORT_3.0.md` remains the unchanged historical record.

## Dispositions and original reproductions

| Finding | Disposition | Before | After / committed regression |
|---|---|---|---|
| A3-001 | CLOSED | Actual MODELED_CROSSING order at 3001 for 0.1 crosses the mock ETH ask; telemetry says nonsimulated and simulated dataset construction fails. | The same actual adapter/book/order path retains `simulated=True` and creates one honest matured simulated sample. BASELINE also passes. Explicit TESTNET records remain nonsimulated, including a description starting with `SIMULATED`; contradictory copies fail before deduplication or telemetry eviction. |
| A3-003 | CLOSED | The audit's `perp_stale=True` plus one-day-old book counterexample produces READY/PREDICTED. | The corrected reproduction produces INSUFFICIENT_DATA/UNAVAILABLE, a fixed diagnostic and no probabilities. Independent book, perpetual and reference timestamp/flag tests cover stale, missing, future, inclusive boundaries and fresh recovery. |
| A3-008 | CLOSED for the reported dependency advisories | Lock installs Vite 7.3.6; audit reports one vulnerable direct dependency, HIGH aggregate, five advisories. | Manifest requires `^7.3.8`; clean `npm ci` resolves Vite 7.3.8. Actual `npm audit --json` reports zero vulnerabilities at every severity. Production build and local Chromium development workflows verified below. |

Before implementation, the two embedded Python reproductions were extracted from the report and run without changing their defect-detection assertions: **2 passed, 1 upstream warning, 0.61 s**. The new tests assert the corrected behavior, not those historical defective assertions. No exploit payload or signed venue order was sent.

## Root causes and contracts

A3-001 coupled simulation provenance to `source.startswith("SIMULATED")`; modeled PAPER uses a different human-readable label. `Fill.execution_mode` now has a bounded PAPER/TESTNET type; the actual PAPER producer explicitly sets PAPER. Telemetry derives its existing boolean from that field, never a free-form description. The model rejects mismatches between mode and reserved PAPER source labels. Unknown/venue descriptions without an explicit TESTNET mode fail closed. This is normalized evidence validation, not cryptographic authentication of externally supplied records; the existing trusted ingestion boundary remains necessary.

Legacy `Fill` was produced only by PAPER. Its omitted mode therefore continues to mean PAPER. The compatibility serializer omits that PAPER default and always retains TESTNET mode. This keeps existing PAPER fill wire bytes, accounting economics/fill identities and replay archives compatible. Telemetry explicitly revalidates mode even when serialization omits the default, catching forged `model_copy`/assignment before state changes. `FillObservation` validates its existing structured simulation flag against the same source/mode contract, including when the dataset builder revalidates copied inputs. Dataset classification checks were retained.

A3-003 checked required numeric values and future timestamps but ignored maximum age and stale flags. The canonical feature boundary now uses fixed, shared inclusive age limits: **book 5 seconds, perpetual 10 seconds, reference 30 seconds**. These follow the existing normal book/perp conventions and allow the existing 30-second public-HTTP reference fallback; stricter provider stale flags still reject. These are deterministic research admission caps, not operational configuration or quote-policy changes. No wall clock, timestamp fabrication or stale-value substitution is used.

Agent evidence now carries the actual perpetual timestamp and at most three eligible core providers' existing `PriceEvidence` records. Book metrics retain `book.timestamp`, so a fresh snapshot envelope cannot renew an old book. Reference validation checks provider identity, market, quorum availability, health/status/stale flags, and both receipt and source times. Missing, naive, future and over-age required timestamps are rejected relative to the actual `AgentEvidenceSnapshot.updated_at`; the prior optional perpetual-window no-future rule remains enforced.

Offline construction and inference call the same feature builder. Offline selection still uses the latest feature observation at or before the fill and first matured future label; the selected sources must additionally remain fresh at the fill's as-of time. It cannot reuse an indefinitely old feature vector or use a future feature. The canonical 12 normalized values, `passive-adverse-v1` schema, model hashes and valid fresh dataset fingerprints are unchanged. Old evidence lacking source timestamps cannot become eligible by inventing provenance: it is explicitly unavailable until valid evidence is supplied.

Known feature unavailability returns INSUFFICIENT_DATA/UNAVAILABLE with fixed public reasons. Malformed model/schema contracts still fail closed with the existing generic ERROR contract. Fresh evidence recovers without installing or promoting another model. SHADOW stays observational: neutral multipliers, `affects_quotes=False`, no ACTIVE/ADVISORY configuration, and exclusion from supervisor/authorization fingerprints. The runtime, final risk authorization, signing adapter and accounting/fee/funding formulas were not changed.

## REUSE / ENHANCE / ADD and exact files

- **REUSE:** existing PAPER engines, typed `FillObservation.simulated`, `PriceEvidence`, canonical feature vectors, artifact validation, dataset as-of selection, supervisor authority separation, terminal schema generator and browser workflows.
- **ENHANCE:** mode validation, telemetry ingestion, source provenance, feature admission, safe unavailable diagnostics, offline selected-feature freshness, generated terminal serialization compatibility and Vite patch floor.
- **ADD:** one focused regression module and this acceptance record. Existing feature fixtures now explicitly supply fresh source times; the existing missing-feature assertion expects the deliberate unavailable state.

Changed implementation and contract files:

- `backend/app/execution/models.py`
- `backend/app/execution/paper.py`
- `backend/app/agents/evidence.py`
- `backend/app/agents/models.py`
- `backend/app/agents/ml_features.py`
- `backend/app/agents/predictive_adverse_selection.py`
- `backend/app/research/ml/dataset.py`
- `backend/scripts/generate_terminal_contract.py`
- `backend/tests/test_agent_expansion.py`
- `backend/tests/test_audit3_security_evidence.py`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/src/contracts/terminal.schema.json`
- `frontend/tests/fixtures/terminal-valid.json`
- `docs/AUDIT3_SECURITY_EVIDENCE_ACCEPTANCE.md`
- `CHANGELOG.md`

The generated terminal schema accepts the additive provenance fields and preserves the optional PAPER default on serialized fills. Historical fixture evidence gets explicit null/empty unavailable provenance rather than fabricated source times. React, TypeScript, routing, charting, all other dependency versions, Vite configuration and development scripts are preserved; only Vite's lock entry changes. No force audit fix was used.

## Verification

Backend dependencies were installed in an isolated virtualenv with the existing `backend[test,redis,ml]` extras. Resolved versions include pytest 8.4.2, pytest-asyncio 0.26.0, Pydantic 2.14.3, FastAPI 0.162.5, Starlette 1.10.0, httpx 0.28.1, Redis 6.4.0, fakeredis 2.40.0, NumPy 2.5.4, scikit-learn 1.9.1 and the official Hyperliquid SDK 0.24.0. `pip check` reports no broken requirements. Playwright 1.65.1 and system Chromium are acceptance tools only, not project dependencies.

| Check | Actual final result |
|---|---|
| Corrected audit counterexamples / focused execution, modeled partial fills, telemetry, feature vectors, datasets, supervisor, risk/final authorization, simulation, accounting and generated contract suites | **527 passed, 0 skipped, 1 warning, 72.31 s** |
| Focused historical replay and portfolio research (`test_phase162_replay.py`, `test_phase173_integration.py`, `test_phase176_acceptance.py`) | **184 passed, 0 skipped, 1 warning, 67.84 s** |
| Full backend: `cd backend && python -m pytest -q` | **3,351 passed, 0 failed, 0 skipped, 2 warnings, 1,041.81 s (17:21)** |
| Optional ML coefficient-export acceptance, with existing `[ml]` extra installed | **1 passed, 0 skipped, 0 warnings, 6.94 s** |
| `npm ci` / `npm ls vite` | PASS; Vite **7.3.8**, clean install |
| `npm audit --json` | PASS (exit 0); info/low/moderate/high/critical/total all **0** |
| `npm run typecheck` | PASS |
| `npm run build` | PASS; existing bundle-size warning (chunk over 500 kB) |
| `npm test` | **788 passed, 0 failed, 0 skipped, 66.693 s** |
| Chromium Portfolio Research workflow | PASS: **19 workflows, 5 viewports (1920/1440/1024/768/390), 58 native engine runs**, 0 page errors, 0 unexpected console errors; 3 deliberate fault-console entries (429, connection refused, 500); operational authority unchanged |
| Chromium Dashboard / Agents / Simulation workflows | PASS: **72 route/viewport checks, 12 workflows**, Chromium **151.0.7922.173**; 0 page errors, 1 expected 422 console error from deliberately invalid settings. Includes real PAPER simulation, unchanged strategy configuration, start/manual kill/resume remaining stopped, keyboard navigation and mobile focus handling |

The focused command selects `test_audit3_security_evidence.py`, `test_agent_expansion.py`, `test_execution.py`, `test_phase163_execution.py`, `test_phase9_agents.py`, `test_phase9_runtime.py`, `test_phase8_risk_firewall.py`, `test_phase8_runtime.py`, `test_phase8_authorization.py`, `test_phase10_simulation.py`, `test_phase11_accounting.py` and `test_audit_terminal_contract.py`. The additional focused research command covers historical replay and portfolio integration/final acceptance; the full suite covers every existing backend test.

Baseline compatibility was captured on `c05ab0b` before implementation and compared byte-for-byte afterward. The committed regression freezes these independently captured values:

| Identity | Unchanged value |
|---|---|
| PAPER fill identity (`compatibility`, ETH BID 3000 × 1, 2001-01-01 UTC) | `36b22f733888bec5256f85648d59f9b44ef1b1023485d03e809177232ced7516` |
| Same fill accounting economics | `0634dbaa6aa4a35d9f63a2acba024bd7edd928d17b470704ce6bb97a1ce9917d` |
| Existing fresh offline dataset fixture | `11a2bff144784789e3d0ce5a9a1bc19d632ba0bca7409dcc81fba335886400bf` |
| 12-frame QUIET simulation run | `26bde070af4f2c759f78c792dfd27e3150c072c530eec28fadb4c892c80970e6` |
| Same simulation dataset | `b6c0db72a67b8c26ca3d9e115968945d4c3645819fa56a3ec242d32f4c2c9fbd` |
| Same simulation accounting | `0f63a3c967bb486ce134657ebe56856ce74beb77a42166b263270b56f4e5c20b` |

No engine or feature-schema version bump was needed. Prediction availability intentionally changes for stale/missing evidence, and corrected modeled-fill classification changes its telemetry label; these are the remediations, not changes to trade economics.

The two full-suite warnings were Starlette's existing `TestClient`/httpx deprecation and a Pydantic serializer warning from the intentionally forged `ConcentrationSelection` in `test_phase174_provenance.py::test_resealed_tampering_still_rejected[selection]`. The latter test passed by rejecting the tampering. Focused runs emitted only the Starlette warning; frontend tests and typecheck emitted no warnings.

## Limitations and intermediate failures

An initial full-backend attempt caught the not-yet-regenerated terminal schema (622 passed, one schema failure, interrupted at 97.28 s). The schema/fixture were updated and the final full run above uses the corrected contract. A subsequent preliminary run was interrupted for final no-future-window review (545 passed, 1 warning, 69.22 s); it is not counted as full-suite acceptance. An intermediate frontend run overlapped schema/fixture updates and failed; only the stable final run is reported above. The first Portfolio Research Chromium attempt timed out on a disabled stress button after Vite schema hot reloads during the run. Its successful earlier steps are not counted as a completed workflow; the stable rerun passed all 19 workflows. The older `browser-phase14.py` also stopped at its literal validation-message assertion after three successful Vault steps: the backend correctly returned 422 for negative capital, while the script expected unsanitized field-error text. That historical harness is not counted as PASS and was not changed; the existing terminal workflow separately checks the target routes, real simulation and operational PAPER controls.

Windows-specific advisory exploit conditions were not exercised on this Linux host; closure refers to the patched installed package and the actual current dependency audit. The build's existing bundle-size warning is not silently suppressed. PAPER crossing/partial fills remain hypothetical, and TESTNET classification tests use normalized fixture records, not independently authenticated real fills or signed trading. Optional ML verifies coefficient export/contracts, not calibration, profitable prediction or model promotion. No Python vulnerability-scanner result or cross-platform certification is claimed.

Other Audit 3.0 findings remain outside this PR. No deployment, infrastructure expansion, new model/agent/market/execution engine, credential handling, or automatic merge is introduced.
