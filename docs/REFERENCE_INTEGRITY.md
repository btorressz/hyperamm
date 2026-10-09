# Phase 8 Reference Integrity

Phase 8 adds a deterministic evidence layer between strategy quotes and execution. Provider networking is isolated in `app/references/`; the risk firewall consumes normalized `PriceEvidence` only.

## Provider roles

| Provider | Role | Authority |
|---|---|---|
| RedStone (Live / public HTTP) | PRIMARY ORACLE | One external oracle identity, with primary and fallback transports |
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
transport
transport_quality
simulated
version
error
```

Provider status is one of `HEALTHY`, `DEGRADED`, `STALE`, `ERROR`, or `DISABLED`.

Raw provider payloads terminate inside provider adapters.

## RedStone Live

RedStone is implemented server-side in Python with the direct `websockets>=15,<16` dependency.

Authentication is an `x-api-key` HTTP upgrade header. The key remains in backend settings and is never returned by REST or terminal WebSocket state. The supported websockets version uses `additional_headers` for custom handshake headers.

Before opening a Live connection, the Live transport requires all of:

```text
API key
WebSocket URL
feed ID
data service ID
```

Incomplete Live configuration transitions only the Live transport to `ERROR` and does not start its reconnect loop. A configured public HTTP fallback can still start and supply effective RedStone evidence without a Live API key or WebSocket URL.

The documented RedStone Live subscription envelope is:

```json
{
  "op": "subscribe",
  "items": [
    {
      "feedId": "<configured feed>",
      "type": "price",
      "dataServiceId": "redstone-primary-prod"
    }
  ]
}
```

The provider builds this contract through `RedStoneProvider.subscription()` and sends the same deterministic envelope after every reconnect.

The lightweight incoming `price` frame is a different wire shape:

```json
{
  "type": "price",
  "dataServiceId": "redstone-primary-prod",
  "dataPackageId": "ETH",
  "timestamp": 1712345678000,
  "value": 2543.12
}
```

For price messages:

```text
dataPackageId -> configured feed identity
timestamp     -> provider/source timestamp
value         -> Decimal normalized price
```

Incoming `feedId` is not required or used for lightweight price identity. `PriceEvidence.source_id` is the stable configured provider/feed identity `<dataServiceId>:<feedId>`, for example `redstone-primary-prod:ETH`.

The price normalizer requires:

```text
type == price
dataServiceId == configured data service
dataPackageId == configured feed
timestamp present and valid
value present, finite and positive
```

It rejects malformed JSON, non-object messages, wrong/missing message types, wrong service/feed IDs, invalid or implausibly future timestamps, replayed/older timestamps, and zero/negative/NaN/Infinity prices.

RedStone error frames are handled separately from price normalization. The documented minimum error shape is:

```json
{
  "type": "error",
  "code": "TOPIC_LIMIT_EXCEEDED",
  "message": "Subscribe rejected: exceeds the 50-topic limit for this connection",
  "limit": 50
}
```

`TOPIC_LIMIT_EXCEEDED` is treated as an `ERROR` for this one-topic provider because the requested subscription was rejected and local/operator action is required. Unknown/temporary provider error frames are `DEGRADED` unless their code/message clearly indicates invalid subscription/feed configuration. Malformed price frames are also `DEGRADED`; a later valid price can recover provider health.

Handshake failures are classified separately: authentication/authorization failures become `ERROR`; rate/connection-limit failures are `DEGRADED` and retried. Error text is sanitized so API keys and authentication-header values are never placed in `PriceEvidence.error`.

The provider uses the normal RedStone connection lifecycle:

```text
CONNECT
  ↓
x-api-key handshake authentication
  ↓
send { op: subscribe, items: [...] }
  ↓
receive price/error frames
  ↓
normalize PriceEvidence
```

No subscription-acknowledgement frame is documented by the current Live API, so HyperAMM does not invent or require one.

RedStone documents WebSocket protocol ping frames after 120 seconds of inactivity; the standards-compliant websockets client handles pong responses automatically. RedStone also documents provider-side connection recycling, including forced closes after eight hours. Normal connection closes therefore transition to `DEGRADED`, use bounded exponential backoff with jitter, reconnect, and re-send the same subscription contract.

The Live WebSocket URL remains configurable. The repository does not embed an unverified service URL; operators set `REDSTONE_LIVE_WS_URL` from the current RedStone Live documentation/account configuration.

Freshness is based on the provider timestamp. A valid newer economically identical tick refreshes source freshness without incrementing the economic price version. Incoming timestamps less than or equal to the last accepted timestamp do not become new economic state.

## Phase 8.2 — RedStone public HTTP fallback

```text
REDSTONE — PRIMARY EXTERNAL ORACLE (one provider, one consensus vote)
    ├── Live WebSocket — PRIMARY transport, x-api-key, 5-second stale threshold
    └── Public HTTP cache — FALLBACK transport, no key, 30-second stale threshold
```

The official [HTTP API documentation](https://github.com/redstone-finance/redstone-api/blob/main/docs/HTTP_API.md), [cache proxy](https://github.com/redstone-finance/redstone-api/blob/main/src/proxies/cache-proxy.ts), and [types](https://github.com/redstone-finance/redstone-api/blob/main/src/types.ts) were inspected on 2026-10-05. They document the configurable default endpoint `https://api.redstone.finance/prices` and the request:

```text
GET /prices?symbol=ETH&provider=redstone&limit=1
```

The response is a non-empty array of price objects with `value` and provider `timestamp` (Unix milliseconds); `symbol`, when supplied, must equal the configured mapping. HyperAMM selects the latest timestamp, normalizes finite positive prices into `Decimal` (including decimal JSON numbers without a float round-trip), and records local receipt time separately. It does not require legacy `signature`, `providerPublicKey`, `permawebTx`, `source`, or `provider` fields, and does not claim signature verification for this HTTP transport.

The server-side Python/httpx transport sends no `x-api-key` or `Authorization` header. It reuses one `AsyncClient`, cancels its polling task and closes owned connections on shutdown. Normal polling defaults to **10 seconds**, with configuration constrained to at least **5 seconds**. Request/payload failures use bounded backoff up to 300 seconds; a valid but stale cache record keeps the ordinary polling schedule. HTTP 400/403 and other non-429 client errors are `ERROR`; 429, server errors, timeouts, connection errors and malformed payloads are `DEGRADED`. Later successful responses can recover all of these states. Future timestamps and regressed/conflicting records are rejected. A repeated still-fresh cache record can restore health after a request failure without resetting its source timestamp; stale responses remain `STALE`.

Configuration:

```text
REDSTONE_ENABLED=true
REDSTONE_API_KEY=
REDSTONE_LIVE_WS_URL=
REDSTONE_FEED_ID=ETH
REDSTONE_PUBLIC_HTTP_FALLBACK_ENABLED=true
REDSTONE_PUBLIC_HTTP_URL=https://api.redstone.finance/prices
REDSTONE_PUBLIC_HTTP_PROVIDER=redstone
REDSTONE_PUBLIC_HTTP_SYMBOL=ETH
REDSTONE_PUBLIC_HTTP_POLL_INTERVAL_SECONDS=10
REDSTONE_PUBLIC_HTTP_STALE_AFTER_SECONDS=30
```

`REDSTONE_PUBLIC_HTTP_SYMBOL` is an explicit mapping for the startup `MARKET`; when omitted it uses the explicitly configured `REDSTONE_FEED_ID`. It never infers a mapping from arbitrary Hyperliquid market names. Changing markets in LIVE mode requires restarting with explicit mappings. `REDSTONE_ENABLED=false` disables both transports; DEMO starts neither real transport.

`RedStoneProvider` retains the Phase 8.1 Live subscription, normalization, authentication, error handling and reconnect interface, and orchestrates `RedStonePublicHttpTransport`. At snapshot time it selects fresh `HEALTHY` Live evidence first, otherwise fresh `HEALTHY` HTTP evidence, otherwise actual unavailable/stale evidence. Live recovery automatically restores precedence on the next snapshot without a restart or provider resume action. The existing firewall recovery confirmations still apply to the resulting risk posture.

The effective evidence always has `provider=REDSTONE` and `source_type=ORACLE`. Live exposes `transport=LIVE_WS`, `transport_quality=PRIMARY`; HTTP exposes `PUBLIC_HTTP`, `FALLBACK`, `simulated=false`, and `source_id=redstone-public-http:ETH`. Provider health and transport quality are distinct: fresh HTTP evidence is `HEALTHY` and remains consensus-eligible. The source hierarchy, `CORE=[REDSTONE, HYPERLIQUID_ORACLE, KRAKEN]`, and six provider-level API rows remain unchanged. HTTP never supplies an additional vote. CoinGecko remains tertiary and cannot authorize NORMAL alone.

Live + Kraken agreement can still produce `VERIFIED`. While usable HTTP fallback evidence is active, confidence is capped at `DEGRADED` with reason `RedStone Live unavailable; public HTTP fallback transport active`. Conflicted or insufficient evidence retains its stricter state. The existing Phase 8 firewall applies unchanged; its default degraded-confidence posture is `REDUCE`.

Effective RedStone versions advance on transport/quality/identity/health/economic version changes even at identical prices. `ReferenceService` explicitly fingerprints `transport` and `transport_quality`. Live → HTTP → Live transitions advance reference provenance and invalidate old FinalQuoteAuthorization before transmission. Same-transport, same-price freshness updates do not introduce economic version churn.

`GET /api/v1/references` and terminal WebSocket serialization expose the singular effective evidence, including price, provider timestamp, age, status, source ID, simulation marker, transport and quality. The terminal keeps one RedStone row, appends the transport and visibly marks `FALLBACK`. Credentials and request headers remain backend-only.

DEMO evidence is deterministic, `simulated=true`, `transport=DEMO`, `transport_quality=SIMULATED`. LIVE uses only real Live or HTTP responses, or unavailable evidence; there is no synthetic runtime fallback.

Real public HTTP acceptance on 2026-10-05 is **BLOCKED BY ENVIRONMENT PROXY**: the production Python implementation received an HTTP CONNECT proxy rejection (`403 Forbidden`, `httpx.ProxyError`). No real ETH price/timestamp was received. This is separate from deterministic mocked transport acceptance and does not establish an API failure. Phase 8 remains IN REVIEW; Phase 9 remains PLANNED.


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

Phase 8.3.1 makes exact price equality independent of the deadband: even with
Yahoo's zero threshold, a legitimately newer unchanged-price observation updates
the actual source timestamp and receipt/age fields, returns `False` for price
change, and retains the price version. Every genuinely changed Yahoo price is
accepted at zero deadband. Duplicate timestamps (including conflicting prices)
and older timestamps return `False` without changing price, freshness or health.
Missing timestamps are never fabricated; stale frames and timestamps more than
five seconds ahead are rejected during Yahoo normalization. A new source frame
can recover degraded/error health, incrementing the provider's health version;
source-age-derived STALE recovers through the actual new timestamp without a
price-version increment. These are observational provider fields, never material
reference or authorization authority.

RedStone/Kraken/CoinGecko retain their positive deadbands. The exact-equality
branch already applied to them, so their behavior is unchanged: an identical
new tick can refresh its own timestamp, while a suppressed different price
cannot lend freshness to the retained price. Regression fixtures cover all three.

`MATERIAL_PROVIDERS` lists the six existing material snapshot/terminal rows:
CORE plus CoinGecko, Hyperliquid mid and mark. `ALL` remains the four consensus
comparison sources, and CORE remains the three quorum roles. The broader
`ProviderId` registry additionally names Yahoo for the separate observation API.
It does not add a material row or vote. The terminal generator uses the explicit
material list, preserving the existing checked-in `phase12-v1` schema exactly.

`ReferenceSnapshot.version` changes when the normalized reference state materially changes. Final execution authority binds to that version.

## DEMO and LIVE PAPER

DEMO creates deterministic simulated RedStone, Kraken and CoinGecko evidence and marks each `simulated=true`.

LIVE market/reference data can run with PAPER execution. No trading wallet is required for public references or PAPER execution.

## Phase 8 CoinGecko hardening and optional Yahoo observation — 2026-10-08

CoinGecko enabled Demo and Pro reference modes require `COINGECKO_API_KEY`. Only the exact TLS hosts `https://api.coingecko.com/api/v3` (Demo / `x-cg-demo-api-key`) and `https://pro-api.coingecko.com/api/v3` (Pro / `x-cg-pro-api-key`) receive credentials. Missing configuration or untrusted hosts become provider ERROR without a network request. Disabled mode needs no credentials. HTTP 400/401/403 are ERROR; 429, 5xx, network and decoding errors are DEGRADED with bounded retries. CoinGecko remains tertiary and cannot satisfy core quorum.

Optional Yahoo personal research observation: install `pip install -e '.[yahoo]'`; defaults are `YFINANCE_REFERENCE_ENABLED=false`, `YFINANCE_SYMBOL=ETH-USD`, `YFINANCE_STALE_AFTER_SECONDS=30`. Mapping is explicit: ETH→ETH-USD, BTC→BTC-USD; other startup markets are unavailable, not guessed. The decoded yfinance `AsyncWebSocket` fields `id`, `price`, and Unix-millisecond `time` are validated against a source-time freshness window. Replays, wrong symbols, invalid values and missing/old/future timestamps are rejected. A bounded reconnect loop cancels listener/watchdog tasks and closes sockets. Missing optional dependency is observational ERROR only.

The separately polled `GET /api/v1/references/observations` endpoint and Risk-page card expose observational health, source age, prices and available signed comparison bps. Unavailable comparisons remain null. **Yahoo is excluded from CORE, ALL, the material reference snapshot, economic version/fingerprint, quorum, outlier decisions, risk, agents, authorization, accounting and execution.** It cannot replace RedStone, Kraken or Hyperliquid evidence or authorize trades. The Phase 12 streaming contract remains unchanged.

**Licensing and acceptance:** Yahoo data is for permitted local personal/research observation only. Do not redistribute it publicly or use it for commercial trading without appropriate rights. Live CoinGecko and Yahoo connections, real schemas and reconnect acceptance remain pending. Phase 8.3.1 fixture and local command results are recorded in the roadmap; they do not establish live-provider acceptance. Historical Audit 2.0 issues A2-001–A2-005 are unchanged. No Actions files, Docker, PostgreSQL, signing changes or new trading authority. No additional oracle providers were introduced; unsupported oracle integrations remain prohibited.
