# Accounting & Vault Domain

The `accounting` package is Phase 11/11.1's deterministic, non-custodial economic authority.

It provides one shared implementation for runtime PAPER accounting and Phase 10 simulation. It does not move money and does not submit orders.

## Position in the pipeline

```text
executed fills + marks + funding
        ↓
AccountingService
        ↓
immutable/idempotent ledger
        ↓
average-cost position
        ↓
realized/unrealized PnL
fees + funding
        ↓
equity / peak / drawdown
        ↓
capital reservation
        ↓
VaultSnapshot
        ↓
Phase 8 capital authority + terminal
```

## Files

| File | Responsibility |
|---|---|
| `config.py` | Research accounting configuration: initial capital, fees, funding/capital limits and retention behavior. |
| `models.py` | Ledger/accounting/vault contracts, completeness and execution-accounting consistency state. |
| `ledger.py` | Append-only idempotent ledger, event identity/economic fingerprints and chained ledger fingerprint. |
| `pnl.py` | Shared average-cost position transitions, reversal handling and PnL breakdown helpers. |
| `fees.py` | Deterministic PAPER fee calculations and identities. |
| `funding.py` | Deterministic funding interval/economic calculations for research accounting. |
| `vault.py` | Capital reservation and vault-related helpers. |
| `service.py` | Stateful accounting authority coordinating fills, fees, funding, marks, reservations, snapshots, consistency checks and reconciliation. |
| `__init__.py` | Public exports. |

## Core invariants

- Fill ingestion is identity/economics bound and idempotent.
- Long/short increases, reductions, closes and reversals share one average-cost formula.
- Fees/funding cannot be double-booked under the same economic identity.
- Ledger entries form a deterministic fingerprint chain.
- Peak equity observes committed economic changes; complete snapshots enforce `peak_equity >= equity`.
- Executed PAPER fills are compared with immutable `TRADE_FILL` evidence.
- Divergence makes accounting/capital authority unavailable and blocks CREATE/REPLACE while cancellation remains possible.

## TESTNET truth boundary

TESTNET exposes only economics already authoritative from available account/position state. Unsupported realized PnL, fees, funding payments or capital fields remain partial/unavailable rather than being fabricated.

## Connections

- Runtime PAPER fills call `AccountingService.ingest_fill()`.
- Perp mark/funding context updates accounting.
- Phase 8 consumes vault-derived PnL/drawdown and capital sufficiency.
- `FinalQuoteAuthorization` binds accounting version/fingerprint.
- Simulation creates a fresh accounting service and reuses the same formulas.
- Terminal/API expose read-only snapshots, ledger and events.
