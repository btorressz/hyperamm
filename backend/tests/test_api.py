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
