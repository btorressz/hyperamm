# HyperAMM — Codebase & Repository Guide

> **Developer orientation and source map** for the Python/FastAPI + React/TypeScript HyperAMM repository. This document describes the tracked source at Git revision `50f6ab9b42cb`, after merged PR #43 (October 9, 2026). Update it as implementations change.

**Purpose.** This is a code navigation and dependency guide: what the directories/files do, which code calls which domain, what information crosses each boundary, how to run or test it, and where changes belong. For project history see [README](README.md), [Summary](Summary.md), [Architecture](docs/ARCHITECTURE.md) and [Roadmap](docs/ROADMAP.md).

**System identity.** HyperAMM is a *virtual AMM quote compiler for Hyperliquid's central limit order book (CLOB)*, **not** a deployed/custodial AMM pool. The mathematical constant-product/concentrated curve proposes order-book liquidity. **PAPER** is the default; **guarded Hyperliquid TESTNET** is optional. There is **no mainnet/custody/withdrawal/bridging capability**. Supported deployment is loopback, single operator, one backend worker—not a public SaaS or remotely exposed trading service.

## 1. Fast orientation

| Question | Read here |
|---|---|
| Where does the app start? | [`main.py`](backend/app/main.py) (FastAPI lifespan/routers) and [`main.tsx`](frontend/src/main.tsx) (React root) |
| Who owns real decisions and current economic state? | [`runtime.py`](backend/app/runtime.py) and domain implementations under `backend/app/` |
| What generates AMM quote prices and quantities? | [`quote_engine.py`](backend/app/strategy/quote_engine.py) calling [`discretizer.py`](backend/app/amm/discretizer.py) and related AMM modules |
| Who can block order submission? | [`firewall.py`](backend/app/risk/firewall.py), [`authorization.py`](backend/app/risk/authorization.py), [`limits.py`](backend/app/risk/limits.py) and runtime's transmission guard |
| Who submits/cancels orders? | [`order_manager.py`](backend/app/execution/order_manager.py) through [`paper.py`](backend/app/execution/paper.py) or [`hyperliquid.py`](backend/app/execution/hyperliquid.py) |
| Where is accounting truth? | [`service.py`](backend/app/accounting/service.py) and [`ledger.py`](backend/app/accounting/ledger.py) |
| How does the terminal get data? | [`service.py`](backend/app/terminal/service.py) → [`websocket.py`](backend/app/api/websocket.py) → [`terminalSocket.ts`](frontend/src/utils/terminalSocket.ts) → [`terminal.ts`](frontend/src/stores/terminal.ts) |
| How does UI invoke actions? | [`client.ts`](frontend/src/api/client.ts) → FastAPI `/api/v1/` router → `HyperAmmRuntime` method |
| How to find a test? | `backend/tests/` (pytest), `frontend/tests/` (Node test runner and optional Chromium harness) |
| Current acceptance gaps? | [`PHASE1321_ACCEPTANCE.md`](docs/PHASE1321_ACCEPTANCE.md) and [`ROADMAP.md`](docs/ROADMAP.md) |

## 2. Repository shape

~~~text
hyperamm/
├── .env.example                 # example local configuration, not secret storage
├── README.md / Summary.md       # overview / long project narrative
├── AUDIT_REPORT_1.0.md / AUDIT_REPORT_2.0.md
├── CODEBASE.md                  # this source/dependency guide
├── backend/
│   ├── pyproject.toml           # Python package, extras and pytest configuration
│   ├── app/
│   │   ├── main.py              # API process / lifespan / router composition
│   │   ├── runtime.py           # single authoritative strategy engine
│   │   ├── config.py            # environment settings and provider switches
│   │   ├── deployment.py        # loopback and single-worker boundary
│   │   ├── market_data/  amm/  strategy/  agents/
│   │   ├── references/   risk/ execution/ accounting/
│   │   ├── simulation/   research/ml/ terminal/ infrastructure/ api/
│   │   └── dependencies.py / diagnostics.py
│   ├── scripts/                  # terminal schema generator
│   └── tests/                    # pytest unit/integration/acceptance
├── frontend/
│   ├── package.json / package-lock.json / vite.config.ts
│   ├── src/
│   │   ├── main.tsx / App.tsx
│   │   ├── pages/                # twelve active operator screens
│   │   ├── components/           # charts, controls, tables, visual evidence
│   │   ├── api/                  # typed REST consumer
│   │   ├── stores/               # accepted terminal and display preferences
│   │   ├── hooks/                # socket/history/navigation subscriptions
│   │   ├── utils/                # validation, freshness, financial formatting
│   │   ├── contracts/            # generated terminal.schema.json
│   │   ├── types/                # TypeScript domain/wire data contracts
│   │   └── styles.css / phase*.css
│   └── tests/                    # Node/contract + optional browser scripts
├── docs/                         # architecture, domain deep dives, acceptance
└── scripts/                      # local startup and source ZIP packaging
~~~

The repository includes historical styles and components alongside active ones; presence of a file alone does not imply it is mounted into a current route. Python `__init__.py` files mark package/import surfaces; use the package README and import references to identify their actual public exports.

## 3. Dependency/authority graph

~~~text
Hyperliquid public market / explicit DEMO      Optional external oracle sources
               │                                 │
               ▼                                 ▼
     market_data + perp_context          references (consensus)
               │                                 │
               ├─> fair_value / perp_policy      │
               ▼                                 │
       amm virtual-reserve curve                 │
               ▼                                 │
      normalized quote discretizer               │
               ▼                                 │
       strategy inventory + L2/volatility        │
               ▼                                 │
          strategy_quotes                        │
               ▼                                 │
       agent supervisor (bounded advice) <───────┤
               ▼                                 │
            agent_quotes                         │
               ▼                                 ▼
          RiskFirewall <──── inventory / positions / vault / venue uncertainty
               ▼
      structurally validated risk quotes
               ▼
       FinalQuoteAuthorization ──────────────┐
               │                            │
               ▼                            │  versions / fingerprints /
        OrderManager + lock <────────────────┘  last-moment authority recheck
               ▼
    PAPER fill simulation / guarded TESTNET
               ├──────────> accounting ledger / vault ──> risk/capital next cycle
               ├──────────> agent fill telemetry
               └──────────> terminal read-only publication
                                       │
               ┌───────────────────────┴─────────────────────┐
               ▼                                             ▼
        /ws/terminal                                 REST history/events
               │                                             │
               ▼                                             ▼
        validated Zustand state                         TanStack Query
               └────────────────────┬────────────────────────┘
                                    ▼
                     React operator terminal (no authority)
~~~

The runtime is **not** a chain of independently authoritative autonomous agents. Agents may recommend bounded, conservative changes. Mathematical quote generation cannot sign or transmit. Risk and final authorization gate CREATE/REPLACE; CANCEL is allowed to remove risk even when new-order authority is unavailable. The React client displays/requests, but cannot grant its own trading permission.

### 3.1 Process creation, startup and shutdown

1. `app.main` loads `Settings` from environment/optional root `.env`, builds the FastAPI app and mounts REST under the configured `/api/v1` plus `/ws/terminal`.
2. The FastAPI lifespan enforces `validate_local_deployment()`, creates **one** `HyperAmmRuntime` and **one** `SimulationExecutor`; `app.state` owns them.
3. If `REDIS_ENABLED` is opted in, an optional `RedisInfrastructure` and `RedisTerminalTransport` are created; `REDIS_RESEARCH_ENABLED` can wrap research admission. Redis never becomes the engine, ledger or risk authority.
4. `runtime.start_services()` starts the selected normalized feed and runtime tasks. The terminal publisher creates immutable display observations on approximately a one-second cadence.
5. API dependencies retrieve the runtime from `request.app.state.runtime`. Request handlers must not instantiate a second trading engine.
6. Lifespan shutdown joins research work, stops runtime services and closes transport/Redis resources in owned order. Lifecycle lock precedes execution lock when both are needed; feed transport awaits must not deadlock the execution lock.

### 3.2 A live quote cycle

1. `MarketDataService` yields validated ordered BBO/L2; `PerpContextService` may provide mark/oracle/funding/OI context. Invalid/stale LIVE data does **not** fall back silently to DEMO.
2. `calculate_fair_value` computes market fair value; `PerpContextPolicy` may produce a bounded strategy reference.
3. `QuoteEngine` creates neutral AMM curve quotes (constant-product or concentrated), applies inventory hard limits/skew, then conservative realized-volatility/L2-imbalance widening and sizing.
4. `AgentSupervisor` consumes immutable accepted evidence/telemetry and emits bounded pre-risk quote recommendations; SHADOW predictions remain display-only.
5. `ReferenceService` supplies source timestamps, consensus/quality/deviation, so `RiskFirewall` can choose NORMAL, WIDEN, REDUCE or HALT using evidence, exposure, venue uncertainty and vault/capital.
6. After quote normalization and structural checks, `FinalQuoteAuthorization` hashes and versions the bound material state, including market/inventory/perp/reference/agent/risk/accounting.
7. `OrderManager` compares authorized desired levels with resting evidence (KEEP/CREATE/REPLACE/CANCEL). The shared execution lock and last-moment runtime authority callback revalidate the **concrete** request before CREATE/REPLACE.
8. PAPER deterministic touch/cross fills or guarded TESTNET venue/account observations feed agent telemetry and `AccountingService`. Risk consumes updated economics and capital reservation on later cycles. Observations are copied into the terminal, never used as a second authorization path.

**Identity caution.** Terminal sequence IDs, order client IDs, runtime material versions, final-authorization hashes, accounting ledger identities and simulation fingerprints each have distinct meanings. They do not automatically prove complete raw provider history, durable replay or build provenance. See [Architecture](docs/ARCHITECTURE.md).

### 3.3 Emergency kill and recovery

`POST /api/v1/risk/kill` invokes runtime kill handling: revoke future create permission, serialize with in-flight execution, cancel known strategy orders and latch the stop state. If cancellation is unconfirmed, do not claim all orders disappeared. `POST /api/v1/risk/resume` uses existing safety/reconciliation checks to clear the manual latch; **resume does not implicitly start** the strategy. Automatic firewall HALT/recovery is distinct from the manual latch. The Header/QuickStrategyControl React buttons are clients, not alternative authority.

### 3.4 Accounting and PAPER economics

Confirmed normalized fills feed `AccountingService`; the append-only idempotent ledger records trade/fee/funding economic identities and fingerprint linkage. Shared average-cost position transitions derive realized/unrealized PnL, equity, peak/drawdown and capital reservations. A fill/ledger mismatch makes authority unavailable rather than silently adjusting economic truth. TESTNET exposes only supported verified account/position economics and must keep unsupported fields partial/unavailable; no custody or durable database is implied.

### 3.5 Research is isolated

`SimulationExecutor` runs bounded scenarios/grid optimization in isolated PAPER/DEMO state, reusing the production strategy, risk, execution and accounting components with deterministic inputs/clocks. Results are evidence, not strategy deployment or permission to order. Optional offline ML dataset/training/evaluation files are separate from live runtime; JSON classifier artifacts can be loaded for SHADOW inference only.


## 4.1 Backend package: `market_data/`

Normalizes LIVE Hyperliquid and explicit DEMO L2/market/perpetual evidence; enforces timestamps, versions and freshness.

**Wiring:** Hyperliquid SDK or DEMO → MarketDataService → QuoteEngine, ReferenceService, RiskFirewall and TerminalService.

**Domain reference:** [`backend/app/market_data/README.md`](backend/app/market_data/README.md).

| Source | Responsibility |
|---|---|
| [`history.py`](backend/app/market_data/history.py) | Bounded unique normalized midpoint history used by Phase 6 volatility and agent research signals. |
| [`hyperliquid.py`](backend/app/market_data/hyperliquid.py) | Hyperliquid public market-data adapter and normalization logic. |
| [`mock.py`](backend/app/market_data/mock.py) | Deterministic DEMO data source used for local development/tests; it remains explicitly simulated. |
| [`models.py`](backend/app/market_data/models.py) | Normalized market/book/level contracts, data mode, timestamps, freshness and sequence metadata. |
| [`perp_context.py`](backend/app/market_data/perp_context.py) | Normalizes mark, oracle, funding, open interest and account-position context; includes deterministic DEMO context. |
| [`service.py`](backend/app/market_data/service.py) | Starts/stops the selected adapter, accepts ordered updates, exposes the current snapshot and notifies runtime listeners. |

## 4.2 Backend package: `amm/`

Contains pure Decimal virtual-pool, concentration, curve sampling, normalization and quote diagnostics.

**Wiring:** Perpetual/fair-value strategy reference → virtual reserves/curve → normalized neutral quote ladder → QuoteEngine.

**Domain reference:** [`backend/app/amm/README.md`](backend/app/amm/README.md).

| Source | Responsibility |
|---|---|
| [`concentrated.py`](backend/app/amm/concentrated.py) | Applies bounded concentration weighting so more of the fixed liquidity budget can sit near the active reference range. |
| [`constant_product.py`](backend/app/amm/constant_product.py) | Core `x * y = k` invariant, marginal-price and virtual swap calculations. |
| [`diagnostics.py`](backend/app/amm/diagnostics.py) | Read-only effective liquidity grouped by executable price, exposing logical slot collapse without changing order placement. |
| [`discretizer.py`](backend/app/amm/discretizer.py) | Compiles mathematical curve output into normalized CLOB bids/asks using tick size, size precision, budgets and no-cross rules. |
| [`liquidity_curve.py`](backend/app/amm/liquidity_curve.py) | Samples the virtual curve and derives liquidity/reserve movement across quote levels. |
| [`models.py`](backend/app/amm/models.py) | AMM models such as virtual pool state, curve points and quote-lineage fields. |
| [`numeric.py`](backend/app/amm/numeric.py) | Shared Decimal guards, executable quote-distance calculation, and up/down size quantization rules. |
| [`virtual_reserves.py`](backend/app/amm/virtual_reserves.py) | Initializes virtual reserves and recenters the pool around a supplied strategy reference. |

## 4.3 Backend package: `strategy/`

Turns normalized market evidence and the AMM ladder into inventory/perp/volatility-adapted pre-agent proposals.

**Wiring:** Market/perp context + AMM → inventory and market adaptation → strategy_quotes → AgentSupervisor.

**Domain reference:** [`backend/app/strategy/README.md`](backend/app/strategy/README.md).

| Source | Responsibility |
|---|---|
| [`fair_value.py`](backend/app/strategy/fair_value.py) | Computes the normalized market fair value from valid market state. |
| [`inventory.py`](backend/app/strategy/inventory.py) | Phase 5 inventory state, reservation-price skew, side-size skew and hard-limit side suppression. |
| [`market_adaptation.py`](backend/app/strategy/market_adaptation.py) | Phase 6 bounded realized-volatility and top-N L2 imbalance decisions; widening/reduction transforms only. |
| [`models.py`](backend/app/strategy/models.py) | `StrategyConfig`, execution/data modes, strategy state and validated configuration. |
| [`perp_policy.py`](backend/app/strategy/perp_policy.py) | Phase 7 bounded mark/oracle/funding-based perpetual strategy reference. |
| [`quote_engine.py`](backend/app/strategy/quote_engine.py) | Composes fair value, virtual AMM, inventory, perp context and market adaptation into the pre-agent ladder. |

## 4.4 Backend package: `agents/`

Analyzes accepted evidence; composes bounded deterministic/heuristic recommendations and observational ML SHADOW.

**Wiring:** Strategy proposals + telemetry/references/perp → AgentSupervisor → agent_quotes → RiskFirewall.

**Domain reference:** [`backend/app/agents/README.md`](backend/app/agents/README.md).

| Source | Responsibility |
|---|---|
| [`common.py`](backend/app/agents/common.py) | Shared utility functions used by agent policies and evidence calculations. |
| [`config.py`](backend/app/agents/config.py) | Versioned thresholds and constraints for supervisor and individual agent behavior. |
| [`evidence.py`](backend/app/agents/evidence.py) | Builds normalized immutable input evidence for deterministic/heuristic agents. |
| [`execution_quality.py`](backend/app/agents/execution_quality.py) | Measures observed capture, markout, churn and available PAPER execution-lifecycle quality. |
| [`liquidity_quality.py`](backend/app/agents/liquidity_quality.py) | Assesses top-N L2 depth, spreads, concentration, imbalance and market instability. |
| [`ml_features.py`](backend/app/agents/ml_features.py) | Fixed passive-adverse-v1 feature order, units and missing-input validation. |
| [`model_artifact.py`](backend/app/agents/model_artifact.py) | Validates bounded JSON shadow-model artifact and fingerprint/provenance without executable deserialization. |
| [`models.py`](backend/app/agents/models.py) | Agent input/output/state and evidence/version/health contracts. |
| [`perp_crowding.py`](backend/app/agents/perp_crowding.py) | Heuristic funding/OI/basis crowding assessment from distinct timestamped perp observations. |
| [`predictive_adverse_selection.py`](backend/app/agents/predictive_adverse_selection.py) | Observational SHADOW-only adverse-fill inference; no quote/execution authority. |
| [`regime.py`](backend/app/agents/regime.py) | Heuristic market-regime classification using volatility, momentum, basis and reference context. |
| [`snapshot.py`](backend/app/agents/snapshot.py) | Published complete cycle agent-state snapshot used by API and terminal reads. |
| [`supervisor.py`](backend/app/agents/supervisor.py) | Conservatively combines agent recommendations and applies bounded quote transformations. |
| [`toxic_flow.py`](backend/app/agents/toxic_flow.py) | Observed post-fill adverse-selection/markout telemetry with immutable first-eligible horizon evidence. |

## 4.5 Backend package: `references/`

Maintains independent price-source health, consensus and outlier evidence; Yahoo is observational only.

**Wiring:** External and native price observations → ReferenceService → consensus/deviation evidence → firewall and agent evidence.

**Domain reference:** [`backend/app/references/README.md`](backend/app/references/README.md).

| Source | Responsibility |
|---|---|
| [`consensus.py`](backend/app/references/consensus.py) | Deterministic median/outlier/quorum policy and confidence classification. |
| [`models.py`](backend/app/references/models.py) | Provider IDs, transports, provider status, normalized evidence, consensus and deviation contracts. |
| [`providers.py`](backend/app/references/providers.py) | RedStone Live + HTTP fallback, Kraken, CoinGecko and supporting provider adapters/normalization. |
| [`service.py`](backend/app/references/service.py) | Owns provider lifecycles, combines native Hyperliquid evidence with external evidence, versions snapshots and wakes strategy recomputation. |
| [`yahoo.py`](backend/app/references/yahoo.py) | Optional Yahoo Finance research observation; explicitly excluded from the material price-reference/authorization quorum. |

## 4.6 Backend package: `risk/`

Evaluates exposure, provider disagreement, capital and kill/firewall state; binds the only final quote authorization.

**Wiring:** agent_quotes + references + inventory/accounting → RiskFirewall → conservative transformation → FinalQuoteAuthorization → execution gate.

**Domain reference:** [`backend/app/risk/README.md`](backend/app/risk/README.md).

| Source | Responsibility |
|---|---|
| [`authorization.py`](backend/app/risk/authorization.py) | Canonical SHA-256 fingerprints and `FinalQuoteAuthorization` binding quote/evidence/risk/agent/accounting versions. |
| [`firewall.py`](backend/app/risk/firewall.py) | Phase 8 exposure, reference deviation, liquidation, drawdown, capital and venue-uncertainty evaluation; state machine and conservative quote transform. |
| [`kill_switch.py`](backend/app/risk/kill_switch.py) | Manual kill/resume state handling used by the runtime. |
| [`limits.py`](backend/app/risk/limits.py) | Structural quote validation and execution-authority checks used close to transmission. |
| [`models.py`](backend/app/risk/models.py) | Core risk status model. |

## 4.7 Backend package: `execution/`

Reconciles authorized quote levels to orders, maintains PAPER fill state and guarded TESTNET venue interactions.

**Wiring:** authorized_quotes → reconciler/OrderManager + lock → PAPER or TESTNET; order/fill states → telemetry/accounting/terminal.

**Domain reference:** [`backend/app/execution/README.md`](backend/app/execution/README.md).

| Source | Responsibility |
|---|---|
| [`base.py`](backend/app/execution/base.py) | Common execution-adapter interface. |
| [`fills.py`](backend/app/execution/fills.py) | Bounded/simple fill storage helper. |
| [`hyperliquid.py`](backend/app/execution/hyperliquid.py) | Guarded Hyperliquid TESTNET adapter, signing, venue reconciliation, position/account-state normalization and uncertain-order handling. |
| [`models.py`](backend/app/execution/models.py) | Normalized order request, strategy order and fill contracts. |
| [`order_manager.py`](backend/app/execution/order_manager.py) | Serializes reconciliation, performs venue reconciliation when available, rechecks authority before CREATE/REPLACE, and issues cancel/submit calls. |
| [`paper.py`](backend/app/execution/paper.py) | In-memory deterministic PAPER order/fill adapter used by runtime and simulation. |
| [`quote_reconciler.py`](backend/app/execution/quote_reconciler.py) | Deterministically compares desired quote levels with existing orders and emits KEEP/CREATE/REPLACE/CANCEL actions. |

## 4.8 Backend package: `accounting/`

Maintains deterministic noncustodial economic truth, immutable ledger chain and conservative capital sufficiency.

**Wiring:** fills/marks/funding → ledger/PnL/VaultSnapshot → capital/risk authority and read-only terminal.

**Domain reference:** [`backend/app/accounting/README.md`](backend/app/accounting/README.md).

| Source | Responsibility |
|---|---|
| [`config.py`](backend/app/accounting/config.py) | Research accounting configuration: initial capital, fees, funding/capital limits and retention behavior. |
| [`fees.py`](backend/app/accounting/fees.py) | Deterministic PAPER fee calculations and identities. |
| [`funding.py`](backend/app/accounting/funding.py) | Deterministic funding interval/economic calculations for research accounting. |
| [`ledger.py`](backend/app/accounting/ledger.py) | Append-only idempotent ledger, event identity/economic fingerprints and chained ledger fingerprint. |
| [`models.py`](backend/app/accounting/models.py) | Ledger/accounting/vault contracts, completeness and execution-accounting consistency state. |
| [`pnl.py`](backend/app/accounting/pnl.py) | Shared average-cost position transitions, reversal handling and PnL breakdown helpers. |
| [`service.py`](backend/app/accounting/service.py) | Stateful accounting authority coordinating fills, fees, funding, marks, reservations, snapshots, consistency checks and reconciliation. |
| [`vault.py`](backend/app/accounting/vault.py) | Capital reservation and vault-related helpers. |

## 4.9 Backend package: `simulation/`

Reuses strategy/risk/execution/accounting in isolated deterministic PAPER scenarios and bounded optimization.

**Wiring:** isolated scenarios/replay → production-stack components with PAPER only → metrics/fingerprints/optimizer → research REST.

**Domain reference:** [`backend/app/simulation/README.md`](backend/app/simulation/README.md).

| Source | Responsibility |
|---|---|
| [`config.py`](backend/app/simulation/config.py) | Simulation limits, accounting assumptions and optimization objective configuration. |
| [`engine.py`](backend/app/simulation/engine.py) | Recreates fresh strategy/agent/risk/execution/accounting state and runs the production pipeline frame-by-frame. |
| [`executor.py`](backend/app/simulation/executor.py) | Lifespan-owned single-slot research worker thread/private event loop so heavy research does not block FastAPI. |
| [`metrics.py`](backend/app/simulation/metrics.py) | Accumulates PnL, drawdown, inventory, fill, spread-capture, markout, churn, risk and regime metrics. |
| [`models.py`](backend/app/simulation/models.py) | Immutable datasets, frames, traces, metrics, candidate/optimization results and stable fingerprints. |
| [`optimizer.py`](backend/app/simulation/optimizer.py) | Deterministic bounded grid search over explicit strategy/agent allowlists with immutable safety fields, baseline and train/validation separation. |
| [`references.py`](backend/app/simulation/references.py) | Builds explicitly simulated provider evidence using the real reference contracts/policy. |
| [`replay.py`](backend/app/simulation/replay.py) | Bounded dataset/frame replay helpers. |
| [`scenarios.py`](backend/app/simulation/scenarios.py) | Built-in deterministic market/perp/reference stress scenarios. |
| [`service.py`](backend/app/simulation/service.py) | Research-facing facade that forces DEMO/PAPER strategy copies and exposes scenario/optimization operations. |
| [`version.py`](backend/app/simulation/version.py) | Code-owned simulation engine version used in provenance/fingerprints. |

## 4.10 Backend package: `terminal/`

Publishes read-only versioned snapshots/history/events without influencing the engine.

**Wiring:** runtime authoritative outputs → TerminalService snapshot → in-process or Redis observational fanout → /ws/terminal and React.

**Domain reference:** [`backend/app/terminal/README.md`](backend/app/terminal/README.md).

| Source | Responsibility |
|---|---|
| [`history.py`](backend/app/terminal/history.py) | Bounded in-memory current-session history, supported ranges and deterministic response sampling. |
| [`models.py`](backend/app/terminal/models.py) | Code-owned terminal contract version, `TerminalSnapshot`, history points, events and health models. |
| [`service.py`](backend/app/terminal/service.py) | Builds observations, assigns process/session/sequence metadata, appends safe history, aggregates health and normalizes/redacts structured events. |

## 4.11 Backend package: `api/`

Thin REST/WebSocket routers that delegate into lifespan-owned runtime/research services.

**Wiring:** HTTP controls/read endpoints → app.state.runtime; heavy research → app.state.simulation_executor; WS → serialized transport.

**Domain reference:** [`backend/app/api/README.md`](backend/app/api/README.md).

| Source | Responsibility |
|---|---|
| [`accounting.py`](backend/app/api/accounting.py) | Read-only vault, PnL, position, ledger and accounting-event endpoints. |
| [`agents.py`](backend/app/api/agents.py) | Read-only Phase 9 agent state/events. |
| [`health.py`](backend/app/api/health.py) | Runtime/service health summary. |
| [`markets.py`](backend/app/api/markets.py) | Normalized market and order-book reads. |
| [`orders.py`](backend/app/api/orders.py) | Read-only order/fill views. |
| [`positions.py`](backend/app/api/positions.py) | Normalized inventory/position observability. |
| [`risk.py`](backend/app/api/risk.py) | Risk state/evidence/events/final authorization plus manual kill/resume controls. |
| [`simulation.py`](backend/app/api/simulation.py) | Bounded research scenario and optimizer endpoints using `SimulationExecutor`. |
| [`strategy.py`](backend/app/api/strategy.py) | Strategy state/config plus approved start/stop/update controls and AMM/market/perp summaries. |
| [`terminal.py`](backend/app/api/terminal.py) | Read-only bounded terminal history/events APIs. |
| [`websocket.py`](backend/app/api/websocket.py) | Primary current-state `/ws/terminal` stream. |

## 5. Backend top-level and optional infrastructure

| Source | Role |
|---|---|
| [`config.py`](backend/app/config.py) | Pydantic settings loaded from environment and optional root .env; mode/provider/Redis/testnet switches. |
| [`dependencies.py`](backend/app/dependencies.py) | FastAPI dependency that retrieves the lifespan-owned runtime from app.state. |
| [`deployment.py`](backend/app/deployment.py) | Loopback-only/single-worker launch and request boundary; not user authentication. |
| [`diagnostics.py`](backend/app/diagnostics.py) | Sanitizes public diagnostics, sensitive paths and credential-like errors. |
| [`main.py`](backend/app/main.py) | FastAPI application factory module and lifespan wiring for runtime, research executor, optional Redis and routers. |
| [`runtime.py`](backend/app/runtime.py) | HyperAmmRuntime: authoritative composition root, lifecycle/execution locking, strategy/risk/accounting pipeline and terminal publisher. |

### 5.1 Infrastructure and offline research

**`backend/app/infrastructure/`**

| Source | Role |
|---|---|
| [`redis.py`](backend/app/infrastructure/redis.py) | Optional redis.asyncio wrapper, health reporting, bounded Redis leases/admission and TTL infrastructure. |
| [`research.py`](backend/app/infrastructure/research.py) | Optional shared research admission/status/result mirrors around the unchanged local SimulationExecutor. |
| [`terminal_transport.py`](backend/app/infrastructure/terminal_transport.py) | Latest-only in-process transport and opt-in Redis mirror/relay; no trading-state ownership. |

**`backend/app/research/ml/`**

| Source | Role |
|---|---|
| [`dataset.py`](backend/app/research/ml/dataset.py) | Builds deterministic offline labeled datasets from typed historical normalized evidence. |
| [`shadow_evaluation.py`](backend/app/research/ml/shadow_evaluation.py) | Evaluates observational shadow predictions separately from execution or strategy authority. |
| [`training.py`](backend/app/research/ml/training.py) | Offline optional scikit-learn logistic model training/validation CLI and inert JSON artifact generation. |
| [`validation.py`](backend/app/research/ml/validation.py) | Research dataset and validation split/metric constraints for offline modeling. |

**Redis boundary:** Optional `REDIS_ENABLED` provides latest-only serialized terminal Pub/Sub/cache, expiring client admission, heartbeat, and optional bounded research admission/result mirrors. It does **not** distribute economic decision state, enable multiple Uvicorn workers, or add operator authentication. `InProcessTerminalTransport` remains the ordinary local path. See [Redis runtime](docs/REDIS.md) and [Redis design](docs/REDIS_DESIGN.md).

**Configuration and safety:** [`config.py`](backend/app/config.py) controls backend-only credentials/provider enables. [`deployment.py`](backend/app/deployment.py) enforces loopback, host/origin and single-worker boundaries; it is not identity-based authorization. `.env` and private keys are not part of the repo's tracked source.


## 6. Frontend: boot, state and routes

**Bootstrap:** [`main.tsx`](frontend/src/main.tsx) mounts React StrictMode inside TanStack Query; [`App.tsx`](frontend/src/App.tsx) starts the terminal socket, reads validated Zustand state, applies the display-only freshness projection, loads health, and renders one page by the typed route registry.

**Page routing:** [`navigation.ts`](frontend/src/utils/navigation.ts) defines twelve hash URLs, [`usePageNavigation.ts`](frontend/src/hooks/usePageNavigation.ts) subscribes to URL changes, and [`Sidebar.tsx`](frontend/src/components/Sidebar.tsx) uses accessible links. Refresh/back/forward preserve the active page. `Planned.tsx` is not one of the twelve live routes.

**Rendering contract:** UI receives `TerminalState` from [`index.ts`](frontend/src/types/index.ts) after the runtime JSON schema validation. It does not import Python domain implementations or recompute authorization. Financial values often arrive as Decimal strings. Chart-only conversions may use JS numbers; order evidence sorting uses exact decimal-aware logic when material precision matters.

### 6.1 Pages and what they consume

| Page module | Operator purpose |
|---|---|
| [`Agents.tsx`](frontend/src/pages/Agents.tsx) | Supervisory-agent readiness, evidence, reasons and SHADOW observation. |
| [`AmmSettings.tsx`](frontend/src/pages/AmmSettings.tsx) | Advanced strategy configuration and settings editor host. |
| [`Analytics.tsx`](frontend/src/pages/Analytics.tsx) | Performance, history, attribution and risk/research analytics. |
| [`Dashboard.tsx`](frontend/src/pages/Dashboard.tsx) | Primary workspace: KPI cards, chart, book, controls, liquidity and recent execution. |
| [`Execution.tsx`](frontend/src/pages/Execution.tsx) | Active/recent order evidence, status filters/sorting, expandable rows, fills and reconciliation timeline. |
| [`Logs.tsx`](frontend/src/pages/Logs.tsx) | Read-only structured terminal and operational event history. |
| [`Markets.tsx`](frontend/src/pages/Markets.tsx) | Market microstructure, L2 book, price chart, perp context and references. |
| [`Planned.tsx`](frontend/src/pages/Planned.tsx) | Legacy/planned-page placeholder component; not an active route in the 12-page navigation. |
| [`Risk.tsx`](frontend/src/pages/Risk.tsx) | Manual kill, firewall/authorization status, projected exposure and risk events. |
| [`Settings.tsx`](frontend/src/pages/Settings.tsx) | Local terminal display preferences and diagnostic settings. |
| [`Simulation.tsx`](frontend/src/pages/Simulation.tsx) | Scenario simulation and bounded research optimization user interface. |
| [`Strategy.tsx`](frontend/src/pages/Strategy.tsx) | Strategy control, quote-stage/lineage detail, AMM and inventory/perp panels. |
| [`Vault.tsx`](frontend/src/pages/Vault.tsx) | Research accounting, equity/PnL, ledger and provenance observability. |

### 6.2 Components by responsibility

| UI component | Role |
|---|---|
| [`AccountingLedger.tsx`](frontend/src/components/AccountingLedger.tsx) | Read-only ledger rows and accounting provenance. |
| [`AgentPanel.tsx`](frontend/src/components/AgentPanel.tsx) | Agent-specific status, outputs and explanatory evidence. |
| [`Badge.tsx`](frontend/src/components/Badge.tsx) | Compact severity/status label. |
| [`EffectiveLiquidity.tsx`](frontend/src/components/EffectiveLiquidity.tsx) | Read-only distinct executable-price depth and logical-slot collapse warnings. |
| [`EventTimeline.tsx`](frontend/src/components/EventTimeline.tsx) | General retained events/history presentation. |
| [`ExecutionActivity.tsx`](frontend/src/components/ExecutionActivity.tsx) | Execution/reconciliation activity summary. |
| [`ExecutionTimeline.tsx`](frontend/src/components/ExecutionTimeline.tsx) | Phase 13.2.1 read-only order/reconciliation event timeline scoped to the observed session. |
| [`Header.tsx`](frontend/src/components/Header.tsx) | Selected market and current/historical mode/risk status; immediate manual kill control. |
| [`HistoryChart.tsx`](frontend/src/components/HistoryChart.tsx) | Retained terminal history plotted in financial series. |
| [`InventoryPanel.tsx`](frontend/src/components/InventoryPanel.tsx) | Position, targets and inventory policy state. |
| [`InventorySkewChart.tsx`](frontend/src/components/InventorySkewChart.tsx) | Inventory-skew visualization. |
| [`LiquidityCurve.tsx`](frontend/src/components/LiquidityCurve.tsx) | Visual representation of virtual-liquidity curve outputs. |
| [`LiquidityDistributionChart.tsx`](frontend/src/components/LiquidityDistributionChart.tsx) | Neutral/strategy/authorized quote distribution visualizations. |
| [`LiquidityPipeline.tsx`](frontend/src/components/LiquidityPipeline.tsx) | One quote-level lineage through the transformation and final-authorization stages. |
| [`MarketAdaptationPanel.tsx`](frontend/src/components/MarketAdaptationPanel.tsx) | Phase 6 volatility/L2-imbalance policy evidence. |
| [`MetricCards.tsx`](frontend/src/components/MetricCards.tsx) | Reusable statistic-card presentation. |
| [`NavIcon.tsx`](frontend/src/components/NavIcon.tsx) | Sidebar icon primitives added in Phase 13.1. |
| [`OrderBook.tsx`](frontend/src/components/OrderBook.tsx) | Normalized visible L2 bids/asks, spread and cumulative depth. |
| [`PerpContextPanel.tsx`](frontend/src/components/PerpContextPanel.tsx) | Mark/oracle/funding/OI and strategy-reference evidence. |
| [`PhaseStatus.tsx`](frontend/src/components/PhaseStatus.tsx) | Phase/status presentation helper. |
| [`PnlBreakdown.tsx`](frontend/src/components/PnlBreakdown.tsx) | PnL breakdown including realized/unrealized/funding/fees. |
| [`PriceChart.tsx`](frontend/src/components/PriceChart.tsx) | Price-series/chart component. |
| [`PriceLiquidityChart.tsx`](frontend/src/components/PriceLiquidityChart.tsx) | Lightweight Charts market/reference/authorized quote history with bounded timescales. |
| [`QuickStrategyControl.tsx`](frontend/src/components/QuickStrategyControl.tsx) | Approved strategy start/stop/kill/resume buttons and compact controls. |
| [`QuoteLadder.tsx`](frontend/src/components/QuoteLadder.tsx) | Pre-agent/post-agent/final quote tables with conservative order-evidence classification. |
| [`RecentExecution.tsx`](frontend/src/components/RecentExecution.tsx) | OrderTable; common order rows, filtering/sorting/details and recent activity. |
| [`RiskFirewallPanel.tsx`](frontend/src/components/RiskFirewallPanel.tsx) | Reference-source health, risk reasons and authorization/evidence display. |
| [`Sidebar.tsx`](frontend/src/components/Sidebar.tsx) | Twelve persistent routes, collapse setting and accessible mobile drawer. |
| [`SimulationPanel.tsx`](frontend/src/components/SimulationPanel.tsx) | Simulation output presentation helper. |
| [`StrategyAttribution.tsx`](frontend/src/components/StrategyAttribution.tsx) | Strategy movement/attribution evidence. |
| [`StrategyControls.tsx`](frontend/src/components/StrategyControls.tsx) | Config form, edit/dirty/reset/save/error workflows and backend validation messages. |
| [`SystemHealth.tsx`](frontend/src/components/SystemHealth.tsx) | Subsystem/transport health evidence. |
| [`TerminalBoundary.tsx`](frontend/src/components/TerminalBoundary.tsx) | React error boundary around the active page. |
| [`TerminalDiagnostics.tsx`](frontend/src/components/TerminalDiagnostics.tsx) | Envelope age, session, rejections and transport/source health. |
| [`TerminalKpis.tsx`](frontend/src/components/TerminalKpis.tsx) | Summary portfolio/position/equity/PnL/capital/quote health metrics. |
| [`TerminalPrimitives.tsx`](frontend/src/components/TerminalPrimitives.tsx) | Shared panel, metrics, empty/loading and status-banner UI. |
| [`VaultSummary.tsx`](frontend/src/components/VaultSummary.tsx) | Research vault/equity/capital summary. |
| [`YahooObservationPanel.tsx`](frontend/src/components/YahooObservationPanel.tsx) | Research-only Yahoo provider readings; never quote-authoritative. |

### 6.3 Hooks, stores, transport and utilities

**Hooks**

| File | Responsibility |
|---|---|
| [`useMobileNavigation.ts`](frontend/src/hooks/useMobileNavigation.ts) | Media-query subscription for responsive sidebar behavior. |
| [`usePageNavigation.ts`](frontend/src/hooks/usePageNavigation.ts) | Hash-route subscription with safe fallback and document navigation. |
| [`useTerminalHistory.ts`](frontend/src/hooks/useTerminalHistory.ts) | TanStack Query session-bound bounded terminal history reads. |
| [`useTerminalSocket.ts`](frontend/src/hooks/useTerminalSocket.ts) | Hook that owns/cleans up the current terminal WebSocket controller. |

**Zustand stores**

| File | Responsibility |
|---|---|
| [`display.ts`](frontend/src/stores/display.ts) | Persisted local UI settings: density, history range/size and collapsed sidebar. |
| [`terminal.ts`](frontend/src/stores/terminal.ts) | Zustand validated terminal snapshot, active/retired identity, sequence, freshness, connection and rejection counters. |

**Utilities**

| File | Responsibility |
|---|---|
| [`authorizationLineage.ts`](frontend/src/utils/authorizationLineage.ts) | Read-only final quote evidence checks and authorized fingerprint display. |
| [`effectiveLiquidity.ts`](frontend/src/utils/effectiveLiquidity.ts) | Aggregate normalized quotes at effective executable prices for display. |
| [`format.ts`](frontend/src/utils/format.ts) | Financial/date/status formatting helpers. |
| [`freshness.ts`](frontend/src/utils/freshness.ts) | Read-only aging/projection and source-price selection; never renews provider data. |
| [`navigation.ts`](frontend/src/utils/navigation.ts) | Twelve-page typed hash-route registry. |
| [`orderView.ts`](frontend/src/utils/orderView.ts) | Order status/mode evidence, exact Decimal parsing, filtering and sorting. |
| [`quoteEvidence.ts`](frontend/src/utils/quoteEvidence.ts) | Matches proposal/authorized quotes to conservative retained-order statuses. |
| [`terminalHistory.ts`](frontend/src/utils/terminalHistory.ts) | Bounded merge/sample utilities for chart history and session identity. |
| [`terminalIntegrity.ts`](frontend/src/utils/terminalIntegrity.ts) | Terminal 5s age/2s skew guards, ordering helpers and replay diagnostics. |
| [`terminalSocket.ts`](frontend/src/utils/terminalSocket.ts) | Single WebSocket controller with accepted-frame watchdog, bounded reconnect and generation ownership. |
| [`validateTerminal.ts`](frontend/src/utils/validateTerminal.ts) | Runtime validation of the versioned generated terminal schema. |

**REST:** [`client.ts`](frontend/src/api/client.ts) is the central fetch client for bounded history, accounting, risk, agents, simulation and allowed controls. [`vite.config.ts`](frontend/vite.config.ts) proxies `/api` to `http://127.0.0.1:8000` and `/ws` to `ws://127.0.0.1:8000` while Vite serves the frontend on port **5173**.

**WebSocket:** `startTerminalSocket()` owns one controller (also across StrictMode replacements). Opening the socket leaves health CONNECTING until a **schema-valid, timely, identity/sequence-valid** frame is accepted. Bad/stale/future/replayed frames cannot refresh `lastValidFrameAt`. Retired identities and out-of-order sequences are tracked conservatively, and stale/closed sockets reconnect with bounded backoff.

**Source freshness:** Envelope-time freshness is separate from underlying provider timestamps; a newly received JSON frame does not renew an old RedStone, Kraken, CoinGecko or Hyperliquid source. Display projections are observational. With historical/disconnected evidence, relevant pages identify last-known status instead of claiming current prices/active venue certainty.

**UI safety:** `QuickStrategyControl` and `Header` invoke established REST controls; they do not grant quote authority. `quoteEvidence` and `orderView` distinguish proposals, authorized levels, open/partial/unknown/historical order evidence. PR #43 added execution filters/sorting/details and a read-only reconciliation timeline without changing backend order states.

### 6.4 Versioned terminal schema

[`models.py`](backend/app/terminal/models.py) owns the Pydantic `phase12-v1` snapshot schema. [`generate_terminal_contract.py`](backend/scripts/generate_terminal_contract.py) is the generator; the committed artifact is [`terminal.schema.json`](frontend/src/contracts/terminal.schema.json). [`validateTerminal.ts`](frontend/src/utils/validateTerminal.ts) validates incoming JSON **before** it reaches accepted app state. Generated-schema currency should be checked; do not edit only the frontend JSON by hand, and do not paper over a mismatch by disabling tests.

### 6.5 Styles and build

[`styles.css`](frontend/src/styles.css) and tracked `frontend/src/phase*.css` are historical/current stylesheet layers; [`phase13.css`](frontend/src/phase13.css) contains the shared institutional dark visual foundation. [`package.json`](frontend/package.json) declares React, TypeScript, Vite, Zustand, TanStack Query and Lightweight Charts. `npm test` invokes [`run.cjs`](frontend/tests/run.cjs) to compile selected TypeScript modules then execute Node's case runner.


## 7. Interface boundaries and request mapping

| Trigger | Client/transport | Backend owner | Result/authority |
|---|---|---|---|
| Observe terminal | `useTerminalSocket` → `/ws/terminal` | `TerminalService` / `api.websocket` | Versioned read-only snapshot; **no mutation** |
| Read chart history/events | `useTerminalHistory` / REST | `api.terminal` → bounded history/event buffer | Current-session read-only data |
| Observe market/perp | Markets/Dashboard, REST/WS | `api.markets` / `api.strategy` | Normalized BBO/L2/mark/oracle/funding evidence |
| Change configuration | AMM Settings → `PUT /api/v1/strategy` | `api.strategy` → `runtime.update_config` | Backend-validated change; invalid configs return 422 |
| Start/stop | QuickStrategyControl → POST | `api.strategy` → runtime | Strategy intent with runtime guards |
| Emergency kill/resume | Header/Risk → POST | `api.risk` → runtime kill state | Backend latch + cancellation/reconciliation |
| Observe orders/fills | Execution/RecentExecution and REST | `api.orders` / terminal publisher | Retained order/fill **evidence**, not proof of all venue history |
| Observe risk/references | Risk and reference panels | `api.risk` | Snapshot, reasons, authorization, sources |
| Observe agents | Agents panel | `api.agents` | Read-only bounded agent state/events |
| Observe vault/ledger | Vault and REST | `api.accounting` | Read-only economic snapshots/ledger |
| Run scenario or optimize | Simulation → `api.simulation` | `SimulationExecutor` / SimulationService | Isolated PAPER research; never auto-deploy |

Typical API prefixes/routes are described in [README's API map](README.md) and directly under `backend/app/api/`. The OpenAPI explorer at `http://127.0.0.1:8000/docs` reflects current mounted REST handlers. WebSocket is `/ws/terminal`, outside the REST prefix.


## 8. Environment, installation and local operation

**Supported environment:** Python 3.12+ (package minimum), local Node/npm compatible with the checked-in Vite toolchain, one FastAPI worker bound to `127.0.0.1`. Run from repo root unless indicated.

~~~bash
cp .env.example .env
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest -q
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
~~~

In a separate terminal:

~~~bash
cd frontend
npm ci
npm test
npm run typecheck
npm run build
npm run dev
~~~

Browser: `http://127.0.0.1:5173`; REST/OpenAPI: `http://127.0.0.1:8000/docs`. Convenience wrappers: [`run_backend.sh`](scripts/run_backend.sh) and [`run_frontend.sh`](scripts/run_frontend.sh). [`package_zip.sh`](scripts/package_zip.sh) creates a source ZIP while excluding local credentials, venv, node_modules and build/test caches.

**Dependencies:** [`pyproject.toml`](backend/pyproject.toml) defines core packages and `test`, `redis`, `ml`, `yahoo` optional extras. The declared direct NumPy dependency is currently retained as project policy, not the live Decimal math engine. `frontend/package-lock.json` pins npm resolution.

**Sample modes:** [`.env.example`](.env.example) uses `MARKET_DATA_MODE=DEMO` and `EXECUTION_MODE=PAPER`. When switching to LIVE, it means public market observations, **not** mainnet execution. Signed TESTNET requires explicit mode, opt-in flag and backend-only account/key. Keep secrets out of frontend, Git logs, screenshots and committed fixtures.

**Providers:** RedStone (primary external oracle, live with one-provider HTTP fallback), native Hyperliquid oraclePx, Kraken (independent exchange), CoinGecko (tertiary aggregate). Hyperliquid mid/mark supply separate venue/perp evidence. Yahoo is a research observation only and cannot enter quote authority. Provider health, source timestamps and quorum constraints are not browser freshness decisions.

**Redis:** Disabled by default. Enable only for its optional ephemeral terminal fanout, client admission and research coordination with a locally provisioned Redis instance. Disabling Redis must leave core local PAPER strategy operation functional. Remote/public deployment and multi-worker execution are **not** made safe by Redis.


## 9. Testing, fixture ownership and acceptance

**Core AMM/strategy/risk:** [`test_amm.py`](backend/tests/test_amm.py), [`test_api.py`](backend/tests/test_api.py), [`test_execution.py`](backend/tests/test_execution.py), [`test_integration.py`](backend/tests/test_integration.py), [`test_strategy_risk.py`](backend/tests/test_strategy_risk.py).

**Market/inventory/adaptation/perp:** [`test_phase5_inventory.py`](backend/tests/test_phase5_inventory.py), [`test_phase5_runtime.py`](backend/tests/test_phase5_runtime.py), [`test_phase6_market_adaptation.py`](backend/tests/test_phase6_market_adaptation.py), [`test_phase6_runtime.py`](backend/tests/test_phase6_runtime.py), [`test_phase7_perp_context.py`](backend/tests/test_phase7_perp_context.py), [`test_phase7_runtime.py`](backend/tests/test_phase7_runtime.py).

**Reference/firewall/provider:** [`test_phase82_redstone_http.py`](backend/tests/test_phase82_redstone_http.py), [`test_phase831_acceptance.py`](backend/tests/test_phase831_acceptance.py), [`test_phase8_authorization.py`](backend/tests/test_phase8_authorization.py), [`test_phase8_provider_observations.py`](backend/tests/test_phase8_provider_observations.py), [`test_phase8_references.py`](backend/tests/test_phase8_references.py), [`test_phase8_risk_firewall.py`](backend/tests/test_phase8_risk_firewall.py), [`test_phase8_runtime.py`](backend/tests/test_phase8_runtime.py), [`test_phase8_static.py`](backend/tests/test_phase8_static.py).

**Agents/ML shadow:** [`test_agent_expansion.py`](backend/tests/test_agent_expansion.py), [`test_phase9_agents.py`](backend/tests/test_phase9_agents.py), [`test_phase9_runtime.py`](backend/tests/test_phase9_runtime.py), [`test_phase9_static.py`](backend/tests/test_phase9_static.py).

**Simulation/optimization:** [`test_phase10_api.py`](backend/tests/test_phase10_api.py), [`test_phase10_executor.py`](backend/tests/test_phase10_executor.py), [`test_phase10_optimizer.py`](backend/tests/test_phase10_optimizer.py), [`test_phase10_scenarios.py`](backend/tests/test_phase10_scenarios.py), [`test_phase10_simulation.py`](backend/tests/test_phase10_simulation.py), [`test_phase10_static.py`](backend/tests/test_phase10_static.py).

**Ledger/vault/accounting:** [`test_phase11_accounting.py`](backend/tests/test_phase11_accounting.py), [`test_phase11_api_static.py`](backend/tests/test_phase11_api_static.py), [`test_phase11_fees_funding.py`](backend/tests/test_phase11_fees_funding.py), [`test_phase11_ledger.py`](backend/tests/test_phase11_ledger.py), [`test_phase11_runtime.py`](backend/tests/test_phase11_runtime.py), [`test_phase11_simulation.py`](backend/tests/test_phase11_simulation.py).

**Terminal, WS, frontend contracts:** [`test_audit_local_publisher.py`](backend/tests/test_audit_local_publisher.py), [`test_audit_read_observations.py`](backend/tests/test_audit_read_observations.py), [`test_audit_terminal_contract.py`](backend/tests/test_audit_terminal_contract.py), [`test_phase121_websocket_reliability.py`](backend/tests/test_phase121_websocket_reliability.py), [`test_phase122_amm_hardening.py`](backend/tests/test_phase122_amm_hardening.py), [`test_phase12_history.py`](backend/tests/test_phase12_history.py), [`test_phase12_static.py`](backend/tests/test_phase12_static.py), [`test_phase12_terminal.py`](backend/tests/test_phase12_terminal.py), [`test_phase12_websocket.py`](backend/tests/test_phase12_websocket.py).

**Redis optional transport/research:** [`test_redis_infrastructure.py`](backend/tests/test_redis_infrastructure.py), [`test_redis_lifespan.py`](backend/tests/test_redis_lifespan.py).

**Frontend Node cases:**

- [`agents.test.cjs`](frontend/tests/agents.test.cjs) — focused module/regression coverage for agents.
- [`audit-lineage.test.cjs`](frontend/tests/audit-lineage.test.cjs) — focused module/regression coverage for audit lineage.
- [`effective-liquidity.test.cjs`](frontend/tests/effective-liquidity.test.cjs) — focused module/regression coverage for effective liquidity.
- [`freshness.test.cjs`](frontend/tests/freshness.test.cjs) — focused module/regression coverage for freshness.
- [`navigation.test.cjs`](frontend/tests/navigation.test.cjs) — focused module/regression coverage for navigation.
- [`order-view.test.cjs`](frontend/tests/order-view.test.cjs) — focused module/regression coverage for order view.
- [`quote-evidence.test.cjs`](frontend/tests/quote-evidence.test.cjs) — focused module/regression coverage for quote evidence.
- [`terminal-integrity.test.cjs`](frontend/tests/terminal-integrity.test.cjs) — focused module/regression coverage for terminal integrity.
- [`terminal.test.cjs`](frontend/tests/terminal.test.cjs) — focused module/regression coverage for terminal.
- [`yahoo.test.cjs`](frontend/tests/yahoo.test.cjs) — focused module/regression coverage for yahoo.

**Integration harnesses:** [`socket-harness.cjs`](frontend/tests/socket-harness.cjs) exercises deterministic WebSocket scenarios, [`browser-phase131.py`](frontend/tests/browser-phase131.py) is a Chromium browser harness, and `docs/acceptance/phase1321/` records PR #43's scoped browser screenshots/results. Inspect required flags before running browser controls; use isolated DEMO/PAPER with signed TESTNET disabled.

**Schema acceptance:** `backend/tests/test_audit_terminal_contract.py` and nearby contract/static tests check generated terminal schema/validators. **Do not weaken schema currency checks**. Different installed Pydantic versions can change inline Decimal schema patterns, which must be investigated explicitly.

**Last verified PR #43 report (not a new test run):** frontend **213 passed**, TypeScript/build passed; backend with full extras **1,124 passed / 1 failed** on `test_generated_terminal_schema_is_current`, reported reproducible on Pydantic 2.13.5 and 2.12.5. Six-page DEMO/PAPER Chromium checks were reported; external provider, Redis service, signed TESTNET, macOS and long-soak acceptance remain separate. Documentation cannot mark those gates closed.

**Basic checks:**

~~~bash
cd backend
python -m pip install -e '.[test,ml,redis,yahoo]'
python -m pip check
python -m compileall -q app
python -m pytest -q

cd ../frontend
npm ci
npm test
npm run typecheck
npm run build
~~~

This docs-only PR must not claim to have fixed the existing Pydantic/schema issue.


## 10. Where to implement a change

| Want to change... | Ownership and recommended tests |
|---|---|
| Hyperliquid L2 normalization/reconnect | `market_data/hyperliquid.py`, `market_data/service.py`; market/perp/integration tests |
| Virtual invariant/reserve recentering | `amm/constant_product.py`, `amm/virtual_reserves.py`; AMM tests |
| Concentration, tick/size/quote feasibility | `amm/concentrated.py`, `amm/discretizer.py`, `amm/numeric.py`, `strategy/quote_engine.py`; Phase 12.2 tests |
| Inventory/volatility/perp reference | `strategy/inventory.py`, `strategy/market_adaptation.py`, `strategy/perp_policy.py`; Phase 5–7 tests |
| Independent provider or reference quorum | `references/providers.py`, `references/service.py`, `references/consensus.py`; Phase 8/provider tests; never silently expand provider votes |
| Agent recommendation or SHADOW features | `agents/`, `research/ml/`; Phase 9 + offline validation; no new execution authority |
| Risk posture or FinalQuoteAuthorization | `risk/firewall.py`, `risk/authorization.py`, `runtime.py`; adversarial risk and integration acceptance |
| Orders, cancellations, venue uncertainty | `execution/quote_reconciler.py`, `execution/order_manager.py`, adapters; execution/venue lifecycle tests |
| Fill/fee/funding/capital/ledger | `accounting/`; Phase 11 ledger/economic tests; avoid direct UI truth edits |
| Research scenarios/grid objectives | `simulation/`; Phase 10 deterministic research tests |
| Add or change REST routes | `api/` + app wiring + frontend API client + backend API tests |
| Terminal wire schema | `terminal/models.py` → generator → JSON contract → TypeScript validator + WS/API/browser tests |
| WebSocket transport/disconnect | `api/websocket.py`, `infrastructure/terminal_transport.py`, frontend socket/store; lifecycle/replay tests |
| UI screen/interaction | `frontend/src/pages/` and relevant components; Node tests, typecheck/build, actual browser |
| Risk/readiness labels in UI | Backend evidence fields + `utils/freshness.ts` + `utils/authorizationLineage.ts`; never fabricate current data |
| Local browser accessibility/navigation | `App.tsx`, `Sidebar.tsx`, nav hooks, `phase13.css`; navigation and Chromium tests |


## 11. Architecture constraints and technical debt

- **Single-process engine:** one authoritative `HyperAmmRuntime` under loopback-only local research. There is no supported remote/multi-operator authorization or multi-worker distributed order lifecycle.
- **No production persistence:** current PAPER, account/ledger and history are in-memory research state. Redis is ephemeral only; PostgreSQL is shown in design documents as a *future*, not a tracked implementation.
- **Market versus transport truth:** an open WebSocket does not imply fresh oracle/provider evidence, and a fresh terminal envelope does not imply that quotes are authorized.
- **Semantic versus physical quote levels:** logical level slots can collapse to the same executable tick. Phase 12.2 exposes observational effective liquidity but does not automatically choose a coalesce/trim/reject policy. See [Phase 12.2 acceptance](docs/PHASE122_ACCEPTANCE.md).
- **Testnet truth:** venue reconciliation/unknown orders and supported positions are not equivalent to a complete signed fill/fee ledger; unsupported details are intentionally unavailable.
- **Simulation truth:** deterministic PAPER crossing is not a backtest of real queue position, hidden liquidity, stochastic fills or real latency.
- **External acceptance:** macOS, real external providers, real Redis, signed TESTNET and extended soak can remain pending even when local tests pass. Phase 13.2 A–E UI work remained planned after PR #43.
- **Documentation versus implementation:** never infer that a README/roadmap future phase is an active import, route or safety feature. If behavior changes, update this guide and its owning domain document after checking source and tests.


## 12. Reference documents and provenance

Each file below exists in the inspected Git tree. Read the source code first for actual behavior; these provide deeper intent, formulas, audits, and historical acceptance records.

| Existing document | Topic |
|---|---|
| [`ACCOUNTING.md`](docs/ACCOUNTING.md) | Capital, ledger, PnL and accounting authority. |
| [`AGENTS.md`](docs/AGENTS.md) | Supervisor behavior, telemetry and optional SHADOW inference. |
| [`AMM_MATH.md`](docs/AMM_MATH.md) | Virtual constant-product and concentrated liquidity mathematics. |
| [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Primary architecture and safety/identity design. |
| [`HYPERLIQUID_INTEGRATION.md`](docs/HYPERLIQUID_INTEGRATION.md) | Hyperliquid public-data and guarded TESTNET adapter integration. |
| [`INVENTORY_SKEW.md`](docs/INVENTORY_SKEW.md) | Inventory policy formulas and hard-limit behavior. |
| [`MARKET_ADAPTATION.md`](docs/MARKET_ADAPTATION.md) | Volatility and top-N book adaptation constraints. |
| [`PERP_CONTEXT.md`](docs/PERP_CONTEXT.md) | Perpetual mark/oracle/funding/OI strategy context. |
| [`PHASE122_ACCEPTANCE.md`](docs/PHASE122_ACCEPTANCE.md) | Phase 12.2 local AMM quote hardening acceptance. |
| [`PHASE123_ACCEPTANCE.md`](docs/PHASE123_ACCEPTANCE.md) | Phase 12.3 frontend timestamp/session/replay acceptance. |
| [`PHASE131_ACCEPTANCE.md`](docs/PHASE131_ACCEPTANCE.md) | Phase 13.1 navigation/design/browser acceptance. |
| [`PHASE132_PARTIAL_EXECUTION_UX.md`](docs/PHASE132_PARTIAL_EXECUTION_UX.md) | PR #42 focused quote-ladder status integrity record. |
| [`PHASE1321_ACCEPTANCE.md`](docs/PHASE1321_ACCEPTANCE.md) | Phase 13.2.1 execution UX and browser acceptance; known backend schema failure. |
| [`REDIS_DESIGN.md`](docs/REDIS_DESIGN.md) | Preimplementation Redis state/authority inventory and design constraints. |
| [`REDIS.md`](docs/REDIS.md) | Implemented opt-in ephemeral transport/admission behavior. |
| [`REFERENCE_INTEGRITY.md`](docs/REFERENCE_INTEGRITY.md) | Provider policy, quorum and outlier detection. |
| [`RISK_FIREWALL.md`](docs/RISK_FIREWALL.md) | Risk decisions, exposure, authorization and escalation. |
| [`ROADMAP.md`](docs/ROADMAP.md) | Phase delivery and pending acceptance gates. |
| [`SIMULATION.md`](docs/SIMULATION.md) | Deterministic scenarios, PAPER replay and bounded optimizer. |
| [`TERMINAL.md`](docs/TERMINAL.md) | Terminal observation contract, history, frontend and WebSocket integration. |

Additional root documents: [`README.md`](README.md), [`Summary.md`](Summary.md), [`AUDIT_REPORT_1.0.md`](AUDIT_REPORT_1.0.md), [`AUDIT_REPORT_2.0.md`](AUDIT_REPORT_2.0.md), [`LICENSE`](LICENSE) and [`.gitignore`](.gitignore). The tracked `backend/app/*/README.md` files serve as per-domain entry guides.

### Maintenance rule

Before modifying this guide in later phases, recheck the repository tree and the real import/call graph. Update file roles, routes, examples, authoritative boundaries and acceptance status together. **Treat a recorded PR test count as historical evidence, never as a new passing run.**

---
**Revision inspected:** `50f6ab9b42cbd72f905b2ffc319f0ea90b7252c4` — merged PR #43. **Purpose:** documentation and navigation only; this file introduces no runtime behavior, schema change, API endpoint or execution permission.


## Phase 13.3.1 — Agents and Vault workspace additions

Implemented against verified main `616ab5b7dc1b48c2573cad5c4f41dffadc4cf1c4`.
The original source inventory above remains historical; these changes add
presentation and client attribution safeguards without backend domain changes.
See [acceptance](docs/PHASE1331_ACCEPTANCE.md) for actual results and limitations.

| Source | Responsibility |
| --- | --- |
| [`AgentDetails.tsx`](frontend/src/components/agents/AgentDetails.tsx) | Six tailored observation/recommendation/reason/evidence cards, exact available detail fields and version-matched input provenance. |
| [`AgentAuthoritySummary.tsx`](frontend/src/components/agents/AgentAuthoritySummary.tsx) | Separates reported agent recommendation, RiskFirewall, final authorization and execution observations; checks declared agent binding without claiming causal attribution. |
| [`AgentEvents.tsx`](frontend/src/components/agents/AgentEvents.tsx) | Typed existing GET event response, agent filtering, manual refresh, bounded retention and terminal-only historical fallback. |
| [`AccountingConsistency.tsx`](frontend/src/components/vault/AccountingConsistency.tsx) | Backend CONSISTENT/DIVERGED/UNAVAILABLE status and supported fill counts/timestamps; no repair action. |
| [`AccountingProvenance.tsx`](frontend/src/components/vault/AccountingProvenance.tsx) | Versions, source/completeness, full inspectable fingerprints and session scope. |
| [`useResearchSession.ts`](frontend/src/hooks/useResearchSession.ts) | Observes accepted terminal store transitions; a connection epoch rejects requests across reconnects even if React batches transitions. |
| [`researchEvidence.ts`](frontend/src/utils/researchEvidence.ts) | Session freshness, ledger response/context matching, bounded event validation and exact decimal presentation. |
| [`phase1331.css`](frontend/src/phase1331.css) | Research-page-scoped dark terminal layout, responsive cards, keyboard details and scrollable financial tables. |
| [`research-workspace.test.cjs`](frontend/tests/research-workspace.test.cjs) | Agent/accounting evidence, precision, filtering, authority and deferred-request regressions. |
| [`browser-phase1331.py`](frontend/tests/browser-phase1331.py) | Optional real Chromium local acceptance, isolated read-only browser fixtures and dedicated backend stop/restart. |

Existing Agents/Vault routes, AgentPanel, VaultSummary, PnlBreakdown and
AccountingLedger are enhanced. AgentPanel retains its compact Dashboard default;
only the Agents route selects the workspace variant. Badge, TerminalPrimitives,
format utilities, exactDecimal, API client, terminal store and Analytics SessionCharts
are reused. Analytics implementation remains unchanged. Ledger filtering keeps
backend newest-first sequence order; it does not introduce financial calculations
or sorting through binary floating-point values. The static backend UI guard follows
the relocated consistency component and session-keyed Vault mount while retaining
read-only route/custody protections.

`GET /agents/events` is an oldest-first array of retained events with a 250 limit;
`GET /accounting/ledger` provides newest-first rows plus mode/market/version/hash,
not a terminal session ID. Queries bind process/session and connection epoch, consume
AbortSignal and check accepted terminal evidence again after completion. Ledger
responses additionally match mode/market/version/fingerprint at request and render.
No previous-session placeholder is shown. Identical genesis fingerprints alone
cannot prove session provenance; this residual wire limitation is documented.
