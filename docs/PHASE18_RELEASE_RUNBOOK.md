# Phase 18 release runbook

Use this runbook for a single operator running DEMO market data and local PAPER research on loopback with one backend worker. Review the candidate's exact evidence and the rollout gates before adoption. [Final acceptance](PHASE18_7_FINAL_ACCEPTANCE.md)

## Install from a clean checkout

The backend manifest requires Python 3.12 or later. Phase 18.7F exercised Python 3.12.14 on Debian 13 x86-64. Vite 7.3.8 requires Node `^20.19.0 || >=22.12.0`. The candidate used Node 24.19.0 and npm 11.9.0. Treat other OS and browser combinations according to the acceptance matrix. [Resolved versions](acceptance/phase187f/environment.json)

From the repository root, create a fresh virtual environment. The backend wheel comes from the checkout. `test` supplies the regression dependencies, `redis` enables optional local coordination, `ml` enables offline training and `yahoo` enables the optional research-only observation integration. Use the base install without extras for a minimal terminal. Enable optional services individually as needed.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install 'pip>=26.2,<27'
python -m pip install './backend[test,redis,ml,yahoo]'
python -m pip check
(cd frontend && npm ci && npm run typecheck && npm test && npm run build)
```

The frontend lockfile covers `npm ci`. Python resolves the declared ranges at install time. Save `python -m pip list --format=json` with each verification run and compare it to the measured environment when investigating differences. A frozen package inventory records the resolution used in the run. Deterministic Python resolution remains a release-engineering gate. [Package manifest](../backend/pyproject.toml) · [Frontend lockfile](../frontend/package-lock.json)

## Start the local terminal

From a clean checkout, create `.env` from `.env.example` in the repository root, or export the settings in the backend terminal. Use these values for local release verification. Keep the working directory at `backend/` when running the source checkout so the settings loader finds the root file.

```dotenv
MARKET_DATA_MODE=DEMO
EXECUTION_MODE=PAPER
ENABLE_HYPERLIQUID_TESTNET_ORDERS=false
HYPERLIQUID_PRIVATE_KEY=
HYPERLIQUID_ACCOUNT_ADDRESS=
MARKET_UNIVERSE_ENABLED=true
MARKET_UNIVERSE_NETWORK=MAINNET
LIVE_OBSERVATIONS_ENABLED=false
LIVE_STREAMS_ENABLED=false
REDIS_ENABLED=false
```

Run in separate terminals from the repository root. Keep command-line binding explicit and use the same host in the browser.

```bash
(cd backend && ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers)
(cd frontend && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort)
```

Open `http://127.0.0.1:5173`. Check `GET http://127.0.0.1:8000/api/v1/health` for `status=ok`, `mode=DEMO`, and `simulated=true`. The terminal header and diagnostics identify PAPER, connectivity and the current process/session. The UI uses Vite's loopback `/api` and `/ws` proxy. Server deployment checks require local peers, accepted Host and browser Origin, and reject forwarded headers. Remote multi-user access requires a separate design and acceptance. [Boundary implementation](../backend/app/deployment.py)

## Explorer and PAPER

1. Open **Markets → Market Explorer**. Confirm the qualified network and namespace for the selected listing, and check source, received age, mark and hourly funding. Server selection and the catalog fingerprint bind the observation. Expired or unavailable data is labeled accordingly. Keep Mainnet selected for the full catalog. The Testnet inventory currently exceeds the 64-namespace discovery cap.
2. From Explorer, open **Run guided research**. Enter an explicit synthetic reference price and select a scenario. Check eligibility, then run local PAPER once. The display keeps public market observations alongside the synthetic scenario input. Check the qualified market, simulated fills and accounting, fees, funding, and result provenance.
3. Use **Pro** to review Constant Product and Concentrated Liquidity settings, supervisory evidence and Quote Economics, Funding/Basis, and Market Eligibility advisories. Asset-aware PAPER applies a declared family and optional risk controls only after qualified admission. **Institutional** exposes native BTC/ETH/SOL portfolio allocation, risk, stress and provenance. Check the Risk Firewall, Vault and Logs from their terminal routes.
4. Historical Replay requires a trusted owner-only local POSIX vault configured through `HISTORICAL_REPLAY_ROOT` and a supported admitted dataset. Review coverage and provenance before running. Content fingerprints bind admitted data. Source authenticity, completeness and licensing require separate evidence. [Historical vault setup](../README.md#enable-a-trusted-local-historical-vault-optional)

For separately enabled native public observations, set `LIVE_OBSERVATIONS_ENABLED=true`. Set `LIVE_STREAMS_ENABLED=true` with it for native BTC/ETH/SOL WebSockets. Keep the operational feed in DEMO and execution in PAPER. The native observer has independent freshness, subscriptions and history. Leave both options off when the local workflow does not need them.

## Troubleshoot, shut down and roll back

| Symptom | Operator response |
| --- | --- |
| Backend or terminal disconnected | Verify the backend PID, bind address, port and `GET /api/v1/health`. Use the exact loopback frontend origin and remove unsupported proxy forwarding. Confirm the terminal received a fresh session before trusting current values. |
| Explorer `409`, stale rows or missing source | Refresh the catalog, reselect by qualified identity and recheck eligibility. For `429`, respect `Retry-After` and allow the provider's backoff. Disabled discovery, timeout, partial catalogs and caps have distinct diagnostics. Avoid repeated manual refreshes. |
| PAPER rejected or worker busy | Inspect the displayed bounded rejection, source identity, precision, generation and selected inputs. A lost client request can leave an admitted job occupying the worker. Let it drain, revalidate inputs and run once when available. |
| Redis degraded | Check the permitted local Redis process and application health. Required coordinated research rejects during an outage. Verify recovery and manual-kill status before further activity. Redis relays and leases support current-process coordination. |
| Replay unavailable | Verify the owner-only local storage path and data admission, then reload the catalog and recheck provenance. Preserve original source labels and receipt bounds. |

Stop an active local PAPER strategy from the terminal, allow in-flight research to drain, then stop the frontend and send an interrupt to Uvicorn. Verify the application shutdown completed, socket clients disconnected and any operator-started verification Redis process exited. The next process has a new identity and begins a fresh session. Retained browser evidence is bound to its accepted session and inputs. An interrupted job, order, accounting ledger or kill state lacks a durable restart protocol. Confirm current state explicitly after restart and re-run research from its inputs as needed.

For rollback, stop the candidate and select a reviewed commit in a clean checkout. Reinstall that commit's Python and locked frontend dependencies, apply the same loopback DEMO/PAPER settings and rerun health, terminal WebSocket and a small PAPER check. Keep the private historical vault outside the checkout and use the reviewed commit's supported storage contracts. Rollback changes the running code and starts a fresh process. It cannot reconcile venue state or resume interrupted work.

## Reproduce release verification

Run shared-port browser suites serially. Set `PYTHON` to the absolute backend virtual-environment interpreter and `AXE` to an approved local copy of axe-core 4.11.1. Install Playwright in the verification environment. The passing Chromium matrix used Playwright 1.62.0 with system Chromium. Firefox and WebKit require the binaries matching the selected Playwright version. The harness owns its local fixture processes.

```bash
(cd backend && ../.venv/bin/python -m pytest -q -rs --tb=short)
(cd frontend && npm ci && npm run typecheck && npm test && npm run build)
python -m playwright install firefox webkit
python frontend/tests/browser-phase187.py --engine chromium --python "$PYTHON" --axe "$AXE" --output work/phase187f/chromium
python frontend/tests/browser-phase187.py --engine firefox --python "$PYTHON" --axe "$AXE" --output work/phase187f/firefox
python frontend/tests/browser-phase187.py --engine webkit --python "$PYTHON" --axe "$AXE" --output work/phase187f/webkit
```

For the existing public observer, deterministic fixture and real Redis checks, run from `backend/`. Use an approved network for public read-only acceptance. The sustained probe uses the existing application and a bounded request cadence. Run it alone on the test IP where possible and record local measured traffic and concurrent traffic limitations.

```bash
PYTHONPATH=. python tests/phase187f_provider_soak.py --allow-public-network --mixed-owners --seconds 1800 --output ../work/phase187f/mainnet-soak.json
python tests/phase155b_live_readonly_acceptance.py --allow-public-network --seconds 30 --reconnect --output ../work/phase187f/native-external.json
python tests/phase155b_soak_runner.py --seconds 30 --max-cycles 1000 --output ../work/phase187f/native-fixture.json
PYTHONPATH=. python tests/phase155a_redis_acceptance.py --redis-server /path/to/redis-server --output ../work/phase187f/redis.json
```

The first two commands use official read-only endpoints. The same soak command without `--mixed-owners` reproduces the earlier catalog-and-summary scope. The fixture soak and Chromium harness use deterministic data. The Redis harness starts and stops a dedicated ephemeral instance on loopback. Native Safari/macOS, Windows, physical mobile browsers and assistive technology each need an independent run. Record time, versions and errors alongside each gate. [Browser matrix](acceptance/phase187f/browser-matrix.json) · [Provider evidence](acceptance/phase187f/provider-soak.json)

For the Testnet capacity check, run another isolated loopback process with `MARKET_UNIVERSE_NETWORK=TESTNET` and signing disabled. Request `GET /api/v1/market-universe` once and retain the sanitized inventory status and catalog count. If the inventory exceeds 64 entries, expect `503` with `inventory.error=CATALOG_CAPACITY` and no catalog. Independently request `{"type":"metaAndAssetCtxs","dex":""}` from the official Testnet `/info` endpoint over an approved network. Compare Core metadata and context rows by index and native identity before recording mark, oracle and funding. Keep the full wire response in scratch only if needed for validation. [Testnet evidence](acceptance/phase187f/provider-soak.json)

## Operator-controlled signed TESTNET gate

**SIGNED TESTNET — NOT RUN** for Phase 18.7F. A separate, explicitly authorized acceptance session must complete all of the following for the supported native Testnet scope.

- Confirm operator authorization, dedicated Testnet-only credentials and endpoint, a supported native market, bounded order count and exposure, a time window and explicit abort criteria. Keep credentials in the operator's approved secret store and outside reports.
- Capture concrete authorized ladder membership, risk and capital checks and final wire-equivalent authorization before a controlled submission. Record acknowledgments and reconcile CREATE, KEEP, REPLACE, CANCEL, duplicate/orphan states, partial fills and rejected changes independently against venue evidence.
- Exercise unknown-order and uncertain-position handling, adverse intervention, the manual kill path and reconciliation after disconnect. Record fees and other accounting with authoritative receipts. Reconcile remaining orders, fills and exposure before shutdown and explicitly verify cleanup.
- Preserve redacted, secret-free evidence for independent review. HIP-3 signing, Mainnet execution and remote multi-user operation are outside this release scope.
