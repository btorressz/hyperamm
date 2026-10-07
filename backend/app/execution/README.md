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

## PAPER

The PAPER adapter is deterministic and in-memory. In simulation it uses an injected deterministic clock. PAPER fills feed Phase 9 telemetry and Phase 11 accounting.

## TESTNET

The Hyperliquid adapter is intentionally guarded by explicit configuration and backend-only key material. It tracks reconciliation errors, unknown exposure and authoritative position/account snapshots. The project does not implement a production-mainnet execution path.

## Connections

- Receives final quotes from `risk`/runtime.
- Supplies fills/orders to `accounting`, `agents`, risk exposure calculations and the terminal.
- Venue uncertainty feeds back into Phase 8 and can halt new risk.
