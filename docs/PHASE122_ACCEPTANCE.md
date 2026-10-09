# Phase 12.2 verification and outstanding acceptance

Implementation and Linux fixture acceptance apply to the Phase 12.2 feature
branch, based on verified main `70a13c04a69924830487c934513e39d363ae653c`.
The PR must remain draft and unmerged. macOS, external providers, external Redis
and signed venue acceptance are separate gates.

## Linux environments and commands

Python **3.12.14**, Linux; Node **24.19.0**, npm **11.9.0**, Vite **7.3.6**.
Two independently installed virtual environments were used, with unchanged
repository dependency declarations and frontend lockfile.

| Dependency | Default `.[test]` | Complete `.[test,ml,redis,yahoo]` |
| --- | --- | --- |
| FastAPI / Starlette / AnyIO | 0.143.0 / 1.7.0 / 4.15.1 | same |
| Pydantic / settings | 2.14.0 / 2.15.0 | same |
| httpx / httpcore | 0.28.1 / 1.0.9 | same |
| pytest / pytest-asyncio | 8.4.2 / 0.26.0 | same |
| Uvicorn / websockets | 0.54.0 / 15.0.1 | same |
| NumPy / venue SDK / eth-account | 2.5.3 / 0.24.0 / 0.13.7 | same |
| redis / fakeredis | 8.1.0 / 2.39.0 | 6.4.0 / 2.39.0 |
| scikit-learn / yfinance | absent / absent | 1.9.1 / 1.7.0 |

From the repository root, these were the installation commands (each environment
is outside tracked source):

```bash
python3.12 -m venv /workspace/work/phase122-extended
cd backend
/workspace/work/phase122-extended/bin/python -m pip install -e '.[test,ml,redis,yahoo]'
/workspace/work/phase122-extended/bin/python -m pip check
/workspace/work/phase122-extended/bin/python -m compileall -q app
/workspace/work/phase122-extended/bin/python -m pip freeze
/workspace/work/phase122-extended/bin/python -m pytest -q tests/test_phase122_amm_hardening.py
/workspace/work/phase122-extended/bin/python -m pytest -q

python3.12 -m venv /workspace/work/phase122-default
/workspace/work/phase122-default/bin/python -m pip install -e '.[test]'
/workspace/work/phase122-default/bin/python -m pip check
/workspace/work/phase122-default/bin/python -m compileall -q app
/workspace/work/phase122-default/bin/python -m pip freeze
/workspace/work/phase122-default/bin/python -m pytest -q

cd ../frontend
npm ci --cache /workspace/work/npm-cache
npm ci --include=dev --cache /workspace/work/npm-cache
npm test
npm run typecheck
npm run build
```

Additional focused historical checks used:

```bash
python -m pytest -q tests/test_amm.py tests/test_strategy_risk.py \
  tests/test_phase5_inventory.py tests/test_phase6_market_adaptation.py \
  tests/test_phase7_runtime.py tests/test_phase8_runtime.py
python -m pytest -q tests/test_phase122_amm_hardening.py tests/test_integration.py
python -m pytest -q tests/test_api.py tests/test_audit_local_publisher.py \
  tests/test_phase11_api_static.py tests/test_phase12_websocket.py \
  tests/test_redis_lifespan.py tests/test_phase121_websocket_reliability.py
```

The complete suite includes existing AMM, risk, execution, reference, authorization,
accounting, simulation, infrastructure and WebSocket cases. Completed final runs:

| Check | Passed | Failed | Skipped | Warnings | Duration |
| --- | --- | --- | --- | --- | --- |
| Phase 12.2 acceptance module | 56 | 0 | 0 | 1 | 1.23s |
| Full complete optional installation | 1125 | 0 | 0 | 1 | 34.33s |
| Full default installation | 1124 | 0 | 1 | 1 | 33.19s |
| Phase 12.2 + final static/scope files | 76 | 0 | 0 | 1 | 1.36s |
| Six historical WebSocket/API files | 66 | 0 | 0 | 1 | 6.97s |
| Initial focused AMM/strategy/inventory/perp/runtime run | 121 | 0 | 0 | 0 | 1.49s |
| Lifecycle + Phase 12.2 focused run before final additions | 111 | 0 | 0 | 1 | 4.13s |
| Frontend case-level test run | 95 | 0 | 0 | 0 | 12.65s |
| TypeScript / production build | passed | 0 | — | build notices | build 3.23s |

`pip check`, `compileall`, generated terminal schema equality, historical audit
bytes, unchanged dependency declarations/lockfile and `git diff --check` passed.
The default skip is `test_agent_expansion.py`'s optional offline sklearn training;
ML is absent from that installation and passes with complete extras. The single
backend warning is upstream Starlette's httpx TestClient deprecation. Vite retains
nonfatal TanStack module-level `use client` directive notices. No test was disabled,
xfail'ed or rerun with a failure-hiding plugin. Chromium **151.0.7922.173** verified
the local terminal. The exact initial failures remain documented below.

No real provider or signed order was sent. Initial sandbox-only Git fetch/package
installation could not reach the configured proxy; supported escalated execution
then fetched actual main and installed packages successfully. Before that fetch,
GitHub connector responses supplied PR reviews and a baseline whose blobs, tree
and signed commit were verified by Git object hashes. No proxy bypass occurred.
One overlapping interrupted npm installation left TypeScript temporarily absent;
a clean locked installation restored it. No dependency or historical test was
changed to work around these environment issues.

Initial acceptance runs exposed an unavailable-perp-context preflight assumption
and an SVG title with multiple React children; both were corrected. The first
full extended run had **1113 passed / 1 failed**, and the first default run had
**1112 passed / 1 failed / 1 skipped**: the existing lifecycle test requires valid
configuration object identity. Revalidation now preserves that contract while
still validating copied inputs. The historical test remains unchanged. A final
review also changed feasibility to quantize allocated order sizes rather than
the whole side budget, retaining otherwise representable configurations.

Actual local Uvicorn/Vite/Chromium integration used DEMO/PAPER and disabled
TESTNET transmission. A 100-slot proposal rendered three grouped ticks at the
observed moving fair value, with one BID and two ASK prices, aggregate bars,
count-based collapse warnings, normalized AMM labels and AMM Settings counts.
No browser page exception occurred. REST stage diagnostics, strategy 200 update,
start and stop passed; stop left no active/partial/UNKNOWN orders. Retained
cancelled history remains visible. The first harness incorrectly expected empty
history after stop; that assertion was corrected to check active status. The
initial bundled Playwright browser was absent; system Chromium was used.
Vite logged ECONNRESET during deliberate socket replacement/closure; backend
logs showed no unexpected exception. This does not establish a reconnect soak,
macOS acceptance or signed exchange behavior.

## Outstanding gates

- Phase 12.1 implementation **MERGED**; Linux acceptance **PASSED**;
  macOS acceptance **PENDING USER VERIFICATION**; cross-platform A2-005 **PENDING**.
- A2-001 and scoped A2-002 code/fixture defects are corrected; live/provider and
  signed TESTNET acceptance remain pending. Feasibility is not a guarantee for
  arbitrary future fair values, source states, venue precision or Decimal inputs.
- A2-003 observation is accepted. Automatic rejection, trimming or coalescing
  requires a separately reviewed operational policy. Whole-finding closure is
  not claimed. No order identity, budget redistribution or execution permission
  change was introduced by the diagnostics.
- External Redis acceptance is separate from the passing fakeredis fixtures.

## macOS verification — pending user execution

Use `~/Desktop/hyperamm`. These commands validate the checked-out code only.
PR #38 acceptance and Phase 12.2 branch acceptance must be recorded separately.

Inspect the working tree first. If it contains changes, preserve them with a
local commit or a named stash (including untracked files where appropriate)
before switching branches. Do not discard modifications.

```bash
cd ~/Desktop/hyperamm
git status
git fetch origin
# For merged-main/PR #38 acceptance:
git switch main
git pull --ff-only origin main
git log -1 --oneline
# For this still-unmerged Phase 12.2 PR, instead select its feature branch:
# git switch --track origin/phase12/12-2-amm-core-quote-hardening
# If it already exists locally: git switch phase12/12-2-amm-core-quote-hardening
# git pull --ff-only origin phase12/12-2-amm-core-quote-hardening
```

Use the established Python 3.12 environment and confirm **3.12.14** before testing:

```bash
cd ~/Desktop/hyperamm/backend
source .venv/bin/activate
python --version
python -m pip install -e '.[test,ml,redis,yahoo]'
python -m pip check
python -m pip freeze
python -m compileall -q app

historical=(
  tests/test_api.py::test_terminal_state_includes_market_adaptation_after_runtime_tick
  tests/test_api.py::test_terminal_state_includes_perp_context_after_runtime_tick
  tests/test_api.py::test_phase8_terminal_serialization_and_secrets_absent
  tests/test_api.py::test_phase9_agents_api_and_terminal_state
  tests/test_audit_local_publisher.py::test_two_websockets_share_cached_observation_and_cleanup
  tests/test_audit_local_publisher.py::test_local_loopback_request_and_browser_origin_work
  tests/test_phase11_api_static.py::test_terminal_websocket_has_compact_accounting_without_full_ledger
  tests/test_phase12_websocket.py::test_websocket_sequence_compact_fields_and_disconnect
  tests/test_redis_lifespan.py::test_disabled_mode_does_not_construct_a_redis_client
  tests/test_redis_lifespan.py::test_redis_websocket_relay_and_research_keep_existing_contracts
)
python -m pytest -q "${historical[@]}"
python -m pytest -q tests/test_api.py tests/test_audit_local_publisher.py \
  tests/test_phase11_api_static.py tests/test_phase12_websocket.py \
  tests/test_redis_lifespan.py tests/test_phase121_websocket_reliability.py
python -m pytest -q
# Repeat in fresh pytest processes; preserve all failed results/tracebacks.
python -m pytest -q "${historical[@]}"
python -m pytest -q
# On the Phase 12.2 branch, also run:
# python -m pytest -q tests/test_phase122_amm_hardening.py
```

Test default and optional extras in separate fresh environments, so previously
installed ML/Yahoo dependencies cannot conceal the default behavior:

```bash
cd ~/Desktop/hyperamm/backend
for matrix in default extended complete; do
  python3.12 -m venv "../work/phase122-macos-$matrix"
  case "$matrix" in
    default) extras='.[test]' ;;
    extended) extras='.[test,ml,redis]' ;;
    complete) extras='.[test,ml,redis,yahoo]' ;;
  esac
  "../work/phase122-macos-$matrix/bin/python" --version
  "../work/phase122-macos-$matrix/bin/python" -m pip install -e "$extras" || break
  "../work/phase122-macos-$matrix/bin/python" -m pip check || break
  "../work/phase122-macos-$matrix/bin/python" -m pytest -q || break
done
```

Frontend:

```bash
cd ~/Desktop/hyperamm/frontend
npm ci
npm test
npm run typecheck
npm run build
```

Backend terminal:

```bash
cd ~/Desktop/hyperamm/backend
source .venv/bin/activate
MARKET_DATA_MODE=DEMO EXECUTION_MODE=PAPER \
ENABLE_HYPERLIQUID_TESTNET_ORDERS=false \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend terminal:

```bash
cd ~/Desktop/hyperamm/frontend
npm run dev
```

Open `http://localhost:5173`. Check `/api/v1/health`, terminal WebSocket updates,
refreshes, multiple tabs and disconnect/tab cleanup. Keep one tab open while
stopping/restarting the backend. Require visibly disconnected/stale state with
no invented valid-frame timestamp, then new valid session/process evidence
before recovery. Check local Vite integration and retain backend/Vite logs.
Correlate EPIPE/ECONNRESET with intentional socket closes; persistent failed
connections or unexplained backend cancellations require investigation.
On Phase 12.2, also inspect group counts, aggregate bars and suppression under
Strategy/Authorized stages. Stop the PAPER strategy after testing.

Only actual macOS results can complete the Mac acceptance gate.
