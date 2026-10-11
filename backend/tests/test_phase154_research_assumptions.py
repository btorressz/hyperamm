from decimal import Decimal as D
import pytest
from app.simulation.scenarios import ScenarioName, generate_scenario
from app.simulation.models import SimulationResult, ResearchMarketAssumptions
from app.simulation.service import SimulationService
from app.simulation.config import SimulationConfig
from app.strategy.models import StrategyConfig
from app.agents.config import AgentConfig
from app.risk.firewall import RiskFirewallConfig
from app.simulation.research_vault import ResearchProposal, ResearchVaultConfig
from app.research_comparison.assumptions import capture_assumptions
from phase154_helpers import market_profile, result_summary

@pytest.mark.parametrize('market', ['BTC','ETH','SOL'])
@pytest.mark.parametrize('scenario', list(ScenarioName))
def test_all_actual_scenario_frames(market, scenario):
    p=market_profile(market)
    dataset=generate_scenario(scenario, frames=8, market=market, market_profile=p)
    a=capture_assumptions(dataset, dataset.frames, scenario.value, p)
    f=dataset.frames[-1]
    assert a.representative_frame_sequence==f.sequence and a.representative_frame_timestamp==f.timestamp
    assert (a.midpoint,a.best_bid,a.best_ask)==(f.market.mid_price,f.market.best_bid,f.market.best_ask)
    assert a.funding_rate==f.perp_context.funding_rate and a.open_interest_base==f.perp_context.open_interest_base
    assert a.spread_quote==f.market.best_ask-f.market.best_bid
    assert a.spread_bps==a.spread_quote/a.midpoint*D(10000)
    assert a.bid_depth_base==sum((x.size for x in f.market.book.bids[:5]),D(0))
    assert a.ask_depth_base==sum((x.size for x in f.market.book.asks[:5]),D(0))
    assert a.market_profile_fingerprint==p.profile_fingerprint and a.dataset_fingerprint==dataset.fingerprint
    assert capture_assumptions(dataset,dataset.frames,scenario.value,p)==a
    other=generate_scenario(scenario,frames=9,market=market,market_profile=p)
    assert capture_assumptions(other,other.frames,scenario.value,p).assumption_fingerprint!=a.assumption_fingerprint
    assert ResearchMarketAssumptions.model_validate_json(a.model_dump_json())==a

@pytest.mark.parametrize('market', ['BTC','ETH','SOL'])
async def test_real_engine_trace_caps_legacy_and_shared_vault_dataset(market):
    service=SimulationService();p=market_profile(market)
    args=dict(scenario='TREND_UP',frames=5,strategy=StrategyConfig(),agents=AgentConfig(),risk=RiskFirewallConfig(),market_profile=p)
    runs=[await service.run_scenario(**args,simulation=SimulationConfig(max_frames=5,record_trace=cap>0,trace_max_points=cap)) for cap in (0,1,5)]
    assert runs[0].research_assumptions==runs[1].research_assumptions==runs[2].research_assumptions
    assert len(runs[0].trace)==0 and len(runs[1].trace)==1
    assert result_summary(runs[0]).assumptions==runs[0].research_assumptions
    data=runs[0].model_dump();data.pop('research_assumptions');assert SimulationResult.model_validate(data).research_assumptions is None
    pair=await service.compare_research_configs(**args,simulation=SimulationConfig(max_frames=5),
        baseline=ResearchProposal(config=ResearchVaultConfig()),custom=ResearchProposal(config=ResearchVaultConfig(paper_fee_model_enabled=True)))
    assert pair.baseline_result.research_assumptions==pair.custom_result.research_assumptions
    assert result_summary(pair.custom_result).research_configuration.config_fingerprint==pair.custom_config_fingerprint
