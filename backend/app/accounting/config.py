from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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
