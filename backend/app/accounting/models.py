from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator


def canonical(value):
    if isinstance(value, Decimal):
        # Numerically equal Decimal encodings have the same provenance.
        if not value.is_finite():
            raise ValueError("accounting fingerprints require finite financial values")
        text = format(value, "f")
        return (text.rstrip("0").rstrip(".") if "." in text else text) if value else "0"
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, BaseModel):
        return canonical(value.model_dump())
    if isinstance(value, dict):
        return {str(k): canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    return value


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    @model_validator(mode="after")
    def aware_times(self):
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, datetime) and value.tzinfo is None:
                raise ValueError("accounting timestamps must be timezone-aware")
        return self


class AccountingEventType(StrEnum):
    TRADE_FILL = "TRADE_FILL"
    FEE = "FEE"
    FUNDING = "FUNDING"


class AccountingCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class ConsistencyStatus(StrEnum):
    CONSISTENT = "CONSISTENT"
    DIVERGED = "DIVERGED"
    UNAVAILABLE = "UNAVAILABLE"


class ExecutionAccountingConsistency(Record):
    execution_fill_count: int = Field(default=0, ge=0)
    accounted_fill_count: int = Field(default=0, ge=0)
    unaccounted_fill_count: int = Field(default=0, ge=0)
    execution_accounting_consistent: bool | None = None
    oldest_unaccounted_fill_at: datetime | None = None
    latest_unaccounted_fill_at: datetime | None = None
    status: ConsistencyStatus = ConsistencyStatus.UNAVAILABLE
    reason: str | None = "Normalized execution fill evidence unavailable"


class AccountingEvent(Record):
    event_id: str
    event_type: AccountingEventType
    market: str
    timestamp: datetime
    source: str
    simulated: bool
    source_reference: str
    cash_delta_quote: Decimal = Decimal("0")
    position_delta_base: Decimal = Decimal("0")
    realized_pnl_delta: Decimal = Decimal("0")
    fee_delta_quote: Decimal = Decimal("0")
    funding_delta_quote: Decimal = Decimal("0")
    side: str | None = None
    price: Decimal | None = None
    size: Decimal | None = None
    evidence_fingerprint: str

    @property
    def fingerprint(self):
        return fingerprint(self)


class PositionAccounting(Record):
    market: str
    position_base: Decimal = Decimal("0")
    average_entry_price: Decimal = Decimal("0")
    cost_basis_quote: Decimal = Decimal("0")
    realized_pnl_quote: Decimal = Decimal("0")
    unrealized_pnl_quote: Decimal | None = None
    mark_price: Decimal | None = None
    position_value_quote: Decimal | None = None
    version: int = 0


class LedgerEntry(Record):
    sequence: int
    event_id: str
    event_type: AccountingEventType
    timestamp: datetime
    market: str
    side: str | None
    price: Decimal | None
    size: Decimal | None
    cash_delta_quote: Decimal
    position_delta_base: Decimal
    fee_delta_quote: Decimal
    funding_delta_quote: Decimal
    realized_pnl_delta: Decimal
    cash_balance_quote: Decimal
    position_base: Decimal
    average_entry_price: Decimal
    cumulative_realized_pnl: Decimal
    cumulative_fees: Decimal
    cumulative_funding: Decimal
    source: str
    simulated: bool
    source_reference: str
    event_fingerprint: str
    evidence_fingerprint: str
    previous_ledger_fingerprint: str
    ledger_fingerprint: str


class PnlBreakdown(Record):
    realized_trading_pnl: Decimal | None = None
    unrealized_trading_pnl: Decimal | None = None
    fee_pnl: Decimal | None = None
    funding_pnl: Decimal | None = None
    net_realized_pnl: Decimal | None = None
    net_unrealized_pnl: Decimal | None = None
    session_pnl: Decimal | None = None
    gross_trading_pnl: Decimal | None = None
    net_pnl: Decimal | None = None


class VaultSnapshot(Record):
    mode: str
    market: str
    source: str
    simulated: bool
    accounting_complete: AccountingCompleteness
    execution_accounting: ExecutionAccountingConsistency = Field(default_factory=ExecutionAccountingConsistency)
    initial_equity_quote: Decimal | None = None
    settled_capital_quote: Decimal | None = None
    position_base: Decimal | None = None
    average_entry_price: Decimal | None = None
    mark_price: Decimal | None = None
    position_value_quote: Decimal | None = None
    realized_pnl_quote: Decimal | None = None
    unrealized_pnl_quote: Decimal | None = None
    gross_pnl_quote: Decimal | None = None
    fees_quote: Decimal | None = None
    funding_quote: Decimal | None = None
    net_pnl_quote: Decimal | None = None
    equity_quote: Decimal | None = None
    peak_equity_quote: Decimal | None = None
    drawdown_quote: Decimal | None = None
    drawdown_pct: Decimal | None = None
    reserved_capital_quote: Decimal | None = None
    available_capital_quote: Decimal | None = None
    gross_exposure_quote: Decimal | None = None
    net_exposure_quote: Decimal | None = None
    capital_utilization: Decimal | None = None
    margin_used_quote: Decimal | None = None
    position_margin_used_quote: Decimal | None = None
    venue_withdrawable_quote: Decimal | None = None
    return_on_equity: Decimal | None = None
    liquidation_price: Decimal | None = None
    fee_source: str = "UNAVAILABLE"
    funding_source: str = "UNAVAILABLE"
    reservation_source: str = "UNAVAILABLE"
    session_pnl_quote: Decimal | None = None
    ledger_version: int
    ledger_fingerprint: str
    accounting_version: int
    accounting_fingerprint: str
    updated_at: datetime | None = None
    stale: bool = True
    error: str | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def paper_invariants(self):
        if self.mode == "PAPER":
            if self.equity_quote is not None and self.peak_equity_quote is not None:
                if self.peak_equity_quote < self.equity_quote:
                    raise ValueError("PAPER peak equity is below current equity")
            if self.accounting_complete == AccountingCompleteness.COMPLETE:
                if (self.error is not None or self.stale
                        or self.execution_accounting.execution_accounting_consistent is not True
                        or self.equity_quote is None or self.peak_equity_quote is None):
                    raise ValueError("COMPLETE PAPER accounting requires valid, consistent equity authority")
        return self


class AccountingNotice(Record):
    timestamp: datetime
    category: str
    source_reference: str | None = None
    message: str
    accounting_version: int
