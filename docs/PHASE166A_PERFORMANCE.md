# Phase 16.6A — Research Performance & Resource Efficiency (foundation)

**Status: implementation draft; native regression and profiling pending Codex validation.**

Base: `8b7d144a2f7ab51185ef608030619ad23bc345e6` (merged Phase 16.5D / PR #67). This work reuses the existing single-slot research executor and native replay/scenario/quantitative engines. No new HTTP endpoint, worker, database, trading control, dependency, or chart package.

## Evidence-based baseline

The prior [Phase 16.5D acceptance](PHASE165D_ACCEPTANCE.md) measured, on its own Linux environment:

| Historical / scenario frames | Worker time | Response | Cumulative process peak RSS |
| --- | ---: | ---: | ---: |
| 1,000 / 1,001 | 11.15 s | 405,414 bytes | 130.6 MiB |
| 4,999 / 5,000 | 59.45 s | 406,191 bytes | 288.7 MiB |

These are *previous* execution results, **not** evidence that the Phase 16.6A patch improves full-worker latency. Measured new timings must be collected in the same environment, using equal fixture/market/frames/mode and repeated trials before any optimization percentage is claimed. Worker time includes serial replay, scenario, comparison receipt validation and bounded transport. RSS numbers are Linux cumulative high-water marks, not independent per-run allocations.

## REUSE / ENHANCE / ADD

**REUSE**:
- `SimulationExecutor`, `SimulationService`, `SimulationEngine`, `HistoricalReplayResult`, `ReplaySegmentResult`, `SimulationResult`, existing `canonical_json` and `stable_fingerprint` utilities.
- Phase 16.5D `bounded_dataset`, native test fixtures and performance bounds.
- `HistoryChart`, `SimulationTrace`, `boundedObservations`, `seriesCoordinates`, `Lightweight Charts` and current chart test harness.

**ENHANCE**:
- `backend/app/research_replay/runner.py`: `archive_wire_and_fingerprint(result)` emits the exact same canonical JSON archive and SHA-256 fingerprint **from a single `model_dump(mode="json")` payload**. Removes production `json.loads(archive)` round trips after serialization for both modeled and baseline archives. Existing Pydantic archive validators **still independently re-read and verify** each archive; no security, receipt validation or immutable evidence gate is skipped.
- `frontend/src/utils/terminalHistory.ts`: `chartObservationIndex` maps frame sequence or already-bounded latest-per-second observation once per React data revision.
- `frontend/src/components/HistoryChart.tsx`: `useMemo` caches the hover index and per-line coordinate projections when source points/axis/lines change, avoiding full-array scans and repeated plot derivation from tooltip-only rerenders. Lookup continues preserving the latest observation per frame/time key, gap/null markers, exact source point sequence and original timestamp for inspection. Economic Decimal values are still displayed/handled by existing utilities; browser float coordinates are chart-only.

**ADD**:
- `backend/tests/test_phase166a_archive.py`: actual deterministic BTC/ETH/SOL scenario/replay receipts, modeled/baseline archive bytes, legacy hash equality, Pydantic round-trip and nonmutation.
- `frontend/tests/phase166a-history-performance.test.cjs`: lookup parity with prior scanning semantics, same-second microsecond frames, duplicate sequences, missing values, and disconnected chart segments.
- `backend/tests/phase166a_profile.py`: optional single-worker fixture profiler, stage timings for replay/scenario/quantitative/archive work, response bytes, RSS high-water mark, archive microbenchmark with exact wire/hash assertions. This profiler patches methods **only inside the profiling process** and restores originals; does not change application/runtime logging or reporting.
- Existing `frontend/tests/run.cjs` includes the new frontend regression cases.

## Verify before merge

Use Python 3.12+ with existing repository test extras and Node/npm from existing lockfile:

```bash
cd backend
python -m pytest tests/test_phase166a_archive.py \
  tests/test_phase165d_acceptance.py tests/test_phase165c2_integration.py \
  tests/test_phase165b_quantitative.py tests/test_phase1641_acceptance.py -q
python -m pytest tests -q -rs

cd ../frontend
npm ci
npm run typecheck
npm run build
npm test
```

Then run the **optional** Python profiler in the native environment:

```bash
cd ..
PYTHONPATH=backend:backend/tests backend/.venv/bin/python \
  backend/tests/phase166a_profile.py --frames 128 --output work/phase166a-128.json
PYTHONPATH=backend:backend/tests backend/.venv/bin/python \
  backend/tests/phase166a_profile.py --frames 1000 --output work/phase166a-1000.json
```

Compare with a clean checkout of the exact base in identical environment and fixtures. Prefer medians of several independent runs, with warm/cold status recorded. Report speed and memory improvements only if measurements actually support them. If a candidate is slower or changes exact archives, rollback that candidate. The existing Phase 16.5D `backend/tests/phase165d_performance.py` remains the authoritative near-limit stress acceptance harness.

## Codex 16.6A.2 integration and acceptance gates

1. Run native tests **before modifying the implementation**; fix any import, typecheck, fixture or chart semantic issue found. Do not change assertions to make failing behavior pass.
2. Verify exact replay archive bytes, fingerprints, result metrics, execution assumptions, baseline sensitivity results, risk state and per-segment reset identity for BTC/ETH/SOL, baseline and modeled PAPER.
3. Benchmark 128/1,000 frames and, when practical, a near-limit 4,999 historical/5,000 scenario run versus untouched base. Decompose wall-clock into replay/scenario/receipt/archive, do not assume an archive micro-optimization accelerates all engine work.
4. Run Chromium replays and comparison charts at 390/768/1024/1440/1920 widths. Verify missing-value gaps, same-second frames, source timestamps, fitted scale and hover exact-value inspection. No fabricated samples, stitched equity curves, or client-derived PnL.
5. Profile deeper repeat hot paths (per-frame accounting/risk/order processing, multiple independent archive revalidations) **before** a second optimization. Never bypass receipt validators, alter canonical encoding, suppress source identity checks or introduce identity-sensitive mutable caches.
6. Report full backend/frontend tests, browser evidence, any warnings, worker capacity/cancellation, operational strategy/ledger/risk/signer isolation. Existing Phase 16.5D local acceptance is the baseline; new optional test skip or external venue gates remain separately labeled.
7. Create `docs/PHASE166A_ACCEPTANCE.md` with actual before/after timing distributions, RSS/response sizes, identity parity and PASS/FAIL/BLOCKED/NOT RUN gates. No false latency improvement claims.

## Boundaries

- Same source and engine identity, same Decimal and canonical fingerprint semantics, same PAPER research outcome.
- No changes to trading authority, risk authorization, live streams, signer, wallet, order execution, market-data ingestion or concurrency admission.
- No Docker, CI workflow, Kubernetes, new dependency, second worker, persistent cache, or simulation engine.
- The frontend chart index is a **presentation-only** optimization; source-time bucketing must not infer authenticated exchange time or connect independent replay segments.
- **Current implementation was authored through GitHub connector. Native Python/Node and Chromium tests and new performance trials have NOT RUN. Do not merge without validation.**
