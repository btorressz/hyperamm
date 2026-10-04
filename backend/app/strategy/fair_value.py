from decimal import Decimal
from app.market_data.models import MarketSnapshot


def calculate_fair_value(snapshot: MarketSnapshot) -> Decimal:
    if snapshot.stale:
        raise ValueError("market data is stale")
    if snapshot.connection_state != "CONNECTED":
        raise ValueError(f"market data is {snapshot.connection_state}")
    if snapshot.best_bid is None or snapshot.best_ask is None:
        raise ValueError("valid bid and ask are required")
    if not snapshot.best_bid.is_finite() or not snapshot.best_ask.is_finite():
        raise ValueError("non-finite BBO")
    if snapshot.mid_price is not None and (not snapshot.mid_price.is_finite() or snapshot.mid_price <= 0):
        raise ValueError("invalid market mid price")
    if snapshot.best_bid <= 0 or snapshot.best_ask <= 0 or snapshot.best_bid >= snapshot.best_ask:
        raise ValueError("invalid BBO")
    return (snapshot.best_bid + snapshot.best_ask) / 2
