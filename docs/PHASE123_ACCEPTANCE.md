# Phase 12.3 acceptance and observation policy

Phase 12.3 hardens frontend terminal observations and preserves `phase12-v1` and
all backend economic authority. Implementation is reviewable on
`phase12/12-3-terminal-freshness-session-integrity`; the PR is draft and must not
be merged by this task. Linux acceptance is complete; macOS remains pending.

## Repository preflight and original reproduction

Fetched main before editing: **777b59f42273442bc3387220e9eecfd5fc2da1ad**.
GitHub connector metadata independently verified merged PR #38 at
`70a13c04a69924830487c934513e39d363ae653c` and PR #39 at the starting main SHA.
The initial working tree was clean. Reviewed Audit 2.0 A2-004, roadmap,
architecture/identity scopes, schema validator, terminal store/socket/effect,
source freshness, Dashboard, Header, System Health, regression runner and backend
publisher/runtime/WebSocket/contract generator. Both historical audits are preserved.

Original compiled schema/store reproduction used schema-valid fixture frames,
increasing sequence and an injected clock of `1700000000000`:

| Original input | Accepted store result |
| --- | --- |
| Current frame then emission `2001-01-01T00:00:00Z` | `connected`, no payload error, accepted ancient snapshot, `lastValidFrameAt=1700000000001` |
| Current frame then emission `2099-01-01T00:00:00Z` | `connected`, no payload error, accepted future snapshot, `lastValidFrameAt=1700000000001` |
| Session A, valid session B, replay session A with higher sequence | `connected`, no payload error, session A restored, `lastValidFrameAt=1700000000002` |

Root cause: the generated validator correctly checked timestamp syntax and all
nested schema fields, but not envelope age. The store only compared sequence
when both process and session matched; an identity change reset that check. It
stored browser arrival time and set connected. The socket inferred acceptance
from the resulting error field, then reset its private watchdog time/backoff.
Duplicate/regressive same-identity and malformed-schema guards already worked.
The unchanged baseline `npm test` completed successfully; the final separate
historical-module run confirms all **95 original cases** still pass.

## Acceptance semantics

The store is the acceptance boundary, including direct callers: unknown input
must pass the unchanged complete generated schema before temporal/identity checks.
JSON decoding belongs to the controller; malformed JSON gets a fixed safe error.
Accepted/rejected outcomes are explicit and never inferred from a previous error.

**Maximum age 5000 ms; maximum future skew 2000 ms; both inclusive.** One backend
publisher sleeps one second between observations, emits aware UTC time, uses a
module-wide process identity and sequence, and assigns new context session IDs.
The five-second envelope limit matches the existing connection watchdog and lets
normal local scheduling/transport delays recover. Two seconds allows a small
fixed clock difference without accepting 2099 or training on arbitrary frames.
Supported deployment remains localhost. Unsynchronized clocks must be corrected,
not accommodated by widening/training the tolerance. Full fractional ISO strings
are compared against UTC boundaries; age display/arrival clocks use milliseconds.
Malformed dates, invalid offsets/types, missing fields and impossible calendars
continue to fail the generated-schema validator.

Within a process, sequence must increase and emission time must not regress,
including a new session. Equal emission instants and timezone-equivalent times
are allowed; sequence gaps are valid for multiple observers. Full fractional-time
comparison catches backend microsecond regressions that Date.parse truncates.
A new non-retired process can reset sequence/time after a legitimate restart,
subject to the same envelope freshness bounds. Rejected transitions cannot retire
current identity. A valid process or session change retires the previous pair;
a process change also retires the whole prior process.

Two independent FIFO arrays retain **64 retired pairs** and **64 retired processes**.
A retired process with a never-seen session is rejected. Many same-process session
changes cannot evict process retirement. At the capacity boundary, the oldest
entry is evicted on the next successful transition. After eviction, temporal
freshness and active-process sequence/time guards still apply. This is bounded
consistency/replay protection, **not authentication**: no indefinite rejection is
promised for an evicted identity presenting forged fresh evidence. History is
in memory for this page lifetime and survives reconnects; reloads/tabs start with
no prior identity history. No server authorization depends on these frontend facts.

Only accepted frames replace the snapshot, advance sequence/emission/arrival
watermarks, clear validation errors, establish connected state or reset retry
delay. A socket open stays connecting and cannot reset the initial watchdog clock.
The watchdog checks accepted arrival age and emission bounds every second,
including a newly received envelope that was already nearly five seconds old.
Repeated rejected traffic therefore cannot keep a connection alive. Retry delay
is 1500→3000→6000→10000 ms, capped; a valid observation resets it to 1500 ms.
Reconnect count is observational and cumulative during a controller lifetime.
One controller owns the store; starting another stops its predecessor. Obsolete
callbacks, closed socket errors and repeated close notifications cannot mutate
the current stream or schedule extra timers. Cleanup is idempotent and releases
owned socket, watchdog and retry timer; React StrictMode remount is supported.

Six rejection counters and reconnect attempts saturate at **65535**. There is no
rejected payload history or snapshot logging. Fixed error reasons are displayed;
identifiers are shortened to eight characters. Recovery/session/gap notices stay
available until later notices replace them. Dashboard diagnostics show active
identity, accepted sequence/time, emission age, counters and market-feed health
**at emission**, independent of socket health.

The accepted snapshot remains immutable historical evidence during disconnection.
A render-only projection increases source ages by elapsed emission time and
ages perp evidence against its existing source-time budget. External-source
health/staleness at emission is retained independently of connection state;
header/risk current prices are withheld when the observation is historical.
Provider source timestamps and backend freshness/decisions stay unchanged. Perp
age uses its existing configured budget; external-provider budgets/quorum remain
backend-owned and provider health labels say **FRESH AT EMISSION**. The projection
never recalculates risk, consensus, authorization or accounting. System Health and
Dashboard explicitly mark historical observations; last authorization stays labeled
as a backend decision. Yahoo's separate observational-only API remains unchanged.

## Commands and exact Linux results

Python **3.12.14**, Node **24.19.0**, npm **11.9.0**, Vite **7.3.6**, system Chromium
**151.0.7922.173**. Backend installation used a new isolated virtual environment
and the declared complete extras; repository dependencies and lockfile are unchanged.
FastAPI **0.143.0**, Starlette **1.7.0**, AnyIO **4.15.1**, Pydantic **2.14.0**,
pytest **8.4.2**, pytest-asyncio **0.26.0**, Uvicorn **0.54.0**, websockets **15.0.1**.

From repository root:

```bash
python -m venv work/backend-venv
work/backend-venv/bin/python -m pip install -e 'backend[test,ml,redis,yahoo]' \
  --cache-dir work/pip-cache
cd backend
../work/backend-venv/bin/python -m pip check
../work/backend-venv/bin/python -m compileall -q app
../work/backend-venv/bin/python -m pytest -q \
  tests/test_phase12_websocket.py \
  tests/test_phase121_websocket_reliability.py \
  tests/test_audit_terminal_contract.py
../work/backend-venv/bin/python -m pytest -q
```

Results: pip check/compileall passed; focused tests **26 passed in 6.03s**;
complete suite **1125 passed in 41.12s**, no failures/skips. Both pytest invocations
report one upstream Starlette/httpx TestClient deprecation warning. No backend
implementation changes were needed.

Generated contract verification, without overwriting committed schema:

```bash
# backend/
../work/backend-venv/bin/python - <<'PY'
import json
from pathlib import Path
from scripts.generate_terminal_contract import build_contract
assert build_contract() == json.loads(
    Path('../frontend/src/contracts/terminal.schema.json').read_text())
print('phase12-v1 generated schema equality passed')
PY
```

Passed. `process_id`, `session_id`, `sequence`, `emitted_at`, `contract_version`
and all generated nested contract fields are unchanged.

```bash
cd frontend
npm ci --cache /workspace/hyperamm/work/npm-cache
npm test
npm run typecheck
npm run build

# Repeat this in three independent processes after npm test compiles utilities:
NODE_PATH="$PWD/node_modules" \
TERMINAL_TEST_BUILD="$PWD/../work/frontend-tests" \
node --test --test-isolation=none --test-reporter=spec \
  tests/terminal-integrity.test.cjs
```

`npm ci` passed using a workspace cache. `npm test`: **149 passed, zero failed,
zero skipped: 95 preserved + 54 new**. The historical six modules independently
passed **95 cases**. Three final independent new-module runs passed **54 each**.
TypeScript and production build pass. Build retains existing nonfatal TanStack
module-directive notices. Runner uses individual-case reporting where Node supports
`--test-isolation`, with the prior default behavior on older supported runtimes.

New coverage includes ancient/future/age/skew boundaries, equivalent timezone,
malformed/impossible/nonnumeric/missing-timezone timestamps; higher-sequence bypass;
full-fraction clock boundaries; duplicate/regression/gaps; session/process changes,
retired-pair/process replay, capacity/eviction and unchanged accepted state; schema
validation at direct store boundary; handshake, malformed/rejected streams,
backoff, arrival/emission watchdog, cleanup, controller generations/StrictMode;
fresh envelope with stale sources and retained historical display invariance.
Historical Yahoo, quote lineage, effective-liquidity and schema tests still pass.

Initial verification issues were corrected rather than hidden: default npm cache
was not writable, so installation used work/npm-cache; one skew fixture advanced
its clock onto the inclusive boundary; a fractional-boundary fixture initially
removed its existing milliseconds. Neither needed a production-policy workaround.
No tests were deleted, marked xfail or weakened; the historical socket fixture now
uses a coherent injected epoch and only retimes originally valid envelopes.

## Actual Uvicorn, Vite and Chromium integration

Services bound to localhost with DEMO/PAPER and signed TESTNET explicitly disabled:

```bash
# backend/
MARKET_DATA_MODE=DEMO EXECUTION_MODE=PAPER \
ENABLE_HYPERLIQUID_TESTNET_ORDERS=false \
../work/backend-venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
# frontend/
npm run dev -- --host 127.0.0.1
```

Actual headless Chromium through Vite completed startup before backend (no valid
time from handshake); multiple advancing real frames; **three browser reloads**;
**three concurrent tabs**, independent tab closure and continued healthy streaming;
abrupt backend SIGKILL (retained accepted time and visibly historical data);
new backend process and valid recovery/restart notice. Final browser/context/backend
shutdown was graceful. No strategy was started and the browser sent **zero control
POSTs**. Existing backend regressions separately cover authority/accounting invariance.

An isolated browser tab used controlled WebSocket fixtures to reject 2001/2099,
session A→B→A and retired-process/unknown-session replay without advancing accepted
time; legitimate new process recovered; a fresh envelope with stale perp evidence
retained source time and backend authorization. Production publisher timestamps
were never modified. Old callbacks and repeated generations are deterministically
covered by the fake-socket regression matrix.

Zero browser page exceptions. Console diagnostics include the deliberately absent
backend health/proxy request, early StrictMode socket closure and a resource 404;
console is not claimed wholly clean. Vite's expected disconnect EPIPE/ECONNRESET
and backend-absent ECONNREFUSED remain logged. No persistent intended-active stream
failure or unexpected backend exception appeared. DEMO startup had no material
reference state; provider quorum/Yahoo invariance is covered by existing and new
schema-valid fixtures, not claimed as live-provider acceptance.

The first browser harness hit Vite dependency-optimization reload while polling;
its navigation polling now explicitly retries only destroyed navigation contexts.
After HMR edits, plain module imports observed a different store instance; the
harness now imports the exact store URL loaded by the page, including Vite cache
timestamps. This required no application workaround.
A later harness assumed optional DEMO references existed; the source-time check
uses actual perp evidence instead. Browser inspection also identified and fixed a
real display issue: the prior UI clock tick could be older than a just-emitted
frame and falsely label it clock skew. Every render now samples Date.now while
retaining the one-second aging tick. No unexpected errors were suppressed.

## Pending environmental gates and Mac verification

Phase 12.1 remains MERGED / Linux accepted / macOS pending; cross-platform A2-005
is still pending. Phase 12.2 is MERGED / Linux accepted / macOS and live/signed
acceptance pending; A2-003's operational collapse policy remains deferred. This
phase does not reopen their implementations or declare those gates complete.

Phase 12.3 macOS acceptance, external-provider/Redis integration and extended
clock/reconnect soak are pending. Linux localhost fixtures do not establish these.
For macOS, preserve any dirty work, fetch the draft branch, use the established
Python 3.12.14 environment, and run:

```bash
cd ~/Desktop/hyperamm
git status
git fetch origin
# Switch only after preserving unrelated changes:
git switch phase12/12-3-terminal-freshness-session-integrity
cd frontend
npm ci
npm test
npm run typecheck
npm run build
cd ../backend
source .venv/bin/activate
python --version
python -m pip check
python -m pytest -q tests/test_phase12_websocket.py \
  tests/test_phase121_websocket_reliability.py tests/test_audit_terminal_contract.py
python -m pytest -q
```

Repeat real browser startup-before-backend, reload/tabs, backend stop/restart,
historical/source freshness and safe shutdown with the DEMO/PAPER commands above.
Only actual Mac results close that gate. The draft must remain unmerged.
