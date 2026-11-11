# Phase 16.6C.1 — Research UX, Diagnostics & Local Release Documentation

**Scope:** read-only React UX and truthful local operator documentation on top of the merged Phase 16.6A.2 implementation. **Status:** implementation committed; native TypeScript, Node, browser and backend acceptance must be run in Phase 16.6C.2.

## Reuse and changes

Existing `HistoricalReplayWorkspace`, `ScenarioReplayComparisonWorkspace`, `ReplayDatasetSelector`, `ReplayExecutionAssumptions`, `StatusBanner`, FastAPI validation/response codes, React Query and the shared research executor remain unchanged in architecture. No new HTTP endpoint, polling, job records, progress socket, Redis dependency, execution adapter, charting package, library, operational authority or financial math was introduced.

Added `frontend/src/utils/researchStatus.ts` with bounded, generic presentation-only diagnostic classifications and the request/preflight summary. Added `components/research/ResearchRunStatus.tsx`, `ResearchDiagnostics.tsx`, and `ResearchWorkloadPreview.tsx` to render state, recovery guidance and source-derived workload metadata. These are used by **both** existing research workspaces. The dataset selector now shows the admitted observation count, gap-related disclaimer and catalog total. The new `phase166c.css` uses the existing dark terminal palette, scoped responsive styles and accessible status/alert roles.

The research preview takes **existing validated catalog summaries and user-entered request bounds**. It displays market, frame ceilings (not viable frames), declared gaps, observation count, source label, coverage quality, PAPER model, and shared-slot policy. A request of 1,000 frames or more is labeled potentially long, **not** assigned a predicted duration. The number of admitted observations does not guarantee usable historical frames; the number of gaps does not guarantee a particular number of replay segments.

`frontend/tests/phase166c1-research-ux.test.cjs` covers bounded frame inputs, larger workloads, missing and unknown metadata, gap disclosure, all existing HTTP categories and credential-safe diagnostic messaging; `frontend/tests/run.cjs` registers it.

## Meaning of the status panel

- **Idle:** No current submitted or completed request (no status banner).
- **Running:** A browser request was submitted; this **does not prove** engine-frame progress or reserve a backend worker if the request is still being admitted.
- **Complete:** The frontend accepted a validated result for the current inputs. It is a PAPER result, not live execution.
- **Retired:** Current input, selected segment or session does not match the captured result. Existing identity/epoch guards continue to hide financial evidence.
- **Error:** Research response was not accepted; diagnostic guidance follows. Backend work may still be active after cancellation or connection loss.

No progress percentage, estimated completion time, cancellation guarantee, successful fills or new simulated samples are invented. The frontend does not query a new server status endpoint or poll to guess execution state.

## Local research runbook

HyperAMM is currently **local/single-operator** research software. Public/LAN deployment is not supported and `CORS` is not authentication. Use only the existing loopback backend and frontend configuration.

### Prepare backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The repository's existing development `--reload` option may be used locally, but restarts retire in-flight browser evidence and an active worker's lifecycle must be handled by the backend. See `backend/README.md` for existing deployment restrictions.

### Configure a private historical vault (optional)

Historical replay is disabled until `HISTORICAL_REPLAY_ROOT` points to a **trusted absolute local POSIX path** owned by the backend user with restrictive permissions on its ancestors. Refer to the root `README.md` for configuration and admission instructions. Creating a directory or setting a variable **does not import datasets**. Trusted operator-side admission uses existing secure importer/storage APIs; there is no web uploader or authenticated exchange archive.

No dataset: the catalog is empty and no replay can be launched. Missing/unavailable storage: 503 and an actionable local diagnostic.

### Start frontend

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Visit the existing Simulation & Optimization page and switch between **Historical Replay** and **Scenario vs Historical**. Use the existing preflight preview to inspect requested limits and coverage before submission. Vite proxy/port settings remain as already configured in the repository.

### Interpret errors

| Condition | Current browser action | Backend/evidence implication |
| --- | --- | --- |
| Busy / 429 | Wait until existing job completes, submit again once | Shared one-slot computation is occupied; browser cancellation does not free it |
| Unavailable / 503 | Verify loopback backend, historical root, local admission configuration; refresh metadata | Missing storage or research coordination cannot be bypassed by frontend |
| Invalid / 422 | Review selected dataset, market, fingerprints, frame bounds and modeled execution | Fail-closed validation, no replacement synthetic data |
| Too large / 413 or response budget | Reduce requests and honor the response budget | Never bypass bounded source or archive validation |
| Disconnected browser | Verify backend and refresh the catalog/provenance before resubmitting | Detached computation may still run; outcome cannot be inferred |
| Retired input/session | Revalidate and submit a new request | Old results remain historical; no stale financial rendering |
| Internal / 500 | Inspect sanitized **local** backend diagnostics | Do not expose stack traces, paths, credentials or provider payloads in UI |

Use the existing `GET /health` if needed for general backend market/Redis status. It is **not** a per-job research progress endpoint and does not certify historical storage or job completion. When a user refreshes a catalog while another research job runs, existing metadata-only retry rules may apply; computation POSTs are not automatically retried.

### Limits and provenance

- Up to 5,000 requested scenario frames and 5,000 historical frames; these are ceilings, not promised viable frame counts.
- At most 32 independent replay segments under existing contracts. Gaps/invalid observations can exclude data; each segment resets capital, risk, inventory, and orders.
- One admitted research computation at a time; no client-side queue or new background worker.
- Scenario vs historical evidence remains CONTEXT_ONLY or INCOMPARABLE as applicable. No direct performance delta, paired-equivalence inference, strategy ranking, or cross-gap returns.
- Recorded-native source labels remain operator assertions. Source authenticity, licensing, venue fills, external Redis acceptance, macOS delivery and live trading authorization are separate acceptance gates.

## Native/Chromium handoff — Phase 16.6C.2

Run actual:
```bash
cd frontend
npm ci
npm run typecheck
npm run build
npm test

cd ../backend
python -m pytest tests -q -rs
```

Extend existing Chromium workflows to check the preflight/status UI on 390/768/1024/1440/1920px, 422/429/503/connection errors, missing catalog, 1,000/5,000 frame preflight, modeled PAPER selection, disconnected/gapped evidence, cancelled client waiter, stale response retirement, keyboard access and no console errors. Validate local startup/shutdown/storage/Redis optional vs required semantics in the native environment. Do not imply an ETA or active cancellation support.

Keep acceptance evidence concise: Markdown summary, compact machine-readable result status and a few relevant real browser screenshots, not tens of thousands of committed profiler/log lines. If Phase 16.6B introduces real lifecycle status, **reuse** its authoritative status contract rather than constructing a duplicate frontend tracker.
