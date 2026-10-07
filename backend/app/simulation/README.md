# Simulation & Optimization Domain

The `simulation` package implements Phase 10/10.1 offline deterministic research around the **same production strategy components** used by the live runtime.

It is intentionally isolated from live execution and does not auto-deploy optimized parameters.

## Position in the architecture

```text
deterministic scenario/replay frames
        ↓
SimulationEngine
        ↓
QuoteEngine → inventory → market adaptation → perp
        ↓
agents → references → risk → FinalQuoteAuthorization
        ↓
OrderManager + PAPER execution
        ↓
shared AccountingService
        ↓
metrics / trace / deterministic fingerprint
        ↓
optional bounded grid optimizer
```

## Files

| File | Responsibility |
|---|---|
| `models.py` | Immutable datasets, frames, traces, metrics, candidate/optimization results and stable fingerprints. |
| `config.py` | Simulation limits, accounting assumptions and optimization objective configuration. |
| `scenarios.py` | Built-in deterministic market/perp/reference stress scenarios. |
| `references.py` | Builds explicitly simulated provider evidence using the real reference contracts/policy. |
| `replay.py` | Bounded dataset/frame replay helpers. |
| `engine.py` | Recreates fresh strategy/agent/risk/execution/accounting state and runs the production pipeline frame-by-frame. |
| `metrics.py` | Accumulates PnL, drawdown, inventory, fill, spread-capture, markout, churn, risk and regime metrics. |
| `optimizer.py` | Deterministic bounded grid search over explicit strategy/agent allowlists with immutable safety fields, baseline and train/validation separation. |
| `service.py` | Research-facing facade that forces DEMO/PAPER strategy copies and exposes scenario/optimization operations. |
| `executor.py` | Lifespan-owned single-slot research worker thread/private event loop so heavy research does not block FastAPI. |
| `version.py` | Code-owned simulation engine version used in provenance/fingerprints. |
| `__init__.py` | Public exports. |

## Deliberate limitations

The simulator currently models deterministic crossing fills and does not claim exchange queue priority, hidden liquidity, stochastic fill probability or real network latency. Fees/funding/capital behavior are explicit research assumptions.

## Optimizer safety

The optimizer only varies allowlisted strategy/agent research parameters. Execution mode, hard safety limits, provider secrets and institutional risk controls are forbidden parameters. Unexpected programming errors propagate rather than being disguised as invalid candidates.

## Isolation

Every run receives fresh/deep-copied state. The executor provides bounded admission and private worker-loop execution. Simulation results never authorize live orders.
