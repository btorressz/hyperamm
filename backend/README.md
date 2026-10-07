# HyperAMM Backend

FastAPI backend for HyperAMM Phases 1–4. It separates normalized market data, AMM mathematics, quote compilation, risk, and execution. The default configuration is `DEMO` market data + `PAPER` execution so no wallet is required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Public live Hyperliquid market data can be enabled with `MARKET_DATA_MODE=LIVE`. Signed testnet execution additionally requires `EXECUTION_MODE=TESTNET`, `ENABLE_HYPERLIQUID_TESTNET_ORDERS=true`, and a testnet signing key supplied through environment variables. Mainnet execution is intentionally absent.


### Audit 1.0: local deployment boundary (A1-009)

HyperAMM currently supports **local, single-operator, research-only** use with
one backend worker. PAPER is the default; TESTNET still requires explicit mode,
order-enable flag and testnet credentials. No mainnet execution is supported.
Bind to loopback, keep the frontend local, and do not expose the backend through
public/LAN interfaces, reverse proxies, tunnels or port forwarding. Remote/public
deployment is unsupported. CORS is browser policy, **not authentication**.

Startup rejects non-loopback `--host`/`--bind` and `UVICORN_HOST`, and worker
counts other than one in `--workers`/`-w`, `WEB_CONCURRENCY` or `UVICORN_WORKERS`.
HTTP and WebSocket requests require a loopback peer, local Host, and local browser
Origin when present; forwarded headers do not grant access. These checks do not
make a loopback proxy or separately launched backend processes supported. Use
one instance only; there is no multi-process coordination. Local Uvicorn reload
remains supported. Starlette's in-process test transport is accepted for tests.

Future remote deployment requires operator authentication/authorization,
request/resource admission, WebSocket client controls, TLS/proxy policy, audit
logging, and a secrets lifecycle before exposure. These are future work, not
features provided by this hardening.

### Audit 1.0: terminal publisher (A1-010)

One runtime publisher observes terminal state on a one-second cadence, caches
and serializes the latest `phase12-v1` snapshot, and fans it out read-only.
Readers never observe domain state or advance sequence/history/events.
Each client has a one-slot queue: newer snapshots replace pending older ones.
At most 32 terminal clients may subscribe; sends time out after five seconds,
and disconnects cancel tasks and release subscriptions. Sequence gaps can reflect
coalescing, not missing trades. Process/session identity and history/event APIs
retain their existing contract. Before the first publication, readers wait for
the publisher; a domain change appears on its next publication.
