# Phase 8 Reference Integrity

Phase 8 adds a deterministic evidence layer between strategy quotes and execution. Provider networking is isolated in `app/references/`; the risk firewall consumes normalized `PriceEvidence` only.

## Provider roles

| Provider | Role | Authority |
|---|---|---|
| RedStone Live | PRIMARY ORACLE | Primary external oracle evidence |
| Hyperliquid `oraclePx` | NATIVE ORACLE | Native venue oracle evidence |
| Kraken WebSocket v2 ticker | VENUE REFERENCE | Independent live executable-market reference |
| CoinGecko simple price | AGGREGATOR REFERENCE | Tertiary sanity/fallback evidence |
| Hyperliquid L2 midpoint | EXECUTION VENUE | Venue dislocation evidence |
| Hyperliquid mark | PERP MARK | Native perpetual mark evidence |

Kraken and CoinGecko are not labeled or treated as oracles.

## PriceEvidence

Every source normalizes into the same contract:

```text
market
provider
source_type
price
observed_at
source_timestamp
age_ms
healthy
stale
status
source_id
simulated
version
error
```

Provider status is one of `HEALTHY`, `DEGRADED`, `STALE`, `ERROR`, or `DISABLED`.

Raw provider payloads terminate inside provider adapters.

## RedStone Live

RedStone is implemented server-side in Python with the direct `websockets` dependency.

Authentication is an `x-api-key` HTTP upgrade header. The key remains in backend settings and is never returned by REST or terminal WebSocket state.

The subscription payload is:

```json
{
  "feedId": "<configured feed>",
  "type": "price",
  "dataServiceId": "redstone-primary-prod"
}
```

The adapter preserves the configured feed ID, data-service ID, provider timestamp, local observed-at timestamp, normalized price, source/package ID, health, freshness and version.

The Live WebSocket URL is deliberately configurable. The repository does not embed an unverified or stale service URL; operators set `REDSTONE_LIVE_WS_URL` from the current RedStone Live documentation/account configuration.

The provider rejects wrong feeds/services, missing timestamps, non-positive/non-finite prices, future timestamps beyond tolerance, and replayed/older timestamps. Newer economically identical observations refresh freshness without unnecessary economic-version churn.

Disconnects and long-lived connection closures are normal lifecycle events. The provider reconnects and resubscribes with bounded exponential backoff plus jitter. Authentication errors map to `ERROR`; rate-limit/transient connectivity maps to degraded state and retries.

## Kraken WebSocket v2

Kraken uses the public v2 endpoint and the `ticker` channel:

```json
{
  "method": "subscribe",
  "params": {
    "channel": "ticker",
    "symbol": ["<configured symbol>"],
    "event_trigger": "bbo",
    "snapshot": true
  }
}
```

Each update validates:

```text
bid > 0
ask > 0
bid < ask
symbol matches configured mapping
timestamp is valid
```

The normalized exchange reference is:

```text
kraken_mid = (bid + ask) / 2
```

Kraken has its own freshness threshold, health state and reconnect/resubscribe lifecycle.

## CoinGecko

CoinGecko uses backend `httpx` and the simple-price endpoint. Requests ask for USD price and `last_updated_at`.

Demo/public and Pro authentication headers are selected from the configured API base URL. The API key never enters frontend-visible configuration.

Provider `last_updated_at`, not local HTTP completion time, is the source freshness timestamp.

CoinGecko is tertiary evidence only. It can support sanity checks, outlier comparison and recovery confirmation, but can never by itself authorize NORMAL quoting.

## Hyperliquid-native evidence

Phase 8 reuses existing normalized Phase 7/market state:

```text
oraclePx -> NATIVE_ORACLE
markPx   -> PERP_MARK
L2 mid   -> EXECUTION_VENUE
```

These sources do not create another Hyperliquid connection lifecycle.

## Consensus and quorum

Core independent reference roles are:

```text
RedStone
Hyperliquid native oracle
Kraken
```

The default deterministic consensus is the median of eligible healthy core prices after deterministic outlier classification.

Normal verified operation requires the external oracle/live-market structure represented by RedStone + Kraken, with Hyperliquid native oracle used as another core cross-check when healthy.

Documented degraded fallbacks include:

```text
HL native oracle + Kraken
    -> DEGRADED

RedStone + HL native oracle with Kraken unavailable
    -> DEGRADED
```

Fewer than two eligible core sources is `INSUFFICIENT`. CoinGecko does not satisfy the independent live-market requirement.

## Outliers

When at least three trusted reference sources are healthy, the median is used as a deterministic outlier center. A source whose absolute deviation exceeds `source_outlier_bps` is excluded from core consensus eligibility.

The primary source is not automatically assumed correct.

## Signed deviations

All deviations preserve sign:

```text
deviation_bps =
    (source_price - reference_price)
    / reference_price
    * 10000
```

The snapshot exposes signed and magnitude views for:

```text
HL mid        <-> consensus
HL mark       <-> consensus
HL oracle     <-> consensus
RedStone      <-> consensus
Kraken        <-> consensus
CoinGecko     <-> consensus
RedStone      <-> Kraken
RedStone      <-> HL oracle
RedStone      <-> CoinGecko
Kraken        <-> HL oracle
Kraken        <-> CoinGecko
HL mark       <-> HL oracle
HL mid        <-> HL mark
HL mid        <-> HL oracle
```

## Version semantics

Provider versions advance on materially changed economic or health state. Replayed/older observations do not advance. Newer observations below the configured material movement threshold can refresh freshness without forcing quote churn.

`ReferenceSnapshot.version` changes when the normalized reference state materially changes. Final execution authority binds to that version.

## DEMO and LIVE PAPER

DEMO creates deterministic simulated RedStone, Kraken and CoinGecko evidence and marks each `simulated=true`.

LIVE market/reference data can run with PAPER execution. No trading wallet is required for public references or PAPER execution.
