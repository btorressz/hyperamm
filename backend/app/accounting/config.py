from decimal import Decimal, InvalidOperation
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


def bounded_exact_decimal(value):
    """Bound exact configuration values before arithmetic/canonical expansion."""
    if isinstance(value, (float, bool)):
        raise ValueError("exact bounded financial input required")
    if isinstance(value, str) and (len(value) > 80 or not re.fullmatch(
            r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d{1,2})?", value)):
        raise ValueError("exact bounded financial input required")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("exact bounded financial input required") from None
    if (not result.is_finite() or not -60 <= result.as_tuple().exponent <= 30 or
            result.copy_abs() > Decimal('1e30')):
        raise ValueError("financial input outside configuration bounds")
    return result


class AccountingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    enabled: bool = True
    paper_initial_equity_quote: Decimal = Field(default=Decimal("100000"), gt=0)
    paper_fee_model_enabled: bool = False
    paper_maker_fee_bps: Decimal = Field(default=Decimal("1"), ge=0, le=10000)
    paper_taker_fee_bps: Decimal = Field(default=Decimal("3"), ge=0, le=10000)
    paper_funding_accounting_enabled: bool = False
    paper_funding_interval_seconds: int = Field(default=3600, ge=1, le=86400)
    accounting_stale_after_seconds: int = Field(default=30, ge=1, le=86400)
    ledger_max_entries: int = Field(default=10000, ge=2, le=100000)
    event_max_entries: int = Field(default=250, ge=1, le=1000)
    max_capital_utilization: Decimal = Field(default=Decimal("1"), gt=0, le=1)

    @field_validator('paper_initial_equity_quote', 'paper_maker_fee_bps',
                     'paper_taker_fee_bps', 'max_capital_utilization', mode='before')
    @classmethod
    def exact_financial_inputs(cls, value):
        return bounded_exact_decimal(value)
