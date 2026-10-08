# Repository-specific Redis design (before implementation)

Redis is **EPHEMERAL DISTRIBUTED INFRASTRUCTURE**. This design was written
before implementation after reviewing runtime composition, lifecycle and deployment,
terminal service/history/contract and browser consumers, simulation API/executor/service,
market history, references, agent telemetry, risk, execution and accounting state.

## In-memory state inventory

| Inspected owner/state | Classification | Placement/reason |
| --- | --- | --- |
| `HyperAmmRuntime`: lifecycle/execution locks, strategy/config, pool and quote stages, inventory/perp/reference versions, firewall decisions, expected versions and final authorization | AUTHORITATIVE | Engine only. Order permission requires the existing deterministic execution path and locks. |
| `MarketDataService`, `MarketPriceHistory`, perp/provider `EvidenceState`, consensus fingerprints/versions, accepted L2 and freshness | AUTHORITATIVE | Feed normalization and rolling accepted observations influence strategy/risk; Redis cannot supply these inputs. Provider sockets/tasks are LOCAL-CACHE/lifecycle resources. |
| `AgentTelemetryStore`: fill identities/provenance, markouts, reconcile/action windows, order statuses; supervisor signatures, regime/recovery state | AUTHORITATIVE | Decision-critical telemetry stays synchronous and engine-owned, despite bounded retention. |
| PAPER `OrderHistory`/`FillStore`, pending fill evidence, consumption receipts and cumulative positions; TESTNET tracked orders, verification pins, account/position truth | AUTHORITATIVE + DURABLE-FUTURE | Economic truth stays local; future durable receipts/lifecycle/fills/reconciliation belong in PostgreSQL. Redis is never recovery. |
| `AccountingService`/`AccountingLedger`: immutable rows, idempotence identities, fill evidence, average-cost position, cash/fees/funding/peaks/reservations/consistency/error latch | AUTHORITATIVE + DURABLE-FUTURE | Financial authority stays local; future durable ledger/session recovery belongs in PostgreSQL. |
| `RiskStatus`/`KillSwitch`, firewall hysteresis, risk and authorization records | AUTHORITATIVE + DURABLE-FUTURE | Kill and execution permission remain local. Future audits persist in PostgreSQL, never Redis. |
| Canonical strategy/agent/risk/accounting configuration and revisions; operational sessions | AUTHORITATIVE + DURABLE-FUTURE | No Redis reads may mutate live configuration; future revisions/session records belong in PostgreSQL. |
| `TerminalService` process/session/sequence, history/event deques/dedupe/transitions | EPHEMERAL-DISTRIBUTABLE observations, backend-owned identity | Keep the service/history untouched. Distribute only serialized `phase12-v1` snapshots. No Streams/replay needed for the current latest-only UI. |
| Runtime serialized latest snapshot, one-slot client queues; React Zustand state/history/socket retry state | LOCAL-CACHE / EPHEMERAL-DISTRIBUTABLE | Extract local fanout; optionally mirror complete snapshots through Redis Pub/Sub and an explicit-TTL process/session cache. Browser contract stays identical. |
| `SimulationExecutor` thread pool/lock/busy/closed flags | LOCAL-CACHE / EPHEMERAL-DISTRIBUTABLE admission | Keep the one-thread local executor. Optional shared expiring research admission and short-lived job status/result mirrors; no remote job queue or new worker topology. |
| Simulation datasets, trace/metrics/candidate evaluations and per-run fresh PAPER engine | Isolated AUTHORITATIVE research calculation; results EPHEMERAL-DISTRIBUTABLE / DURABLE-FUTURE | Deep-copy inputs, reuse existing PAPER/DEMO forcing. Cache results using process/session, complete input digest and engine version. Future durable research metadata/results belong in PostgreSQL. |
| Terminal client cap and infrastructure worker liveness | EPHEMERAL-DISTRIBUTABLE | Shared token leases expire abandoned clients/jobs; TTL heartbeat is operational only. |

## Justified seams

1. Keep `TerminalService` unchanged. Extract existing latest-only local fanout
   into `InProcessTerminalTransport`. An optional `RedisTerminalTransport` receives
   serialized snapshots through a one-slot nonblocking publisher queue; separate
   Redis publisher/subscriber tasks reconnect. Relays validate the complete model,
   pin the current engine process/session, reject stale/future, duplicate/regressed
   sequence/time and preserve the original wire bytes. They never observe domain state.
2. WebSocket Redis mode uses namespace-wide bounded token admission with server-time
   TTL leases and renewal. Failed admission/renewal closes the relay conservatively.
   Local mode retains the 32-client cap and existing one-slot behavior.
3. One TTL worker heartbeat identifies the infrastructure role and process. Optional
   research coordination wraps the existing executor with renewable admission, opaque
   job IDs, TTL status and TTL result mirrors; HTTP responses remain synchronous.
   Request cancellation retains admission until the actual thread completes.
4. Disabled Redis creates no client/network tasks. Optional startup failure is
   sanitized and retried; local engine/publication continues, while Redis-dependent
   resource admission fails closed. `redis_required` fails startup clearly before
   engine services start. Runtime loss affects observability/research admission only.

## Explicit exclusions

No engine distribution, Redis execution locks, Redis-sourced prices/telemetry,
canonical config, kill latch, accounting, authorization, economic receipts, recovery,
PostgreSQL implementation, custody, mainnet, new agents, changed economics,
fingerprints/risk thresholds, public deployment, multi-worker enablement or CI workflows.
The deployment guard and `LocalOnlyBoundary` stay intact. Redis Pub/Sub and caches
are lossy observations, not an audit journal. A future separately reviewed topology
must have exactly one authoritative engine and many authenticated API/WS/research
workers; adding transport does not make that topology supported today.
