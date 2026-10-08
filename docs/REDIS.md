# Redis: EPHEMERAL DISTRIBUTED INFRASTRUCTURE

Redis distributes observations and coordinates bounded research/UI resources.
The in-process engine retains trading/risk/execution/accounting authority.
The [pre-implementation state inventory and design](REDIS_DESIGN.md) classifies
existing in-memory state; bounded collections were not automatically migrated.

```text
                    AUTHORITATIVE ENGINE
                    one execution authority
                             |
                Strategy -> Risk -> Authorization
                             |
                         Execution
                             |
                         Accounting
                             |
              +--------------+----------------+
              |                               |
         PostgreSQL                         Redis
     FUTURE / NOT IMPLEMENTED              ephemeral
              |                               |
       ledger / fills                  terminal Pub/Sub
       receipts / audit                worker heartbeat
       recovery / configs              WS/research admission
       durable research                TTL status/result mirrors
              |                               |
              +---------------+---------------+
                              |
                  API / WS -> React observations
```

Today one local API process still owns one `HyperAmmRuntime`. Before: a one-second
publisher serialized a snapshot and copied it into local one-slot client queues.
After: local mode does the same through `InProcessTerminalTransport`. With Redis
opt-in, a separate publisher mirrors those bytes into Redis; a validated subscriber
relays them to local WebSockets. Future API/WS/research workers can reuse the
transport/coordination seams, but no separate worker entrypoint, election, remote
job queue, public deployment or multi-worker support is introduced here.

## Configuration and installation

```bash
cd backend
pip install -e '.[test,redis]'
```

The maintained official `redis.asyncio` client is an optional runtime extra.
Local PAPER needs neither the extra nor a Redis server. Tests use an in-memory
`fakeredis` server with Lua support and require no live Redis or venue.

| Setting | Default | Purpose |
| --- | --- | --- |
| `REDIS_ENABLED` | `false` | Opt into terminal distribution and shared WS admission/heartbeat. |
| `REDIS_REQUIRED` | `false` | Fail startup if Redis cannot be reached; requires enabled mode. |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Backend-only connection URL; `rediss://` supported. Hidden in Settings repr and sanitized in diagnostics. |
| `REDIS_NAMESPACE` | `hyperamm` | Bounded alphanumeric/underscore/hyphen key prefix. Use a separate namespace per installation. |
| `REDIS_TERMINAL_CHANNEL` | `terminal` | Bounded channel component, scoped by engine process ID. |
| `REDIS_DEFAULT_TTL_SECONDS` | `30` | Explicit cache/status TTL, 10–300 seconds. |
| `REDIS_WORKER_HEARTBEAT_TTL_SECONDS` | `15` | Worker and admission TTL, 10–300 seconds; renew every TTL/3. |
| `REDIS_OPERATION_TIMEOUT_SECONDS` | `1` | Bounded Redis I/O deadline, greater than zero and at most 5 seconds. |
| `REDIS_RESEARCH_ENABLED` | `false` | Opt into shared research admission and TTL status/results. Requires Redis enabled. |

Provision Redis separately on a trusted connection. The namespace/channel and
process/session pinning are identity isolation, not authentication. Redis access
must be restricted to trusted operators/workers; this adds no remote authentication.
Keep the API loopback-bound and single-worker. `LocalOnlyBoundary`, launch checks,
TESTNET opt-in and all existing local deployment limits remain unchanged.

## Terminal behavior

The existing engine observation task owns `phase12-v1`, process/session identity,
sequence and `emitted_at`. `TerminalService`, chart history and event retention are
unchanged. Redis receives complete serialized normalized/provenance envelopes,
including nested market/reference/risk/agent/accounting observations; these copies
are display data and are never read back by strategy or authority.

The engine calls a nonblocking one-slot `offer`, with no Redis I/O on that path.
The Redis publisher caches with an explicit TTL under
`namespace:terminal-latest:process_id:session_id`, then publishes the same bytes to
`namespace:channel:process_id`. Separate publisher/subscriber tasks retry after
one second. A reconnect subscribes before loading the current session cache to
avoid a cache/subscribe gap. Full Pydantic contract validation rejects malformed,
oversize (>4 MB), foreign process/session, future or older-than-five-second frames.
Accepted sequence must increase and emission time must not regress, including
across session changes. Duplicates are harmless. Wire payload fields/timestamps
are never rewritten. A delayed outage frame is discarded, not re-dated.

Every browser still has a one-slot queue, 32 clients per process, a five-second
send timeout and disconnect cleanup. Redis mode also uses a namespace-wide cap
of 32 expiring tokens. A server-time Lua transaction removes expired tokens and
admits/renews a UUID token atomically. Expired tokens cannot be resurrected by
renewal; crashes or failed releases recover capacity by TTL. Failed admission
closes with 1013; renewal failure closes an existing connection conservatively.
The browser's existing freshness watchdog remains in force.

No Redis Streams or observation replay is added: the current UI uses latest-only
snapshots and the existing session history APIs. Redis observations are lossy,
not a durable audit trail, execution journal or immutable accounting history.

## Research and liveness

The default `SimulationExecutor` remains one non-queued `ThreadPoolExecutor`
worker with its original busy flag and HTTP 429. Redis research opt-in wraps that
same executor: namespace-wide renewable admission allows one active research job;
UUID hex IDs are opaque, bounded and collision-resistant. Inputs are deep-copied
before admission; existing `SimulationService` still forces PAPER/DEMO and creates
fresh simulation state. Optimizer output is never applied to live config.

Existing `/simulation/run` and `/simulation/optimize` request/response JSON stays
synchronous and unchanged. Shared contention returns 429; unavailable Redis
admission returns 503. There are no public job management/cancellation endpoints.
Operational Redis status mirrors have RUNNING/COMPLETED/FAILED/LEASE_LOST states;
RUNNING TTL is refreshed while the job runs. Status keys include process/session
and job ID. Results include engine version, full detached-input digest and full
result digest (including dataset/run provenance), and have explicit TTLs. These
are mirrors only: no cache lookup can substitute a result for a fresh execution.
Internal UUID IDs are for operational Redis correlation, not API identifiers.

HTTP cancellation does not release admission while the thread is running;
shutdown waits for detached work. If a lease expires during an outage, isolated
research may overlap in a future worker topology, and its status/results are
best-effort. No exactly-once or durable job guarantees are claimed. Lease presence
never authorizes trading. Local calculation can finish during Redis loss; status
or result mirroring can be unavailable without changing that calculation.

A TTL worker key `namespace:worker:process_id:worker_id` records operational
API/WS/research liveness. Expiry is not evidence that an execution leader may be
replaced. No heartbeat/lease is an execution authorization or leader election.

## Failure and authority boundaries

`GET /api/v1/health` includes a read-only `redis` object: `enabled`, `required`,
`research_enabled`, `status` (`DISABLED`, `CONNECTED`, `DEGRADED`), sanitized
`last_error`, and UTC `last_success_at` (null before the first success).
Enabled infrastructure starts DEGRADED until an actual Redis operation succeeds;
an operation/subscriber failure marks it DEGRADED, and a later successful operation
clears the error and records recovery. Shutdown clears the connected state.
This is the last observed operation outcome, not a live probe or a guarantee that
every Redis function/subscription is healthy. The timestamp lets operators assess
recency; the health request itself performs no Redis I/O. The overall API status
stays `ok` during Redis degradation. This status never enters the terminal contract,
risk firewall, authorization, kill switch, execution or accounting paths.

Disabled mode creates no Redis client/tasks and preserves local publication and
simulation behavior. Optional startup unavailability logs a sanitized degradation,
starts the local engine normally and retries distribution. Local cached publication,
REST observations and kill/cancel still work; Redis-dependent WS/research admission
fails closed. Required-mode startup failure is explicit and happens before engine
services start. Missing optional client installation or invalid configuration is
an actionable startup error, not reported as a healthy connection.

Runtime disconnects degrade distribution/cache/heartbeat/admission only. No Redis
await is added to execution/lifecycle/accounting/kill lock ordering. No Redis reads
can populate `FinalQuoteAuthorization`, authoritative positions, ledger balances,
kill state, Phase 8 evidence or canonical configuration. A valid Redis snapshot
may display an authorization observation; that observation is never permission
to execute. No authority modules, formulas, thresholds or fingerprints are changed.

Future PostgreSQL owns durable ledger rows, execution receipts, order/fill/lifecycle
records, risk/authorization audits, config revisions, reconciliation/session records,
durable research metadata/results and restart recovery. PostgreSQL is **not
implemented** in this task. Redis loss/restart cannot recover financial truth.
