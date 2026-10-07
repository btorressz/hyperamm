# API Layer

The `api` package is the thin FastAPI transport layer for HyperAMM. Routers translate HTTP/WebSocket requests into calls on the lifespan-owned `HyperAmmRuntime` or `SimulationExecutor`.

Business logic should stay in the domain packages rather than being duplicated in route handlers.

## Application wiring

`app.main` creates:

- one `HyperAmmRuntime`;
- one `SimulationExecutor`;
- REST routers under the configured `/api/v1` prefix;
- the terminal WebSocket at `/ws/terminal`.

`app.dependencies.runtime()` retrieves the current runtime from `request.app.state`.

## Files

| File | Responsibility |
|---|---|
| `health.py` | Runtime/service health summary. |
| `markets.py` | Normalized market and order-book reads. |
| `strategy.py` | Strategy state/config plus approved start/stop/update controls and AMM/market/perp summaries. |
| `positions.py` | Normalized inventory/position observability. |
| `orders.py` | Read-only order/fill views. |
| `risk.py` | Risk state/evidence/events/final authorization plus manual kill/resume controls. |
| `agents.py` | Read-only Phase 9 agent state/events. |
| `simulation.py` | Bounded research scenario and optimizer endpoints using `SimulationExecutor`. |
| `accounting.py` | Read-only vault, PnL, position, ledger and accounting-event endpoints. |
| `terminal.py` | Read-only bounded terminal history/events APIs. |
| `websocket.py` | Primary current-state `/ws/terminal` stream. |
| `__init__.py` | Package marker. |

## Design rules

- API handlers should not reimplement AMM, risk, agent or accounting formulas.
- Mutation routes invoke runtime methods that hold the shared execution lock and enforce existing authority.
- Simulation endpoints are research-heavy and use the isolated executor.
- Terminal/accounting/agent observability is read-only.
- Credentials remain backend configuration and must never be serialized to clients.
- HTTP/WebSocket presentation never bypasses `FinalQuoteAuthorization`.

## Main consumers

The React frontend uses these REST endpoints for bounded history, ledgers, simulation jobs and controls while `/ws/terminal` carries compact current operator state.
