"""Normalize Hyperliquid account inventory before it can affect execution."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


TESTNET_URL = "https://api.hyperliquid-testnet.xyz"
ACCOUNT = re.compile(r"0x[0-9a-fA-F]{40}")
_CLOID = re.compile(r"0x[0-9a-fA-F]{32}")
_COIN = re.compile(r"(?:[A-Za-z0-9_.-]+:)?[A-Za-z0-9_.@/-]{1,64}")
_DEX = re.compile(r"[A-Za-z0-9_.-]{1,32}")
_MAX_DEXS = 32
_MAX_OPEN_ORDERS = 2000


class InventoryError(RuntimeError):
    """A public-safe account inventory rejection."""


def order_id(value):
    if type(value) is not int or not 0 < value < 2**64:
        raise InventoryError("invalid venue order ID")
    return str(value)


def _decimal(value, *, positive=False):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise InventoryError("invalid venue order economics")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise InventoryError("invalid venue order economics") from None
    if (not result.is_finite() or not 0 <= result <= Decimal("1e18")
            or result.as_tuple().exponent < -8 or (positive and not result)):
        raise InventoryError("invalid venue order economics")
    return result


@dataclass(frozen=True)
class VenueOrder:
    oid: str
    coin: str
    side: str
    price: Decimal
    remaining: Decimal
    original: Decimal
    cloid: str | None

    @classmethod
    def parse(cls, row, address, *, active):
        if not isinstance(row, dict):
            raise InventoryError("malformed venue order")
        if (("user" in row and row["user"] != address)
                or ("network" in row and row["network"] != "TESTNET")):
            raise InventoryError("venue order account or network mismatch")
        coin, side, cloid = row.get("coin"), row.get("side"), row.get("cloid")
        if not isinstance(coin, str) or len(coin) > 100 or not _COIN.fullmatch(coin) or side not in ("B", "A"):
            raise InventoryError("invalid venue order market or side")
        if cloid is not None and (not isinstance(cloid, str) or not _CLOID.fullmatch(cloid)):
            raise InventoryError("invalid venue client order ID")
        if active and row.get("status", "open") != "open":
            raise InventoryError("non-open row in venue open-order inventory")
        remaining = _decimal(row.get("sz"), positive=active)
        original = _decimal(row.get("origSz"), positive=True)
        if remaining > original:
            raise InventoryError("remaining venue size exceeds original size")
        return cls(order_id(row.get("oid")), coin, "BID" if side == "B" else "ASK",
                   _decimal(row.get("limitPx"), positive=True), remaining, original,
                   cloid.lower() if cloid is not None else None)


def read_open_orders(info, address):
    """Fetch the Core/spot scope and each named perp DEX for the same account."""
    dexs = info.perp_dexs()
    if not isinstance(dexs, list) or not dexs or dexs[0] is not None or len(dexs) > _MAX_DEXS:
        raise InventoryError("venue account market scopes unavailable")
    scopes = [""]
    for dex in dexs[1:]:
        name = dex.get("name") if isinstance(dex, dict) else None
        if not isinstance(name, str) or not _DEX.fullmatch(name) or name in scopes:
            raise InventoryError("invalid venue account market scope")
        scopes.append(name)

    by_oid = {}
    cloids = set()
    for scope in scopes:
        rows = info.frontend_open_orders(address, scope)
        if not isinstance(rows, list) or len(by_oid) + len(rows) >= _MAX_OPEN_ORDERS:
            raise InventoryError("incomplete venue open-order inventory")
        for raw in rows:
            row = VenueOrder.parse(raw, address, active=True)
            if row.coin.rpartition(":")[0] != scope:
                raise InventoryError("venue order market scope mismatch")
            if row.oid in by_oid or (row.cloid is not None and row.cloid in cloids):
                raise InventoryError("duplicate venue order identity")
            # Child orders are external exposure even when the parent is recognized.
            if raw.get("children") or raw.get("isTrigger") or raw.get("reduceOnly"):
                raise InventoryError("unmanaged conditional venue exposure")
            by_oid[row.oid] = row
            if row.cloid is not None:
                cloids.add(row.cloid)
    return by_oid
