"""Read-only depth of a supplied normalized ladder, never venue order status."""
from decimal import Decimal
from .numeric import numeric_guard


@numeric_guard
def effective_liquidity(quotes):
    groups = {}
    slots = set()
    for q in quotes:
        slot = (q.side, q.level_index)
        if (q.side not in {"BID", "ASK"} or slot in slots
                or any(not v.is_finite() or v <= 0 for v in (q.price, q.size))):
            raise ValueError("effective liquidity requires a valid normalized ladder")
        slots.add(slot)
        key = (q.side, q.price)
        group = groups.setdefault(key, {"side": q.side, "price": q.price,
            "logical_slots": 0, "quantity": Decimal("0"), "notional": Decimal("0"),
            "level_indices": []})
        group["logical_slots"] += 1
        group["quantity"] += q.size
        group["notional"] += q.price * q.size
        group["level_indices"].append(q.level_index)
    bids = [price for side, price in groups if side == "BID"]
    asks = [price for side, price in groups if side == "ASK"]
    if bids and asks and max(bids) >= min(asks):
        raise ValueError("effective liquidity requires an uncrossed ladder")
    depth = sorted(groups.values(), key=lambda g: (g["side"], g["price"]))
    for group in depth:
        group["level_indices"].sort()
    warnings = []
    for side in ("BID", "ASK"):
        logical = sum(q.side == side for q in quotes)
        unique = sum(g["side"] == side for g in depth)
        if logical > unique:
            warnings.append(f"{logical} logical {side} slots produced {unique} distinct executable {side} prices; slots are preserved")
    return {"observational": True, "logical_slots": len(quotes),
        "unique_executable_prices": len(depth),
        "effective_bid_levels": len(bids), "effective_ask_levels": len(asks),
        "duplicate_price_groups": sum(g["logical_slots"] > 1 for g in depth),
        "collapsed_level_count": len(quotes) - len(depth),
        "collapse_ratio": Decimal(len(quotes) - len(depth)) / len(quotes) if quotes else Decimal("0"),
        "total_bid_quantity": sum((q.size for q in quotes if q.side == "BID"), Decimal("0")),
        "total_ask_quantity": sum((q.size for q in quotes if q.side == "ASK"), Decimal("0")),
        "price_groups": depth, "warnings": warnings}
