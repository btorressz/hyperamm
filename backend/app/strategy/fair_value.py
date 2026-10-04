from decimal import Decimal
from app.market_data.models import MarketSnapshot


def calculate_fair_value(snapshot: MarketSnapshot) -> Decimal:
    if snapshot.stale:
        raise ValueError("market data is stale")
    if snapshot.best_bid is None or snapshot.best_ask is None:
        raise ValueError("valid bid and ask are required")
    if snapshot.best_bid <= 0 or snapshot.best_ask <= 0 or snapshot.best_bid >= snapshot.best_ask:
        raise ValueError("invalid BBO")
    return (snapshot.best_bid + snapshot.best_ask) / 2
