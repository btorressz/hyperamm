# Phase 16.4 — Historical Replay Studio (draft acceptance)

Base: main at `3a42fc8873896734931fe8470127a1e136eda851` (merged PR #59).

## Scope: ADD / ENHANCE / REUSE

- **ADD** bounded `HistoricalDatasetSummary` and GET `/api/v1/historical-replay/dataset-summaries`. Uses the existing `HistoricalStorage` read checks and single-slot `SimulationExecutor`; no importer, filesystem creation, upload, delete, raw historical dataset endpoint, or new worker.
- **ADD** React `components/replay/` workspace and Phase 16.4 CSS, exact wire types in `types/replay.ts`, defensive response handling in `utils/replayEvidence.ts`.
- **ENHANCE** `pages/Simulation.tsx`, `api/client.ts` and offline render availability through `App.tsx`. Original scenario/optimizer interfaces remain intact.
- **REUSE** `HistoryChart`, `SimulationPanel`, `SimulationTrace`, terminal panels and formatting, existing research policies, `SimulationEngine`, PAPER adapter, read-only replay APIs, fingerprints and Phase 16.3 baseline/model comparison archives.

## UX behavior and authority

- Dataset picker displays the actual validated market, receipt window, source kind, gap and observation counts, and dataset fingerprint; never promotes user-asserted recorded source/licensing to authenticated or complete.
- A selected dataset's existing provenance must match before POST. UI can run the existing Phase 16.2 replay API with bounded Phase 16.3 assumptions: precision, max frames, as-of pairing, receipt interval, crossing model, latency, slippage, participation, retained depth and partial fills. No trading or deployment endpoints.
- Playback is read-only browser navigation over original segment frames (not a market feed), with no chart interpolation across segments. Each segment retains independent simulation capital, orders, risk, fills and accounting; do not show a combined return.
- The selected segment alone is decoded from the existing canonical `simulation_result_json` result archive. Modeled crossing reads the backend's already-computed baseline archive and displayed delta. Missing market or result evidence stays unavailable.
- UI reports explicit gaps, excluded evidence, source timestamp uncertainty, user-model assumptions and fingerprints.
- 429 and 503 are presented as shared worker busy and disabled storage/unavailable admission; 422 structured rejections show missing-economics reasons where provided. No backend exceptions/raw path/provider wire data are echoed.

## Security and acceptance limits

- The added metadata route uses the existing local-only HTTP middleware, `Cache-Control: no-store`, worker admission and disabled `HISTORICAL_REPLAY_ROOT` behavior; it does not expose unbounded raw L2 or stored financial observations.
- The dataset summary records are bounded to the existing maximum 256 datasets, reuse storage read-back validation and expose only market/coverage/source kind/identity/counts.
- UI response validation is a display guard, **not independent cryptographic fingerprint verification**. The backend validates source/result fingerprints and source assertions as in Phase 16.1–16.3.
- Source recording identity, licensing, latency and fills remain unverified. No actual queue priority, passive fill, live-provider validation, profitability prediction, full continuous coverage or real settlement is claimed.
- No new dependencies, Docker, GitHub Actions, alternate state manager, jobs, scheduler or local dataset upload.

## Test additions and required acceptance

- `backend/tests/test_phase164_catalog.py`: catalog identity, restricted metadata, executor reuse and storage corruption/permission rejection.
- `frontend/tests/phase164-replay.test.cjs`: summary bounds, provenance match, model input limits and malformed archive/replay rejection.
- `frontend/tests/run.cjs` now includes the replay utility compilation and focused test.

**Not executed in this connector-only checkout:** native Python/Node tests, TypeScript compile, Vite build, Chromium browser acceptance and complete regression suites. These must be executed independently before merge. The last merged backend PR #59 reported 2,244 passing, 3 pre-existing static documentation checks failing and 1 optional skip; those counts are **not** validation results for this PR.

### Required verification

From `backend/`, run actual dependency-backed `pytest tests/test_phase164_catalog.py tests/test_phase163_execution.py tests/test_phase162_replay.py tests/test_phase161b_importers.py tests/test_phase161a_contracts.py -q`, followed by full `pytest tests -q -rs`.

From `frontend/`, run `npm run typecheck`, `npm run build`, `npm test`. Run actual Chromium navigation, dataset summary/provenance, selection changes, replay submission, baseline/model comparison, zero fills, a segmented/gapped capture, error/429/503, mobile and no-terminal access. Confirm old Simulation/Vault/Markets pages still work and that no live trading state is modified.

**DRAFT. DO NOT MERGE AUTOMATICALLY.**
