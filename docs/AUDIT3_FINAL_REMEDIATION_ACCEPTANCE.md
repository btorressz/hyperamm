# Audit 3.0 final remediation acceptance

## Executive summary

Audit base `c817a969bd5b7c2850eaad3eb76276ebd39b16ff`, fetched from `origin/main` before editing. Implementation commit `1dfc3b783953c7bc0d873bca047298deceb8509a`. Acceptance ran on Linux with local DEMO market data, PAPER execution and generated historical fixtures.

The changes close the liquidity shock feasibility gap, complete stale perpetual preflight handling, restore Historical Replay browser coverage and improve access to existing financial evidence. The dependency audit found a new advisory in the development dependency tree. See the [original Audit 3.0](../AUDIT_REPORT_3.0.md), [Audit 2.0](../AUDIT_REPORT_2.0.md) and [Audit 1.0](../AUDIT_REPORT_1.0.md).

**Conditional PASS** for read-only Phase 18.0/18.1 design and market discovery within the tested local research scope. The development-tree advisory and external gates remain open.

## Prior PR verification

| PR and merge | Reviewed | Independent result |
| --- | --- | --- |
| [#80](https://github.com/btorressz/hyperamm/pull/80) `bac4225` | Native portfolio risk and compact receipts, exact capital, chart clocks/extrema, shared worker, frontend guards and documented limits. | **PASS**. Native portfolio tests, six browser stresses, transport/authority checks and five viewports passed. |
| [#81](https://github.com/btorressz/hyperamm/pull/81) `c05ab0b` | Eight findings, baseline counterexamples, historical crosswalks and scope. | Reviewed the merged audit and reran the original SOL stress condition against the fetched base and implementation. |
| [#82](https://github.com/btorressz/hyperamm/pull/82) `9351683` | Typed fill provenance, offline/inference freshness, terminal schema, Vite lockfile and tests. | A3-001 and A3-003 checks pass. Original direct Vite advisories are absent. Current dev audit flags a new transitive advisory. [Prior acceptance](AUDIT3_SECURITY_EVIDENCE_ACCEPTANCE.md) |
| [#83](https://github.com/btorressz/hyperamm/pull/83) `7dc3d2b` | Runtime preflight, native-only precision, Kraken transport, targeted tests and partial accessibility changes. | The merged preflight test still returned 500 and required a correction. Unsupported instruments and quiet heartbeat behavior passed independently. The target accessibility states passed current Chromium measurements. [Prior handoff](AUDIT3_CHATGPT_PATCH_REVIEW.md) |

The pre-change frontend clean install resolved Vite 7.3.8 and passed typecheck, build and 788 tests. Known install/build notices and warnings include TanStack Query's ignored client directives, a chunk over 500 kB and the test DOM's unavailable Zustand storage. The pre-change #82/#83 focused tests produced 54 passes and one failure in the stale-context test. The Replay browser timed out on the initial studio locator with zero completed workflows. The baseline axe scan found five mobile scroll-focus failures. Registry audit connectivity and Git fetch succeeded. Python optional ML and Redis clients were installed into an isolated dependency directory. Local Chromium was available. The physical Redis 7.4.11 binary was built from its upstream Git tag for this run.

## Finding closure

| Finding | Disposition | Current evidence |
| --- | --- | --- |
| A3-001 | **CLOSED, verified** | Actual baseline and modeled crossing PAPER fills keep their simulated labels through telemetry and offline dataset construction. Explicit TESTNET fixtures with a simulated-looking text prefix remain nonsimulated. Legacy PAPER serialization, accounting and fill identities match frozen regressions. |
| A3-002 | **CLOSED** | The actual route returns bounded 422 for the stale source. Existing config, lifecycle READY, and final authorization survive the failure. Cancellation and invalidation spies record zero calls. Fresh configuration succeeds. The existing missing-context static preflight remains usable and grants no quote permission. |
| A3-003 | **CLOSED, verified** | Book, perpetual and reference source timestamps, inclusive freshness, future/missing evidence, offline/inference as-of checks and fresh recovery pass. Predictive outputs remain SHADOW only. The optional estimator export test ran with scikit-learn. |
| A3-004 | **CLOSED for native-only fail-closed behavior** | Native boundary asset 9,999 normalizes with native decimals, BID down, ASK up and size down. Negative, spot/builder ranges and non-integer metadata fail before request authorization, SDK submission or order registration. Existing concrete-request wire authority tests pass. |
| A3-005 | **CLOSED** | Preview, direct stress and terminal STRESS reject impossible SOL depth with 422 and zero engine calls. Corrected depth executes both native legs. Quantum, one-sided, both-sided and elapsed recovery tests pass. |
| A3-006 | **CLOSED within measured scope** | Zero automated violations across 32 route/viewport checks and Chromium 200% zoom. Measured small-text minimum 6.71:1, keyboard scroll and inspected screenshots. |
| A3-007 | **CLOSED for the fixture-proven Kraken control path** | Repeated heartbeat frames preserve the exact ticker, source/receipt times and version. The source ages to STALE, leaves quorum and recovers on the next ticker. Malformed heartbeat, unknown message, subscription rejection/resubscribe and shutdown are exercised. |
| A3-008 | **CLOSED for the original five Vite advisories** | Vite 7.3.8, clean install. The current audit still reports four high-severity entries rooted in one newly reported development dependency advisory. The production dependency audit reports zero. |

The new development audit advisory is `GHSA-fc5q-39xc-vjpf` in picomatch 4.0.7. npm also reports the transitive findings through fdir, tinyglobby and Vite. The registry served picomatch 4.0.7 as latest and returned 404 for 4.0.8. Vite 7.3.8 was the latest available 7.x release. The audit suggests a major downgrade outside the accepted 7.x line. Lockfiles and manifests retain the already-remediated Vite version. Both audits ran against the same install. [Advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)

## Liquidity depth admission

On the fetched base, SOL with size precision 2, both depth multipliers `0.000001` and spread `3` passed preview. The native service started one SOL baseline run, then failed with ten positive-level validation errors while building the shocked frame. On the implementation, preview and both native entry points return the bounded `LIQUIDITY_DEPTH_PRECISION` 422. The response identifies SOL, BID and the two-decimal precision. Correcting the multipliers to `0.005` runs one baseline and one stressed leg. Invalid requests in the route test make zero native engine calls and preserve operational state.

The shared size generator produces the same five sizes per side as the native DEMO scenario. Admission evaluates each selected market across the actual onset and duration using the same STEP_WINDOW or LINEAR_TO_BASELINE strength and the same `quantize_size` call as the transformer. The transformer shares the positive-quantity check. Preview performs no engine work or full dataset construction. Direct and terminal requests check after admission and before baseline generation or execution, and a failed request releases the worker. No executable depth is invented.

Boundary tests use native BTC/ETH/SOL precision (5/4/2), equal, below and above the first size quantum, one- and both-side collapse, an 18-decimal multiplier, shallow baseline frames inside and outside the shock, and an unselected market. Independent base-to-implementation parity compared 39 market–scenario datasets and all six completed native stress types. The request, scenario, result, market dataset/run/result and both accounting fingerprints matched byte for byte. The digest of the comparison data is `af77b2da228c399f06089811cfbda82b9e2b371a51d41fdfdbf703487fae812e`.

## Runtime acceptance

The stale-context snapshot raises a typed `RuntimeError` subclass before the reference policy sees the inputs. Runtime maps that specific unavailable/stale evidence to the existing configuration feasibility response. The merged `ValueError` handler alone could not catch it. The route retains its public diagnostic sanitizer and returns the exact current reason `perpetual market context is stale`. The failure does not enter the staged runtime transition.

Native precision acceptance corrects a legacy regression test whose spot expectations predated the #83 native-only contract. Every supported size precision is exercised on native boundaries, and the guarded adapter rejects the unsupported cases before checking request authority or invoking the fixture SDK. No wallet or venue credentials are needed.

The Kraken experiment uses a controlled clock and actual async provider transport loop. Age progresses from 0 to 1,000, 2,000, 3,000 and 6,000 ms across heartbeat traffic. The eligible quorum count falls from three to two only when the ticker ages out and returns to three after a new ticker. Subscription rejection opens a second fixture connection and shutdown closes it.

## Browser acceptance

Chromium **151.0.7922.173**, Playwright **1.65.2**, local HTTP and real application routes. The Replay repair now enters the accessible **Historical replay** workspace from **Simulation research workspaces** and returns to **Scenario & optimization** before invoking the original controls. Remounts explicitly reenter Replay. Diagnostics are checked by role and accessible wording, with actual 429 and structured 422 assertions on the wire, including `NO_VIABLE_FRAMES`. No financial, provenance, chart, worker or retirement assertion was removed. The browser exposed another replay defect where every failed terminal reconnect retired independent REST work. Replay now retires on changes to accepted connectivity, process or session identity. Repeated attempts while disconnected leave valid REST evidence usable.

| Harness | Actual result |
| --- | --- |
| Phase 16.4.1 | **16 workflows PASS** in 29.304 s, zero page errors or unexpected console errors. Fixture-only replay verified baseline and modeled results, independent segments, positive partial fills, accounting consistency, original charts, 422 invalid history, 429 busy, 503 disabled storage, process restart, retirement and scenario/Vault navigation. Uvicorn logged complete startup and shutdown for both processes. |
| Phase 16.5C.2 with 16.5D/16.6A/C/D checks | **29 workflows PASS** in 207.119 s, zero page errors or unexpected console/network failures. Actual Replay, Comparison, Scenario, optimizer, Research Vault, restart and 1,000-frame workflows. Induced 4xx/5xx, connection faults and malformed result probes retain their expected outcome. |
| Phase 17.6 with Audit 3.0 probes | **22 workflows PASS**, **60 native engine invocations**, five viewports, zero page or unexpected console errors. Expected fault entries were 422, 429, 500 and connection refused. Valid custom SOL stress and manual retry exercised the two native legs. The failed preview ran zero engines. Editing cleared completed evidence. Maximum observed request and response were 23,116 and 32,246 bytes, respectively. The official SDK metadata catalog reported EXCHANGE_VERIFIED for BTC/ETH/SOL, while strategy execution used DEMO/PAPER. |
| Accessibility harness | **32 route/viewport checks plus actual 200% zoom**, zero ruleset violations, page errors or console errors. The live local UI workflow included operational Markets, saving and restoring a valid AMM setting over HTTP, and the Risk and Agent evidence views. |

Chromium observed 14 successful replay POSTs, one each of 422, 429 and deliberate restart-time 500, and two successful native Scenario/optimizer POSTs. The disabled-storage catalog produced 503. Four deliberate offline-terminal WebSocket handshake responses (403) and four deliberate HTTP fault console messages were expected.

## Accessibility measurements

Axe-core **4.11.1** with tags `wcag2a`, `wcag2aa`, `wcag21a` and `wcag21aa`. Viewports were **1920×1080, 1440×1000, 1024×768, 768×900 and 390×844**. Chromium read the computed foreground, font size and underlying solid background layers for the affected small text. The acceptance script compares relative luminance to the WCAG 4.5:1 requirement. Retained agent events use a named focusable scroll region around the semantic ordered list. Financial tables scroll with their headers and values in intact columns.

| Small text measured | Foreground / effective background | Minimum ratio |
| --- | --- | --- |
| Risk small label | `#a8bed0` / `#0a1420` | 9.65:1 |
| Risk values’ accompanying labels | `#8aa2b8` / `#0d1925` | 6.71:1 |
| Risk Firewall labels | `#8aa2b8` / `#0d1925` | 6.71:1 |
| Reference source column headings | `#8aa2b8` / `#0a1420` | 7.00:1 |
| Strategy gauge, inventory and perp labels | `#a6bbce` / `#0a1420` | 9.37:1 |
| Agent event timestamps | `#8aa2b8` / `#0a1420` | 7.00:1 |

Chromium’s native Appearance → Page zoom control changed 1440×1000 at DPR 1 to 720×500 CSS at DPR 2. The document width remained 720 CSS px. The zoomed Pages button measured **13.58:1** and reference headings measured **7.00:1**.
The reference table was reached in **3 Tabs** from page content and responded to ArrowRight. The named event region was reached in **11 Tabs** and responded to ArrowDown. Both showed a two-pixel focus outline. Chromium exposed the event list and listitems inside the region. The desktop/mobile portfolio pass measured **127 financial cells per viewport** on one visual line each, including `−1,422.280324 USDC` in the negative case. Zero, explicit unavailable values, grouped long prices, notionals and currency units were exercised across Portfolio, Risk and historical comparison.

Twelve fresh captures were visually inspected. Wide/tablet layouts, financial tokens, alert text and provenance were legible in the shown regions. The narrow captures show the initial horizontal scroll position where applicable.

| Capture | Route and viewport | Inspected state |
| --- | --- | --- |
| [risk-1920.png](acceptance/audit3-final/risk-1920.png) | `#/risk` · 1920×1080 | Reference prices, timestamps and firewall side by side. |
| [risk-1440.png](acceptance/audit3-final/risk-1440.png) | `#/risk` · 1440×1000 | Retained reference evidence and risk/authorization metrics. |
| [risk-1024.png](acceptance/audit3-final/risk-1024.png) | `#/risk` · 1024×768 | Stacked panels and a horizontally scrollable source table. |
| [risk-768.png](acceptance/audit3-final/risk-768.png) | `#/risk` · 768×900 | Tablet navigation and source freshness beside intact prices. |
| [risk-390.png](acceptance/audit3-final/risk-390.png) | `#/risk` · 390×844 | Mobile risk and source prices. The table scrolls to remaining columns. |
| [agents-1440.png](acceptance/audit3-final/agents-1440.png) | `#/agents` · 1440×1000 | Retained events, times and diagnostic reasons. |
| [agents-390.png](acceptance/audit3-final/agents-390.png) | `#/agents` · 390×844 | Scrollable event list, reasons and disclosure text. |
| [risk-zoom-200.png](acceptance/audit3-final/risk-zoom-200.png) | `#/risk` · 720×500 CSS at 200% | Enlarged reference rows and risk panel. The 1280×633 browser surface capture is a viewport excerpt. |
| [sol-precision-390.png](acceptance/audit3-final/sol-precision-390.png) | `#/portfolio-research` · 390×844 | Readable SOL precision alert and unavailable submission controls after 422. |
| [sol-stress-390.png](acceptance/audit3-final/sol-stress-390.png) | `#/portfolio-research` · 390×844 | Corrected SOL comparison with intact headers, grouped digits, zero and USDC units. Remaining columns scroll into view. |
| [fixture-modeled-gap-1440.png](acceptance/audit3-final/fixture-modeled-gap-1440.png) | `#/simulation · Historical replay` · 1440×900 | Full page with separate PAPER segments, declared gap, retained chart/L2, evidence and generated fixture label. |
| [metrics-390.png](acceptance/audit3-final/metrics-390.png) | `#/simulation · Scenario vs historical` · 390×844 | Mobile locator capture of separate PAPER metrics and explicit eligibility/provenance. |

Axe results cover the rendered states. Incomplete automated results such as chart/gradient checks need manual review. The keyboard and inspected screenshot evidence covers the named elements shown here. Platform screen readers and equivalent chart narratives were NOT RUN.

## Regression evidence

| Command or check | Result |
| --- | --- |
| Focused Python suites | **1,196 passed, 0 failed or skipped** in 487.04 s. Includes audit evidence, liquidity precision, execution, AMM/quote normalization, perpetual/agent/reference paths, accounting, replay, six stresses, worker, HTTP and WebSocket/Redis suites. |
| Full `cd backend && python -m pytest -q -rs --tb=short` | **3,373 passed, 0 failed or skipped** in 791.44 s. The optional scikit-learn coefficient-export case ran. |
| `npm ci` and `npm ls vite` | PASS, 27 packages and Vite 7.3.8. |
| `npm audit` | Four high-severity entries tracing to the new picomatch dev dependency advisory. `npm audit --omit=dev` reports zero. |
| `npm run typecheck` | PASS. |
| `npm run build` | PASS. Existing TanStack client directive and large-chunk warnings. |
| `npm test` | **789 passed, 0 failed or skipped**. |
| Physical Redis | **7 checks passed** on real 7.4.11, including health, two Pub/Sub WebSockets and subscriber release, a coordinated native PAPER job, TTL/admission/Lua/heartbeat, outage 503, recovery with manual kill retained and clean shutdown. |
| Repeated Linux lifecycle | **84 passed** across three fresh subprocesses of 28 tests each. |

Python 3.12.14, FastAPI 0.142.2, Starlette 1.7.0, Pydantic 2.13.5, Hyperliquid SDK 0.24.0, pytest 8.4.2, pytest-asyncio 0.26.0, websockets 15.0.1, fakeredis 2.40.0, redis-py 6.4.0, NumPy 2.5.5, scikit-learn 1.9.1 and SciPy 1.18.1. Node 24.19.0 and npm 11.9.0. Python includes the existing Starlette TestClient/httpx deprecation and Pydantic serializer warning from an intentionally malformed concentration fixture. Results overlap across suites and are counted per command.

Research runs continue to use the single worker, captured native PAPER inputs and isolated accounting. Executed regressions cover final quote authority, Risk Firewall and manual kill, execution/reconciliation, balances, fee/funding, unchanged data identity and fingerprints, baseline/modeled replay, agent authority and SHADOW isolation. Browser worker counts, abort/busy recovery, and operational before/after comparisons are part of the executed portfolio and replay checks.

The 1,000-frame comparison rendered bounded 120-point traces. At the harness sampling point Chromium reported 63.6 MB JS heap usage and a maximum observed animation frame of 321.1 ms on the shared runner. Portfolio also exercised the 300-frame-per-market FINAL_ONLY case. These are local observations rather than timing or memory guarantees.

To reproduce after installing the existing `backend[test,redis,ml]` and Playwright environment, run the existing backend suite and frontend npm commands. From the repository root run the browser harnesses serially when using their default ports.

```sh
python frontend/tests/browser-phase1641.py --python "$(command -v python)" --output work/audit3/replay
python frontend/tests/browser-phase165c2.py --python "$(command -v python)" --phase165d --phase166a --phase166c --phase166d --output work/audit3/comparison
python frontend/tests/browser-phase176.py --python "$(command -v python)" --output work/audit3/portfolio
```

For accessibility, start the ordinary loopback backend in DEMO/PAPER with venue execution disabled and the Vite frontend. Use an isolated instance because the script briefly starts and stops the DEMO strategy to populate real retained agent events. Supply axe-core 4.11.1's `axe.min.js` to `frontend/tests/browser-audit3-accessibility.py --axe PATH --output work/audit3/accessibility`. The physical Redis run uses `backend/tests/phase155a_redis_acceptance.py --redis-server PATH --output work/audit3/redis.json` with `backend` on `PYTHONPATH`.

## Remaining limits and verdict

- **PARTIAL** A2-003 effective-price consolidation and actual venue-cost policy. Current native slot/exposure semantics and exact economic identities pass regressions. A2-005 remains partial outside the repeated Linux lifecycle scope.
- **PARTIAL / NOT RUN** A1-001/A1-006 signed TESTNET submission and reconciliation, A1-003/A1-004 real operational SDK reconnect/shutdown soak, A1-016 empirical cadence and model calibration, and A1-017 reproducible Python environment resolution. Optional ML coefficient export is local fixture evidence.
- **NOT RUN** macOS and Windows lifecycle checks, public read-only provider soak, authenticated historical acquisition and licensing, signed TESTNET, and platform screen-reader verification. DEMO profiles and deterministic provider fixtures prove their specific contracts.
- **BLOCKED** Phase 16.6B durable lifecycle and recovery, HIP-3 and broader-market execution, mainnet signing and production readiness. Local Redis recovery and explicit manual reruns establish the tested in-process guarantees.
- **OPEN** Current development-tree picomatch advisory. The original Audit 3.0 report and earlier acceptance records remain historical evidence.

**Conditional PASS** for the read-only Phase 18.0/18.1 design and market-discovery work. The evidence supports bounded local PAPER research on the tested native profiles. Keep the unresolved dev-tool advisory and the external acceptance gates visible when planning follow-on work.
