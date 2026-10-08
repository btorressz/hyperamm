# Phase 11: deterministic research vault/accounting

Phase 11 accounts for execution; it has no execution authority. It is a
non-custodial, in-memory research capital layer for perpetual markets. It does
not implement money movement, investor accounting, shares or fund fees. Phase 12
remains planned.

## A1-026 operational and custody boundary

The Phase 11/11.1 vault is a **non-custodial, in-memory research accounting
system**. Its ledger and session identities describe the active research process;
they are not a bank/exchange statement, custody ledger or durable cross-restart
strategy book.

PAPER economics are simulated under the documented fee/funding assumptions.
TESTNET exposes only the authoritative account/position fields currently available
through the existing integration and keeps unsupported cash, realized PnL, fee,
funding and capital-availability fields partial or null. HyperAMM does not infer
missing economics from zero.

There are no deposits, withdrawals, transfers, investor shares, fund fees or
custodial asset flows. Durable journals, restart/order recovery and attribution of
external account movements would require a separately reviewed operational scope;
they are not implied by the current append-only in-memory ledger.

## One accounting authority

```text
Fill / normalized perp and account evidence
                   ↓
           AccountingService
                   ↓
 immutable AccountingEvent → append-only AccountingLedger
                   ↓
      average-cost PositionAccounting + fees/funding
                   ↓
       PnlBreakdown → VaultSnapshot
                   ↓
 Phase 8 risk → FinalQuoteAuthorization → pre-transmission check
                   ↓
         read-only REST / WebSocket / Vault page
```

Runtime PAPER and Phase 10 simulation instantiate the same `AccountingService`. PAPER inventory and simulation ending inventory consume its position record; the existing adapter FillStore and fill callback remain the execution evidence source.
The only average-cost fill formula is `accounting/pnl.py:apply_trade()`. The
legacy `risk/firewall.py:paper_pnl()` delegates to that implementation and remains
a gross-PnL compatibility function for earlier callers. Runtime, simulation
engine and simulation metrics do not call it. Metrics consume the final vault
snapshot instead of calculating another equity or PnL ledger.

## Configuration and clocks

`AccountingConfig` is separate from `StrategyConfig`, immutable, forbids unknown
fields, and rejects nonfinite financial values. Defaults:

| Setting | Default |
|---|---|
| enabled | true |
| paper_initial_equity_quote | 100000 |
| paper_fee_model_enabled | false |
| paper_maker_fee_bps / paper_taker_fee_bps | 1 / 3 |
| paper_funding_accounting_enabled | false |
| paper_funding_interval_seconds | 3600 |
| accounting_stale_after_seconds | 30 |
| ledger_max_entries / event_max_entries | 10000 / 250 |
| max_capital_utilization | 1 |

Live accounting uses the existing UTC clock. Simulation injects `SimulationClock`
and supplies scenario observation timestamps to marks. Genesis contains no clock
value. Notices, funding intervals, ledger entries and snapshots are reproducible.
Simulation settings accept `simulation.accounting`; the existing
`simulation.initial_equity_quote` sets that run's starting capital. Accounting
settings are detached with the existing research request, are fingerprint-bound,
and are not part of the optimizer's strategy/agent parameter grids.

There is no public accounting configuration/reset/write endpoint. An accounting
configuration change requires an internal service rebind under the execution
lock. A mismatched runtime/service configuration fails transmission closed.
Disabling accounting does not fabricate unlimited capital authority.

## Perpetual research capital and average cost

Positive base means LONG; negative means SHORT. A BID buys base exposure and an
ASK sells it. Trade notional is not transferred between spot wallets.

Let `q` be signed position, `a` average entry, `p` fill price, and `s` unsigned
fill size. Same-direction increases use:

```text
new average = (a × abs(q) + p × s) / abs(new q)
signed cost basis = new q × new average
```

Opposite-direction fills close `min(abs(q), s)` base:

```text
long realized delta  = (p - a) × closed base
short realized delta = (a - p) × closed base
```

Partial reductions retain the old average. Closing resets average to zero.
Reversals first close the old position and then open the residual at the fill
price. LONG 1 @ 3000 followed by SELL 2 @ 3100 realizes +100 and opens SHORT
1 @ 3100. BUY 1 @ 3000, BUY 1 @ 3100 gives average 3050; SELL 1 @ 3200 realizes
+150 and retains LONG 1 @ 3050.

```text
unrealized trading PnL = (mark - average) × signed base
signed position value = mark × signed base
gross exposure = abs(signed position value)
net exposure = signed position value
```

All economic calculations use Decimal. Snapshot Decimal values serialize as
strings; frontend number formatting is presentation only.

## PnL, equity and drawdown

`cash_balance_quote` on ledger rows means **research settled capital**, not
exchange wallet custody. The Vault calls it `settled_capital_quote`.

```text
settled capital = initial capital + realized trading PnL - fees + funding
gross trading PnL = realized trading PnL + unrealized trading PnL
fee_pnl = -cumulative fees
funding_pnl = cumulative signed funding
net realized PnL = realized trading PnL - fees + funding
net unrealized PnL = unrealized trading PnL
net PnL = session PnL = gross trading PnL - fees + funding
vault equity = initial capital + net PnL = settled capital + unrealized PnL
peak equity = max(previous peak, current committed equity), seeded by initial capital
drawdown quote = max(0, peak equity - equity)
drawdown fraction = drawdown quote / peak equity, when peak > 0
```

Snapshots retain last-known balances when stale and label their health explicitly.
Before a valid mark, unrealized PnL and equity are unavailable. A missing input is
not replaced with zero. Zero fees/funding are valid only when explicitly
configured as PAPER research assumptions.

### Phase 11.1 high-water invariant

`AccountingService._observe_equity()` uses the shared `pnl()` result after each
committed fill plus fee transaction, funding accrual, and mark update. It never
observes an intermediate trade-only balance before its corresponding fee. An
unavailable equity does not change peak. A failed ledger append leaves position,
settled capital, fees/funding and peak unchanged. `EQUITY_PEAK_UPDATED` is emitted
once per new economic high, including realized fills and funding receipts; an
unchanged peak emits no notice. Intermediate highs survive later fills/payments
even when no new mark intervenes.

PAPER snapshot validation rejects `peak_equity_quote < equity_quote`; it does
not repair corrupt state. COMPLETE additionally requires a fresh, error-free,
execution-consistent snapshot with available equity and peak. Capital utilization
continues to use exact Decimal `reserved_capital_quote / equity_quote` for positive
equity.

### Execution/accounting consistency and internal reconciliation

Vault and compact WebSocket accounting summaries include `execution_accounting`:
execution, accounted and unaccounted fill counts, a nullable consistency boolean,
CONSISTENT / DIVERGED / UNAVAILABLE status, reason, and oldest/latest unaccounted
timestamps. Runtime reconciles the current session's entire PAPER FillStore with
immutable TRADE_FILL ledger identities and economic fingerprints, independently
of API ledger pagination. `fill_identity()` and `_fill_evidence()` are shared with
ingestion; there is no separate identity formula. A matching TRADE_FILL counts
once; FEE and FUNDING rows never count as fills. Missing rows, duplicate execution
identities, market mismatches and changed economics are explicit divergence.
TESTNET has UNAVAILABLE consistency with a null boolean; no fills are fabricated.

Divergence makes PAPER completeness UNAVAILABLE while keeping last-known balances
visible. Consistency is material accounting provenance: divergence and valid
reconciliation change accounting version/fingerprint, invalidating prior final
authorization. Existing Phase 8 capital authority and pre-transmission checks
block CREATE/REPLACE. CANCEL and cancel_all remain available. The PAPER callback
retains executed fills, attempts accounting, updates telemetry and wakes strategy
even when ingestion fails.

`reconcile_paper_fills()` is an internal operation, used under the runtime execution
lock. It may book pending evidence when no failure is latched, configuration is
still bound, timestamps are ordered and no newer mark/funding evidence precedes
replay. Normal ingestion validates economics and ledger capacity; each trade/fee
batch remains atomic. Repeated reconciliation books nothing twice. Processing
stops at the first failure; there is no cursor that can skip failed fills.

Callback exceptions (including temporary interruptions), conflicting economics,
invalid economics, exhausted retention, unsafe chronology and config mismatches
latch the first accounting error. No reconciliation clears it or retries later
fills. These cases require a new internal PAPER session; capacity is never
expanded automatically. The permitted recovery case is unfailed pending evidence,
not recovery after an accounting failure. There is no public reset, replay,
rebuild or other accounting mutation endpoint.

## Events, identities and atomic append

Economic event types are `TRADE_FILL`, `FEE`, `FUNDING`. There is no public
adjustment path. Initialization is deterministic genesis, not a synthetic
deposit. Immutable `AccountingEvent` records carry signed cash/position deltas,
realized PnL, fee/funding deltas, source, simulation flag, source reference and
an economic evidence fingerprint.

The existing Fill model is reused. Its optional `liquidity` field records PAPER
research maker/taker classification: resting crossing fills are MAKER, immediate
crossing fills are TAKER. This does not claim actual venue fees.

A fill identity hashes client order ID, market, normalized UTC timestamp and
source. A separate input fingerprint binds all fill fields, including side,
price, size and liquidity, plus the fee schedule/rate/notional/amount. Replaying
the same input is a no-op. Reusing that identity with changed economics raises
an error, preserves balances/history, and invalidates future accounting authority.
Different timestamps support distinct partial economic fills. Out-of-order
new fill timestamps are rejected; the existing PAPER adapter emits full fills.
No complete TESTNET fill-history rewrite is added.

Each fill books its trade and fee in one `append_batch()` transaction. The ledger
validates identity conflicts, capacity and all immutable rows before appending
either row. A failed batch cannot settle a trade without its fee. Even a
configured zero fee has an explicit PAPER_CONFIG row. Funding appends one row.

## Ledger provenance and retention

Genesis hashes schema `phase11-v1`, market, execution mode and accounting config,
including starting capital. Every row commits to:

```text
SHA256(canonical(previous ledger fingerprint,
                 monotonic sequence,
                 event fingerprint and evidence fingerprint,
                 source/identity/deltas,
                 post-entry capital, position, average, realized PnL, fees, funding))
```

Canonical JSON uses sorted keys, compact separators, UTC timestamps and finite
Decimal strings with redundant trailing fractional zeros removed without
rounding. Ledger sequence/version increments once per economic row. Historical
entries are frozen; readers get an immutable tuple, never the internal list.
Sequence is append order; funding timestamps identify effective intervals and
may precede their observation/booking time.

Retention policy is explicitly `HALT_WHEN_FULL`. There is no silent eviction or
loss of deduplication identities. Ledger and identity storage are bounded by the
configured session capacity; capacity exhaustion fails closed and leaves every
existing row intact. A new internal research session is required to resume.
Default capacity is 10000 rows. This is a session ledger, not durable storage or
a recoverable exchange history; process restart starts a new research session.

Diagnostic notices are a separate bounded deque (default 250) and are never
balance authority. Categories include FILL_BOOKED, FILL_DUPLICATE_IGNORED,
FEE_BOOKED, FUNDING_BOOKED, POSITION_OPENED/REDUCED/CLOSED/REVERSED,
EQUITY_PEAK_UPDATED and ACCOUNTING_ERROR. Runtime recovery processes only new
FillStore records, avoiding repeated replay noise during refresh.

## PAPER fees

```text
fee = unsigned fill notional × configured fee bps / 10000
```

Enabled fees use MAKER/TAKER research rates; unclassified PAPER fills use the
conservative taker assumption. Disabled fees are explicitly configured zero-fee
research accounting. Every fee is `simulated=true`, `source=PAPER_CONFIG`.
Fee evidence binds fill identity, fee schedule version `paper-fees-v1`, enabled
flag, both configured rates, classification, actual rate, notional and amount.
Replay cannot charge the same fill twice. These are never advertised as actual
Hyperliquid fees.

## PAPER funding

Funding signals used by Phase 7 pricing are separate from accounting cash flows.
The opt-in research accrual model uses UTC epoch-aligned configured boundaries
(default hourly). The configured rate is interpreted as the signed rate **per
research interval**; shorter research periods do not claim venue payment timing.

```text
funding delta = -signed position × observed mark × interval funding rate
positive delta = received; negative delta = paid
```

At positive rates longs pay and shorts receive. Negative rates reverse that
direction. A flat position books zero. The first observation establishes the
current interval without retroactively accruing it. The first observation of
the next consecutive interval books one accrual using the position after fills
already observed at that refresh/frame and that observation's mark/rate/version.
This is an explicit sampled research convention, not exact historical exposure
integration. Repeated refreshes within the interval do not book payments. Gaps
of more than one interval fail closed because a historical basis is unavailable;
no interpolation or catch-up payment is fabricated.

Explicit internal `accrue_funding()` calls require aligned effective timestamps.
Identity binds market and UTC effective interval; economics bind rate, signed
position/notional, mark, research source and evidence version. Same identity and
economics replay is ignored; conflicting evidence for an already-booked interval
raises an error. Disabled PAPER funding is labeled configured zero-funding.

## Simulated capital reservation

The model is deliberately conservative full-notional research reservation:

```text
reserved capital = abs(position × mark)
                 + sum(effective desired/resting order notional)
available capital = max(0, equity - reserved capital)
capital utilization = reserved capital / equity, when equity > 0
```

Per `(side, level_index)`, KEEP/REPLACE overlap reserves the maximum of desired
notional and total remaining resting notional, not old plus new. Distinct levels
are added. Multiple existing orders at one slot are summed before that maximum.
UNKNOWN and PARTIALLY_FILLED orders count; only their remaining size reserves
capital. CANCEL releases reservation when cancellation is confirmed, not merely
proposed. A filled order releases its order reservation and becomes position
exposure. The final desired ladder reserves future liquidity until reevaluation.

Proposed reservations are previewed without publishing an intermediate authority
version. Phase 8 receives the preview and can HALT if required capital exceeds
`max(0, equity) × max_capital_utilization`. Final transformed quotes are committed
once before authorization. This layer only allows or blocks; it never increases
liquidity, tightens spreads or restores suppressed sides. It is explicitly
`SIMULATED CAPITAL RESERVATION`, not Hyperliquid margin or leverage.

## Authority, freshness and cancellation

Accounting version increments on material ledger/position/mark/PnL/peak/reservation,
error or TESTNET evidence changes. Equal marks, refreshed timestamps, identical
reservations and duplicate fills do not churn versions. Mark changes are versioned
even while flat because they affect reservation prices/mark provenance. Position
record version increments on trade fills. A service rebind establishes a new
mode/market/config-bound genesis; version counters are local to that context.

The accounting fingerprint binds the material state and its version. Snapshot
freshness is checked separately, so passing time does not manufacture economic
version changes. FinalQuoteAuthorization canonical hashing binds both
`accounting_version` and `accounting_fingerprint` alongside Phase 8/9 provenance.

Runtime PAPER flow is telemetry → ingest fill → wake the existing strategy loop.
Strategy refresh observes fills/inventory/perp, marks accounting, previews capital,
then runs the existing strategy/agents/Phase 8 transforms, commits final
reservation, authorizes and reconciles. Feed callbacks also update accounting
while the strategy is stopped. Phase 8 PnlDrawdown is adapted from VaultSnapshot,
including net session PnL, equity and drawdown.

Immediately before CREATE/REPLACE runtime verifies fresh accounting, the expected
version/fingerprint and the authorization binding. It also checks current mark
and that actual resting/desired reservation does not exceed the authorized
reservation. TESTNET account evidence is re-observed at that check because account
equity may change without position version changing. A materially changed state
requires fresh strategy evaluation. Failure, stale evidence, disabled accounting
or unknown state block new authority. CANCEL/cancel-all remain available through
the existing execution safety path; accounting cannot prevent risk reduction.
During replacement the conservative old/new maximum remains reserved until the
batch completes; any released capital then advances accounting and wakes refresh.

Market, execution-mode and market-data-mode transitions cancel/invalidate under
the existing serialized lock and start a fresh accounting context and PAPER
adapter. PAPER history never becomes TESTNET money or another market's capital.
Ordinary quote settings preserve the research session. No public reset is added.

## TESTNET truth boundary

Only normalized existing authoritative evidence is exposed: signed position,
entry, position value, unrealized PnL, position margin, liquidation, ROE, and
account value/total margin/venue withdrawable when present in the existing user
state adapter. Account equity and account margin are account-wide; position
metrics are market-specific. Venue withdrawable is labeled as venue evidence and
is not claimed to be available trading capital. No formula infers exact margin
availability from it.

Full normalized authoritative TESTNET fills, fees, booked funding, settled cash,
realized PnL, gross/net PnL and research reservation/available capital remain
`None`. A current funding rate is never treated as a paid funding event. A known
flat position is actual evidence; missing positions are not fabricated flat.
There is no synthetic TESTNET ledger. `PARTIAL` means some authoritative evidence
exists but full accounting is unsupported; `UNAVAILABLE` means no position/account
evidence exists. `COMPLETE` is reserved for valid fresh PAPER accounting in this
implementation. TESTNET freshness/error remain separate explicit health fields.

When account equity exists, observed-session peak/drawdown and equity change from
the first observed account value are derived from it. That session change is not
claimed as reconciled trading PnL, and its initial value is not research capital.
Unsupported TESTNET capital sufficiency is not invented; existing Phase 8
inventory/exposure/liquidation guards remain in force.

## APIs and frontend

All new endpoints are GET:

| Endpoint | Response |
|---|---|
| `/api/v1/vault` | current snapshot and provenance/health/source labels |
| `/api/v1/accounting/pnl` | explicit PnL components, unknown values null |
| `/api/v1/accounting/position` | PAPER cost basis or existing TESTNET position evidence |
| `/api/v1/accounting/ledger?limit=100` | newest-first immutable rows and ledger provenance |
| `/api/v1/accounting/events?limit=100` | oldest-first retained recent diagnostic notices |

Limits are integers from 1 to 500, enforced by FastAPI (invalid values return
422) and the service. GET observation may update marks but never executes an
order or writes an arbitrary adjustment. `/ws/terminal` adds `vault` and compact
`accounting` (config, PnL, version/fingerprints, retention policy, latest 20
notices); it does not stream ledger rows.

The active Vault sidebar opens `pages/Vault.tsx`, `VaultSummary`, `PnlBreakdown`
and `AccountingLedger`, styled by `phase11.css`. It displays capital, position,
PnL, fees/funding, equity/peak/drawdown, recent ledger rows and provenance. PAPER
is labeled PAPER / SIMULATED; TESTNET shows AUTHORITATIVE EVIDENCE plus PARTIAL
or UNAVAILABLE, with unsupported values displayed as Unavailable. The ledger
fetches at most 100 rows with mode/market/fingerprint-scoped query keys. It has
loading/error/empty states. There are no money movement controls.

## Validation and limitations

Focused Phase 11 tests cover exact Decimal long/short increases, reductions,
closures and reversals; fees and funding signs/idempotency; atomic conflicting
replay rejection; immutable ledger hashing and capacity; capital KEEP/REPLACE/
CANCEL; equity/peak/drawdown; runtime authority races and cancellation; mode
isolation; TESTNET missing truth; deterministic simulation reuse; bounded REST,
terminal WebSocket and static architecture/UI checks. See the Phase 11 roadmap
entry for exact acceptance evidence.

PAPER balances, fee rates and funding sampling are research assumptions. Ledger
storage is in-memory and capacity-bounded. TESTNET completeness is deliberately
partial. Full-notional reservation may halt trading conservatively; it is not a
production margin engine. No live signed TESTNET execution is required for local
acceptance.
