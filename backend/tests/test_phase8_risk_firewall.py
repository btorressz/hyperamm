from decimal import Decimal as D

from app.amm.models import AmmModel,QuoteLevel
from app.execution.models import OrderStatus,StrategyOrder
from app.references.models import PriceEvidence,ProviderId,ProviderStatus,ReferenceConsensus,ReferenceSnapshot,SourceType,utcnow
from app.risk.firewall import (
    PnlDrawdown,RiskFirewall,RiskFirewallConfig,RiskState,
    exposure_metrics,liquidation_evidence,paper_pnl,
)
from app.execution.models import Fill


def quote(side,price,size,level=0,intent="NEUTRAL"):
    return QuoteLevel(side=side,price=D(price),size=D(size),level_index=level,distance_bps=D("10"),source_model=AmmModel.CONSTANT_PRODUCT,market_fair_value=D("3000"),inventory_intent=intent)


def refs(mid_dev="0",confidence="VERIFIED",version=1):
    now=utcnow();consensus=D("3000");mid=consensus*(D("1")+D(mid_dev)/D("10000"))
    ev={}
    for p,t,px in [
        (ProviderId.REDSTONE,SourceType.ORACLE,consensus),
        (ProviderId.HYPERLIQUID_ORACLE,SourceType.NATIVE_ORACLE,consensus),
        (ProviderId.KRAKEN,SourceType.VENUE_REFERENCE,consensus),
        (ProviderId.COINGECKO,SourceType.AGGREGATOR_REFERENCE,consensus),
        (ProviderId.HYPERLIQUID_MID,SourceType.EXECUTION_VENUE,mid),
        (ProviderId.HYPERLIQUID_MARK,SourceType.PERP_MARK,consensus),
    ]:
        ev[p.value]=PriceEvidence(market="ETH",provider=p,source_type=t,price=px,observed_at=now,source_timestamp=now,healthy=True,status=ProviderStatus.HEALTHY,version=version)
    c=ReferenceConsensus(market="ETH",primary_oracle_price=consensus,native_oracle_price=consensus,exchange_reference_price=consensus,aggregate_reference_price=consensus,consensus_price=consensus,healthy_sources=6,healthy_core_sources=3,confidence_state=confidence,max_source_deviation_bps=D("0"),source_statuses={k:"HEALTHY" for k in ev},eligible_providers=["REDSTONE","HYPERLIQUID_ORACLE","KRAKEN"],version=version,updated_at=now)
    dev={"hl_mid_consensus":D(mid_dev),"hl_mark_consensus":D("0"),"hl_oracle_consensus":D("0")}
    return ReferenceSnapshot(market="ETH",evidence=ev,consensus=c,deviations_bps=dev,deviation_magnitudes_bps={k:abs(v) for k,v in dev.items()},version=version,updated_at=now)


def pnl(value="0"):
    return PnlDrawdown(realized_pnl=D("0"),unrealized_pnl=D(value),session_pnl=D(value),source="TEST")


def evaluate(fw,r,quotes=None,position=D("0"),liq=None,existing=None):
    return fw.evaluate(refs=r,quotes=quotes or [quote("BID","2990","1"),quote("ASK","3010","1")],current_position=position,mark=D("3000"),liquidation=liq,pnl=pnl(),market_version=1,inventory_version=1,perp_version=1,existing_orders=existing)


def test_risk_states_and_quote_transformations():
    cfg=RiskFirewallConfig(max_projected_long_base=D("20"),max_projected_short_base=D("20"))
    for dev,state in [("0",RiskState.NORMAL),("25",RiskState.WIDEN),("45",RiskState.REDUCE),("85",RiskState.HALT)]:
        fw=RiskFirewall(cfg);d=evaluate(fw,refs(dev))
        assert d.state==state
        original=[quote("BID","2990","1",0,"INVENTORY_INCREASING"),quote("ASK","3010","1",0,"INVENTORY_REDUCING")]
        transformed=fw.transform(original,d,center=D("3000"),tick_size=D(".1"),size_precision=4,base_order_size=D(".1"))
        if state==RiskState.NORMAL:
            assert [(q.price,q.size) for q in transformed]==[(q.price,q.size) for q in original]
        elif state==RiskState.WIDEN:
            assert transformed[0].price<original[0].price and transformed[1].price>original[1].price
        elif state==RiskState.REDUCE:
            assert transformed[0].size<transformed[1].size<original[1].size
        else:
            assert transformed==[]


def test_hysteresis_requires_confirmations_to_recover():
    cfg=RiskFirewallConfig(max_projected_long_base=D("20"),max_projected_short_base=D("20"),risk_recovery_confirmations=3)
    fw=RiskFirewall(cfg)
    assert evaluate(fw,refs("85")).state==RiskState.HALT
    d=evaluate(fw,refs("45"));assert d.state==RiskState.HALT and d.healthy_confirmation_count==1
    d=evaluate(fw,refs("45"));assert d.state==RiskState.HALT and d.healthy_confirmation_count==2
    d=evaluate(fw,refs("45"));assert d.state==RiskState.REDUCE
    assert evaluate(fw,refs("25")).state==RiskState.REDUCE
    assert evaluate(fw,refs("25")).state==RiskState.REDUCE
    assert evaluate(fw,refs("25")).state==RiskState.WIDEN


def test_existing_keep_level_is_not_double_counted_but_unmatched_resting_is_counted():
    desired=[quote("BID","2990","1",0),quote("ASK","3010","1",0)]
    existing=[
        StrategyOrder(client_order_id="keep",market="ETH",side="BID",price=D("2990"),size=D("1"),level_index=0,status=OrderStatus.OPEN),
        StrategyOrder(client_order_id="old",market="ETH",side="BID",price=D("2980"),size=D("2"),level_index=5,status=OrderStatus.OPEN),
    ]
    e=exposure_metrics(desired,D("0"),D("3000"),D("10"),existing)
    assert e.bid_quantity==D("3")
    assert e.projected_long_base==D("3")


def test_unknown_venue_exposure_halts():
    fw=RiskFirewall(RiskFirewallConfig(max_projected_long_base=D("20"),max_projected_short_base=D("20")))
    d=fw.evaluate(refs=refs("0"),quotes=[quote("BID","2990","1")],current_position=D("0"),mark=D("3000"),liquidation=None,pnl=pnl(),market_version=1,inventory_version=1,perp_version=1,venue_uncertain=True)
    assert d.state==RiskState.HALT


def test_liquidation_distance_long_short_null_and_thresholds():
    assert liquidation_evidence(D("1"),D("3000"),D("2700")).distance_bps==D("1000")
    assert liquidation_evidence(D("-1"),D("3000"),D("3300")).distance_bps==D("1000")
    assert liquidation_evidence(D("1"),D("3000"),None).status=="UNAVAILABLE"
    assert liquidation_evidence(D("0"),D("3000"),None).status=="FLAT"
    cfg=RiskFirewallConfig(max_projected_long_base=D("20"),max_projected_short_base=D("20"))
    fw=RiskFirewall(cfg)
    assert evaluate(fw,refs("0"),position=D("1"),liq=D("3030")).state==RiskState.HALT


def test_paper_pnl_uses_fills_only_for_long_and_short():
    fills=[
        Fill(client_order_id="a",market="ETH",side="BID",price=D("100"),size=D("2")),
        Fill(client_order_id="b",market="ETH",side="ASK",price=D("110"),size=D("1")),
    ]
    p=paper_pnl(fills,"ETH",D("105"))
    assert p.realized_pnl==D("10") and p.unrealized_pnl==D("5") and p.session_pnl==D("15")
    shorts=[
        Fill(client_order_id="s1",market="ETH",side="ASK",price=D("100"),size=D("2")),
        Fill(client_order_id="s2",market="ETH",side="BID",price=D("90"),size=D("1")),
    ]
    p=paper_pnl(shorts,"ETH",D("95"))
    assert p.realized_pnl==D("10") and p.unrealized_pnl==D("5")


def test_manual_kill_state_is_not_part_of_automatic_firewall_state():
    fw=RiskFirewall(RiskFirewallConfig(max_projected_long_base=D("20"),max_projected_short_base=D("20")))
    assert evaluate(fw,refs("85")).state==RiskState.HALT
    assert fw.state==RiskState.HALT
