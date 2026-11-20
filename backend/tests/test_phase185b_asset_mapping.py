from decimal import Decimal, localcontext

import pytest

from app.amm.asset_policy import apply_asset_research_policy
from app.amm.models import AmmModel
from app.simulation.market_profiles import GeneralizedPrecisionError, round_level, validate_price
from app.strategy.models import StrategyConfig
from test_phase182_generalized_paper import evidence
from test_phase185a_asset_amm_contracts import controls, policy as declaration

D = Decimal


def policy(record, **values):
    return declaration(record, **{"declared_at": record.observed_at, **values})


@pytest.mark.parametrize(("name", "dex", "precision", "reference"), [
    ("BTC", "", 5, "60000"), ("ETH", "", 4, "3000"), ("SOL", "", 2, "150"),
    ("GOLD", "xyz", 3, "2500"), ("OIL", "other", 0, "0.001"),
    ("DOGE", "", 2, "0.1234"), ("INDEX", "xyz", 6, "10000000"),
])
@pytest.mark.parametrize("model", list(AmmModel))
def test_mapping_uses_discovery_precision_and_preserves_baseline(name, dex, precision, reference, model):
    record = evidence(name=name, dex=dex, precision=precision)
    baseline = StrategyConfig(market=record.identity.stable_key, quote_refresh_interval_ms=1500,
                              volatility_window_samples=75, imbalance_size_strength="0.4")
    original = baseline.model_dump()
    settings = controls(amm_model=model, levels_per_side=2, base_order_size="1", total_liquidity="4",
                        virtual_base_reserve="100", virtual_quote_reserve="310000")
    declared = policy(record, controls=settings, simulated_reference_price=reference)
    mapped = apply_asset_research_policy(baseline, declared, metadata=record)
    with localcontext(prec=5):
        assert apply_asset_research_policy(baseline, declared, metadata=record) == mapped
    assert mapped is not baseline and baseline.model_dump() == original
    assert mapped.size_precision == precision
    assert mapped.tick_size == D(1).scaleb(precision - 6)
    assert mapped.amm_model == model and mapped.virtual_quote_reserve == D("310000")
    assert mapped.quote_refresh_interval_ms == 1500 and mapped.volatility_window_samples == 75
    assert mapped.imbalance_size_strength == D("0.4")


@pytest.mark.parametrize("record", [
    evidence(name="OIL", dex="other", precision=3),
    evidence(name="OIL", dex="xyz", precision=3, network="TESTNET"),
    evidence(name="OIL", dex="xyz", precision=2),
    evidence(name="OIL", dex="xyz", precision=3, listed=False),
])
def test_mapping_rejects_wrong_market_or_metadata(record):
    original = evidence(name="OIL", dex="xyz", precision=3)
    declared = policy(original, simulated_reference_price="100")
    baseline = StrategyConfig(market=record.identity.stable_key)
    with pytest.raises(ValueError, match="matching listed metadata"):
        apply_asset_research_policy(baseline, declared, metadata=record)


def test_mapping_revalidates_mutated_inputs_and_blocks_unrepresentable_minimums():
    record = evidence(precision=2)
    baseline = StrategyConfig(market=record.identity.stable_key)
    declared = policy(record, simulated_reference_price="1")
    with pytest.raises(ValueError, match="synthetic PAPER"):
        apply_asset_research_policy(StrategyConfig(market=baseline.market, execution_mode="TESTNET"),
                                    declared, metadata=record)
    for name, value in [
        ("base_order_size", 0.1), ("virtual_quote_reserve", D("Infinity")),
        ("virtual_base_reserve", D("1e99")), ("concentration_upper_bps", D("1")),
    ]:
        forged = declared.model_copy(update={"controls": declared.controls.model_copy(update={name: value})})
        with pytest.raises(ValueError):
            apply_asset_research_policy(baseline, forged, metadata=record)
    for size in ("0.001", "0.011"):
        with pytest.raises(GeneralizedPrecisionError, match="SIZE_UNREPRESENTABLE"):
            apply_asset_research_policy(baseline, policy(record, controls=controls(base_order_size=size)),
                                        metadata=record)
    with pytest.raises(GeneralizedPrecisionError, match="PRICE_UNREPRESENTABLE"):
        apply_asset_research_policy(baseline, policy(record, simulated_reference_price="0.000001"),
                                    metadata=record)
    with pytest.raises(ValueError, match="two-sided capacity"):
        apply_asset_research_policy(baseline, policy(record, controls=controls(target_inventory_base="10")),
                                    metadata=record)


@pytest.mark.parametrize(("price", "size", "precision"), [
    ("9999.91", "0.035001", 5), ("1000010.9", "0.035001", 6), ("0.001234567", "118.99999", 0),
])
def test_outward_rounding_preserves_size_and_notional(price, size, precision):
    price, size = D(price), D(size)
    bid, bid_size = round_level(price, size, precision, up=False)
    ask, ask_size = round_level(price, size, precision, up=True)
    assert 0 < bid < price < ask and validate_price(bid, precision) and validate_price(ask, precision)
    assert bid_size <= size and ask_size <= size
    assert bid * bid_size <= price * size and ask * ask_size <= price * size


def test_outward_rounding_does_not_promote_a_lot():
    assert round_level(D("100.002"), D("0.01"), 2, up=True) == (D("100.01"), D("0.00"))
