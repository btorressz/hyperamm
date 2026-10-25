# Phase 15.5A — macOS fallback and independent platform verification

Cloud offline implementation and acceptance succeeded. No required offline
Cloud test is left unexecuted because of a missing dependency or browser.
**Genuine venue access remains BLOCKED; macOS execution is NOT RUN.**
Do not report the Linux results as macOS acceptance or mark Phase 15 complete.

## Actual Cloud attempts and diagnosis

| Attempt | Result / evidence | Classification / recovery |
| --- | --- | --- |
| `git fetch origin main` | Initial sandbox: `Failed to connect to proxy port 8080`. | Network sandbox restriction. Same configured proxy with permitted command execution succeeded; latest main and PR #53 verified. Resolved. |
| `python -m pip install -e 'backend[test,ml,redis,yahoo]'` | Initial sandbox: `Cannot connect to proxy ... Operation not permitted` while resolving setuptools. | Installation permission, not nonexistent package. Supported proxy retry succeeded; no TLS/policy changes. Resolved. |
| `npm ci` | Initial sandbox installation failed; locked proxy retry restored all 27 packages. | Installation permission. No manifest/lockfile changes. Resolved. |
| `python -m pytest -q` | Sandboxed TestClient stalled after 49 tests, before application lifespan. Focused 25s diagnostic reproduced it; faulthandler showed portal `_spawn_task_from_thread` waiting while the event loop remained in `select`. | Sandbox event-loop/loopback limitation. Stopped incomplete run; permitted loopback run passed unchanged baseline 1649 and final 1822. No assertion skipped or weakened. Resolved. |
| `apt-get download redis-server redis-tools` | System package metadata absent: `Unable to locate package`. Extracted binary then needed `liblzf.so.1`. | Workspace-only apt metadata from permitted official Debian mirror and extracted standard liblzf resolved setup. Actual Redis 8.0.2 passed seven checks. No system service/Docker/new Redis architecture. Resolved. |
| Actual Chromium harness | First extension assumed Risk had an h1; the existing page uses `Risk Management`. A later fixed-delay unavailable-state assertion was premature. | Harness defects, not application regressions. Correct page selector and event-based state waits; final 28 workflows/54 route-viewport checks passed. Resolved. |
| `cd backend; python -c 'from app.market_data.hyperliquid_metadata import load_sdk_metadata; load_sdk_metadata()'` | `ProxyError ... host='api.hyperliquid.xyz' ... Tunnel connection failed: 403 Forbidden` | **BLOCKED: configured outbound destination restriction.** Actual policy excludes this venue host; no alternate route, TLS disablement or geographic bypass attempted. Offline normalized fixtures succeeded. |

Cloud: Debian 13.6 / Linux x86_64, Python 3.12.14, Node 24.19.0, Chromium
151.0.7922.173 / Playwright 1.62.0. Full dependency versions and exact passing
counts are in [acceptance](PHASE155A_ACCEPTANCE.md). A Linux execution environment
cannot certify the macOS scheduler/browser/SDK thread lifecycle. Independent
macOS verification remains a user/local platform gate, not a claimed remote pass.

## Exact macOS offline commands

Use the actual PR branch after review. Run from a clean clone/worktree so local
credentials/settings do not activate live streams or TESTNET. These commands
explicitly preserve DEMO/PAPER; they never send signed orders.

```bash
git fetch origin main phase15/15-5a-integrity-offline-acceptance
git switch phase15/15-5a-integrity-offline-acceptance
git rev-parse HEAD
sw_vers
uname -m
brew install python@3.12 node@24 redis
export PATH="$(brew --prefix node@24)/bin:$PATH"
python3.12 -m venv work/phase155a-macos/venv
source work/phase155a-macos/venv/bin/activate
export MARKET_DATA_MODE=DEMO EXECUTION_MODE=PAPER
export ENABLE_HYPERLIQUID_TESTNET_ORDERS=false
export LIVE_OBSERVATIONS_ENABLED=false LIVE_STREAMS_ENABLED=false
export REDIS_ENABLED=false REDIS_REQUIRED=false REDIS_RESEARCH_ENABLED=false
cd backend
python -m pip install -e '.[test,ml,redis,yahoo]'
python -m pip check
python -m compileall -q app
python -m pytest -q
for iteration in {1..10}; do
  python -m pytest -q tests/test_redis_lifespan.py || break
done
python tests/phase155a_redis_acceptance.py \
  --redis-server "$(command -v redis-server)" \
  --output ../docs/acceptance/phase155a-macos/redis-results.json
cd ../frontend
npm ci
npm test
npm run typecheck
npm run build
cd ..
python -m pip install playwright
python -m playwright install chromium
PHASE155A_CHROMIUM=$(python -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); print(p.chromium.executable_path); p.stop()')
python frontend/tests/browser-phase155a.py \
  --python "$VIRTUAL_ENV/bin/python" --chromium "$PHASE155A_CHROMIUM" \
  --output docs/acceptance/phase155a-macos
git diff --check
```

The browser script owns loopback Uvicorn/Vite processes on ports 8000/5173 and
cleans up. Stop unrelated local services on those ports first. Its normalized
fixtures are explicitly labeled, and four explicit real PAPER runs are isolated
from operational strategy. The Redis script starts an ephemeral loopback-only
server on a free port, with persistence disabled, and shuts it down.

Success criteria: all-extra backend **1822 passed, 0 failed/skipped**, frontend
**641 passed, 0 failed/skipped/cancelled**, typecheck/build/pip/compile success,
Chromium report `classification: PASS`, **28 workflows**, all six sizes/54 route
checks, zero page exceptions, and Redis report seven successful checks. Record
actual counts if upstream main or optional package versions change; investigate
any mismatch instead of overwriting Cloud evidence or assuming an environment bug.

## Genuine public metadata fallback (only where permitted)

Requires permitted network/venue access, the official installed SDK and valid
public endpoint reachability. No signing credential is needed. From `backend`
with the venv active:

```bash
python - <<'PY'
from datetime import datetime, timezone
from app.market_data.hyperliquid_metadata import load_sdk_metadata, validate_native_metadata
raw = load_sdk_metadata()
markets = validate_native_metadata(raw, datetime.now(timezone.utc))
for market in markets:
    print(market.model_dump(mode='json'))
assert all(m.metadata_status == 'EXCHANGE_VERIFIED' for m in markets)
PY
```

Capture the exact command/status, sanitized error or validated native BTC/ETH/SOL
metadata, timestamp, OS/Python/SDK versions and network conditions. A 403/451,
permission denial or venue restriction stays BLOCKED; do not use a VPN/alternate
endpoint to circumvent it. This is metadata-only acceptance and does not establish
WS reconnects, event times, cleanup or soak. Coordinate those with Phase 15.5B.

## Merge gate and reporting results

The draft PR is reviewable now. Before unqualified final acceptance/merge, report
independent macOS lifecycle/browser results and resolve or explicitly retain the
remaining authorized external gates with the Phase 15.5B collaborator. Signed
TESTNET, public hosting and long venue soak are not part of this offline task.

Reply to the PR with tested SHA, `sw_vers`/architecture, Python/Node/SDK/dependency
versions, commands, exact passed/failed/skipped counts, browser/Redis JSON and
actual desktop/mobile screenshots. Classify each check PASS, FAIL, BLOCKED,
NOT RUN or NOT APPLICABLE. Attach failure output if anything fails; do not replace
an original failure with a later pass without explaining what changed.
