# HyperAMM Backend Application

This directory contains the Python/FastAPI implementation of HyperAMM. The backend is organized by domain so the mathematical AMM, strategy transformations, supervisory agents, deterministic risk, execution, accounting, simulation, and terminal observability remain separate concerns.

## Runtime architecture

```text
Market data + perpetual context
        ↓
Strategy reference / fair value
        ↓
Virtual AMM + concentrated liquidity
        ↓
Inventory-aware quoting
        ↓
Volatility / L2 market adaptation
        ↓
Phase 9 supervisory agents
        ↓
Reference consensus
        ↓
Phase 8 risk firewall
        ↓
FinalQuoteAuthorization
        ↓
OrderManager reconciliation
        ↓
PAPER / guarded TESTNET execution
        ↓
Phase 11 accounting / vault
        ↓
Phase 12 terminal observations
```

`runtime.py` is the composition root for the live strategy path. It owns the current market, strategy state, adapters, services, execution lock, quote stages, risk/authorization state, accounting state, and terminal observation service. Domain packages should remain reusable and should not depend on the React frontend.

## Top-level files

| File | Responsibility |
|---|---|
| `main.py` | Creates the FastAPI application, installs CORS, owns lifespan startup/shutdown, constructs `HyperAmmRuntime` and `SimulationExecutor`, and mounts REST/WebSocket routers. |
| `runtime.py` | Orchestrates the live Phase 1–12 pipeline and enforces the serialized execution/authority path. |
| `config.py` | Environment-backed application/provider settings, including market/data/execution mode and external reference configuration. |
| `dependencies.py` | FastAPI dependency that returns the lifespan-owned runtime. |
| `__init__.py` | Package marker. |

## Domain packages

| Package | Role |
|---|---|
| [`amm/`](amm/) | Constant-product virtual reserves, concentrated-liquidity shaping, curve sampling and CLOB quote discretization. |
| [`market_data/`](market_data/) | Normalized Hyperliquid/DEMO market state, bounded price history, and perpetual-market context. |
| [`strategy/`](strategy/) | Fair value, inventory policy, volatility/book-imbalance adaptation, perpetual reference policy and quote-engine composition. |
| [`agents/`](agents/) | Deterministic/heuristic supervisory regime, toxic-flow and execution-quality analysis. |
| [`references/`](references/) | RedStone, Hyperliquid, Kraken and CoinGecko evidence normalization and consensus. |
| [`risk/`](risk/) | Structural quote limits, kill switch, institutional risk firewall and final authorization fingerprints. |
| [`execution/`](execution/) | PAPER and guarded TESTNET execution adapters, quote reconciliation and serialized order management. |
| [`accounting/`](accounting/) | Deterministic position/PnL accounting, immutable ledger, fees/funding, vault and execution/accounting consistency. |
| [`simulation/`](simulation/) | Offline deterministic scenarios, production-stack simulation, research metrics and bounded parameter optimization. |
| [`terminal/`](terminal/) | Versioned read-only operator snapshots, bounded current-session history, events and system-health aggregation. |
| [`api/`](api/) | Thin FastAPI routing layer over the runtime and simulation executor. |

## Authority boundaries

The backend intentionally separates recommendation from authority:

- AMM/strategy code proposes liquidity.
- Agents may only make the strategy more conservative.
- Reference integrity and the Phase 8 firewall remain downstream authority.
- `FinalQuoteAuthorization` binds material versions and fingerprints.
- `OrderManager` checks authority immediately before CREATE/REPLACE.
- Accounting is economic/capital authority but never submits orders.
- Terminal/API presentation is not trading authority.
- Cancellation remains available when new-risk authority fails.
- The project contains no production-mainnet execution or custody path.

## Further documentation

See the repository `docs/` directory for AMM math, inventory skew, market adaptation, perpetual context, reference integrity, risk, agents, simulation, accounting, terminal design, and the Phase 1–12 roadmap.
