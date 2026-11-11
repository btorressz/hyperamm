# HyperAMM — FastAPI API Layer

> **API source/ownership guide · updated November 5, 2026 · through merged Phase 16.4 (PR #60).** This package is a thin HTTP/WebSocket transport layer, **not** a second AMM, simulator, market data authority or order execution engine. A merged phase is not necessarily fully accepted; see [Phase 16.4 acceptance](../../../docs/PHASE164_ACCEPTANCE.md).

## Application wiring and boundaries

[`app/main.py`](../main.py) creates **one** `HyperAmmRuntime`, **one** `SimulationExecutor` and the separate Phase 15 read-only market observation service in the FastAPI lifespan. The executor can be wrapped by optional Redis research admission/coordination, but Redis does not replace the local research worker, strategy engine, ledger, or risk authority. Routers delegate into these existing owners; they do not instantiate new execution or research systems.

- REST routes are mounted under the configured `/api/v1` prefix (`Settings.api_prefix`). The primary operational terminal WebSocket is **`/ws/terminal`**, and Phase 15's native-market observation WebSocket is **`/ws/live-markets/{market}`**; neither WebSocket is an `/api/v1` path.
- `app.dependencies.runtime()` retrieves the lifespan-owned operational runtime. Research routes invoke `request.app.state.simulation_executor`; **they never directly mutate the operational strategy, risk settings, signer or orders**.
- Operational market evidence (`market_data/` plus strategy/risk) differs from opt-in, independent read-only public Hyperliquid observation (`market_data/live_*`) and from *operator-admitted local* historical PAPER replay (`research_replay/`). All three paths must remain isolated.
- The API is for **local, loopback-only, single-operator use**, not authenticated public multi-tenant or remotely exposed access. [`deployment.py`](../deployment.py) enforces local Host/peer/origin and single-worker limits; CORS is **not** user authentication. Credentials remain on the backend.

## Router ownership

| Router file | API responsibility | State/economic authority |
| --- | --- | --- |
| [`health.py`](health.py) | Health summary and operational readiness | Read-only observation |
| [`markets.py`](markets.py) | Operational normalized market/book reads | Read-only; operational market owned by runtime |
| [`strategy.py`](strategy.py) | Approved strategy config, start/stop, AMM/market/perp views | Mutations delegate to runtime validation/locks |
| [`positions.py`](positions.py) | Inventory/position evidence | Read-only |
| [`orders.py`](orders.py) | Existing order/fill views | Read-only; no browser order submit endpoint |
| [`risk.py`](risk.py) | Risk state/evidence/authorization and explicit manual kill/resume | Kill/resume use runtime-controlled authority |
| [`agents.py`](agents.py) | Supervisory-agent evidence and events | Read-only; agent advice cannot bypass risk |
| [`simulation.py`](simulation.py) | Deterministic scenario runs and bounded grid optimization | Shared isolated PAPER research executor |
| [`research_markets.py`](research_markets.py) | BTC/ETH/SOL single-native-perp research market metadata | Read-only selection; never operational market switching |
| [`research_vault.py`](research_vault.py) | Bounded research presets, proposal preview and controlled comparisons; request body admission | Research-only; no strategy auto-application |
| [`research_market_comparison.py`](research_market_comparison.py) | Phase 15 observed-market vs simulated-research comparison | Computational read-only result, no execution |
| [`live_markets.py`](live_markets.py) | Phase 15 native BTC/ETH/SOL overview, snapshots, stream state, bounded history, provider health | Independent read-only public observation |
| [`live_market_streams.py`](live_market_streams.py) | Phase 15 independent `/ws/live-markets/{market}` stream | Observation-only; no signer or trade permissions |
| [`historical_replay.py`](historical_replay.py) | Phase 16 bounded local dataset IDs, summaries, provenance, and receipt-ordered PAPER replay | **No** browser import, save/delete, raw dataset download, live order or deployment |
| [`accounting.py`](accounting.py) | Vault/PnL/positions/ledger/events reads | Read-only; accounting truth is in `accounting/` |
| [`terminal.py`](terminal.py) | Bounded current-session terminal history/events | Read-only; not a historical exchange archive |
| [`websocket.py`](websocket.py) | Versioned `/ws/terminal` operational status and display evidence | Read-only publisher; no strategy authority |
| `__init__.py` | Python package marker | None |

## Selected endpoint map

All HTTP paths below are relative to **`/api/v1`**. For exact request and response schemas, use local `http://127.0.0.1:8000/docs` and the corresponding router contracts rather than treating this table as exhaustive.

| Workstream | Endpoints | Constraints |
| --- | --- | --- |
| Operational health and strategy | `GET /health`, `GET/PUT /strategy`, `POST /strategy/start`, `POST /strategy/stop` | Backend-authorized operational mutations only |
| Emergency risk | `POST /risk/kill`, `POST /risk/resume`, `GET /risk/evidence`, `GET /risk/authorization` | Kill latch, final-authorization and cancellation rules remain authoritative |
| Scenario research | `GET /simulation/scenarios`, `POST /simulation/run`, `POST /simulation/optimize` | One-slot deterministic PAPER worker; no deployment |
| Research market and Vault | `GET /research-markets`, `GET /research-vault/presets`, `POST /research-vault/preview`, `POST /research-vault/compare` | Validated user research assumptions, no operational strategy changes |
| Phase 15 native market observations | `GET /live-markets/overview`, `GET /live-markets/{market}/snapshot`, `GET /live-markets/{market}/stream-status`, `GET /live-markets/{market}/stream-snapshot`, `GET /live-markets/{market}/history`, `GET /live-markets/{market}/references` | BTC, ETH, SOL; provider freshness and missing evidence explicit |
| Phase 15 observed vs research | `POST /research-market-comparison/compare` | Compares separate source epochs; not a historical backtest or execution authorization |
| Phase 16 historical research | `GET /historical-replay/datasets`, `GET /historical-replay/dataset-summaries`, `GET /historical-replay/provenance?dataset_id=...`, `POST /historical-replay/run` | Bounded stored metadata and deterministic hypothetical PAPER computation |

## Phase 16 historical replay API contract

The Phase 16 endpoints are **disabled unless** `HISTORICAL_REPLAY_ROOT` names a trusted, pre-provisioned **owner-only POSIX local directory**. An authorized operator must separately validate and admit JSON records via [`research_replay/importers.py`](../research_replay/importers.py) and [`research_replay/storage.py`](../research_replay/storage.py). **There is no HTTP ingestion route, exchange history downloader, raw-data export, or browser signing/trading path.** Stored historical evidence is separate from the bounded current-session terminal and Phase 15 observer history.

- `GET /datasets`: dataset IDs only, from the existing secure vault.
- `GET /dataset-summaries`: typed, bounded dataset identity, BTC/ETH/SOL market, user-asserted source kind, receipt coverage, counts and gaps. Does not return the recorded L2/context content.
- `GET /provenance?dataset_id=...`: read-only source, observer, fingerprint, coverage and limitation metadata.
- `POST /run`: versioned `phase162-v1` receipt-ordered historical replay with optional `phase163-v1` hypothetical PAPER execution assumptions. It copies current strategy/agent/risk configurations, reuses the **single existing** research worker, and returns independent simulation segments and provenance. A gap, stale/missing economics or observer reset is not silently interpolated across. No continuous aggregate returns across independently reset capital.

**Response and admission behavior:** `Cache-Control: no-store`; disabled storage or research admission returns **503**; a busy shared research worker returns **429**; structured replay rejection or invalid historical evidence can return **422**. Failures must not expose local filesystem paths, credentials, raw provider payloads or unbounded internal diagnostics. Client cancellation is not proof that already-started worker computation stopped.

**Source uncertainty:** recorded-native labels and permitted-use assertions are not independent exchange authentication or license evidence. Source timestamps are distinct from local receipt time, and hypothetical crossing/latency/depth/partial-fill outcomes are not actual fills, queue priority or realized returns.

## Design rules

- **Business logic in domains:** no AMM, strategy, risk, accounting, L2 normalization, execution model or research-run reimplementation in HTTP handlers. Reference [`runtime.py`](../runtime.py), [`simulation/`](../simulation/), [`research_replay/`](../research_replay/), and [`execution/`](../execution/) for authoritative implementations.
- **No authority escalation:** mutation routes use existing runtime locks, validation and `FinalQuoteAuthorization`; research and public observation cannot switch operational markets, clear the manual kill switch, modify signer/account state, or initiate real orders.
- **Explicit bounded evidence:** reject malformed, incomplete, stale or ambiguous inputs as appropriate; never replace failed LIVE data with DEMO values, synthesize missing economics or claim an exchange event-time verification that did not occur.
- **Limit exposure:** preserve loopback/Origin/Host controls, no-store and relevant request-size/admission guards, credential redaction and typed public errors. HTTP/WS local deployment enforcement is not user authentication.
- **Preserve existing ownership:** keep a single runtime and research executor in the lifespan. Redis remains optional ephemeral coordination, not durable accounting, multi-user access or independent economic authority.

## Testing and status

**Merged:** Phase 15.5A/B and Phase 16.1A–16.4. **Not acceptance-complete:** Phase 15 genuine permitted venue delivery/macOS/long-soak verification, and Phase 16.4 full native backend/frontend tests, TypeScript/build and Chromium integration. The Phase 16.4 implementation includes tests but they were **not executed** in its authoring environment. Full backend Phase 16.3 testing reported **2,244 passed, 3 pre-existing static-documentation failures, 1 optional skip**; this was **not** a fully green suite and is not a Phase 16.4 test result.

Validation and architecture details: [root README](../../../README.md), [CODEBASE.md](../../../CODEBASE.md), [CHANGELOG.md](../../../CHANGELOG.md), [Phase 15.5B](../../../docs/PHASE155B_ACCEPTANCE.md), [Phase 16.2](../../../docs/PHASE162_ACCEPTANCE.md), [Phase 16.3](../../../docs/PHASE163_ACCEPTANCE.md), and [Phase 16.4 acceptance plan](../../../docs/PHASE164_ACCEPTANCE.md).


## Phase 16.5C.2 — bounded scenario/historical comparison

`POST /api/v1/research-comparison/scenario-historical` is a computational read-only PAPER endpoint. `research_scenario_replay_comparison.py` delegates to the existing lifespan executor, capturing copies of operational strategy/agent/risk configuration without admitting browser overrides. The new allowlisted `SimulationService.compare_scenario_historical` runs validated historical replay, a scenario with `include_comparison_provenance=True`, and existing `compare_quantitative_paper` sequentially in one worker job. Cancellation detaches the HTTP waiter; the executor retains capacity until real computation finishes. Optional existing Redis coordination wraps the same job.

Request: deterministic scenario, 2–5,000 frames within simulation limits, BTC/ETH/SOL scenario market, optional existing Research Vault proposal, existing `HistoricalReplayRequest` (dataset ID, original fingerprint, market, bounded policy/execution/accounting/window controls), selected index 0–31, trace opt-in and 0–250 transport points per side. Unknown top-level fields, forged result archives, strategy/risk/signer/account overrides and coercible integer/boolean controls are rejected. The existing 65,536-byte write-body limit, loopback/Host/Origin boundary and no-store headers apply.

Response: `phase165c2-v1` envelope carrying an unchanged validated `phase165b-v1` quantitative receipt, captured request/fingerprint, 1–32 independent segment identities, selected-segment policy `RERUN_SELECTED_SEGMENT`, source provenance, up to 1,024 declared gaps, the first 100 replay issues with omitted count, and at most 250 original trace points per side. Trace projection retains sequence, engine timestamp and selected historical book/context receipt/source timestamps with verification flags, without order-book payloads or raw archives. Every omitted point is counted; the JSON response has a 1,000,000-byte ceiling checked inside the worker. Reduce trace retention/point limit if the response budget is exceeded. This is a prefix projection of original retained points, not interpolation or invented downsampling.

Segment selection reruns the bounded validated request; no server sessions or result cache were added. Each segment keeps fresh capital, positions, orders, risk and execution state. Original historical and engine-segment dataset fingerprints are distinct. Source labels, licenses and scenario service receipts do not establish independent exchange authentication. `CONTEXT_ONLY` permits independent backend descriptive values; `INCOMPARABLE` emits no paired financial rows or trace points. `ALIGNED`, direct financial deltas, cross-segment aggregation and strategy ranking remain unavailable.

Errors: 422 invalid inputs/identity/evidence/selection/response budget or corrupt data; 429 authoritative shared-worker busy; 503 unconfigured/unsafe storage or admission outage; 500 sanitized internal failure. Error bodies omit private paths, credentials, stack traces and provider payloads. Replay rejection issues are capped at 100 on this route. Other historical routes preserve their existing status behavior.

This endpoint cannot submit orders, start strategy execution, reset the kill switch, modify operational configuration or ledgers, reserve account capital, sign transactions or create live subscriptions. See [native and Chromium evidence](../../../docs/PHASE165C2_ACCEPTANCE.md).
