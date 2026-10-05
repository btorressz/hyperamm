from decimal import Decimal as D
from datetime import timedelta
import pytest
from pydantic import ValidationError

from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
from app.execution.models import OrderRequest
from app.execution.paper import PaperExecutionAdapter
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.models import utcnow
from app.strategy.inventory import (
    HardInventoryLimitState, InventoryPolicy, build_inventory_state,
    calculate_inventory_ratio, calculate_reservation_price,
    calculate_side_size_multipliers, clamp_inventory_ratio,
)
from app.strategy.models import StrategyConfig
from app.strategy.quote_engine import QuoteEngine


def inv(position="0", target="0", soft="5", *, stale=False):
    return build_inventory_state(
        market="ETH", position=D(position), target=D(target), soft_limit=D(soft),
        source="PAPER", stale=stale,
    )


def test_inventory_ratio_target_and_clamping():
    assert calculate_inventory_ratio(D("2.5"), D("0"), D("5")) == D(".5")
    assert calculate_inventory_ratio(D("-2.5"), D("0"), D("5")) == D("-.5")
    assert calculate_inventory_ratio(D("3"), D("1"), D("4")) == D(".5")
    assert clamp_inventory_ratio(D("2")) == D("1")
    assert clamp_inventory_ratio(D("-2")) == D("-1")


def test_reservation_price_is_bounded_and_symmetric():
    fair=D("3000")
    long,long_bps=calculate_reservation_price(fair,D(".5"),D("20"))
    short,short_bps=calculate_reservation_price(fair,D("-.5"),D("20"))
    bound,bound_bps=calculate_reservation_price(fair,D("99"),D("20"))
    assert long < fair < short
    assert (long_bps,short_bps)==(D("-10"),D("10"))
    assert bound_bps==D("-20") and bound==fair*D(".998")


def test_size_multiplier_direction_and_bounds():
    bid,ask=calculate_side_size_multipliers(D(".5"),D(".75"),D(".25"),D("1.75"))
    assert bid < 1 < ask
    bid,ask=calculate_side_size_multipliers(D("-.5"),D(".75"),D(".25"),D("1.75"))
    assert bid > 1 > ask
    assert calculate_side_size_multipliers(D("5"),D("2"),D(".25"),D("1.75"))==(D(".25"),D("1.75"))


def test_invalid_inventory_config_rejected():
    with pytest.raises(ValidationError):
        StrategyConfig(soft_inventory_limit_base=D("10"),hard_inventory_limit_base=D("10"))
    with pytest.raises(ValidationError):
        StrategyConfig(target_inventory_base=D("NaN"))
    with pytest.raises(ValidationError):
        StrategyConfig(min_inventory_size_multiplier=D("1.1"))


def test_neutral_inventory_preserves_phase_4_1_ladder():
    config=StrategyConfig()
    snap=MockMarketDataAdapter().snapshot_for(1)
    fair,pool,neutral=QuoteEngine().generate(config,snap)
    fair2,pool2,final,decision=QuoteEngine().generate_inventory_aware(config,snap,inv())
    assert fair2==fair and pool2==pool
    assert [(q.side,q.price,q.size,q.level_index,q.distance_bps) for q in final] == [
        (q.side,q.price,q.size,q.level_index,q.distance_bps) for q in neutral
    ]
    assert decision.reservation_price==fair
    assert decision.bid_size_multiplier==decision.ask_size_multiplier==1


@pytest.mark.parametrize("position,long_inventory",[("2.5",True),("-2.5",False)])
def test_inventory_skew_direction_and_uncrossed_ordering(position,long_inventory):
    config=StrategyConfig()
    snap=MockMarketDataAdapter().snapshot_for(1)
    fair,_,neutral=QuoteEngine().generate(config,snap)
    _,_,final,decision=QuoteEngine().generate_inventory_aware(config,snap,inv(position))
    bids=[q for q in final if q.side=="BID"]; asks=[q for q in final if q.side=="ASK"]
    assert bids==sorted(bids,key=lambda q:q.price,reverse=True)
    assert asks==sorted(asks,key=lambda q:q.price)
    assert bids[0].price < asks[0].price
    if long_inventory:
        assert decision.reservation_price < fair
        assert decision.bid_size_multiplier < 1 < decision.ask_size_multiplier
        assert sum(q.size for q in bids) < sum(q.size for q in neutral if q.side=="BID")
        assert sum(q.size for q in asks) > sum(q.size for q in neutral if q.side=="ASK")
    else:
        assert decision.reservation_price > fair
        assert decision.bid_size_multiplier > 1 > decision.ask_size_multiplier


def test_hard_limits_suppress_only_inventory_increasing_side():
    config=StrategyConfig()
    snap=MockMarketDataAdapter().snapshot_for(1)
    _,_,long_quotes,long_decision=QuoteEngine().generate_inventory_aware(config,snap,inv("10"))
    assert long_decision.hard_limit_state==HardInventoryLimitState.LONG_LIMIT
    assert not any(q.side=="BID" for q in long_quotes)
    assert any(q.side=="ASK" for q in long_quotes)
    _,_,short_quotes,short_decision=QuoteEngine().generate_inventory_aware(config,snap,inv("-10"))
    assert short_decision.hard_limit_state==HardInventoryLimitState.SHORT_LIMIT
    assert any(q.side=="BID" for q in short_quotes)
    assert not any(q.side=="ASK" for q in short_quotes)


def test_hard_limit_safety_remains_when_skew_disabled():
    config=StrategyConfig(inventory_skew_enabled=False)
    snap=MockMarketDataAdapter().snapshot_for(1)
    fair,_,quotes,decision=QuoteEngine().generate_inventory_aware(config,snap,inv("10"))
    assert decision.reservation_price==fair
    assert decision.bid_size_multiplier==decision.ask_size_multiplier==1
    assert not any(q.side=="BID" for q in quotes)


@pytest.mark.asyncio
async def test_paper_inventory_derives_only_from_economic_fills():
    ex=PaperExecutionAdapter()
    snap=MockMarketDataAdapter().snapshot_for(1)
    ex.update_market(snap)
    await ex.submit_orders([
        OrderRequest(client_order_id="buy",market="ETH",side="BID",price=snap.best_ask,size=D("2")),
        OrderRequest(client_order_id="sell",market="ETH",side="ASK",price=snap.best_bid,size=D(".5")),
        OrderRequest(client_order_id="rest",market="ETH",side="BID",price=snap.best_bid-D("20"),size=D("9")),
    ])
    assert ex.position_base("ETH")==D("1.5")
    await ex.cancel_orders(["rest"])
    assert ex.position_base("ETH")==D("1.5")


def test_testnet_user_state_normalizes_signed_position_and_ignores_other_markets():
    payload={"assetPositions":[
        {"position":{"coin":"BTC","szi":"99"}},
        {"position":{"coin":"ETH","szi":"-2.25"}},
    ]}
    assert HyperliquidTestnetExecutionAdapter.normalize_user_position(payload,"ETH")==D("-2.25")
    assert HyperliquidTestnetExecutionAdapter.normalize_user_position({"assetPositions":[]},"ETH")==0
    with pytest.raises(ValueError):
        HyperliquidTestnetExecutionAdapter.normalize_user_position({"assetPositions":[{}]},"ETH")


def test_inventory_policy_rejects_stale_or_config_mismatch():
    config=StrategyConfig()
    with pytest.raises(ValueError,match="stale"):
        InventoryPolicy(config).decision(D("3000"),inv("1",stale=True))
    mismatch=inv("1",target="1")
    with pytest.raises(ValueError,match="configuration"):
        InventoryPolicy(config).decision(D("3000"),mismatch)
