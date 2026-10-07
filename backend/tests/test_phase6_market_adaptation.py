from decimal import Decimal as D
import math

import pytest
from pydantic import ValidationError

from app.market_data.history import MarketPriceHistory
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.models import (
    MarketConnectionState,
    MarketDataMode,
    MarketLevel,
    MarketSnapshot,
    OrderBookSnapshot,
    utcnow,
)
from app.strategy.inventory import build_inventory_state
from app.strategy.market_adaptation import (
    ImbalanceState,
    MarketAdaptationPolicy,
    VolatilityRegime,
    calculate_book_imbalance,
    calculate_realized_volatility,
    calculate_spread_multiplier,
    calculate_volatility_score,
)
from app.strategy.models import StrategyConfig
from app.strategy.quote_engine import QuoteEngine


def snapshot(mid: str, sequence: int, bid_sizes=None, ask_sizes=None):
    value=D(mid)
    bid_sizes=bid_sizes or [D("1"),D("1"),D("1"),D("1"),D("1")]
    ask_sizes=ask_sizes or [D("1"),D("1"),D("1"),D("1"),D("1")]
    now=utcnow()
    bids=[MarketLevel(price=value-D("0.5")-D(i),size=size) for i,size in enumerate(bid_sizes)]
    asks=[MarketLevel(price=value+D("0.5")+D(i),size=size) for i,size in enumerate(ask_sizes)]
    book=OrderBookSnapshot(market="ETH",bids=bids,asks=asks,timestamp=now,sequence=sequence)
    return MarketSnapshot(
        market="ETH",best_bid=bids[0].price,best_ask=asks[0].price,mid_price=value,book=book,
        latest_valid_update=now,connection_state=MarketConnectionState.CONNECTED,
        mode=MarketDataMode.DEMO,simulated=True,stale=False,
    )


def inventory(position="0"):
    return build_inventory_state(
        market="ETH",position=D(position),target=D("0"),soft_limit=D("5"),source="PAPER"
    )


def history_for(prices):
    h=MarketPriceHistory()
    for i,price in enumerate(prices,1):
        assert h.add_snapshot(snapshot(str(price),i))
    return h


def test_flat_series_has_zero_realized_volatility():
    assert calculate_realized_volatility([D("100"),D("100"),D("100")]) == 0


def test_known_rms_log_return_series():
    prices=[D("100"),D("110"),D("99")]
    sigma=calculate_realized_volatility(prices)
    expected=math.sqrt((math.log(1.1)**2 + math.log(0.9)**2)/2)
    assert float(sigma) == pytest.approx(expected)


def test_volatility_score_thresholds_and_clamp():
    low=D(".001"); high=D(".003")
    assert calculate_volatility_score(D("0"),low,high)==0
    assert calculate_volatility_score(low,low,high)==0
    assert calculate_volatility_score(D(".002"),low,high)==D(".5")
    assert calculate_volatility_score(high,low,high)==1
    assert calculate_volatility_score(D(".9"),low,high)==1


def test_history_warmup_duplicate_and_bound():
    h=MarketPriceHistory(max_samples=3)
    s1=snapshot("100",1)
    assert h.add_snapshot(s1)
    version=h.version
    assert not h.add_snapshot(s1)
    assert h.version==version
    h.add_snapshot(snapshot("101",2)); h.add_snapshot(snapshot("102",3)); h.add_snapshot(snapshot("103",4))
    assert len(h)==3
    assert h.prices(3)==[D("101"),D("102"),D("103")]


def test_warmup_is_explicit_and_neutral():
    config=StrategyConfig(volatility_min_samples=3,volatility_window_samples=5)
    h=history_for(["100","101"])
    decision=MarketAdaptationPolicy(config).decision(snapshot("102",3),h)
    assert decision.volatility_ready is False
    assert decision.realized_volatility is None
    assert decision.volatility_score==0
    assert decision.spread_multiplier==1
    assert decision.global_size_multiplier==1
    assert decision.regime==VolatilityRegime.WARMING_UP


def test_book_imbalance_balanced_bid_heavy_and_ask_heavy():
    balanced=snapshot("100",1)
    _,_,value=calculate_book_imbalance(balanced,5)
    assert value==0

    bid=snapshot("100",2,[D("3")]*5,[D("1")]*5)
    bd,ad,value=calculate_book_imbalance(bid,5)
    assert bd==D("15") and ad==D("5") and value==D(".5")

    ask=snapshot("100",3,[D("1")]*5,[D("3")]*5)
    _,_,value=calculate_book_imbalance(ask,5)
    assert value==D("-.5")


def test_book_imbalance_uses_available_top_n():
    s=snapshot("100",1,[D("3"),D("1")],[D("1"),D("1")])
    bid,ask,value=calculate_book_imbalance(s,5)
    assert bid==4 and ask==2 and value==D("0.3333333333333333333333333333")


def test_invalid_phase6_config_rejected():
    with pytest.raises(ValidationError):
        StrategyConfig(volatility_window_samples=5,volatility_min_samples=10)
    with pytest.raises(ValidationError):
        StrategyConfig(volatility_low_threshold=D(".01"),volatility_high_threshold=D(".01"))
    with pytest.raises(ValidationError):
        StrategyConfig(min_spread_multiplier=D(".9"))
    with pytest.raises(ValidationError):
        StrategyConfig(min_spread_multiplier=D("2"),max_spread_multiplier=D("1.5"))


def test_neutral_market_adaptation_preserves_phase5_ladder():
    config=StrategyConfig(volatility_min_samples=3)
    snap=MockMarketDataAdapter().snapshot_for(1)
    h=MarketPriceHistory(); h.add_snapshot(snap)
    engine=QuoteEngine()
    _,_,phase5,_=engine.generate_inventory_aware(config,snap,inventory())
    _,_,final,_,decision=engine.generate_market_adaptive(config,snap,inventory(),h)
    assert decision.volatility_ready is False
    assert [(q.side,q.price,q.size,q.distance_bps) for q in final] == [
        (q.side,q.price,q.size,q.distance_bps) for q in phase5
    ]


def test_high_volatility_widens_and_reduces_variable_size():
    config=StrategyConfig(
        volatility_window_samples=3,volatility_min_samples=3,
        volatility_low_threshold=D("0"),volatility_high_threshold=D(".001"),
        volatility_spread_strength=D("1"),volatility_size_strength=D(".5"),
        imbalance_spread_strength=D("0"),imbalance_size_strength=D("0"),
    )
    h=history_for(["100","105","95"])
    snap=snapshot("95",3)
    engine=QuoteEngine()
    _,_,phase5,inv_decision=engine.generate_inventory_aware(config,snap,inventory())
    _,_,final,_,decision=engine.generate_market_adaptive(config,snap,inventory(),h)
    assert decision.volatility_score==1
    assert decision.spread_multiplier==2
    assert decision.global_size_multiplier==D(".5")
    center=inv_decision.reservation_price
    before=next(q for q in phase5 if q.side=="BID")
    after=next(q for q in final if q.side=="BID")
    assert abs(after.price-center) > abs(before.price-center)
    assert after.size <= before.size
    assert after.size >= config.base_order_size


def test_bid_heavy_book_reduces_bid_more_than_ask():
    config=StrategyConfig(
        volatility_window_samples=2,volatility_min_samples=2,
        volatility_low_threshold=D("0"),volatility_high_threshold=D("1"),
        volatility_spread_strength=D("0"),volatility_size_strength=D("0"),
        imbalance_spread_strength=D("0"),imbalance_size_strength=D(".5"),
    )
    h=history_for(["100","100"])
    snap=snapshot("100",2,[D("3")]*5,[D("1")]*5)
    decision=MarketAdaptationPolicy(config).decision(snap,h)
    assert decision.imbalance_state==ImbalanceState.BID_HEAVY
    assert decision.bid_size_multiplier < decision.ask_size_multiplier
    assert decision.ask_size_multiplier==1


def test_spread_multiplier_respects_maximum():
    config=StrategyConfig(
        volatility_spread_strength=D("10"),imbalance_spread_strength=D("10"),
        max_spread_multiplier=D("2.5")
    )
    assert calculate_spread_multiplier(config,D("1"),D("1"))==D("2.5")


def test_phase6_cannot_restore_phase5_hard_limit_side():
    config=StrategyConfig(
        volatility_window_samples=2,volatility_min_samples=2,
        volatility_low_threshold=D("0"),volatility_high_threshold=D(".001"),
    )
    h=history_for(["100","110"])
    snap=snapshot("110",2)
    engine=QuoteEngine()
    _,_,final,inv_decision,_=engine.generate_market_adaptive(config,snap,inventory("10"),h)
    assert inv_decision.hard_limit_state=="LONG_LIMIT"
    assert not any(q.side=="BID" for q in final)
    assert any(q.side=="ASK" for q in final)


def test_market_adaptation_disabled_preserves_phase5_even_when_ready():
    config=StrategyConfig(
        market_adaptation_enabled=False,
        volatility_window_samples=2,volatility_min_samples=2,
        volatility_low_threshold=D("0"),volatility_high_threshold=D(".001"),
    )
    h=history_for(["100","110"])
    snap=snapshot("110",2)
    engine=QuoteEngine()
    _,_,phase5,_=engine.generate_inventory_aware(config,snap,inventory("2"))
    _,_,final,_,decision=engine.generate_market_adaptive(config,snap,inventory("2"),h)
    assert decision.volatility_ready is True
    assert decision.spread_multiplier==1
    assert [(q.price,q.size) for q in final]==[(q.price,q.size) for q in phase5]


def test_final_market_size_multiplier_respects_configured_floor():
    config=StrategyConfig(
        volatility_size_strength=D("1"),
        imbalance_size_strength=D("1"),
        min_market_size_multiplier=D(".35"),
    )
    h=history_for(["100","110"])
    config.volatility_window_samples=2
    config.volatility_min_samples=2
    config.volatility_low_threshold=D("0")
    config.volatility_high_threshold=D(".001")
    snap=snapshot("110",2,[D("5")]*5,[D("1")]*5)
    decision=MarketAdaptationPolicy(config).decision(snap,h)
    assert decision.bid_size_multiplier>=D(".35")
    assert decision.ask_size_multiplier>=D(".35")


def test_duplicate_sequence_or_timestamp_does_not_inflate_history():
    h=MarketPriceHistory(max_samples=10)
    first=snapshot("100",1)
    assert h.add_snapshot(first)
    duplicate_sequence=snapshot("101",1)
    assert not h.add_snapshot(duplicate_sequence)

    second=snapshot("102",2)
    second=second.model_copy(update={
        "latest_valid_update": first.latest_valid_update,
        "book": second.book.model_copy(update={"timestamp": first.book.timestamp}),
    })
    assert not h.add_snapshot(second)
    assert len(h)==1


def test_non_finite_depth_is_rejected():
    s=snapshot("100",1)
    bad_level=MarketLevel.model_construct(price=D("99.5"),size=D("NaN"),order_count=1)
    bad_book=s.book.model_copy(update={"bids":[bad_level]})
    bad_snapshot=s.model_copy(update={"book":bad_book})
    with pytest.raises(ValueError,match="order-book size"):
        calculate_book_imbalance(bad_snapshot,5)


def test_phase6_cannot_restore_short_hard_limit_side():
    config=StrategyConfig(
        volatility_window_samples=2,volatility_min_samples=2,
        volatility_low_threshold=D("0"),volatility_high_threshold=D(".001"),
    )
    h=history_for(["100","90"])
    snap=snapshot("90",2,[D("1")]*5,[D("5")]*5)
    engine=QuoteEngine()
    _,_,final,inv_decision,_=engine.generate_market_adaptive(config,snap,inventory("-10"),h)
    assert inv_decision.hard_limit_state=="SHORT_LIMIT"
    assert any(q.side=="BID" for q in final)
    assert not any(q.side=="ASK" for q in final)


def test_phase6_metadata_proves_inventory_then_market_composition():
    config=StrategyConfig(
        volatility_window_samples=2,volatility_min_samples=2,
        volatility_low_threshold=D("0"),volatility_high_threshold=D(".001"),
        volatility_spread_strength=D("1"),volatility_size_strength=D(".5"),
    )
    h=history_for(["100","105"])
    snap=snapshot("105",2)
    engine=QuoteEngine()
    fair,_,phase5,inventory_decision=engine.generate_inventory_aware(config,snap,inventory("2.5"))
    fair2,_,final,inventory_decision2,market_decision=engine.generate_market_adaptive(
        config,snap,inventory("2.5"),h
    )
    assert fair2==fair
    assert inventory_decision2.reservation_price==inventory_decision.reservation_price
    assert inventory_decision.reservation_price != fair
    assert market_decision.spread_multiplier>1
    phase5_by_key={(q.side,q.level_index):q for q in phase5}
    for quote in final:
        before=phase5_by_key[(quote.side,quote.level_index)]
        assert quote.pre_market_adaptation_price==before.price
        assert quote.pre_market_adaptation_size==before.size


def test_changed_same_identity_depth_advances_authority_without_duplicate_price_sample():
    h=MarketPriceHistory()
    initial=snapshot('100',1)
    assert h.add_snapshot(initial)
    version=h.version
    changed=initial.model_copy(deep=True)
    changed.book.bids[0].size=D('100')
    assert not h.add_snapshot(changed)
    assert len(h)==1 and h.version==version+1
    assert not h.add_snapshot(changed.model_copy(deep=True))
    assert h.version==version+1
    # An old observation cannot roll back the material authority watermark.
    old=initial.model_copy(deep=True)
    from datetime import timedelta
    old.latest_valid_update-=timedelta(milliseconds=1)
    assert not h.add_snapshot(old)
    assert h.version==version+1
