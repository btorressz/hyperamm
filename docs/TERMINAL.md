# Phase 12 operator terminal

Phase 12 adds a React operator interface above the Phase 1–11.1 runtime. It
observes approved outputs and invokes the existing strategy configuration,
start/stop, manual kill and resume APIs. It never owns trading, risk, agent,
order-manager or accounting authority.

```text
Existing market → perp reference → AMM → inventory → market adaptation
    → Phase 9 supervision → Phase 8 firewall → FinalQuoteAuthorization
    → reconciliation → PAPER / guarded TESTNET → Phase 11.1 accounting
                                      ↓
                         versioned terminal observations
                                      ↓
                          React operator terminal
```

Perp context supplies the AMM reference upstream. The lineage view presents it
alongside transformations without pretending it is a second downstream price
transform. Phase 10 simulation/optimization remains a separate deterministic
research workload.

## Snapshot and WebSocket

`backend/app/terminal/models.py` defines `TerminalSnapshot`. Existing market,
strategy, fair value, virtual pool, inventory, adaptation, perpetual context,
references/consensus, agents/events, firewall/authorization/events, exposure,
drawdown, vault/accounting, risk, orders, fills and reconciliation fields remain.
Financial domain objects reuse their existing Pydantic models; composite
observability envelopes retain their upstream serialized contracts. Decimal
fields continue to serialize as strings.

The code-owned `TERMINAL_CONTRACT_VERSION` is `phase12-v1`; clients cannot select
it. Every `/ws/terminal` snapshot contains:

- `contract_version`: schema identity.
- `sequence`: process-wide increasing observation counter, including background
  samples and other readers. Gaps can represent intervening observations; they
  are not proof of lost exchange evidence and have no execution meaning.
- `emitted_at`: timezone-aware UTC observation/emission time, never client time.
  Within an observer, wall-clock rollback cannot reverse emission timestamps.
- `process_id`: code-generated process identity for restart detection.
- `session_id`: observation-context identity, reset on runtime session or changes
  to market, market-data mode, or execution mode. Sequence does not reset on a
  context change.

`strategy_quotes` exposes existing pre-agent output, `agent_quotes` post-agent
output, and `authorized_quotes` final output. Legacy `quotes` aliases the final
stage. Existing `FinalQuoteAuthorization` remains authoritative. Retained final
quote evidence does not authorize execution if the current authorization is
blocked.

Current-state payloads include at most 200 active orders and 100 recent closed
orders, 100 recent PAPER fills, 100 latest reconciliation actions, and 20 recent
notices per authority. `execution_summary` retains full runtime status counts,
PAPER fill count and actual gross filled notional. An explicit truncation flag
warns if the active-order view is capped. TESTNET fill aggregates are null.
`diagnostics` contains only testnet-enabled and firewall-enabled booleans.

Public diagnostic fields (`error`, `message`, reasons, and warnings) in terminal
snapshots/events and corresponding REST observations use a shared sanitizer
before outward serialization. Within those
selected fields, nested metadata strings are sanitized too. Complete labeled
credentials, including Authorization scheme + credential values, are redacted;
provider URLs are replaced with `[provider URL]`. Public diagnostic text remains
bounded to 500 characters. Domain identifiers and fingerprints are preserved;
this boundary does not mutate the underlying trading or risk decisions.
No ledger, chart-history collection, simulation trace, optimizer results,
credentials, signed payloads or environment dump is streamed.

WebSocket disconnects are monitored alongside the sender; both tasks are
cancelled when either exits. One terminal WebSocket remains the primary live
transport. A one-second runtime observation task gathers history without a
connected browser; it only reads current outputs and is cancelled at shutdown.

## History

`TerminalHistory` stores at most **3600** points in a deque, sampled at most once
per second. Points include observation sequence/time, mid/fair/strategy-reference,
mark/oracle/consensus, best authorized bid/ask, position/inventory ratio, risk state,
agent regime, equity/peak equity, net PnL, drawdown and capital utilization.
Simulated and execution-mode labels accompany observations.

No future source timestamps are used; unavailable/stale market, perpetual,
inventory and accounting economics remain null. History is a charting observation,
not a replay dataset, ledger, persistent exchange store or accounting authority.
Equal timestamps are allowed with strictly increasing sequences; reverse time
and non-increasing sequences are rejected. Context changes clear retained history.

`GET /api/v1/terminal/history?range=session&limit=600` supports `1m`, `5m`,
`15m`, `1h`, and `session`. Limits are **1–1000**; invalid limits/ranges return
HTTP 422. Windows are relative to the latest retained observation. Responses
include retained span, oldest/latest times, session identity and available ranges.
The chart disables ranges until the retained session supports them. A requested
long window returns only existing observations. Deterministic decimation preserves
the selected span when it exceeds the response limit; it never invents candles.
There is no database dependency.

## Structured events and system health

`GET /api/v1/terminal/events?limit=100&category=RISK` returns newest-first
normalized events. The event deque is capped at **500**, queries at **1–500**,
and deduplication memory at 1000 identities. Categories are MARKET, REFERENCES,
STRATEGY, AGENTS, RISK, EXECUTION, ACCOUNTING and SYSTEM. Events combine existing
risk/agent/accounting notices, provider/feed/strategy/health transitions,
order-status changes and reconciliation-action changes. Event fields are time,
category, previous/current state, normalized message, version/reference and
simulation label. Credential-shaped values and provider URLs are redacted;
raw server logs are never exposed. Both terminal HTTP APIs are GET-only.

`SystemHealthState` normalizes HEALTHY, DEGRADED, HALTED and UNAVAILABLE across
market feed, perpetual context, references/consensus, RedStone transport, agents,
risk, final authorization, execution, venue reconciliation, accounting,
execution/accounting consistency and strategy. VERIFIED reference consensus and
READY agents map to healthy evidence; VERIFIED consensus additionally requires
its retained supporting sources to remain fresh at emission. Warmup/insufficient/disabled/unavailable
states retain their actual meaning. PAPER venue reconciliation is explicitly
inapplicable. Manual kill, risk HALT, blocked final authorization and accounting
divergence remain visible. Any required missing evidence prevents an aggregate
HEALTHY claim. This aggregation is **display-only**, never a firewall or bypass.

## Pages

| Page | Operator purpose |
|---|---|
| Dashboard | Price/liquidity, L2, compact approved controls, KPIs, AMM distribution, inventory skew, transformations, agents, recent execution and health |
| Markets | Market microstructure, BBO, venue/perp prices, funding/OI/basis, volatility/imbalance, feed freshness and provider status; no raw JSON feed panel |
| Strategy | Current virtual pool, reference, inventory/adaptation/context, lineage, all three quote stages and final authorization |
| AMM Settings | Existing advanced configuration, dirty edits preserved across frames, Save/Reset, busy/success/error states and context/execution warnings |
| Execution | Open orders, bounded order history, PAPER fills, unknown/rejected counts, quality/churn, reconciliation and explicit TESTNET unavailability |
| Risk | Immediate manual kill, confirmed resume, firewall, references, exposure, capital/drawdown gauges, consistency, fingerprint and transitions |
| Supervisory Agents | Regime, toxic-flow, execution-quality and deterministic supervisor evidence, health/confidence, factors, reasons and versions |
| Vault | Existing authoritative Phase 11.1 summary, PnL, immutable ledger, consistency/provenance plus bounded equity/peak, drawdown, capital and position charts |
| Analytics | Session economics, exposure, fill/notional/capture/markout/churn evidence and retained risk/regime observation distributions; offline results remain separate |
| Simulation & Optimization | Existing offline deterministic scenario/grid workflow, loading/error states, baseline/training/validation comparisons; no apply/deploy control |
| Logs | Filterable structured event timeline |
| Settings | Browser density, default chart range and bounded view-size preferences; safe backend diagnostics and subsystem health |

The fixed sidebar is manually collapsible on desktop and automatically becomes
compact below 1100px. Header exposes the current perpetual market, mid, mark,
HL oracle, funding, OI, connection/data/execution/running/risk/kill state. Emergency
kill has no confirmation delay; resume requires confirmation and backend checks.

## Charts and lineage

Lightweight Charts instances are created once per mount and resized with
ResizeObserver. The price chart loads bounded backend history, incrementally
updates live series using `emitted_at`, and supports eight display toggles. No
client clock fabricates market observations. Sparse timestamps and null economics
stay sparse. History refreshes every five seconds and replaces bounded series;
if history retrieval fails, current-state updates remain visible with an error.

Liquidity and inventory charts plot backend quote size versus price/distance.
RAW AMM uses retained `neutral_price`/`neutral_size`; strategy and authorized
modes use their actual stages. Levels suppressed before retained lineage are not
reconstructed. Inventory bars distinguish BID/ASK even when distances overlap.

The level-selectable pipeline displays retained neutral, inventory/pre-market, pre-agent,
pre-risk, agent/final and resting-order evidence. Missing stage size/price is
unavailable. It reports factors, survival/blocking state and authorization
fingerprint. Some lineage labels are approximate (Audit 1.0 A1-021); retained
fields do not prove independent evidence at every stage. Strategy attribution uses actual shifts and multiplicative factors;
it does not invent additive basis-point contributions or TypeScript AMM formulas.

L2 remains Hyperliquid data in LIVE and explicitly simulated in DEMO. Spread,
spread bps, seven-level cumulative depth/shading/imbalance, sequence and backend
freshness are presentation arithmetic, never trading policy.

## Connection and error behavior

The store tracks last valid reception time, sequence, process/contract identity,
payload error, connection notice and reconnect attempts. Unsupported contracts,
malformed JSON or required nested shape errors show PAYLOAD ERROR while retaining
the last valid snapshot. Non-increasing process sequences are rejected. Restart
and observation gaps are visible; neither authorizes an action. A page boundary
contains unexpected render failures.

After five seconds without valid state, the UI shows TERMINAL STALE and
reconnects with 1.5s/3s/6s/10s bounded backoff. A valid frame resets backoff.
The browser clock is used only for connection freshness. Backend market,
perp, reference and accounting staleness remain independent subsystem labels.

Layouts compress at 1100–1439px, collapse navigation and stack panels at
768–1099px, and remain vertically usable below tablet width. Tables scroll inside
panels. Buttons have focus/disabled/error states, controls have semantic labels,
and critical statuses contain text rather than relying on color.

## Truth boundaries and limitations

### Emission-time source provenance (Audit 1.0 A1-022)

Terminal `emitted_at` freshness differs from source-data freshness, provider
transport state, and the last reference/risk decision state. A current terminal
WebSocket frame can carry stale retained market evidence. The terminal clock
ages serialized observation copies before health aggregation, validation and
history creation; it never evaluates providers/consensus or mutates trading
objects, versions, final authorization or fingerprints.

Perpetual context becomes observationally stale when `emitted_at - updated_at`
exceeds the active strategy `perp_context_stale_after_seconds`. Reference
`age_ms` is recomputed from the retained price's `source_timestamp`, never from
the terminal frame timestamp or the old evaluation age. Existing thresholds apply:

| Retained evidence | Observation stale threshold |
|---|---|
| RedStone LIVE_WS | `settings.redstone_stale_after_seconds` |
| RedStone PUBLIC_HTTP | `settings.redstone_public_http_stale_after_seconds` |
| Kraken | `settings.kraken_stale_after_seconds` |
| CoinGecko | `settings.coingecko_stale_after_seconds` |
| Hyperliquid native oracle / mark (including DEMO native context) | Active perp-context threshold |
| Hyperliquid midpoint | Active market-data service threshold |
| DEMO external reference evidence | Corresponding simulated market-observation threshold |

Missing/invalid/naive timestamps cannot be fresh. Perp/native/DEMO/public HTTP
future timestamps are stale; live external evidence retains the existing
five-second provider clock-skew tolerance. Native Hyperliquid context age is
local receive/observation age, not certified upstream exchange age.

`status`, `transport`, and `transport_quality` retain the last provider state.
`stale` and `healthy` describe source freshness at this emission. Thus retained
`status=HEALTHY` can coexist with `stale=true`, `healthy=false`; the source table
labels these separately and reports “Source age now”. The RedStone transport
health row includes last known provider/transport state in its reason, while a
HEALTHY observation also requires retained source freshness; a provider state
alone does not establish current transport connectivity.
Consensus confidence, statuses and price remain the last evaluated decision;
no observational quorum/outlier calculation occurs. Current consensus support
requires every retained `eligible_providers` input to be available and fresh.
An aged-out VERIFIED decision remains VERIFIED but current consensus health is
DEGRADED and its price is suppressed from new history and current-price surfaces.
Fresh supported DEGRADED decisions can still supply a price.

New history and live chart observations suppress stale mark, oracle and strategy
reference prices with `None`/`null`, and suppress unsupported consensus prices.
Header/Markets/current risk-price metrics follow the same boundary. Intentionally
retained diagnostic values are labeled STALE. Old history remains unchanged;
no values are interpolated. Backend sequence identity, response-watermark merge,
bounded observations and controlled chart fitting from A1-020 remain intact.
The `phase12-v1` schema is unchanged. Terminal health remains observational;
execution callbacks retain their own freshness and authority checks.

- History/events are in-memory current-session observations; no durable 24-hour
  statistics, persistence or fabricated historical candles.
- PAPER execution/accounting and DEMO evidence stay explicitly SIMULATED.
- TESTNET remains guarded; normalized TESTNET fill ledger, markouts, realized
  per-fill PnL, fees and funding details remain unavailable where unsupported.
  The Execution page says “TESTNET fill history unavailable”.
- Per-fill realized/fee deltas are omitted without an explicit immutable ledger
  match. Session aggregates and observations never become accounting authority.
- There is no production-mainnet execution, wallet/custody, deposits, money
  movement, investor accounting or autonomous optimization deployment.
- External-provider Phase 8 acceptance and Phase 9 acceptance remain separate.
  Their roadmap review statuses are unchanged. All Phase 1–12 implementation
  scopes exist, but the whole roadmap is not declared fully accepted/COMPLETE.
- System health is observational; existing authority checks remain downstream.
- Price-chart series retain the queried backend history plus live observations.
  Each browser series is capped at 1000 points, including during history API
  outages. The memory-bound GET history defines retained chart windows.
- The original visual mockup was not included as an image in this request or
  repository. Styling follows the described dark institutional terminal layout.

Local acceptance evidence is recorded in the Phase 12 roadmap entry. No signed
TESTNET trade is required or performed by the acceptance workflow.

## Current audit qualifications (2026-10-07)

All 12 pages above are active; historical Phase 12 local/browser acceptance is
recorded at merge on 2026-10-06, not a fresh external-provider acceptance claim.
See [Audit 1.0](../AUDIT_REPORT_1.0.md): A1-020 qualifies history/live ordering,
A1-021 qualifies exact lineage, and remaining authority/provider/operational
issues remain separate from UI observability. A1-009 keeps the local deployment
boundary. Lifecycle A1-019 blocks recovery until publication completes and normal
runtime evidence passes; failure requires restart and does not disable kill or
cancellation. Terminal health is observational and cannot restore quote authority.

The full REST/WebSocket inventory is listed in [README](../README.md#api-surface),
including terminal history/events and vault/accounting summary, position, PnL,
ledger and event routes. No new route or terminal contract is added by A1-019.

## Optional Redis transport

[Redis infrastructure](REDIS.md) can mirror the engine's existing serialized
`phase12-v1` frames through Pub/Sub and a process/session TTL cache. The runtime
still owns sequence, session and emission time; `TerminalService`, history and
events are unchanged. Relays validate the full contract and identity, reject
stale/duplicate/regressed observations and preserve original bytes. Redis mode
adds shared expiring WS admission; local mode keeps its original 32-client cap.
Loss degrades Redis observability/admission without changing trading authority.
No Streams/replay, remote access or multi-worker deployment is enabled.
