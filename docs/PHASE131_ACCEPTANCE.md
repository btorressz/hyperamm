# Phase 13.1 — Institutional Design Foundation & Navigation

Implemented for review on `phase13/13-1-design-foundation-navigation`, against
`main`. This task creates a **draft PR and does not merge**. Phases 13.2 and 13.3
remain follow-on stages. Available Linux acceptance: **2026-10-09
(America/Los_Angeles)**.

## Verified preflight

Fetched current `main`: **68949b04edb1099828f8bf5f9deca0afe4b85e62**. The initial
checkout was clean. The same SHA was fetched again before delivery; no concurrent
main changes were displaced. GitHub connector metadata independently verified:

| Prerequisite | Merged commit |
| --- | --- |
| PR #38 — Phase 12.1 | `70a13c04a69924830487c934513e39d363ae653c` |
| PR #39 — Phase 12.2 | `777b59f42273442bc3387220e9eecfd5fc2da1ad` |
| PR #40 — Phase 12.3 | `68949b04edb1099828f8bf5f9deca0afe4b85e62` |

Reviewed architecture, roadmap, Phase 12.1 acceptance in the roadmap,
`PHASE122_ACCEPTANCE.md`, `PHASE123_ACCEPTANCE.md`, the generated terminal schema,
API client, terminal validator/socket/store, display preferences, existing twelve
pages, shared controls, chart sizing and CSS layers. The supplied reference PNG
and recording were unavailable in this execution context; neither was inspected.
The actual current frontend was inspected in Chromium using a detached,
unmodified checkout of the starting SHA, then compared with the updated frontend
against the same real DEMO/PAPER backend. The original working tree was preserved.

Unchanged-main baseline: **149 frontend tests passed**, 0 failed/skipped;
TypeScript and production build passed. The repository's locked dependencies
were installed; package declarations and lockfile were not changed.

## Audit and implemented changes

The existing dark navy terminal and all twelve functional pages are retained:
Dashboard, Markets, Strategy, AMM Settings, Execution, Risk, Supervisory Agents,
Vault, Analytics, Simulation & Optimization, Logs and Settings.

| Area | Before | Implemented foundation |
| --- | --- | --- |
| Navigation | Component-local page state; refresh returns to Dashboard | Typed twelve-route registry, native `#/...` links, direct URLs, refresh/history, active sidebar, safe invalid-route replacement and page-specific document titles |
| Sidebar | Mixed Unicode icons; collapse state resets; collapse control disappears below 1100px | Consistent original stroke SVGs, saved collapse preference, reachable expand/collapse control, scrolling navigation at short heights |
| Narrow screens | Permanent icon rail; labels/collapse unavailable | Below 768px, labeled navigation drawer with modal semantics, focus trap, Escape/close/scrim dismissal, focus return, inert background and scroll-lock cleanup |
| Header | Tightly mixed status/controls; retained midpoint and running status can look current | Consistent market/status hierarchy; sticky header with immediately available kill; unavailable current midpoint and explicit last-snapshot strategy/risk labels during stale/disconnected observation |
| Shared UI | Repeated shell rules; 8–9px secondary labels; uneven panel hierarchy | Named palette/spacing/radius/table tokens in `phase13.css`, superseded shell CSS removed, existing panel borders/surfaces bound to tokens, consistent labels, controls, badges, focus, disabled/hover states |
| Panels and states | Bold text acting as titles; duplicated status markup | Named sections with semantic `h2` titles; shared loading/status banners and readable empty/error states |
| Financial tables | Tabular digits but left-aligned numeric order columns | Explicit right-aligned price/size/filled columns in the existing shared order table; formatter precision, units and Decimal aggregation retained |
| Diagnostics | Nine observations in two columns before every workspace | Three columns on desktop, two on tablet, one on small mobile; all identity/freshness/rejection evidence retained |

No UI framework/router or production dependency was added. Tokens cover normal,
raised and header surfaces, borders, positive/negative/risk/error colors, focus,
interactive/disabled/hover states, spacing and table density. Existing
page-specific chart dimensions and financial logic remain in their existing
components; longer page workflows belong to 13.2/13.3. The original desktop
information density is preserved.

Changed implementation files:

- `frontend/src/App.tsx`; `hooks/usePageNavigation.ts`, `hooks/useMobileNavigation.ts`;
  `utils/navigation.ts`; `stores/display.ts`.
- `components/Sidebar.tsx`, `NavIcon.tsx`, `Header.tsx`, `TerminalPrimitives.tsx`,
  `TerminalDiagnostics.tsx`, `RecentExecution.tsx`.
- `phase13.css`, `styles.css`, `phase12.css`; existing `phase5.css`, `phase6.css`,
  `phase7.css`, `phase8.css`, `phase9.css`, `phase11.css` consume shared border tokens.
- `frontend/tests/navigation.test.cjs`, `browser-phase131.py`, `run.cjs`.
- `backend/tests/test_phase11_api_static.py`: replace an old exact sidebar tuple
  assertion with route-registry/native-link/Vault-page wiring assertions. All
  read-only accounting and authority checks in that test remain intact. No
  backend application implementation changed.
- This acceptance document, roadmap and two non-sensitive DEMO/PAPER screenshots.

## Regression results

Python **3.12.14**, Node **24.19.0**, npm **11.9.0**, Vite **7.3.6**,
Chromium **151.0.7922.173**. Backend used a fresh virtualenv with all requested
extras; no external Redis or signed venue connection was established.

| Final completed check | Exact result |
| --- | --- |
| `npm ci --include=dev --cache ../work/npm-cache` | Passed; declarations/lock unchanged |
| `npm test` | **164 passed**, 0 failed/skipped; all **149 original + 15 foundation regressions** |
| `npm run typecheck` | Passed |
| `npm run build` | Passed; 1.51s |
| Focused backend accounting/terminal/WebSocket/AMM suite | **84 passed**, 0 failed/skipped; 1 warning; 6.75s |
| Complete backend `.[test,ml,redis,yahoo]` suite | **1125 passed**, 0 failed/skipped; 1 warning; 26.26s |
| `python -m pip check` / `compileall -q app` | Passed |
| All twelve pages at six requested representative widths | **72 actual Chromium layout checks passed** |
| Protected audits/schema/dependencies/integrity/effective-depth files | Unchanged |
| `git diff --check` / forbidden infrastructure scope | Passed / no excluded infrastructure added |

The fifteen new frontend cases cover all route round-trips, invalid/empty routes,
normalization without extra history, subscription cleanup, native active-page
links, collapse preference isolation, mobile modal/inert semantics, historical
sidebar labeling, named panels, loading/empty/error semantics, disconnected and
expired header evidence, missing strategy evidence, and the active kill latch.
Original financial precision, complete schema, timestamp/session/process/replay,
watchdog, socket generation, bounded history and provider-isolation tests pass.

One backend warning is upstream Starlette/httpx TestClient deprecation. The build
retains existing nonfatal TanStack `use client` directive notices. Server-rendered
preference tests can report unavailable browser storage; real-browser preference
persistence passed. Initial `npm ci` failed because the default cache was outside
the writable workspace; specifying the workspace cache corrected installation.
The first backend run was **1124 passed / 1 failed**, exposing the old sidebar
literal assertion; it was updated to the new wiring. An initial frontend run was
**163 passed / 1 failed** because SSR reads Zustand's initial snapshot rather than
mutated client state; the collapse test now checks actual store preference
isolation, and Chromium independently checks collapsed rendering/persistence.
Browser harness label and prior-focus assumptions were corrected before final
acceptance. No tests were removed, skipped, xfailed or weakened to conceal a failure.

## Actual browser acceptance

Real Uvicorn and Vite ran locally in **DEMO/PAPER** with signed TESTNET disabled.
The committed optional `frontend/tests/browser-phase131.py` checks:

- Each of twelve pages at **1920×1080, 1440×900, 1366×768, 1024×768,
  768×900 and 390×844**. No document-level horizontal overflow; tables keep their
  intentional internal scroll. The header kill control stays inside every viewport.
- Native sidebar selection, direct routes, refresh, back/forward, invalid-route
  fallback, keyboard skip link, collapsed width and saved collapse/density settings.
- Mobile modal/inert state, Tab/Shift+Tab wrap, Escape focus return and selecting
  a page. Panels, real market charts and tables render across the twelve pages.
- With explicit `--paper-controls`, existing AMM settings remain local while
  unsaved, invalid zero reserves return readable **422** without active-config
  mutation, Reset discards edits, a valid stopped-strategy edit saves, and the exact
  original config is restored through the same UI.
- Existing simulation returns actual results without modifying runtime config or
  starting strategy. Start updates the strategy state; immediate header kill
  activates the backend latch, stops strategy intent and clears authorized quotes.
  Confirmed Resume clears the latch through the existing backend API and leaves
  strategy stopped. No exchange orders are sent.

A separate real-browser run navigated between pages without adding sockets,
stopped the task-owned Uvicorn process while the page stayed open, checked the
historical banner/current-price suppression and retained accepted timestamp,
then restarted a real backend process. Recovery required fresh new-process
evidence. Browser calls into the actual store rejected an ancient advancing
frame and a fresh-looking retired-process replay without replacing accepted
identity/time. The unchanged deterministic suite separately covers schema,
future skew, sequence/time regressions, retirement bounds and generation ownership.
Both backend processes shut down cleanly. This is a short local reconnect check,
not extended soak or cross-platform acceptance.

**Zero browser page exceptions.** Console is not claimed completely clean:
a resource 404 and the deliberately invalid strategy request's 422 were recorded.
Intentional disconnect/restart and StrictMode socket replacement continue to
produce existing Vite EPIPE/ECONNRESET/ECONNREFUSED diagnostics. No persistent
intended-active connection failure or unexpected backend exception was observed.

Accessibility acceptance is scoped to labeled native navigation, active-page
semantics, focus indicators and skip target, named panels, modal keyboard/inert/
focus-return behavior, reduced-motion preference, readable shared labels and
reachable safety controls. It is not a complete screen-reader or WCAG certification.

## Reproduction commands

```bash
cd frontend
npm ci --include=dev --cache ../work/npm-cache
npm test
npm run typecheck
npm run build

cd ../backend
python3.12 -m venv ../work/phase131-venv
../work/phase131-venv/bin/python -m pip install -e '.[test,ml,redis,yahoo]'
../work/phase131-venv/bin/python -m pip check
../work/phase131-venv/bin/python -m compileall -q app
../work/phase131-venv/bin/python -m pytest -q tests/test_phase11_api_static.py \
  tests/test_phase12_websocket.py tests/test_phase121_websocket_reliability.py \
  tests/test_phase122_amm_hardening.py
../work/phase131-venv/bin/python -m pytest -q

# Separate backend terminal:
MARKET_DATA_MODE=DEMO EXECUTION_MODE=PAPER \
ENABLE_HYPERLIQUID_TESTNET_ORDERS=false \
../work/phase131-venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000

# Separate frontend terminal:
cd frontend
npm run dev -- --host 127.0.0.1

# Python with Playwright installed and system Chromium available:
python tests/browser-phase131.py --output ../work/phase131/browser
# Only against an isolated stopped DEMO/PAPER runtime with TESTNET disabled:
python tests/browser-phase131.py --output ../work/phase131/browser --paper-controls
```

## Review media and remaining gates

[Before](images/phase131-before-dashboard.png) and
[after](images/phase131-after-dashboard.png) show actual local DEMO/PAPER
observations, not example live financial performance. Screenshots were captured
at different observation times; prices/time ranges should not be compared as
performance. The after image includes the visible keyboard workspace focus.
Only these two review images are committed; private recordings/reference assets
and intermediate logs are excluded.

Phase 13.2 Dashboard/Markets/Strategy/AMM/Risk/Execution workflow enhancements and
Phase 13.3 Agents/Vault/Analytics/Simulation/Logs/Settings enhancements are **not
implemented by this PR**. Proceed only after the relevant preceding PR is merged
or on an explicitly reviewed dependent branch with its correct base.

Phase 12.1/12.2/12.3 macOS acceptance, live-provider/real Redis/signed TESTNET
acceptance and extended reconnect/clock soak remain pending. A2-003's stronger
collapsed-slot execution policy remains deferred; cross-platform A2-005 is not
closed. No backend economic, API contract, source quorum, risk/authorization,
signing, PAPER settlement, accounting, agent or ML SHADOW authority changed.
No Actions/`.github`, Docker/database, new AMM/provider/agent, MAINNET/custody,
remote/multiuser hosting, Phase 14/15 work or automatic merge was introduced.
