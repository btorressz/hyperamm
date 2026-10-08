# HyperAMM — Project Summary
  
> Adaptive virtual AMM, market-making, risk, simulation, accounting, and operator-terminal research system for Hyperliquid.

---

## Current review status (2026-10-07)

Phases 1–12 are implemented, including all 12 active terminal pages. Implementation,
local fixture acceptance and live/external-provider acceptance are separate gates.
Historical acceptance counts below describe their merge milestones, not the current
suite. Phase 6–12 review status is not promoted by local tests; external provider,
authority and operational limitations remain tracked in
[Audit 1.0](AUDIT_REPORT_1.0.md). Recent hardening closed A1-018 through A1-023;
A1-024 through A1-027 are informational scope boundaries documented rather than
implemented as new runtime authority. PAPER remains deterministic and crossing-only;
TESTNET remains guarded. No mainnet,
custody or money movement is supported. History is bounded, in memory and limited
to the current session.

## 🚀 Overview

HyperAMM is a research-focused market-making infrastructure project built with:

- **Python 3.12**
- **FastAPI**
- **React**
- **TypeScript**
- **Hyperliquid Python SDK**

The project explores how AMM-style liquidity models can be adapted to operate over Hyperliquid's central-limit-order-book structure.

Rather than deploying a traditional on-chain AMM directly, HyperAMM internally models liquidity using AMM mathematics and then compiles that desired liquidity into executable CLOB bid/ask levels.

The system evolved through twelve major phases from basic Hyperliquid market data and PAPER execution into a broader trading-infrastructure stack containing:

- virtual constant-product AMM modeling
- concentrated liquidity
- inventory-aware quoting
- volatility adaptation
- order-book imbalance adaptation
- perpetual-market context
- multi-source reference-price validation
- deterministic institutional risk controls
- supervisory trading agents
- strategy simulation and optimization
- deterministic vault/accounting
- a full React trading and liquidity terminal

The system remains intentionally focused on:

**PAPER execution + guarded TESTNET research**

and does **not** claim production-mainnet readiness.

## Audit informational boundaries

Audit 1.0 findings A1-024 through A1-027 are documented design boundaries rather
than requests for new runtime behavior:

- virtual `k` defines AMM curve geometry while configured per-side liquidity budgets define emitted quote capacity;
- scientific libraries may support future offline research, but they do not own live signing, risk, position or capital authority;
- vault/accounting state is non-custodial, in-memory research accounting with explicitly partial TESTNET economics;
- semantic versions, decision fingerprints, observation sequences and simulation fingerprints each identify a declared scope rather than a complete raw-evidence or build-provenance archive.

---

# 🧠 Core Design Philosophy

HyperAMM separates:

```text
Strategy
    from
Risk
    from
Execution
    from
Accounting
    from
Observability
```

The system is designed so that increasingly intelligent strategy components can propose changes without becoming the final authority over execution.

The core hierarchy is:

```text
Market Evidence
      ↓
Perpetual Context
      ↓
Fair Value
      ↓
Virtual AMM
      ↓
Concentrated Liquidity
      ↓
Inventory Policy
      ↓
Volatility / Book Imbalance
      ↓
Supervisory Agents
      ↓
Risk Firewall
      ↓
Final Quote Authorization
      ↓
Quote Reconciliation
      ↓
PAPER / Guarded TESTNET Execution
      ↓
Accounting / Vault
      ↓
React Operator Terminal
```

A major principle throughout the project is:

> **Agents recommend. Deterministic infrastructure decides and executes.**

---

# 🏗️ High-Level Architecture

```text
                         Hyperliquid
                             │
                   Market / Perp Evidence
                             │
                             ▼
                ┌────────────────────────┐
                │ Normalized Market Data │
                └────────────┬───────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │   Perpetual Context    │
                │ Mark / Oracle / Funding│
                │ OI / Position / Basis  │
                └────────────┬───────────┘
                             │
                             ▼
                    Strategy Reference
                             │
                             ▼
                ┌────────────────────────┐
                │    Virtual AMM Core    │
                │       x * y = k        │
                └────────────┬───────────┘
                             │
                             ▼
                Concentrated Liquidity
                             │
                             ▼
                  Inventory-Aware Quotes
                             │
                             ▼
                 Volatility / L2 Adaptation
                             │
                             ▼
                  Supervisory Agents
                             │
                             ▼
             Multi-Source Reference Integrity
                             │
                             ▼
                  Phase 8 Risk Firewall
                             │
                             ▼
                FinalQuoteAuthorization
                             │
                             ▼
                  Quote Reconciliation
                             │
                             ▼
            PAPER / Guarded TESTNET Execution
                             │
                             ▼
               Deterministic Accounting
                             │
                             ▼
                    Vault / PnL / Equity
                             │
                             ▼
                 React Operator Terminal
```

---

# 📊 Phase 1 — Hyperliquid Market Data + PAPER Execution

The first phase established the market/execution foundation.

Implemented:

- Hyperliquid normalized market data
- L2 order book
- best bid / ask
- midpoint calculation
- DEMO market mode
- LIVE market mode
- PAPER execution adapter
- guarded TESTNET execution adapter
- normalized order models
- normalized fill models
- quote lifecycle management
- strategy start/stop behavior
- WebSocket terminal state

PAPER execution became the default environment for later strategy development.

Mainnet execution was intentionally excluded.

---

# 🧮 Phase 2 — Virtual Constant-Product AMM

Phase 2 introduced the internal AMM model.

The foundation is the classic constant-product relationship:

```text
x * y = k
```

The virtual pool maintains:

```text
virtual base reserve
virtual quote reserve
invariant k
AMM reference price
```

Instead of directly executing AMM swaps, the system samples the virtual AMM curve to determine how liquidity should be distributed around the current reference price.

This makes the AMM a **liquidity-generation model** rather than the exchange itself.

---

# 📚 Phase 3 — AMM Curve → CLOB Compiler

Phase 3 translated internal AMM liquidity into Hyperliquid-compatible order-book quotes.

The compiler:

```text
Virtual AMM Curve
       ↓
Sample Curve
       ↓
Calculate Reserve Deltas
       ↓
Normalize Price Tick
       ↓
Normalize Order Size
       ↓
Generate BID / ASK Levels
       ↓
CLOB Quote Ladder
```

An important design rule was preserving AMM-derived size differences rather than assigning identical fixed size to every order-book level.

The generated order ladder therefore represents the underlying liquidity curve rather than merely copying its prices.

---

# 🟢 Phase 4 — Concentrated Liquidity

Phase 4 extended the virtual AMM with concentrated-liquidity behavior.

The system can place more liquidity near the active price while reducing liquidity farther away.

Implemented concepts include:

- concentration factor
- lower concentration range
- upper concentration range
- normalized liquidity weights
- concentrated reserve allocation
- full-range fallback behavior

This allows HyperAMM to model both:

```text
Full-Range AMM Liquidity
```

and:

```text
Concentrated Liquidity
```

while still compiling the resulting liquidity to CLOB orders.

---

# 🛡️ Phase 4.1 — Execution Hardening

Phase 4.1 focused on execution correctness.

Major improvements included:

- fail-closed quote handling
- execution locking
- deterministic quote reconciliation
- stale-market invalidation
- cancellation behavior
- TESTNET reconciliation
- UNKNOWN exposure handling
- kill / resume behavior
- execution authority checks
- additional regression testing

The system established the rule that stale or invalid strategy authority cannot continue creating risk.

---

# 📦 Phase 5 — Inventory-Aware Quoting

Phase 5 added inventory management.

The strategy tracks:

```text
current position
target inventory
soft inventory limit
hard inventory limit
inventory ratio
```

Inventory may affect:

- reservation price
- BID size
- ASK size
- side suppression

Example:

```text
Too Long
   ↓
BIDs become less attractive / smaller
ASKs become more favorable for reducing inventory
```

Hard inventory limits remain deterministic safety constraints.

A strategy or agent cannot restore a side that inventory protection has suppressed.

---

# 🌊 Phase 6 — Volatility + Order-Book Imbalance

Phase 6 introduced market-adaptive quoting.

The system calculates:

## Realized Volatility

Using bounded historical midpoint observations and deterministic return calculations.

## L2 Book Imbalance

Using top-N bid and ask liquidity.

These signals can modify:

```text
spread multiplier
global size multiplier
BID size multiplier
ASK size multiplier
```

The policy is conservative:

- volatility may widen spreads
- volatility may reduce liquidity
- imbalance may modify side size
- market adaptation may not tighten beyond the base safety behavior
- hard inventory rules remain authoritative

---

# ♾️ Phase 7 — Perpetual vAMM Context

Phase 7 incorporated Hyperliquid perpetual-market evidence.

Inputs include:

- mark price
- oracle price
- funding rate
- open interest
- mark/oracle basis
- mark/mid basis
- oracle/mid basis
- TESTNET position evidence
- liquidation price
- leverage
- margin usage
- unrealized PnL

The strategy calculates a bounded:

```text
Strategy Reference Price
```

using market, mark, oracle, and funding context.

Funding influences the strategy reference price, but this is separate from accounting funding cash flows introduced later in Phase 11.

---

# 🌐 Phase 8 — Reference Integrity & Institutional Risk Firewall

Phase 8 introduced multi-source pricing and deterministic risk authority.

Reference hierarchy:

```text
RedStone
    PRIMARY EXTERNAL ORACLE

Hyperliquid oraclePx
    NATIVE ORACLE

Kraken
    INDEPENDENT EXCHANGE REFERENCE

CoinGecko
    TERTIARY AGGREGATE REFERENCE

Hyperliquid Mid
    VENUE EXECUTION EVIDENCE

Hyperliquid Mark
    PERPETUAL MARKET EVIDENCE
```

Reference evidence tracks:

- source
- price
- source timestamp
- observed timestamp
- freshness
- transport
- transport quality
- simulated/live status
- health
- provenance

Reference consensus states include:

```text
VERIFIED
DEGRADED
CONFLICTED
INSUFFICIENT
```

---

## 🔌 RedStone Provider Hardening

The RedStone integration was hardened after the initial Phase 8 implementation.

The provider hierarchy remains:

```text
RedStone Live WebSocket
    PRIMARY TRANSPORT

RedStone Public HTTP
    FALLBACK TRANSPORT
```

Both transports still represent **one RedStone provider vote**.

The public HTTP fallback does not become an additional oracle.

Transport provenance is tracked so the system can distinguish primary and fallback evidence.

Fallback RedStone evidence remains eligible for consensus but is conservatively capped rather than being treated as equivalent to a healthy primary live feed.

---

## 🛡️ Risk Firewall

Phase 8 introduced deterministic risk states:

```text
NORMAL
WIDEN
REDUCE
HALT
```

The firewall evaluates:

- reference integrity
- reference deviations
- stale data
- projected exposure
- inventory utilization
- drawdown
- equity
- liquidation distance
- accounting state
- manual kill state

Strategy output passes through the firewall before it can become executable.

Escalation is immediate while recovery may use hysteresis to avoid rapidly oscillating between states.

---

## 🔐 FinalQuoteAuthorization

Final executable quotes receive deterministic authorization containing provenance such as:

```text
market version
inventory version
perp version
reference version
agent version
risk version
accounting version
fingerprints
quote evidence
```

Material state changes invalidate stale authorization.

This creates a strong pre-transmission trust boundary.

---

# 🔴 Manual Kill Switch

The system contains a manual emergency kill mechanism.

Kill behavior is absolute:

```text
Manual Kill
     ↓
HALT
     ↓
No new risk
```

Automatic strategy logic cannot clear a manual kill.

Cancellation remains available so existing resting exposure can be removed.

---

# 🤖 Phase 9 — Supervisory Trading Agents

Phase 9 introduced deterministic and heuristic supervisory agents.

These are **not autonomous traders**.

Agents cannot:

- submit orders directly
- cancel orders directly
- replace orders directly
- restore inventory-suppressed sides
- override the risk firewall
- clear the kill switch
- enable mainnet
- bypass FinalQuoteAuthorization

Agents operate between strategy generation and Phase 8 risk.

```text
Base Strategy
      ↓
Phase 9 Agents
      ↓
Phase 8 Risk Firewall
      ↓
Final Authorization
```

---

## 🧠 Regime Agent

Classifies market conditions such as:

```text
QUIET
NORMAL
TRENDING
HIGH_VOL
DISLOCATED
```

Possible trend direction:

```text
UP
DOWN
NEUTRAL
```

Inputs may include:

- volatility
- momentum
- book imbalance
- funding
- basis
- reference state

Output may:

- widen spread
- reduce size
- reduce levels

---

## ☣️ Toxic Flow Agent

Analyzes fill behavior and post-fill markouts.

Signed markout logic distinguishes:

```text
BID fill
ASK fill
```

and measures whether price movement after execution was favorable or adverse.

The agent may conservatively:

- widen quotes
- reduce BID size
- reduce ASK size

It does not invent future observations.

Markouts mature only after the required future evidence actually exists.

---

## 📈 Execution Quality Agent

Evaluates execution quality using available evidence such as:

- fill count
- spread capture
- mature markouts
- reconciliation churn
- rejected orders
- unknown orders
- order lifecycle evidence

TESTNET does not fabricate unavailable fill-quality metrics.

---

## 🧩 Agent Supervisor

The AgentSupervisor combines recommendations conservatively.

Typical combination logic:

```text
spread = maximum requested widening

BID size = minimum recommendation

ASK size = minimum recommendation

levels = minimum allowed level count
```

The supervisor never creates more aggressive liquidity than the upstream strategy.

---

# 🧪 Phase 10 — Strategy Simulation & Optimization

Phase 10 added an offline deterministic research framework around the actual production strategy stack.

The simulator reuses:

```text
MarketPriceHistory
QuoteEngine
InventoryPolicy
MarketAdaptationPolicy
PerpContextPolicy
ReferenceConsensusPolicy
AgentSupervisor
RiskFirewall
FinalQuoteAuthorization
OrderManager
PaperExecutionAdapter
AccountingService
```

It does **not** implement a toy duplicate strategy.

---

## 🧭 Deterministic Scenarios

Built-in scenarios include conditions such as:

```text
QUIET
TREND_UP
TREND_DOWN
MEAN_REVERTING
HIGH_VOLATILITY
BID_HEAVY_BOOK
ASK_HEAVY_BOOK
FLASH_MOVE
ORACLE_DISLOCATION
REFERENCE_DEGRADATION
POSITIVE_FUNDING_STRESS
NEGATIVE_FUNDING_STRESS
```

Simulation frames contain deterministic:

- market data
- L2
- perp data
- mark
- oracle
- funding
- open interest
- external reference evidence

---

## ⏱️ Deterministic Simulation Clock

PAPER execution supports an injectable deterministic clock.

This ensures:

```text
same scenario
+
same config
=
same orders
same fills
same timestamps
same accounting
same metrics
```

---

## 📊 Simulation Metrics

Metrics include:

- starting equity
- ending equity
- session PnL
- return
- realized PnL
- unrealized PnL
- max drawdown
- fill count
- filled notional
- fill activity
- inventory exposure
- inventory utilization
- spread capture
- mature markout
- adverse fill rate
- reconciliation churn
- risk-state distribution
- agent-regime distribution

---

# ⚙️ Strategy Optimization

Phase 10 includes deterministic bounded grid search.

No:

- machine learning
- reinforcement learning
- LLM optimization
- Bayesian optimization
- autonomous live tuning

The optimizer evaluates explicitly allowlisted strategy and agent parameters.

Safety configuration remains immutable.

The optimizer cannot weaken:

```text
RiskFirewall
hard inventory limits
HALT thresholds
execution mode
reference safety
kill behavior
mainnet restrictions
```

Optimization compares:

```text
BASELINE

vs

Candidate Configurations
```

across:

```text
Training Scenarios
Validation Scenarios
```

with transparent objective-score components.

---

# 🧱 Phase 10.1 — Simulation Hardening

Phase 10.1 hardened the research layer.

Improvements included:

- simulation workload isolation from the FastAPI event loop
- bounded research concurrency
- one heavy research slot
- private worker-thread asyncio loop
- clean worker shutdown
- unexpected optimizer errors propagate
- invalid candidates remain rejected candidates
- code-owned simulation engine version
- fingerprint-bound engine provenance
- API spoof protection
- additional deterministic acceptance testing

Simulation cannot mutate the live runtime.

---

# 🏦 Phase 11 — Vault & Deterministic Accounting

Phase 11 introduced a dedicated accounting domain.

Architecture:

```text
Orders / Fills
      ↓
Accounting Events
      ↓
Immutable Ledger
      ↓
Position Accounting
      ↓
PnL
      ↓
Vault Equity
      ↓
Risk / Terminal
```

Accounting does not execute trades.

---

# 📒 Append-Only Ledger

The accounting ledger is:

- immutable
- append-only
- deterministic
- idempotent
- fingerprint chained

Each ledger entry binds:

```text
previous ledger fingerprint
economic event
post-entry balances
```

into a deterministic SHA-256 fingerprint.

---

# 🔁 Fill Idempotency

Repeated observation of the same fill does not double-book economics.

```text
Same Fill
   ↓
Already Accounted
   ↓
No Economic Change
```

Conflicting economics under the same identity fail closed.

---

# 📐 Average-Cost Position Accounting

Position convention:

```text
positive base = LONG
negative base = SHORT
```

The system supports:

```text
flat → long
flat → short
increase long
increase short
reduce long
reduce short
close long
close short
long → short reversal
short → long reversal
```

Example:

```text
LONG 1 @ 3000
SELL 2 @ 3100

→ close long 1
→ realize +100
→ open short 1 @ 3100
```

---

# 💰 PnL

Trading PnL uses one shared accounting implementation.

Long realized PnL:

```text
(fill - average entry) × closed quantity
```

Short realized PnL:

```text
(average entry - fill) × closed quantity
```

Unrealized PnL:

```text
(mark - average entry) × signed position
```

Net PnL:

```text
realized trading PnL
+
unrealized trading PnL
-
fees
+
funding
```

---

# 💸 PAPER Fees

PAPER fee accounting is explicitly simulated.

Fees may be configured using deterministic maker/taker fee rates.

They are labeled:

```text
PAPER_CONFIG
SIMULATED
```

The same fill cannot be charged twice.

---

# 💵 Funding Accounting

Funding used for strategy context remains separate from funding booked into accounting.

PAPER funding accrues at deterministic intervals.

Funding delta:

```text
-signed position × mark × funding rate
```

Positive accounting cash flow means funding was received.

Missing funding intervals are not silently interpolated.

---

# 📈 Vault Equity

PAPER vault equity:

```text
initial equity
+
realized PnL
+
unrealized PnL
-
fees
+
funding
```

The vault tracks:

- equity
- peak equity
- drawdown
- available capital
- reserved capital
- capital utilization
- accounting version
- accounting fingerprint

---

# 🔒 Capital Reservation

HyperAMM uses a conservative research capital-reservation model.

Reservation considers:

```text
current position exposure
+
effective desired/resting order exposure
```

KEEP/REPLACE overlap avoids accidental double counting.

This is explicitly:

**SIMULATED CAPITAL RESERVATION**

and is not represented as an exact clone of Hyperliquid's production margin engine.

---

# 🧾 Phase 11.1 — Accounting Integrity Hardening

Phase 11.1 hardened two major accounting invariants.

## 📈 High-Water Equity

Peak equity now updates after every committed economic change:

```text
fill + fee
funding
mark
```

rather than only during mark updates.

Invariant:

```text
peak_equity >= current_equity
```

for every complete valid PAPER accounting snapshot.

Intermediate equity highs between market marks are retained.

## 🔄 Execution / Accounting Consistency

The system explicitly compares:

```text
executed PAPER fills

vs

accounted TRADE_FILL events
```

and exposes:

```text
execution_fill_count
accounted_fill_count
unaccounted_fill_count
execution_accounting_consistent
```

Possible consistency states include:

```text
CONSISTENT
DIVERGED
UNAVAILABLE
```

If an executed fill is missing from accounting:

```text
Accounting becomes unavailable
CREATE blocked
REPLACE blocked
CANCEL still available
```

This ensures executed economic reality cannot silently diverge from the ledger.

A narrow internal reconciliation path can replay only safe pending PAPER fill evidence. Latched non-recoverable errors remain fail-closed rather than being silently cleared.

---

# 🖥️ Phase 12 — Full React Trading & Liquidity Terminal

Phase 12 transformed the project from a collection of strategy panels into a cohesive operator terminal.

Phase 12 is primarily:

```text
Frontend / UX / Visualization
```

with smaller backend observability enhancements.

No new trading authority was introduced.

---

# 🧩 Versioned Terminal Contract

The terminal uses a normalized backend contract:

```text
phase12-v1
```

Each frame contains:

```text
process_id
session_id
sequence
emitted_at
```

plus normalized state for:

- market
- strategy
- liquidity
- inventory
- perp context
- references
- agents
- risk
- execution
- vault
- accounting
- system health

---

# 🔢 Terminal Sequence

Terminal observations receive a process-wide monotonically increasing sequence.

This lets React detect:

- stale frames
- out-of-order frames
- process restart
- sequence gaps
- connectivity problems

Sequence is strictly observability metadata.

It has no trading authority.

---

# 🕒 Bounded Terminal History

Phase 12 includes a bounded in-memory terminal history.

Retained:

```text
3,600 observations
```

Maximum returned:

```text
1,000 observations
```

Available ranges include:

```text
1m
5m
15m
1h
Session
```

when enough current-session history exists.

No fake 4h/1d/24h history is generated.

History is:

```text
CURRENT SESSION ONLY
IN MEMORY
READ ONLY
NON-AUTHORITATIVE
```

---

# 📚 Structured Terminal Events

The terminal aggregates existing structured system events under categories including:

```text
MARKET
REFERENCES
STRATEGY
AGENTS
RISK
EXECUTION
ACCOUNTING
SYSTEM
```

The terminal exposes structured events instead of raw backend log files.

Sensitive credential-shaped values are redacted.

---

# ❤️ System Health

Phase 12 introduced observational system-health aggregation.

Subsystems include:

- market feed
- perp context
- references
- consensus
- RedStone transport
- agents
- risk
- final authorization
- execution
- venue reconciliation
- accounting
- execution/accounting consistency
- strategy

Normalized statuses:

```text
HEALTHY
DEGRADED
HALTED
UNAVAILABLE
```

System health is explicitly:

```text
OBSERVATIONAL
```

and never overrides the actual underlying risk/execution authorities.

---

# 🖥️ Terminal Pages

The current Phase 12 terminal contains twelve active pages:

```text
Dashboard
Markets
Strategy
AMM Settings
Execution
Risk
Supervisory Agents
Vault
Analytics
Simulation & Optimization
Logs
Settings
```

No Phase 12 navigation entry remains a placeholder.

---

# 📊 Dashboard

The Dashboard provides a high-density operator overview containing:

- market state
- price/liquidity chart
- L2 order book
- quick strategy controls
- operator KPIs
- liquidity distribution
- strategy attribution
- inventory skew
- supervisory-agent state
- recent execution
- system/reference/risk health

The dashboard reflects actual HyperAMM state rather than illustrative mockup values.

---

# 📉 Price & Liquidity Visualization

The terminal charts:

- midpoint
- fair value
- strategy reference
- mark
- Hyperliquid oracle
- reference consensus
- authorized BID
- authorized ASK

Charts use backend observation timestamps.

The Lightweight Charts instance is retained and updated incrementally instead of being recreated on every update.

---

# 📖 Order Book

The Hyperliquid L2 view includes:

- BID levels
- ASK levels
- cumulative depth
- spread
- spread bps
- depth shading
- imbalance
- feed freshness
- observation sequence

---

# 🌊 Liquidity Distribution

The terminal can visualize liquidity across quote distance.

Views include real backend-produced stages such as:

```text
Raw AMM

Strategy

Authorized
```

No AMM math is recreated in React.

---

# 🔬 Liquidity Pipeline

One of the major Phase 12 visualizations shows how an individual quote evolves through the system:

```text
Raw AMM
     ↓
Inventory
     ↓
Market Adaptation
     ↓
Perpetual Context
     ↓
Supervisory Agents
     ↓
Risk
     ↓
Final Authorized
     ↓
Resting CLOB
```

Each stage may expose:

- price
- size
- transformation factors
- survival/suppression state
- authorization provenance

Missing stages remain unavailable. Some retained lineage labels are approximate;
Audit 1.0 A1-021 qualifies exact per-stage provenance. A1-020 tracks history/live
chart ordering; local visual acceptance did not establish production authority.

---

# 📦 Inventory Skew Visualization

The terminal visualizes BID/ASK liquidity distribution relative to inventory.

It also exposes:

- current position
- target position
- inventory ratio
- reservation price
- BID size multiplier
- ASK size multiplier
- hard-limit state

---

# 🧮 Strategy Attribution

The terminal explains the current strategy using actual implemented transformations such as:

- perpetual reference shift
- inventory skew
- volatility score
- market spread multiplier
- market size multiplier
- book imbalance
- agent spread multiplier
- agent size multipliers
- risk spread multiplier
- risk size multiplier

It avoids inventing fake additive attribution when the real implementation uses multiplicative transformations.

---

# 🎛️ Strategy Controls

The Dashboard provides compact controls for common operations.

Advanced configuration is separated into:

```text
AMM Settings
```

The UI supports:

- strategy start
- strategy stop
- manual kill
- resume
- AMM configuration
- inventory configuration
- market adaptation
- perp configuration
- execution mode
- DEMO/LIVE market mode

The emergency kill action remains immediately accessible.

Resume may require confirmation.

---

# 📈 Strategy Page

The Strategy page answers:

> What is HyperAMM doing right now?

It displays:

- strategy status
- AMM model
- pool state
- current reference
- inventory policy
- market adaptation
- perp context
- strategy quotes
- agent quotes
- final quotes
- authorization
- liquidity pipeline

---

# ⚙️ AMM Settings

AMM Settings provides the advanced configuration interface.

It includes:

- AMM model
- virtual reserves
- concentration
- quote levels
- liquidity
- inventory limits
- inventory skew
- volatility thresholds
- book imbalance
- perp context
- refresh settings
- market/execution mode

The form includes:

- dirty-state preservation
- save/reset
- validation errors
- busy state
- success feedback
- context-change warnings

Backend validation remains authoritative.

---

# 🔄 Execution Page

The Execution page exposes:

- open orders
- recent order history
- PAPER fills
- reconciliation actions
- venue reconciliation
- execution quality
- rejected orders
- unknown orders
- order churn
- execution mode

For TESTNET, unavailable normalized fill history is shown explicitly as unavailable rather than as zero activity.

---

# 🌐 Markets Page

The Markets page provides market microstructure instead of raw JSON.

It includes:

- L2 order book
- BBO
- spread
- midpoint
- fair value
- mark
- oracle
- reference consensus
- funding
- open interest
- basis
- volatility
- book imbalance
- provider state
- connection/freshness status

---

# 🛡️ Risk Page

The Risk page exposes:

- manual kill state
- automatic risk state
- final authorization
- reference confidence
- projected exposure
- inventory utilization
- capital utilization
- vault drawdown
- liquidation distance
- accounting consistency
- authorization fingerprint
- recent risk-state transitions

Phase 8 remains the actual risk authority.

---

# 🤖 Supervisory Agents Page

The terminal presents the actual Phase 9 components:

```text
Regime Agent
Toxic Flow Agent
Execution Quality Agent
Agent Supervisor
```

It does **not** invent:

```text
Optimization Agent
Risk Supervisor Agent
```

because:

- Phase 10 optimization is offline research
- Phase 8 risk is separate deterministic authority

---

# 🏦 Vault Page

The Vault page displays Phase 11 accounting state.

It includes:

- equity
- peak equity
- drawdown
- settled capital
- available capital
- reserved capital
- capital utilization
- current position
- average entry
- realized PnL
- unrealized PnL
- fees
- funding
- net PnL
- execution/accounting consistency
- ledger
- accounting provenance

Phase 12 also adds bounded session charts for:

- equity
- high-water mark
- drawdown
- capital utilization
- exposure

---

# 📊 Analytics Page

Live session analytics include:

- equity curve
- PnL curve
- drawdown
- inventory exposure
- capital utilization
- fill activity
- filled notional
- spread capture
- mature markout
- adverse fill rate
- reconciliation churn
- retained risk-state distribution
- retained agent-regime distribution

Offline simulation results remain clearly separate from live-session metrics.

---

# 🧪 Simulation & Optimization Page

The Phase 10 research workflow remains available through the terminal.

The interface supports:

- deterministic scenarios
- simulation metrics
- baseline comparison
- optimization candidates
- training vs validation
- score components
- candidate comparison

There is intentionally no:

```text
Apply Best
Deploy Strategy
Auto Tune
Trade Candidate
```

action.

Optimization remains research-only.

---

# 📜 Logs Page

The Logs page is a structured system-event timeline.

It supports filters such as:

```text
ALL
MARKET
REFERENCES
STRATEGY
AGENTS
RISK
EXECUTION
ACCOUNTING
SYSTEM
```

It does not expose raw backend application logs or credentials.

---

# ⚙️ Settings Page

Settings contains safe terminal preferences and read-only diagnostics.

Possible UI settings include:

- display precision
- chart range
- compact layout
- history size

It does not expose:

- private keys
- API tokens
- RedStone credentials
- environment secrets

---

# 🔌 WebSocket Resilience

The React terminal handles:

```text
CONNECTING
CONNECTED
DISCONNECTED
STALE
ERROR
```

Reconnect backoff is bounded approximately:

```text
1.5s
3s
6s
10s max
```

The terminal detects:

- malformed payloads
- unsupported contracts
- non-increasing sequences
- backend restarts
- sequence gaps
- stale terminal connection

The last valid state is retained when malformed payloads are rejected.

---

# 📱 Responsive Terminal

Phase 12 added responsive layouts for:

```text
large desktop
compressed desktop
tablet
narrow stacked layouts
```

Tables remain horizontally scrollable where appropriate.

The system remains designed primarily as a professional trading terminal rather than a mobile-first consumer application.

---

# 🧪 DEMO / PAPER / TESTNET Truth Boundaries

The terminal explicitly labels the source and reliability of data.

## DEMO

```text
DEMO
SIMULATED
```

remains visible.

## PAPER

PAPER execution/accounting is clearly labeled simulated.

## TESTNET

TESTNET is guarded and may contain:

```text
PARTIAL
UNAVAILABLE
```

accounting/economic fields.

The system does not fabricate unavailable TESTNET:

- normalized fills
- realized PnL
- fees
- funding payments
- cash
- capital availability

---

# 🔐 Safety Boundaries

HyperAMM intentionally does NOT include:

```text
❌ mainnet launch
❌ wallet custody
❌ deposits
❌ withdrawals
❌ transfers
❌ bridging
❌ investor fund shares
❌ KYC
❌ autonomous optimizer deployment
❌ LLM trading authority
❌ direct agent order execution
❌ risk-bypass APIs
```

The project remains:

```text
Research Infrastructure
+
PAPER Trading
+
Guarded TESTNET
```

---

# 🧱 Authority Hierarchy

The final authority model is:

```text
Strategy
    proposes liquidity

Inventory
    constrains inventory risk

Market Adaptation
    widens/reduces under market conditions

Supervisory Agents
    recommend additional caution

Reference Integrity
    validates market evidence

Risk Firewall
    decides whether risk may exist

Accounting
    determines capital/equity truth

FinalQuoteAuthorization
    binds trusted state

OrderManager
    reconciles desired vs resting liquidity

Execution Adapter
    transmits only authorized actions
```

No React component or terminal health indicator becomes part of that authority.

---

# 🧪 Validation

The repository grew substantially throughout the roadmap.

Historical locally accepted test milestones included:

```text
Phase 4.1
88 tests passing

Phase 8.2
287 tests passing

Phase 10.1
407 tests passing

Phase 11
492 tests passing

Phase 11.1
517 tests passing

Phase 12
546 tests passing
```

Historical Phase 12 acceptance at merge (2026-10-06, America/Los_Angeles):

```text
Python 3.12.14

546 passed
1 warning
```

The remaining warning is an upstream Starlette/httpx deprecation warning rather than a HyperAMM test failure.

Phase 12 also passed:

- FastAPI startup/shutdown
- REST endpoint acceptance
- WebSocket acceptance
- sequential terminal-frame acceptance
- terminal contract validation
- bounded-history validation
- structured-event validation
- frontend TypeScript typecheck
- production frontend build
- Chromium page rendering
- responsive layout testing
- malformed/out-of-order payload handling
- stale terminal handling
- TESTNET partial-state rendering
- `git diff --check`

---

# 🖥️ Historical Phase 12 Frontend Acceptance (2026-10-06)

The completed React terminal contains twelve active pages and passed browser rendering without page-level errors.

Responsive checks included widths approximately:

```text
1600px
1200px
900px
600px
390px
```

The terminal avoids document-level overflow while allowing internal tables/panels to scroll where required.

---

# 📡 Phase 12 Terminal Payload

The live terminal snapshot contains normalized state including:

```text
contract_version

process_id
session_id
sequence
emitted_at

market
strategy

fair_value
pool

strategy_quotes
agent_quotes
authorized_quotes
quotes

inventory
market_adaptation
perp_context

references
reference_consensus

agents
agent_events

risk_firewall
risk_authorization
risk_events

projected_exposure
pnl_drawdown

vault
accounting

orders
fills

venue_reconciliation
reconciliation

system_health
execution_summary
diagnostics
```

Heavy data such as:

```text
full history
full ledger
simulation traces
optimizer result sets
```

is intentionally excluded from every WebSocket frame.

---

# 🗂️ Project Areas

The project is organized broadly around:

```text
backend/app/

amm/
strategy/
market_data/
references/
risk/
agents/
execution/
simulation/
accounting/
terminal/
api/
```

Frontend areas include:

```text
frontend/src/

pages/
components/
hooks/
stores/
utils/
```

Each major architecture phase has dedicated domain separation rather than placing all logic inside the runtime or UI.

---

# 📌 Current Roadmap Status

```text
Phase 1
Market data + PAPER execution
✅ COMPLETE

Phase 2
Virtual constant-product AMM
✅ COMPLETE

Phase 3
AMM → CLOB compiler
✅ COMPLETE

Phase 4
Concentrated liquidity
✅ COMPLETE

Phase 4.1
Execution acceptance/hardening
✅ COMPLETE

Phase 5
Inventory-aware quoting
✅ COMPLETE

Phase 6
Volatility + book imbalance
🟡 IN REVIEW

Phase 7
Perpetual vAMM context
🟡 IN REVIEW

Phase 8
Reference integrity + risk firewall
🟡 IN REVIEW

Phase 9
Supervisory agents
🟡 IMPLEMENTED / IN REVIEW

Phase 10
Strategy optimization + simulation
✅ BUILD / HARDENING DONE

Phase 10.1
Simulation runtime/provenance hardening
✅ ACCEPTED

Phase 11
Vault / accounting
✅ BUILD DONE

Phase 11.1
Accounting invariant hardening
✅ ACCEPTED

Phase 12
Full React trading / liquidity terminal
✅ IMPLEMENTED / IN REVIEW
```

---

# ⚠️ Remaining Limitations

The full Phase 1–12 implementation roadmap exists, but this does not mean the system is production-mainnet ready.

## Phase 8 External Provider Acceptance

Real external-provider acceptance remains separate from offline deterministic acceptance.

The project still needs environment-supported live verification of the complete reference-provider stack where required.

## Phase 9 Review Status

Phase 9 remains implemented/in review even though later phases successfully reuse its architecture.

## Session History

Terminal history is:

```text
in-memory
current-session
bounded
```

There is no durable:

```text
24h
multi-day
historical database
```

storage.

## TESTNET Fill History

Normalized authoritative TESTNET fill history remains unavailable where the existing SDK/runtime does not provide it.

The terminal explicitly reports this rather than fabricating data.

## No Mainnet

HyperAMM intentionally remains PAPER / guarded TESTNET focused.

---

# 🎯 What HyperAMM Demonstrates

From an engineering/research perspective, HyperAMM demonstrates how several normally separate trading-system concerns can be composed into one architecture:

```text
AMM mathematics

CLOB liquidity generation

inventory management

market microstructure

volatility adaptation

perpetual-market signals

oracle/reference integrity

institutional risk controls

deterministic agent supervision

execution reconciliation

strategy simulation

parameter optimization

ledger accounting

capital management

operator observability
```

while keeping deterministic safety infrastructure downstream from strategy intelligence.

---

# 💡 Research Goal

The original research question was:

> How can AMM-style liquidity models be adapted to work effectively with Hyperliquid's order-book structure?

The project evolved into a broader question:

> How can AMM-derived liquidity, adaptive market-making logic, deterministic risk controls, supervisory agents, execution evidence, accounting provenance, simulation, and operator observability be composed into one coherent market-making infrastructure stack?

HyperAMM is the result of exploring that architecture.

---

# 📝 Short Project Description

I built a research-focused Python/FastAPI + React/TypeScript adaptive virtual AMM and market-making system for Hyperliquid, covering constant-product and concentrated-liquidity models, inventory-aware quoting, volatility and order-book adaptation, perpetual-market context, CLOB order generation, multi-source price validation, deterministic institutional risk controls, supervisory trading agents, strategy simulation and optimization, deterministic vault/accounting infrastructure, and a full React operator terminal.

The goal was to explore how AMM-style liquidity models could be translated into adaptive bid/ask liquidity for Hyperliquid's order-book structure while maintaining clear trust boundaries between strategy, risk, execution, accounting, and observability.

---

# ✅ Final Implementation Status

The complete planned Phase 1–12 implementation roadmap is now present.

```text
Market Data
      ↓
Virtual AMM
      ↓
Concentrated Liquidity
      ↓
Inventory
      ↓
Market Adaptation
      ↓
Perpetual Context
      ↓
Supervisory Agents
      ↓
Reference Integrity
      ↓
Risk Firewall
      ↓
Final Authorization
      ↓
Execution
      ↓
Accounting
      ↓
Simulation / Optimization
      ↓
Full Operator Terminal
```

The project should currently be described as:

**A comprehensive research-grade market-making infrastructure stack for Hyperliquid with PAPER execution, guarded TESTNET integration, deterministic risk/accounting authority, offline simulation/optimization, and a full operator terminal.**

It should not yet be described as:

**production-mainnet trading infrastructure.**
