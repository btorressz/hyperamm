# Hyperliquid Integration

HyperAMM targets the official `hyperliquid-python-sdk` and pins the Phase 1–4 compatibility range to `>=0.24.0,<0.25`. The integration boundary is intentionally narrow so SDK payload changes do not propagate through strategy or frontend code.

## Public market data

`HyperliquidMarketDataAdapter` constructs `Info` against the main public API and subscribes to `{"type":"l2Book","coin":market}`. It also requests an initial `l2_snapshot`. The adapter normalizes SDK `levels` (`px`, `sz`, `n`) into `MarketLevel` and `OrderBookSnapshot`, tracks the exchange millisecond timestamp, and rejects older updates rather than allowing them to overwrite newer state.

If initialization/subscription fails, the service reports an unavailable/degraded LIVE state. It never invents a live price and never silently falls back to demo data. Demo mode is separately and visibly labeled `SIMULATED DEMO DATA`.

## Testnet execution

`HyperliquidTestnetExecutionAdapter` uses the SDK `Exchange` client only after all guards pass. Limit liquidity is submitted using `Exchange.order(...)` with `Alo` (add-liquidity-only/post-only) and a deterministic 16-byte `Cloid`. Cancellation uses `cancel_by_cloid`.

Signed order transmission requires all of:

```text
EXECUTION_MODE=TESTNET
ENABLE_HYPERLIQUID_TESTNET_ORDERS=true
HYPERLIQUID_PRIVATE_KEY=<testnet signing key>
```

The default is PAPER and the guard is checked before a signing client is created. No mainnet execution adapter exists. Withdrawals, transfers and bridging are not implemented.

## Security assumptions

Signing material exists only in backend environment variables. React never receives it. `.env` is ignored. The code never logs the private key. Public LIVE market data requires no wallet.

## Known limitations

Phases 5–8 now implement inventory-aware quoting, volatility/book-imbalance adaptation, Hyperliquid-native perpetual context, multi-source reference integrity, and the deterministic institutional risk firewall. Phases 9–12 supervisory agents, offline optimization, research vault accounting and the 12-page terminal are implemented / in review. Mainnet execution remains out of scope. Local fixture acceptance does not establish real provider or signed TESTNET acceptance; see [Audit 1.0](../AUDIT_REPORT_1.0.md) for current authority/provider/operational limitations.

## Phase 4.1 venue reconciliation

Implementation was checked against installed SDK **0.24.0** and current official
[`examples/basic_ws.py`](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/2fdb18f9517675ea03695a0962bd19eece9c83f0/examples/basic_ws.py)
and `Info` source at that revision. Supported calls used are
`subscribe(subscription, callback)`, `open_orders(address)`,
`query_order_by_oid(address, oid)`, and `query_order_by_cloid(address, cloid)`.

A separate guarded `Info` client subscribes to `orderUpdates` and `userFills`.
SDK-thread callbacks only wake an asyncio event; they never mutate order state.
The runtime queries the authoritative open-order set under the execution lock
on those notifications, every five seconds, and before quote reconciliation.
This deliberate event-triggered read avoids double-counting fill snapshots and
out-of-order events; latency includes the authoritative HTTP read.

For tracked orders present in the open set, remaining `sz` determines
`filled_size` and OPEN/PARTIALLY_FILLED status. Missing tracked orders require
an order-status lookup; `filled`, cancellation/expiry and rejection states map
to local FILLED, CANCELLED and REJECTED. Venue IDs, fill quantities and timestamps
are updated idempotently. Acknowledged cancellations receive a follow-up status
check to capture fills that preceded cancellation. Partial orders remain active
and reconciliation compares desired size with their remaining quantity.
Unrelated account orders are neither adopted nor cancelled.

An absent order without terminal evidence becomes UNKNOWN, remains cancellable,
and blocks new quoting. Failed/malformed submissions retain uncertain exposure
by client ID; cancellation is attempted rather than assuming rejection. Cancel
responses must acknowledge success or a status query must prove a terminal
order. All cancellation targets are attempted even if one fails. An unresolved
failure latches runtime execution HALTED, and cancellation failure is surfaced.

Only `https://api.hyperliquid-testnet.xyz` is accepted by the signing adapter.
PAPER/DEMO remain defaults. Disabled TESTNET never constructs a signing client.
Query/event and exchange clients can be injected for deterministic offline tests;
normal tests need no wallet, credentials, or live Hyperliquid service.

Historical Phase 4.1 acceptance: live signed orders, real WebSocket delivery/reconnect timing, venue rate limits,
and real fill/cancel races were **not exercised**. Later fake-SDK thread/reconnect
regressions remain local fixture evidence, not live provider acceptance.
Periodic authoritative polling continues when WebSocket notifications are absent.
Ownership IDs are still in memory: discovering previous-process strategy orders
and durable restart recovery are outside this pass. This is a tested Phase 1–4
foundation, not a claim of production/mainnet readiness.


## Phase 7 perp context

The public adapter reuses its existing official SDK `Info` client and WebSocket manager. Alongside `l2Book`, it subscribes to:

```python
Info.subscribe({"type": "activeAssetCtx", "coin": market}, callback)
```

and bootstraps current context with:

```python
Info.meta_and_asset_ctxs()
```

The normalized fields used are `funding`, `openInterest`, `oraclePx`, `markPx`, optional `midPx`, and optional `premium`. Market mapping uses the matching `meta["universe"][i]["name"]`; it does not silently assume the configured coin is at a fixed index.

TESTNET `Info.user_state(address)` is parsed once per refresh into both the authoritative Phase 5 signed position and Phase 7 account/perp observability. Phase 7 does not call leverage or isolated-margin mutation APIs.

Live signed TESTNET behavior and real public `activeAssetCtx` delivery are not required by deterministic unit tests and must not be represented as exercised unless explicitly validated against Hyperliquid.


## Phase 8 native evidence reuse

Phase 8 does not create another Hyperliquid market-data client. It reuses the normalized Phase 7/market state:

```text
oraclePx -> native oracle evidence
markPx   -> perpetual mark evidence
L2 mid   -> execution-venue evidence
```

The TESTNET user-state refresh also retains currently available authoritative account-value context for Phase 8 session equity/drawdown observability. Missing values remain unavailable; Phase 8 does not fabricate them or call leverage/margin mutation methods.

External reference networking is independent of the signed execution adapter. LIVE market/reference data can therefore run with PAPER execution and no trading wallet. Final TESTNET order transmission remains guarded by the existing explicit testnet opt-in and now additionally requires a current Phase 8 FinalQuoteAuthorization.

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
