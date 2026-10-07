from decimal import Decimal

from .models import Record, fingerprint


class FeeAccrual(Record):
    fill_identity: str
    notional_quote: Decimal
    fee_rate_bps: Decimal
    fee_quote: Decimal
    liquidity: str
    schedule_fingerprint: str
    source: str = "PAPER_CONFIG"
    simulated: bool = True

    @property
    def fingerprint(self):
        return fingerprint(self)


def paper_fee(fill, identity, config):
    # Unclassified PAPER fills conservatively use the configured taker assumption.
    liquidity = getattr(fill, "liquidity", None) or "TAKER"
    rate = config.paper_maker_fee_bps if liquidity == "MAKER" else config.paper_taker_fee_bps
    if not config.paper_fee_model_enabled:
        rate = Decimal("0")
    notional = fill.price * fill.size
    schedule = fingerprint({"version": "paper-fees-v1", "enabled": config.paper_fee_model_enabled,
                            "maker_bps": config.paper_maker_fee_bps, "taker_bps": config.paper_taker_fee_bps})
    return FeeAccrual(fill_identity=identity, notional_quote=notional, fee_rate_bps=rate,
                      fee_quote=notional * rate / Decimal("10000"), liquidity=liquidity,
                      schedule_fingerprint=schedule)
