# Phase 10 — Strategy Optimization + Deterministic Simulation

Phase 10 is an offline research framework around the actual HyperAMM strategy implementation.

Volatility is supplied by the shared Phase 6 `MarketAdaptationPolicy` through
QuoteEngine, then copied into Phase 9 agent evidence. It is
[per accepted observation RMS log return](MARKET_ADAPTATION.md#realized-volatility),
without annualization or elapsed-time weighting; no simulation-specific estimator
exists. Identical accepted price sequences yield identical sigma/score/regime
regardless of regular, bursty, sparse or irregular frame timing. Warmup and the
trailing window count accepted prices, not seconds. Other simulation effects
(funding intervals, markout maturity, freshness, timestamps and dataset/run
fingerprints) can depend on timing; equality of volatility does not imply equality
of all economic outputs across retimed datasets. Repeated runs of each dataset
remain deterministic.

It is:

```text
RESEARCH
SIMULATION
PAPER
OFFLINE
DETERMINISTIC
```

It is not a live optimizer, autonomous trader, production execution simulator, or profitability guarantee.

## A1-025 scientific-tooling boundary

The current deterministic simulation and bounded optimizer do not require Pandas
or SciPy to produce authoritative runtime decisions, and no scientific-library
output is permitted to become signing, kill-switch, position, accounting-capital
or Phase 8 authorization truth.

If a concrete future workflow benefits from NumPy/Pandas/SciPy—for example dataset
alignment, offline sensitivity analysis, calibration or uncertainty studies—it
belongs in an **optional offline research path**. That path should consume exported
immutable inputs, emit proposal/research outputs, record dataset identity and
holdout assumptions, and require explicit review before any configuration is
applied. Installing a scientific package by itself does not validate crossing-only
fill economics, create out-of-sample evidence or justify live auto-application.

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
2. build simulated provider evidence and run ReferenceConsensusPolicy, binding fill-time consensus;
3. apply the market snapshot to existing PAPER orders and allow crossing-only fills;
4. record fills into Phase 9 telemetry;
5. derive PAPER inventory from actual fills;
6. add the current market observation to `MarketPriceHistory`;
7. use the frame's normalized `PerpMarketContext`;
8. run the real `QuoteEngine.generate_perp_market_adaptive()`;
9. retain the prepared reference consensus for this frame;
10. retain that same fill-time reference for any immediate submit fills;
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

Phase 9 formulas are reused for spread capture, markouts and churn. Capture uses
the frame's accepted consensus bound before any fill, with explicit consensus and
eligible-provider provenance; absent consensus stays unavailable, never midpoint.
Churn is `(REPLACE + CANCEL) / max(1, CREATE + REPLACE + CANCEL)` over run-wide
counts; KEEP cannot dilute it. GOOD requires mature markout evidence; positive
capture alone remains provisional with an explicit agent reason.

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

Phase 11 additionally binds accounting schema `phase11-v1` and full accounting config into every run fingerprint, and exposes the final vault, bounded accounting ledger and accounting fingerprint. The existing pipeline engine provenance is owned by code: `SIMULATION_ENGINE_VERSION = "phase10.1-v2"`
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

Candidates are constructed through normal Pydantic `StrategyConfig` / `AgentConfig` validation. Invalid combinations are reported as rejected candidates; they are not silently clamped. Only `ValidationError` raised while constructing those configs is a candidate rejection. Dataset generation, simulation, scoring and result construction run outside that exception handler; unexpected failures, including engine/runtime `ValueError` or `ValidationError`, abort optimization.

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

After training ranking, the baseline and top candidates are evaluated on validation scenarios without retuning.

Every `ScenarioEvaluation` exposes `dataset_fingerprint` alongside `run_fingerprint`.
Dataset identity reuses the existing `SimulationDataset.fingerprint`; scenario labels
and configuration-dependent run fingerprints do not establish independence.
The baseline, each candidate and the overall optimization result expose:

- `training_dataset_fingerprints` and `validation_dataset_fingerprints`;
- `validation_overlap`: whether those identity sets intersect;
- `independent_holdout`: true only when both sets are nonempty and disjoint;
- `validation_classification`: `INDEPENDENT_HOLDOUT`, `REUSED_OVERLAPPING`
  (REUSED / OVERLAPPING validation), or `NOT_EVALUATED`.

These fields are derived from the evaluations and included in serialized results.
Candidate identity lists retain evaluation order and duplicates; overall lists
are sorted unique identities across the baseline and all candidates. Candidates
outside the validation selection have `NOT_EVALUATED` status. Any overlap makes
the entire validation set reused/overlapping, including partially overlapping sets.
Repeated deterministic scenarios cannot be called out-of-sample, and different
labels resolving to the same dataset fingerprint remain overlapping. An independent
holdout here means disjoint dataset identities within this synthetic research run;
it does not establish real-market out-of-sample performance. Validation provenance
does not change candidate generation, objective scoring or training ranking.

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

Only `pydantic.ValidationError` during candidate config construction is recorded
as a rejected candidate. Engine/runtime exceptions, including `ValueError` and
`ValidationError`, propagate out of the optimizer instead of entering
`rejected_candidates`. The existing API boundary maps `ValueError` (including
Pydantic validation errors) to HTTP 422; other unexpected failures produce a
generic HTTP 500 with engineering diagnostics in application logs. Broad exception handlers exist only
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

## Optional Redis research coordination

With Redis and `REDIS_RESEARCH_ENABLED=true`, the existing local `SimulationExecutor`
is wrapped by renewable namespace-wide research admission and TTL job/status/result
mirrors. HTTP APIs remain synchronous; contention returns 429 and unavailable
admission returns 503. Detached request cancellation holds the slot until the real
worker completes. Inputs are deep-copied and existing PAPER/DEMO isolation remains.
Cached results include process/session, full input digest, code-owned engine version
and result/dataset identity; cache data is never substituted into live strategy.
No remote queue, cancellation endpoint, candidate deployment or durable research
store is added. See [Redis semantics and limitations](REDIS.md).


## Agent expansion and predictive shadow evaluation

The simulator reuses the production v2 Regime/Toxic Flow/Execution Quality agents
and the new Liquidity Quality and Perp Crowding agents. Their conservative
recommendations still pass through Phase 8 and FinalQuoteAuthorization. The
code-owned simulation version is `phase10.1-v3`; deterministic evidence changes
are reflected in research run identity.

Predictive ML is **SHADOW ONLY**. Programmatic research may explicitly supply a
validated `LogisticModelArtifact` to `SimulationEngine.run(predictive_model=...)`.
It cannot change quotes, fills, accounting or risk outcomes, and cannot auto-apply
optimizer output or promote itself. Each frame's trace includes state and side
probabilities; a prediction binds at order creation and then to an actual PAPER
fill. Mature labels share the production immutable first-eligible midpoint
selection, rather than rebinding later fills/prices. Pending labels stay pending
when replay ends. The bounded report keeps up to 1000 fill predictions and order
bindings, reports discarded prediction counts, and identifies its retained
cohort. Side/horizon accuracy, precision, recall, AUC, Brier, calibration error
and ten probability buckets compare predictions with actual matured markouts;
buckets below minimum support are flagged. No profitability follows from these
classifier metrics or deterministic PAPER matching.

`app.research.ml.dataset.build_dataset` constructs one configurable-horizon
conditional adverse-fill target from typed evidence/fills/history. Features
are selected at or before the fill, targets only from later observations.
Duplicate identities cannot inflate sample counts. Dataset hashes cover source
fingerprints, time bounds including label maturity, market, target, sample count,
simulated/live classification and `passive-adverse-v1` feature schema. Independent
train/validation claims require distinct dataset/sample identities and disjoint
feature-to-label windows. Required missing features reject dataset construction
or inference rather than being silently imputed.

Optional `pip install -e '.[test,ml]'` provides scikit-learn LogisticRegression.
Training has no runtime hook or execution-adapter imports and exports a bounded
JSON coefficient artifact with strict model/dataset/config provenance. NumPy and
SciPy usage stays transitive inside optional sklearn research; they do not enter
AMM, risk, order sizing, accounting or final authorization. The ordinary backend
install works without sklearn. See [complete agent and offline ML contracts](../backend/app/agents/README.md)
for CLI usage, normalization, fingerprint scope and retained evidence formulas.

## Phase 14 — Customizable Research Vault

A stateless `ResearchProposal` carries a strict `ResearchVaultConfig` plus optional
`selected_preset_id`. Python owns preset definitions (`simulation/presets.py`),
versions and validation. Preset selection and editable drafts live only in browser
memory. Research never writes active strategy, runtime accounting, risk, signing,
kill state or orders. The existing PAPER engine and accounting formulas are reused.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v1/research-vault/presets` | Deterministic, versioned Python catalog |
| `POST /api/v1/research-vault/preview` | Validation and Decimal configuration arithmetic; no engine/trades/persistence |
| `POST /api/v1/research-vault/compare` | One admitted worker operation, two sequential isolated runs from one captured snapshot and dataset |
| `POST /api/v1/simulation/run` / `optimize` | Optional `research` proposal; legacy requests retain defaults |

Canonical request example:

```json
{
  "scenario": "FLASH_MOVE",
  "frames": 120,
  "research": {
    "selected_preset_id": "balanced-research",
    "config": {
      "initial_equity_quote": "100000",
      "paper_fee_model_enabled": true,
      "paper_maker_fee_bps": "1",
      "paper_taker_fee_bps": "3",
      "paper_funding_accounting_enabled": false,
      "paper_funding_interval_seconds": 3600,
      "max_capital_utilization": "0.75"
    }
  },
  "simulation": {"max_frames": 120, "record_trace": true, "trace_max_points": 250}
}
```

With `research`, `simulation` can supply only frame/trace controls: explicitly
supplied capital, accounting or fill model is ambiguous and rejected. There is
one starting-capital input: `initial_equity_quote`. Explicit mapping sets both
simulation initial equity and isolated accounting initial equity to that value;
the engine retains its existing capital override. Accounting enablement, ledger/
event bounds and freshness remain code-owned defaults. CROSSING_ONLY is mandatory.
Research fields are excluded from optimizer strategy/agent parameter allowlists.

Financial bounds reuse AccountingConfig metadata, with narrower research limits:
capital >0 and ≤1e12 quote; maker/taker fees 0–100 bps; utilization >0 and ≤1;
finite Decimals with at most 18 fractional places and 80 input characters. Flags
are strict booleans; funding intervals are integer seconds in
`1, 60, 300, 3600, 28800, 86400`. Short intervals are explicitly sampled research
stress assumptions. Unknown/nested/protected fields and unknown preset IDs fail
closed. POST research bodies are bounded to 64 KiB before parsing (including
chunked requests). Validation errors retain location/type/message without echoing
input/exception context, including raw JSON NaN/Infinity.

| Preset ID (version 1) | Capital quote | Enabled maker/taker bps | Funding | Utilization cap |
| --- | ---: | --- | --- | ---: |
| conservative-capital | 50000 | 1 / 3 | Disabled, 3600s | 0.35 |
| balanced-research | 100000 | 1 / 3 | Disabled, 3600s | 0.75 |
| high-cost-stress | 100000 | 10 / 25 | Enabled, 60s | 0.75 |

Names describe hypothetical studies, not safety or profit guarantees. The narrow
model's defaults preserve legacy accounting assumptions (fees/funding disabled,
100000 capital, utilization 1); Balanced Research is a separate catalog profile.

Preview compares the submitted configuration to the selected preset (or the
explicitly reported Balanced baseline when no preset is supplied). It returns
old/new values, Decimal differences and units, canonical values, schema
`phase14-v1`, preset ID/version, fingerprint, warnings and limitations. Its only
capital calculation is initial capital × utilization fraction; that ceiling is
neither venue margin nor guaranteed allocation. Preview calculates no PnL.
Funding enabled may produce no events within a short dataset. Scenario rates
remain per research interval, using existing sampled position/mark evidence.

The research SHA-256 uses existing simulation stable-fingerprint serialization
on a canonical config plus schema version. Decimal encodings such as `1.00` and
`1` normalize without rounding. Preset versions are code-owned and must increment
when definitions change. Simulation/optimization results add nullable
`research_configuration` provenance; engine/run/dataset/strategy fingerprints
retain their existing semantics. The run endpoint validates again and never
accepts a preview hash as validation authority.

Comparison payload: `{baseline: ResearchProposal, custom: ResearchProposal,
scenario, frames, record_trace, trace_max_points}`. Bounds are 2–1000 frames per
run and 0–500 trace points. The request captures strategy/agents/risk synchronously
before awaiting admission, forces PAPER/DEMO on copied strategy and generates
one dataset. Two engine invocations create fresh PAPER accounting/execution/
supervision/risk state. Only permitted accounting assumptions differ. The same
local worker (and optional existing Redis admission wrapper) owns the operation;
429 and cancellation behavior are preserved, with no queue or second executor.

Comparison returns both existing SimulationResults, config provenance,
custom-minus-baseline Decimal deltas, actual risk-state counts and limitations.
Fees/funding and ending capital utilization come from actual VaultSnapshots;
unavailable values stay null. `max_inventory_utilization` remains the existing
inventory-risk metric, distinct from ending capital reservation utilization.
Starting-capital differences carry an explicit interpretation warning. Higher
PnL is an observed simulated outcome, never a guaranteed improvement.

Vault appends a clearly distinct studio after existing accounting provenance.
Decimal inputs remain strings; percent movement is textual and scales once.
Preset selection/reset, validation, stale preview and selection for research are
separate states. Request/draft/connection generations reject obsolete completions,
including edits, preset switches, navigation and batched reconnects. Backend restart
retires prior validation while preserving the local draft. Simulation captures
selected research settings at submission and keeps completed results associated
with their request; optimization presets remain independent. Disconnect/AbortSignal
never claims the worker has stopped. No browser persistence or live deployment
action is added. See [Phase 14 acceptance](PHASE14_ACCEPTANCE.md).
## Phase 14.6 — Validated single-native-perpetual research selection

Exactly `BTC`, `ETH`, and `SOL` are accepted as optional `research_market` on
`POST /api/v1/simulation/run`, `/simulation/optimize`, and `/research-vault/compare`.
Display labels are BTC-PERP, ETH-PERP, SOL-PERP; these labels, lowercase names,
spot pairs, HIP-3 identifiers, arrays and arbitrary symbols are rejected by the
request contract. Omission preserves the legacy request/worker behavior and ETH
scenario methodology. One immutable market profile is resolved before worker
admission; optimization never varies market identity.

```json
{"research_market":"BTC","scenario":"FLASH_MOVE","frames":30,
 "simulation":{"max_frames":30,"record_trace":true,"trace_max_points":250}}
```

`GET /api/v1/research-markets` is a separate read-only catalog with exactly three
entries, `research_only: true`, and `execution_mode: PAPER`. Operational
`/markets/{market}` remains the active market only. Clients cannot supply asset
indices, profiles, precision or tick values. Existing Research Vault proposals,
presets, simulation controls, candidate bounds and parameter allowlists remain.

### Metadata ownership and offline eligibility

The existing official `hyperliquid-python-sdk>=0.24.0,<0.25` dependency is unchanged.
Installed 0.24.0 signatures were inspected. A lifespan-owned catalog uses one
dedicated synchronous worker, single-flight initialization/refresh and a 300s
immutable snapshot cache. `Info(MAINNET_API_URL, skip_ws=True, timeout=5, ...)`
receives empty supported initialization maps to avoid constructor-side spot and
perp discovery; exchange facts come solely from the subsequent actual
`Info.meta(dex="")` response. No WebSocket, trading Exchange, keys, HIP-3 discovery,
permanent collector or refresh loop is created. Requests remain off the FastAPI
event loop. Cancellation preserves ownership of the real worker; shutdown drains
the task and closes the SDK HTTP session even on failures.

Validation rejects duplicate identities, malformed/bounded universes, unsupported
native identifiers, missing size precision, noninteger/boolean/out-of-range
`szDecimals`, invalid delisting flags and non-native dex metadata. The actual
universe position supplies `asset_index`. A valid response that explicitly
delists or omits an allowlisted market yields `UNAVAILABLE`; it never receives a
DEMO override. Metadata failures replace expired verified eligibility rather than
silently retaining it.

`EXCHANGE_VERIFIED` originates only from successful validated official SDK native
metadata. `DEMO_PROFILE` is permitted only when the server starts in DEMO/PAPER,
and uses code-owned pinned fixtures. DEMO listing, observed timestamp and asset
index remain null; source is `PINNED_RESEARCH_FIXTURE`. No current listing, live
price or trading eligibility is asserted. In other modes a metadata outage makes
research unavailable. Catalog observation age is reported at retrieval; it is
not a continuously refreshed venue clock. A copied research strategy always
forces DEMO/PAPER regardless of operational mode.

### Deterministic calibration and actual executable precision

Profile version `phase146-v1` uses hypothetical anchors **BTC 60000**, **ETH 3000**,
**SOL 150** quote per base. These are fixed research inputs, never current mark
prices. DEMO size precisions are respectively 5, 4 and 2; verified size precision
comes from metadata. No fixture asset index is guessed.

The isolated adapter derives the source pool price from configured quote/base
reserves, keeps virtual quote reserves unchanged, sets virtual base reserves to
quote reserves / selected anchor, and scales base order size and per-side
liquidity by source reference / selected anchor. Quantities round downward.
Inventory targets, soft/hard limits and every risk configuration field remain
unchanged. Pydantic/curve feasibility still validates the complete copy. An
infeasible lot-size budget rejects; capital/exposure violations retain genuine
HALT behavior. SOL may have no fills under unchanged configured base limits.

The selected-profile scenario path reuses all 13 existing scenario shapes by
scaling the legacy 3000-anchor movements, book spreads/depth notionals and price
offsets proportionally. Book prices round outward, sizes downward; BBO midpoint
is recomputed from the rounded book. Mark/oracle observations follow the same
asset price rules. Market/book/perp identity, frame time/sequence and positive,
uncrossed prices retain existing validations. Legacy generation stays untouched
when no profile is supplied. Negative long-horizon scenario prices fail closed.

Price normalization enforces at most five significant figures for nonintegers,
at most `6 - szDecimals` decimal places, and the documented integer exemption.
It computes precision from each actual price, rather than claiming a universal
fixed exchange tick. Isolated agent and final risk ladders are normalized before
existing final validation, capital reservation and FinalQuoteAuthorization.
Outward ASK rounding reduces size as necessary so neither proposed quantity nor
individual order notional increases. Sub-lot quantities are removed; no fill is
fabricated. Runtime/venue quote paths and AMM formulas are unchanged.

### Provenance, comparisons and client lifecycle

Selected results expose `research_market`, `market_profile_version`,
`market_profile_fingerprint`, `metadata_source`, `metadata_status` alongside
existing dataset/strategy/run fingerprints and engine version. Economic profile
identity includes market, metadata source/status/listing/precision/index and
fixed anchor/version; observation times/age are excluded from deterministic
identity. Dataset source commits to the profile; run identity also commits to
its evidence. The legacy engine version is preserved and selected-path
calibration is separately versioned. Each optimization scenario's dataset/run
fingerprint binds the same chosen profile. Baseline/custom comparison generates
one dataset and copies one strategy/agents/risk snapshot; only permitted
accounting assumptions differ. Both results independently retain market evidence.

Vault and Simulation share an in-memory ETH-default research preference, separate
from terminal state and research accounting drafts. TanStack Query retrieves and
validates the bounded server catalog. Both workspaces show metadata state, fixed
anchor, size/price rules, source, version and limitations. Switching market keeps
accounting values but retires market-dependent approval and pending responses.
Requests capture a detached profile, selection generation and backend connection
epoch. A response must match that market/profile and current generation before
being accepted. Completed results render their captured returned identity after
dropdown changes; previous-connection results carry an explicit historical notice.
Restart retires catalog/accounting validation while retaining local drafts and
preference. There is no browser persistence or strategy write.

Operational VaultSummary, PnlBreakdown, consistency/provenance, ledger and session
charts remain separate from the selected simulated market. No operational feed,
strategy/order lifecycle, ledger, risk authority, kill switch or TESTNET signing
eligibility is mutated by this feature. See [Phase 14.6 acceptance](PHASE146_ACCEPTANCE.md)
for executed tests, real Chromium evidence and the blocked live-provider check.

## Phase 15.4 — Captured research assumptions and observed comparison

`SimulationResult.research_assumptions` is optional and backward compatible.
`ResearchMarketAssumptions` is frozen/extra-forbid `phase154-v1` evidence extracted
from the **last frame consumed from the actual supplied dataset**, independently
of trace retention. It retains BBO/mid/spread, mark/oracle/raw funding, modeled
base OI, actual top-five per-side levels/sizes/depth, sequence/time, market/profile/
dataset/scenario and a separate assumptions fingerprint. Existing run, strategy,
profile and dataset fingerprints retain their original meaning. A representative
frame is not an aggregate of the entire scenario. Legacy evidence stays null.

The existing SimulationService still generates one deterministic dataset per
individual run and one shared dataset for baseline/custom Research Vault runs;
engine extraction therefore gives both sides identical market assumptions.
Fees/funding/capital provenance and hypothetical PnL remain their original actual
simulation outputs. Optimizer ranking and candidate summaries are unchanged.

`POST /api/v1/research-market-comparison/compare` accepts `{market, research}`;
research is a compact completed-result summary with original identities,
assumptions, bounded performance fields and optional Research Vault provenance.
Exactly BTC/ETH/SOL, no unknown fields, 64 KiB pre-parsing body bound, at most five
levels per side, bounded finite Decimal inputs and strict PAPER flags. No trace,
strategy program, URL, credential, order or execution configuration is admitted.
422 errors omit input/exception context; service failures return a sanitized 500.
Responses have `Cache-Control: no-store`.

The service reads only existing `LiveMarketStreamService.snapshot(market)`. It
never starts an SDK, calls REST refresh, schedules work, regenerates research or
writes operational state. Disabled observations yield unavailable observed values
while preserving research performance and provenance. L2 exchange time, L2 receipt,
context receipt (economic event time UNKNOWN), research frame and processing time
are separate. Acquisition gaps are explicit. Current component eligibility also
requires valid/fresh native metadata and an accepted connection boundary.

Decimal equations: price delta = observed − research; price bps = delta / research
× 10000; spread quote delta = observed spread − research spread; spread bps delta
= observed bps − research bps, **not** a relative price percentage. Funding is raw
subtraction only, classified PARTIAL because native hourly rates and sampled
research intervals do not establish comparable settled payments. OI subtraction
requires actual modeled frame base OI and is descriptive/PARTIAL. Depth subtraction
requires five distinct prices per side and comparable base units. SOL's current
rounded synthetic frames can have repeated modeled prices: actual sizes remain
visible, but depth delta is unavailable. No book economics are rewritten.

Metric statuses COMPARABLE/PARTIAL/NOT_COMPARABLE/UNAVAILABLE gate every delta;
cross-market requests return NOT_COMPARABLE with no cross-asset arithmetic.
Completeness is deterministic: all eleven supported metrics available →
COMPLETE_FOR_SUPPORTED_METRICS; some → PARTIAL; none with incompatible evidence →
INSUFFICIENT; otherwise UNAVAILABLE. PARTIAL raw funding/OI can count as available
without becoming equivalent economic contexts. Interpretation always remains
CROSS_CONTEXT_DESCRIPTIVE_ONLY. Completeness never predicts profit.

Client research is **structurally validated, not independently authenticated**.
Recomputed assumption/config hashes check consistency; a supplied run hash is not
proof of server execution. No durable registry is added. Semantic comparison
identity binds accepted research/observer/generation/source times/values, contract
and eligibility, excluding processing time, evaluation time and advancing ages.
Freshness transitions retire eligibility; unchanged economic captures retain a
stable fingerprint. [Acceptance](PHASE154_ACCEPTANCE.md) records actual tests and
remaining Phase 15.5/external gates.


## Phase 15.5B — October 29, 2026 update

Simulation public exports now load on demand to prevent importing the engine
through shared market profiles during standalone observation/provider imports.
All exported classes/functions and simulation economics are preserved. Actual
seeded PAPER fills, orders, ledger, reservations, kill and authorization remain
unchanged under adversarial observation actions. The browser's Phase 15.4
comparison stays frozen until an explicit refresh, including new stream ticks
and reconnects. See [15.5B acceptance](PHASE155B_ACCEPTANCE.md).
