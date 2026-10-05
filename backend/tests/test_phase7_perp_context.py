from datetime import timedelta
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from app.market_data.mock import MockMarketDataAdapter
from app.market_data.perp_context import (
    PerpContextService,
    build_perp_market_context,
    demo_perp_context,
    normalize_active_asset_ctx,
    normalize_meta_and_asset_ctxs,
    normalize_user_position_context,
    utcnow,
)
from app.strategy.models import StrategyConfig
from app.strategy.perp_policy import (
    PerpContextPolicy,
    calculate_blended_reference,
    calculate_funding_score,
    calculate_funding_shift_bps,
    clamp_reference_shift,
)


def active(mark="3004.2", oracle="3001.5", funding="0.00010", oi="251430.2", mid="3002.9", premium="0.0009"):
    return {
        "channel":"activeAssetCtx",
        "data":{
            "coin":"ETH",
            "ctx":{
                "markPx":mark,
                "oraclePx":oracle,
                "funding":funding,
                "openInterest":oi,
                "midPx":mid,
                "premium":premium,
            },
        },
    }


def context(**kwargs):
    base=dict(
        market="ETH",
        market_mid=D("3002.9"),
        mark_price=D("3004.2"),
        oracle_price=D("3001.5"),
        funding_rate=D("0.00010"),
        open_interest_base=D("251430.2"),
        premium=D("0.0009"),
        provider_mid_price=D("3002.9"),
        updated_at=utcnow(),
        source="HYPERLIQUID",
        simulated=False,
        version=1,
    )
    base.update(kwargs)
    return build_perp_market_context(**base)


def test_active_asset_context_normalization_and_exact_basis():
    c=normalize_active_asset_ctx(active(),"ETH")
    assert c.mark_price==D("3004.2")
    assert c.oracle_price==D("3001.5")
    assert c.funding_rate==D("0.00010")
    assert c.open_interest_base==D("251430.2")
    assert c.open_interest_notional==D("251430.2")*D("3004.2")
    assert c.mark_oracle_basis_bps==(D("3004.2")-D("3001.5"))/D("3001.5")*D("10000")
    assert c.mark_mid_basis_bps==(D("3004.2")-D("3002.9"))/D("3002.9")*D("10000")
    assert c.oracle_mid_basis_bps==(D("3001.5")-D("3002.9"))/D("3002.9")*D("10000")


@pytest.mark.parametrize("mark,oracle,expected",[
    ("3000","3000",D("0")),
    ("3001","3000",D("1")/D("3000")*D("10000")),
    ("2999","3000",D("-1")/D("3000")*D("10000")),
])
def test_basis_signs(mark,oracle,expected):
    c=normalize_active_asset_ctx(active(mark=mark,oracle=oracle,mid="3000"),"ETH")
    assert c.mark_oracle_basis_bps==expected


def test_meta_context_maps_by_name_not_array_position():
    payload=[
        {"universe":[{"name":"BTC","szDecimals":5},{"name":"ETH","szDecimals":4}]},
        [
            {"markPx":"60000","oraclePx":"59900","funding":"0","openInterest":"10","midPx":"59950","premium":"0"},
            {"markPx":"3004","oraclePx":"3001","funding":"0.0001","openInterest":"200","midPx":"3002","premium":"0.001"},
        ],
    ]
    c=normalize_meta_and_asset_ctxs(payload,"ETH")
    assert c.market=="ETH" and c.mark_price==D("3004") and c.open_interest_base==D("200")


@pytest.mark.parametrize("payload,match",[
    (active(mark="NaN"),"non-finite mark price"),
    (active(oracle="-1"),"oracle price must be positive"),
    (active(funding="Infinity"),"non-finite funding rate"),
    (active(oi="-1"),"open interest must be non-negative"),
])
def test_invalid_execution_relevant_perp_values_rejected(payload,match):
    with pytest.raises(ValueError,match=match):
        normalize_active_asset_ctx(payload,"ETH")


def test_wrong_or_duplicate_market_mapping_rejected():
    with pytest.raises(ValueError,match="market/context mismatch"):
        normalize_active_asset_ctx(active(),"BTC")
    payload=[{"universe":[{"name":"ETH"},{"name":"ETH"}]},[{},{}]]
    with pytest.raises(ValueError,match="missing or duplicate"):
        normalize_meta_and_asset_ctxs(payload,"ETH")


@pytest.mark.parametrize("funding,expected",[("0.00025",D("1")),("-0.00025",D("-1")),("0",D("0")),("0.01",D("1")),("-0.01",D("-1"))])
def test_funding_score_clamps(funding,expected):
    assert calculate_funding_score(D(funding),D("0.00025"))==expected


def test_funding_shift_direction_and_bound():
    assert calculate_funding_shift_bps(D("1"),D("5"))==D("-5")
    assert calculate_funding_shift_bps(D("-1"),D("5"))==D("5")
    assert calculate_funding_shift_bps(D("0"),D("5"))==0


def test_weighted_reference_and_total_shift_clamp():
    blended,mid_weight=calculate_blended_reference(D("3000"),D("3010"),D("2990"),D(".25"),D(".25"))
    assert mid_weight==D(".5")
    assert blended==D("3000")
    final,shift=clamp_reference_shift(D("3000"),D("3300"),D("50"))
    assert shift==D("50")
    assert final==D("3015")


def test_reference_policy_funding_positive_biases_against_long():
    config=StrategyConfig(
        perp_mark_weight=D("0"),perp_oracle_weight=D("0"),
        funding_reference_abs_rate=D("0.00025"),
        max_funding_reference_shift_bps=D("5"),
    )
    d=PerpContextPolicy(config).decision(D("3000"),context(market_mid=D("3000"),mark_price=D("3000"),oracle_price=D("3000")))
    assert d.blended_reference_price==D("3000")
    assert d.funding_score==D(".4")
    assert d.funding_shift_bps==D("-2.0")
    assert d.final_reference_price < D("3000")


def test_reference_policy_negative_funding_biases_against_short():
    config=StrategyConfig(perp_mark_weight=D("0"),perp_oracle_weight=D("0"))
    d=PerpContextPolicy(config).decision(
        D("3000"),context(market_mid=D("3000"),mark_price=D("3000"),oracle_price=D("3000"),funding_rate=D("-0.00025"))
    )
    assert d.funding_score==-1
    assert d.funding_shift_bps==D("5")
    assert d.final_reference_price>D("3000")


def test_disabled_policy_returns_raw_market_fair():
    config=StrategyConfig(perp_context_enabled=False)
    d=PerpContextPolicy(config).decision(D("3000"),context())
    assert d.enabled is False
    assert d.final_reference_price==D("3000")
    assert d.final_reference_shift_bps==0
    assert d.funding_shift_bps==0


def test_invalid_perp_config_rejected():
    with pytest.raises(ValidationError):
        StrategyConfig(perp_mark_weight=D(".8"),perp_oracle_weight=D(".3"))
    with pytest.raises(ValidationError):
        StrategyConfig(funding_reference_abs_rate=D("0"))
    with pytest.raises(ValidationError):
        StrategyConfig(perp_mark_weight=D("NaN"))


def test_perp_context_version_semantics_and_staleness():
    service=PerpContextService("ETH",1)
    now=utcnow()
    first=context(updated_at=now,version=0)
    assert service.accept(first)
    assert service.version==1
    identical=context(updated_at=now+timedelta(milliseconds=100),version=0)
    assert service.accept(identical) is False
    assert service.version==1
    assert service.snapshot(D("3002.9"),now=now+timedelta(milliseconds=500)).version==1
    changed=context(mark_price=D("3005"),updated_at=now+timedelta(milliseconds=200),version=0)
    assert service.accept(changed)
    assert service.version==2
    with pytest.raises(RuntimeError,match="stale"):
        service.snapshot(D("3002.9"),now=now+timedelta(seconds=2))


def test_demo_context_is_explicitly_simulated():
    snap=MockMarketDataAdapter().snapshot_for(7)
    c=demo_perp_context(snap)
    assert c.source=="DEMO"
    assert c.simulated is True
    assert c.market==snap.market
    assert c.mark_price>0 and c.oracle_price>0 and c.open_interest_base>0


def test_user_position_context_long_short_flat_and_fields():
    state={"assetPositions":[{"position":{
        "coin":"ETH","szi":"2.25","entryPx":"3000","leverage":{"type":"cross","value":5},
        "liquidationPx":"2400","marginUsed":"1200","positionValue":"6750",
        "unrealizedPnl":"12.5","returnOnEquity":"0.0104"
    }}]}
    p=normalize_user_position_context(state,"ETH")
    assert p.signed_position_base==D("2.25")
    assert p.entry_price==D("3000")
    assert p.leverage_type=="cross" and p.leverage_value==D("5")
    assert p.liquidation_price==D("2400")
    assert p.unrealized_pnl==D("12.5")
    short=normalize_user_position_context({"assetPositions":[{"position":{"coin":"ETH","szi":"-1","entryPx":None,"leverage":{"type":"isolated","value":3},"liquidationPx":None,"marginUsed":"1","positionValue":"2","unrealizedPnl":"-1","returnOnEquity":"-0.1"}}]},"ETH")
    assert short.signed_position_base==D("-1") and short.liquidation_price is None
    flat=normalize_user_position_context({"assetPositions":[]},"ETH")
    assert flat.signed_position_base==0 and flat.entry_price is None
