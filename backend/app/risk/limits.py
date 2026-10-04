from __future__ import annotations
from decimal import Decimal
from app.amm.models import QuoteLevel
from app.market_data.models import MarketSnapshot
from .models import RiskStatus


def validate_quotes(quotes: list[QuoteLevel], snapshot: MarketSnapshot, risk: RiskStatus):
    if risk.kill_switch_active:
        raise PermissionError("kill switch is active")
    if snapshot.stale:
        raise ValueError("market data is stale")
    if len(quotes) > risk.max_quote_levels * 2:
        raise ValueError("too many quote levels")
    total = Decimal("0")
    for q in quotes:
        if q.price < risk.min_valid_price:
            raise ValueError("quote below minimum valid price")
        if q.size > risk.max_order_size:
            raise ValueError("order size exceeds limit")
        if q.distance_bps > risk.max_quote_distance_bps:
            raise ValueError("quote distance exceeds limit")
        total += q.price * q.size
    if total > risk.max_aggregate_notional:
        raise ValueError("aggregate quote notional exceeds limit")


def validate_execution_authority(*, risk: RiskStatus, execution_mode: str, strategy_running: bool):
    if risk.kill_switch_active:
        raise PermissionError("kill switch is active")
    if execution_mode not in {"PAPER", "TESTNET"}:
        raise PermissionError("unsupported execution mode")
    if not strategy_running:
        raise PermissionError("strategy is stopped")
