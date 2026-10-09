# HyperAMM Architecture

HyperAMM is a virtual-liquidity compiler. It does **not** create or settle against an on-chain constant-product pool. AMM mathematics produces a deterministic liquidity curve; that curve is sampled, normalized and compiled into discrete CLOB quotes.

```text
Hyperliquid public API / explicit demo feed
                 ↓
       market-data adapter
                 ↓
       normalized market state
      BBO · L2 · freshness · mode
                 ↓
          fair-value engine
        fair = (bid + ask) / 2
                 ↓
          virtual AMM core
              x · y = k
                 ↓
         liquidity policy
  constant-product / concentrated
                 ↓
       liquidity discretizer
    price ticks · size precision
                 ↓
        CLOB quote compiler
          bids / asks / size
                 ↓
      deterministic risk checks
 freshness · size · notional · distance
                 ↓
        quote reconciliation
     KEEP/CREATE/REPLACE/CANCEL
                 ↓
         execution adapter
     PAPER (default) / TESTNET
```

## Boundaries

`market_data/` owns Hyperliquid payload parsing and stale/monotonic state. `amm/` contains pure deterministic financial math. `strategy/` owns fair value, configuration and quote generation. `risk/` is an authority boundary that can stop quotes regardless of strategy intent. `execution/` is the only layer allowed to transmit an order, which prevents AMM math from gaining signing authority.

The React terminal consumes Pydantic-normalized REST/WebSocket state only. It never receives private keys, seed phrases or raw SDK objects.

## Expanded Phase 9 supervision and ML shadow boundary

```text
Strategy → Regime/Toxic Flow/Execution Quality v2 + Liquidity Quality + Perp Crowding
→ AgentSupervisor (MAX spread / MIN side sizes / MIN level cap)
→ bounded conservative transformation → Phase 8 RiskFirewall
→ FinalQuoteAuthorization → Execution

Offline normalized evidence → versioned feature dataset → optional logistic training
→ validated JSON artifact + model/dataset provenance → ML SHADOW predictions
→ API / terminal / isolated simulation evaluation only
```

Agents recommend. Phase 8 decides. FinalQuoteAuthorization controls execution.
No execution, risk, kill, accounting, position or FinalQuoteAuthorization authority
is delegated to an agent or machine-learning model. The existing Phase 5/6/7
strategy mathematics and Phase 8 thresholds remain authoritative.

`AgentEvidenceSnapshot` is frozen, finite and versioned. Book summaries contain
base-unit depth, BBO/span bps, concentration and accepted midpoint instability.
Perp changes require bounded retained observations with distinct source timestamps;
a single OI value never implies OI change. PAPER lifecycle metrics use recorded
order/fill timestamps; unavailable TESTNET fill/venue latency stays null.

Predictive mode accepts DISABLED or SHADOW only. The fixed feature ordering is
`passive-adverse-v1`, shared by training and inference. Optional sklearn training
is offline; live inference accepts bounded inert JSON logistic coefficients,
requires their SHA-256 identity/schema to validate and performs fixed-cost
inference. Default SHADOW has no artifact and reports UNAVAILABLE. ML outputs
and model identity are observational: they are excluded from material supervisor
fingerprints and FinalQuoteAuthorization, avoiding quote-authorization churn.
Simulation research identity includes the supplied observational model hash.

`AgentSystemSnapshot` publishes a deep copy of one complete cycle. GET endpoints
observe this publication and never invoke model loading, training, inference or
network work. Agent events remain capped at 250 and filterable. The trusted local
artifact path is setup configuration excluded from public payloads. No executable
serialized model format is accepted. See [agent contracts](../backend/app/agents/README.md)
for formulas, capacities, feature units and dataset provenance.

## A1-027 identity and provenance scopes

HyperAMM deliberately uses several different identities. They are not
interchangeable and none should be described as a complete evidence archive unless
its contract explicitly says so:

| Identity | What it means | What it does **not** mean |
|---|---|---|
| Market/perp/reference/agent/risk/accounting versions | Monotonic identity for declared material state/decision changes | Every raw provider packet, timestamp refresh or full historical evidence stream |
| FinalQuoteAuthorization fingerprints | Canonical hashes over the fields bound by the authorization contract | A complete archive of all upstream wire messages or external source revisions |
| Terminal `process_id` / `session_id` / `sequence` | Observation-process, context-session and emitted-observation ordering | Exchange order identity, economic-event identity or proof that every upstream packet was archived |
| Simulation dataset/run fingerprints | Deterministic semantic dataset/config/result identity for the declared research contract | Automatic Git commit, dependency lock, compiler or machine provenance |
| Accounting ledger fingerprint chain | Integrity linkage inside the active research ledger/session | Durable custody, database persistence or cross-restart reconstruction |

Unchanged material decisions may legitimately retain a semantic version while
display/receive timestamps advance. Conversely, a new terminal observation
sequence does not require a new trading-authority version. Do not advance
authority versions solely to capture UI timestamps or observability refreshes.

If future research requires reproducible full-evidence provenance, add an immutable
research record that explicitly captures the desired source revisions, inputs and
environment metadata. Expanding the material fields of an existing authority hash
is a compatibility/authority change and requires deliberate review rather than a
documentation-only adjustment.

## Runtime

`HyperAmmRuntime` composes services without merging their responsibilities. A strategy refresh reads one normalized snapshot, computes fair value, recenters virtual reserves while preserving `k`, builds quotes, applies risk validation, and reconciles against currently resting strategy orders. PAPER fills are deterministic touch/cross simulations and are explicitly labeled `SIMULATED PAPER FILL`.

## Phase 4.1 execution safety

The sizing path is now explicitly:

```text
fair-value reserve state → constant-product curve → incremental reserve movement
→ AMM-derived sizing → optional concentration weighting → per-side budget scaling
→ CLOB tick/size normalization → risk → serialized execution
```

Strategy intent (`running`) is separate from `quote_health`:

| State | Meaning |
|---|---|
| NO_QUOTES | Stopped; a valid desired ladder may be displayed as a preview only |
| HEALTHY | Enabled, validated, reconciled strategy quotes |
| DEGRADED | Bad feed, generation/risk failure, or venue reconciliation failure; desired ladder and fair value cleared and strategy orders cancelled |
| HALTED | Kill latch active, including cancellation that could not be confirmed |

Missing/non-finite/non-positive/crossed BBO, invalid mid, stale timestamps and any
non-CONNECTED feed state invalidate quoting. Invalid LIVE payloads explicitly
publish degraded state. Freshness uses the exchange timestamp, not just receipt
time. A strategy refresh and the market listener both fail closed; while enabled,
a safety check runs at most one second apart between quote cycles even when the
configured quote interval is long. Venue/network work can delay a check while
it holds the execution lock. HTTP SDK calls have a ten-second timeout.

Transient degradation preserves enabled intent and can recover on the next
valid quote cycle, provided the kill latch is inactive and execution/risk checks
pass. Manual kill disables intent. Resume clears the latch only after successful
cancellation and **does not start the strategy**. A cancellation failure clears
the desired ladder, reports `cancellation unconfirmed`, and latches HALTED;
it does not claim the venue has no orders. Explicit operator recovery is required.

One shared `asyncio.Lock` serializes generation/reconciliation, order creates,
replacements and cancellations, cancel-all, market-driven paper mutations,
venue updates, kill completion and execution-adapter/configuration publication. A separate lifecycle lock serializes
transport transitions (see A1-019 below).
Kill revokes authority before waiting for the lock, then cancels after in-flight
work finishes. Authority and fresh market state are checked before each create,
again inside the TESTNET adapter after SDK setup, and after reconciliation.
Signed worker-thread calls finish before a cancelled waiter releases the lock.
Consequently successful kill completion is a cancellation barrier: an older
reconciliation cannot subsequently leave a newly transmitted order active.

The terminal displays quote health and the existing strategy error banner.
TESTNET order history exposes venue status and fill quantities; the terminal
payload also includes the last venue reconciliation timestamp and error.
PAPER retains its existing `SIMULATED PAPER FILL` labeling and remains the default.


## Phase 5 inventory-aware strategy layer

The accepted Phase 4.1 AMM path remains intact. Phase 5 is a strategy transform:

```text
normalized market state
        ↓
fair value
        ↓
virtual x*y=k AMM
        ↓
reserve-delta liquidity
        ↓
optional concentration
        ↓
neutral QuoteLevel ladder
        ↓
normalized InventoryState
        ↓
InventoryPolicy
  reservation-price shift
  side-size multipliers
  hard-limit suppression
        ↓
deterministic risk
        ↓
KEEP / CREATE / REPLACE / CANCEL
        ↓
PAPER / guarded TESTNET
```

PAPER position is the signed sum of actual simulated fills: BID fills add base and ASK fills subtract base. Resting, cancelled, rejected, and unknown orders do not create PAPER inventory.

TESTNET position comes from the official Hyperliquid SDK account-state path (`Info.user_state(account_address)`) and normalizes the configured market's signed `assetPositions[].position.szi`. Position refresh occurs before TESTNET quote generation and during venue reconciliation. Missing/stale state, malformed state, reconciliation errors, or UNKNOWN economic exposure invalidate inventory-aware execution instead of assuming zero.

Generated decisions bind to an inventory version. Final transmission authority verifies that the current version still matches the version used to generate the ladder. Fill/venue events wake the existing strategy loop; they do not introduce a second execution lock or reconciliation system.


## Phase 6 market-adaptation layer

Phase 6 adds one deterministic transform after Phase 5 and before risk:

```text
normalized market state
        ↓
fair value
        ↓
virtual x*y=k AMM
        ↓
reserve-delta sizing
        ↓
optional concentration
        ↓
Phase 5 InventoryPolicy
  reservation center
  inventory size skew
  hard-limit suppression
        ↓
Phase 6 MarketAdaptationPolicy
  rolling mid-price volatility
  top-N L2 imbalance
  widening-only spread multiplier
  bounded variable-liquidity reduction
        ↓
deterministic risk on FINAL prices/sizes/distance/notional
        ↓
KEEP / CREATE / REPLACE / CANCEL
        ↓
PAPER / guarded TESTNET
```

`MarketPriceHistory` is bounded in memory and accepts only fresh normalized snapshots with a positive finite mid price and unique sequence/timestamp identity. Replays do not inflate volatility samples. History is cleared when market/feed mode changes.

Phase 6 uses the Phase 5 reservation price as its strategy center without overwriting either fair value or reservation price. The existing Phase 5 hard-limit side suppression happens first; because Phase 6 only transforms the surviving quote list, it cannot re-enable a forbidden side.

The runtime binds final quotes to both the Phase 5 inventory version and the Phase 6 market-history version. Final execution authority refreshes the normalized market snapshot and rejects transmission if either material dependency changed after quote generation. The existing shared execution lock remains the serialization boundary.

Startup volatility warmup is not a failure: if fewer than the configured minimum observations exist, realized volatility is `None`, the regime is `WARMING_UP`, and all Phase 6 spread/size multipliers are neutral. Invalid book state or invalid/non-finite Phase 6 math after that point follows the existing invalidation/cancel semantics.


## Phase 7 perpetual strategy-reference layer

Phase 7 inserts one deterministic context decision before AMM construction:

```text
normalized market snapshot
        ↓
raw market fair value
        ↓
normalized PerpMarketContext
        ↓
PerpContextPolicy
        ↓
bounded strategy reference
        ↓
virtual AMM recenter
        ↓
reserve-delta sizing / concentration
        ↓
Phase 5 inventory
        ↓
Phase 6 market adaptation
        ↓
existing deterministic risk/reconciliation/execution
```

The existing public Hyperliquid `Info` client owns both `l2Book` and `activeAssetCtx` subscriptions. `meta_and_asset_ctxs()` is used for bootstrap and maps by universe name. No second public WebSocket lifecycle is introduced.

Final execution authority binds the generated ladder to inventory, market/adaptation, and perp-context versions. Stale or materially changed perp context cannot transmit an old decision. Phase 7 does not add Phase 8 oracle-firewall authority.


## Phase 8 reference integrity and final risk authority

Phase 8 is intentionally downstream of all strategy transforms:

```text
Hyperliquid normalized market/perp state
        ↓
Phase 7 strategy reference
        ↓
AMM / reserve-delta sizing / concentration
        ↓
Phase 5 inventory authority
        ↓
Phase 6 market adaptation
        ↓
desired strategy quotes
        ↓
normalized reference evidence
        ├── RedStone primary oracle
        ├── Hyperliquid native oracle
        ├── Kraken exchange BBO midpoint
        ├── CoinGecko aggregate reference
        ├── Hyperliquid L2 midpoint
        └── Hyperliquid mark
        ↓
ReferenceConsensus + signed deviation matrix
        ↓
projected exposure / PnL / liquidation evidence
        ↓
RiskFirewall
 NORMAL / WIDEN / REDUCE / HALT
        ↓
authorized quote ladder
        ↓
existing validate_quotes()
        ↓
FinalQuoteAuthorization
        ↓
existing reconciliation + execution adapters
```

Provider networking remains in `references/`. The firewall does not know HTTP/WebSocket payload formats. Raw external payloads are normalized before they can influence risk authority.

Phase 8 uses the existing execution lock; no second lock hierarchy is introduced. Provider tasks only update their own normalized evidence and wake the existing strategy loop on material changes. CREATE/REPLACE actions still pass through `OrderManager` and the same execution adapters.

Automatic risk HALT does not set the manual kill latch. It produces an empty authorized ladder and uses existing reconciliation to cancel resting strategy orders. Recovery requires deterministic hysteresis and consecutive healthy confirmations. Manual kill still disables strategy intent and cannot be cleared by automatic firewall recovery.

Immediately before transmission, authority rechecks market/adaptation, inventory, perp, reference and risk versions plus the current authorized quote fingerprint. Stale authorization is rejected before the execution adapter is allowed to submit an order.

## A1-019 serialized configuration lifecycle

`HyperAmmRuntime.update_config()` holds a dedicated `lifecycle_lock` for the
entire transition. The deterministic order is lifecycle lock, then execution
lock; callbacks, quote refresh and emergency controls acquire only execution.
Runtime start/stop share lifecycle serialization. Transport stop/start awaits do
not hold the execution lock, so callback drain and cancellation can proceed.

The configuration sequence is:

```text
invalidate quote authority / cancel strategy orders
→ capture exact old market/reference identities
→ stage replacement market, perp and reference services and session objects
→ stop captured old transports
→ start staged replacement transports
→ publish config/service graph and reset dependent evidence under execution lock
→ wake ordinary strategy recovery through normal authority checks
```

Replacement listeners are registered before startup and bind their source market
identity. They ignore callbacks while transitioning/failed and from retired
markets. Reference wakeups are detached during transition and retirement; only
the published replacement can wake recovery. Market/feed or PAPER↔TESTNET context
changes create fresh PAPER, telemetry/supervisor and research accounting sessions.

Publication/reset has no awaits; it is atomic relative to this asyncio runtime's
execution-lock users, not a distributed transport transaction. `start()` completion
means transport startup was scheduled/completed by its service, not proof of fresh
LIVE data or external provider health. Strategy intent may stay enabled, but
refresh, periodic authority checks, venue refresh and CREATE/REPLACE are gated
while the lifecycle is incomplete. Success only wakes the ordinary quote loop;
market/perp/reference evidence, Phase 8 final authorization and Phase 11 accounting
must independently pass before reconciliation can transmit.

Constructor failure, old-service stop failure, either replacement start failure,
partial startup and request cancellation all latch `FAILED`. The old published
config/references remain visible but are explicitly unavailable for quoting;
desired/authorized ladders stay invalidated and strategy health/error reports the
failure. Every constructed staged transport gets a stop attempt, including one
that started before its peer failed. Cleanup failures are reported and ownership
is retained for shutdown retry. No automatic rollback is claimed: uncertain old
shutdown cannot support safe recovery. Further config/start requests require a
runtime restart; resume clears only the manual kill latch and never the lifecycle
failure. Cancellation, strategy stop and manual kill remain available. The initial
runtime service startup also fails closed if a transport start raises.

Current implementation is PAPER/guarded TESTNET research, not production readiness.
See [Audit 1.0](../AUDIT_REPORT_1.0.md) for outstanding authority, lineage and
provider limitations. Historical phase acceptance does not close those findings.

## Optional ephemeral infrastructure

[Redis infrastructure](REDIS.md) adds terminal distribution and WS/research
resource coordination alongside the existing authoritative engine. The
[pre-implementation inventory](REDIS_DESIGN.md) distinguishes AUTHORITATIVE,
DURABLE-FUTURE, EPHEMERAL-DISTRIBUTABLE and LOCAL-CACHE state. Redis never supplies
execution locks, market/risk evidence, decision-critical agent telemetry,
FinalQuoteAuthorization, accounting/positions, canonical config or the kill latch.
Future PostgreSQL persistence is explicitly not implemented. Local deployment
and one engine/one worker remain required.

## Phase 8 CoinGecko hardening and optional Yahoo observation — 2026-10-08

CoinGecko enabled Demo and Pro reference modes require `COINGECKO_API_KEY`. Only the exact TLS hosts `https://api.coingecko.com/api/v3` (Demo / `x-cg-demo-api-key`) and `https://pro-api.coingecko.com/api/v3` (Pro / `x-cg-pro-api-key`) receive credentials. Missing configuration or untrusted hosts become provider ERROR without a network request. Disabled mode needs no credentials. HTTP 400/401/403 are ERROR; 429, 5xx, network and decoding errors are DEGRADED with bounded retries. CoinGecko remains tertiary and cannot satisfy core quorum.

Optional Yahoo personal research observation: install `pip install -e '.[yahoo]'`; defaults are `YFINANCE_REFERENCE_ENABLED=false`, `YFINANCE_SYMBOL=ETH-USD`, `YFINANCE_STALE_AFTER_SECONDS=30`. Mapping is explicit: ETH→ETH-USD, BTC→BTC-USD; other startup markets are unavailable, not guessed. The decoded yfinance `AsyncWebSocket` fields `id`, `price`, and Unix-millisecond `time` are validated against a source-time freshness window. Replays, wrong symbols, invalid values and missing/old/future timestamps are rejected. A bounded reconnect loop cancels listener/watchdog tasks and closes sockets. Missing optional dependency is observational ERROR only.

The separately polled `GET /api/v1/references/observations` endpoint and Risk-page card expose observational health, source age, prices and available signed comparison bps. Unavailable comparisons remain null. **Yahoo is excluded from CORE, ALL, the material reference snapshot, economic version/fingerprint, quorum, outlier decisions, risk, agents, authorization, accounting and execution.** It cannot replace RedStone, Kraken or Hyperliquid evidence or authorize trades. The Phase 12 streaming contract remains unchanged.

**Licensing and acceptance:** Yahoo data is for permitted local personal/research observation only. Do not redistribute it publicly or use it for commercial trading without appropriate rights. Live CoinGecko and Yahoo connections, real schemas and reconnect acceptance remain pending. Phase 8.3.1 fixture and local command results are recorded in the roadmap; they do not establish live-provider acceptance. Historical Audit 2.0 issues A2-001–A2-005 are unchanged. No Actions files, Docker, PostgreSQL, signing changes or new trading authority. No additional oracle providers were introduced; unsupported oracle integrations remain prohibited.
