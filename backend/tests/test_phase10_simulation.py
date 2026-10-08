from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

import app.simulation.engine as engine_module
from app.agents import AgentSupervisor,AgentTelemetryStore,build_agent_evidence,transform_quotes
from app.agents.config import AgentConfig
from app.execution.models import Fill,OrderRequest
from app.execution.paper import PaperExecutionAdapter
from app.market_data.history import MarketPriceHistory
from app.market_data.models import MarketConnectionState,MarketDataMode,MarketLevel,MarketSnapshot,OrderBookSnapshot
from app.risk.firewall import PnlDrawdown,RiskFirewall,RiskFirewallConfig,RiskState,paper_pnl
from app.strategy.inventory import build_inventory_state
from app.strategy.models import StrategyConfig
from app.strategy.quote_engine import QuoteEngine
from app.simulation.config import SimulationConfig
from app.simulation.engine import SimulationClock,SimulationEngine
from app.simulation.metrics import MetricsAccumulator
from app.simulation.models import SimulationDataset,SimulationReferencePrices
from app.simulation.references import build_simulated_references
from app.simulation.scenarios import generate_scenario


@pytest.mark.parametrize("select_before_eviction",[True,False])
def test_final_simulation_markout_preserves_selected_or_unavailable_evidence(select_before_eviction):
    from test_phase9_agents import snapshot

    t0=generate_scenario("QUIET",frames=2).frames[0].timestamp
    fill=Fill(client_order_id="maturity",market="ETH",side="BID",price=D("3000"),size=D("1"),timestamp=t0)
    telemetry=AgentTelemetryStore()
    telemetry.observe_fill(fill,D("3000"))
    history=MarketPriceHistory(max_samples=2)
    history.add_snapshot(snapshot("3000",1,t0))
    history.add_snapshot(snapshot("2997",2,t0+timedelta(seconds=5)))
    agents=AgentConfig(toxic_flow_markout_horizon_seconds=5)
    acc=MetricsAccumulator(D("1000"))
    kwargs=dict(
        paper=SimpleNamespace(fills=SimpleNamespace(all=lambda:[fill])),market="ETH",
        vault=SimpleNamespace(net_pnl_quote=D("0"),equity_quote=D("1000"),realized_pnl_quote=D("0"),unrealized_pnl_quote=D("0"),position_base=D("0")),
        telemetry=telemetry,history=history,agent_config=agents,frame_count=4,
    )
    if select_before_eviction:
        assert acc.finalize(**kwargs).mean_mature_markout_bps==D("-10")
    history.add_snapshot(snapshot("3100",3,t0+timedelta(seconds=6)))
    history.add_snapshot(snapshot("3200",4,t0+timedelta(seconds=7)))
    expected=D("-10") if select_before_eviction else None
    for _ in range(3):
        metrics=acc.finalize(**kwargs)
        assert metrics.mean_mature_markout_bps==expected
        assert metrics.adverse_fill_rate==(D("1") if select_before_eviction else None)


@pytest.mark.asyncio
async def test_code_owned_engine_version_is_visible_and_fingerprint_bound(monkeypatch):
    from app.simulation import version
    kwargs=dict(dataset=generate_scenario("QUIET",frames=3),strategy_config=StrategyConfig(),
                agent_config=AgentConfig(),risk_config=RiskFirewallConfig(),
                simulation_config=SimulationConfig(max_frames=3))
    first=await SimulationEngine().run(**kwargs)
    assert first.engine_version==version.SIMULATION_ENGINE_VERSION=="phase10.1-v3"
    monkeypatch.setattr(version,"SIMULATION_ENGINE_VERSION","test-implementation-v2")
    second=await SimulationEngine().run(**kwargs)
    assert second.engine_version=="test-implementation-v2"
    assert first.run_fingerprint!=second.run_fingerprint
    assert first.metrics==second.metrics


def crossed_snapshot(frame,*,bid=None,ask=None):
    mid=frame.market.mid_price
    best_bid=D(str(bid)) if bid is not None else mid-D("1")
    best_ask=D(str(ask)) if ask is not None else mid+D("1")
    return MarketSnapshot(
        market="ETH",best_bid=best_bid,best_ask=best_ask,mid_price=(best_bid+best_ask)/D("2"),
        book=OrderBookSnapshot(
            market="ETH",bids=[MarketLevel(price=best_bid,size=D("1"))],
            asks=[MarketLevel(price=best_ask,size=D("1"))],
            timestamp=frame.timestamp,sequence=frame.sequence,
        ),
        latest_valid_update=frame.timestamp,connection_state=MarketConnectionState.CONNECTED,
        mode=MarketDataMode.DEMO,simulated=True,stale=False,
    )


@pytest.mark.asyncio
async def test_paper_crossing_clock_bid_and_ask_semantics():
    dataset=generate_scenario("QUIET",frames=3)
    clock=SimulationClock(dataset.frames[0].timestamp)
    paper=PaperExecutionAdapter(clock=clock)
    paper.update_market(crossed_snapshot(dataset.frames[0],bid="99",ask="101"))
    bid=OrderRequest(client_order_id="bid",market="ETH",side="BID",price=D("100"),size=D("1"),level_index=0)
    ask=OrderRequest(client_order_id="ask",market="ETH",side="ASK",price=D("102"),size=D("1"),level_index=0)
    created=await paper.submit_orders([bid,ask])
    assert all(o.created_at==dataset.frames[0].timestamp for o in created)
    assert paper.fills.all()==[]

    clock.set(dataset.frames[1].timestamp)
    paper.update_market(crossed_snapshot(dataset.frames[1],bid="99",ask="100"))
    assert [f.client_order_id for f in paper.fills.all()]==["bid"]
    assert paper.fills.all()[0].price==D("100")
    assert paper.fills.all()[0].timestamp==dataset.frames[1].timestamp

    clock.set(dataset.frames[2].timestamp)
    paper.update_market(crossed_snapshot(dataset.frames[2],bid="102",ask="103"))
    assert [f.client_order_id for f in paper.fills.all()]==["bid","ask"]
    assert paper.fills.all()[1].price==D("102")
    assert paper.fills.all()[1].timestamp==dataset.frames[2].timestamp
    paper.update_market(crossed_snapshot(dataset.frames[2],bid="102",ask="103"))
    assert len(paper.fills.all())==2


@pytest.mark.asyncio
async def test_same_simulation_twice_is_reproducible():
    dataset=generate_scenario("FLASH_MOVE",frames=30)
    kwargs=dict(
        dataset=dataset,strategy_config=StrategyConfig(),agent_config=AgentConfig(),
        risk_config=RiskFirewallConfig(),simulation_config=SimulationConfig(max_frames=30,trace_max_points=30),
        scenario="FLASH_MOVE",
    )
    a=await SimulationEngine().run(**kwargs)
    b=await SimulationEngine().run(**kwargs)
    assert a.run_fingerprint==b.run_fingerprint
    assert a.metrics==b.metrics
    assert a.orders==b.orders
    assert a.fills==b.fills
    assert [x.timestamp for x in a.trace]==[x.timestamp for x in b.trace]


@pytest.mark.asyncio
async def test_simulation_reuses_real_quote_agent_and_risk_components(monkeypatch):
    calls={"quote":0,"agent":0,"risk":0}
    quote_original=engine_module.QuoteEngine.generate_perp_market_adaptive
    agent_original=engine_module.AgentSupervisor.evaluate
    risk_original=engine_module.RiskFirewall.evaluate

    def quote_wrapped(self,*args,**kwargs):
        calls["quote"]+=1
        return quote_original(self,*args,**kwargs)

    def agent_wrapped(self,*args,**kwargs):
        calls["agent"]+=1
        return agent_original(self,*args,**kwargs)

    def risk_wrapped(self,*args,**kwargs):
        calls["risk"]+=1
        return risk_original(self,*args,**kwargs)

    monkeypatch.setattr(engine_module.QuoteEngine,"generate_perp_market_adaptive",quote_wrapped)
    monkeypatch.setattr(engine_module.AgentSupervisor,"evaluate",agent_wrapped)
    monkeypatch.setattr(engine_module.RiskFirewall,"evaluate",risk_wrapped)

    dataset=generate_scenario("QUIET",frames=6)
    await SimulationEngine().run(
        dataset=dataset,strategy_config=StrategyConfig(),agent_config=AgentConfig(),
        risk_config=RiskFirewallConfig(),simulation_config=SimulationConfig(max_frames=6),
    )
    assert calls=={"quote":6,"agent":6,"risk":6}


@pytest.mark.asyncio
async def test_phase8_evaluates_post_agent_quotes(monkeypatch):
    captured=[]
    original=engine_module.RiskFirewall.evaluate

    def wrapped(self,*args,**kwargs):
        captured.append([(q.side,q.price,q.size,q.pre_agent_size) for q in kwargs["quotes"]])
        return original(self,*args,**kwargs)

    monkeypatch.setattr(engine_module.RiskFirewall,"evaluate",wrapped)
    agents=AgentConfig(
        regime_min_samples=2,regime_momentum_window_samples=3,regime_spread_strength=D(".8"),
        regime_size_strength=D(".8"),regime_trend_threshold_bps=D("1"),
    )
    dataset=generate_scenario("TREND_UP",frames=8)
    await SimulationEngine().run(
        dataset=dataset,strategy_config=StrategyConfig(),agent_config=agents,
        risk_config=RiskFirewallConfig(),simulation_config=SimulationConfig(max_frames=8),
    )
    assert captured
    assert any(any(pre is not None and size<=pre for _,_,size,pre in ladder) for ladder in captured)


@pytest.mark.asyncio
async def test_insufficient_reference_quorum_halts_and_creates_no_orders():
    base=generate_scenario("QUIET",frames=8)
    frames=[
        frame.model_copy(update={"reference_prices":SimulationReferencePrices(redstone=None,kraken=None,coingecko=None)})
        for frame in base.frames
    ]
    dataset=SimulationDataset(market="ETH",frames=frames,source="insufficient")
    result=await SimulationEngine().run(
        dataset=dataset,strategy_config=StrategyConfig(),agent_config=AgentConfig(),
        risk_config=RiskFirewallConfig(),simulation_config=SimulationConfig(max_frames=8),
    )
    assert result.metrics.risk_state_counts.get("HALT")==8
    assert result.orders==[]
    assert result.fills==[]


@pytest.mark.asyncio
async def test_no_future_leakage_in_early_trace():
    a=generate_scenario("QUIET",frames=12)
    volatile=generate_scenario("HIGH_VOLATILITY",frames=12)
    changed=a.frames[:6]+volatile.frames[6:]
    b=SimulationDataset(market="ETH",frames=changed,source="future-changed")
    kwargs=dict(
        strategy_config=StrategyConfig(),agent_config=AgentConfig(),risk_config=RiskFirewallConfig(),
        simulation_config=SimulationConfig(max_frames=12,trace_max_points=12),
    )
    ra=await SimulationEngine().run(dataset=a,**kwargs)
    rb=await SimulationEngine().run(dataset=b,**kwargs)
    assert [x.model_dump() for x in ra.trace[:6]]==[x.model_dump() for x in rb.trace[:6]]


def test_exact_pnl_equity_and_drawdown_math():
    fills=[
        Fill(client_order_id="a",market="ETH",side="BID",price=D("100"),size=D("1")),
        Fill(client_order_id="b",market="ETH",side="ASK",price=D("110"),size=D("1")),
    ]
    pnl=paper_pnl(fills,"ETH",D("110"))
    assert pnl.realized_pnl==D("10")
    assert pnl.unrealized_pnl==D("0")

    acc=MetricsAccumulator(D("1000"))
    risk=SimpleNamespace(
        state=SimpleNamespace(value="NORMAL"),
        exposure=SimpleNamespace(inventory_utilization=D("0")),
    )
    agent=SimpleNamespace(
        regime=SimpleNamespace(state=SimpleNamespace(value="NORMAL")),
        toxic_flow=SimpleNamespace(state=SimpleNamespace(value="NORMAL")),
        execution_quality=SimpleNamespace(state=SimpleNamespace(value="NORMAL")),
        liquidity_quality=SimpleNamespace(state=SimpleNamespace(value="HEALTHY")),
        perp_crowding=SimpleNamespace(state=SimpleNamespace(value="NEUTRAL")),
    )
    inventory=SimpleNamespace(position_base=D("0"),inventory_ratio=D("0"))
    acc.record(authorized_quotes=[],inventory=inventory,risk_decision=risk,agent_decision=agent,equity=D("1100"),drawdown_pct=D("0"),actions=[])
    acc.record(authorized_quotes=[],inventory=inventory,risk_decision=risk,agent_decision=agent,equity=D("990"),drawdown_pct=D(".1"),actions=[])
    assert acc.peak_equity==D("1100")
    assert acc.max_drawdown_pct==D(".1")


def _pipeline_candidate_with_position(position:D):
    dataset=generate_scenario("QUIET",frames=2)
    frame=dataset.frames[0]
    config=StrategyConfig(soft_inventory_limit_base=D(".5"),hard_inventory_limit_base=D("1"))
    history=MarketPriceHistory()
    history.add_snapshot(frame.market)
    inventory=build_inventory_state(
        market="ETH",position=position,target=D("0"),soft_limit=config.soft_inventory_limit_base,
        source="PAPER",updated_at=frame.timestamp,version=0,
    )
    _,_,proposed,inventory_decision,market_decision,_=QuoteEngine().generate_perp_market_adaptive(
        config,frame.market,inventory,history,frame.perp_context
    )
    refs=build_simulated_references(frame,agreement_bps=D("30"),outlier_bps=D("75"),version=1)
    agents=AgentConfig()
    evidence=build_agent_evidence(
        market_decision=market_decision,inventory=inventory,perp_context=frame.perp_context,
        refs=refs,history=history,momentum_window=agents.regime_momentum_window_samples,
    )
    decision=AgentSupervisor(agents).evaluate(
        evidence=evidence,telemetry=AgentTelemetryStore(),history=history,execution_mode="PAPER"
    )
    agent_quotes=transform_quotes(
        proposed,decision,center=inventory_decision.reservation_price,
        tick_size=config.tick_size,size_precision=config.size_precision,
    )
    firewall=RiskFirewall(RiskFirewallConfig())
    risk=firewall.evaluate(
        refs=refs,quotes=agent_quotes,current_position=position,mark=frame.perp_context.mark_price,
        liquidation=None,pnl=PnlDrawdown(session_pnl=D("0"),source="TEST",simulated=True),
        market_version=market_decision.version,inventory_version=inventory.version,
        perp_version=frame.perp_context.version,
    )
    final=firewall.transform(
        agent_quotes,risk,center=inventory_decision.reservation_price,
        tick_size=config.tick_size,size_precision=config.size_precision,base_order_size=config.base_order_size,
    )
    return proposed,agent_quotes,final,risk


def test_phase5_suppressed_sides_remain_absent_through_agents_and_phase8():
    long_base,long_agent,long_final,_=_pipeline_candidate_with_position(D("1"))
    short_base,short_agent,short_final,_=_pipeline_candidate_with_position(D("-1"))
    assert long_base and all(q.side=="ASK" for q in long_base)
    assert long_agent and all(q.side=="ASK" for q in long_agent)
    assert long_final and all(q.side=="ASK" for q in long_final)
    assert short_base and all(q.side=="BID" for q in short_base)
    assert short_agent and all(q.side=="BID" for q in short_agent)
    assert short_final and all(q.side=="BID" for q in short_final)


def test_agent_widening_survives_phase8_normal_and_phase8_reduce_remains_more_conservative():
    dataset=generate_scenario("TREND_UP",frames=10)
    frame=dataset.frames[-1]
    config=StrategyConfig(volatility_min_samples=2,volatility_window_samples=10)
    history=MarketPriceHistory()
    for item in dataset.frames:
        history.add_snapshot(item.market)
    inventory=build_inventory_state(
        market="ETH",position=D("0"),target=D("0"),soft_limit=config.soft_inventory_limit_base,
        source="PAPER",updated_at=frame.timestamp,version=0,
    )
    _,_,proposed,inventory_decision,market_decision,_=QuoteEngine().generate_perp_market_adaptive(
        config,frame.market,inventory,history,frame.perp_context
    )
    refs=build_simulated_references(frame,agreement_bps=D("30"),outlier_bps=D("75"),version=frame.sequence)
    agent_cfg=AgentConfig(regime_min_samples=2,regime_momentum_window_samples=10,regime_trend_threshold_bps=D("1"),regime_spread_strength=D(".5"))
    evidence=build_agent_evidence(
        market_decision=market_decision,inventory=inventory,perp_context=frame.perp_context,
        refs=refs,history=history,momentum_window=agent_cfg.regime_momentum_window_samples,
    )
    agent_decision=AgentSupervisor(agent_cfg).evaluate(
        evidence=evidence,telemetry=AgentTelemetryStore(),history=history,execution_mode="PAPER"
    )
    agent_quotes=transform_quotes(
        proposed,agent_decision,center=inventory_decision.reservation_price,
        tick_size=config.tick_size,size_precision=config.size_precision,
    )
    assert any(q.pre_agent_price is not None and (
        (q.side=="BID" and q.price<=q.pre_agent_price) or (q.side=="ASK" and q.price>=q.pre_agent_price)
    ) for q in agent_quotes)

    normal_fw=RiskFirewall(RiskFirewallConfig())
    normal=normal_fw.evaluate(
        refs=refs,quotes=agent_quotes,current_position=D("0"),mark=frame.perp_context.mark_price,
        liquidation=None,pnl=PnlDrawdown(session_pnl=D("0"),source="TEST",simulated=True),
        market_version=market_decision.version,inventory_version=0,perp_version=frame.perp_context.version,
    )
    assert normal.state==RiskState.NORMAL
    normal_quotes=normal_fw.transform(
        agent_quotes,normal,center=inventory_decision.reservation_price,tick_size=config.tick_size,
        size_precision=config.size_precision,base_order_size=config.base_order_size,
    )
    assert [(q.side,q.price,q.size) for q in normal_quotes]==[(q.side,q.price,q.size) for q in agent_quotes]

    reduce_fw=RiskFirewall(RiskFirewallConfig())
    reduce=reduce_fw.evaluate(
        refs=refs,quotes=agent_quotes,current_position=D("0"),mark=frame.perp_context.mark_price,
        liquidation=None,pnl=PnlDrawdown(
            session_pnl=D("0"),current_equity=D("890"),peak_equity=D("1000"),
            drawdown_pct=D(".11"),source="TEST",simulated=True,
        ),
        market_version=market_decision.version,inventory_version=0,perp_version=frame.perp_context.version,
    )
    assert reduce.state==RiskState.REDUCE
    reduced=reduce_fw.transform(
        agent_quotes,reduce,center=inventory_decision.reservation_price,tick_size=config.tick_size,
        size_precision=config.size_precision,base_order_size=config.base_order_size,
    )
    assert all(q.size<=next(a.size for a in agent_quotes if a.side==q.side and a.level_index==q.level_index) for q in reduced)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario",["FLASH_MOVE","ORACLE_DISLOCATION","REFERENCE_DEGRADATION","HIGH_VOLATILITY"])
async def test_stress_scenarios_are_finite_and_preserve_risk_authority(scenario):
    result=await SimulationEngine().run(
        dataset=generate_scenario(scenario,frames=24),
        strategy_config=StrategyConfig(),agent_config=AgentConfig(),risk_config=RiskFirewallConfig(),
        simulation_config=SimulationConfig(max_frames=24,trace_max_points=24),scenario=scenario,
    )
    financial=[
        result.metrics.starting_equity,result.metrics.ending_equity,result.metrics.session_pnl,
        result.metrics.return_pct,result.metrics.max_drawdown_pct,result.metrics.max_abs_inventory_base,
        result.metrics.max_inventory_utilization,result.metrics.reconciliation_churn_ratio,
    ]
    assert all(value.is_finite() for value in financial)
    assert result.metrics.risk_state_counts
    assert all(point.equity.is_finite() and point.drawdown_pct.is_finite() for point in result.trace)
    assert all(D(str(order["size"]))>0 and D(str(order["price"]))>0 for order in result.orders)


@pytest.mark.asyncio
async def test_simulation_does_not_start_reference_service_or_network_transport(monkeypatch):
    async def forbidden(*args,**kwargs):
        raise AssertionError("network/provider service must not be used by simulation")
    monkeypatch.setattr("app.references.service.ReferenceService.start",forbidden)
    dataset=generate_scenario("QUIET",frames=4)
    result=await SimulationEngine().run(
        dataset=dataset,strategy_config=StrategyConfig(),agent_config=AgentConfig(),
        risk_config=RiskFirewallConfig(),simulation_config=SimulationConfig(max_frames=4,record_trace=False),
    )
    assert result.metrics.frame_count==4


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_consensus",[False,True])
async def test_frame_fills_bind_consensus_before_update_and_match_runtime(monkeypatch,missing_consensus):
    from app.config import Settings
    from app.runtime import HyperAmmRuntime
    from app.agents.execution_quality import ExecutionQualityAgent,spread_capture_bps
    from test_phase9_agents import evidence

    dataset=generate_scenario("FLASH_MOVE",frames=12)
    stores=[];bound_refs={};phases=[];in_update=[False]
    class CapturingTelemetry(AgentTelemetryStore):
        def __init__(self):
            super().__init__();stores.append(self)
        def observe_fill_from_references(self,fill,refs):
            bound_refs[self.fill_identity(fill)]=refs.model_copy(deep=True)
            phases.append(in_update[0])
            return super().observe_fill_from_references(fill,refs)
    monkeypatch.setattr(engine_module,"AgentTelemetryStore",CapturingTelemetry)
    original_refs=engine_module.build_simulated_references
    prepared={}
    def build_refs(frame,**kwargs):
        refs=original_refs(frame,**kwargs)
        refs.consensus.consensus_price=None if missing_consensus else frame.market.mid_price+D(".25")
        prepared[frame.timestamp]=refs.model_copy(deep=True)
        return refs
    monkeypatch.setattr(engine_module,"build_simulated_references",build_refs)
    # Permit orders to rest despite missing fill-capture evidence, then exercise
    # their market-update fills. Phase 8 behavior is covered independently.
    original_risk=engine_module.RiskFirewall.evaluate
    def risk_evaluate(self,**kwargs):
        if missing_consensus:
            kwargs["refs"]=kwargs["refs"].model_copy(deep=True)
            kwargs["refs"].consensus.consensus_price=kwargs["mark"]
        return original_risk(self,**kwargs)
    monkeypatch.setattr(engine_module.RiskFirewall,"evaluate",risk_evaluate)
    original_update=PaperExecutionAdapter.update_market
    def update(self,snapshot):
        in_update[0]=True
        try:return original_update(self,snapshot)
        finally:in_update[0]=False
    monkeypatch.setattr(PaperExecutionAdapter,"update_market",update)
    agents=AgentConfig(execution_quality_min_fills=1)
    result=await SimulationEngine().run(dataset=dataset,strategy_config=StrategyConfig(),agent_config=agents,
                                      risk_config=RiskFirewallConfig(),simulation_config=SimulationConfig(max_frames=12))
    assert result.fills and any(phases),"must exercise fills inside update_market"
    sim_store=stores[0];runtime=HyperAmmRuntime(Settings(_env_file=None))
    for payload in result.fills:
        fill=Fill.model_validate(payload)
        refs=prepared[fill.timestamp]
        assert bound_refs[sim_store.fill_identity(fill)]==refs
        runtime.references=refs
        runtime._on_paper_fill(fill)
    observed=sim_store.fills(500)
    assert runtime.agent_telemetry.fills(500)==observed
    for fill in observed:
        if missing_consensus:
            assert fill.reference_price is None and fill.reference_source is None
            assert fill.reference_provenance=={}
        else:
            refs=prepared[fill.timestamp]
            assert fill.reference_price==refs.consensus.consensus_price
            assert fill.reference_timestamp==refs.consensus.updated_at==fill.timestamp
            assert fill.reference_source=="CONSENSUS" and fill.reference_version==refs.version
            assert set(fill.reference_provenance)==set(refs.consensus.eligible_providers)
            for provider,item in fill.reference_provenance.items():
                assert item==refs.evidence[provider]
                assert item.source_timestamp==fill.timestamp and item.source_id.startswith("simulation:")
    history=MarketPriceHistory()
    for frame in dataset.frames:history.add_snapshot(frame.market)
    runtime_quality=ExecutionQualityAgent(agents).evaluate(evidence(),runtime.agent_telemetry,history,"PAPER")
    sim_quality=ExecutionQualityAgent(agents).evaluate(evidence(),sim_store,history,"PAPER")
    assert runtime_quality.metrics.average_spread_capture_bps==sim_quality.metrics.average_spread_capture_bps==result.metrics.mean_spread_capture_bps
    if missing_consensus:assert result.metrics.mean_spread_capture_bps is None
    else:
        expected=sum((spread_capture_bps(f.side,f.price,f.reference_price) for f in observed),D("0"))/D(len(observed))
        assert result.metrics.mean_spread_capture_bps==expected
        # Later provider/reference updates must not rebind the accepted fill evidence.
        refs=prepared[observed[0].timestamp]
        refs.consensus.consensus_price=D("1")
        refs.evidence[next(iter(observed[0].reference_provenance))].source_id="later"
        assert observed[0].reference_price!=D("1")
        assert all(item.source_id!="later" for item in observed[0].reference_provenance.values())


def test_simulation_churn_is_action_based_and_ignores_keep_cadence():
    from app.agents.execution_quality import churn_ratio
    acc=MetricsAccumulator(D("1000"));acc.create=1;acc.replace=1
    kwargs=dict(paper=SimpleNamespace(fills=SimpleNamespace(all=lambda:[])),market="ETH",
                vault=SimpleNamespace(net_pnl_quote=D("0"),equity_quote=D("1000"),realized_pnl_quote=D("0"),unrealized_pnl_quote=D("0"),position_base=D("0")),
                telemetry=AgentTelemetryStore(),history=MarketPriceHistory(),agent_config=AgentConfig(),frame_count=1)
    initial=acc.finalize(**kwargs);acc.keep=1000;after=acc.finalize(**kwargs)
    assert initial.reconciliation_churn_ratio==after.reconciliation_churn_ratio==churn_ratio(1000,1,1,0)==D(".5")
    assert after.keep_count==1000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "training,validation,alias_validation,overlap",
    [
        (["QUIET"],["TREND_UP"],False,False),
        (["QUIET"],["QUIET"],False,True),
        (["QUIET","QUIET"],["QUIET","QUIET"],False,True),
        (["QUIET"],["TREND_UP"],True,True),
        (["QUIET","TREND_UP"],["TREND_UP","MEAN_REVERTING"],False,True),
    ],
)
async def test_optimizer_validation_provenance_uses_dataset_identity(
    monkeypatch,training,validation,alias_validation,overlap
):
    import app.simulation.optimizer as optimizer_module
    from app.simulation.config import OptimizationObjectiveConfig
    from app.simulation.models import OptimizationResult

    frames=3
    if alias_validation:
        # Different labels resolve to one real, validated deterministic dataset.
        shared=generate_scenario("QUIET",frames=frames)
        monkeypatch.setattr(optimizer_module,"generate_scenario",lambda *args,**kwargs:shared)
    result=await optimizer_module.StrategyOptimizer().optimize(
        baseline_strategy=StrategyConfig(),baseline_agents=AgentConfig(),risk_config=RiskFirewallConfig(),
        simulation_config=SimulationConfig(max_frames=frames,record_trace=False),
        strategy_grid={"levels_per_side":[4,6]},agent_grid={},
        training_scenarios=training,validation_scenarios=validation,
        objective=OptimizationObjectiveConfig(),max_candidates=2,frames=frames,top_n=1,
    )
    expected_training=[optimizer_module.generate_scenario(name,frames=frames).fingerprint for name in training]
    expected_validation=[optimizer_module.generate_scenario(name,frames=frames).fingerprint for name in validation]
    classification="REUSED_OVERLAPPING" if overlap else "INDEPENDENT_HOLDOUT"
    for candidate in [result.baseline,result.ranked_candidates[0]]:
        assert candidate.training_dataset_fingerprints==expected_training
        assert candidate.validation_dataset_fingerprints==expected_validation
        assert candidate.validation_overlap is overlap
        assert candidate.independent_holdout is (not overlap)
        assert candidate.validation_classification==classification
        for evaluation,expected in zip(candidate.training+candidate.validation,expected_training+expected_validation):
            assert evaluation.dataset_fingerprint==expected
            assert evaluation.model_dump(mode="json")["dataset_fingerprint"]==expected
        encoded=candidate.model_dump(mode="json")
        assert encoded["training_dataset_fingerprints"]==expected_training
        assert encoded["validation_dataset_fingerprints"]==expected_validation
        assert encoded["validation_overlap"] is overlap
        assert encoded["independent_holdout"] is (not overlap)
        assert encoded["validation_classification"]==classification

    unevaluated=result.ranked_candidates[1]
    assert unevaluated.validation==[]
    assert unevaluated.validation_classification=="NOT_EVALUATED"
    assert unevaluated.independent_holdout is False
    assert result.training_dataset_fingerprints==sorted(set(expected_training))
    assert result.validation_dataset_fingerprints==sorted(set(expected_validation))
    assert result.validation_overlap is overlap
    assert result.independent_holdout is (not overlap)
    assert result.validation_classification==classification
    serialized=result.model_dump(mode="json")
    assert serialized["training_dataset_fingerprints"]==sorted(set(expected_training))
    assert serialized["validation_dataset_fingerprints"]==sorted(set(expected_validation))
    assert serialized["validation_overlap"] is overlap
    assert serialized["independent_holdout"] is (not overlap)
    assert serialized["validation_classification"]==classification
    assert OptimizationResult.model_validate_json(result.model_dump_json()).model_dump()==result.model_dump()
    if overlap:
        # Caller-supplied claims cannot override the classification derived from identity.
        serialized.update(independent_holdout=True,validation_overlap=False,validation_classification="INDEPENDENT_HOLDOUT")
        reconstructed=OptimizationResult.model_validate(serialized)
        assert reconstructed.independent_holdout is False
        assert reconstructed.validation_overlap is True
        assert reconstructed.validation_classification=="REUSED_OVERLAPPING"


@pytest.mark.asyncio
@pytest.mark.parametrize("cadence", range(4), ids=["regular", "bursty", "sparse", "irregular"])
async def test_simulation_shared_count_sampling_and_retimed_run_determinism(monkeypatch, cadence):
    import app.strategy.market_adaptation as adaptation
    from test_phase6_runtime import SAMPLING_CADENCES

    regular = generate_scenario("HIGH_VOLATILITY", frames=5)
    start = regular.frames[0].timestamp
    frames = []
    for frame, offset in zip(regular.frames, SAMPLING_CADENCES[cadence]):
        timestamp = start + timedelta(seconds=offset)
        market = frame.market.model_copy(update={
            "latest_valid_update": timestamp,
            "book": frame.market.book.model_copy(update={"timestamp": timestamp}),
        })
        frames.append(frame.model_copy(update={
            "timestamp": timestamp, "market": market,
            "perp_context": frame.perp_context.model_copy(update={"updated_at": timestamp}),
        }))
    dataset = SimulationDataset(market=regular.market, source=regular.source, frames=frames)
    config = StrategyConfig(volatility_window_samples=4, volatility_min_samples=3)
    agents = AgentConfig(regime_min_samples=3, regime_momentum_window_samples=5)
    observed = []
    calculated = []
    original_evidence = engine_module.build_agent_evidence
    original_estimator = adaptation.calculate_realized_volatility

    def capture_estimator(prices):
        calculated.append(list(prices))
        return original_estimator(prices)

    def capture_evidence(**kwargs):
        decision = kwargs["market_decision"]
        evidence = original_evidence(**kwargs)
        assert evidence.realized_volatility == decision.realized_volatility
        assert evidence.volatility_score == decision.volatility_score
        assert evidence.market_adaptation_regime == decision.regime.value
        observed.append((decision.sample_count, decision.volatility_ready, decision.realized_volatility, decision.volatility_score, decision.regime))
        return evidence

    monkeypatch.setattr(adaptation, "calculate_realized_volatility", capture_estimator)
    monkeypatch.setattr(engine_module, "build_agent_evidence", capture_evidence)
    kwargs = dict(dataset=dataset, strategy_config=config, agent_config=agents,
                  risk_config=RiskFirewallConfig(), simulation_config=SimulationConfig(max_frames=5, trace_max_points=5))
    first = await SimulationEngine().run(**kwargs)
    second = await SimulationEngine().run(**kwargs)
    assert first.run_fingerprint == second.run_fingerprint
    assert first.metrics == second.metrics
    assert first.orders == second.orders and first.fills == second.fills
    assert first.trace == second.trace
    assert observed[:5] == observed[5:]
    expected = []
    history = MarketPriceHistory()
    for frame in regular.frames:
        history.add_snapshot(frame.market)
        decision = adaptation.MarketAdaptationPolicy(config).decision(frame.market, history)
        expected.append((decision.sample_count, decision.volatility_ready, decision.realized_volatility, decision.volatility_score, decision.regime))
    assert observed[:5] == expected
    windows = [[frame.market.mid_price for frame in regular.frames[:count]][-4:] for count in range(3, 6)]
    # Exactly one Phase 6 estimator call per ready frame, with its trailing prices.
    assert calculated[:6] == windows * 2
    assert [point.agent_regime for point in first.trace] == ["WARMING_UP"] * 2 + ["HIGH_VOLATILITY"] * 3
