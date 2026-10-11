from app.simulation.market_profiles import profile, ResearchPerpMarketMetadata
from app.simulation.scenarios import generate_scenario
from app.research_comparison.assumptions import capture_assumptions
from app.research_comparison.models import ResearchEvidenceSummary, ResearchMarketComparisonRequest


def market_profile(market='BTC'):
    return profile(ResearchPerpMarketMetadata(market=market, sz_decimals={'BTC':5,'ETH':4,'SOL':2}[market],
        metadata_status='DEMO_PROFILE', metadata_source='PINNED_RESEARCH_FIXTURE'))


def summary(market='BTC', scenario='QUIET', assumptions=True):
    p = market_profile(market)
    dataset = generate_scenario(scenario, frames=3, market=market, market_profile=p)
    a = capture_assumptions(dataset, dataset.frames, scenario, p)
    return ResearchEvidenceSummary(engine_version='test-fixture', **p.evidence(),
        run_fingerprint='a'*64, dataset_fingerprint=dataset.fingerprint, strategy_fingerprint='b'*64,
        scenario=scenario, simulated=True, assumptions=a if assumptions else None,
        performance=dict(frame_count=3, session_pnl='0', return_pct='0', realized_pnl='0', unrealized_pnl='0',
            max_drawdown_pct='0', fill_count=0, quoted_notional='0', filled_notional='0', fill_activity_ratio=None,
            mean_spread_capture_bps=None, mean_mature_markout_bps=None, adverse_fill_rate=None,
            ending_inventory_base='0', max_inventory_utilization='0', risk_halt_fraction='0', risk_state_counts={'NORMAL':3}))


def request(selected_market='BTC', **kwargs):
    return ResearchMarketComparisonRequest(market=selected_market, research=summary(**kwargs))


def result_summary(result):
    fields = set(ResearchEvidenceSummary.model_fields) - {'assumptions','performance'}
    data = result.model_dump(mode='json')
    performance = {k:data['metrics'][k] for k in result_summary.metric_fields}
    performance.update(fees_quote=data['vault']['fees_quote'] if data['vault'] else None,
                       funding_quote=data['vault']['funding_quote'] if data['vault'] else None)
    return ResearchEvidenceSummary(**{k:data.get(k) for k in fields}, assumptions=data['research_assumptions'], performance=performance)

result_summary.metric_fields = ('frame_count','session_pnl','return_pct','realized_pnl','unrealized_pnl','max_drawdown_pct',
    'fill_count','quoted_notional','filled_notional','fill_activity_ratio','mean_spread_capture_bps','mean_mature_markout_bps',
    'adverse_fill_rate','ending_inventory_base','max_inventory_utilization','risk_halt_fraction','risk_state_counts')
