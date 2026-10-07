# Market Data Domain

The `market_data` package owns normalized market observations and perpetual context used by strategy, risk, agents, accounting marks and terminal observability.

It is the first evidence layer in the live pipeline.

## Files

| File | Responsibility |
|---|---|
| `models.py` | Normalized market/book/level contracts, data mode, timestamps, freshness and sequence metadata. |
| `hyperliquid.py` | Hyperliquid public market-data adapter and normalization logic. |
| `mock.py` | Deterministic DEMO data source used for local development/tests; it remains explicitly simulated. |
| `service.py` | Starts/stops the selected adapter, accepts ordered updates, exposes the current snapshot and notifies runtime listeners. |
| `history.py` | Bounded unique normalized midpoint history used by Phase 6 volatility and agent research signals. |
| `perp_context.py` | Normalizes mark, oracle, funding, open interest and account-position context; includes deterministic DEMO context. |
| `__init__.py` | Package marker. |

## Connections

```text
Hyperliquid / DEMO
      ↓
MarketDataService
      ├──→ Strategy fair value + AMM
      ├──→ MarketPriceHistory → Phase 6 + agents
      ├──→ PerpContextService → Phase 7
      ├──→ ReferenceService (HL mid/mark/oracle evidence)
      ├──→ Risk freshness/version checks
      └──→ Terminal / API observability
```

The runtime installs listeners so new market/perpetual evidence wakes strategy recomputation. Invalid/stale evidence is handled fail-closed by the runtime rather than silently substituting DEMO values into LIVE mode.

## Ordering and freshness

Market history accepts unique monotonic observations and rejects stale/invalid/non-positive prices. Exchange sequence/timestamps remain distinct from local observation/terminal timestamps.

For LIVE L2, `latest_valid_update` is the exchange timestamp; `book.timestamp`
is local receive time and `book.sequence` is a monotonic HyperAMM material
identity. The service retains the source ordering watermark across unavailable
states. Full normalized bids/asks (prices, sizes and order counts) and BBO bind
material identity. Economically identical replays, including alternate Decimal
formatting, retain identity. Changed books advance it even within one exchange
millisecond. History keeps duplicate-time price samples deduplicated while
advancing its authority version for changed material. The existing Phase 6
decision, Phase 8 authorization and Phase 9 evidence all bind that version;
the final transmission guard observes the current book before checking it.

## Official SDK WebSocket lifecycle (Audit 1.0 A1-003 / A1-004)

The supported SDK 0.24.0 WebsocketManager does not automatically reconnect.
HyperAMM monitors its socket, manager and ping sender plus L2/context delivery.
Failures publish DEGRADED, unsubscribe when possible, call
`Info.disconnect_websocket()`, and join/verify both SDK threads before dropping
ownership. RECONNECTING uses interruptible exponential backoff from one to ten
seconds. Each attempt owns one new Info, subscribes l2Book once and
activeAssetCtx once when used, bootstraps perp context through
`Info.meta_and_asset_ctxs()`, and requires a fresh valid `Info.l2_snapshot()`
before CONNECTED. Queued stream updates cannot cross that recovery barrier;
callbacks from old clients cannot reach a new session.

Ownership begins before SDK initialization because its constructor starts the
socket before fetching metadata. Cancellation drains in-flight SDK calls before
shutdown. Stop and reconfiguration disconnect the owned socket. A bounded
shutdown timeout retains the old Info and prevents replacement while cleanup
is unresolved; it never reports recovery or starts another socket. Deterministic
Phase 1/6/7/8 tests use SDK-shaped HTTP fixtures and the actual SDK subscription
methods, WebsocketManager and threads with a fake socket. No signed trades are
needed for lifecycle acceptance.

## Safety boundary

This package supplies normalized evidence only. It does not decide position sizing, risk posture or whether an order may be transmitted.
