from decimal import Decimal as D
from types import SimpleNamespace

import pytest

import app.simulation.engine as engine_module
from app.agents.config import AgentConfig
from app.execution.models import Fill,OrderRequest
from app.execution.paper import PaperExecutionAdapter
from app.market_data.models import MarketConnectionState,MarketDataMode,MarketLevel,MarketSnapshot,OrderBookSnapshot
from app.risk.firewall import RiskFirewallConfig,paper_pnl
from app.strategy.models import StrategyConfig
from app.simulation.config import SimulationConfig
from app.simulation.engine import SimulationClock,SimulationEngine
from app.simulation.metrics import MetricsAccumulator
from app.simulation.models import SimulationDataset,SimulationReferencePrices
from app.simulation.scenarios import generate_scenario


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
    assert paper.fills.all()[0].timestamp==dataset.frames[1].timestamp

    clock.set(dataset.frames[2].timestamp)
    paper.update_market(crossed_snapshot(dataset.frames[2],bid="102",ask="103"))
    assert [f.client_order_id for f in paper.fills.all()]==["bid","ask"]
    assert paper.fills.all()[1].timestamp==dataset.frames[2].timestamp


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
    risk=SimpleNamespace(state=SimpleNamespace(value="NORMAL"))
    agent=SimpleNamespace(
        regime=SimpleNamespace(state=SimpleNamespace(value="NORMAL")),
        toxic_flow=SimpleNamespace(state=SimpleNamespace(value="NORMAL")),
        execution_quality=SimpleNamespace(state=SimpleNamespace(value="NORMAL")),
    )
    inventory=SimpleNamespace(position_base=D("0"),inventory_ratio=D("0"))
    acc.record(authorized_quotes=[],inventory=inventory,risk_decision=risk,agent_decision=agent,equity=D("1100"),drawdown_pct=D("0"),actions=[])
    acc.record(authorized_quotes=[],inventory=inventory,risk_decision=risk,agent_decision=agent,equity=D("990"),drawdown_pct=D(".1"),actions=[])
    assert acc.peak_equity==D("1100")
    assert acc.max_drawdown_pct==D(".1")
