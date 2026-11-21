# HyperAMM Phase 18 local release runbook

Use the [final acceptance report](PHASE18_7_FINAL_ACCEPTANCE.md) to check the release decision. The deployment is a single operator on a trusted loopback host with one backend worker. The acceptance host used Debian 13.6 x86-64, Python 3.12.14, Node 24.19.0, npm 11.9.0 and Chromium 151.

## Install from a reviewed revision

Check the revision with `git rev-parse HEAD`. Start from a clean checkout and keep local configuration and data out of version control. The backend declares Python >=3.12 and dependency ranges. The tested resolution is in [environment.json](acceptance/phase187f/environment.json). The frontend uses the checked-in lockfile.

```bash
# From the repository root
python3.12 -m venv work/phase187f/venv
source work/phase187f/venv/bin/activate
python -m pip install -e './backend[test,redis,ml,yahoo]'
python -m pip check
(cd frontend && npm ci && npm run typecheck && npm test && npm run build)
```

Install `./backend` without extras for the minimal runtime. The `test` extra supplies pytest and the in-memory Redis fixture. The `redis` extra supports optional local coordination with a physical Redis server. The `ml` and `yahoo` extras enable optional offline SHADOW tooling and Yahoo research observations respectively. Use the existing local Vite server for the verified API and WebSocket proxy configuration. The production build separately verifies artifact generation.

## Configure and start on loopback

In a new checkout, copy `.env.example` to `.env`. The backend reads it relative to `backend/`. Set the following values in that file or export them in the backend shell.

```dotenv
MARKET_DATA_MODE=DEMO
EXECUTION_MODE=PAPER
ENABLE_HYPERLIQUID_TESTNET_ORDERS=false
HYPERLIQUID_PRIVATE_KEY=
HYPERLIQUID_ACCOUNT_ADDRESS=
REDIS_ENABLED=false
MARKET_UNIVERSE_ENABLED=true
MARKET_UNIVERSE_NETWORK=MAINNET
LIVE_OBSERVATIONS_ENABLED=false
LIVE_STREAMS_ENABLED=false
REDSTONE_ENABLED=false
```

Start the backend and frontend in separate terminals. The backend command uses the existing app entry point in a single process without the development reloader.

```bash
# Backend terminal, from the repository root, with the environment activated
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

```bash
# Frontend terminal, from the repository root
cd frontend
npm run dev -- --host 127.0.0.1 --strictPort
```

Open `http://127.0.0.1:5173/`. Vite routes `/api` and `/ws` to port 8000. Keep both listeners on loopback. The backend checks the connection peer, Host and Origin and rejects forwarded headers. The host's user and session controls determine who can reach loopback.

Check `GET http://127.0.0.1:8000/api/v1/health` for `status=ok`, `mode=DEMO` and `simulated=true`. The Terminal should connect to `/ws/terminal` and advance its sequence. Open Risk Firewall, Vault and Logs and confirm the expected local state. To work offline, set `MARKET_UNIVERSE_ENABLED=false` and use the native DEMO/PAPER workflows.

## Explore public markets and run PAPER research

1. Enable Mainnet discovery and select a listed Core or HIP-3 instrument in Market Explorer. Confirm the network, DEX, market identity and catalog status.
2. A current mark and hourly funding rate carry local receipt time and expire with the observation or catalog. For API checks, GET `/api/v1/market-universe`, then POST the active `catalog_fingerprint`, `network` and 1–13 canonical `market_keys` to `/api/v1/market-universe/market-summaries`.
3. In Starter, follow the qualified market handoff, choose a scenario and enter a synthetic price and hypothetical assumptions. Validate, run and inspect Results. Switch to Pro for standard or asset-aware controls and choose Constant Product or Concentrated Liquidity. Review modeled fills, fees, funding and provenance. Predictive Adverse Selection remains SHADOW.
4. In Institutional, run Portfolio Research on a supported BTC/ETH/SOL selection and inspect allocation, risk and stress receipts. For Historical Replay, provision a private owner-only POSIX evidence root, admit a valid dataset and set `HISTORICAL_REPLAY_ROOT` to its absolute path before startup. Confirm the dataset in Replay and preserve the source and rights evidence. [Historical importer and private storage](PHASE161B_ACCEPTANCE.md#admission-and-use)
5. For independent native public REST observations, set `LIVE_OBSERVATIONS_ENABLED=true`. To add native BTC/ETH/SOL streams, also set `LIVE_STREAMS_ENABLED=true`. Keep execution in PAPER.

## Respond to source failures and stop

- For a replaced or expired catalog, reload it and reselect the exact market. Recheck PAPER eligibility before submitting a fresh run.
- A 429 means capacity or backoff. Honor `Retry-After` where returned and allow at least 30 seconds after an upstream 429. Pause automation during a provider incident. TIMEOUT, STALE and PARTIAL require checking the displayed source state before using observations.
- Full Testnet discovery rejects inventories above 64 namespaces. A standalone Core context response establishes only Core availability.
- After a WebSocket interruption, confirm Terminal or stream identity and fresh data after reconnect. Revalidate held research evidence. An admitted worker can hold its slot after a caller loses the response.
- Stop issuing requests, let admitted work finish, close the browser or Vite and send SIGTERM or Ctrl-C to Uvicorn. Wait for application shutdown and check for a released port and exited process. During optional Redis coordination, stop Redis after the app.
- A restart starts a fresh process and session. Local Redis restores tested connectivity, leases and admission behavior after an outage in the same backend process. Manual kill stays set under that contract. Durable order or accounting restoration and resumption of interrupted jobs remain separately gated.

## Verify and roll back

```bash
(cd backend && python -m pytest -q -rs --tb=short)
(cd frontend && npm ci && npm run typecheck && npm test && npm run build)
(cd frontend && npm audit && npm audit --omit=dev)
```

Compare compatibility receipts using the [controlled PAPER and native probe commands](PHASE18_7_FINAL_ACCEPTANCE.md#financial-compatibility). Install Playwright and obtain a local axe-core script. Run browser harnesses serially with ports 8000 and 5173 free.

```bash
python -m pip install playwright
python -m playwright install firefox webkit
python frontend/tests/browser-phase187.py --engine chromium --python "$(command -v python)" \
  --axe /path/to/axe.min.js --output work/phase187f/chromium
```

With approved public network access and no competing load on the shared provider budget, run the existing-owner checks serially. The first probe samples resources on Linux and uses a 20-second cycle plus an immediate cache-reuse check. The second verifies native SDK delivery and one controlled reconnect. Keep raw evidence in scratch.

```bash
mkdir -p work/phase187f
(
  cd backend
  PYTHONPATH=. python tests/phase187f_provider_soak.py --allow-public-network \
    --seconds 1800 --output ../work/phase187f/provider-soak.json
  python tests/phase155b_live_readonly_acceptance.py --allow-public-network \
    --seconds 60 --reconnect --output ../work/phase187f/native-live.json
)
```

With a physical Redis binary, run `PYTHONPATH=. python tests/phase155a_redis_acceptance.py --redis-server /path/to/redis-server --output ../work/phase187f/redis.json` from `backend/`. It owns a disposable loopback Redis instance.

To roll back, stop both processes and preserve the local configuration and private data. Use a separate clean checkout of PR #103 merge `dd9e1488e027061a42cffd77e0761f8461de7226`, reinstall that revision's dependencies and repeat the loopback smoke with signing disabled. Verify the fresh Terminal identity and explicitly rerun research if needed. The fallback evidence is scoped by the [D–E report](PHASE18_7DE_ACCEPTANCE.md).

## Operator-controlled signed TESTNET acceptance

**SIGNED TESTNET — NOT RUN.** This requires a separately authorized task and designated operator. Confirm the following before scheduling that acceptance.

- Document approval for the operator, Testnet endpoint, existing supported market, maximum exposure and stop conditions.
- Use dedicated Testnet-only credentials in a private backend environment. Record the initial test inventory, balances and resting-order baseline.
- Verify concrete final authorization against the market, side, exact normalized wire price and size, reservation and lifecycle generation.
- Capture acknowledgements, rejection and unknown-order outcomes. Reconcile partial and complete fills, cancels, retained exposure and KEEP/REPLACE outcomes under the existing adapter contract.
- Halt new risk while an order is unknown. Exercise the manual kill, pending-order reconciliation and operator-controlled recovery.
- Reconcile fees and modeled/local accounting to Testnet receipts, clean up test orders and exposure, disable signing and retain redacted evidence. Keep credentials and operator authorization records out of the PR.
