from unittest.mock import AsyncMock

import fakeredis
import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.main as main
from app.config import Settings
from app.infrastructure.redis import RedisInfrastructure
from app.runtime import HyperAmmRuntime


def wire_infrastructure(monkeypatch, *, connected=True, required=False, research=True):
    server = fakeredis.FakeServer()
    server.connected = connected
    settings = Settings(_env_file=None, redis_enabled=True, redis_required=required,
                        redis_research_enabled=research)
    monkeypatch.setattr(main, "settings", settings)
    def factory(settings):
        return RedisInfrastructure(settings, fakeredis.aioredis.FakeRedis(server=server, decode_responses=True))
    monkeypatch.setattr(main, "RedisInfrastructure", factory)
    return server


def test_disabled_mode_does_not_construct_a_redis_client(monkeypatch):
    monkeypatch.setattr(main, "settings", Settings(_env_file=None))
    def unexpected(*args):
        pytest.fail("disabled mode constructed infrastructure")
    monkeypatch.setattr(main, "RedisInfrastructure", unexpected)
    with TestClient(main.app) as client:
        assert main.app.state.terminal_relay is None
        assert client.get("/api/v1/health").json()["redis"] == {
            "enabled": False, "required": False, "status": "DISABLED",
            "research_enabled": False, "last_error": None, "last_success_at": None,
        }
        with client.websocket_connect("/ws/terminal") as ws:
            payload = ws.receive_json()
            assert payload["contract_version"] == "phase12-v1"
            assert not any("redis" in field for field in payload)
        assert client.post("/api/v1/simulation/run", json={"frames": 3}).status_code == 200


def test_redis_websocket_relay_and_research_keep_existing_contracts(monkeypatch):
    wire_infrastructure(monkeypatch)
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/terminal") as first:
            first_snapshot = first.receive_json()
            with client.websocket_connect("/ws/terminal") as second:
                second_snapshot = second.receive_json()
                assert first_snapshot["process_id"] == second_snapshot["process_id"]
                assert first_snapshot["session_id"] == second_snapshot["session_id"]
                assert second_snapshot["sequence"] >= first_snapshot["sequence"]
                assert set(first_snapshot) == set(main.app.state.runtime._terminal_latest)
                assert not main.app.state.runtime._terminal_clients
        assert not main.app.state.terminal_relay.local.clients
        config = client.get("/api/v1/strategy").json()
        response = client.post("/api/v1/simulation/run", json={"frames": 3})
        assert response.status_code == 200, response.text
        assert response.json()["simulated"]
        assert client.get("/api/v1/strategy").json() == config


def test_optional_startup_outage_preserves_local_kill_and_rejects_redis_admission(monkeypatch):
    wire_infrastructure(monkeypatch, connected=False)
    with TestClient(main.app) as client:
        assert client.get("/api/v1/health").status_code == 200
        response = client.post("/api/v1/simulation/run", json={"frames": 3})
        assert response.status_code == 503
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect("/ws/terminal"):
                pass
        assert error.value.code == 1013
        assert client.post("/api/v1/risk/kill").status_code == 200
        assert main.app.state.runtime.risk.kill_switch_active
        assert not main.app.state.runtime.strategy.running


def test_required_redis_fails_before_engine_services_start(monkeypatch):
    wire_infrastructure(monkeypatch, connected=False, required=True)
    rt = HyperAmmRuntime(main.settings)
    rt.start_services = AsyncMock()
    monkeypatch.setattr(main, "HyperAmmRuntime", lambda settings: rt)
    with pytest.raises(RuntimeError, match="Required Redis infrastructure"):
        with TestClient(main.app):
            pass
    rt.start_services.assert_not_awaited()
    assert not main.app.state.terminal_relay


def test_health_is_read_only_sanitized_and_reports_recovery(monkeypatch):
    server = wire_infrastructure(monkeypatch, required=True)
    with TestClient(main.app) as client:
        infra = main.app.state.redis_infrastructure
        # Stop background observers so each HTTP response has a deterministic
        # last-operation state. The local DEMO/PAPER runtime remains running.
        client.portal.call(main.app.state.terminal_relay.close)
        health = client.get("/api/v1/health").json()["redis"]
        assert health["status"] == "CONNECTED"
        assert health["enabled"] and health["required"] and health["research_enabled"]
        assert health["last_success_at"] is not None
        server.connected = False
        assert client.post("/api/v1/simulation/run", json={"frames": 3}).status_code == 503
        infra.diagnose(RuntimeError(
            "redis://user:SYNTHETIC_VALUE@localhost:6379 "
            "Authorization: Bearer SYNTHETIC_VALUE"))
        call = infra.call
        with monkeypatch.context() as context:
            context.setattr(infra, "call", AsyncMock(side_effect=AssertionError("health probed Redis")))
            response = client.get("/api/v1/health")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
            assert response.json()["redis"]["status"] == "DEGRADED"
            assert response.json()["redis"]["last_error"]
            assert "SYNTHETIC_VALUE" not in response.text
            infra.call.assert_not_awaited()
        assert client.post("/api/v1/risk/kill").status_code == 200
        assert main.app.state.runtime.risk.kill_switch_active
        server.connected = True
        client.portal.call(call, "ping")
        recovered = client.get("/api/v1/health").json()["redis"]
        assert recovered["status"] == "CONNECTED"
        assert recovered["last_error"] is None
        assert main.app.state.runtime.risk.kill_switch_active
