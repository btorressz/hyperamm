# Phase 15.5A — Integrity & Offline Acceptance

**IMPLEMENTED / CLOUD OFFLINE ACCEPTANCE PASS — DRAFT REVIEW.**
Genuine venue acceptance remains BLOCKED; macOS is NOT RUN. Phase 15 is not
complete. Do not merge automatically. No Phase 16/17 work is included.

## Git baseline and environment

- Repository: `https://github.com/btorressz/hyperamm`.
- Branch: `phase15/15-5a-integrity-offline-acceptance`.
- Exact fetched main baseline: **`e656a51c3d378f787281f6e4ba5d6ad020e48135`**.
- Final implementation/test commit: **`c85d8bd5513c37c5b5fd63e4755ac1a55e395f32`**.
  The subsequent evidence/documentation-only commit is identified as the delivery
  head in the draft PR; a tracked document cannot embed its own Git commit hash.
- GitHub independently verified Phase 15.4 PR **#53 merged**. Main was fetched
  again before delivery and remained the exact same SHA; no open concurrent PRs
  were returned on either review. Original working tree was clean; no user edits
  were discarded.
- Reviewed CODEBASE, Summary, CHANGELOG, ROADMAP, relevant Phase 15.1–15.4
  acceptance, docs/AGENTS and Audit Reports 1.0/2.0, then actual security,
  research/API/worker, frontend evidence/store/hook and browser harness modules.
- Execution date: October 17, 2026, America/Los_Angeles. Linux source timestamps
  and observer/event timestamps retain their independent UTC attribution.

Cloud: Debian GNU/Linux 13.6, Linux 6.18.55 x86_64/glibc 2.41, Python **3.12.14**,
Node **24.19.0**, npm **11.9.0**. FastAPI **0.143.3**, Starlette **1.8.0**,
Pydantic **2.14.1**, pytest **8.4.2**, pytest-asyncio **0.26.0**, AnyIO **4.15.1**,
httpx **0.28.1**, official SDK **0.24.0**, NumPy **2.5.4**, sklearn **1.9.1**,
Redis client **6.4.0**, fakeredis **2.40.0**, yfinance **1.7.0**.
Actual browser: system Chromium **151.0.7922.173**, Playwright **1.62.0**.
Actual ephemeral Redis server: **8.0.2**, bound to loopback with persistence off.
Resolved [versions](acceptance/phase155a/versions.json) and
[backend dependency snapshot](acceptance/phase155a/backend-dependencies.txt)
are evidence, not a newly imposed dependency lock.

## Implemented backend changes

1. Strict local peer/Host authority and browser-origin validation shared by HTTP
   and WS. Browser Origin must be same origin or explicitly configured local
   HTTP(S) origin. Default Vite localhost/127.0.0.1/[::1]:5173 works; unrelated
   localhost ports, null/non-HTTP origins, userinfo/path/invalid port, duplicate
   security headers and forwarding headers do not. In-process TestClient remains
   supported only through its existing synthetic peer boundary.
2. Local boundary runs before body admission. The existing body middleware now
   covers write methods, enforces 64 KiB declared/actual bounds, validates framing,
   coalesces tiny chunks and abandons disconnected bodies. No unbounded message
   list or parsing of a rejected oversized/foreign-origin body.
3. All API validation responses omit raw input/exception context, redact unsafe
   diagnostics and unknown field/key locations, and use no-store. Structured
   credential-bearing keys redact whole nested values. Comparison failure output
   and logs omit raw exception message/traceback and preserve no-store.
4. Strategy update API rejects unknown fields before lifecycle mutation; accepted
   data returns to the original StrategyConfig type. No domain schema, economic
   formula, authorization or valid strategy behavior was changed.

[Security findings](PHASE155A_SECURITY_FINDINGS.md) detail one HIGH local browser
boundary issue, six MEDIUM input/evidence issues and one LOW session issue. These
are verified synthetic defects, not claims of observed credential theft or trades.

## Implemented frontend changes

- Retained book/context evidence independently shows CURRENT / ELIGIBLE AT CAPTURE,
  STALE, HISTORICAL or UNAVAILABLE; historical deltas explicitly remain historical.
  Existing backend COMPARABLE/PARTIAL/NOT_COMPARABLE/UNAVAILABLE contracts remain
  authoritative. No stale number is described as confirmed live.
- Exact observed/research values and source timestamps remain distinct. Required
  PAPER metrics, source-value consistency and completeness partitions are checked;
  valid large relative output differences are no longer rejected by input bounds.
- Confidence explains partial metrics, missing evidence, source conventions,
  simulated model assumptions and unauthenticated client provenance. Hypothetical
  performance remains separate from observations.
- The request gate owns abort/generation retirement. Frozen objects detach from
  callers, retain a one-time transport age and advance expiry monotonically;
  clock rollback/new ticks cannot renew them. Research eviction clears an invalid
  selection. Old response, disconnect/reconnect, replacement, expiry and unmount
  cannot silently revive a retired capture.
- Markets/Simulation entry points and all other terminal flows remain intact;
  no terminal redesign, wire-state invention or strategy/research execution action
  was added to the comparison workspace.

## Executed validation — exact results

Historical Phase 15.4 numbers were references only. These are independent runs:

| Check | Result | Actually executed evidence |
| --- | --- | --- |
| Unchanged backend baseline, all declared extras | **PASS — 1649 passed, 0 failed/skipped**, 1 warning; 56.56s | [baseline log](acceptance/phase155a/backend-baseline.txt) |
| Unchanged frontend baseline | **PASS — 602 passed, 0 failed/skipped/cancelled**, 9.97534536s | [baseline summary](acceptance/phase155a/frontend-baseline.txt) |
| Baseline TypeScript / production build | **PASS / PASS**, build 1.85s | Executed before frontend edits |
| Final backend, `.[test,ml,redis,yahoo]` | **PASS — 1822 passed, 0 failed/skipped**, 1 warning; 61.63s | [final log](acceptance/phase155a/backend-final.txt) |
| New Phase 15.5A backend suites | **PASS — 173 passed, 0 failed/skipped**, 1 warning; 0.78s | [focused log](acceptance/phase155a/backend-focused.txt) |
| Final frontend | **PASS — 641 passed, 0 failed/skipped/cancelled**, 9.946965169s | [final output](acceptance/phase155a/frontend-final.txt) |
| Final TypeScript / production build | **PASS / PASS**, build 1.86s | tsc -b / Vite, no manifest/lock changes |
| pip check / compileall / whitespace | **PASS / PASS / PASS** | Actual commands exited 0 |
| Actual Chromium | **PASS — 28 workflows**, six sizes, **54 route/viewport checks**, **0 page exceptions**, 44.47s | [browser JSON](acceptance/phase155a/browser-results.json) |
| Actual local Redis | **PASS — seven checks**, 0 failed; 0.35s | [Redis JSON](acceptance/phase155a/redis-results.json) |
| Fresh test-extra-only complete backend | **PASS — 1821 passed, 0 failed, 1 skipped**, 1 warning; 57.47s | [normal-extra JSON](acceptance/phase155a/normal-extra-results.json) |
| Fresh test-extra-only original Redis lifespan suite × 10 | **PASS — 50 passed**, 0 failed/skipped across ten independent pytest processes | Same normal-extra JSON; five original tests per repeat |
| Genuine public SDK metadata | **BLOCKED — proxy CONNECT 403 Forbidden** | [actual attempt](acceptance/phase155a/cloud-attempts.txt) |
| macOS kernel/browser/SDK lifecycle | **NOT RUN** | Independent local gate; [exact commands](PHASE155A_MACOS_FALLBACK.md) |
| Signed TESTNET orders / mainnet | **NOT APPLICABLE** | Excluded by task; no signed orders sent |
| Phase 15.5B real streaming/provider soak | **NOT RUN / reserved for collaborator** | No changes to reserved modules |

Added **173 backend + 39 frontend** cases; every preexisting test/schema is retained
without weakened assertions or added skips. The sole fresh-normal-extra skip is
`test_offline_training_optional_import_and_real_coefficient_export` because
`sklearn` is absent in that intentionally test-only venv. The all-extra suite
executes and passes it. Fresh normal-extra versions: Redis client **8.1.0**,
fakeredis **2.40.0**, Starlette **1.8.0**, AnyIO **4.15.1**. This independently
rechecks A2-005 without attributing its historical race to a Redis client version.
No macOS or long-soak closure is claimed.

Existing non-failing notices: upstream Starlette/httpx TestClient deprecation,
headless Zustand storage notice, TanStack `use client` bundle directives and Vite
main-chunk advisory (about 602 kB minified). No warning was suppressed or assertion
changed to obtain a pass. Initial sandbox/setup and harness failures are recorded
in fallback; they are not counted as passing acceptance.

## Browser workflows and screenshots

The existing Phase 15.4 harness now accepts an optional extension; its original
assertions remain intact. The new Phase 15.5A extension reuses its genuine
DEMO/PAPER Uvicorn/Vite services, actual production comparison endpoint, existing
normalized native fixture server, normalizers/contracts and real Chromium.
Fixture notices distinguish these observations from genuine venue delivery.
No production fixture routes or image mocks were introduced.

Executed: no-result/disabled-source selection; actual BTC/ETH/SOL PAPER runs;
source/value/timestamp/difference/provenance checks; newer tick versus frozen
capture; stale context/fresh book; insufficient book depth; cross-market mismatch;
observer restart while POST is delayed; explicit resynchronization; captured source
expiry despite new publications; legacy missing assumptions; hostile origin and
forwarding HTTP access; real browser offline/online and component unmount while
POST is pending; visible 503/invalid-result behavior; all requested terminal pages;
desktop links/mobile drawer; unavailable provider and disabled observation states.
Only four explicit individual PAPER runs and comparison POSTs are recorded from
the browser. No strategy, order, kill, capital, optimizer or apply/deploy write is
performed by browser research. Backend Redis acceptance separately exercises the
manual kill path in its isolated PAPER runtime.

Route sweep: Dashboard, Markets (Operational / Live Intelligence / Comparison),
Simulation, Vault, Agents, Risk, Execution, Settings and Logs. Sizes:
**1920×1080, 1440×900, 1366×768, 1024×768, 768×900, 390×844**.
Assertions cover visible page content/navigation and no horizontal document
content overflow at each size. Tables retain their intended local scrolling.

Actually captured screenshots, inspected after capture:

- [market-comparison-1440.png](acceptance/phase155a/market-comparison-1440.png)
- [market-comparison-390.png](acceptance/phase155a/market-comparison-390.png)
- [live-markets-1440.png](acceptance/phase155a/live-markets-1440.png)
- [stale-evidence-1440.png](acceptance/phase155a/stale-evidence-1440.png)
- [simulation-1440.png](acceptance/phase155a/simulation-1440.png)
- Reused harness also captured [BTC](acceptance/phase155a/btc-comparison-1440.png),
  [legacy desktop](acceptance/phase155a/comparison-1440.png) and
  [legacy mobile](acceptance/phase155a/comparison-390.png) states in this run.

## Runtime and authority isolation

Seeded actual PAPER fills/positions, quotes/resting orders, ledger/accounting,
reservations/capital, configs/service identities, running/kill states and
FinalQuoteAuthorization are preserved through valid/invalid research and read-only
GETs. Cancellation retains worker capacity until actual completion and shutdown
drains the worker; comparisons cannot create SDK clients or execute research.
Real Redis accepts Pub/Sub/TTL/admission, degrades to research 503 during actual
server outage, preserves local kill, and recovers without clearing kill or changing
strategy. The original nested WebSocket teardown tests pass in both full suites
and ten additional fresh-normal-extra repeats.

## Remaining gates and final assessment

All feasible Cloud offline gates were attempted and completed. One public
SDK metadata call was attempted through the unchanged configured proxy and denied
with CONNECT 403; venue hosts are absent from the supported policy. This is not
an application test failure or genuine live acceptance. No restriction/TLS bypass,
credentials, VPN routing, Docker, PostgreSQL, Actions, new markets/curves, mainnet,
execution authority or autonomous trading was added.

Phase 15.5B's reserved live_streams/live_observations/live_history/live_stream_models,
live_market_streams API and live_provider_integrity/mappings modules are unchanged.
Its SDK lifecycle/REST/WS/reconnection/subscriptions/cleanup/provider integrity,
queue/history and permitted venue/soak work remains separate. No new defect in
those modules was proven here. Independent macOS acceptance remains NOT RUN;
[the fallback](PHASE155A_MACOS_FALLBACK.md) supplies exact commands, expected counts,
merge-gate context and how to report results.

**Phase 15.5A is ready for draft review with Cloud offline acceptance evidence.
External/macOS gates remain explicit. The entire Phase 15 is not accepted or complete.**
