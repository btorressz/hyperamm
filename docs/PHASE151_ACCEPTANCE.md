# Phase 15.1 — Read-Only Hyperliquid Live Market Observation & API Contracts

Implementation and deterministic fixture acceptance on Linux, October 10, 2026.
**Full regression acceptance remains open:** the terminal-schema equality test
already fails on the unchanged base. **LIVE EXTERNALLY VERIFIED is not claimed:**
the managed network policy excludes `api.hyperliquid.xyz`. Delivery is one draft
PR; do not merge. Phase 15.2–15.5 remain planned.

## Verified preflight

Repository `btorressz/hyperamm`; original working tree clean on branch `work`.
Fetched latest `origin/main`, independently verified PRs #43–#49 merged with the
GitHub connector, and created `phase15/15-1-live-market-observation` from exact
base **66dbe4f1d1e6ffd8832a99916ba927e0b284655c**. Fetched main again before delivery.
The local checkout initially predated Phase 14.6; no implementation was made
against that obsolete tree. Sandbox-only fetch initially failed; normal proxy
network execution fetched the permitted GitHub host without bypassing policy.

Read CODEBASE, ROADMAP, ARCHITECTURE, HYPERLIQUID_INTEGRATION,
REFERENCE_INTEGRITY, PERP_CONTEXT, TERMINAL, SIMULATION, PHASE14_ACCEPTANCE,
PHASE146_ACCEPTANCE and docs/AGENTS. Inspected the actual runtime authority graph,
SDK adapter/cleanup, metadata catalog, market models/history/service, research
profiles, perpetual normalizers, FastAPI lifecycle/routers and existing isolation
fixtures before implementation. Historical test counts were not substituted for
new executions.

Python 3.12.14; official Hyperliquid SDK **0.24.0**; dependency range
`hyperliquid-python-sdk>=0.24.0,<0.25` unchanged. Actual resolved FastAPI 0.142.2,
Pydantic 2.13.5, Starlette 1.7.0, httpx 0.28.1, pytest 8.4.2. SDK `Info` constructor,
`meta`, `l2_snapshot`, `meta_and_asset_ctxs`, native symbol mappings and HTTP
session/timeout implementation were inspected. No dependency-range changes.

## Delivered contracts and routes

| Contract | Semantics |
| --- | --- |
| `LiveMarketId` | Reuses the Phase 14.6 exact BTC/ETH/SOL whitelist; display labels are separate |
| `LiveMarketMetadata` | Native index, listing, `szDecimals`, real receipt time, source and EXCHANGE_VERIFIED/UNAVAILABLE/STALE/ERROR |
| `LiveBookObservation` | Frozen tuple depth, BBO, midpoint, spread/bps, exchange event time and separate receipt time |
| `LivePerpObservation` | Mark, oracle, raw funding, OI base/notional, premium/provider mid, available basis values; null event time |
| `LiveFreshness` | Independent metadata, L2 source and context receipt ages/statuses; acquisition gap/coherence; unknown perp event-time freshness |
| `LiveMarketSnapshot` | `phase151-v1`, identity/provenance, component evidence, status, generation/cache/last-success times, fixed safe errors and limitations |
| `LiveMarketOverview` | Exactly BTC, ETH, SOL once in catalog order, with independent snapshots and a final freshness evaluation |

Externally constructed models forbid extra fields and accepted evidence is
frozen, including nested levels/tuples. Financial fields accept finite Decimal,
integer or plain decimal strings, reject binary floats/booleans/nonfinite or
malformed inputs, and serialize explicitly to JSON strings. Inputs are bounded
at 80 text characters, absolute magnitude 1e30 and decimal exponents from -60 to 30 before
financial arithmetic. These resource bounds are not venue funding forecasts.
Positive prices and nonnegative sizes/OI are required; missing values remain
null. UTC-aware datetimes are required; production clocks emit UTC.

Only these new GET routes are registered under the existing prefix:

```text
GET /api/v1/live-markets/overview
GET /api/v1/live-markets/{market}/snapshot
```

The selected-market response is the typed snapshot for every modeled status.
HTTP 200 means AVAILABLE or explicitly PARTIAL/DEGRADED evidence; errors,
nullable components and freshness remain visible. STALE and disabled/closed/
unavailable snapshots use 503; external timeout uses 504; capacity and upstream
429 use 429 with Retry-After. An overview with at least one usable/partial row
uses 200; otherwise priority is 429, 504, 503. All rows retain their own status.
Responses use `Cache-Control: no-store`. Invalid symbols use sanitized 422;
unknown routes use existing 404; POST on a known observer path is 405. Fixed
error messages never echo SDK exceptions, headers, URLs or credentials.

Frontend additions are wire types only in `frontend/src/types/index.ts`:
matching statuses, nullable event times/components and string Decimal fields.
There is no mounted consumer, new polling, selector, market navigation, chart
or live-terminal change. React terminal and operational APIs retain their contracts.

## Native exchange evidence and normalization

`validate_native_metadata` is reused unchanged. It validates native `dex=""`,
bounded universe structure/order, unique compatible names, strict integer size
precision and boolean delisting. Missing/delisted markets are unavailable.
No pinned DEMO profile can establish a live listing, index, price or eligibility.
The research catalog retains its own explicitly allowed research-only fallback;
both paths use the same validator, and no redundant metadata endpoint is added.

Each admitted refresh owns a metadata-only bootstrap `Info` with empty supported
initialization maps, calls `meta(dex="")`, validates the actual response and
closes that session. A second `Info` initializes with the **actual validated
native universe** and empty spot metadata. The official constructor populates
`name_to_coin`, `coin_to_asset` and `asset_to_sz_decimals`; their requested-market
entries must match the validated metadata. No internal SDK maps are fabricated
or modified. `l2_snapshot` is never called on the empty bootstrap.

Acquisition order is metadata, requested L2, native meta/context. There are three
public HTTP calls per successful refresh, no constructor spot/HIP-3 discovery,
no WebSocket and no account/address/private key. A failed L2 can still yield
clearly partial context, and failed context can yield partial L2.

The operational book normalizer is not reused because it constructs mutable
models and stamps local time. A narrow observation normalizer preserves the
real millisecond source time and requires an **explicit matching `coin`**;
missing symbols are rejected. Both sides must be present, with valid finite
prices, nonnegative sizes, integer nonnegative order counts, strict descending
bids/ascending asks and uncrossed BBO. Duplicates and malformed levels are
rejected. All received levels are validated before optional truncation: at most
100 wire levels per side and 20 returned levels. Size lot precision and official
five-significant-figure/noninteger decimal-place rules with the integer exception
reuse Phase 14.6 `validate_price`; no guessed universal price tick is asserted.

Perpetual context validates its own full native metadata, target index/precision/
listing and exact universe/context cardinality before resolving the selected
entry. Explicit conflicting context symbols are rejected. Existing
`normalize_meta_and_asset_ctxs` → `normalize_active_asset_ctx` →
`build_perp_market_context` supplies financial parsing and basis/OI arithmetic.
Mark/oracle context prices are economic values, not proposed executable orders.
OI notional is OI base × mark; funding is the raw current venue rate, not annualized.
Mark/oracle basis keeps the established formula. Mark/mid and oracle/mid bases
use **only the provider mid in the same context response**. Missing provider mid
produces null mid/bases; the existing parser's fallback mid is not exposed.
No basis calculation combines an independently retrieved book with the context.

## Timestamp, freshness and cache semantics

- L2 `source_timestamp` is the exact exchange milliseconds, distinct from local
  `observed_at`. Up to one second of future clock skew is allowed by default;
  farther future, noninteger, impossible or absent timestamps are invalid.
- Context `source_timestamp` is always null because this REST source has no
  exchange event time. `observed_at` is its actual local receipt, and its
  event-time freshness is UNKNOWN even when retrieval age is FRESH.
- Metadata age is since successful local receipt, never proof of listing-event
  time. EXCHANGE_VERIFIED requires actual validated receipt; expiration is STALE.
- Snapshot `observed_at` is the latest accepted book/context receipt; it is null
  when neither component was accepted. `generated_at` is response construction.
  `cache_stored_at` records refresh completion; cache age/TTL use monotonic time.
- `last_successful_observed_at` is the last complete AVAILABLE acquisition; it
  survives refresh failure for diagnostics without retaining old current values.
- Coherence compares local book/context receipt times (default two seconds),
  not asserted exchange simultaneity. Excess gap yields DEGRADED plus an explicit
  temporal discrepancy. Separate source times/limitations remain visible.
- Cache hits never retime source evidence. Expiration, backward local time,
  old exchange snapshots and aging context are evaluated independently. Stale
  evidence remains explicitly STALE/503 even if its cache TTL has not expired.
- Per-market L2 watermarks reject older event times and changed normalized depth
  at the same timestamp. Identical repeated event-time depth is allowed, retains
  the original source time and ages normally; no history sample is created.
- Failed refresh replaces the current cache with unavailable/partial evidence;
  it never relabels retained old success as a fresh observation. Each cache and
  watermark is keyed by the fixed market, so one asset cannot contaminate another.

## Enablement, ownership and bounded work

| Environment setting | Default | Valid range |
| --- | --- | --- |
| `LIVE_OBSERVATIONS_ENABLED` | false | Boolean opt-in |
| `LIVE_OBSERVATION_HTTP_TIMEOUT_SECONDS` | 5 | >0 to 30 |
| `LIVE_OBSERVATION_CACHE_TTL_SECONDS` | 2 | >0 to 60 |
| `LIVE_OBSERVATION_STALE_AFTER_SECONDS` | 10 | >0 to 300 |
| `LIVE_OBSERVATION_MAX_CONCURRENT_REQUESTS` | 2 | Integer 1–3 |
| `LIVE_OBSERVATION_METADATA_STALE_AFTER_SECONDS` | 300 | >0 to 3600 |
| `LIVE_OBSERVATION_COHERENCE_SECONDS` | 2 | >0 to 30 |
| `LIVE_OBSERVATION_FUTURE_TOLERANCE_SECONDS` | 1 | 0–5 |
| `LIVE_OBSERVATION_BOOK_LEVELS` | 20 | Integer 1–20 |

All numeric settings reject invalid/nonfinite values; integer options also
support bounded environment strings while rejecting booleans/floats. TTL and
freshness are deliberately independent: a long cache TTL cannot renew evidence.
Explicit observer enablement works with operational DEMO/PAPER without changing
its market or execution mode. Disabled construction/reads make no SDK requests.

FastAPI lifespan creates one independent service with lazy network acquisition.
A finite thread pool runs synchronous SDK calls off the event loop. Admission
rejects capacity immediately: no executor queue, at most configured in-flight
market tasks, one shielded single-flight task per market, and three cache entries.
Bootstrap closes before mapped-client construction. SDK sessions are owned
entirely by their workers. Overview sequentially acquires the fixed catalog and
reevaluates all ages/cache ages at completion; capacity=1 remains supported.

SDK socket connect/read timeout is finite. Response deadline is 6 × HTTP timeout
+ 5 seconds (35s default); shutdown deadline is five seconds longer (40s default).
Timeout/cancellation of an asyncio reader does **not** terminate its synchronous
worker or release admission. The owned operation continues closing its session,
and later readers may join it. Shutdown stops admission, shields retained drain
ownership, joins operations, then shuts down the worker pool. A shutdown deadline
reports incomplete cleanup while retaining the drain task; it never pretends a
running worker has stopped. Synchronous transport work cannot be forcibly killed
by asyncio; pathological transport behavior remains an explicit runtime limit.

Failed session close disables further admission, retains at most the sessions
of admitted workers, publishes CLEANUP_ERROR and retries retained close once
on shutdown. Continued cleanup failure raises a fixed shutdown error; no false
healthy snapshot or successful cleanup claim. Ordinary retries are demand-driven:
zero immediate network retries, at least five seconds negative-cache cooldown,
and at least 30 seconds for upstream 429/403. Successful demand recovers after
cooldown; there is no background refresh loop or history architecture.

## Authority and regression proof

The observer/router never imports or retrieves the operational runtime. It has
no `Exchange`, signing helpers, wallet/account fields, runtime configuration
writes, order methods, leverage/margin calls, withdrawal or transfer methods.
Its only SDK calls are native metadata, L2 and native context. No new evidence
is passed to agents, reference consensus, RiskFirewall, FinalQuoteAuthorization,
execution, capital reservations or authoritative accounting. Existing
`/markets/{market}` and `/markets/{market}/book` remain active-market-only.

New tests seed a **real** DEMO/PAPER runtime with quotes, authorization and PAPER
orders, freeze background ticks, and exercise overview and all three snapshot
routes with the separate fake SDK. Both normal and manually killed states retain
exact StrategyConfig, market, running state, feed/perp/reference service identities,
AgentConfig/RiskFirewallConfig, kill latch, authorization, quotes/orders/fills,
execution/order/accounting identities, vault/ledger/entries/reservations and
TESTNET eligibility. Hypothetical research anchors are unchanged. AST call-graph
checks independently reject trading-authority imports/calls. Existing tests are
preserved, without skip, xfail, suppression or changed terminal schema.

Fixtures cover all supported assets, malformed/missing/delisted metadata,
precision/identity/book ordering, finite financial values, timestamp expiry,
future/replayed/conflicting events, context mapping/cardinality, correct basis,
unknown event times, partial failures, cache expiry/failed refresh/recovery,
rate cooldown, overload, cancellation, response/shutdown deadlines, retained
cleanup failure, lazy enabled/disabled lifespans, OpenAPI/HTTP states and isolation.
An additional HTTP-intercepted test runs the **actual installed official SDK**
constructor and methods for BTC/ETH/SOL, verifying mappings/timeouts/session close
and absence of spot/HIP-3 discovery. It is deterministic compatibility evidence,
not an external live API test.

## Executed checks

| Check | Executed result |
| --- | --- |
| Unchanged-base backend full suite | **1280 passed, 1 failed, 0 skipped, 1 warning; 59.94s** |
| Unchanged-base frontend suite | **454 passed, 0 failed/skipped/cancelled; 19.282s** |
| Unchanged-base TypeScript / build | PASS / PASS; Vite 4.61s |
| Final focused observer suite | **132 passed, 0 failed/skipped, 1 warning; 1.37s** |
| First final backend, frontend running alongside | **1407 passed, 2 failed, 0 skipped, 1 warning; 72.59s** |
| Serial backend before final Decimal zero-scale guard | **1408 passed, 1 failed, 0 skipped, 1 warning; 50.40s** |
| Final backend after zero-scale guard | **1412 passed, 1 failed, 0 skipped, 1 warning; 51.36s** |
| Final frontend suite | **454 passed, 0 failed/skipped/cancelled; 32.747s** |
| Final TypeScript / build | PASS / PASS; Vite 4.66s |
| Pip check / compileall / diff whitespace | PASS / PASS / PASS |
| Isolated final watchdog regression | **1 passed, 0 failed/skipped; 1.37s** |
| Clean-base watchdog + schema investigation | **1 passed, 1 failed, 0 skipped; 1.76s** (schema fails, watchdog passes) |

The first final run also observed a timeout in
`test_stale_watchdog_with_long_quote_interval`, which has a 0.1s source window
and a 0.5s order-appearance deadline. It passed independently and on the clean
base, and did not recur in either subsequent serial full run. Concurrent frontend
work was present during the failing run; no causal root claim or timing-test
change is made. The failure remains recorded, not hidden by retrying until green.
The last full run follows the final Decimal scale guard, including zero values,
with all 132 new tests preserved and only the unchanged-base schema failure.

Node 24.19.0, npm 11.9.0; each frontend suite logs one existing headless Zustand
storage-unavailable notice. Test warnings are not summarized by Node; no new
frontend warning is introduced. Nonfatal TanStack build notices/chunk advisory
remain. Backend warning count is exactly one in each full/focused run.

Commands used from backend: existing interpreter, `python -m pip install -e
'.[test,ml,redis,yahoo]'`, `python -m pip check`, `python -m compileall -q app`,
`python -m pytest -q`, and focused `python -m pytest
tests/test_phase151_live_markets.py -q`. Frontend: locked `npm ci` with workspace
cache, `npm test`, `npm run typecheck`, `npm run build` before and after. Logs are
scratch files, not committed wire dumps or evidence archives.

The unchanged-base failure is
`tests/test_audit_terminal_contract.py::test_generated_terminal_schema_is_current`:
computed inventory/perpetual Decimal field schemas differ in `pattern` keys
from the checked-in schema. This observer does not change terminal models,
generator, schema, dependencies or that protected test. The failure is recorded
as an open gate, not fixed by weakening checks or regenerating unrelated artifacts.
One upstream Starlette/httpx TestClient deprecation remains. Frontend build
retains existing TanStack directive notices and the Vite chunk-size advisory.
No browser UI was changed, so new Chromium workflow/viewport acceptance is not
claimed. Historical browser artifacts remain untouched.

## Genuine network acceptance and limitations

The current supported environment status reports enforced restricted HTTP policy.
The executor policy excludes `api.hyperliquid.xyz`; there are no VPN/TCP grants.
No live source request was sent to a policy-denied destination, no proxy/TLS
controls were changed, and no external observation is fabricated. The historical
Phase 14.6 ProxyError is prior evidence, not a new executed request.

| Genuine SDK check | Result |
| --- | --- |
| `Info.meta(dex="")` native metadata | NOT RUN — destination outside enforced allowlist |
| `Info.l2_snapshot("BTC")` | NOT RUN — requires permitted API and validated live maps |
| `Info.l2_snapshot("ETH")` | NOT RUN — same blocker |
| `Info.l2_snapshot("SOL")` | NOT RUN — same blocker |
| `Info.meta_and_asset_ctxs()` | NOT RUN — same blocker |

Consequently no genuine HTTP success/status, live metadata, source time or source
age is claimed. SDK version and fixture acceptance are known; **LIVE EXTERNALLY
VERIFIED remains open** for a network-permitted local environment. The application
remains usable with the disabled optional observer. macOS, existing unrelated
audit/provider/Redis/signed TESTNET/soak gates are not closed by this phase.

Phase 15.2 should add owned streams, source/reconnect integrity, stale/replay
handling and appropriately bounded history. Phase 15.3 should build the terminal
consumer with strict response/freshness/market attribution; 15.4 comparison and
15.5 final security/regression acceptance remain separate. No WebSocket/history
collector, full React live terminal, provider quorum, HIP-3/spot, multiple trading
engines, portfolio allocation, Docker, PostgreSQL, Actions or ML work is added.

## Complete changed-file list

```text
CODEBASE.md
backend/app/api/live_markets.py
backend/app/config.py
backend/app/main.py
backend/app/market_data/live_models.py
backend/app/market_data/live_observations.py
backend/tests/test_phase151_live_markets.py
docs/ARCHITECTURE.md
docs/HYPERLIQUID_INTEGRATION.md
docs/PHASE151_ACCEPTANCE.md
docs/ROADMAP.md
frontend/src/types/index.ts
```
