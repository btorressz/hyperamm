# Terminal Observation Domain

The `terminal` package is Phase 12's backend observability layer. It turns existing runtime state into a versioned operator contract plus bounded history/events without becoming trading authority.

## Position in the architecture

```text
Phase 1–11 runtime authorities
        ↓
TerminalService
        ↓
TerminalSnapshot (phase12-v1)
        ├──→ /ws/terminal
        ├──→ bounded session history
        └──→ structured terminal events / system health
        ↓
React operator terminal
```

## Files

| File | Responsibility |
|---|---|
| `models.py` | Code-owned terminal contract version, `TerminalSnapshot`, history points, events and health models. |
| `history.py` | Bounded in-memory current-session history, supported ranges and deterministic response sampling. |
| `service.py` | Builds observations, assigns process/session/sequence metadata, appends safe history, aggregates health and normalizes/redacts structured events. |
| `__init__.py` | Public terminal exports. |

## Snapshot semantics

Every snapshot includes:

- `contract_version = phase12-v1`;
- process ID and session ID;
- process-wide monotonically increasing observation sequence;
- timezone-aware emission time;
- market/strategy/AMM/inventory/perp/reference/agent/risk/accounting/execution state;
- pre-agent `strategy_quotes`, post-agent `agent_quotes`, and final `authorized_quotes`;
- observational `system_health`.

Legacy `quotes` remains an alias for the final authorized stage for compatibility.

## History and events

History is bounded, in-memory and current-session only. It is for charts/observability, not trading evidence, replay or accounting. Structured events combine normalized upstream transitions while redacting credential-shaped text; raw Python logs are not exposed.

## Authority boundary

`TerminalService` consumes serialized outputs and must not:

- submit/cancel/replace orders;
- alter risk state;
- mutate accounting economics;
- authorize quotes;
- become a second strategy engine.

System health is display-only. The runtime's underlying risk/authorization/accounting state remains authoritative.

## Connections

- One runtime publisher observes upstream state once per second.
- `runtime.terminal_state()` reads a copy of the latest cached snapshot (or `None` before publication).
- `api.websocket` sends pre-serialized publications through one-slot coalescing queues; slow sends time out and disconnects release subscriptions.
- `api.terminal` exposes history/events.
- React validates `phase12-v1` and uses sequence/process/session metadata for stale/restart/gap diagnostics.
