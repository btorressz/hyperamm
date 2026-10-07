# Supervisory Agents

The `agents` package implements Phase 9's deterministic/heuristic supervisory layer.

The governing rule is:

> **Agents recommend. Deterministic infrastructure decides and executes.**

These agents do not call Hyperliquid, do not own credentials, do not bypass the Phase 8 firewall, and do not have unrestricted order authority.

## Position in the pipeline

```text
Phase 7/6/5 strategy output
        ↓
BASE STRATEGY QUOTES
        ↓
Regime Agent
Toxic-Flow Agent
Execution-Quality Agent
        ↓
AgentSupervisor
        ↓
bounded post-agent quotes
        ↓
Phase 8 references + RiskFirewall
        ↓
FinalQuoteAuthorization
        ↓
execution
```

## Files

| File | Responsibility |
|---|---|
| `config.py` | Bounded agent settings, enable flags, thresholds and maximum/minimum allowed adaptations. |
| `models.py` | Evidence, recommendation, health, regime/toxic/execution states, supervisor decision and event contracts. |
| `evidence.py` | Builds normalized agent evidence and owns bounded fill/reconciliation telemetry used by the agents. |
| `regime.py` | Classifies warming-up/quiet/normal/trending/high-volatility/dislocated conditions using existing normalized market/perp/reference evidence. |
| `toxic_flow.py` | Measures matured signed post-fill markouts and side-specific adverse-flow behavior without trader-identity inference. |
| `execution_quality.py` | Evaluates spread capture, mature markout, order status and reconciliation churn when authoritative evidence exists. |
| `supervisor.py` | Runs agents, handles individual-agent failures, composes conservative recommendations, versions/fingerprints the decision and transforms quotes. |
| `__init__.py` | Public package exports. |

## Conservative composition

The supervisor is intentionally one-way:

- spread multiplier = most conservative/widest recommendation;
- BID/ASK size multiplier = smallest recommendation;
- max levels = smallest non-null recommendation;
- agents cannot restore inventory-suppressed liquidity;
- agents cannot intentionally tighten below the upstream strategy;
- warmup/insufficient-data recommendations remain neutral.

Post-agent quotes and the supervisor version/fingerprint are passed to Phase 8 and bound into final authorization.

## Agent semantics

### Regime Agent
Uses Phase 6 volatility/imbalance plus bounded momentum, basis/funding and reference state to characterize the current environment.

### Toxic-Flow Agent
Uses fill-time evidence and the first eligible future reference after the configured horizon to calculate signed markouts. The selected observation sequence, timestamp, reference price, target maturity time and computed markout are frozen per fill and horizon for the lifetime of the retained fill. Future evidence remains pending until available; if history eviction or clearing has discarded the required maturity observation before selection, the result is terminally unavailable (reported in telemetry summary), rather than replaced with a newer sample.

### Execution-Quality Agent
Uses normalized fills/order/reconciliation evidence. Spread capture uses accepted
consensus retained at fill time, recording price, consensus timestamp/source/version
and eligible normalized provider provenance. Runtime and simulation share this
binding; simulation prepares consensus before any frame fills. Missing consensus
stays unavailable without midpoint substitution. Churn is `(REPLACE + CANCEL) /
max(1, CREATE + REPLACE + CANCEL)`; KEEP remains observable and cannot dilute or
evict runtime action evidence. GOOD requires mature non-negative markouts as well
as positive capture; without mature markouts quality is provisional NORMAL (or
INSUFFICIENT_DATA with too few fills), with an explicit reason. Poor evidence can
still produce POOR. TESTNET metrics requiring an authoritative normalized fill
ledger remain unavailable instead of being synthesized.

## Failure boundary

This is a deliberate soft/optional supervisory failure policy: an individual
exception produces `AgentHealth.ERROR` and a fresh neutral recommendation while
remaining agents continue. Stale prior advice is never silently reused. ERROR may
be less conservative than that agent's previous successful recommendation, but
quotes remain bounded by the current upstream ladder (no tightening or size
increase beyond upstream, no restored levels/sides). ERROR does not authorize
execution. Phase 8 deterministic risk, structural validation and
FinalQuoteAuthorization remain authoritative. The error and reason are visible
in agent output; this tradeoff does not make agents sticky execution authority.
