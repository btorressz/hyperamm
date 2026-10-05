#  HyperAMM
## Adaptive Virtual AMM & Market-Making Engine for Hyperliquid

**HyperAMM converts a mathematical AMM liquidity curve into discrete order-book liquidity for Hyperliquid.** It is not an on-chain pool. The system uses virtual constant-product reserves as a deterministic liquidity model, samples that curve around a market-derived fair value, optionally concentrates liquidity near the reference range, normalizes prices/sizes, and reconciles the desired ladder into resting CLOB orders.

Phases 1–5 are implemented as one integrated Python/FastAPI + React/TypeScript system. PAPER is the default execution mode; signed Hyperliquid testnet orders are separately guarded. Mainnet trading, withdrawals, transfers and bridging are deliberately out of scope.

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

## Phase 1–5 capabilities

- **Phase 1 — Market data + paper execution:** normalized L2/BBO state, WebSocket subscription adapter, initial L2 snapshot, monotonic exchange-time handling, reconnection/degraded states, explicit deterministic demo feed, paper orders/fills, optional testnet adapter.
- **Phase 2 — Virtual constant-product AMM:** invariant, marginal price, reserve initialization/recentering, base→quote and quote→base virtual swaps, curve-state calculations.
- **Phase 3 — AMM curve → CLOB compiler:** deterministic bid/ask levels, tick and size normalization, stable side ordering, no-cross checks, and stateful quote reconciliation.
- **Phase 4 — Concentrated liquidity:** bounded deterministic weighting that shifts more fixed liquidity near fair value as concentration increases.\n- **Phase 5 — Inventory-aware quoting:** normalized PAPER/TESTNET inventory, bounded reservation-price and side-size skew, hard-limit side suppression, inventory freshness/version checks, and terminal controls/visibility.

A minimal Phase 1–4 risk authority enforces freshness, level count, per-order size, aggregate notional, minimum price, quote distance, execution state and a kill switch. The kill switch cancels active strategy orders and blocks new quote generation.

## Technology

Backend: Python 3.12+, FastAPI, Pydantic v2, Decimal math, asyncio, official `hyperliquid-python-sdk`, pytest. Frontend: React, TypeScript, Vite, TanStack Query, Zustand, Lightweight Charts, native WebSocket.

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
GET  /api/v1/orders
GET  /api/v1/fills
GET  /api/v1/risk
POST /api/v1/risk/kill
POST /api/v1/risk/resume
WS   /ws/terminal
```

## Frontend

The terminal uses a dark institutional layout with selected-market/feed/execution/risk state in the header, rolling market + fair-value charting, Hyperliquid L2, an AMM liquidity view, quote ladder, strategy controls, metric cards, kill-switch controls and roadmap status. AI Agents, Vault, Analytics, Backtesting, Logs and expanded Settings are visibly marked planned/not enabled; no fake confidence, PnL, win rate, vault balances or model outputs are displayed.

## Tests

The backend suite covers constant-product invariants, marginal price, both virtual swap directions, invalid reserves, deterministic sampling, concentrated normalization and concentration behavior, bid/ask ordering, no-cross guarantees, price/size normalization, deterministic quote generation, KEEP/CREATE/REPLACE/CANCEL reconciliation, strategy validation, stale feed rejection, risk validation, kill switch, paper lifecycle/fills, API lifecycle, and the disabled-testnet transmission guard.

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

Phase 5 intentionally stops at deterministic inventory-aware quoting. Adaptive volatility/order-book imbalance logic, perp vAMM/funding context, external oracle protection, full institutional risk firewall, AI agents, optimization/simulation, persistent vault accounting and production mainnet trading remain out of scope.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/AMM_MATH.md`
- `docs/HYPERLIQUID_INTEGRATION.md`
- `docs/ROADMAP.md`

## 12-phase roadmap

Phases 1–5 are the implemented foundation. Phase 6 adds volatility/book imbalance; Phase 7 perpetual vAMM context; Phase 8 oracle protection/risk firewall; Phase 9 AI supervisory agents; Phase 10 optimization/simulation; Phase 11 vault/accounting; Phase 12 the expanded production trading terminal.

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
wallet. Phases 5–8 remain planned and are not implemented in this change.


## Phase 5 — Inventory-Aware Quoting

Phase 5 composes after the accepted neutral AMM/concentration ladder and before deterministic risk/reconciliation. PAPER inventory is derived from economic fills only. TESTNET inventory is normalized from Hyperliquid account state and fails closed when authoritative state is missing, stale, malformed, or economically uncertain.

For deviation `d = position - target`, normal skew uses `r = clamp(d / soft_limit, -1, 1)`. The reservation shift is `-r * max_inventory_price_skew_bps`; bid and ask sizes use bounded `1 - strength*r` and `1 + strength*r` side multipliers. At the long hard limit, inventory-increasing bids are omitted; at the short hard limit, inventory-increasing asks are omitted. Existing reconciliation therefore cancels forbidden resting quotes without a second order-management path.

See [Inventory Skew](docs/INVENTORY_SKEW.md) for formulas, source semantics, failure behavior, and test coverage.
