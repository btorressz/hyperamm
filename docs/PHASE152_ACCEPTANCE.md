# Phase 15.2 — Live streams, market integrity and provider health

Implemented on Linux for read-only public BTC/ETH/SOL native perpetual observation,
October 10, 2026 (America/Los_Angeles). Delivery is one draft PR, **do not merge**.
Deterministic fixtures and intercepted actual SDK compatibility are separate from
genuine venue acceptance. **LIVE EXTERNALLY VERIFIED remains open.**

## Verified preflight

Repository `btorressz/hyperamm`; original checkout was clean at Phase 14.6.
Fetched latest `origin/main`, independently verified PRs #49 and #50 merged via
GitHub, then created `phase15/15-2-live-stream-provider-integrity` from exact main
**3ba75863ccd4d7b4c80bde6f600b5aecd5269762**. Main was fetched again before delivery
and remained that SHA. No implementation was built against the obsolete checkout.

Read CODEBASE, ROADMAP, ARCHITECTURE, HYPERLIQUID_INTEGRATION, REFERENCE_INTEGRITY,
PERP_CONTEXT, PHASE146_ACCEPTANCE, PHASE151_ACCEPTANCE and docs/AGENTS. Inspected
SDK constructor/subscription/unsubscription/shutdown and actual worker/ping
ownership, the operational adapter, Phase 15.1 contracts/service, metadata/profile
rules, history patterns, terminal WebSocket ownership and provider authority graph.

Python 3.12.14, SDK **0.24.0**, FastAPI 0.143.0, Pydantic 2.14.0, Starlette 1.7.0,
httpx 0.28.1, pytest 8.4.2; Node 24.19.0. Dependency ranges and lockfile unchanged.
Installed existing `.[test,ml,redis,yahoo]` in a workspace venv and locked `npm ci`
with a workspace cache. Shell network access uses the existing policy/proxy; no
TLS bypass, route change, secret inspection or policy modification was performed.

Actual unchanged-base backend: **1413 passed, 0 failed/skipped, 1 warning; 39.98s**.
Frontend: **454 passed, 0 failed/skipped/cancelled; 15.272575s**. TypeScript passed;
production build passed, 2.91s. Historical Phase 15.1's **1412 passed + 1 generated
schema failure** was explicitly compared: the failure did **not** reproduce with
current dependencies. The protected generated-schema test, generator and schema
were neither changed, skipped, weakened nor regenerated.

Setup attempts are not acceptance: initial shell fetch could not reach its proxy
without network execution; global pip/home npm-cache writes were read-only, so a
workspace venv/cache was used. A prematurely started pytest collection while pip
was still installing had eight collection errors. A subsequent sandbox-only
TestClient run stalled and was terminated; enabling the permitted local networking
resolved it. The completed clean-base execution above supersedes these setup
attempts, rather than concealing or counting them as successful regression runs.

## Delivered files and reuse

Added backend: `live_streams.py`, `live_stream_models.py`, `live_history.py`,
`live_provider_mappings.py`, `live_provider_integrity.py`, `live_market_streams.py`
and three focused `test_phase152_*.py` files. Enhanced `config.py`, `main.py`,
`api/live_markets.py`, and narrowly shared helpers in `live_observations.py`.

Reused unchanged: Phase 15.1 immutable metadata/book/perp models and strict
normalizers, native metadata validation, research native-market whitelist and
price rules, operational adapter socket readiness, existing perpetual parsing/
basis/OI arithmetic, and reference ProviderId/PriceEvidence/SourceType/status/
transport/quality contracts. Existing history/terminal resource ownership patterns
informed the separate stores and WS router; no operational history is reused as
storage for observed markets. REST cache/acquisition/source identities remain
independent, and phase151-v1 is unchanged.

Frontend changes are strict TypeScript contracts, four GET helpers and four
contract/API tests only. No React terminal, page redesign, charts, trading controls,
market-vs-PAPER comparison or browser SDK connection is introduced. Documentation
updates: CODEBASE, ROADMAP, ARCHITECTURE, HYPERLIQUID_INTEGRATION,
REFERENCE_INTEGRITY, TERMINAL and this acceptance record. Earlier artifacts remain.

The existing Phase 15.1 API route enumeration test was expanded from its two GET
paths to all six GET paths, retaining its exact-route and GET-only assertions.
No existing test or authority assertion was removed or weakened.

## SDK ownership, bootstrap and recovery

One serialized worker owns one public stream `Info`/WebSocket manager for the
fixed three-market scope. Metadata-only bootstrap `Info.meta(dex='')` is validated
and closed before constructing mapped `Info(skip_ws=False)` with actual native
metadata and empty spot metadata. The mapped object is owned before its SDK
constructor starts threads; interrupted initialization is cleaned up. Native
`name_to_coin`, `coin_to_asset` and `asset_to_sz_decimals` must match the validated
universe. Missing/delisted markets get no subscription or DEMO fallback.

Every listed market has one `l2Book` and one `activeAssetCtx` handle. SDK readiness
precedes registration; all six subscriptions precede per-market REST L2 snapshots
and validated REST native context. REQUESTED is not OBSERVED. Acknowledgements
are ignored as economic evidence; AVAILABLE requires a valid book boundary,
complete component state, fresh metadata/L2/context, and actual validated delivery
on both WS channels. REST bootstrap keeps its actual REST source; identical WS
L2 packets do not relabel or retime it.

Hyperliquid L2 packets are complete snapshots. Strict Decimal precision/size,
market attribution, source timestamp, ordering, duplicate/crossed levels and depth
checks are reused. All received validated levels enter the same-time economic
identity, including depth beyond the 20-level API output. Older source events and
conflicting equal-time economics are rejected; equal identical events do not
renew receipts, source age or history. Watermarks persist across connection
recovery, while current components and channel-delivery state do not.

Reconnect retires the old ingress, closes the old client before replacement,
advances generation, clears current components, records history gaps, revalidates
native metadata/maps, recreates handles and fresh REST book barriers, then
reconciles queued snapshots. Older queued books cannot replace the barrier. Late
old-generation callbacks cannot mutate state, counters or history. Native context
receipts older than the latest acquisition are rejected without asserting trusted
economic event time. Sustained source/metadata staleness also triggers recovery.
Backoff doubles within configured bounds; rate/forbidden failures wait at least
30 seconds. Stop interrupts backoff.

## Bounded callbacks and browser transport

Each market has a thread-owned fixed buffer; a callback only captures actual
receipt and detaches a bounded JSON message. The ingestion mechanism schedules
**one pending asyncio wake**, rather than an unbounded callback for every packet.
Per-market overflow is counted, records a gap, invalidates both components and
requires a fresh book boundary plus new context/channel evidence. Repeated
malformed/stale data cannot advertise uninterrupted history.

The additive `phase152-v1` status/envelope carries an observer UUID, connection
generation, service publication sequence, emission time and normalized component
payload. Publication sequence is not an exchange sequence. Freshness is recomputed
from source/receipt time, independent of browser polls and health ticks. Browser
publication sends latest state per bounded ingestion batch; each accepted
component still has an opportunity to enter history. No raw SDK data is exposed.

`WS /ws/live-markets/{BTC|ETH|SOL}` requires both switches and never creates an SDK
client per browser. Its initial frame is a newly evaluated snapshot/status.
Admission is bounded across all markets, per-client queues hold eight envelopes,
frames are at most 64 KiB and sends have a five-second deadline. Queue overflow
replaces queued frames with a termination sentinel; the endpoint closes 1013 and
requires a new snapshot connection. Slow clients retain admission until their
structured sender/receiver have joined and unsubscribed. Unsupported markets
close 1008; disabled/capacity admission closes 1013. Incoming browser messages have
no strategy/configuration/subscription-control authority.

Shutdown stops admission and ingress, signals browsers, drains synchronous SDK
operations, unsubscribes all registered handles and closes the socket/sessions.
SDK `disconnect_websocket()` joins ping but not the manager; both threads are
explicitly joined/verified. Disconnected unsubscribe failures are recorded safely
and resolved by verified whole-connection teardown. Cleanup failure reports
CLEANUP_ERROR, retains ownership and prevents replacement. A cancelled/timed-out
shutdown keeps an owned drain task; completion also waits for browser owners to
release queues. Pathological synchronous SDK calls cannot be forcibly stopped by
asyncio: an incomplete shutdown is reported, not claimed successful.

## Source and history semantics

L2 source_timestamp is exact venue milliseconds, separate from actual receipt.
Context `activeAssetCtx` has no documented trusted per-event timestamp here:
source_timestamp remains **null**, event_time_verified false and perp_event_time
UNKNOWN. Recent receipt establishes transport observation only. Funding stays the
raw current venue rate; OI notional/basis arithmetic uses existing normalizers.
Missing provider mid keeps midpoint-basis values null. No L2-derived fake oracle,
forward-filled mark or synthetic source timestamp is produced.

Each market retains at most configured history points. L2 accepted event times
are monotonic and duplicate-suppressed across generations. Context duplicate
financial observations are suppressed without inventing event chronology. Points
contain only their arriving component's actual values; unrelated values are null.
Buffered book receipt order can differ from REST receipt order, so source ordering
is tracked separately and retained receipt coverage uses actual min/max receipts.
Explicit eviction/gap counts and observer/generation identity describe coverage;
continuous_history_verified is always false. Polling/health publication creates
no sample. Restart changes observer UUID and empties history. No durable database,
interpolation, terminal-history mutation or invented prior coverage exists.

## Providers and APIs

Native midpoint, oracle and mark are separate roles within one HYPERLIQUID source
group. Mid health uses exchange-event freshness. Recent context oracle/mark rows
are DEGRADED/EVENT_TIME_UNKNOWN; aging rows are STALE. Missing or disconnected
components and expired/invalid metadata cannot create healthy price evidence.
The existing PriceEvidence contract is reused only inside this observation path.

External RedStone/Kraken/CoinGecko/Yahoo rows remain disabled with no guessed symbol
or validation timestamp. Mapping allowlists validate explicit operator candidates;
they are not configuration or proof of underlying live feed support. Each mapping
binds market/provider/native symbol/source ID/transport/validation time, and a
pure evidence gate rejects wrong provider/market/source role/transport/simulation.
RedStone Live PRIMARY and HTTP FALLBACK share one identity; no double vote exists.
Kraken is an exchange reference, CoinGecko a tertiary aggregator, Yahoo authority
NONE. Existing Yahoo supports explicit BTC/ETH only; SOL is unavailable. No new
external collector is enabled. No usable independent external observation exists,
so consensus_price is null. All rows have authority NONE and cannot enter trading
quorum, reference versions or order authorization.

| Route | Contract |
| --- | --- |
| Existing GET `/api/v1/live-markets/overview` | unchanged phase151-v1 REST overview/HTTP availability semantics |
| Existing GET `/api/v1/live-markets/{market}/snapshot` | unchanged phase151-v1 REST snapshot/HTTP availability semantics |
| GET `/api/v1/live-markets/{market}/stream-status` | phase152-v1 connection/subscription/component age/status/counters |
| GET `/api/v1/live-markets/{market}/stream-snapshot` | typed independent stream components and current availability |
| GET `/api/v1/live-markets/{market}/history?limit=100` | retained component points, coverage, gaps and eviction; limit 1–1000 |
| GET `/api/v1/live-markets/{market}/references` | native source roles and disabled external provider evidence |
| WS `/ws/live-markets/{market}` | normalized bounded phase152-v1 snapshot/status envelopes |

New GET endpoints return status-bearing HTTP 200 evidence even when DISABLED or
UNAVAILABLE; clients must inspect payload statuses. Invalid market/limit gets
sanitized 422, POST gets 405, all GET responses are no-store. Existing REST routes
continue their original 200/429/503/504 availability semantics. Selecting or
subscribing never changes the operational market.

## Configuration

| Setting | Default | Bounds |
| --- | --- | --- |
| LIVE_STREAMS_ENABLED | false | requires LIVE_OBSERVATIONS_ENABLED when true |
| LIVE_STREAM_MAX_SUBSCRIBERS | 16 | integer 1–64 |
| LIVE_STREAM_QUEUE_CAPACITY | 64 | integer 1–1024 per market |
| LIVE_STREAM_HISTORY_MAX_POINTS | 1000 | integer 1–3600 per market |
| LIVE_STREAM_L2_STALE_AFTER_SECONDS | 10 | finite >0 to 300 |
| LIVE_STREAM_PERP_STALE_AFTER_SECONDS | 30 | finite >0 to 300 |
| LIVE_STREAM_CONNECT_TIMEOUT_SECONDS | 10 | finite >0 to 30 |
| LIVE_STREAM_RECONNECT_INITIAL_SECONDS | 1 | finite >0 to 30, not greater than maximum |
| LIVE_STREAM_RECONNECT_MAX_SECONDS | 30 | finite >0 to 300 |
| LIVE_STREAM_SHUTDOWN_TIMEOUT_SECONDS | 15 | finite >0 to 120 |

Browser queue capacity is eight, SDK input/output message cap 64 KiB. Existing
observation HTTP timeout (5s), metadata stale budget (300s), future skew tolerance
(1s) and book output depth (20) are reused. Integer options reject booleans/floats
while accepting bounded environment strings. Default DEMO/PAPER startup makes no
new SDK socket. Explicit observation switches can coexist with operational ETH
DEMO/PAPER without changing execution mode, keys or permissions.

## Runtime authority proof

Actual DEMO/PAPER runtime tests seed quotes, authorization, resting orders,
executed PAPER fills/position and accounting/ledger state; background operational
ticks are not started. Both normal and manual-kill fixtures preserve exact
StrategyConfig, running/market, AgentConfig/RiskFirewallConfig, kill latch,
FinalQuoteAuthorization, quotes/orders/fills, PAPER position, order/execution/
accounting identities/configuration, vault/ledger entries/fingerprint/capital
reservations, TESTNET eligibility and market/perp/reference service identities.
All assets, new GET routes, browser subscriptions, stream changes, malformed
source, reconnect and shutdown are exercised. Research anchors stay unchanged.
AST checks independently exclude runtime/trading-authority imports and calls.
Observational receipts/publication sequences may naturally advance; they are not
protected trading invariants and are not incorrectly asserted frozen.

## Executed regression

Commands use the workspace venv/cache and permitted local networking for tests:

```bash
cd backend
python -m pip install -e '.[test,ml,redis,yahoo]'
python -m pip check
python -m compileall -q app
python -m pytest -q
python -m pytest tests/test_phase152_live_streams.py tests/test_phase152_provider_integrity.py tests/test_phase152_runtime_isolation.py -q
cd ../frontend
npm ci --cache /workspace/work/npm-cache
npm test
npm run typecheck
npm run build
```

| Check | Exact result |
| --- | --- |
| Clean-base backend | 1413 passed, 1 warning, 39.98 s |
| Final Phase 15.2 focused backend | 135 passed, 1 warning, 21.07 s |
| Final complete backend | 1548 passed, 1 warning, 90.60 s; 0 failed/skipped |
| Preserved Phase 15.1 suite, separate final run | 132 passed, 1 warning, 2.10 s |
| Clean-base frontend | 454 passed, 15.272575 s |
| Final frontend | 458 passed, 20.118815 s; 0 failed/skipped/cancelled |
| Baseline and final TypeScript | PASS |
| Baseline / final production build | PASS, 2.91 s / 3.89 s |
| Dependency consistency / Python compilation / diff whitespace | PASS |
| Existing terminal schema regression | PASS unchanged on baseline and final; historical failure did not reproduce |

One upstream Starlette/httpx TestClient deprecation warning remains. Frontend
keeps its headless Zustand storage notice, TanStack module-directive notices and
~536 kB main chunk advisory. Installation also reports pip's unwritable default
home cache; acceptance uses the writable workspace venv/cache. No React UI was
changed, so new Chromium UI/viewport acceptance is not claimed.

An early focused test attempted to fail the SDK constructor but also failed the
metadata-only bootstrap, so it did not reach partial WS initialization. The
fixture was corrected to fail only the mapped constructor after thread start;
manager/ping/session ownership is now directly tested. Earlier successful runs
preceded the final browser-drain admission refinement and are not substituted for
the final full execution. No implementation test failure is left unresolved.

## Genuine external acceptance and remaining gates

The executor's version-1 networking snapshot excludes `api.hyperliquid.xyz` from
restricted HTTP egress and grants no VPN/TCP destination. The current environment
status reports observations_current=true but network policy state **unknown**;
it does not prove enforced/readiness. No grant permits genuine Hyperliquid API/WS
acceptance. Per the request, no policy-denied live request, synthetic success or
TLS/proxy bypass was attempted. Historical PR #50's blocker remains separate from
this execution's **NOT RUN** outcome.

| Genuine venue gate | Actual result |
| --- | --- |
| Native metadata/maps via live official SDK | NOT RUN — no permitted destination |
| BTC/ETH/SOL l2Book delivery/source timestamps | NOT RUN — same blocker |
| BTC/ETH/SOL activeAssetCtx delivery/receipt semantics | NOT RUN — same blocker |
| Genuine reconnect/snapshot recovery/cleanup | NOT RUN — same blocker |
| Rate limits, provider availability and soak | NOT RUN — same blocker |

Network-permitted Mac acceptance must opt into both switches with operational
DEMO/PAPER and signing disabled, verify all six native subscriptions and real L2
source times, context null-event/receipt semantics, disconnect/reconnect generation
retirement/rest barriers, source stalls, limits and both SDK thread shutdowns.
Capture actual evidence and retain an open gate until that happens. Fixture
compatibility does not close this gate or certify production/signed trading.

Phase 15.3 remains responsible for the React live consumer and strict observer/
generation/availability handling. Phase 15.4 comparison, Phase 15.5 final
security/regression acceptance, external provider enablement, macOS, real Redis,
signed TESTNET and long soak remain separate. No multi-market AMM execution,
portfolio allocation, new oracle provider, Docker, PostgreSQL, Actions, `.github/`,
wallet/custody, ML training or execution permissions are added. **Draft only.**
