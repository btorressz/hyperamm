"""Phase 14 contracts, economics, controlled comparisons and authority isolation."""
import asyncio
from decimal import Decimal as D
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.accounting.config import AccountingConfig
from app.agents.config import AgentConfig
from app.config import Settings
from app.main import app
from app.runtime import HyperAmmRuntime
from app.risk.firewall import RiskFirewallConfig
from app.simulation.config import SimulationConfig
from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.presets import PRESETS, get_preset
from app.simulation.research_vault import ResearchProposal, ResearchVaultConfig, preview, result_deltas
from app.simulation.service import SimulationService
from app.strategy.models import StrategyConfig


@pytest.fixture
def research_client(monkeypatch):
    rt = HyperAmmRuntime(Settings(market_data_mode='DEMO', execution_mode='PAPER',
                                 enable_hyperliquid_testnet_orders=False))
    worker = SimulationExecutor()
    monkeypatch.setattr(app.state, 'runtime', rt, raising=False)
    monkeypatch.setattr(app.state, 'simulation_executor', worker, raising=False)
    # Deliberately no lifespan/feed: authoritative state stays frozen for exact
    # before/after checks; this is a runtime fixture, not live provider evidence.
    client = TestClient(app)
    yield client, rt
    client.close()
    asyncio.run(worker.shutdown())


def proposal(config=None, preset='balanced-research'):
    return ResearchProposal(config=config or get_preset(preset).config, selected_preset_id=preset)


def authority(rt):
    vault = rt.accounting_service.snapshot().model_dump(mode='json')
    return dict(strategy=rt.config.model_dump(mode='json'), agents=rt.agent_config.model_dump(mode='json'),
        risk=rt.risk_config.model_dump(mode='json'), running=rt.strategy.running,
        kill=rt.risk.kill_switch_active, authorization=rt.authorization,
        accounting_id=id(rt.accounting_service), accounting_config=rt.accounting_config.model_dump(mode='json'),
        vault=vault, ledger=rt.accounting_service.ledger.fingerprint,
        entries=rt.accounting_service.ledger.entries(500), orders_id=id(rt.orders),
        orders=[o.model_dump(mode='json') for o in rt.paper.all_orders()],
        fills=[f.model_dump(mode='json') for f in rt.paper.fills.all()],
        quotes=list(rt.quotes), testnet_enabled=rt.testnet.enabled, execution=id(rt.execution))


def test_defaults_reuse_domain_rules_and_single_capital():
    config = ResearchVaultConfig()
    assert config.initial_equity_quote == AccountingConfig().paper_initial_equity_quote
    converted = config.to_simulation()
    assert converted.initial_equity_quote == converted.accounting.paper_initial_equity_quote
    assert converted.accounting.enabled and converted.fill_model == 'CROSSING_ONLY'
    assert converted.accounting.ledger_max_entries == AccountingConfig().ledger_max_entries
    assert set(type(config).model_fields) == {'initial_equity_quote','paper_fee_model_enabled','paper_maker_fee_bps',
        'paper_taker_fee_bps','paper_funding_accounting_enabled','paper_funding_interval_seconds','max_capital_utilization'}


@pytest.mark.parametrize('field,value', [
    ('initial_equity_quote','0'), ('initial_equity_quote','-1'), ('initial_equity_quote','NaN'),
    ('initial_equity_quote','Infinity'), ('initial_equity_quote','1e10000'), ('initial_equity_quote','abc'),
    ('initial_equity_quote',True), ('initial_equity_quote','1000000000001'), ('initial_equity_quote','1e-19'),
    ('paper_maker_fee_bps','-1'), ('paper_taker_fee_bps','101'), ('paper_taker_fee_bps','NaN'),
    ('max_capital_utilization','0'), ('max_capital_utilization','1.01'), ('max_capital_utilization','-0.1'),
    ('max_capital_utilization','Infinity'), ('paper_funding_interval_seconds',0),
    ('paper_funding_interval_seconds',2), ('paper_funding_interval_seconds',86401),
    ('paper_funding_interval_seconds',True), ('paper_funding_interval_seconds','60'),
    ('paper_fee_model_enabled','true'), ('paper_funding_accounting_enabled',1),
    ('initial_equity_quote','1'*81), ('paper_maker_fee_bps',{'enabled':True}),
])
def test_malformed_values_fail_closed(field, value):
    with pytest.raises(ValidationError):
        ResearchVaultConfig(**{field:value})


@pytest.mark.parametrize('field', ['execution_mode','market_data_mode','hyperliquid_private_key',
    'enable_hyperliquid_testnet_orders','accounting','enabled','fill_model','paper_initial_equity_quote',
    'ledger_max_entries','event_max_entries','accounting_stale_after_seconds','risk','strategy','kill'])
def test_protected_fields_are_never_research_fields(field):
    with pytest.raises(ValidationError):
        ResearchVaultConfig(**{field:{'execution_mode':'TESTNET'}})


def test_economically_equivalent_decimals_have_same_versioned_fingerprint():
    a = ResearchVaultConfig(initial_equity_quote='100000.000', paper_maker_fee_bps='1.00', max_capital_utilization='0.750')
    b = ResearchVaultConfig(initial_equity_quote='1e5', paper_maker_fee_bps='1', max_capital_utilization='0.75')
    assert a.fingerprint() == b.fingerprint() and a.canonical() == b.canonical()
    assert a.fingerprint() != ResearchVaultConfig(initial_equity_quote='100001').fingerprint()


def test_catalog_and_preview_are_deterministic_decimal_only(research_client):
    client, rt = research_client
    before = authority(rt)
    one = client.get('/api/v1/research-vault/presets').json()
    assert one == client.get('/api/v1/research-vault/presets').json()
    assert [p['preset_id'] for p in one['presets']] == [p.preset_id for p in PRESETS]
    config = get_preset('balanced-research').config.model_copy(update={'initial_equity_quote':D('12345.123456789123456789')})
    p = proposal(config)
    a = client.post('/api/v1/research-vault/preview',json=p.model_dump(mode='json'))
    assert a.status_code == 200, a.text
    assert a.json() == preview(p)
    assert D(a.json()['illustrative_utilization_ceiling_quote']) == D('9258.84259259184259259175')
    assert D(a.json()['changed_fields'][0]['difference']) == D('-87654.876543210876543211')
    assert 'pnl' not in a.json() and a.json()['validation_status'] == 'VALID'
    assert authority(rt) == before


@pytest.mark.parametrize('payload', [
    {'config':{'execution_mode':'MAINNET'}}, {'config':{'accounting':{'enabled':False}}},
    {'config':{},'selected_preset_id':'unknown'}, {'config':{},'hyperliquid_private_key':'injection-fixture'},
    {'config':{'initial_equity_quote':'NaN'}}, {'config':{'paper_taker_fee_bps':'-3'}},
])
def test_api_rejects_malicious_proposals_without_mutation(research_client,payload):
    client, rt = research_client
    before = authority(rt)
    response = client.post('/api/v1/research-vault/preview', json=payload)
    assert response.status_code == 422
    assert authority(rt) == before


def test_oversized_chunked_and_regular_payloads(research_client):
    client, _ = research_client
    response = client.post('/api/v1/research-vault/preview', content=b'x'*65537)
    assert response.status_code == 413
    response = client.post('/api/v1/research-vault/preview', content=iter([b'x'*40000,b'x'*40000]))
    assert response.status_code == 413


@pytest.mark.parametrize('literal', ['NaN', 'Infinity', '-Infinity'])
def test_raw_nonfinite_json_returns_safe_validation_error(research_client, literal):
    client, _ = research_client
    response = client.post('/api/v1/research-vault/preview',
        content='{"config":{"initial_equity_quote":'+literal+'}}', headers={'content-type':'application/json'})
    assert response.status_code == 422
    assert all(set(error) == {'loc','msg','type'} for error in response.json()['detail'])


def test_legacy_research_and_optimizer_compatibility_and_isolation(research_client):
    client, rt = research_client
    before = authority(rt)
    legacy = client.post('/api/v1/simulation/run',json={'frames':3}).json()
    assert legacy['research_configuration'] is None and legacy['metrics']['starting_equity'] == '100000'
    p = proposal(ResearchVaultConfig(initial_equity_quote='40000.125', paper_fee_model_enabled=True,
        paper_funding_accounting_enabled=True, paper_funding_interval_seconds=1))
    request = {'frames':30,'scenario':'FLASH_MOVE','research':p.model_dump(mode='json')}
    one = client.post('/api/v1/simulation/run',json=request)
    assert one.status_code == 200, one.text
    two = client.post('/api/v1/simulation/run',json=request)
    assert one.json() == two.json()
    result = one.json()
    assert result['metrics']['starting_equity'] == result['vault']['initial_equity_quote'] == '40000.125'
    assert D(result['vault']['fees_quote']) > 0
    assert any(e['event_type']=='FUNDING' for e in result['accounting_ledger'])
    assert result['research_configuration']['config_fingerprint'] == p.config.fingerprint()
    opt = client.post('/api/v1/simulation/optimize',json={'research':p.model_dump(mode='json'),
        'strategy_grid':{'levels_per_side':[4]},'agent_grid':{},'training_scenarios':['QUIET'],
        'validation_scenarios':['TREND_UP'],'frames':3,'max_candidates':1,'top_n':1})
    assert opt.status_code == 200, opt.text
    assert opt.json()['research_configuration']['config_fingerprint'] == p.config.fingerprint()
    assert authority(rt) == before


@pytest.mark.parametrize('simulation', [{'accounting':{'enabled':False}}, {'initial_equity_quote':'10'}, {'fill_model':'CROSSING_ONLY'}])
def test_research_rejects_ambiguous_legacy_accounting_controls(research_client, simulation):
    client, _ = research_client
    assert client.post('/api/v1/simulation/run',json={'research':proposal().model_dump(mode='json'),
                                                   'simulation':simulation}).status_code == 422


def test_controlled_comparison_results_and_delta_correctness(research_client):
    client, rt = research_client
    before = authority(rt)
    baseline = proposal()
    custom = proposal(ResearchVaultConfig(initial_equity_quote='80000', paper_fee_model_enabled=True,
        paper_maker_fee_bps='10',paper_taker_fee_bps='25',max_capital_utilization='0.75'))
    body = {'baseline':baseline.model_dump(mode='json'),'custom':custom.model_dump(mode='json'),
            'scenario':'FLASH_MOVE','frames':30}
    response = client.post('/api/v1/research-vault/compare',json=body)
    assert response.status_code == 200, response.text
    assert response.json() == client.post('/api/v1/research-vault/compare',json=body).json()
    data = response.json(); a, b = data['baseline_result'], data['custom_result']
    for key in ('dataset_fingerprint','strategy_fingerprint','engine_version'):
        assert a[key] == b[key]
    assert a['metrics']['frame_count'] == b['metrics']['frame_count'] == 30
    for name in ('ending_equity','session_pnl','max_drawdown_pct'):
        assert D(data['comparison_deltas'][name]) == D(b['metrics'][name]) - D(a['metrics'][name])
    assert D(data['comparison_deltas']['fees_quote']) == D(b['vault']['fees_quote'])-D(a['vault']['fees_quote'])
    assert any('Starting capital differs' in s for s in data['limitations'])
    assert authority(rt) == before


@pytest.mark.asyncio
async def test_comparison_uses_single_dataset_and_frozen_copies(monkeypatch):
    import app.simulation.service as module
    service = SimulationService(); generate = module.generate_scenario
    count = []; seen = []; run = service.engine.run
    def counted(*args, **kwargs):
        count.append(1); return generate(*args,**kwargs)
    async def observed(**kwargs):
        seen.append((id(kwargs['dataset']),kwargs['agent_config'].model_dump(),kwargs['risk_config'].model_dump()))
        return await run(**kwargs)
    monkeypatch.setattr(module,'generate_scenario',counted)
    monkeypatch.setattr(service.engine,'run',observed)
    strategy = StrategyConfig(execution_mode='TESTNET', market_data_mode='LIVE')
    result = await service.compare_research_configs(scenario='QUIET',frames=3,strategy=strategy,
        agents=AgentConfig(),risk=RiskFirewallConfig(),simulation=SimulationConfig(max_frames=3),
        baseline=proposal(),custom=proposal(ResearchVaultConfig(initial_equity_quote='1')))
    assert len(count) == 1 and seen[0] == seen[1]
    assert result.custom_result.metrics.risk_state_counts == {'HALT':3}
    assert strategy.execution_mode == 'TESTNET' and strategy.market_data_mode == 'LIVE'
    assert result.custom_result.orders == []
    result.baseline_result.vault = None
    assert result_deltas(result.baseline_result,result.custom_result)['fees_quote'] is None


@pytest.mark.asyncio
async def test_comparison_cancellation_keeps_single_worker_admission(monkeypatch):
    started, release, finished = Event(), Event(), Event()
    original = SimulationService.compare_research_configs
    async def held(self, **kwargs):
        started.set()
        assert release.wait(5)
        try: return await original(self,**kwargs)
        finally: finished.set()
    monkeypatch.setattr(SimulationService,'compare_research_configs',held)
    worker = SimulationExecutor()
    kwargs = dict(scenario='QUIET',frames=3,strategy=StrategyConfig(),agents=AgentConfig(),
        risk=RiskFirewallConfig(),simulation=SimulationConfig(max_frames=3),baseline=proposal(),custom=proposal())
    task = asyncio.create_task(worker.execute('compare_research_configs',**kwargs))
    try:
        assert await asyncio.to_thread(started.wait,3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        with pytest.raises(ResearchBusyError): await worker.execute('compare_research_configs',**kwargs)
        release.set()
        assert await asyncio.to_thread(finished.wait,3)
    finally:
        release.set(); await worker.shutdown()
