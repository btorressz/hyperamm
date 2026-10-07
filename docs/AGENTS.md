# Phase 9 Supervisory Agents

Phase 9 adds a deterministic, heuristic supervisory layer to HyperAMM.

The governing rule is:

> Agents recommend. Deterministic infrastructure decides and executes.

Phase 9 does not add an autonomous trader, an LLM, direct venue execution, a new risk state, a new oracle, or Phase 10 optimization.

## Authority hierarchy

```text
Hyperliquid market data
        ↓
Phase 7 perpetual context
        ↓
virtual AMM / reserve-delta liquidity / concentration
        ↓
Phase 5 inventory policy
        ↓
Phase 6 volatility + book imbalance
        ↓
BASE STRATEGY QUOTES
        ↓
Phase 9 supervisory agents
        ├── Regime Agent
        ├── Toxic-Flow Agent
        └── Execution-Quality Agent
        ↓
deterministic AgentSupervisor
        ↓
BOUNDED AGENT-ADAPTED QUOTES
        ↓
Phase 8 reference integrity
        ↓
Phase 8 institutional risk firewall
        ↓
structural quote validation
        ↓
FinalQuoteAuthorization
        ↓
OrderManager reconciliation
        ↓
PAPER / guarded TESTNET
```

Phase 8 remains higher authority than Phase 9. Phase 9 cannot clear the manual kill switch, bypass structural validation, bypass final authorization, restore Phase 5-suppressed liquidity, or transmit orders.

Nothing in `backend/app/agents/` directly invokes execution-adapter submit/cancel/replace methods or Hyperliquid order methods.

## Configuration

`AgentConfig` is separate from `StrategyConfig`.

It owns bounded deterministic settings for:

- global enable/disable
- per-agent enable/disable
- maximum agent spread multiplier
- minimum agent size multiplier
- minimum recommendation confidence
- regime momentum/history thresholds
- toxic-flow fill window, markout horizon and adverse threshold
- execution-quality fill/reconciliation thresholds

All Decimal fields are validated as finite and bounded.

Phase 9 has no secrets.

## Normalized evidence

`AgentEvidenceSnapshot` contains only normalized existing state:

```text
market/history version
inventory version
perp version
reference version

Phase 6 regime / realized volatility / volatility score / imbalance
bounded short-horizon momentum

inventory position / inventory ratio

mark / oracle / funding / OI
mark-oracle and mark-mid basis

reference confidence
maximum reference deviation

simulation flag
```

It does not copy provider wire payloads.

Momentum is deterministic:

```text
momentum_bps =
    (latest_mid - earliest_mid)
    / earliest_mid
    * 10000
```

The selected history is bounded and must contain finite positive prices in monotonic timestamp/sequence order.

Relevant upstream version changes force runtime recomputation. Agent authority version/fingerprint changes only when the material supervisory decision changes, avoiding unnecessary authorization churn. Market, inventory, perp and reference versions remain independently bound by FinalQuoteAuthorization.

## Regime Agent

The Regime Agent is broader than Phase 6 but does not replace `MarketAdaptationPolicy`.

States:

```text
WARMING_UP
QUIET
NORMAL
TRENDING
HIGH_VOLATILITY
DISLOCATED
```

Direction:

```text
NEUTRAL
UP
DOWN
```

Primary inputs:

- Phase 6 realized volatility and score
- Phase 6 book imbalance
- bounded market history / momentum
- mark/oracle basis
- funding
- reference confidence and deviation

Priority is deterministic:

1. conflicted/insufficient or materially dislocated reference state → DISLOCATED
2. Phase 6 high-volatility state → HIGH_VOLATILITY
3. momentum threshold exceeded → TRENDING
4. low volatility + low momentum → QUIET
5. otherwise → NORMAL

The recommendation is symmetric in v1.

Conceptually:

```text
spread = 1 + regime_spread_strength * risk_score
size   = 1 - regime_size_strength * risk_score
```

Both are clamped through AgentConfig.

## Toxic-Flow Agent

"Toxic flow" means measurable adverse post-fill behavior, not trader identity.

For a BID fill:

```text
side_sign = +1
```

For an ASK fill:

```text
side_sign = -1
```

Markout:

```text
signed_markout_bps =
    side_sign
    * (future_reference_price - fill_price)
    / fill_price
    * 10000
```

Positive is favorable. Negative is adverse.

The future reference is the first normalized market-history observation at or after:

```text
fill.timestamp + toxic_flow_markout_horizon_seconds
```

If no such observation exists, the markout remains pending.

The telemetry store is bounded and deduplicates fills using stable normalized fill fields.

Metrics include:

- total fills
- matured fills
- pending markouts
- adverse fill count/rate
- mean signed markout
- mean adverse markout
- bid toxicity score
- ask toxicity score
- overall toxicity score

Scores are bounded 0–1.

States:

```text
INSUFFICIENT_DATA
NORMAL
ELEVATED
TOXIC
```

Adverse BID markouts can reduce BID size more heavily; adverse ASK markouts can reduce ASK size more heavily. Neither side can exceed a multiplier of 1.

PAPER fills are explicitly simulated.

## Execution-Quality Agent

The Execution-Quality Agent consumes actual normalized execution evidence already available:

- PAPER fills
- order status
- reconciliation actions
- UNKNOWN and REJECTED order state
- fill-time normalized reference when available

Spread capture:

BID:

```text
(reference - fill_price)
/
reference
* 10000
```

ASK:

```text
(fill_price - reference)
/
reference
* 10000
```

Positive means favorable passive capture.

Reconciliation churn:

```text
(REPLACE + CANCEL)
/
max(1, CREATE + REPLACE + CANCEL)
```

Metrics include:

- fill count
- filled-order ratio when meaningful
- average spread capture
- mature markout
- reject/UNKNOWN counts
- KEEP/CREATE/REPLACE/CANCEL counts
- churn ratio

States:

```text
INSUFFICIENT_DATA
GOOD
NORMAL
POOR
```

GOOD requires sufficient fills, positive capture and available non-negative mature
markout evidence. Positive capture without mature markouts remains NORMAL with
`provisional: mature markout unavailable`; adverse authoritative evidence can
still produce POOR. Mature markout values and sample counts appear in reasons.
KEEP counts remain observable but do not dilute churn. Runtime uses the bounded
window of order-changing reconciliation cycles; KEEP-only/empty cycles do not
evict action evidence. Simulation applies the same formula to run-wide counts.

## TESTNET limitation

Current TESTNET order/position reconciliation does not expose a normalized authoritative fill ledger equivalent to PAPER FillStore.

Therefore Phase 9 does not fabricate:

- TESTNET fill prices
- TESTNET markouts
- TESTNET slippage
- TESTNET spread capture

Execution-quality metrics requiring fill detail return `INSUFFICIENT_DATA`.

Authoritative TESTNET order-status evidence can still be observed and can wake runtime recomputation.

## Agent Supervisor

Aggregation is deliberately conservative:

```text
spread multiplier
    = max(regime, toxic flow, execution quality)

bid size multiplier
    = min(regime, toxic flow, execution quality)

ask size multiplier
    = min(regime, toxic flow, execution quality)

max levels
    = minimum non-null recommendation
```

The supervisor is deterministic. There is no vote, randomness, model API or LLM.

Individual agent exceptions become:

```text
health = ERROR
recommendation = neutral
reason = recorded
```

This is a deliberate soft/optional supervisory failure policy: an individual
exception produces `AgentHealth.ERROR` and a fresh neutral recommendation while
remaining agents continue. Stale prior advice is never silently reused. ERROR may
be less conservative than that agent's previous successful recommendation, but
quotes remain bounded by the current upstream ladder (no tightening or size
increase beyond upstream, no restored levels/sides). ERROR does not authorize
execution. Phase 8 deterministic risk, structural validation and
FinalQuoteAuthorization remain authoritative. The error and reason are visible
in agent output; this tradeoff does not make agents sticky execution authority.

Warmup/insufficient-data recommendations are also neutral.

## Quote transformation

Phase 9 sits after Phase 6 and before Phase 8.

For every surviving quote:

```text
distance =
    abs(pre_agent_price - inventory_reservation_center)

new_distance =
    distance * agent_spread_multiplier
```

Then:

```text
BID -> center - new_distance
ASK -> center + new_distance
```

Existing tick normalization is applied.

Size:

```text
new_size =
    pre_agent_size * side_size_multiplier
```

with existing size precision.

Invariants:

- spread multiplier >= 1
- size multiplier <= 1
- no new quote level is created
- no suppressed side is restored
- level trimming only removes existing levels
- no quote is recentered
- resulting prices/sizes must be finite and positive
- crossed quotes are rejected

When `agents_enabled=false`, `transform_quotes()` returns the original quote objects unchanged, preserving prices, sizes, levels and metadata exactly.

## Explainability

`QuoteLevel` retains:

```text
pre_agent_price
pre_agent_size
agent_spread_multiplier
agent_size_multiplier
agent_regime
agent_toxic_flow_state
agent_execution_quality_state
agent_version
```

Existing Phase 5–8 metadata remains.

This makes the pipeline observable as:

```text
pre-agent strategy quote
        ↓
agent-adapted candidate
        ↓
pre-risk quote
        ↓
Phase 8 risk adjustment
        ↓
authorized quote
```

## Authority version and fingerprint

`AgentSupervisorDecision` has a deterministic material version and SHA-256 fingerprint.

Canonical serialization uses the same principles as Phase 8:

- sorted keys
- Decimal as stable strings
- UTC datetimes
- enum values
- deterministic structures

A material recommendation/state change changes the agent version/fingerprint even if normalized quote prices happen to remain numerically identical.

An unchanged material decision does not churn agent authority simply because an upstream version changed. Upstream market/inventory/perp/reference versions are bound independently.

FinalQuoteAuthorization now binds:

```text
market version
inventory version
perp version
reference version
agent version
risk version

quote fingerprint
agent fingerprint
evidence fingerprint
risk fingerprint
authorization fingerprint
```

Immediately before CREATE/REPLACE the execution-authority path validates current agent version and fingerprint in addition to all existing Phase 8 checks.

## Fill and event wakeups

PAPER fill callback:

```text
new simulated fill
    ↓
bounded telemetry update
    ↓
strategy wakeup
```

Spread capture binds the accepted consensus retained at fill time. FillObservation
records reference price, consensus evaluation timestamp/source/version and the
eligible providers' normalized PriceEvidence (including source timestamps and
transport provenance). It never substitutes midpoint when consensus is absent;
reference price remains null. Runtime and simulation share this binding method.
Simulation prepares each frame's consensus before update_market can fill resting
orders, and retains that binding for immediate submit fills from the same frame.

No second runtime loop is introduced.

Agent event history is an in-memory deque capped at 250 entries. It records material supervisor changes and agent state changes. No database is added.

## APIs

Read-only:

```text
GET /api/v1/agents
GET /api/v1/agents/events
```

There is intentionally no agent trade/execute/order POST endpoint.

The terminal WebSocket includes:

```text
agents
agent_events
agent_quotes
```

## Simulation labeling

DEMO/PAPER agent evidence is marked `simulated=true`.

PAPER fill-derived toxic-flow and execution-quality metrics are simulated evidence and are displayed accordingly.

No claim of real agent trading performance is made from simulated evidence.
