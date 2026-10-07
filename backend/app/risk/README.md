# Risk & Authorization Domain

The `risk` package is the deterministic downstream safety authority between strategy/agent proposals and order transmission.

It contains both early structural limits and the later Phase 8 institutional risk/firewall + authorization layer.

## Position in the pipeline

```text
post-agent quotes + reference evidence + inventory/perp/accounting state
        ↓
RiskFirewall
        ↓
NORMAL / WIDEN / REDUCE / HALT
        ↓
risk quote transform
        ↓
structural validate_quotes()
        ↓
FinalQuoteAuthorization
        ↓
OrderManager authority check
```

## Files

| File | Responsibility |
|---|---|
| `firewall.py` | Phase 8 exposure, reference deviation, liquidation, drawdown, capital and venue-uncertainty evaluation; state machine and conservative quote transform. |
| `authorization.py` | Canonical SHA-256 fingerprints and `FinalQuoteAuthorization` binding quote/evidence/risk/agent/accounting versions. |
| `limits.py` | Structural quote validation and execution-authority checks used close to transmission. |
| `kill_switch.py` | Manual kill/resume state handling used by the runtime. |
| `models.py` | Core risk status model. |
| `__init__.py` | Package marker. |

## Risk states

- `NORMAL`: normal authorized behavior.
- `WIDEN`: widen and reduce liquidity conservatively.
- `REDUCE`: stronger widening/size/level reduction.
- `HALT`: no new quotes.

Deterioration escalates immediately; recovery is confirmation/hysteresis based.

## Inputs

The firewall evaluates, among other evidence:

- multi-source reference confidence/deviation;
- projected desired/resting exposure;
- current inventory;
- gross/notional limits;
- liquidation distance;
- session loss and drawdown;
- accounting completeness/capital reservation;
- venue uncertainty;
- manual kill state at the runtime authority boundary.

## Final authorization

`FinalQuoteAuthorization` binds material state such as market, inventory, perp, reference, agent, risk and accounting versions/fingerprints. The runtime rechecks these immediately before CREATE/REPLACE.

## Safety boundary

This package does not directly transmit orders. Cancellation is intentionally permitted even when CREATE/REPLACE authority is unavailable so risk can be removed.
