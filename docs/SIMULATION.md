# Phase 10 — Strategy Optimization + Deterministic Simulation

Phase 10 is an offline research framework around the actual HyperAMM strategy implementation.

It is:

```text
RESEARCH
SIMULATION
PAPER
OFFLINE
DETERMINISTIC
```

It is not a live optimizer, autonomous trader, production execution simulator, or profitability guarantee.

## Architecture

Phase 10 deliberately reuses the production strategy stack:

```text
SimulationDataset / SimulationFrame
        ↓
MarketSnapshot + PerpMarketContext
        ↓
MarketPriceHistory
        ↓
QuoteEngine
        ├── virtual AMM
        ├── concentrated liquidity
        ├── Phase 5 InventoryPolicy
        ├── Phase 6 MarketAdaptationPolicy
        └── Phase 7 PerpContextPolicy
        ↓
simulated PriceEvidence
        ↓
ReferenceConsensusPolicy
        ↓
Phase 9 AgentSupervisor
        ↓
transform_quotes()
        ↓
POST-AGENT / PRE-RISK candidates
        ↓
Phase 8 RiskFirewall
        ↓
Phase 8 quote transform
        ↓
validate_quotes()
        ↓
FinalQuoteAuthorization
        ↓
OrderManager
        ↓
reconcile_quotes()
        ↓
PaperExecutionAdapter
        ↓
simulated orders / fills
        ↓
metrics + bounded trace
```

There is no simplified second trading strategy.

Each simulation run owns fresh mutable state:

- `MarketPriceHistory`
- `PaperExecutionAdapter`
- `AgentTelemetryStore`
- `AgentSupervisor`
- `RiskFirewall`
- `OrderManager`
- PAPER orders/fills
- PnL/equity/drawdown state

Optimizer candidates never share this state.

## No network providers

Simulation does not instantiate or start `ReferenceService`.

The `app/simulation/` package does not import or call:

- RedStone transport
- Kraken transport
- CoinGecko transport
- Hyperliquid WebSocket
- Hyperliquid REST
- Hyperliquid TESTNET adapter
- private keys

Simulation-generated references reuse the existing normalized contracts:

- `PriceEvidence`
- `ProviderId`
- `SourceType`
- `ReferenceConsensusPolicy`
- `ReferenceSnapshot`

Provider identities remain:

```text
REDSTONE
HYPERLIQUID_ORACLE
KRAKEN
COINGECKO
HYPERLIQUID_MID
HYPERLIQUID_MARK
```

Every synthetic source is explicitly:

```text
transport = DEMO
transport_quality = SIMULATED
simulated = true
```

Source IDs are explicit simulation identities such as `simulation:redstone` and `simulation:kraken`.

The real consensus policy still decides VERIFIED / DEGRADED / CONFLICTED / INSUFFICIENT.

## SimulationConfig

Phase 10 settings are separate from live `StrategyConfig`.

```text
initial_equity_quote
max_frames
record_trace
trace_max_points
fill_model = CROSSING_ONLY
```

The live runtime is never mutated by a simulation request. API orchestration deep-copies current strategy, agent and risk configuration. The research strategy copy forces:

```text
execution_mode = PAPER
market_data_mode = DEMO
```

without writing those values back to `rt.config`.

Initial position is flat in Phase 10 v1. A fake cost basis is never seeded.

## Deterministic clock

`PaperExecutionAdapter` now accepts an optional clock:

```python
PaperExecutionAdapter(clock=utcnow)
```

Production behavior is unchanged by default.

Simulation supplies a mutable scenario clock. PAPER-owned timestamps use this clock for:

- order creation
- order updates
- fills
- cancellation
- replacement

Generated scenarios use a fixed timezone-aware start time plus:

```text
frame_index * interval
```

No simulation scenario defaults to wall-clock `utcnow()`.

## SimulationFrame

Each immutable input concept contains:

```text
sequence
timestamp
MarketSnapshot
PerpMarketContext
external simulated reference prices
```

Validation requires:

- market/perp identity match
- frame sequence == book sequence
- frame timestamp == book timestamp
- timezone-aware timestamps
- complete BBO/book/mid state
- finite positive BBO/mid
- non-crossed BBO
- BBO matches top book levels
- midpoint equals BBO midpoint
- non-stale market/perp context
- finite positive reference prices when present

Existing Pydantic market/perp models additionally validate level prices/sizes, mark/oracle prices, funding and open interest.

Malformed caller replay data is rejected; it is not silently reordered or repaired.

## SimulationDataset

A dataset contains:

```text
market
frames
source
simulated
fingerprint
```

It rejects:

- empty datasets
- market mismatch
- duplicate/regressed sequence
- duplicate/regressed timestamp

The dataset fingerprint is canonical SHA-256 over semantic dataset content.

No historical-data downloader, scraper, or exchange ingestion service is included in Phase 10.

## Scenario catalog

Built-in deterministic scenarios:

- QUIET
- TREND_UP
- TREND_DOWN
- MEAN_REVERTING
- HIGH_VOLATILITY
- BID_HEAVY_BOOK
- ASK_HEAVY_BOOK
- FLASH_MOVE
- ORACLE_DISLOCATION
- REFERENCE_DEGRADATION
- POSITIVE_FUNDING_STRESS
- NEGATIVE_FUNDING_STRESS
- LIQUIDITY_SHOCK

All use deterministic formulas based on frame index.

Examples:

```text
TREND_UP
    start_price * (1 + index * 0.0005)

TREND_DOWN
    start_price * (1 - index * 0.0005)

MEAN_REVERTING
    fixed deterministic price-offset cycle

HIGH_VOLATILITY
    fixed alternating large price-offset cycle

BID_HEAVY_BOOK
    bid top-depth > ask top-depth

ASK_HEAVY_BOOK
    ask top-depth > bid top-depth
```

FLASH_MOVE applies an abrupt deterministic downside move followed by deterministic partial recovery.

ORACLE_DISLOCATION supplies divergent RedStone evidence; it does not hardcode a risk state.

REFERENCE_DEGRADATION removes RedStone evidence and lets the existing consensus/fallback policy decide.

Funding-stress scenarios alter funding context. Phase 11 optionally books deterministic PAPER research funding through the shared accounting service.

## Frame processing order

For each frame:

1. advance scenario clock;
2. apply the new market snapshot to existing PAPER orders;
3. allow existing crossing-only PAPER orders to fill;
4. record fills into Phase 9 telemetry;
5. derive PAPER inventory from actual fills;
6. add the current market observation to `MarketPriceHistory`;
7. use the frame's normalized `PerpMarketContext`;
8. run the real `QuoteEngine.generate_perp_market_adaptive()`;
9. build simulated provider evidence;
10. run the real `ReferenceConsensusPolicy`;
11. build Phase 9 agent evidence;
12. run the real `AgentSupervisor`;
13. run Phase 9 `transform_quotes()`;
14. mark the shared Phase 11 accounting service and preview simulated capital reservation;
15. load existing PAPER open orders;
16. run the real Phase 8 `RiskFirewall` against POST-AGENT candidates;
17. run the Phase 8 risk transform;
18. run existing `validate_quotes()`;
19. build `FinalQuoteAuthorization`;
20. reconcile through the real `OrderManager` / `reconcile_quotes()`;
21. capture any immediate crossing-only fills;
22. update telemetry;
23. record metrics and bounded trace.

Phase 8 therefore evaluates exactly the POST-AGENT / PRE-RISK ladder.

## Simulation authority

The simulation uses a local authority callback for `OrderManager`.

Before CREATE/REPLACE it verifies:

- market/history version
- PAPER inventory version
- perp version
- reference version
- agent version
- agent fingerprint
- risk version
- authorized quote fingerprint
- `FinalQuoteAuthorization.authorized`

The callback never contacts a venue.

## PAPER fill model

Phase 10 v1 is:

```text
CROSSING_ONLY
```

Existing PAPER semantics are reused:

```text
resting BID fills when best ask <= BID price
resting ASK fills when best bid >= ASK price
fill price = resting order price
fill size = remaining order size
```

No probabilistic fill model is introduced.

Known execution-model limitations:

- no queue priority
- fees use configured PAPER maker/taker research assumptions, not venue facts
- funding uses opt-in deterministic research intervals, not actual venue payments
- no exchange latency model
- no hidden liquidity
- no stochastic fill probability

These limitations are returned with every `SimulationResult`.

## PnL, equity and drawdown

Phase 10 reuses the same Phase 11 `AccountingService` as runtime PAPER. Risk receives its vault-derived PnlDrawdown and metrics consume the final vault; neither calculates a separate ledger.

PnL is explicitly:

```text
net session PnL = realized + unrealized - configured fees + configured funding
```

Defaults explicitly select zero-fee and zero-funding PAPER research accounting. Optional `simulation.accounting` settings enable simulated fees/funding and reservation limits. The existing simulation initial equity sets accounting starting capital. See [Accounting](ACCOUNTING.md).

Equity:

```text
current_equity =
    initial_equity_quote
    + session_pnl
```

Peak equity is the running maximum.

Drawdown:

```text
drawdown_pct =
    (peak_equity - current_equity)
    / peak_equity
```

The Phase 8 firewall receives a simulated `PnlDrawdown` containing realized/unrealized/session PnL, current equity, peak equity and drawdown.

## Metrics

`SimulationMetrics` records:

- frame count
- starting/ending equity
- net session PnL
- return %
- realized/unrealized PnL
- max drawdown %
- fill count and BID/ASK fill counts
- quoted notional
- filled notional
- filled-notional / quoted-notional activity ratio
- ending inventory
- max absolute inventory
- max inventory utilization
- mean spread capture when available
- mean mature markout when available
- adverse fill rate when available
- KEEP / CREATE / REPLACE / CANCEL counts
- reconciliation churn ratio
- risk-state counts and HALT fraction
- regime-state counts
- toxic-flow state counts
- execution-quality state counts

Unavailable execution-quality values remain `None`; zero is not used as an unavailable sentinel.

Phase 9 formulas are reused for spread capture, markouts and churn.

## Trace

Trace points are optional and bounded by `trace_max_points`.

Each point records:

- sequence/timestamp
- mid/mark/oracle
- inventory
- PnL/equity/drawdown
- reference confidence
- Phase 9 states
- Phase 8 risk state
- desired/agent/authorized quote counts
- open-order count
- fill count

When the bound is reached, the deque retains the most recent points. Full strategy state is not retained per frame.

## Reproducibility and fingerprints

Phase 11 additionally binds accounting schema `phase11-v1` and full accounting config into every run fingerprint, and exposes the final vault, bounded accounting ledger and accounting fingerprint. The existing pipeline engine provenance is owned by code: `SIMULATION_ENGINE_VERSION = "phase10.1-v1"`
in `backend/app/simulation/version.py`. `SimulationConfig` has no version field.
Both `SimulationResult.engine_version` and `OptimizationResult.engine_version`
report this constant. Every candidate run fingerprint binds the same constant;
changing the implementation version changes the fingerprint without changing
scenario economics. Run/optimization request models, `SimulationConfig` and
`OptimizationObjectiveConfig` use `extra="forbid"`; caller-selected versions or
unknown behavior/safety fields receive HTTP 422.

The run fingerprint binds:

- engine version
- dataset fingerprint
- StrategyConfig
- AgentConfig
- fixed RiskFirewallConfig
- SimulationConfig semantic settings

It does not bind local wall clock or Python object identity.

Scenario timestamps own PAPER order/fill timestamps.

Same inputs are expected to produce identical:

- run fingerprint
- metrics
- economic orders/fills
- candidate ranking

Candidate state isolation is mandatory: A → B → A must reproduce A.

Run-order independence is mandatory: candidate result identity cannot depend on evaluation order.

## No future leakage

At frame `t`, decision-making uses only:

- current/prior market frames already placed in history
- fills that have already happened
- markouts whose horizon has already matured
- current frame perp/reference evidence

Future frames are not passed to the strategy, agents, consensus or firewall.

Future prices are used only retrospectively by the existing Phase 9 markout logic once simulation time/history has advanced beyond the markout horizon.

Validation scenarios do not influence candidate generation or training ranking.

## Grid optimizer

Phase 10 v1 uses deterministic `itertools.product` grid search.

No:

- ML
- reinforcement learning
- Bayesian optimization
- random search
- LLM optimizer

### Strategy allowlist

Approved `StrategyConfig` research fields:

- levels_per_side
- max_distance_bps
- total_liquidity
- concentration_factor
- concentration_lower_bps
- concentration_upper_bps
- max_inventory_price_skew_bps
- inventory_size_skew_strength
- volatility_low_threshold
- volatility_high_threshold
- volatility_spread_strength
- volatility_size_strength
- imbalance_spread_strength
- imbalance_size_strength
- perp_mark_weight
- perp_oracle_weight
- max_funding_reference_shift_bps
- max_perp_reference_shift_bps
- base_order_size

### Agent allowlist

Approved `AgentConfig` research fields:

- regime_trend_threshold_bps
- regime_spread_strength
- regime_size_strength
- toxic_flow_adverse_markout_bps
- toxic_flow_spread_strength
- toxic_flow_size_strength
- execution_quality_poor_markout_bps
- execution_quality_max_churn_ratio
- execution_quality_spread_strength
- execution_quality_size_strength

Unknown fields are rejected.

Candidates are constructed through normal Pydantic `StrategyConfig` / `AgentConfig` validation. Invalid combinations are reported; they are not silently clamped.

## Immutable safety/runtime settings

The optimizer explicitly rejects attempts to tune safety/runtime values including:

- execution_mode
- market_data_mode
- hard_inventory_limit_base
- reference firewall enablement
- reference warning/reduce/HALT thresholds
- projected exposure limits
- liquidation HALT distance
- drawdown HALT threshold
- TESTNET enablement
- API URLs
- credentials/private keys

The fixed `RiskFirewallConfig` is copied into every candidate and never optimized.

## Candidate bound

`max_candidates` has a hard maximum of 128.

The complete Cartesian product is counted before evaluation.

If:

```text
requested candidate count > max_candidates
```

the request is rejected. The grid is never silently truncated.

## Objective score

Every scenario exposes raw metrics plus the following components:

```text
return_bps =
    return_pct * 100

drawdown_penalty =
    drawdown_weight
    * max_drawdown_pct
    * 10000

inventory_penalty =
    inventory_weight
    * max_inventory_utilization
    * 10000

adverse_markout_penalty =
    adverse_markout_weight
    * max(0, -mean_markout_bps)

churn_penalty =
    churn_weight
    * churn_ratio
    * 10000

halt_penalty =
    halt_weight
    * halt_fraction
    * 10000

final_score =
    return_bps
    - drawdown_penalty
    - inventory_penalty
    - adverse_markout_penalty
    - churn_penalty
    - halt_penalty
```

If mature markout is unavailable, the markout penalty is zero and the raw metric remains `None`.

The score is transparent research ranking, not a black-box model.

## Baseline, training and validation

The unchanged current configuration is always evaluated as:

```text
BASELINE
```

Candidates are ranked only on the mean training-scenario objective score.

After training ranking, top candidates are evaluated on validation scenarios without retuning.

Results expose:

- training score
- validation score
- score delta vs baseline
- mean PnL delta
- drawdown delta
- inventory-utilization delta
- markout delta when available
- churn delta
- HALT-fraction delta

A candidate is described as highest-ranked under the selected scenarios/objective, never "optimal" in an absolute sense.

## Deterministic tie-breaking

Equal training scores are ordered by:

1. lower mean max drawdown;
2. lower max inventory utilization;
3. lower mean churn;
4. configuration fingerprint.

## API

Offline-only endpoints:

```text
GET  /api/v1/simulation/scenarios
POST /api/v1/simulation/run
POST /api/v1/simulation/optimize
```

Requests are bounded by frame count, scenario count, trace count and candidate count.

The endpoints never:

- start/stop live strategy
- enable TESTNET
- submit/cancel live runtime orders
- mutate live strategy configuration
- mutate live agent configuration
- mutate live risk configuration
- mutate the kill switch

## Frontend

The focused page is:

```text
Simulation & Optimization
```

It provides:

- scenario selection
- frame count
- run simulation
- small bounded optimization presets
- baseline and ranked candidates
- training/validation scores
- PnL, drawdown, inventory, fills, markout, churn, risk/agent distributions

It prominently displays:

```text
SIMULATED
NO LIVE ORDERS
```

There is no auto-apply/deploy/trade-best-candidate control.

## Phase 10.1 workload isolation and lifecycle

FastAPI lifespan owns one persistent `SimulationExecutor` in
`app.state.simulation_executor`. Simulation and optimization share **one research
slot**: maximum concurrent simulation jobs = 1, maximum concurrent optimization
jobs = 1, maximum combined jobs = 1. A thread-safe admission lock guards only
submission and completion. Busy requests immediately receive HTTP 429 with
`Phase 10 research is already running`; there is no research request queue.

Before admission, handlers capture deep copies of validated strategy, agent,
risk, simulation and objective models, grid values and scenario lists. Only
these detached inputs and scalar settings cross into the worker. The worker
never receives the runtime, its services, orders, async locks/events, reference
service or execution adapter. It calls `asyncio.run()` inside the dedicated
thread, creating a separate event loop and a fresh `SimulationService`, engine
and optimizer per request. Each engine run still constructs fresh PAPER,
history, telemetry, supervisor, firewall and reconciliation state. The existing
production strategy/risk/authorization pipeline remains intact.

The executor completion callback releases admission on success or failure.
Request cancellation stops awaiting a shielded worker future but does not kill
the thread or release its slot early. The worker finishes safely, and detached
unexpected errors are logged. Shutdown closes admission and waits for the one
bounded active job to finish, off the live event loop; the pool is explicitly
joined before runtime services are stopped. Python threads are never forcibly
terminated. This protects event-loop scheduling, not separate-process CPU or
memory isolation; the worker still shares the interpreter.

Only `pydantic.ValidationError` and `ValueError` in candidate validation/domain
execution are recorded as rejected candidates. `RuntimeError`, `AttributeError`,
`KeyError`, `TypeError` and other unexpected failures abort optimization and
produce a generic HTTP 500, with engineering diagnostics in application logs.
Bad request/config inputs receive HTTP 422. Broad exception handlers exist only
at the worker/API/submit cleanup boundaries, where they log or re-raise failures;
none converts unexpected candidate errors into rejections.

Existing bounds remain: 128 candidates, at most 8 training and 8 validation
scenarios, optimization frames 2..1000, standalone simulation frames 2..5000
subject to `SimulationConfig.max_frames`, trace points 0..5000 and top_n 1..10.
The optimizer also validates its direct-call bounds before evaluating baseline.
No additional total-frame budget is introduced; bounded admission and the
existing per-request limits are the Phase 10.1 workload policy.

Acceptance tests hold a worker behind a synchronization event, prove a health
request runs while it is occupied, reject concurrent simulation and optimization,
and accept another job after completion. Tests also cover candidate failure
cleanup, detached config identities/mutation, cancellation, submission failure,
shutdown thread joining, version spoofing and code-version fingerprint binding.

## Acceptance status

Phase 10 is IMPLEMENTED / IN REVIEW after Phase 10.1 local acceptance on
2026-10-06 (America/Los_Angeles). Python 3.12.14 completed the full suite:
**407 passed, 1 warning in 8.91s** (upstream Starlette/httpx deprecation).
Real Uvicorn startup, eight required REST endpoints, terminal WebSocket state and
graceful application shutdown passed in DEMO/PAPER mode. The installed Uvicorn
version re-raises SIGTERM after lifespan shutdown, returning -15. Frontend
typecheck and build exited 0 (115 modules, 2.49s; non-failing TanStack Query
directive warnings). `git diff --check` passed. Completed acceptance gates:

- full Python 3.12 backend suite passes
- Phase 10 scenario/engine/optimizer/API/static tests pass
- FastAPI existing and simulation endpoints pass
- terminal WebSocket regression passes
- frontend typecheck passes
- frontend build passes
- `git diff --check` passes
- no additional oracle provider, GitHub Actions, LLM/ML optimizer, or expanded terminal work is introduced

Phase 8 remains IN REVIEW.

Phase 9 remains IMPLEMENTED / IN REVIEW.

Phase 11 shared research accounting is IMPLEMENTED / IN REVIEW; Phase 12 remains PLANNED.
