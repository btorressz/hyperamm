# Execution Domain

The `execution` package converts an already-authorized desired quote ladder into venue/order lifecycle actions.

Execution is downstream from strategy, agents, references, risk and final authorization.

## Files

| File | Responsibility |
|---|---|
| `base.py` | Common execution-adapter interface. |
| `models.py` | Normalized order request, strategy order and fill contracts. |
| `quote_reconciler.py` | Deterministically compares desired quote levels with existing orders and emits KEEP/CREATE/REPLACE/CANCEL actions. |
| `order_manager.py` | Serializes reconciliation, performs venue reconciliation when available, rechecks authority before CREATE/REPLACE, and issues cancel/submit calls. |
| `paper.py` | In-memory deterministic PAPER order/fill adapter used by runtime and simulation. |
| `hyperliquid.py` | Guarded Hyperliquid TESTNET adapter, signing, venue reconciliation, position/account-state normalization and uncertain-order handling. |
| `fills.py` | Bounded/simple fill storage helper. |
| `__init__.py` | Package marker. |

## Execution flow

```text
authorized QuoteLevel ladder
        ↓
OrderManager
        ↓
reconcile_quotes()
        ↓
KEEP / CREATE / REPLACE / CANCEL
        ↓
authority recheck before new risk
        ↓
PAPER or guarded TESTNET adapter
```

`OrderManager` uses the shared runtime execution lock. CREATE/REPLACE calls the supplied authority callback immediately before submission. CANCEL paths do not require permission to create new risk.

For guarded TESTNET, runtime normalizes the risk-transformed ladder in Decimal
before final structural, exposure and capital checks and FinalQuoteAuthorization.
The manager passes the concrete request to authority; market, side, level, price
and size must match exactly one current authorized slot. CLOID remains a
reconciliation identity, separate from economic authority.

## PAPER

The PAPER adapter is deterministic and in-memory. In simulation it uses an injected deterministic clock. PAPER fills feed Phase 9 telemetry and Phase 11 accounting.

## TESTNET

The Hyperliquid adapter is intentionally guarded by explicit configuration and backend-only key material. It tracks reconciliation errors, unknown exposure and authoritative position/account snapshots. The project does not implement a production-mainnet execution path.

Precision follows the supported SDK 0.24.0
[rounding example](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/0.24.0/examples/rounding.py):
non-integer prices have at most five significant figures and `6 - szDecimals`
fractional places for perps, `8 - szDecimals` for spot; integer prices are allowed
regardless of significant figures. BID prices round down, ASK prices round up,
and size rounds down to `szDecimals`. Normalization is pure and idempotent.
The adapter rejects requests requiring further normalization and requires a
concrete-request authority callback. Float conversion happens only after that
check; both Decimal round trip and SDK `float_to_wire` output must equal the
authorized values before an order is registered or transmitted.

Final TESTNET capital checks use the existing full-notional reservation formula
plus current account margin against account equity times the configured capital
utilization limit. This deliberately conservative gate assumes no leverage and
requires equity and margin evidence. It does not claim complete TESTNET cash or
fill accounting, and does not change Phase 11 accounting formulas. Cancellation
requires neither create authority nor normalization, including after a failed
replacement.

## Connections

- Receives final quotes from `risk`/runtime.
- Supplies fills/orders to `accounting`, `agents`, risk exposure calculations and the terminal.
- Venue uncertainty feeds back into Phase 8 and can halt new risk.

## Audit 1.0 A1-005 / A1-006 retention and reconciliation

Authoritative OPEN, PARTIALLY_FILLED and UNKNOWN orders have no eviction limit.
PAPER and TESTNET retain **1,000 unpinned closed orders** each. Closed orders
with pending PAPER fill evidence, TESTNET cancellation verification, or TESTNET
fill/order evidence awaiting Phase 11 position/account consumption remain
pinned outside that allowance until consumed/resolved. Closed transitions reach
agent telemetry before pruning. TESTNET verification rows remain conservative
UNKNOWN exposure for risk and capital even after a cancellation acknowledgement;
new transmission waits for independent terminal venue evidence. TESTNET closed
fill evidence additionally waits for Phase 11 observation of authoritative
position/account timestamps at least as new as the order update; no full TESTNET
trade ledger is inferred.

PAPER retains **1,000 acknowledged fills**, plus all pending evidence. Both
matching immutable ledger evidence and agent consumption are required to
acknowledge a fill. **1,000 pending fills** stop admission of new PAPER orders;
already-active execution can still produce authoritative fills beyond this
threshold, which are preserved rather than truncated. Cancellation remains
available. Consumption receipts cannot exceed half the configured immutable
ledger capacity (default **5,000** identities); duplicate execution remains
an error even after its recent UI row is evicted. Phase 11's existing **10,000**
entry default ledger and HALT_WHEN_FULL policy are unchanged: trade and fee
commit atomically, and no ledger entry or economic identity is evicted.

Position, inventory version, last-fill time and fill notional are cumulative
counters, independent of recent fill retention. Pending booking visits only
pending evidence; consistency checks visit bounded retained fills plus pending
evidence and use the ledger's immutable commit-time fill index. Agent order
observations consume transitions/current active state rather than replaying
closed history. API /orders and /fills default to **100** recent rows and accept
`limit=1..1000`; /orders additionally includes every authoritative active or
verification-pinned order. Terminal reads **100** recent closed orders/fills
directly before its existing display limits (100 recent, 200 active) apply.
Display limits never prune execution or accounting authority.

Every active order belongs to a slot group `(side, level_index)`, or is explicitly
unmanaged and cancelled. Remaining exposure uses `size - filled_size` for every
order. Quantity and notional sums have independent maxima against the desired
slot, retaining ordinary single-order KEEP/cancel-before-create REPLACE overlap
without hiding duplicates at differing prices. Phase 11 capital already sums
resting duplicate notionals and remains at least as conservative as risk quote
notional. Reconciliation chooses at most one verified keeper, cancels all surplus
and unmanaged orders first, and blocks CREATE/REPLACE on UNKNOWN or unconfirmed
cancellation/verification. Active client order identities cannot be overwritten.
