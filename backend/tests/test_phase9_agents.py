from datetime import timedelta
from decimal import Decimal as D

import pytest

from app.agents.config import AgentConfig
from app.agents.evidence import AgentTelemetryStore
from app.agents.execution_quality import ExecutionQualityAgent,churn_ratio,spread_capture_bps
from pydantic import ValidationError

from app.agents.models import (
    AgentEvidenceSnapshot,AgentHealth,AgentSupervisorDecision,
    ExecutionQualityAgentOutput,ExecutionQualityMetrics,ExecutionQualityState,
    MarketRegime,RegimeAgentOutput,RegimeDirection,
    ToxicFlowAgentOutput,ToxicFlowMetrics,ToxicFlowState,semantic_fingerprint,
)
from app.agents.regime import RegimeAgent
from app.agents.supervisor import AgentSupervisor,transform_quotes
from app.agents.toxic_flow import ToxicFlowAgent
from app.amm.models import AmmModel,QuoteLevel
from app.execution.models import Fill
from app.market_data.history import MarketPriceHistory
from app.market_data.models import MarketConnectionState,MarketDataMode,MarketLevel,MarketSnapshot,OrderBookSnapshot,utcnow
from app.risk.firewall import ExposureMetrics,LiquidationEvidence,PnlDrawdown,RiskDecision,RiskFirewall,RiskFirewallConfig,RiskState


def evidence(**updates):
    data=dict(
        market="ETH",market_version=10,inventory_version=2,perp_version=3,reference_version=4,
        market_adaptation_regime="NORMAL",realized_volatility=D(".0003"),volatility_score=D(".2"),
        book_imbalance=D("0"),history_sample_count=20,momentum_bps=D("0"),
        inventory_position_base=D("0"),inventory_ratio=D("0"),mark_price=D("3000"),
        oracle_price=D("3000"),funding_rate=D("0"),open_interest_base=D("100"),
        mark_oracle_basis_bps=D("0"),mark_mid_basis_bps=D("0"),
        reference_confidence="VERIFIED",max_reference_deviation_bps=D("2"),
        simulated=True,version=123,
    )
    data.update(updates)
    return AgentEvidenceSnapshot(**data)


def snapshot(price,sequence,timestamp=None):
    p=D(str(price));ts=timestamp or utcnow()
    bids=[MarketLevel(price=p-D(".5"),size=D("1"))]
    asks=[MarketLevel(price=p+D(".5"),size=D("1"))]
    return MarketSnapshot(
        market="ETH",best_bid=bids[0].price,best_ask=asks[0].price,mid_price=p,
        book=OrderBookSnapshot(market="ETH",bids=bids,asks=asks,timestamp=ts,sequence=sequence),
        latest_valid_update=ts,connection_state=MarketConnectionState.CONNECTED,
        mode=MarketDataMode.DEMO,simulated=True,stale=False,
    )


def history(prices,start=None,step=1):
    h=MarketPriceHistory()
    start=start or utcnow()
    for i,p in enumerate(prices):
        assert h.add_snapshot(snapshot(p,i+1,start+timedelta(seconds=i*step)))
    return h


def quote(side,price,size="1",level=0):
    return QuoteLevel(side=side,price=D(price),size=D(size),level_index=level,distance_bps=D("10"),source_model=AmmModel.CONSTANT_PRODUCT,market_fair_value=D("3000"))


def neutral_toxic(ev,spread="1",bid="1",ask="1",state=ToxicFlowState.NORMAL,max_levels=None):
    metrics=ToxicFlowMetrics(total_fills=5,matured_fills=5,pending_markouts=0,adverse_fill_count=0,adverse_fill_rate=D("0"),bid_toxic_flow_score=D("0"),ask_toxic_flow_score=D("0"),overall_toxic_flow_score=D("0"))
    return ToxicFlowAgentOutput(agent="TOXIC_FLOW",health=AgentHealth.READY,confidence=D("1"),spread_multiplier=D(spread),bid_size_multiplier=D(bid),ask_size_multiplier=D(ask),max_levels=max_levels,reasons=["fixture"],simulated=True,evidence_version=ev.version,version=1,state=state,metrics=metrics)


def neutral_regime(ev,spread="1",size="1",state=MarketRegime.NORMAL,max_levels=None):
    return RegimeAgentOutput(agent="REGIME",health=AgentHealth.READY,confidence=D("1"),spread_multiplier=D(spread),bid_size_multiplier=D(size),ask_size_multiplier=D(size),max_levels=max_levels,reasons=["fixture"],simulated=True,evidence_version=ev.version,version=1,state=state,direction=RegimeDirection.NEUTRAL,momentum_bps=D("0"),realized_volatility=D("0"),volatility_score=D("0"),book_imbalance=D("0"))


def neutral_execution(ev,spread="1",size="1",state=ExecutionQualityState.NORMAL,max_levels=None):
    metrics=ExecutionQualityMetrics(fill_count=5,reject_count=0,unknown_order_count=0,keep_count=5,create_count=0,replace_count=0,cancel_count=0,reconciliation_churn_ratio=D("0"))
    return ExecutionQualityAgentOutput(agent="EXECUTION_QUALITY",health=AgentHealth.READY,confidence=D("1"),spread_multiplier=D(spread),bid_size_multiplier=D(size),ask_size_multiplier=D(size),max_levels=max_levels,reasons=["fixture"],simulated=True,evidence_version=ev.version,version=1,state=state,metrics=metrics)


def decision(ev,spread="1",bid="1",ask="1",levels=None,enabled=True,version=1,fingerprint=None):
    r=neutral_regime(ev);t=neutral_toxic(ev);x=neutral_execution(ev)
    material={"spread":spread,"bid":bid,"ask":ask,"levels":levels,"enabled":enabled}
    return AgentSupervisorDecision(
        market="ETH",enabled=enabled,regime=r,toxic_flow=t,execution_quality=x,
        spread_multiplier=D(spread),bid_size_multiplier=D(bid),ask_size_multiplier=D(ask),
        max_levels=levels,reasons=["fixture"],market_version=ev.market_version,
        inventory_version=ev.inventory_version,perp_version=ev.perp_version,
        reference_version=ev.reference_version,simulated=True,version=version,
        fingerprint=fingerprint or semantic_fingerprint(material),
    )


def test_agent_config_rejects_invalid_bounds_and_nonfinite():
    with pytest.raises(ValueError):AgentConfig(agent_max_spread_multiplier=D(".9"))
    with pytest.raises(ValueError):AgentConfig(agent_min_size_multiplier=D("0"))
    with pytest.raises(ValueError):AgentConfig(regime_min_samples=50,regime_momentum_window_samples=20)
    with pytest.raises(ValueError):AgentConfig(regime_spread_strength=D("NaN"))


def test_regime_states_direction_and_bounds():
    c=AgentConfig(regime_min_samples=3,regime_momentum_window_samples=5,regime_trend_threshold_bps=D("10"))
    agent=RegimeAgent(c)
    warm=agent.evaluate(evidence(history_sample_count=2,momentum_bps=None))
    assert warm.state==MarketRegime.WARMING_UP and warm.spread_multiplier==1 and warm.bid_size_multiplier==1
    quiet=agent.evaluate(evidence(history_sample_count=5,momentum_bps=D("1"),volatility_score=D("0")))
    assert quiet.state==MarketRegime.QUIET and quiet.direction==RegimeDirection.NEUTRAL
    normal=agent.evaluate(evidence(history_sample_count=5,momentum_bps=D("6"),volatility_score=D(".2")))
    assert normal.state==MarketRegime.NORMAL
    up=agent.evaluate(evidence(history_sample_count=5,momentum_bps=D("25")))
    assert up.state==MarketRegime.TRENDING and up.direction==RegimeDirection.UP
    down=agent.evaluate(evidence(history_sample_count=5,momentum_bps=D("-25")))
    assert down.direction==RegimeDirection.DOWN
    high=agent.evaluate(evidence(history_sample_count=5,momentum_bps=D("0"),market_adaptation_regime="HIGH_VOLATILITY",volatility_score=D(".9")))
    assert high.state==MarketRegime.HIGH_VOLATILITY
    dis=agent.evaluate(evidence(history_sample_count=5,momentum_bps=D("0"),reference_confidence="CONFLICTED"))
    assert dis.state==MarketRegime.DISLOCATED
    for output in (warm,quiet,normal,up,down,high,dis):
        assert D("0")<=output.confidence<=1
        assert output.spread_multiplier>=1
        assert D("0")<output.bid_size_multiplier<=1
        assert output.spread_multiplier.is_finite()


def test_toxic_flow_bid_ask_markout_signs_pending_dedup_and_bounds():
    c=AgentConfig(toxic_flow_min_matured_fills=1,toxic_flow_markout_horizon_seconds=5,toxic_flow_window_fills=2)
    telemetry=AgentTelemetryStore(max_fills=2)
    t0=utcnow()
    bid=Fill(client_order_id="b",market="ETH",side="BID",price=D("3000"),size=D("1"),timestamp=t0)
    ask=Fill(client_order_id="a",market="ETH",side="ASK",price=D("3000"),size=D("1"),timestamp=t0)
    assert telemetry.observe_fill(bid,D("3000"))
    assert not telemetry.observe_fill(bid,D("3000"))
    assert telemetry.observe_fill(ask,D("3000"))
    h=history(["3000","2997"],start=t0,step=5)
    markouts,pending=telemetry.markouts(h,horizon_seconds=5,window=10)
    assert pending==0
    by_side={m.side:m.signed_markout_bps for m in markouts}
    assert by_side["BID"]<0
    assert by_side["ASK"]>0
    out=ToxicFlowAgent(c).evaluate(evidence(),telemetry,h)
    assert out.state in {ToxicFlowState.ELEVATED,ToxicFlowState.TOXIC}
    assert out.bid_size_multiplier<out.ask_size_multiplier<=1
    assert out.spread_multiplier>=1
    pending_store=AgentTelemetryStore()
    pending_store.observe_fill(Fill(client_order_id="p",market="ETH",side="BID",price=D("3000"),size=D("1"),timestamp=t0),D("3000"))
    pending_out=ToxicFlowAgent(c).evaluate(evidence(),pending_store,history(["3000"],start=t0))
    assert pending_out.state==ToxicFlowState.INSUFFICIENT_DATA
    assert pending_out.metrics.pending_markouts==1
    assert pending_out.metrics.mean_signed_markout_bps is None
    assert pending_out.simulated is True


def test_toxic_flow_ask_adverse_sign():
    c=AgentConfig(toxic_flow_min_matured_fills=1,toxic_flow_markout_horizon_seconds=5)
    telemetry=AgentTelemetryStore();t0=utcnow()
    telemetry.observe_fill(Fill(client_order_id="a",market="ETH",side="ASK",price=D("3000"),size=D("1"),timestamp=t0),D("3000"))
    out=ToxicFlowAgent(c).evaluate(evidence(),telemetry,history(["3000","3003"],start=t0,step=5))
    assert out.metrics.mean_signed_markout_bps<0
    assert out.ask_size_multiplier<1


@pytest.mark.parametrize("side,expected",[("BID",D("-10")),("ASK",D("10"))])
def test_matured_markout_is_frozen_and_survives_history_eviction_and_clear(side,expected):
    t0=utcnow()
    telemetry=AgentTelemetryStore()
    fill=Fill(client_order_id="immutable",market="ETH",side=side,price=D("3000"),size=D("1"),timestamp=t0)
    telemetry.observe_fill(fill,D("3000"))
    h=MarketPriceHistory(max_samples=2)
    h.add_snapshot(snapshot("3000",1,t0))
    # First valid observation may be after, rather than exactly at, the target.
    selected_at=t0+timedelta(seconds=6)
    h.add_snapshot(snapshot("2997",2,selected_at))
    first,pending=telemetry.markouts(h,horizon_seconds=5,window=10)
    assert pending==0 and len(first)==1
    markout=first[0]
    assert markout.fill_identity==telemetry.fill_identity(fill)
    assert markout.target_maturity_time==t0+timedelta(seconds=5)
    assert markout.selected_observation_sequence==2
    assert markout.selected_observation_timestamp==selected_at
    assert markout.future_reference_price==D("2997")
    assert markout.signed_markout_bps==expected
    with pytest.raises(ValidationError,match="frozen"):
        markout.future_reference_price=D("3100")
    h.add_snapshot(snapshot("3100",3,t0+timedelta(seconds=7)))
    h.add_snapshot(snapshot("3200",4,t0+timedelta(seconds=8)))
    assert all(obs.sequence!=2 for obs in h.observations(2))
    for _ in range(3):
        again,pending=telemetry.markouts(h,horizon_seconds=5,window=10)
        assert pending==0 and again==first and again[0] is markout
    c=AgentConfig(toxic_flow_min_matured_fills=1,execution_quality_min_fills=1)
    assert ToxicFlowAgent(c).evaluate(evidence(),telemetry,h).metrics.mean_signed_markout_bps==expected
    assert ExecutionQualityAgent(c).evaluate(evidence(),telemetry,h,execution_mode="PAPER").metrics.average_mature_markout_bps==expected
    h.clear()
    assert telemetry.markouts(h,horizon_seconds=5,window=10)==(first,0)


def test_missed_evicted_maturity_is_terminal_unavailable_instead_of_newer_substitution():
    t0=utcnow()
    telemetry=AgentTelemetryStore()
    telemetry.observe_fill(Fill(client_order_id="missed",market="ETH",side="BID",price=D("3000"),size=D("1"),timestamp=t0),D("3000"))
    h=MarketPriceHistory(max_samples=2)
    h.add_snapshot(snapshot("3000",1,t0))
    assert telemetry.markouts(h,horizon_seconds=5,window=10)==([],1)
    # The first eligible sample arrives and is evicted before telemetry evaluates.
    for seq,seconds,price in [(2,5,"2997"),(3,6,"3100"),(4,7,"3200")]:
        h.add_snapshot(snapshot(price,seq,t0+timedelta(seconds=seconds)))
    for _ in range(3):
        assert telemetry.markouts(h,horizon_seconds=5,window=10)==([],0)
        assert telemetry.summary()["unavailable_markouts"]==1
    h.clear()
    h.add_snapshot(snapshot("3300",5,t0+timedelta(seconds=8)))
    assert telemetry.markouts(h,horizon_seconds=5,window=10)==([],0)
    assert telemetry.summary()["unavailable_markouts"]==1


def test_eviction_before_target_does_not_prevent_maturity_and_cache_is_horizon_scoped():
    t0=utcnow()
    telemetry=AgentTelemetryStore(max_fills=1)
    telemetry.observe_fill(Fill(client_order_id="bounded",market="ETH",side="BID",price=D("3000"),size=D("1"),timestamp=t0),D("3000"))
    h=MarketPriceHistory(max_samples=2)
    for seq,seconds,price in [(1,0,"3000"),(2,1,"3000"),(3,5,"2997")]:
        h.add_snapshot(snapshot(price,seq,t0+timedelta(seconds=seconds)))
    first,_=telemetry.markouts(h,horizon_seconds=5,window=1)
    assert first[0].selected_observation_sequence==3
    assert telemetry.markouts(h,horizon_seconds=10,window=1)==([],1)
    h.add_snapshot(snapshot("3010",4,t0+timedelta(seconds=10)))
    later,_=telemetry.markouts(h,horizon_seconds=10,window=1)
    assert later[0].selected_observation_sequence==4
    assert telemetry.markouts(h,horizon_seconds=5,window=1)==(first,0)
    telemetry.observe_fill(Fill(client_order_id="replacement",market="ETH",side="BID",price=D("3000"),size=D("1"),timestamp=t0+timedelta(seconds=11)),D("3000"))
    assert not telemetry._markouts


def test_clear_before_maturity_selection_marks_discarded_evidence_unavailable():
    t0=utcnow()
    telemetry=AgentTelemetryStore()
    telemetry.observe_fill(Fill(client_order_id="cleared",market="ETH",side="BID",price=D("3000"),size=D("1"),timestamp=t0),D("3000"))
    h=history(["3000","2997"],start=t0,step=5)
    h.clear()
    assert telemetry.markouts(h,horizon_seconds=5,window=10)==([],0)
    assert telemetry.summary()["unavailable_markouts"]==1


def test_small_consumer_window_preserves_maturity_for_other_retained_fills():
    t0=utcnow()
    telemetry=AgentTelemetryStore()
    for identity in ("older","newer"):
        telemetry.observe_fill(Fill(client_order_id=identity,market="ETH",side="BID",price=D("3000"),size=D("1"),timestamp=t0),D("3000"))
    h=MarketPriceHistory(max_samples=2)
    h.add_snapshot(snapshot("3000",1,t0))
    h.add_snapshot(snapshot("2997",2,t0+timedelta(seconds=5)))
    small,pending=telemetry.markouts(h,horizon_seconds=5,window=1)
    assert len(small)==1 and pending==0
    h.add_snapshot(snapshot("3100",3,t0+timedelta(seconds=6)))
    h.add_snapshot(snapshot("3200",4,t0+timedelta(seconds=7)))
    expanded,pending=telemetry.markouts(h,horizon_seconds=5,window=2)
    assert len(expanded)==2 and pending==0
    assert all(m.selected_observation_sequence==2 and m.signed_markout_bps==D("-10") for m in expanded)


def test_spread_capture_signs_and_churn():
    assert spread_capture_bps("BID",D("2997"),D("3000"))==D("10")
    assert spread_capture_bps("ASK",D("3003"),D("3000"))==D("10")
    assert churn_ratio(5,1,2,2)==D("0.8")


def test_execution_quality_no_data_and_testnet_do_not_fabricate():
    c=AgentConfig(execution_quality_min_fills=1)
    agent=ExecutionQualityAgent(c)
    telemetry=AgentTelemetryStore()
    out=agent.evaluate(evidence(),telemetry,history(["3000","3000"]),execution_mode="PAPER")
    assert out.state==ExecutionQualityState.INSUFFICIENT_DATA
    assert out.metrics.average_spread_capture_bps is None
    testnet=agent.evaluate(evidence(simulated=False),telemetry,history(["3000","3000"]),execution_mode="TESTNET")
    assert testnet.health==AgentHealth.INSUFFICIENT_DATA
    assert testnet.metrics.average_spread_capture_bps is None
    assert testnet.metrics.average_mature_markout_bps is None


def test_supervisor_conservative_aggregation_and_stable_material_version(monkeypatch):
    ev=evidence();s=AgentSupervisor(AgentConfig())
    monkeypatch.setattr(s.regime,"evaluate",lambda _ev:neutral_regime(ev,spread="1.2",size=".9",max_levels=6))
    monkeypatch.setattr(s.toxic_flow,"evaluate",lambda *_:neutral_toxic(ev,spread="1.5",bid=".6",ask=".8",max_levels=4))
    monkeypatch.setattr(s.execution_quality,"evaluate",lambda *_:neutral_execution(ev,spread="1.3",size=".7",max_levels=5))
    telemetry=AgentTelemetryStore();h=history(["3000","3000"])
    first=s.evaluate(evidence=ev,telemetry=telemetry,history=h,execution_mode="PAPER")
    second=s.evaluate(evidence=ev.model_copy(update={"version":999,"reference_version":9}),telemetry=telemetry,history=h,execution_mode="PAPER")
    assert first.spread_multiplier==D("1.5")
    assert first.bid_size_multiplier==D(".6")
    assert first.ask_size_multiplier==D(".7")
    assert first.max_levels==4
    assert second.version==first.version
    assert second.fingerprint==first.fingerprint


def test_disabled_quote_transform_is_exact_and_enabled_is_conservative():
    ev=evidence()
    quotes=[quote("BID","2990","1",0),quote("ASK","3010","1",0),quote("BID","2980","1",1)]
    disabled=transform_quotes(quotes,decision(ev,enabled=False),center=D("3000"),tick_size=D(".1"),size_precision=4)
    assert disabled==quotes
    assert all(a is b for a,b in zip(disabled,quotes))
    adapted=transform_quotes(quotes,decision(ev,spread="1.5",bid=".7",ask=".8",levels=1),center=D("3000"),tick_size=D(".1"),size_precision=4)
    assert len(adapted)==2
    bid=next(q for q in adapted if q.side=="BID");ask=next(q for q in adapted if q.side=="ASK")
    assert bid.price<=D("2990") and ask.price>=D("3010")
    assert bid.size<=D("1") and ask.size<=D("1")
    assert not any(q.level_index==1 for q in adapted)
    assert bid.price<ask.price


def test_transform_never_restores_missing_side():
    ev=evidence()
    only_asks=[quote("ASK","3010","1",0)]
    out=transform_quotes(only_asks,decision(ev,spread="1.5",bid=".5",ask=".5"),center=D("3000"),tick_size=D(".1"),size_precision=4)
    assert out and all(q.side=="ASK" for q in out)


def test_agent_events_are_bounded():
    s=AgentSupervisor(AgentConfig())
    for i in range(400):
        s.events.append(__import__("app.agents.models",fromlist=["AgentEvent"]).AgentEvent(agent="X",new_state=str(i),version=i))
    assert len(s.events)==250


def test_phase5_long_and_short_suppression_survive_agent_transform():
    ev=evidence()
    cautious=decision(ev,spread="1.4",bid=".6",ask=".6")
    long_ladder=[quote("ASK","3010","1",0),quote("ASK","3020","1",1)]
    short_ladder=[quote("BID","2990","1",0),quote("BID","2980","1",1)]
    long_out=transform_quotes(long_ladder,cautious,center=D("3000"),tick_size=D(".1"),size_precision=4)
    short_out=transform_quotes(short_ladder,cautious,center=D("3000"),tick_size=D(".1"),size_precision=4)
    assert long_out and all(q.side=="ASK" for q in long_out)
    assert short_out and all(q.side=="BID" for q in short_out)


def test_phase6_widened_quote_is_preserved_or_widened_never_tightened():
    ev=evidence()
    phase6=[quote("BID","2985","1",0),quote("ASK","3015","1",0)]
    neutral=transform_quotes(phase6,decision(ev),center=D("3000"),tick_size=D(".1"),size_precision=4)
    assert [(q.price,q.size) for q in neutral]==[(q.price,q.size) for q in phase6]
    wider=transform_quotes(phase6,decision(ev,spread="1.5"),center=D("3000"),tick_size=D(".1"),size_precision=4)
    assert next(q for q in wider if q.side=="BID").price<=D("2985")
    assert next(q for q in wider if q.side=="ASK").price>=D("3015")


def test_phase8_transform_remains_more_conservative_than_agent_candidate():
    ev=evidence()
    base=[quote("BID","2990","1",0),quote("ASK","3010","1",0)]
    agent=transform_quotes(base,decision(ev,spread="1.5",bid=".7",ask=".7"),center=D("3000"),tick_size=D(".1"),size_precision=4)
    exposure=ExposureMetrics(
        current_position=D("0"),current_position_notional=D("0"),
        bid_quote_notional=D("0"),ask_quote_notional=D("0"),gross_quote_notional=D("0"),
        bid_quantity=D("0"),ask_quantity=D("0"),projected_long_base=D("0"),projected_short_base=D("0"),
        projected_long_notional=D("0"),projected_short_notional=D("0"),inventory_utilization=D("0"),
    )
    risk=RiskDecision(
        state=RiskState.REDUCE,allow_quotes=True,spread_multiplier=D("1.8"),size_multiplier=D(".5"),
        max_levels=None,reasons=["fixture"],reference_version=1,market_version=1,inventory_version=1,perp_version=1,
        projected_long_base=D("0"),projected_short_base=D("0"),exposure=exposure,
        liquidation=LiquidationEvidence(status="FLAT",position_base=D("0"),mark_price=D("3000")),
        pnl_drawdown=PnlDrawdown(source="TEST"),version=1,
    )
    firewall=RiskFirewall(RiskFirewallConfig(max_projected_long_base=D("20"),max_projected_short_base=D("20")))
    final=firewall.transform(agent,risk,center=D("3000"),tick_size=D(".1"),size_precision=4,base_order_size=D(".1"))
    agent_bid=next(q for q in agent if q.side=="BID");final_bid=next(q for q in final if q.side=="BID")
    agent_ask=next(q for q in agent if q.side=="ASK");final_ask=next(q for q in final if q.side=="ASK")
    assert final_bid.price<=agent_bid.price and final_ask.price>=agent_ask.price
    assert final_bid.size<=agent_bid.size and final_ask.size<=agent_ask.size


def test_agent_exception_becomes_error_neutral_recommendation(monkeypatch):
    ev=evidence()
    supervisor=AgentSupervisor(AgentConfig())
    monkeypatch.setattr(supervisor.regime,"evaluate",lambda _ev:(_ for _ in ()).throw(RuntimeError("boom")))
    out=supervisor.evaluate(evidence=ev,telemetry=AgentTelemetryStore(),history=history(["3000","3000"]),execution_mode="PAPER")
    assert out.regime.health==AgentHealth.ERROR
    assert out.regime.spread_multiplier==1
    assert out.regime.bid_size_multiplier==1
    assert out.regime.ask_size_multiplier==1


def test_nonfinite_agent_recommendation_is_rejected():
    ev=evidence()
    with pytest.raises(ValidationError):
        RegimeAgentOutput(
            agent="REGIME",health=AgentHealth.READY,confidence=D("1"),spread_multiplier=D("NaN"),
            bid_size_multiplier=D("1"),ask_size_multiplier=D("1"),reasons=[],simulated=True,
            evidence_version=ev.version,version=1,state=MarketRegime.NORMAL,direction=RegimeDirection.NEUTRAL,
            momentum_bps=D("0"),realized_volatility=D("0"),volatility_score=D("0"),book_imbalance=D("0"),
        )


def test_bounded_fill_history_evicts_oldest_deterministically():
    telemetry=AgentTelemetryStore(max_fills=2)
    t0=utcnow()
    for i in range(3):
        telemetry.observe_fill(Fill(client_order_id=str(i),market="ETH",side="BID",price=D("3000"),size=D("1"),timestamp=t0+timedelta(seconds=i)),D("3000"))
    fills=telemetry.fills(10)
    assert len(fills)==2
    assert [fill.client_order_id for fill in fills]==["1","2"]


def test_execution_quality_unknown_reject_and_churn_degrade_quality():
    c=AgentConfig(execution_quality_min_fills=1,execution_quality_max_churn_ratio=D(".4"))
    telemetry=AgentTelemetryStore()
    t0=utcnow()
    telemetry.observe_fill(Fill(client_order_id="f",market="ETH",side="BID",price=D("2999"),size=D("1"),timestamp=t0),D("3000"))
    from app.execution.models import StrategyOrder,OrderStatus
    telemetry.observe_orders([
        StrategyOrder(client_order_id="u",market="ETH",side="BID",price=D("2990"),size=D("1"),status=OrderStatus.UNKNOWN),
        StrategyOrder(client_order_id="r",market="ETH",side="ASK",price=D("3010"),size=D("1"),status=OrderStatus.REJECTED),
    ])
    from app.execution.quote_reconciler import ReconcileAction,ReconcileActionType
    telemetry.observe_reconcile([
        ReconcileAction(action=ReconcileActionType.REPLACE,desired=quote("BID","2990"),existing=StrategyOrder(client_order_id="old",market="ETH",side="BID",price=D("2980"),size=D("1"))),
        ReconcileAction(action=ReconcileActionType.CANCEL,existing=StrategyOrder(client_order_id="cancel",market="ETH",side="ASK",price=D("3020"),size=D("1"))),
    ],[])
    out=ExecutionQualityAgent(c).evaluate(evidence(),telemetry,history(["3000","3000"],start=t0,step=5),execution_mode="PAPER")
    assert out.state==ExecutionQualityState.POOR
    assert out.metrics.unknown_order_count>=1
    assert out.metrics.reject_count>=1
    assert out.metrics.reconciliation_churn_ratio>D(".4")
    assert out.spread_multiplier>=1
    assert out.bid_size_multiplier<=1


def test_execution_quality_healthy_evidence_can_be_good():
    c=AgentConfig(execution_quality_min_fills=1,execution_quality_max_churn_ratio=D(".8"),toxic_flow_markout_horizon_seconds=5)
    telemetry=AgentTelemetryStore();t0=utcnow()
    telemetry.observe_fill(Fill(client_order_id="g",market="ETH",side="BID",price=D("2999"),size=D("1"),timestamp=t0),D("3000"))
    out=ExecutionQualityAgent(c).evaluate(evidence(),telemetry,history(["3000","3001"],start=t0,step=5),execution_mode="PAPER")
    assert out.state==ExecutionQualityState.GOOD
    assert out.metrics.average_spread_capture_bps is not None
    assert out.metrics.average_mature_markout_bps is not None


def test_missing_fill_reference_remains_unavailable_not_fabricated():
    c=AgentConfig(execution_quality_min_fills=1)
    telemetry=AgentTelemetryStore();t0=utcnow()
    telemetry.observe_fill(Fill(client_order_id="noref",market="ETH",side="BID",price=D("3000"),size=D("1"),timestamp=t0),None)
    out=ExecutionQualityAgent(c).evaluate(evidence(),telemetry,history(["3000","3001"],start=t0,step=5),execution_mode="PAPER")
    assert out.metrics.average_spread_capture_bps is None


@pytest.mark.parametrize("status",["pending","unavailable","adverse","favorable"])
def test_quality_requires_mature_markout_and_explains_provisional(status):
    t0=utcnow();telemetry=AgentTelemetryStore()
    telemetry.observe_fill(Fill(client_order_id="quality",market="ETH",side="BID",price=D("2999"),size=D("1"),timestamp=t0),D("3000"))
    h=MarketPriceHistory(max_samples=2)
    h.add_snapshot(snapshot("3000",1,t0))
    if status!="pending":
        h.add_snapshot(snapshot("2990" if status=="adverse" else "3001",2,t0+timedelta(seconds=5)))
    if status=="unavailable":
        h.add_snapshot(snapshot("3010",3,t0+timedelta(seconds=6)))
        h.add_snapshot(snapshot("3020",4,t0+timedelta(seconds=7)))
    out=ExecutionQualityAgent(AgentConfig(execution_quality_min_fills=1,toxic_flow_markout_horizon_seconds=5)).evaluate(evidence(),telemetry,h,"PAPER")
    assert out.metrics.average_spread_capture_bps>0
    if status in {"pending","unavailable"}:
        assert out.state==ExecutionQualityState.NORMAL
        assert out.metrics.average_mature_markout_bps is None
        assert "provisional: mature markout unavailable" in out.reasons
    else:
        assert out.state==(ExecutionQualityState.POOR if status=="adverse" else ExecutionQualityState.GOOD)
        assert any("mature markout" in reason for reason in out.reasons)


def test_keep_cadence_cannot_dilute_or_evict_action_churn():
    from types import SimpleNamespace
    from app.execution.quote_reconciler import ReconcileActionType as A
    telemetry=AgentTelemetryStore(max_reconcile_cycles=2)
    agent=ExecutionQualityAgent(AgentConfig(execution_quality_window=2,execution_quality_min_fills=1))
    telemetry.observe_reconcile([SimpleNamespace(action=A.CREATE),SimpleNamespace(action=A.REPLACE)],[])
    initial=agent.evaluate(evidence(),telemetry,MarketPriceHistory(),"PAPER").metrics
    assert initial.reconciliation_churn_ratio==D(".5")
    for _ in range(10):
        telemetry.observe_reconcile([SimpleNamespace(action=A.KEEP)],[])
        metrics=agent.evaluate(evidence(),telemetry,MarketPriceHistory(),"PAPER").metrics
        assert metrics.reconciliation_churn_ratio==initial.reconciliation_churn_ratio
        assert (metrics.create_count,metrics.replace_count)==(1,1)
        assert metrics.keep_count>0
    assert churn_ratio(0,1,1,0)==churn_ratio(1000,1,1,0)
    assert churn_ratio(1000,0,0,0)==0


@pytest.mark.parametrize("failed_agent",["regime","toxic_flow","execution_quality"])
def test_soft_error_discards_prior_advice_and_preserves_upstream_bounds(monkeypatch,failed_agent):
    ev=evidence();s=AgentSupervisor(AgentConfig())
    outputs={"regime":neutral_regime(ev,spread="1.7",size=".5"),
             "toxic_flow":neutral_toxic(ev,spread="1.7",bid=".5",ask=".5"),
             "execution_quality":neutral_execution(ev,spread="1.7",size=".5")}
    neutral={"regime":neutral_regime(ev),"toxic_flow":neutral_toxic(ev),"execution_quality":neutral_execution(ev)}
    calls=[]
    for name in outputs:
        def evaluate(*args,name=name):
            calls.append(name)
            return outputs[name] if name==failed_agent else neutral[name]
        monkeypatch.setattr(getattr(s,name),"evaluate",evaluate)
    kwargs=dict(evidence=ev,telemetry=AgentTelemetryStore(),history=MarketPriceHistory(),execution_mode="PAPER")
    previous=s.evaluate(**kwargs)
    assert previous.spread_multiplier==D("1.7")
    def fail(*args):
        calls.append(failed_agent)
        raise RuntimeError("deliberate failure")
    monkeypatch.setattr(getattr(s,failed_agent),"evaluate",fail)
    calls.clear();current=s.evaluate(**kwargs)
    assert set(calls)==set(outputs)
    error=getattr(current,failed_agent)
    assert error.health==AgentHealth.ERROR
    assert (error.confidence,error.spread_multiplier,error.bid_size_multiplier,error.ask_size_multiplier)==(0,1,1,1)
    assert error.max_levels is None and "deliberate failure" in error.reasons[0]
    assert current.spread_multiplier==1 and current.bid_size_multiplier==1
    assert current.version>previous.version and current.fingerprint!=previous.fingerprint
    base=[quote("BID","2990"),quote("ASK","3010")]
    adapted=transform_quotes(base,current,center=D("3000"),tick_size=D(".1"),size_precision=4)
    for before,after in zip(base,adapted):
        assert after.size<=before.size
        assert after.price<=before.price if before.side=="BID" else after.price>=before.price
    assert len(adapted)==len(base)
