from decimal import Decimal, localcontext

import pytest

from app.portfolio_research.exposure import position_notional, calculate_exposure
from app.portfolio_research.models import sealed
from phase173_fixtures import native173, reseal
from phase172_fixtures import portfolio


@pytest.mark.parametrize("market,position,mark,expected", [
    ("BTC", "0.5", "60000", "30000"), ("ETH", "-5", "3000", "-15000"),
    ("SOL", "100", "100", "10000"), ("BTC", "0", "60000", "0"),
    ("ETH", "0.0001", "3000.1", ".30001"), ("SOL", "-100", "150", "-15000"),
    ("BTC", "1000000000000", "999999", "999999000000000000")])
def test_signed_native_units_exact_large_and_precision_boundaries(market, position, mark, expected):
    profile = portfolio((market,)).scenarios[0].captured.inputs().market_profile
    with localcontext() as ctx:
        ctx.prec = 8
        value = position_notional(market=market, base_currency=market, quote_currency="USDC",
            position_base=position, mark_price_quote=mark, profile=profile)
    assert value == Decimal(expected)


@pytest.mark.parametrize("changes", [dict(mark_price_quote=None), dict(mark_price_quote="0"),
    dict(mark_price_quote="NaN"), dict(mark_price_quote=1.1), dict(market="ETH"),
    dict(base_currency="USDC"), dict(quote_currency="USD"), dict(position_base="0.000001"),
    dict(mark_price_quote="60000.01")])
def test_missing_invalid_or_wrong_market_units_marks_rejected(changes):
    profile = portfolio(("BTC",)).scenarios[0].captured.inputs().market_profile
    args = dict(market="BTC", base_currency="BTC", quote_currency="USDC", position_base="1", mark_price_quote="60000", profile=profile)
    args.update(changes)
    with pytest.raises(ValueError): position_notional(**args)


def test_gross_net_concentration_and_explicit_denominators(native173):
    _, receipts, _, r = native173
    x = r.exposure
    assert x.gross_exposure_quote == sum(abs(p.signed_exposure_quote) for p in x.positions)
    assert x.net_exposure_quote == sum(p.signed_exposure_quote for p in x.positions)
    assert x.max_inventory_concentration == max(p.gross_concentration for p in x.positions)
    assert x.modeled_leverage == x.gross_notional_utilization
    assert x.reserved_capital_quote == sum(m.vault.reserved_capital_quote for m in receipts)
    assert x.pending_order_exposure_quote is None


@pytest.mark.parametrize("equity", ["0", "-1"])
def test_nonpositive_equity_has_no_finite_leverage(native173, equity):
    _, receipts, _, r = native173
    a = reseal(r.accounting, equity_quote=Decimal(equity))
    x = calculate_exposure(receipts, a, r.temporal)
    assert x.modeled_leverage is None and x.gross_notional_utilization is None
    assert x.reserved_capital_utilization is None


@pytest.mark.parametrize("positions,net,gross", [(("1", "2", "3"), "66450", "66450"),
    (("-1", "-2", "-3"), "-66450", "66450"), (("0.5", "-5", "100"), "30000", "60000"),
    (("0", "0", "0"), "0", "0")])
def test_long_short_mixed_and_flat_portfolios(positions, net, gross):
    p = portfolio()
    notionals = [position_notional(market=s.market, base_currency=s.market, quote_currency="USDC",
        position_base=position, mark_price_quote=s.captured.inputs().market_profile.simulated_reference_price,
        profile=s.captured.inputs().market_profile) for s, position in zip(p.scenarios, positions)]
    assert sum(notionals) == Decimal(net)
    assert sum(map(abs, notionals)) == Decimal(gross)


def test_small_repeating_ratios_remain_within_observation_precision():
    from app.portfolio_research.config import portfolio_ratio
    from app.market_data.live_models import financial_decimal
    value = portfolio_ratio(Decimal("0.000000000001"), Decimal("999999999999.999999999999999999"))
    assert value > 0 and value.as_tuple().exponent >= -60
    assert financial_decimal(value) == value


def test_oversize_marks_fail_even_with_flat_position_and_low_ambient_precision():
    profile = portfolio(("BTC",)).scenarios[0].captured.inputs().market_profile
    with localcontext() as ctx:
        ctx.prec = 8
        with pytest.raises(ValueError):
            position_notional(market="BTC", base_currency="BTC", quote_currency="USDC", position_base="0",
                mark_price_quote="1000000000000000000000000000001", profile=profile)
