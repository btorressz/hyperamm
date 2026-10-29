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

---

# Latest HyperAMM updates — October 14, 2026

> **About this update:** Everything above is the original detailed Phase 1–12 summary and has been kept unchanged. This section explains, in plain English, the important features, improvements, and fixes merged afterward. The earlier "Current review status (2026-10-07)" is a historical snapshot, not today's full feature list.

## What HyperAMM can do now

HyperAMM has grown beyond its original virtual AMM and PAPER trading terminal. It is now a local, open-source market-making and research platform that brings together liquidity modeling, market data, conservative risk checks, supervised strategy decisions, accounting, simulation, and a detailed React interface.

The original trading and quote-management system remains separate from newer market-intelligence features. The active operational system is not automatically switched when someone browses BTC, ETH, or SOL market data or chooses a different market for a research simulation.

The project can be explored using deterministic DEMO market data and PAPER execution. Some Hyperliquid TESTNET functionality is guarded separately. **Mainnet trading, custody, deposits, withdrawals, and money transfers are not supported or claimed to be ready.**

## Additional improvements to the original trading system

After the first twelve phases, the repository received several rounds of independent audits and targeted improvements:

- **Safer outgoing orders:** The system now checks the exact price and size that would reach the Hyperliquid SDK, including venue rounding, before final authorization. This prevents an authorized mathematical quote from quietly becoming a different order on the wire.
- **More reliable market data:** Changes to an order book are tracked even when the exchange timestamp stays the same. Out-of-order or replayed evidence cannot silently replace the current trusted market state.
- **Stronger reconnection and shutdown:** Hyperliquid and terminal WebSocket handling has more explicit ownership, cleanup, retry, and recovery behavior. Genuine long-running exchange acceptance is still a separate test.
- **More reliable fills and accounting:** Closed-order history is bounded, duplicate order slots are handled more carefully, and simulated fills are checked against accounting records.
- **Clearer price timestamps:** The time attached to an exchange price stays tied to that price. A newer message or terminal refresh does not make older market evidence current again.
- **Safer configuration changes:** Runtime startup, shutdown, and configuration updates have stricter ordering. When an important transition fails, new quote creation is blocked rather than assuming recovery succeeded.
- **More accurate measurements:** Volatility sampling and execution-quality calculations now state their assumptions, check numerical limits, and preserve evidence used in their results.
- **Better audit history:** Audit 1.0 and Audit 2.0 document what was checked, what was corrected, and what still needs outside testing. Not every audit finding was a production defect, and not every remaining acceptance gate is closed.

These improvements are covered in the linked [changelog](CHANGELOG.md), [Audit 1.0](AUDIT_REPORT_1.0.md), and [Audit 2.0](AUDIT_REPORT_2.0.md).

## More capable supervisory agents and optional predictive research

The original Regime, Toxic Flow, and Execution Quality agents were expanded to explain more about market conditions and simulated execution:

- **Regime Agent improvements:** More context from price movement, order-book pressure, funding, basis, and inventory.
- **Toxic Flow improvements:** Several post-fill observation periods, stronger sample tracking, and clearer evidence about whether a fill was followed by an unfavorable price move.
- **Execution Quality improvements:** Better PAPER fill timing, partial-fill and order-lifetime observations, while leaving unavailable TESTNET measurements unavailable.
- **Liquidity Quality Agent:** Examines whether the visible order book shows enough liquidity and whether that liquidity is uneven or weak.
- **Perpetual Crowding Agent:** Looks at supported funding, open interest, and related perpetual-market observations without treating any single signal as proof of crowding.
- **Optional predictive adverse-selection research:** An offline logistic-regression model can be trained and evaluated using controlled historical research features and labels.

**Important:** Predictive machine learning remains in SHADOW mode. It provides research observations only and cannot place trades, change executable quotes, relax risk checks, or automatically become an active trading model. Deterministic risk rules and FinalQuoteAuthorization still decide what may be sent to the execution layer.

## Price providers and market-data integrity

The reference-price system was also improved:

- **RedStone:** The primary live transport has a separate public HTTP fallback. Both count as one RedStone source, not two independent votes.
- **CoinGecko:** Enabled requests require the appropriate Demo or Pro API key and use the expected secure host and header. Bad settings and provider errors are handled conservatively.
- **Kraken and Hyperliquid:** Their exchange and perpetual evidence continue to have distinct source roles and freshness rules.
- **Yahoo Finance:** An optional research-only observation source was added. Its data can appear in read-only diagnostics but does not influence trading consensus, risk decisions, authorization, or accounting.

The system distinguishes prices supplied by the exchange, prices from external providers, and simulated DEMO data. A price arriving through a new transport does not automatically prove that the underlying economic information is new. Actual provider connectivity, usage rights, and live-network acceptance remain subject to separate checks.

## Optional Redis infrastructure

HyperAMM can optionally connect to Redis to help distribute terminal updates and coordinate limited research and WebSocket resources.

In plain English, Redis can temporarily hold the latest terminal snapshot, share selected updates, track whether a worker is alive, and help enforce limits on simultaneous browser/research activity. The existing application still owns strategy, risk, orders, and accounting; Redis does **not** become the trading engine.

Redis is **off by default**. It is an optional temporary coordination layer, not a permanent trade database. The project does not yet implement PostgreSQL-based durable accounts, permanent ledger recovery, or a distributed multi-worker trading service.

See [Redis documentation](docs/REDIS.md) for configuration and limits.

## Phase 12.1–12.3 — Reliability improvements to the operator terminal

After the original Phase 12 terminal was built, three focused updates made it safer to use:

- **12.1 — WebSocket reliability:** Better handling when browser clients disconnect, tests stop, and background connection tasks are cancelled.
- **12.2 — Quote and liquidity accuracy:** Execution-facing quote checks now use the prices actually rounded to exchange ticks. The interface can also show how liquidity is grouped at those executable prices.
- **12.3 — Freshness and session protection:** Old terminal sessions, timestamps that are far outside acceptable time, and replayed messages cannot pretend to be current market evidence.

These updates improve reliability and clarity; they do not replace the original PAPER/TESTNET execution authority.

## Phase 13 — Improved React interface and research experience

Phase 13 made the terminal easier to navigate, inspect, and use for research while keeping its existing safety rules.

### Phase 13.1 — Navigation and visual design

The React application gained a more consistent dark, professional-looking interface. Its twelve main pages have clearer navigation, bookmarkable routes, better browser back/forward behavior, saved sidebar preferences, and mobile-friendly navigation.

### Phase 13.2 — Trading workspace clarity

The quote and execution pages now better distinguish:

- A **proposed** quote that has not yet been authorized.
- A quote **authorized** by the backend.
- An order that is actually **retained/resting** in the execution view.
- An order or quote with **uncertain, outdated, or historical** evidence.

Execution history gained better filtering, sorting, and order-detail inspection. These improvements avoid suggesting that a proposed quote is already a filled trade. This phase focused mainly on the interface; it did not introduce new signing or order authority.

### Phase 13.3 — Agents, Vault, Analytics, Simulation, Logs and Settings

- **Agents:** Clearer cards explaining each agent's observations, advice, reasons, and available supporting evidence.
- **Vault:** Better viewing of simulated equity, ledger entries, accounting consistency, and which backend session the information belongs to.
- **Analytics:** More useful charts for equity, profit and loss, drawdown, inventory and capital use, with history-range and freshness information.
- **Simulation:** Better charts, traces, simulated performance summaries, and optimizer-result inspection.
- **Logs:** Searchable and filterable operational events with clearer session identity.
- **Settings:** A cleaner separation between local display preferences and read-only backend settings.

The added frontend pages and controls continue to use backend evidence instead of calculating or granting trading permission in the browser.

## Phase 14 — Customizable Research Vault

Phase 14 added a separate place to experiment with **hypothetical research settings** without changing the live operational Vault.

Researchers can now:

- Choose from prepared capital/fee/funding research presets.
- Make controlled changes to allowed starting equity, simulated fees, funding settings, and capital-utilization assumptions.
- Preview whether those settings are valid before running research.
- Run the existing PAPER simulator or bounded optimizer using an accepted research configuration.
- Compare a preset baseline with a customized configuration using a controlled, shared simulation dataset.
- See differences in simulated results and inspect which exact settings produced them.

The original accounting and risk settings are still protected. Choosing a research preset does not move money, change real balances, or deploy a trading strategy.

### Phase 14.6 — BTC, ETH and SOL research markets

Research is no longer tied to ETH-like price assumptions for every run. A researcher can select **BTC-PERP, ETH-PERP or SOL-PERP** for an individual PAPER study. The system uses market-specific pricing and size rules and identifies whether metadata came from the exchange or from a clearly marked DEMO research profile.

Each run still studies **one selected market at a time**. This is not a live multi-market portfolio engine, and selecting a research market does not switch the market used by the operational trading service.

## Phase 15 — Independent Live Market Intelligence

Phase 15 is a larger new area of HyperAMM, separate from the original operator's quote-generation and execution controls.

### Phase 15.1 — Read-only market snapshots

Added a separate, opt-in way to request native Hyperliquid market observations for BTC, ETH and SOL. The results can contain order-book prices and sizes, midpoint, spread, mark, oracle, funding, open interest, source timestamps, and reasons why evidence is missing or stale.

The service is **read-only**. It cannot use a market-data request to start the strategy, switch execution markets, or place an order. External networking is disabled by default.

### Phase 15.2 — Read-only live streams and provider health

Added a separate WebSocket observation service for BTC, ETH, and SOL. It is designed to receive native order-book and perpetual-market updates, maintain bounded recent observations, reconnect safely, and publish status to browser clients.

Source freshness, observer identity, generation changes, and provider health are tracked so that a disconnected, replaced, or outdated stream cannot simply appear current. The external sources listed in this view are not automatically enabled, and several native values come from **one Hyperliquid source group**, not independent sources.

### Phase 15.3 — Live Markets terminal

The Markets page now includes an **independent Live Market Intelligence view** alongside the original Operational Market view.

A visitor can select BTC, ETH, or SOL for observation without changing the strategy's trading market. The live view includes:

- A selected-market overview and read-only price history.
- A native order-book display and spread information.
- Mark price, oracle price, funding, and open-interest context.
- Source and provider-health information with timestamps.
- Visible connecting, stale, unavailable, reconnecting, and recovery states.
- Layouts checked on desktop, tablet, and mobile sizes.

This workspace can still show a useful disabled/unavailable state even when the original operational terminal is not connected.

### Phase 15.4 — Market vs Research Comparison and Explainability

HyperAMM can now show **actual observed market evidence next to a completed hypothetical PAPER simulation** for the same selected market.

For example, a user can inspect a BTC order-book midpoint observed by the read-only service and compare it with the midpoint assumed by a completed BTC research scenario. Where the evidence supports it, the interface also shows differences in bid/ask prices, spread, funding, and visible book depth.

The comparison explains which numbers can be compared, which are missing, and how the results were produced. Existing simulation performance, including PAPER profit and loss, remains clearly labeled **hypothetical**.

These numbers are not necessarily from the same point in time. A live snapshot compared with an older synthetic scenario is **not** a matched historical backtest, proof that the strategy would have filled, or evidence of realized profit.

Research results submitted by the browser are structurally checked but are **not authenticated proof of a previous server-run simulation**. The comparison feature is computational and does not automatically optimize, trade, or apply new strategy settings.

### Phase 15.5 — Security, Regression and Final Acceptance (not implemented yet)

Phase 15.5 is the remaining planned work for final security review, WebSocket and SDK lifecycle testing, frontend stale-data display, full regression, real-browser checks, and permitted live-provider acceptance. The repository must not describe this phase as complete until the work and its evidence are actually present.

## What is different in the terminal today?

The original twelve-page navigation remains. Inside the **Markets** page, users now have three distinct ways to inspect information:

1. **Operational Market:** The existing strategy-facing market and quote evidence.
2. **Live Market Intelligence:** Independent read-only BTC/ETH/SOL exchange observations, if available and enabled.
3. **Market vs Research:** A frozen comparison between a selected market observation and a separately completed PAPER simulation.

The **Simulation** and **Vault** pages have also become more capable research interfaces. They let users experiment with controlled hypotheses and view results without making those experiments authoritative for real orders or capital.

## Testing and development status

Phases 13, 14, 14.6 and 15.1–15.4 have merged code and documented local acceptance. The most recent full-suite results recorded for **Phase 15.4** were:

- **1,649 backend tests passed**.
- **602 frontend tests passed**.
- **TypeScript checking and the production frontend build passed**.
- **15 Chromium browser workflows were recorded across six viewport sizes**, using controlled local/fixture evidence.

Those are results **reported in the Phase 15.4 acceptance document**, not a claim that this documentation update reran the test suite. Read [Phase 15.4 acceptance](docs/PHASE154_ACCEPTANCE.md) for the exact conditions and findings, or the earlier [15.3](docs/PHASE153_ACCEPTANCE.md), [15.2](docs/PHASE152_ACCEPTANCE.md), and [15.1](docs/PHASE151_ACCEPTANCE.md) reports.

## What HyperAMM does not yet claim

- **No production-mainnet execution.** Guarded TESTNET code and PAPER tests are not proof of completed signed venue acceptance.
- **No unrestricted public or multi-user deployment.** The current application is designed for local, single-operator research. Loopback and CORS checks are not user authentication.
- **No guaranteed live external data.** Genuine Hyperliquid REST/WebSocket connection, reconnect/soak behavior, and permitted provider access must be verified separately from fixtures.
- **No permanent market-history database.** Bounded observation history and optional Redis caches are not durable exchange-history storage.
- **No real or automatically trusted research profits.** Simulated fills, funding, returns and comparisons remain hypothetical and limited by their inputs.
- **No autonomous ML trading.** Predictive models remain SHADOW research, not final quote authority.
- **No simultaneous BTC/ETH/SOL portfolio trading or historical market replay engine.** Those are not part of the currently merged scope.
- **No Pyth integration or added execution signing authority.** The provider and risk-authority boundaries remain as documented.

An external venue connection may also be unavailable depending on configuration, geographic restrictions, or applicable data-access terms. The project does not offer a workaround for venue restrictions.

## Updated short description

**HyperAMM is an open-source, research-focused Hyperliquid market-making platform built with Python, FastAPI, React, and TypeScript. It combines virtual AMM liquidity models, adaptive quoting, deterministic risk controls, supervisory agents, simulated accounting, strategy research, and a professional trading terminal. The platform also includes independent read-only BTC/ETH/SOL market intelligence and a way to explain differences between observed market conditions and hypothetical PAPER simulations.**

HyperAMM remains a **local research system**, not a production-mainnet trading service. Its strongest engineering distinction is that strategies, agents, and research can provide information or proposals while separate deterministic checks retain control over executable orders.

## Further reading

- [Full dated changelog](CHANGELOG.md) — all merged PRs and what they changed.
- [Roadmap](docs/ROADMAP.md) — implementation history, remaining phases, and acceptance gates.
- [Codebase guide](CODEBASE.md) — where backend/frontend features live and how the pieces connect.
- [Architecture](docs/ARCHITECTURE.md) — how information moves from market data to strategy, risk, execution, and accounting.
- [Audit 1.0](AUDIT_REPORT_1.0.md) and [Audit 2.0](AUDIT_REPORT_2.0.md) — reviewed limitations and hardening findings.



## Phase 15.5B — October 29, 2026 update

Phase 15.5A merged in PR #54. Phase 15.5B now hardens the independent public
BTC/ETH/SOL observation layer and has Linux offline acceptance: 1916 backend and
652 frontend tests pass, 47 actual Chromium workflows pass, and a short bounded
fake-SDK soak completed without owned resource leaks. One genuine venue metadata
attempt was blocked by the Cloud proxy; macOS/local/Replit and long venue soak
remain unverified. This does not grant trading readiness or complete Phase 15.
See [the new acceptance report](docs/PHASE155B_ACCEPTANCE.md).
