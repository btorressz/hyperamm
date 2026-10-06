#  HyperAMM
## Adaptive Virtual AMM & Market-Making Engine for Hyperliquid

**HyperAMM converts a mathematical AMM liquidity curve into discrete order-book liquidity for Hyperliquid.** It is not an on-chain pool. The system uses virtual constant-product reserves as a deterministic liquidity model, samples that curve around a market-derived fair value, optionally concentrates liquidity near the reference range, normalizes prices/sizes, and reconciles the desired ladder into resting CLOB orders.

Phases 1–8 are implemented, Phase 9 supervisory agents are implemented / in review, and Phase 10 deterministic simulation + bounded optimization is in development as one integrated Python/FastAPI + React/TypeScript system. PAPER is the default execution mode; signed Hyperliquid testnet orders are separately guarded. Mainnet trading, withdrawals, transfers and bridging are deliberately out of scope.

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

## Phase 1–10 capabilities

- **Phase 1 — Market data + paper execution:** normalized L2/BBO state, WebSocket subscription adapter, initial L2 snapshot, monotonic exchange-time handling, reconnection/degraded states, explicit deterministic demo feed, paper orders/fills, optional testnet adapter.
- **Phase 2 — Virtual constant-product AMM:** invariant, marginal price, reserve initialization/recentering, base→quote and quote→base virtual swaps, curve-state calculations.
- **Phase 3 — AMM curve → CLOB compiler:** deterministic bid/ask levels, tick and size normalization, stable side ordering, no-cross checks, and stateful quote reconciliation.
- **Phase 4 — Concentrated liquidity:** bounded deterministic weighting that shifts more fixed liquidity near fair value as concentration increases.
- **Phase 5 — Inventory-aware quoting:** normalized PAPER/TESTNET inventory, bounded reservation-price and side-size skew, hard-limit side suppression, inventory freshness/version checks, and terminal controls/visibility.
- **Phase 6 — Volatility + order-book imbalance adaptation:** bounded rolling mid-price volatility, normalized top-N L2 imbalance, widening-only spread adaptation, conservative size/depth reduction, market-state version binding, and terminal explainability.
- **Phase 7 — Perpetual vAMM context:** normalized mark/oracle/funding/OI context, bounded perp strategy reference, AMM recentering, shared TESTNET position observability, freshness/version authority, and terminal explainability.
- **Phase 8 — Reference integrity + institutional risk firewall:** normalized multi-source price evidence, deterministic quorum/consensus, source health and freshness, signed deviation matrix, projected exposure, liquidation/PnL guards, NORMAL/WIDEN/REDUCE/HALT postures, hysteresis/recovery, SHA-256 authorization fingerprints, and final pre-transmission authority binding.
- **Phase 9 — Supervisory agents (IMPLEMENTED / IN REVIEW):** deterministic regime, adverse-selection markout and execution-quality analysis; conservative supervisor composition; bounded quote widening/size/level reduction; agent provenance bound into final authorization.
- **Phase 10 — Strategy simulation + bounded optimization (IN DEVELOPMENT):** deterministic scenario/replay datasets, scenario-time PAPER execution, production-stack simulation, research metrics, reproducible fingerprints, and deterministic grid search across an explicit strategy/agent allowlist.

A minimal Phase 1–4 risk authority enforces freshness, level count, per-order size, aggregate notional, minimum price, quote distance, execution state and a kill switch. The kill switch cancels active strategy orders and blocks new quote generation.

## Technology

Backend: Python 3.12+, FastAPI, Pydantic v2, Decimal math, asyncio, `websockets`, `httpx`, official `hyperliquid-python-sdk`, pytest. Frontend: React, TypeScript, Vite, TanStack Query, Zustand, Lightweight Charts, native WebSocket.

## Quick start

Copy optional configuration:

```bash
cp .env.example .env
```

### Backend

```bash
cd hyperamm/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
uvicorn app.main:app --reload
```

API: `http://127.0.0.1:8000` · OpenAPI: `http://127.0.0.1:8000/docs`

### Frontend

```bash
cd hyperamm/frontend
npm install
npm run build
npm run dev
```

Terminal: `http://127.0.0.1:5173`

## Demo-data mode

The provided `.env.example` deliberately starts with:

```text
MARKET_DATA_MODE=DEMO
EXECUTION_MODE=PAPER
```

Demo values are generated deterministically and are visibly labeled as simulated. HyperAMM does **not** silently use demo values when a LIVE feed fails.

To use public Hyperliquid data without a wallet:

```text
MARKET_DATA_MODE=LIVE
```

## Paper execution

PAPER orders are in-memory strategy orders with explicit status, timestamps and client order IDs. The deterministic simulator fills an order only when it touches/crosses the normalized market. Every such fill is labeled `SIMULATED PAPER FILL`.

## Optional Hyperliquid testnet mode

Testnet signing is off by default. To enable it intentionally:

```text
EXECUTION_MODE=TESTNET
ENABLE_HYPERLIQUID_TESTNET_ORDERS=true
HYPERLIQUID_ACCOUNT_ADDRESS=0x...
HYPERLIQUID_PRIVATE_KEY=...
```

The key remains backend-only. The testnet adapter uses post-only `Alo` limit orders and deterministic SDK client order IDs. No mainnet execution path is implemented.

## API surface

```text
GET  /api/v1/health
GET  /api/v1/markets/{market}
GET  /api/v1/markets/{market}/book
GET  /api/v1/strategy
PUT  /api/v1/strategy
POST /api/v1/strategy/start
POST /api/v1/strategy/stop
GET  /api/v1/amm/state
GET  /api/v1/amm/curve
GET  /api/v1/amm/quotes
GET  /api/v1/positions
GET  /api/v1/market-adaptation
GET  /api/v1/perp-context
GET  /api/v1/orders
GET  /api/v1/fills
GET  /api/v1/references
GET  /api/v1/risk
GET  /api/v1/risk/evidence
GET  /api/v1/risk/events
GET  /api/v1/risk/authorization
GET  /api/v1/agents
GET  /api/v1/agents/events
GET  /api/v1/simulation/scenarios
POST /api/v1/simulation/run
POST /api/v1/simulation/optimize
POST /api/v1/risk/kill
POST /api/v1/risk/resume
WS   /ws/terminal
```

## Frontend

The terminal uses a dark institutional layout with selected-market/feed/execution/risk state in the header, rolling market + fair-value charting, Hyperliquid L2, an AMM liquidity view, quote ladder, strategy controls, metric cards, kill-switch controls, supervisory-agent observability, and a focused Simulation & Optimization research page. Vault, expanded Analytics, Logs and expanded Settings remain planned; simulation is visibly labeled SIMULATED / NO LIVE ORDERS and has no auto-deploy action.

## Tests

The backend suite covers constant-product invariants, marginal price, both virtual swap directions, invalid reserves, deterministic sampling, concentrated normalization and concentration behavior, bid/ask ordering, no-cross guarantees, price/size normalization, deterministic quote generation, inventory policy, rolling volatility history, realized-volatility scoring, top-N L2 imbalance, Phase 6 spread/size adaptation, KEEP/CREATE/REPLACE/CANCEL reconciliation, strategy validation, stale feed rejection, risk validation, kill switch, paper lifecycle/fills, API lifecycle, and the disabled-testnet transmission guard.

Live Hyperliquid integration is intentionally not required by normal unit tests.

## Safety model

- PAPER default.
- TESTNET signing requires explicit opt-in plus a backend key.
- No mainnet execution implementation.
- No withdrawal, transfer or bridge methods.
- No browser signing secrets.
- `.env` and generated secrets are excluded from source control/ZIP packaging.
- LIVE feed failures are surfaced as degraded/unavailable rather than replaced with fabricated prices.

## Limitations

Phase 8 adds deterministic multi-source reference integrity and institutional risk authorization. Phase 9 supervisory agents are implemented / in review. Phase 10 simulation is offline PAPER research with deterministic crossing-only fills and does not model fees, funding cash flows, exchange latency, queue priority, hidden liquidity, or stochastic fill probability. Persistent vault accounting and production mainnet trading remain out of scope.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/AMM_MATH.md`
- `docs/HYPERLIQUID_INTEGRATION.md`
- `docs/ROADMAP.md`
- `docs/REFERENCE_INTEGRITY.md`
- `docs/RISK_FIREWALL.md`
- `docs/AGENTS.md`
- `docs/SIMULATION.md`

## 12-phase roadmap

Phases 1–8 are implemented. Phase 9 supervisory agents are IMPLEMENTED / IN REVIEW. Phase 10 deterministic simulation + bounded optimization is IN DEVELOPMENT. Phase 11 vault/accounting and Phase 12 expanded production trading terminal remain planned.

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

Phase 9 inserts a bounded, deterministic supervisory layer after Phase 6 strategy adaptation and before the Phase 8 firewall. The Regime, Toxic-Flow and Execution-Quality agents consume normalized existing evidence only. Their supervisor can widen spreads, reduce side sizes or trim existing levels; it cannot execute orders, restore suppressed liquidity, clear the manual kill switch or override Phase 8.

FinalQuoteAuthorization now binds agent version and fingerprint in addition to the existing market, inventory, perp, reference and risk authority.

PAPER fill telemetry is explicitly simulated. TESTNET fill-quality metrics remain unavailable where authoritative fill detail does not exist; no slippage or markout is fabricated.

See [Supervisory Agents](docs/AGENTS.md).


## Phase 10 — Strategy Optimization + Deterministic Simulation

Phase 10 is offline research tooling around the actual HyperAMM strategy stack. It does not contain a second simplified strategy. Each simulation run creates fresh MarketPriceHistory, PAPER execution, Phase 9 telemetry/supervisor, Phase 8 firewall, reconciliation and accounting state, then reuses the existing QuoteEngine → inventory → market adaptation → perp policy → agents → risk → FinalQuoteAuthorization → OrderManager path frame by frame.

Built-in deterministic scenarios cover quiet/trending/mean-reverting/high-volatility markets, book imbalance, flash moves, oracle dislocation, reference degradation, funding stress and liquidity shock. Synthetic references preserve the existing provider identities but are explicitly labeled DEMO / SIMULATED.

The v1 optimizer is deterministic grid search only. It supports an explicit allowlist of strategy/agent research parameters, rejects safety/runtime fields, evaluates an unchanged BASELINE, ranks on training scenarios, evaluates top candidates on separate validation scenarios, and exposes every numeric score component. Results are research rankings under the selected scenarios/objective—not claims of optimality or future profitability.

See [Simulation](docs/SIMULATION.md).
