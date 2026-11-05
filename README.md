# HyperAMM
### Adaptive Virtual AMM, Market-Making & PAPER Research Terminal for Hyperliquid

**HyperAMM converts virtual AMM liquidity curves into tick/size-normalized Hyperliquid CLOB quotes.** Its Python/FastAPI engine combines constant-product and concentrated-liquidity modeling with inventory skew, perpetual context, market adaptation, deterministic supervisory agents, a risk firewall and final execution authorization. Its React/TypeScript terminal separates operational controls from read-only market intelligence and offline PAPER research.

> **Open source · active development · local/single-operator architecture.** This repository is an engineering and research project, **not** a production-ready trading service, investment product, custody system or verified profitable strategy. PAPER/DEMO is the default; TESTNET signing is separately guarded. No mainnet trading, withdrawal, transfer or bridging path is implemented.

## Current project status — November 5, 2026

| Workstream | Merged implementation | Acceptance / boundary |
| --- | --- | --- |
| Core AMM, inventory, perp context, reference risk, supervisory agents and Vault (Phases 1–12) | Operational pipeline, deterministic PAPER simulation, guarded optional TESTNET, 12-page terminal | Historical local/fixture acceptance; external, platform and production gates remain |
| Institutional UX and research (Phases 13–14.6) | Analytics, Execution/Markets UX, Research Vault presets/comparisons, BTC/ETH/SOL isolated PAPER market selection | Local/browser acceptance does not establish venue performance |
| Read-only native market intelligence (Phases 15.1–15.5B, PRs #50–#55) | Official SDK REST/WS observation, L2/perp contexts, stream freshness, bounded history, provider health, observer lifecycle hardening | **Combined Phase 15 not closed:** genuine permitted venue connectivity, long soak and independent macOS acceptance outstanding |
| Historical research contracts and importer (Phases 16.1A/B, PRs #56–#57) | Immutable provenance, bounded secure local JSON admission, owner-only POSIX evidence vault | Source/permission labels are user assertions; no authenticated historical-feed or license proof |
| Deterministic replay and modeled PAPER execution (Phases 16.2–16.3, PRs #58–#59) | Receipt-ordered replay, explicit segment resets, missing-economics rejection, optional latency/slippage/depth/partial-fill sensitivity | No verified real fills, queue priority, market completeness or production forecast |
| Historical Replay Studio (Phase 16.4, PR #60) | React dataset selector, frame navigation, historical book/chart views, per-segment metrics, baseline-versus-modeled comparisons | **Merged but native frontend/backend regression and Chromium acceptance not yet reported** |
| Next (Phases 16.5–16.6, then 17) | Scenario/replay comparison, adversarial acceptance, then multi-market portfolio research | Planned; not implemented or accepted here |

The current **research and independent live-observation universe** is **BTC-PERP, ETH-PERP and SOL-PERP**. That does not expand the operational strategy market or permit switching live execution through the research UI. Operational market data, independent read-only observation and the historical PAPER replay vault are **three separate evidence paths**.

Details and actual milestone tests: [CHANGELOG.md](CHANGELOG.md), [CODEBASE.md](CODEBASE.md), [Audit 1.0](AUDIT_REPORT_1.0.md), [Audit 2.0](AUDIT_REPORT_2.0.md), and the [Phase 15.5B](docs/PHASE155B_ACCEPTANCE.md) / [Phase 16.4](docs/PHASE164_ACCEPTANCE.md) acceptance documents.

## Why a virtual AMM?

CLOB market making and AMM liquidity have different execution mechanics but can share a useful mathematical representation. HyperAMM treats `x*y=k` as a **quote-generation model** instead of a settlement venue:

```text
Hyperliquid L2 / Demo Feed
          ↓
 normalized BBO + freshness
          ↓
 fair value = (bid + ask) / 2
          ↓
 virtual x*y=k reserves
          ↓
 constant / concentrated curve
          ↓
 tick + size discretization
          ↓
 bid/ask QuoteLevel ladder
          ↓
 deterministic risk checks
          ↓
 KEEP / CREATE / REPLACE / CANCEL
          ↓
 PAPER execution or guarded TESTNET
```

## Capabilities at a glance

| Area | What is implemented |
| --- | --- |
| **AMM and quote generation · Phases 1–4.1** | Virtual constant-product `x*y=k` reserves, concentrated liquidity, deterministic CLOB ladder sampling, venue price/size normalization, KEEP/CREATE/REPLACE/CANCEL |
| **Inventory and market adaptation · Phases 5–7** | Inventory-aware price/size skew, hard limits, realized volatility, L2 imbalance, mark/oracle/funding/open-interest context and bounded reference recentering |
| **Risk and agents · Phases 8–9** | Source freshness and role-aware reference integrity, exposure/capital checks, NORMAL/WIDEN/REDUCE/HALT firewall, deterministic/heuristic supervisor, optional **ML SHADOW** research |
| **Simulation and accounting · Phases 10–11** | Isolated deterministic scenarios, bounded grid optimizer, research accounting presets, average-cost PAPER ledger, fees/funding assumptions, equity/drawdown and capital authorization |
| **React operator terminal · Phases 12–14.6** | Twelve active pages, charts, quote/execution evidence, risk/Vault views, log/settings/analytics UX, Research Vault controls and BTC/ETH/SOL PAPER market selection |
| **Independent market intelligence · Phase 15** | Opt-in BTC/ETH/SOL public Hyperliquid SDK REST + WS observer, L2 book, mark/oracle/funding/OI, stream diagnostics, bounded time-aware history, provider integrity and Market vs Research comparison |
| **Historical market replay · Phase 16** | Immutable BTC/ETH/SOL source contracts, secure bounded local datasets, deterministic receipt-order replay, explicit gaps/segment resets, per-segment PAPER accounting, modeled crossing controls and Historical Replay Studio |

The operational path still runs **normalized market evidence → AMM/strategy → inventory/perp/adaptation → supervisory recommendations → risk firewall → final quote authorization → order reconciliation → PAPER or guarded TESTNET**. The Phase 15 observer cannot supply execution authority. Phase 16 cannot import data or deploy a strategy from the browser; it runs independent computational research through the existing one-slot simulator.

For detailed earlier implementations, keep reading the phase notes below. For changed files and component-level boundaries, see [CODEBASE.md](CODEBASE.md).

## Technology

| Layer | Stack |
| --- | --- |
| Backend | Python 3.12+, FastAPI, Pydantic v2, asyncio, exact `Decimal` financial math, `httpx`, `websockets`, official `hyperliquid-python-sdk` |
| Operational & research execution | Reused AMM/strategy engine, risk firewall, final authorization, simulated PAPER adapter, bounded single-slot `SimulationExecutor`; optional ephemeral Redis coordination |
| Historical replay storage | Strict immutable Pydantic contracts, SHA-256 content fingerprints, owner-only **local POSIX** filesystem vault, bounded JSON read/admission |
| Frontend | React 19, TypeScript, Vite, TanStack Query, Zustand, Lightweight Charts v5, native WebSocket |
| Tests | pytest, Node frontend test harness, TypeScript/Vite checks and independently executed Chromium scenarios where recorded |

No Docker, Kubernetes or GitHub Actions infrastructure is required. PostgreSQL-based durable operational accounting and production deployment are **not** part of the current implementation.

## Quick start — native local development

Requirements: Python **3.12+**, Node.js/npm, and a supported loopback desktop environment. Run the backend and frontend in **separate terminals**. These commands assume you start at the repository root (`hyperamm/`).

Create a local config file from the tracked example (do not commit credentials):

```bash
cp .env.example .env
```

### Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest tests -q
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API: `http://127.0.0.1:8000` · interactive local OpenAPI: `http://127.0.0.1:8000/docs`.

### Frontend

From a **second terminal** at the repository root:

```bash
cd frontend
npm install
npm run typecheck
npm run build
npm test
npm run dev
```

Terminal: `http://127.0.0.1:5173`. Vite proxies `/api` and `/ws` to the local backend. These are instructions to reproduce validation, not claims that the latest full suite is green. See [tests and acceptance](#tests-and-acceptance).

## Market modes and independent native observation

The tracked [`.env.example`](.env.example) starts in deterministic research mode:

```dotenv
MARKET=ETH
MARKET_DATA_MODE=DEMO
EXECUTION_MODE=PAPER
```

DEMO observations are visibly simulated. To select operational public market data (without changing execution mode), `MARKET_DATA_MODE=LIVE` is available. Failed LIVE data does **not** silently fall back to DEMO.

Phase 15's **independent read-only BTC/ETH/SOL market observer** is different from the operational market mode. Enable its opt-in public REST and WebSocket observations with:

```dotenv
LIVE_OBSERVATIONS_ENABLED=true
LIVE_STREAMS_ENABLED=true
```

`LIVE_STREAMS_ENABLED` requires `LIVE_OBSERVATIONS_ENABLED`. The Markets page shows native order books, mark/oracle/funding/OI, source and receipt times, provider health, reconnects and explicit gaps. These observation endpoints cannot sign orders or change the active operational market. Genuine permitted Hyperliquid delivery and independent macOS acceptance remain open after Phase 15.5B.

## PAPER and optional TESTNET execution

Normal operational PAPER orders and built-in deterministic scenario simulation use the existing crossing-only hypothetical fill model. The **Phase 16.3 historical replay** additionally supports opt-in receipt-clock order/cancel latency, slippage, observed-depth participation and partial-fill sensitivities. They are hypothetical modeling controls, **not** evidence of real exchange execution, queue priority or market latency.

TESTNET signing is **disabled by default**. Only if explicitly intended, configure backend-only credentials and enable the guarded TESTNET path:

```dotenv
EXECUTION_MODE=TESTNET
ENABLE_HYPERLIQUID_TESTNET_ORDERS=true
HYPERLIQUID_ACCOUNT_ADDRESS=0x...
HYPERLIQUID_PRIVATE_KEY=...
```

The existing TESTNET adapter uses guarded Hyperliquid post-only `Alo` limit orders and authoritative risk checks. Never put a private key in frontend code or commit it. No production mainnet order, custody, withdrawal, transfer or bridging path is implemented.

## Selected API surface

All HTTP paths below use the `/api/v1` prefix and assume a trusted **local** operator; HTTP loopback restrictions are not public remote authentication.

| Area | Selected endpoints |
| --- | --- |
| Operations | `GET /health`, `GET /strategy`, `PUT /strategy`, `POST /strategy/start`, `POST /strategy/stop`, `POST /risk/kill`, `POST /risk/resume` |
| AMM/risk/agents | `GET /amm/state`, `GET /amm/curve`, `GET /amm/quotes`, `GET /risk/evidence`, `GET /risk/authorization`, `GET /agents/events` |
| Market/reference | `GET /market-adaptation`, `GET /perp-context`, `GET /references`, `GET /references/observations` |
| Vault & terminal | `GET /vault`, `GET /accounting/pnl`, `GET /accounting/ledger`, `GET /terminal/history`, `GET /terminal/events` |
| Simulation & research | `GET /simulation/scenarios`, `POST /simulation/run`, `POST /simulation/optimize`, `GET /research-markets`, `GET /research-vault/presets`, `POST /research-vault/compare`, `POST /research-market-comparison/compare` |
| Native market observations | `GET /live-markets/overview`, `GET /live-markets/{market}/snapshot`, `GET /live-markets/{market}/stream-status`, `GET /live-markets/{market}/history`, `GET /live-markets/{market}/references` |
| Historical replay | `GET /historical-replay/datasets`, `GET /historical-replay/dataset-summaries`, `GET /historical-replay/provenance?dataset_id=...`, `POST /historical-replay/run` |

Operational terminal WebSocket: `/ws/terminal`. The historical replay APIs execute isolated PAPER research; they are **not** exchange order or browser dataset-upload endpoints. See local `/docs` for the authoritative route schemas.

## React terminal and research UX

The institutional React terminal contains twelve active pages: **Dashboard, Markets, Strategy, AMM Settings, Execution, Risk, Supervisory Agents, Vault, Analytics, Simulation & Optimization, Logs and Settings**.

Markets separates operational evidence from independently observed read-only native markets and the Market vs Research comparison. Simulation & Optimization contains deterministic scenario studies, Research Vault comparisons and the new Historical Replay Studio; this reuses the existing charting and research machinery rather than adding another application.

Historical replay charts render admitted source observations only; there is no invented OHLCV, synthetic exchange event timestamp or continuous price series across gaps. Browser replay controls navigate already-returned PAPER frames, not live trades, and cannot deploy a research strategy.

## Tests and acceptance

Normal backend tests exercise AMM/invariant math, inventory, quote validity, provider timing, risk authorization, lifecycle and PAPER accounting; later suites add native observation integrity, historical import/storage, deterministic replay, modeled execution sensitivity and operational-state isolation. Frontend tests cover typed evidence, charts, session retirement, route behavior, and specific research-view guardrails. Normal fixture tests do not require live venue credentials.

| Recorded milestone | Reported validation | Important caveat |
| --- | --- | --- |
| Phase 15.5A · [PR #54](https://github.com/btorressz/hyperamm/pull/54) | 1,822 backend; 641 frontend; 28 Chromium workflows; 7 actual Redis checks | Offline/fixture evidence; external/macOS gates remain |
| Phase 15.5B · [PR #55](https://github.com/btorressz/hyperamm/pull/55) | 1,916 backend; 652 frontend; 47 Chromium workflows | Genuine Hyperliquid delivery proxy-blocked; final Phase 15 acceptance open |
| Phase 16.1B · [PR #57](https://github.com/btorressz/hyperamm/pull/57) | 146 focused; full backend 2,058 passed / 3 failed / 1 skipped | Three static documentation failures reproduced on unchanged base |
| Phase 16.2 · [PR #58](https://github.com/btorressz/hyperamm/pull/58) | 205 focused; full backend 2,102 passed / 3 failed / 1 skipped | Same baseline failures; no real native history or frontend acceptance |
| Phase 16.3 · [PR #59](https://github.com/btorressz/hyperamm/pull/59) | 376 focused; full backend 2,244 passed / 3 failed / 1 skipped | Same baseline failures; hypothetical execution only |
| Phase 16.4 · [PR #60](https://github.com/btorressz/hyperamm/pull/60) | New focused tests and acceptance plan committed | **No native Python/Node, TypeScript/build, full regression or Chromium run reported for this merged PR** |

The three Phase 16.1B–16.3 baseline failures were static scans involving unchanged `docs/PHASE155B_ACCEPTANCE.md`; the one skip is optional ML training without scikit-learn. **Do not claim the full backend suite is green.** These are per-PR historical reports, not fresh tests for the current README update.

Before releasing or treating Phase 16.4 as accepted, run native Python/Node suites, `npm run typecheck`, `npm run build`, `npm test`, actual Chromium replay/retirement/error-path acceptance, and independent operational isolation checks. Details: [16.4 acceptance plan](docs/PHASE164_ACCEPTANCE.md).

## Safety and authority boundaries

- **Default DEMO/PAPER.** TESTNET signing requires explicit opt-in, backend-only credentials, and authoritative checks; no mainnet execution, deposits, withdrawals, transfers, custody or bridging features.
- **Local/single-operator only.** Bind loopback `127.0.0.1` and one backend worker; exact local HTTP/WS Host/Origin/peer guards and write-body limits are **not** public authentication or a remote deployment model.
- **No new trading authority through research.** Phase 15 observation, Yahoo SHADOW research, Research Vault presets and Phase 16 replay have no strategy/risk/quote/signing authority.
- **Fail-closed evidence.** Stale/missing/invalid market observations cannot authorize new orders. Historical missing economics are rejected or explicitly excluded, never imputed as venue history.
- **Source and result provenance is scoped.** Content SHA-256 fingerprints are reproducibility identities, not authenticity, licensed-use evidence, signatures or complete source archives.
- **No fabricated economic outcomes.** Order-book snapshots do not establish actual queue position, unobserved trades, passive fills, real order latency, continuous history or reproducible future returns.
- **Secrets and infrastructure remain backend-only.** Do not commit `.env`, wallet keys or external provider credentials. Optional Redis is ephemeral coordination, not a durable execution ledger.

## Limitations and outstanding acceptance

Research-mode software is **not** production authorization. Phase 15's independent public-stream observer was hardened with meaningful offline SDK, fixture and Chromium tests, but genuine live delivery and independent macOS verification remain open. Phase 16 can process **bounded locally admitted** recorded-native or explicitly synthetic histories; data rights, external authenticity and market coverage remain user assertions. Historical simulations intentionally reset all PAPER state on gaps and model unobserved execution effects only as separately labeled hypotheses.

Live operating/reference data and TESTNET signing remain governed by the existing runtime and final risk authority; neither the historical Replay Studio nor the market-comparison UI can deploy a candidate. Optional Redis does not enable distributed execution, and accounting is a non-custodial in-memory operational/PAPER session ledger. The local historical evidence vault is **separate owner-only file storage**, not durable operational accounting.

Phase 16.4 is **merged but acceptance-incomplete**. The next planned work is **16.5 scenario-vs-replay comparison, 16.6 adversarial acceptance**, and later **Phase 17 multi-market shared-capital portfolio research**. Do not equate a merged feature or historical test count with a fully validated deployment.

### Audit informational boundaries (A1-024–A1-027)

- **AMM capital semantics (A1-024):** virtual reserves and `k` define curve geometry. `total_liquidity` is the explicit per-side base-asset quote budget; changing `k` alone does not imply more quoted capital, TVL or margin.
- **Scientific-tooling boundary (A1-025):** current deterministic strategy/simulation authority does not depend on Pandas or SciPy. Future scientific tooling belongs in optional offline research with immutable exported inputs and proposal-only outputs, never signing/risk/position/capital authority.
- **Accounting/custody boundary (A1-026):** the vault and ledger are non-custodial, in-memory research accounting. TESTNET economics remain partial where unsupported; deposits, withdrawals, shares and durable production-book recovery are outside current scope.
- **Provenance boundary (A1-027):** semantic versions and fingerprints identify their declared material decision/input scopes. They are not complete raw-evidence archives, source-revision manifests or automatic Git/dependency provenance.

## Documentation

| Guide | Purpose |
| --- | --- |
| [CHANGELOG.md](CHANGELOG.md) | Merged PR history through Phase 16.4 and limitations |
| [CODEBASE.md](CODEBASE.md) | Repository structure and architecture/authority inventory |
| [Architecture](docs/ARCHITECTURE.md) · [AMM math](docs/AMM_MATH.md) | Core runtime pipeline, curve and sizing math |
| [Hyperliquid integration](docs/HYPERLIQUID_INTEGRATION.md) | Operational feed, SDK and guarded TESTNET boundaries |
| [Reference integrity](docs/REFERENCE_INTEGRITY.md) · [Risk firewall](docs/RISK_FIREWALL.md) | Evidence/quorum and final-authority constraints |
| [Agents](docs/AGENTS.md) · [Simulation](docs/SIMULATION.md) · [Accounting](docs/ACCOUNTING.md) | Supervision, PAPER scenarios and Vault economics |
| [Phase 15.5A](docs/PHASE155A_ACCEPTANCE.md) · [Phase 15.5B](docs/PHASE155B_ACCEPTANCE.md) | Local/browser security and live-observer acceptance gaps |
| [16.1A](docs/PHASE161A_CONTRACTS.md) · [16.1B](docs/PHASE161B_ACCEPTANCE.md) | Historical evidence and bounded secure storage |
| [16.2](docs/PHASE162_ACCEPTANCE.md) · [16.3](docs/PHASE163_ACCEPTANCE.md) · [16.4](docs/PHASE164_ACCEPTANCE.md) | Historical replay, execution sensitivities and UI acceptance plan |
| [Development roadmap](docs/ROADMAP.md) | Detailed historical phased implementation notes; status may lag the changelog |

## Development milestones

**Implemented/merged:** Phases 1–12 (core trading/research/terminal), 13–14.6 (institutional UX and customizable PAPER research), 15.1–15.5B (read-only native market intelligence and hardening), 16.1A–16.4 (historical research and Replay Studio).

**Acceptance still required:** combined Phase 15 permitted live/macOS checks and Phase 16.4 native+browser integration checks.

**Planned:** Phase 16.5 comparative scenario-vs-history research, 16.6 final regression/security acceptance, then Phase 17 shared-capital BTC/ETH/SOL portfolio research. See [CHANGELOG.md](CHANGELOG.md) for merged work and [Phase 16 acceptance](docs/PHASE164_ACCEPTANCE.md) for outstanding gates.

The detailed historical Phase 4–12 descriptions below document how the existing operational engine was built; they are preserved for technical context.

## Phases 13–14.6 — Institutional terminal and Research Vault

Phase 13 introduced a consistent institutional layout, accessible navigation, richer Execution/Risk/Vault/Agents pages, session-aware Logs and Settings, and the improved Analytics/Simulation workspace. Phase 14 added bounded Research Vault presets and validated custom accounting assumptions, with controlled baseline-versus-custom comparisons. Phase 14.6 added isolated **BTC/ETH/SOL PAPER research selection** with typed market metadata and fingerprints. None of these browser selections changes the operational market or promotes research outcomes to live execution.

## Phase 15 — Independent public Hyperliquid market intelligence

Phases 15.1–15.5B added read-only official SDK REST and WebSocket observation for **BTC, ETH and SOL perpetuals**. Markets exposes actual accepted L2 depth, midpoint/spread, mark/oracle/funding/OI, receipt-vs-source timestamps, freshness, provider health, reconnects and bounded historical observations. The Market vs Research view compares independently timed native observations and hypothetical PAPER evidence without claiming simultaneous ticks or implying fills.

The Phase 15.5A/B hardening improves local security, trusted-source identity, bounded callback processing, SDK ownership/cleanup, recovery, history integrity and stale/degraded UI. It has substantial recorded offline and browser acceptance, **not verified genuine venue delivery**. The complete Phase 15 external/macOS gate remains open. See [Phase 15.5A](docs/PHASE155A_ACCEPTANCE.md) and [15.5B](docs/PHASE155B_ACCEPTANCE.md).

## Historical Replay Studio — Phase 16

Phase 16 uses an independent evidence and research path. It **does not** add a historical exchange feed or alter the live runtime:

1. **16.1A / 16.1B — contracts and secure admission:** Immutable `phase16-replay-v1` recorded-native versus synthetic contracts, explicit observation/gap/receipt identity, owner-only POSIX JSON vault and deterministic content fingerprints. The library exposes bounded local `import_file` / `HistoricalStorage.save` utilities for trusted operator-side admission, **not a browser upload or automatic exchange-history collector**.
2. **16.2 — deterministic replay:** The existing single-slot `SimulationExecutor` drives chronological receipt-time replay through the production research engine. Missing actual L2, mark, oracle, funding or OI is excluded/rejected, not invented. Observer resets, declared gaps and interval breaks create separate fresh PAPER segments. Source time remains distinct from receipt time.
3. **16.3 — modeled crossing sensitivities:** Baseline PAPER behavior is preserved. Opt-in model settings allow declared latency, slippage, observed-depth participation and partial-fill sensitivity, with existing accounting and authoritative per-segment baseline comparisons. These are **hypothetical**, not calibrated real execution.
4. **16.4 — React Replay Studio:** Under **Simulation & Optimization** (`#/simulation`), choose a previously admitted dataset, inspect source/coverage/provenance, select modeling assumptions, run a bounded replay, navigate independent segments and frames, inspect historical price/book, simulated equity/risk/PnL and baseline-versus-modeled deltas.

### Enable a trusted local historical vault (optional)

Historical replay is **disabled** until you explicitly provision `HISTORICAL_REPLAY_ROOT` in the backend environment. On a local POSIX filesystem, for example:

```bash
mkdir -p "$HOME/.hyperamm/replay"
chmod 700 "$HOME/.hyperamm" "$HOME/.hyperamm/replay"
# Add an absolute, trusted path to your root .env file:
# HISTORICAL_REPLAY_ROOT=/absolute/path/to/your/private/replay
```

The configured directory must be owned by the backend user, restricted to that user, and under trusted path ancestors; unsafe roots fail closed. **Setting a directory does not import datasets.** An operator must supply permitted-use assertions and validate/admit bounded local JSON files through the existing Python importer/storage interfaces. There is no bundled genuine historic market data, exchange archival downloader, raw-data browser upload or automatic import. With no admitted dataset, the Studio is empty. When unset, the historical API responds with **503**.

The UI's `GET /historical-replay/dataset-summaries` selector only exposes dataset metadata; `GET /historical-replay/provenance` explains source/time trust limits; `POST /historical-replay/run` performs simulated computation in the **existing** research worker. A busy worker returns 429; malformed or incomplete historical economic evidence is rejected explicitly. The browser's play button changes **displayed frame position**, not the exchange or runtime.

Each segment's equity and PnL are independent, so no cross-gap aggregate return is shown. Recorded-native labels, source-time assertions, licensing and fingerprint identities are **not independently authenticated**. Model slippage/latency and fill results do **not** validate hidden liquidity, real network delays or future profitability.

**Status:** [PR #60](https://github.com/btorressz/hyperamm/pull/60) is merged, but native Python/Node, TypeScript/Vite and Chromium acceptance for 16.4 **was not reported before merge**. Follow [the Phase 16.4 acceptance plan](docs/PHASE164_ACCEPTANCE.md) before treating it as finished.

## Phase 4.1 acceptance and hardening

Constant-product **incremental reserve movement** now drives quote sizes.
Concentrated mode modifies that AMM profile; `total_liquidity` remains a per-side
base-asset budget including baseline sizes. See [AMM math](docs/AMM_MATH.md).

Invalid/stale/degraded feeds and generation/risk failures clear the desired
ladder and cancel strategy orders. Enabled intent can recover automatically;
manual kill requires explicit resume and start. Quote health is shown in the
terminal. Unconfirmed cancellation latches HALTED rather than reporting success.

Execution uses a shared lock and final authority checks. TESTNET reconciles
tracked orders through WebSocket-triggered and periodic authoritative venue
queries, including partial fills and uncertain order states. See
[architecture](docs/ARCHITECTURE.md) and [integration](docs/HYPERLIQUID_INTEGRATION.md).
Normal acceptance tests use deterministic fixtures and require no live venue or
wallet. Phase 5 is complete; later phases retain the same execution-authority boundaries.


## Phase 5 — Inventory-Aware Quoting

Phase 5 composes after the accepted neutral AMM/concentration ladder and before deterministic risk/reconciliation. PAPER inventory is derived from economic fills only. TESTNET inventory is normalized from Hyperliquid account state and fails closed when authoritative state is missing, stale, malformed, or economically uncertain.

For deviation `d = position - target`, normal skew uses `r = clamp(d / soft_limit, -1, 1)`. The reservation shift is `-r * max_inventory_price_skew_bps`; bid and ask sizes use bounded `1 - strength*r` and `1 + strength*r` side multipliers. At the long hard limit, inventory-increasing bids are omitted; at the short hard limit, inventory-increasing asks are omitted. Existing reconciliation therefore cancels forbidden resting quotes without a second order-management path.

See [Inventory Skew](docs/INVENTORY_SKEW.md) for formulas, source semantics, failure behavior, and test coverage.


## Phase 6 — Volatility + Order-Book Imbalance Adaptation

Phase 6 composes after the accepted Phase 5 inventory policy and before deterministic risk. It uses only normalized Hyperliquid/demo market data already present in the project.

The volatility input is normalized mid price. A bounded rolling window stores unique market observations by exchange sequence/timestamp. Once the configured minimum sample count is reached, per-observation realized volatility is:

```text
r_t = ln(P_t / P_(t-1))
sigma = sqrt(mean(r_t^2))
```

Before minimum history exists, Phase 6 reports `WARMING_UP`, exposes no fabricated realized-volatility value, and leaves spread/size adaptation neutral.

Top-N L2 imbalance is base-size depth:

```text
imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)
```

with a bounded range of `[-1,+1]`. Once volatility is ready, the widening-only spread multiplier is:

```text
1 + volatility_spread_strength * volatility_score
  + imbalance_spread_strength * abs(book_imbalance)
```

clamped to configured limits. Variable liquidity above the existing Phase 5 `base_order_size` floor is reduced by bounded global volatility and conservative side-specific imbalance multipliers. Phase 5 hard-limit suppression remains authoritative and Phase 6 cannot restore a removed side.

See [Market Adaptation](docs/MARKET_ADAPTATION.md).


## Phase 7 — Perpetual vAMM Context

Phase 7 keeps raw market fair value separate from a bounded perpetual strategy reference. It normalizes Hyperliquid native `markPx`, `oraclePx`, current `funding`, and `openInterest`; computes signed basis values and OI notional; blends market/mark/oracle prices with configurable weights; applies a bounded funding shift; clamps the total reference move; then recenters the virtual AMM around that strategy reference before Phase 5 inventory and Phase 6 market adaptation.

PAPER mode requires no wallet and exposes null account-only fields. DEMO perp values are deterministic and explicitly labeled simulated. TESTNET reuses the same `user_state()` snapshot for Phase 5 inventory and Phase 7 perp-position observability, with an exact signed-position consistency check.

See [Perpetual Context](docs/PERP_CONTEXT.md).


## Phase 8 — Reference Integrity + Institutional Risk Firewall

Phase 8 is the final deterministic authority between strategy proposal and execution. It normalizes RedStone primary-oracle evidence, Hyperliquid native oracle/mark/mid evidence, Kraken exchange BBO evidence, and CoinGecko aggregate evidence into provider-independent contracts. It evaluates source health, per-provider freshness, role-aware quorum, deterministic median consensus, outliers, signed deviations, projected exposure, liquidation distance, fill-derived PAPER PnL, TESTNET equity/drawdown where authoritative values exist, and an explicit `NORMAL / WIDEN / REDUCE / HALT` state machine.

Only the authorized ladder continues to the existing structural `validate_quotes()`, reconciliation, and PAPER/guarded TESTNET execution path. Final CREATE/REPLACE authority is bound to market, inventory, perp, reference and risk versions plus SHA-256 quote/evidence/risk fingerprints.

DEMO/PAPER generates deterministic simulated external-reference evidence. LIVE/PAPER can run public reference infrastructure without a trading wallet. Provider credentials remain backend-only.

See [Reference Integrity](docs/REFERENCE_INTEGRITY.md) and [Risk Firewall](docs/RISK_FIREWALL.md).


## Phase 9 — Deterministic Supervisory Agents

Phase 9 inserts a bounded, deterministic supervisory layer after Phase 6 strategy adaptation and before the Phase 8 firewall. Regime v2, multi-horizon Toxic-Flow v2, Execution-Quality v2, Liquidity Quality and Perp Crowding consume normalized existing evidence only. Their supervisor can widen spreads, reduce side sizes or trim existing levels; it cannot execute orders, restore suppressed liquidity, clear the manual kill switch or override Phase 8.

FinalQuoteAuthorization binds the material deterministic/heuristic agent version and fingerprint in addition to the existing market, inventory, perp, reference and risk authority. Predictive Adverse Selection is **ML SHADOW ONLY**, with conditional BID/ASK adverse-fill probabilities and `affects_quotes=false`; shadow predictions and model changes do not alter quotes or execution authority.

PAPER fill telemetry is explicitly simulated. TESTNET fill-quality metrics remain unavailable where authoritative fill detail does not exist; no slippage or markout is fabricated.

Offline research adds a canonical `passive-adverse-v1` feature schema, leakage-aware datasets with independent train/validation identities, optional scikit-learn logistic training (`pip install -e '.[test,ml]'` from `backend`), bounded JSON artifacts with SHA-256 provenance, and side/horizon calibration reports. Normal backend installation does not require ML dependencies. The terminal labels heuristic/deterministic/ML SHADOW evidence, and agent APIs publish one coherent cycle snapshot with bounded event filters. No artifact is supplied by default.

Agents recommend. Phase 8 decides. FinalQuoteAuthorization controls execution.

See [Supervisory Agents](docs/AGENTS.md) and the [agent implementation and ML contracts](backend/app/agents/README.md).


## Phase 10 — Strategy Optimization + Deterministic Simulation

Phase 10 is offline research tooling around the actual HyperAMM strategy stack. It does not contain a second simplified strategy. Each simulation run creates fresh MarketPriceHistory, PAPER execution, Phase 9 telemetry/supervisor, Phase 8 firewall, reconciliation and accounting state, then reuses the existing QuoteEngine → inventory → market adaptation → perp policy → agents → risk → FinalQuoteAuthorization → OrderManager path frame by frame.

Built-in deterministic scenarios cover quiet/trending/mean-reverting/high-volatility markets, book imbalance, flash moves, oracle dislocation, reference degradation, funding stress and liquidity shock. Synthetic references preserve the existing provider identities but are explicitly labeled DEMO / SIMULATED.

The v1 optimizer is deterministic grid search only. It supports an explicit allowlist of strategy/agent research parameters, rejects safety/runtime fields, evaluates an unchanged BASELINE, ranks on training scenarios, evaluates top candidates on separate validation scenarios, and exposes every numeric score component. Results are research rankings under the selected scenarios/objective—not claims of optimality or future profitability.

See [Simulation](docs/SIMULATION.md).


## Phase 11 — Vault & Deterministic Accounting Layer

The Vault page exposes research settled capital, average-cost position accounting, realized/unrealized PnL, configured PAPER fees and funding, equity/peak/drawdown, simulated full-notional capital reservation and append-only ledger provenance. Runtime PAPER, Phase 8 risk and Phase 10 simulation share one accounting service. Final authorization binds accounting version/fingerprint and stale or changed accounting blocks CREATE/REPLACE while cancellation remains possible.

PAPER accounting is always SIMULATED. TESTNET only exposes existing authoritative account/position evidence and labels full accounting PARTIAL; unavailable cash, realized PnL, fees, funding payments and capital availability remain null. No real custody, deposits, withdrawals, transfers, bridging, investor accounting or fund fees are introduced.

Read-only endpoints: `/api/v1/vault`, `/api/v1/accounting/pnl`, `/api/v1/accounting/position`, `/api/v1/accounting/ledger`, `/api/v1/accounting/events`. The terminal WebSocket adds compact accounting summary and recent notices. See [Accounting](docs/ACCOUNTING.md) for formulas, defaults, retention, identities and truth boundaries.

Phase 11.1 hardening observes PAPER equity highs after committed fill+fee batches,
funding and marks. Vault/API/WebSocket expose identity-based execution/accounting
consistency. Missing or conflicting executed fills make capital authority
UNAVAILABLE and block CREATE/REPLACE; cancellation remains available. Internal
reconciliation books only safe, unfailed pending evidence and never clears a
latched error. No public accounting reset/replay endpoint is provided.


## Phase 12 operator terminal

The React terminal exposes the existing Phase 1–11.1 pipeline through twelve
active pages: Dashboard, Markets, Strategy, AMM Settings, Execution, Risk,
Supervisory Agents, Vault, Analytics, Simulation & Optimization, Logs and Settings.
It displays retained quote-stage evidence, incremental price/liquidity charts, session analytics,
responsive layouts, visible emergency kill and WebSocket diagnostics. Missing or
approximate lineage remains qualified by A1-021; chart history ordering (A1-020)
and remaining remote/operational limits are tracked in [Audit 1.0](AUDIT_REPORT_1.0.md).

`/ws/terminal` now carries the code-owned `phase12-v1` contract, process-wide
sequence, UTC emission time, pre-agent/post-agent/final quote stages and
observational system health. Read-only `/api/v1/terminal/history` (3600 retained
points, at most 1000 per response) and `/api/v1/terminal/events` (500 retained
and at most 500 per response) keep history outside live snapshots.

Operational terminal history is in-memory and current-session only (the Phase 16 owner-only historical evidence vault is separate). PAPER/DEMO remains simulated;
TESTNET fills and unsupported accounting economics remain explicitly unavailable.
Existing risk, supervision, execution and accounting authority/formulas are
unchanged. No custody, money movement or autonomous candidate deployment is added.
See [Terminal architecture, operator pages and limits](docs/TERMINAL.md).


### Audit 1.0: local deployment boundary (A1-009)

HyperAMM currently supports **local, single-operator, research-only** use with
one backend worker. PAPER is the default; TESTNET still requires explicit mode,
order-enable flag and testnet credentials. No mainnet execution is supported.
Bind to loopback, keep the frontend local, and do not expose the backend through
public/LAN interfaces, reverse proxies, tunnels or port forwarding. Remote/public
deployment is unsupported. CORS is browser policy, **not authentication**.

Startup rejects non-loopback `--host`/`--bind` and `UVICORN_HOST`, and worker
counts other than one in `--workers`/`-w`, `WEB_CONCURRENCY` or `UVICORN_WORKERS`.
HTTP and WebSocket requests require a loopback peer and strictly parsed local Host.
Browser Origin must match the request origin or an exact local origin configured
in `CORS_ORIGINS` (default localhost/127.0.0.1/[::1] on port 5173). Unrelated
localhost ports, ambiguous security headers and forwarded headers are rejected.
API write bodies share a 64 KiB pre-parsing bound, including chunked requests. These checks do not
make a loopback proxy or separately launched backend processes supported. Use
one instance only; there is no multi-process coordination. Local Uvicorn reload
remains supported. Starlette's in-process test transport is accepted for tests.

Future remote deployment requires operator authentication/authorization,
request/resource admission, WebSocket client controls, TLS/proxy policy, audit
logging, and a secrets lifecycle before exposure. These are future work, not
features provided by this hardening.

### Audit 1.0: terminal publisher (A1-010)

One runtime publisher observes terminal state on a one-second cadence, caches
and serializes the latest `phase12-v1` snapshot, and fans it out read-only.
Readers never observe domain state or advance sequence/history/events.
Each client has a one-slot queue: newer snapshots replace pending older ones.
At most 32 terminal clients may subscribe; sends time out after five seconds,
and disconnects cancel tasks and release subscriptions. Sequence gaps can reflect
coalescing, not missing trades. Process/session identity and history/event APIs
retain their existing contract. Before the first publication, readers wait for
the publisher; a domain change appears on its next publication.

### Optional Redis infrastructure

Redis is **EPHEMERAL DISTRIBUTED INFRASTRUCTURE** for terminal Pub/Sub, TTL
snapshot caches, shared bounded WebSocket admission and operational heartbeat.
Optional research coordination adds admission and TTL status/result mirrors around
the existing local PAPER thread worker. `REDIS_ENABLED=false` is the default;
install the backend `[redis]` extra to opt in. `REDIS_REQUIRED=true` fails startup
clearly if Redis is unavailable. Redis-dependent admission fails closed during
outages; local risk, kill/cancel, accounting and execution authority stay in process.

The `phase12-v1` contract and local single-operator/single-worker deployment limits
are unchanged. Redis does not enable remote deployment or distributed execution.
PostgreSQL is the future durable operational layer and is not implemented here.
See [Redis behavior and configuration](docs/REDIS.md) and the
[repository-specific state inventory/design](docs/REDIS_DESIGN.md).

## Phase 8 CoinGecko hardening and optional Yahoo observation — 2026-10-08

CoinGecko enabled Demo and Pro reference modes require `COINGECKO_API_KEY`. Only the exact TLS hosts `https://api.coingecko.com/api/v3` (Demo / `x-cg-demo-api-key`) and `https://pro-api.coingecko.com/api/v3` (Pro / `x-cg-pro-api-key`) receive credentials. Missing configuration or untrusted hosts become provider ERROR without a network request. Disabled mode needs no credentials. HTTP 400/401/403 are ERROR; 429, 5xx, network and decoding errors are DEGRADED with bounded retries. CoinGecko remains tertiary and cannot satisfy core quorum.

Optional Yahoo personal research observation: install `pip install -e '.[yahoo]'`; defaults are `YFINANCE_REFERENCE_ENABLED=false`, `YFINANCE_SYMBOL=ETH-USD`, `YFINANCE_STALE_AFTER_SECONDS=30`. Mapping is explicit: ETH→ETH-USD, BTC→BTC-USD; other startup markets are unavailable, not guessed. The decoded yfinance `AsyncWebSocket` fields `id`, `price`, and Unix-millisecond `time` are validated against a source-time freshness window. Replays, wrong symbols, invalid values and missing/old/future timestamps are rejected. A bounded reconnect loop cancels listener/watchdog tasks and closes sockets. Missing optional dependency is observational ERROR only.

The separately polled `GET /api/v1/references/observations` endpoint and Risk-page card expose observational health, source age, prices and available signed comparison bps. Unavailable comparisons remain null. **Yahoo is excluded from CORE, ALL, the material reference snapshot, economic version/fingerprint, quorum, outlier decisions, risk, agents, authorization, accounting and execution.** It cannot replace RedStone, Kraken or Hyperliquid evidence or authorize trades. The Phase 12 streaming contract remains unchanged.

**Licensing and acceptance:** Yahoo data is for permitted local personal/research observation only. Do not redistribute it publicly or use it for commercial trading without appropriate rights. Live CoinGecko and Yahoo connections, real schemas and reconnect acceptance remain pending. Phase 8.3.1 fixture and local command results are recorded in the roadmap; they do not establish live-provider acceptance. Historical Audit 2.0 issues A2-001–A2-005 are unchanged. No Actions files, Docker, PostgreSQL, signing changes or new trading authority. No additional oracle providers were introduced; unsupported oracle integrations remain prohibited.

## Contributors

HyperAMM is developed and maintained by:

| Contributor | GitHub | LinkedIn |
|-------------|--------|----------|
| **Brandon Torres** — Creator & Lead Developer | [@btorressz](https://github.com/btorressz) | [LinkedIn](https://www.linkedin.com/in/brandon-t-b94312ab) |
| **Alexander Delano** — Contributor | [@thatdela](https://github.com/thatdela) | [LinkedIn](https://www.linkedin.com/in/alexander-delano/) |
