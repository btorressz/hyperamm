"""Financial field policy for qualified Hyperliquid public perpetual responses."""

from decimal import Decimal

from app.accounting.config import bounded_exact_decimal

HYPERLIQUID_INTERVAL_SECONDS = 3600
HOURLY_FUNDING_CAP = Decimal("0.005")
QUOTE_UNIT_FIELDS = ("quoteUnit", "markQuoteUnit", "prevDayQuoteUnit", "oracleQuoteUnit", "midQuoteUnit")


def hourly_funding_rate(raw):
    """Normalize a signed fraction for one official hourly interval."""
    rate = bounded_exact_decimal(raw)
    if rate.copy_abs() > HOURLY_FUNDING_CAP:
        raise ValueError("funding outside supported hourly bounds")
    return rate


def public_price(raw):
    price = bounded_exact_decimal(raw)
    if price <= 0:
        raise ValueError("price must be positive")
    return price


def has_quote_unit_claim(row):
    # The documented public response has no denomination tags to authenticate.
    return any(field in row for field in QUOTE_UNIT_FIELDS)


def collateral_matches(raw, expected_index):
    if "collateralToken" not in raw:
        return expected_index is None
    index = raw["collateralToken"]
    return type(index) is int and index == expected_index


def context_binding(record):
    return (record.identity, record.source_coin, record.universe_index, record.sz_decimals, record.listed)


def context_row_error(row, record):
    if not isinstance(row, dict):
        return "INVALID_DATA"
    identity = record.identity
    if row.get("network", identity.network) != identity.network:
        return "NETWORK_MISMATCH"
    index = row.get("universeIndex", record.universe_index)
    if (row.get("coin", record.source_coin) != record.source_coin or row.get("dex", identity.dex) != identity.dex
            or type(index) is not int or index != record.universe_index):
        return "NAMESPACE_CONFLICT"
    return None
