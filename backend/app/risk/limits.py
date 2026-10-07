from __future__ import annotations
from decimal import Decimal
from app.amm.models import QuoteLevel
from app.market_data.models import MarketSnapshot
from .models import RiskStatus


def validate_quotes(quotes: list[QuoteLevel], snapshot: MarketSnapshot, risk: RiskStatus, *, final_venue=False):
    if risk.kill_switch_active:
        raise PermissionError("kill switch is active")
    from app.strategy.fair_value import calculate_fair_value
    calculate_fair_value(snapshot)
    if len(quotes) > risk.max_quote_levels * 2:
        raise ValueError("too many quote levels")
    total = Decimal("0")
    for q in quotes:
        if final_venue and q.side not in {"BID", "ASK"}:
            raise ValueError("invalid final quote side")
        if not q.price.is_finite() or not q.size.is_finite() or q.price <= 0 or q.size <= 0:
            raise ValueError("quote price and size must be finite and positive")
        if q.price < risk.min_valid_price:
            raise ValueError("quote below minimum valid price")
        if q.size > risk.max_order_size:
            raise ValueError("order size exceeds limit")
        if q.distance_bps > risk.max_quote_distance_bps:
            raise ValueError("quote distance exceeds limit")
        total += q.price * q.size
    if total > risk.max_aggregate_notional:
        raise ValueError("aggregate quote notional exceeds limit")
    if final_venue:
        bids=[q.price for q in quotes if q.side == "BID"]
        asks=[q.price for q in quotes if q.side == "ASK"]
        if bids and asks and max(bids) >= min(asks):
            raise ValueError("final venue quote ladder is crossed")


def validate_execution_authority(*, risk: RiskStatus, execution_mode: str, strategy_running: bool):
    if risk.kill_switch_active:
        raise PermissionError("kill switch is active")
    if execution_mode not in {"PAPER", "TESTNET"}:
        raise PermissionError("unsupported execution mode")
    if not strategy_running:
        raise PermissionError("strategy is stopped")
