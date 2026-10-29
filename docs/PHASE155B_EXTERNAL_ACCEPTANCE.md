# Phase 15.5B — Genuine public SDK acceptance

**BLOCKED in this Cloud environment. Local/Replit/macOS: NOT RUN.**
This does not imply a Hyperliquid outage. Offline fixtures, including the real
Chromium captures, are not genuine market delivery or trading-readiness evidence.

On October 29, 2026 the opt-in runner imported official SDK **0.24.0** and attempted
one native public metadata request through the unchanged configured proxy.
It received **ProxyError: configured proxy CONNECT returned 403 Forbidden**.
The attempt stopped before WebSocket construction/subscriptions or L2/context
requests. No VPN, alternate endpoint, route/proxy/TLS change, signing key, wallet,
private account operation or signed TESTNET order was used.

[Sanitized actual JSON](acceptance/phase155b/external-results.json) records
SDK import PASS, metadata BLOCKED, no observations or subscriptions, 0.059s.
The metadata helper closes its owned HTTP session in `finally`; streaming SDK
cleanup is NOT APPLICABLE because no streaming client was constructed.

| Genuine check | This execution |
| --- | --- |
| Official SDK import/version | PASS — 0.24.0 |
| Native BTC/ETH/SOL metadata | BLOCKED — proxy CONNECT 403 |
| Public L2 / perpetual-context REST | NOT RUN — metadata prerequisite blocked |
| Six actual WS subscriptions and accepted native messages | NOT RUN |
| Genuine source/receipt attribution | NOT RUN |
| Controlled venue disconnect/resubscribe and cleanup | NOT RUN |
| Browser after genuine venue disconnect | NOT RUN — offline production-service path separately passed |
| Developer's normal local environment / Replit | NOT RUN — no such runtime was attached |
| Independent macOS / long venue soak | NOT RUN |
| Trading / signed TESTNET / mainnet readiness | NOT APPLICABLE to this runner |

## Permitted-environment fallback

Use an existing environment with legitimately permitted venue access and Python
3.12+. No signing credential or application security change is needed. Run from
the reviewed branch in a clean clone/worktree; preserve normal proxy/TLS policy.
Install the existing supported dependency range and reproduce the accepted schema
version explicitly:

```bash
python3.12 -m venv work/phase155b-venv
source work/phase155b-venv/bin/activate
cd backend
python -m pip install -e '.[test,ml,redis,yahoo]'
python -m pip install 'pydantic==2.14.1'
python -m pip check
python tests/phase155b_live_readonly_acceptance.py \
  --allow-public-network --seconds 20 --reconnect \
  --output ../docs/acceptance/phase155b-permitted/external-results.json
```

The runner uses the production owned official SDK observation client/service.
It validates live native metadata and REST responses, records each successful
subscription and accepted stream snapshot, preserves actual L2 event time and
unknown context event time, optionally closes the public socket and waits for a
new validated generation, and invokes retained owner shutdown. It reports
post-shutdown API status, worker/task/subscriber counts when that stage is reached.
Requested delivery window is bounded to 5–120 seconds, with finite HTTP/connect/
shutdown budgets; it is not a long-soak certification. Exit 0 means PASS; exit 2
means BLOCKED or FAIL, requiring review of the JSON. No pytest discovery runs it.

Review the actual resulting JSON before claiming Replit/local acceptance. Record
reviewed commit, OS/Python/SDK, duration, generations, six intended subscriptions,
all three real-market snapshots, event/receipt attribution and cleanup results.
A network/venue denial remains BLOCKED and ends that attempt. Do not use alternate
routes or geographic bypasses. Passing public observation never authorizes orders.

For offline lifecycle reproduction use:

```bash
python -m pytest -q tests/test_phase155b_*.py
python tests/phase155b_soak_runner.py --seconds 30 --max-cycles 1000 \
  --output ../docs/acceptance/phase155b-permitted/soak-results.json
```

Those results remain explicitly OFFLINE FAKE SDK evidence even when executed in
Replit. Independent macOS additionally needs the full regression/browser/Redis
commands in [15.5A's platform fallback](PHASE155A_MACOS_FALLBACK.md), adapted to this
branch and the actual new counts. Signed TESTNET gates stay outside this work.
