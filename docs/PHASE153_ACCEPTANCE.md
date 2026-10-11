# Phase 15.3 — BTC/ETH/SOL Live Markets Terminal UX

**IMPLEMENTED / FIXTURE ACCEPTED. Draft delivery only; do not merge.** Phase 15
is not complete. Genuine external venue acceptance remains open.

## Verified baseline and setup

Repository `btorressz/hyperamm`; freshly fetched `origin/main` before editing:
**4244e8d2713a411dda7487414b7ca46a542ab266**. GitHub independently confirmed
PRs #49, #50 and #51 merged. The original working tree was clean. Branch:
`phase15/15-3-live-markets-terminal`; main was not edited.

Reviewed CODEBASE, Architecture, Roadmap, Terminal, Hyperliquid Integration,
Reference Integrity and Phase 14.6/15.1/15.2 acceptance, alongside the existing
pages, stores, API/types, financial/freshness utilities, chart/socket lifecycle,
provider panels and Node/Chromium harnesses. Dependencies use the existing lock
and chart package; no new production dependency or runtime is introduced.

## Workspace and authority boundary

Markets defaults to **Operational Market** on each page mount. Its existing JSX,
PriceLiquidityChart, operational OrderBook, context and reference panels remain
inside a small OperationalMarketsView. The pressed-button segmented control
opens a separate Live Market Intelligence workspace. App narrowly permits
Markets to render with `t=null`; other trading-dependent pages retain their
existing readiness rules. A read-only socket never changes global terminal,
header, signing, kill-switch or trading readiness.

Live selection defaults to BTC, supports exactly BTC/ETH/SOL, and lives only in a
nonpersistent Zustand store. It does not import research/terminal stores or call
strategy, research approval, start, stop, risk or execution mutations. Operational
ETH, completed SOL PAPER research and live BTC can coexist. Selection increments
an epoch, clears prior displayed evidence, aborts HTTP work, closes the previous
socket and rejects old-market completions. Returning to Markets requires fresh
observations; raw market evidence is never persisted across restarts.

Three overview cards use bounded 15-second GET queries, not three extra sockets.
The selected card uses accepted stream evidence. Missing values stay unavailable.
Native L2 book rows are typed observation rows, never operational MarketState
casts. Actual asks/bids, cumulative base size, BBO/mid/spread/bps, source time,
age and truncation remain attributable to the selected asset. Retained stale
levels are explicitly STALE — LAST OBSERVED and lose live side coloring.

Context displays reported mark/oracle/provider midpoint, raw venue funding,
base OI versus quote notional, premium and same-acquisition backend basis values.
Missing or stale context never borrows an L2 midpoint or old mark. Native context
has **unknown event time**; receipt freshness is not exchange-event verification.
Financial Decimal strings remain unchanged in wire/store state; finite display
and chart conversions preserve sensible reported price/native size precision.

Provider rows come from the independent per-market references endpoint. Native
mid/oracle/mark share one Hyperliquid source group. Health and REST/bootstrap
status never confirm streaming. Provider rows age independently even if a newer
selected book is fresh. RedStone primary/fallback share one identity; Kraken,
CoinGecko and Yahoo retain actual disabled/unconfigured evidence. Authority stays
NONE, consensus null and independent usable external count zero.

## Validation, identity and lifecycle

One controller owns one selected-market browser socket at
`/ws/live-markets/{market}`, using same-origin WS/WSS. It reuses the operational
socket ownership principle without accessing operational state. StrictMode
replacement closes the prior owner, aborts requests and cancels listeners/timers.
Browser socket opens alone never confirm evidence.

Incoming phase152-v1 frames validate contract, exact market attribution throughout
components, observer UUID, generation, increasing publication sequence, emission
and component timestamps, actual enum/status/metadata fields, bounded depth and
financial Decimal strings. Unknown contracts, malformed/nonfinite values,
future/invalid dates, crossed/unsorted books, mismatched context event time and
replays cannot renew accepted evidence. Publication sequence is labeled as
publication ordering, never exchange sequence; its baseline survives reconnects
within the same observer/generation.

Disconnect, timeout, visibility/offline pause and overflow retire current claims.
Observer/generation replacement clears current evidence and obtains a validated
HTTP boundary before stream restoration. Confirmed old observers and older
generations cannot return. An unconfirmed observer frame does not permanently
retire the genuine observer. New-generation notification rejects an older HTTP
generation rather than merging components. Full immutable snapshots replace
components; books/context are never merged across generations.

Backoff is bounded at 1/2/4/8/16/30 seconds with six automatic retries. A stable
available stream lasting at least 30 seconds can reset the retry budget. Unsupported
1008 and terminal errors stop retries until explicit action; unavailable/disabled
HTTP 200 evidence remains meaningful. 1013 performs fresh snapshot resynchronization.
Snapshot deadline is 10 seconds, publication watchdog 30 seconds; malformed frames
do not reset it. Page exit closes with code 1000 and removes all owned resources.

## Targeted additive backend correction

Phase 15.2 HTTP snapshots/status had no observer identity and did not publish
configured component freshness budgets. A browser could not reliably bind a
snapshot to an observer restart or honor nondefault stale limits. The status now
adds `observer_instance_id`, `evaluated_at`, `l2_stale_after_seconds`,
`perp_stale_after_seconds`, `metadata_stale_after_seconds`. Existing fields,
routes/version and economics remain intact. Envelope validation binds its observer
to the nested status as well as the existing generation/market checks.

Actual service snapshot construction fills these fields even when disabled.
Finite bounded budgets remain backend configuration; no defaults or network
activation changed. HTTP transit/evaluation age and elapsed monotonic browser
time conservatively advance reported ages, never renew source timestamps or
reduce reported age. Clock-uncertain/old evaluations fail closed. Metadata,
L2 exchange-source freshness and context receipt freshness remain separate.

Six new backend cases verify actual GET/status/WS/history identity boundaries for
all three markets, custom budgets/aging/restart, and actual-runtime browsing
isolation in normal/kill fixtures. The unchanged Phase 15.2 seeded tests additionally
preserve resting orders, PAPER fills/position, authorization, accounting/ledger/
capital reservations and all service/configuration identities through reconnect.

## Chart and retained history

Uses existing Lightweight Charts only, with owned chart/ResizeObserver cleanup,
configuration reconciliation, bounded GET history and zoom preserved across refresh.
L2 midpoint/bid/ask use genuine source times; optional mark/oracle use a separate
receipt-time view with explicit event-time limitation. Latest actual observation
within each whole-second bucket wins; no fake sequence timestamps, candles,
forward fills, interpolation or PnL are created.

Series split at generations, retired identities, null/unavailable values,
regressing chronology and intervals beyond the backend component freshness limit.
Because the history contract reports a global gap count without gap positions,
responses with any known gap render isolated points throughout. Visual connections
between retained observations are not certified uninterrupted exchange history.
History is bounded to presets 100/300/600/1000 and refreshed every five seconds;
provider queries refresh every 15 seconds. Old keys/requests are discarded on
selection/boundary change. The inspection table retains null component fields,
source/receipt time, generation/observer, retained/returned/evicted/gap counts,
receipt coverage and **continuous_history_verified=false**.

## Executed checks

| Check | Actual final result |
| --- | --- |
| Unchanged frontend baseline | 458 passed, 0 failed/skipped/cancelled; 15.325870774 s |
| Unchanged backend baseline | 1547 passed, 1 failed, 1 warning; 245.56 s; see below |
| Full frontend `npm test` | **539 passed**, 0 failed/skipped/cancelled; **21.586590275 s** |
| Full backend `python -m pytest -q` | **1554 passed**, 0 failed/skipped, 1 warning; **61.65 s** |
| New backend focused cases (initial run) | 6 passed, 1 warning; 2.57 s |
| TypeScript | PASS |
| Production build | PASS; 2.37 s |
| pip check / compileall / diff whitespace | PASS |
| Actual Chromium | **13 workflows, 6 viewports**, 0 page exceptions / unexpected console errors; **21.65 s** |

All 458 existing frontend and 1548 existing backend tests remain present and pass
in the final runs; 81 frontend and six backend cases are added. No existing test,
schema, generator, assertion or route authority was removed/weakened/skipped.

Clean-base backend failed the existing
`test_events_bounded_deduplicated_filtered_and_redacted`: a generated SHA event ID
coincidentally contained literal `abc123`, which the test searches across the
entire serialized response. The message fields were redacted. This pre-existing
probabilistic assertion remains unchanged; the final full run passes it. Earlier
root-directory collection errors and a restricted-sandbox run interrupted during
setup are not passing acceptance. Correct checks use backend cwd and permitted
loopback networking. The clean base was separately checked in a detached worktree.

One upstream Starlette/httpx TestClient warning remains. Frontend retains its
headless Zustand storage notice, TanStack module-directive warnings and the Vite
500 kB main-chunk advisory (about 573 kB minified). Python 3.12.14, Node 24.19.0,
Playwright 1.58.0 and system Chromium were used. npm ci completed with the existing
lock. Local environments/caches/logs stay under ignored `work/`.

## Actual browser acceptance and artifacts

`browser-phase153.py` owns loopback Uvicorn/Vite process groups and an actual
Chromium session. Production entrypoint/configuration defaults are untouched.
A separate test-only `phase153_browser_backend.py` injects Pydantic-serialized
live fixtures while retaining the genuine DEMO/PAPER operational runtime. Native
browser WebSockets carry normalized frames; no Playwright WebSocket monkeypatch
or venue connection is used in final acceptance. Test controls exist only when
that explicit test module is launched and are not production routes.

Fixture JSON is reproducible via `phase153-fixtures.py` using the existing
injected FakeClients seam and actual normalizers/models. It is labeled fixture
evidence throughout. A supported browser-only delayed HTTP interception proves
old BTC retirement while selecting ETH. The one browser POST is an authorized
real isolated SOL PAPER run performed **before** live browsing; there are **zero
new live-workspace mutations**. Test-server controls are separate harness calls.

Workflows cover actual disabled defaults, Operational/Live switching, BTC book/
chart/context/providers, BTC→ETH→SOL→BTC selection, delayed old-market HTTP,
real socket 1013 closure/reconnect, observer restart, separate generation change,
fresh REST bootstrap without confirmed streaming, independently stale L2/current
context, HTTP 200 unavailable, navigation cleanup and one-socket StrictMode return,
unchanged operational strategy/order/kill/ledger/signing and completed research
state, and first mount without an operational terminal snapshot.

Actual viewports: 1920×1080, 1440×900, 1366×768, 1024×768, 768×900 and 390×844.
No document overflow; chart width adjusts, pressed selectors remain usable and
book/provider/history tables scroll locally. Desktop chart/book use a grid;
tablet stacks; mobile uses one column. Status/error text stays visible.

[Compact browser report](acceptance/phase153/browser-results.json) and six useful
screenshots are retained under `docs/acceptance/phase153`: BTC/ETH/SOL desktop,
mobile, actual disabled and fixture reconnect. Active screenshots carry the
**DETERMINISTIC FIXTURE ACCEPTANCE · NOT LIVE VENUE DATA** banner. Earlier phase
acceptance artifacts are preserved.

Interim Chromium runs exposed the unbound browser clearTimeout invocation; the
implementation now cancels through a bound wrapper. Playwright WebSocket routing
also produced tool-specific close-race exceptions and incompatible async fixture
callback handling. Those runs are not claimed as acceptance. Final tests use
native loopback WebSockets and server subscription counts, with zero exceptions.

## Files enhanced, added and reused

Enhanced: `frontend/src/pages/Markets.tsx`, `App.tsx`, `api/client.ts`,
`types/index.ts`, `utils/format.ts`, `utils/freshness.ts`, `tests/run.cjs`;
`backend/app/market_data/live_stream_models.py`, `live_streams.py`; CODEBASE,
Architecture, Roadmap and Terminal docs.

Added frontend: `components/markets/LiveMarketsView.tsx`, LiveMarketSelector,
LiveMarketOverview, LiveMarketChart, LiveMarketOrderBook, LivePerpMetrics,
LiveProviderStatus, LiveMarketConnection, LiveMarketHistory; `hooks/useLiveMarket.ts`,
`useLiveMarketHistory.ts`; `stores/liveMarkets.ts`; `utils/liveMarketEvidence.ts`,
`liveMarketSocket.ts`, `liveMarketHistory.ts`; `phase153.css`.

Added validation: four `phase153-live-*.test.cjs` suites, shared test helpers,
fixture generator/JSON, native browser server/harness,
`backend/tests/test_phase153_live_terminal_acceptance.py`, this acceptance report
and compact browser artifacts. No new production execution route or dependency.

Reused: typed Phase 15.1/15.2 GET functions/contracts, Panel/Metrics/StatusBanner/
Empty/Badge, existing financial presentation, operational views unchanged,
HistoryChart lifecycle/gap practices, terminal socket ownership and bounded-history
patterns, provider panel terminology, existing Zustand/TanStack/Lightweight Charts
and Node/Python Chromium tooling. Research selector mutations and operational
stores/consensus/order/chart data are deliberately not reused for live evidence.

## External limitations and next phases

Genuine Hyperliquid metadata, BTC/ETH/SOL native live delivery/source times,
reconnect/rate-limit/cleanup/soak and external providers are **NOT RUN / BLOCKED**.
The enforced managed network policy excludes `api.hyperliquid.xyz` and grants no
VPN/TCP venue access. No denied venue request, TLS disablement, geographic
circumvention, signing or automatic live activation was attempted.

Known gates: probabilistic legacy redaction test, existing bundle advisory,
network-permitted genuine venue/Mac acceptance, external collector configuration,
real Redis, signed TESTNET and long soak. Observational fixture acceptance does
not close any of these gates or certify trading. Phase 15.4 must implement actual
live-versus-PAPER comparison with provenance; 15.5 retains final security/regression
and external acceptance closure. No portfolio/parallel trading, custody, new
oracle, Docker, PostgreSQL, Actions, `.github/` or merge is introduced.
