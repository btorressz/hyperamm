from fastapi.testclient import TestClient
from app.main import app


def test_fastapi_health_and_strategy():
    with TestClient(app) as client:
        r=client.get('/api/v1/health'); assert r.status_code==200 and r.json()['app']=='HyperAMM'
        r=client.get('/api/v1/strategy'); assert r.status_code==200
        assert r.json()['config']['execution_mode']=='PAPER'

def test_api_start_stop_kill_resume():
    with TestClient(app) as client:
        assert client.post('/api/v1/strategy/start').status_code==200
        assert client.post('/api/v1/strategy/stop').status_code==200
        assert client.post('/api/v1/risk/kill').json()['kill_switch_active'] is True
        assert client.post('/api/v1/risk/resume').json()['kill_switch_active'] is False

def test_stopped_strategy_preview_does_not_place_orders():
    with TestClient(app) as client:
        client.get('/api/v1/amm/curve')
        orders=client.get('/api/v1/orders').json()
        assert orders == []


def test_positions_returns_normalized_paper_inventory():
    with TestClient(app) as client:
        r=client.get('/api/v1/positions')
        assert r.status_code==200
        data=r.json()
        assert data['market']=='ETH'
        assert data['source']=='PAPER'
        assert data['position_base']=='0'
        assert data['target_base']=='0'
        assert data['stale'] is False


def test_market_adaptation_endpoint_returns_normalized_warmup_or_ready_state():
    with TestClient(app) as client:
        r=client.get('/api/v1/market-adaptation')
        assert r.status_code==200
        data=r.json()
        assert data['market']=='ETH'
        assert data['source']=='NORMALIZED_MID_L2'
        assert data['sample_count']>=1
        assert data['volatility_ready'] in {True,False}
        if not data['volatility_ready']:
            assert data['realized_volatility'] is None
            assert data['spread_multiplier']=='1'


def test_terminal_state_includes_market_adaptation_after_preview_refresh():
    with TestClient(app) as client:
        assert client.get('/api/v1/amm/curve').status_code==200
        with client.websocket_connect('/ws/terminal') as ws:
            data=ws.receive_json()
            assert 'market_adaptation' in data
            assert data['market_adaptation'] is not None
            assert data['market_adaptation']['market']=='ETH'


def test_invalid_market_adaptation_config_returns_422():
    with TestClient(app) as client:
        config=client.get('/api/v1/strategy').json()['config']
        config['volatility_window_samples']=5
        config['volatility_min_samples']=10
        r=client.put('/api/v1/strategy',json=config)
        assert r.status_code==422


def test_perp_context_endpoint_returns_normalized_demo_context():
    with TestClient(app) as client:
        r=client.get('/api/v1/perp-context')
        assert r.status_code==200
        data=r.json()
        assert data['market']=='ETH'
        assert data['source']=='DEMO'
        assert data['simulated'] is True
        assert data['stale'] is False
        assert data['mark_price'] is not None
        assert data['oracle_price'] is not None
        assert data['funding_rate'] is not None
        assert data['open_interest_base'] is not None
        assert data['open_interest_notional'] is not None
        assert data['funding_score'] is not None
        assert data['strategy_reference_price'] is not None
        assert data['position']['source']=='PAPER'
        assert data['position']['entry_price'] is None
        assert data['position']['liquidation_price'] is None


def test_terminal_state_includes_perp_context_after_preview_refresh():
    with TestClient(app) as client:
        assert client.get('/api/v1/amm/curve').status_code==200
        with client.websocket_connect('/ws/terminal') as ws:
            data=ws.receive_json()
            assert data['perp_context'] is not None
            assert data['perp_context']['market']=='ETH'
            assert data['perp_context']['source']=='DEMO'


def test_invalid_perp_config_returns_422():
    with TestClient(app) as client:
        config=client.get('/api/v1/strategy').json()['config']
        config['perp_mark_weight']='0.8'
        config['perp_oracle_weight']='0.3'
        r=client.put('/api/v1/strategy',json=config)
        assert r.status_code==422


def test_phase8_reference_and_risk_endpoints_in_demo():
    with TestClient(app) as client:
        assert client.get('/api/v1/amm/curve').status_code==200
        refs=client.get('/api/v1/references')
        assert refs.status_code==200
        data=refs.json()
        assert data['consensus']['confidence_state']=='VERIFIED'
        assert data['evidence']['REDSTONE']['simulated'] is True
        assert data['evidence']['KRAKEN']['source_type']=='VENUE_REFERENCE'
        assert data['evidence']['COINGECKO']['source_type']=='AGGREGATOR_REFERENCE'

        risk=client.get('/api/v1/risk')
        assert risk.status_code==200
        assert 'firewall' in risk.json()

        evidence=client.get('/api/v1/risk/evidence')
        assert evidence.status_code==200
        assert evidence.json()['references'] is not None
        assert evidence.json()['risk'] is not None

        events=client.get('/api/v1/risk/events')
        assert events.status_code==200 and isinstance(events.json(),list)

        auth=client.get('/api/v1/risk/authorization')
        assert auth.status_code==200
        assert 'authorized' in auth.json()


def test_phase8_terminal_serialization_and_secrets_absent():
    with TestClient(app) as client:
        assert client.get('/api/v1/amm/curve').status_code==200
        with client.websocket_connect('/ws/terminal') as ws:
            data=ws.receive_json()
            for key in ('references','reference_consensus','risk_firewall','risk_authorization','risk_events','projected_exposure','pnl_drawdown'):
                assert key in data
            raw=str(data).lower()
            assert 'hyperliquid_private_key' not in raw
            assert 'redstone_api_key' not in raw
            assert 'coingecko_api_key' not in raw


def test_phase9_agents_api_and_terminal_state():
    with TestClient(app) as client:
        assert client.get('/api/v1/amm/curve').status_code==200
        agents=client.get('/api/v1/agents')
        assert agents.status_code==200
        data=agents.json()
        for key in ('config','regime','toxic_flow','execution_quality','supervisor','agent_version','agent_fingerprint','telemetry'):
            assert key in data
        assert data['supervisor'] is not None
        assert data['supervisor']['enabled'] is True
        assert data['supervisor']['simulated'] is True

        events=client.get('/api/v1/agents/events')
        assert events.status_code==200
        assert isinstance(events.json(),list)

        assert client.post('/api/v1/agents/trade').status_code==404
        assert client.post('/api/v1/agents/execute').status_code==404
        assert client.post('/api/v1/agents/order').status_code==404

        with client.websocket_connect('/ws/terminal') as ws:
            terminal=ws.receive_json()
            assert terminal['agents']['supervisor'] is not None
            assert 'agent_events' in terminal
            assert 'agent_quotes' in terminal
            assert terminal['risk_authorization']['agent_version']==terminal['agents']['agent_version']
            assert terminal['risk_authorization']['agent_fingerprint']==terminal['agents']['agent_fingerprint']


def test_phase9_agent_api_exposes_no_secrets_or_execution_actions():
    with TestClient(app) as client:
        assert client.get('/api/v1/amm/curve').status_code==200
        raw=str(client.get('/api/v1/agents').json()).lower()
        for token in ('private_key','redstone_api_key','coingecko_api_key','submit_orders','cancel_orders','replace_orders'):
            assert token not in raw


def test_execution_api_uses_recent_views_and_validates_limits(monkeypatch):
    from app.execution.models import Fill, OrderStatus
    from test_execution import o
    from decimal import Decimal
    with TestClient(app) as client:
        rt = app.state.runtime
        rt.paper.orders.limit = 120
        for index in range(150):
            order = o(cid=f'closed-{index}')
            order.status = OrderStatus.CANCELLED
            rt.paper.orders[order.client_order_id] = order
        active = o(cid='active'); rt.paper.orders[active.client_order_id] = active
        for index in range(150):
            rt.paper.fills.add(Fill(client_order_id=f'fill-{index}', market='ETH', side='BID',
                                   price=Decimal('3000'), size=Decimal('.01')))
        monkeypatch.setattr(rt.paper, 'all_orders', lambda: (_ for _ in ()).throw(AssertionError('full order scan')))
        monkeypatch.setattr(rt.paper.fills, 'all', lambda: (_ for _ in ()).throw(AssertionError('full fill scan')))
        rows = client.get('/api/v1/orders').json()
        assert len(rows) == 101 and rows[0]['client_order_id'] == 'active'
        assert rows[1]['client_order_id'] == 'closed-50'
        assert len(client.get('/api/v1/orders?limit=7').json()) == 8
        rows = client.get('/api/v1/fills?limit=7').json()
        assert len(rows) == 7 and rows[0]['client_order_id'] == 'fill-143'
        for endpoint in ['/orders', '/fills']:
            for limit in [0, 1001]:
                assert client.get(f'/api/v1{endpoint}?limit={limit}').status_code == 422
