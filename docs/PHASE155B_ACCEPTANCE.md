# Phase 15.5B — Live Stream Reliability, Provider Integrity & Integration Acceptance

**PASS — implemented and offline accepted for draft review. Genuine venue access:
BLOCKED. Independent macOS/local/Replit acceptance: NOT RUN. Phase 15 is not complete.**
The owner must reconcile 15.5A/15.5B and decide the combined audit disposition.

## Provenance and environment

Repository `btorressz/hyperamm`; branch
`phase15/15-5b-live-stream-integrity-acceptance`. Fetched latest main before changes;
GitHub independently confirmed PR #54 merged October 25, 2026. Exact baseline:
**`72596ffed757acbcfc6f61ef36376593b77964c1`**. Original checkout was clean.
Final tested implementation commit:
**`e68f12707f565955c6b0f25f165fdca343601a6a`**. Subsequent commits contain only
acceptance evidence/documentation; the exact delivery head is recorded in the
single draft PR (a tracked document cannot contain its own commit hash).

Executed October 29, 2026, America/Los_Angeles. Reviewed CODEBASE, Summary,
CHANGELOG, ROADMAP, Phase 15.1–15.4 and 15.5A acceptance/security/macOS fallback,
Audit Reports 1.0/2.0, docs/AGENTS and actual observer, official SDK, lifecycle,
normalizers, providers, history, API, runtime-isolation and React/browser modules.
Historical acceptance counts were not substituted for execution.

Linux 6.18.55 x86_64 / Debian GNU/Linux 13 / glibc 2.41; Python **3.12.14**,
Node **24.19.0**, npm **11.9.0**, official SDK **0.24.0**, Pydantic **2.14.1**,
FastAPI **0.142.2**, Starlette **1.7.0**, pytest **8.4.2**,
Chromium **151.0.7922.173**, Playwright **1.64.1**.
[All measured versions](acceptance/phase155b/versions.json).
No production dependency range or frontend lockfile changed.

## Independently executed results

| Check | Baseline | Final / classification |
| --- | --- | --- |
| Full backend, all declared extras | Initial: **1821 passed, 1 failed**, 83.78s, Pydantic 2.13.5. Accepted-version rerun: **1822 passed**, 72.84s | **PASS — 1916 passed, 0 failed/skipped**, 75.51s; one upstream warning |
| Frontend Node | **641 passed**, 23.94447038s | **PASS — 652 passed, 0 failed/skipped/cancelled**, 16.133580824s |
| TypeScript / production build | PASS / PASS | **PASS / PASS**, final Vite 3.04s |
| pip check / compileall / whitespace | PASS / PASS | **PASS / PASS / PASS** |
| Lifecycle/reconnect/shutdown/generation focused execution | NOT APPLICABLE | **PASS — 26 tests**, 3.32s XML suite duration |
| Provider/mapping/isolation/fresh import focused execution | NOT APPLICABLE | **PASS — 27 tests**, 1.552s XML suite duration |
| Full new Phase 15.5B cases | NOT APPLICABLE | **94 new backend and 11 new frontend cases** included in the full runs |
| New actual Chromium production-stream workflows | NOT APPLICABLE | **PASS — 6 workflows**, desktop/mobile, zero page errors; 12.317s |
| Reused Phase 15.5A Chromium workflows | Historical results only | **PASS — 28 workflows**, six viewports, 54 route/viewport checks, zero page errors; 48.16s |
| Reused source/terminal-independence Chromium | Historical results only | **PASS — 13 workflows**, six sizes, zero page/console errors; 17.85s |
| Offline bounded SDK traffic soak | NOT RUN historically for this milestone | **PASS — 30.2484s, 298 cycles**, detailed measurements below |
| Genuine SDK metadata | NOT RUN before this work | **BLOCKED — configured proxy CONNECT 403**, one attempt, 0.059s |
| Genuine venue WS/REST delivery/reconnect/soak | NOT RUN | **NOT RUN — blocked metadata prerequisite** |
| New actual Redis server acceptance | 15.5A historical: seven checks passed | **NOT RUN — binary absent; package-source setup blocked by proxy**. Full pytest Redis fixtures pass. |
| Independent macOS / developer local / Replit | NOT RUN | **NOT RUN** — no attached runtime for these platforms |
| Signed TESTNET/mainnet/order readiness | NOT APPLICABLE | **NOT APPLICABLE** — explicitly excluded |

Evidence: [backend initial baseline](acceptance/phase155b/backend-baseline-initial.txt),
[accepted-version baseline](acceptance/phase155b/backend-baseline.txt),
[backend final](acceptance/phase155b/backend-results.txt),
[frontend baseline](acceptance/phase155b/frontend-baseline.txt),
[frontend final](acceptance/phase155b/frontend-results.txt),
[typecheck](acceptance/phase155b/typecheck-results.txt),
[build](acceptance/phase155b/build-results.txt),
[lifecycle JSON](acceptance/phase155b/lifecycle-results.json),
[provider JSON](acceptance/phase155b/provider-results.json).

The initial generated-terminal-schema failure was independently reproduced on
unchanged main with Pydantic 2.13.5. Installing the previously accepted 2.14.1,
inside the existing declared range, restored the exact 1822-pass baseline. The
schema, generator and equality test were not modified. Reproduction should install
`.[test,ml,redis,yahoo]`, then explicitly `pydantic==2.14.1`; the broad dependency
range alone does not guarantee that older versions generate the checked-in schema.
[Setup/development failures](acceptance/phase155b/cloud-attempts.txt) are retained.
Existing Starlette/httpx deprecation, headless Zustand notice, TanStack directives
and Vite bundle-size advisory remain; no warning was suppressed.

## Production changes and reuse

Changed backend production files:

- `market_data/live_streams.py`: bounded callback traversal, scope/duplicate owner
  guards, explicit channel/receipt validation, retained rejected evidence, accurate
  degraded publication, safe REST barriers and isolated paced recovery, bounded
  SDK thread joins and cancellation-safe pool drain.
- `market_data/live_history.py`: per-market generation admission and context
  economic deduplication across reconnects, preserving existing gaps/retention.
- `references/live_provider_integrity.py`: degraded native health follows stream
  errors; disabled native source uses existing DISABLED vocabulary.
- `simulation/__init__.py`: lazy existing public exports resolve a verified
  standalone observation import cycle. No engine/configuration/economic change.

Changed React production files: `LiveMarketsView.tsx` and
`LiveProviderStatus.tsx`, solely to prevent cached HEALTHY native badges from
contradicting a newly DEGRADED stream. No layout or trading workflow redesign.

Reused unchanged contracts/services: `live_models`, `live_stream_models`,
`live_observations` strict Decimal/book/context helpers, `hyperliquid_metadata`
validation, existing adapter socket readiness, `perp_context` financial arithmetic,
`market_profiles` whitelist/precision, config and FastAPI lifespan ownership,
reference identities/roles/status/transport/mappings, existing GET/WS handlers,
React stores/hooks/history/freshness/socket/session controls, and Phase 15.5A
browser fixtures/workflows. No replacement WebSocket implementation or collector.

[Seven findings and severities](PHASE155B_SECURITY_FINDINGS.md) describe verified
defects, narrow hardening and evidence. One existing context rejection assertion
was strengthened to check retained evidence and DEGRADED delivery state instead
of deletion. Every original test remains; no added skips/xfails, removed cases,
weakened validation or unrelated generated-schema changes.

## SDK lifecycle, evidence and resource boundaries

Preserved one official public SDK owner and one serialized worker. Native
BTC/ETH/SOL each retain exactly `l2Book` and `activeAssetCtx` when listed. SDK
maps/index/precision are checked against native metadata. Disabled observations
open no clients. Acknowledgements are not economic observations. Partial opens,
partial subscriptions, HTTP/REST failures, socket refusal, repeated reconnects,
metadata delisting, cancellation during initialization/backoff/shutdown and cleanup
failure are exercised. Prior actual SDK compatibility tests still execute real
manager/ping threads with intercepted transport and verify six subscriptions,
six unsubscriptions and closed HTTP sessions; this remains offline compatibility.

Retired ingress/generations cannot publish or mutate counters/history. Failed
cleanup retains its owner and blocks replacement until a later close succeeds.
Individual SDK thread joins have finite deadlines. Synchronous socket/session
operations remain owned while draining if they outlast an asyncio response budget;
no force-killed-worker or universal cleanup guarantee is claimed. Repeated close
and cancelled shutdown readers preserve the retained drain task.

Malformed/wrong-market/channel/nested/oversized/nonfinite/extreme inputs, future/
stale/replayed books and same-time conflicts cannot overwrite accepted values.
Rejected delivery loses its channel proof; new valid recovery is required before
AVAILABLE. Source timestamps remain exchange L2 timestamps, context event time
remains unknown, and receipt/publication remain separate. Polling/publication
never adds economic history or retimes accepted L2 evidence. Histories remain
bounded per market with eviction counts, explicit gaps and no continuity claim.

Slow browser queues terminate without blocking other markets and retain admission
until the socket owner releases them. Tests cover capacity exhaustion, failed
accept/send, disconnect, cancellation and shutdown joining child tasks. REST
recovery failure is isolated per market, with a minimum 250 ms retry interval.
One Hyperliquid source group includes midpoint/oracle/mark; context remains
DEGRADED when recently received because upstream event time is unverified.
External provider mappings remain disabled; RedStone primary/fallback are one
provider and no independent usable external consensus is claimed. UNAVAILABLE is
represented by existing connection/mapping/error contracts; ProviderStatus retains
its existing five permitted values rather than adding incompatible vocabulary.

## Executed offline soak

[Actual report](acceptance/phase155b/soak-results.json): requested 30 seconds,
**30.2484 seconds executed**, **298 completed reconnect cycles**, **299 fake SDK
connections**, maximum observed per-market ingress queue **8**, **2682 dropped**
events, **8046 rejected** events, **894 retired callback attempts**. Each market
retained 32 history points and recorded 596 gaps. After shutdown: **0 subscribers,
0 owned threads, 0 owned tasks, 0 leaked/uncertain fake SDK resources**.
Drops/rejections are intentional exercised pressure/replay paths, not missing
counters or fabricated continuity. This is a short local offline soak, not a
long-running or genuine venue soak. Runner bounds: 0.1–300 seconds and 1–1000 cycles.

## Actual Chromium evidence

New harness: real Chromium → normal local HTTP/WS security → unchanged production
routes → actual LiveMarketStreamService → deterministic fake SDK callbacks.
It verifies all three markets, actual server generation replacement, retired client
closure, retained DEGRADED provider state, real browser offline/online and subscriber
release on navigation. Desktop **1440×900**, mobile **390×844**. Fixture notices
are visible; screenshots were opened and inspected, not synthesized.

- [BTC overview](acceptance/phase155b/fixture-btc-overview-desktop.png)
- [ETH book](acceptance/phase155b/fixture-eth-orderbook-desktop.png)
- [SOL context](acceptance/phase155b/fixture-sol-perpetual-desktop.png)
- [Degraded native provider](acceptance/phase155b/fixture-degraded-provider-desktop.png)
- [Disconnected browser](acceptance/phase155b/fixture-disconnected-desktop.png)
- [Mobile intelligence](acceptance/phase155b/fixture-live-intelligence-mobile.png)
- [New report](acceptance/phase155b/browser-results.json)
- [28 reused workflows / six sizes / 54 route checks](acceptance/phase155b/regression/browser-results.json)

The combined 47 workflows include a separate unchanged Phase 15.3 harness run
[verifying terminal independence](acceptance/phase155b/terminal-independence/browser-results.json).
Reused workflows verify frozen comparison does not recalculate on new live ticks,
source expiry, historic/gap/missing evidence, no operational snapshot at first
mount, delayed responses, PAPER/runtime isolation, exact origin/forwarding rejection,
all terminal routes and mobile navigation. Sizes: 1920/1440/1366/1024/768/390 px.
Playwright's async wait behavior was independently diagnosed; this harness checks
resolved booleans explicitly for both new and reused workflows.

## External gates and combined audit disposition

[External acceptance and runnable fallback](PHASE155B_EXTERNAL_ACCEPTANCE.md)
separate the one blocked genuine request from fixture tests. No alternate venue
route or endpoint, VPN, geographic evasion, TLS change, signing key or order was
used. Local/Replit/macOS outcomes remain NOT RUN until actual output is reviewed.
The new real Redis setup attempt was blocked at package sources and never ran a
Redis test; historical 15.5A Redis evidence is preserved as historical only.

PAPER seeded isolation and original full regressions preserve strategy economics,
reference consensus, risk/firewall, FinalQuoteAuthorization, order submission/
cancellation authority, active operational market, inventory, capital reservations,
accounting, manual kill and validated research configuration. No new markets,
AMM curves, Pyth, mainnet, autonomous authority, Docker, PostgreSQL, Actions,
historical replay engine, Phase 16 or Phase 17 work is introduced.

**Ready for the combined Phase 15.5 review with offline evidence.** Before any
unqualified final Phase 15 acceptance, reconcile 15.5A security findings, these
stream/provider findings, combined regressions/browser/Redis, native SDK lifecycle,
independent macOS and actual permitted venue delivery/long soak, plus remaining
external/signed TESTNET gates. The project owner decides disposition; keep this
single PR Draft and unmerged.
