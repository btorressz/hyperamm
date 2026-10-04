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
