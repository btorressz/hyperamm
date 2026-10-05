# Phase 8 Institutional Risk Firewall

The strategy proposes quotes. Phase 8 decides whether those quotes may exist.

Phase 8 runs after Phase 5 inventory and Phase 6 market adaptation and before existing structural quote validation/reconciliation.

## Authority order

```text
Phase 7 perpetual reference
        ↓
AMM
        ↓
Phase 5 inventory / hard-side suppression
        ↓
Phase 6 volatility + L2 adaptation
        ↓
Phase 8 institutional risk firewall
        ↓
existing validate_quotes()
        ↓
FinalQuoteAuthorization
        ↓
KEEP / CREATE / REPLACE / CANCEL
        ↓
PAPER / guarded TESTNET
```

Phase 8 may remove or reduce surviving quotes. It never restores a side already suppressed by Phase 5.

## Risk states

### NORMAL

Healthy quorum and risk conditions.

```text
spread multiplier = 1
size multiplier   = 1
quotes preserved exactly
```

### WIDEN

Moderate reference/liquidation/drawdown risk.

Quotes are widened around the Phase 5 reservation center. The configured spread multiplier is never below one, so Phase 8 cannot tighten a Phase 6 quote. Size may be slightly reduced.

### REDUCE

Elevated risk.

Phase 8 widens, reduces sizes, may trim deeper levels, and applies a stronger reduction to quotes marked `INVENTORY_INCREASING`. The risk layer is allowed to reduce below the strategy baseline because safety has higher authority than minimum-liquidity preference.

### HALT

Severe integrity/risk failure.

```text
authorized quotes = []
existing strategy orders -> existing serialized cancellation/reconciliation path
new transmissions blocked
deterministic reasons surfaced
```

Automatic HALT does not set the manual kill flag.

## Default thresholds

The initial deterministic defaults are configuration, not market-alpha predictions:

```text
reference warning  = 20 bps
reference reduce   = 40 bps
reference halt     = 80 bps

source agreement   = 30 bps
source outlier     = 75 bps

liquidation warning distance = 1500 bps
liquidation reduce distance  = 800 bps
liquidation halt distance    = 300 bps
```

All reference thresholds satisfy `warn < reduce < halt`. Liquidation danger uses inverse ordering because smaller distance is more dangerous.

## Hysteresis and recovery

Escalation is immediate.

Recovery requires both:

```text
materially safer recovery threshold
+
risk_recovery_confirmations consecutive healthy decisions
```

Default recovery uses 75% of the current state's entry threshold and three confirmations.

A single favorable tick cannot clear an automatic halt.

Manual kill is independent:

```text
manual kill
    -> never automatic recovery
    -> explicit resume
    -> explicit strategy start
```

## Projected exposure

The firewall computes:

```text
current position
current position notional
candidate bid quantity
candidate ask quantity
bid quote notional
ask quote notional
gross quote notional
projected long base/notional
projected short base/notional
inventory utilization
```

Existing resting orders are included conservatively. Matching side/level exposure is represented by the larger of desired and remaining resting quantity, avoiding naive KEEP/REPLACE double counting. Unmatched resting or uncertain exposure remains counted.

```text
projected_long =
    current_position + effective bid quantity

projected_short =
    current_position - effective ask quantity
```

Unknown TESTNET venue exposure is fail-closed.

## Liquidation distance

For a long position:

```text
distance =
    (mark - liquidation) / mark
```

For a short position:

```text
distance =
    (liquidation - mark) / mark
```

The firewall reports basis points. Flat positions report `FLAT`; missing liquidation price reports `UNAVAILABLE`; no value is fabricated.

## PAPER PnL

PAPER PnL uses actual economic fills only with deterministic average-cost accounting:

```text
realized PnL
unrealized PnL at current mark
session PnL
```

It is labeled `SIMULATED PAPER PNL`. Unfilled/cancelled orders do not contribute.

PAPER does not invent an account equity baseline, so drawdown is unavailable unless reliable equity exists.

## TESTNET equity and drawdown

The existing authoritative Hyperliquid user-state refresh also retains currently available account value, total margin used and withdrawable values.

If authoritative account value exists:

```text
session_start_equity
peak_equity
current_equity
session PnL
drawdown =
    (peak_equity - current_equity) / peak_equity
```

If reliable equity is unavailable, drawdown remains unavailable.

No leverage or margin mutation API is called by Phase 8.

## Event log

The firewall stores a bounded in-memory log of the most recent 250 state transitions:

```text
timestamp
previous_state
new_state
reasons
reference_version
risk_version
```

No database is introduced in Phase 8.

## Deterministic fingerprints

Canonical serialization uses:

```text
sorted dictionary keys
Decimal -> stable string
datetime -> UTC ISO-8601
enum -> stable value
deterministic list ordering from the input contract
```

SHA-256 fingerprints bind:

```text
authorized quote ladder
reference evidence snapshot
risk decision
final authorization
```

## FinalQuoteAuthorization

The final contract contains:

```text
authorized
risk_state
quote_fingerprint
evidence_fingerprint
risk_fingerprint
authorization_fingerprint

market_version
inventory_version
perp_version
reference_version
risk_version

authorized_quote_count
bid_authorized
ask_authorized
reasons
created_at
```

Immediately before every CREATE/REPLACE transmission, the existing serialized authority path verifies:

```text
manual kill inactive
strategy running
execution mode authorized
inventory version current
market/adaptation version current
perp version current
reference version current
risk version current
authorized quote fingerprint current
FinalQuoteAuthorization authorized
```

Any mismatch rejects transmission and forces recomputation through the normal strategy loop.

## Existing structural risk

Phase 8 does not replace `validate_quotes()`. The transformed authorized ladder still passes the existing structural checks for market freshness, finite positive values, level count, order size, aggregate notional and quote distance.

## Observability

REST:

```text
GET /api/v1/references
GET /api/v1/risk
GET /api/v1/risk/evidence
GET /api/v1/risk/events
GET /api/v1/risk/authorization
```

The terminal WebSocket exposes normalized references, consensus, firewall decision, final authorization, recent risk events, projected exposure and PnL/drawdown.

Provider and signing credentials are never included.
