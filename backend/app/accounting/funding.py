from datetime import datetime, timezone
from decimal import Decimal

from .models import Record, fingerprint


class FundingAccrual(Record):
    market: str
    effective_at: datetime
    position_base: Decimal
    mark_price: Decimal
    position_notional: Decimal
    funding_rate: Decimal
    funding_delta_quote: Decimal
    source: str = "PAPER_RESEARCH_INTERVAL"
    simulated: bool = True
    evidence_version: int

    @property
    def fingerprint(self):
        return fingerprint(self)


def interval_boundary(timestamp, seconds):
    if timestamp.tzinfo is None:
        raise ValueError("funding timestamp must be timezone-aware")
    epoch = int(timestamp.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, timezone.utc)


def paper_funding(*, market, effective_at, position, mark, rate, evidence_version):
    if not mark.is_finite() or mark <= 0 or not rate.is_finite() or not position.is_finite():
        raise ValueError("invalid funding basis")
    # Positive rate: longs pay and shorts receive. Positive delta is a receipt.
    return FundingAccrual(market=market, effective_at=effective_at, position_base=position,
                          mark_price=mark, position_notional=position * mark, funding_rate=rate,
                          funding_delta_quote=-position * mark * rate, evidence_version=evidence_version)
