from decimal import Decimal as D

import pytest

from app.strategy.market_adaptation import calculate_book_imbalance,calculate_realized_volatility
from app.simulation.models import SimulationDataset
from app.simulation.references import build_simulated_references
from app.simulation.scenarios import ScenarioName,generate_scenario


@pytest.mark.parametrize("name",list(ScenarioName))
def test_every_builtin_scenario_is_deterministic_and_valid(name):
    a=generate_scenario(name,frames=24)
    b=generate_scenario(name,frames=24)
    assert a.fingerprint==b.fingerprint
    assert a.model_dump(mode="json")==b.model_dump(mode="json")
    assert [f.sequence for f in a.frames]==list(range(1,25))
    assert all(x.timestamp<y.timestamp for x,y in zip(a.frames,a.frames[1:]))
    for frame in a.frames:
        assert frame.market.simulated is True
        assert frame.perp_context.simulated is True
        assert frame.market.best_bid<frame.market.best_ask
        refs=build_simulated_references(frame,agreement_bps=D("30"),outlier_bps=D("75"),version=frame.sequence)
        assert all(item.simulated for item in refs.evidence.values())
        assert all(item.transport.value=="DEMO" for item in refs.evidence.values())
        assert all(item.transport_quality.value=="SIMULATED" for item in refs.evidence.values())


def test_scenario_directional_properties():
    up=generate_scenario("TREND_UP",frames=20)
    down=generate_scenario("TREND_DOWN",frames=20)
    quiet=generate_scenario("QUIET",frames=20)
    high=generate_scenario("HIGH_VOLATILITY",frames=20)
    bid=generate_scenario("BID_HEAVY_BOOK",frames=20)
    ask=generate_scenario("ASK_HEAVY_BOOK",frames=20)
    assert up.frames[-1].market.mid_price>up.frames[0].market.mid_price
    assert down.frames[-1].market.mid_price<down.frames[0].market.mid_price
    quiet_vol=calculate_realized_volatility([f.market.mid_price for f in quiet.frames])
    high_vol=calculate_realized_volatility([f.market.mid_price for f in high.frames])
    assert high_vol>quiet_vol
    assert calculate_book_imbalance(bid.frames[-1].market,5)[2]>0
    assert calculate_book_imbalance(ask.frames[-1].market,5)[2]<0


def test_oracle_dislocation_and_reference_degradation_use_real_consensus_policy():
    dis=generate_scenario("ORACLE_DISLOCATION",frames=5)
    refs=build_simulated_references(dis.frames[-1],agreement_bps=D("30"),outlier_bps=D("75"),version=5)
    assert refs.evidence["REDSTONE"].price!=refs.evidence["HYPERLIQUID_ORACLE"].price
    assert refs.consensus.confidence_state in {"DEGRADED","CONFLICTED"}
    degraded=generate_scenario("REFERENCE_DEGRADATION",frames=5)
    refs=build_simulated_references(degraded.frames[-1],agreement_bps=D("30"),outlier_bps=D("75"),version=5)
    assert refs.evidence["REDSTONE"].status.value=="ERROR"
    assert refs.consensus.confidence_state=="DEGRADED"


def test_dataset_rejects_duplicate_or_regressed_sequence_and_timestamp():
    good=generate_scenario("QUIET",frames=3)
    duplicate=good.frames[1].model_copy(update={"sequence":good.frames[0].sequence})
    with pytest.raises(ValueError,match="sequence"):
        SimulationDataset(market="ETH",frames=[good.frames[0],duplicate],source="bad")
    same_time=good.frames[1].model_copy(update={"timestamp":good.frames[0].timestamp})
    with pytest.raises(ValueError,match="timestamp"):
        SimulationDataset(market="ETH",frames=[good.frames[0],same_time],source="bad")


def test_frame_rejects_mid_bbo_mismatch():
    frame=generate_scenario("QUIET",frames=2).frames[0]
    with pytest.raises(ValueError,match="mid"):
        frame.model_validate({**frame.model_dump(),"market":{**frame.market.model_dump(),"mid_price":D("2999")}})
