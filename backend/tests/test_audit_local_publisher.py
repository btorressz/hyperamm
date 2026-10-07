import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.config import Settings
from app.deployment import validate_local_deployment
from app.main import app
from app.runtime import HyperAmmRuntime


@pytest.mark.parametrize("key,value", [("WEB_CONCURRENCY", "2"), ("UVICORN_WORKERS", "4"), ("UVICORN_HOST", "0.0.0.0")])
def test_unsupported_environment(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match="research-only"):
        validate_local_deployment()


@pytest.mark.parametrize("args", [["--workers", "2"], ["--host=0.0.0.0"], ["--bind", "0.0.0.0:8000"], ["-w", "3"]])
def test_unsupported_launch(monkeypatch, args):
    monkeypatch.setattr("sys.argv", ["uvicorn", *args])
    with pytest.raises(RuntimeError):
        validate_local_deployment()


def test_local_reload_and_default_paper(monkeypatch):
    monkeypatch.setattr("sys.argv", ["uvicorn", "--reload", "--host", "127.0.0.1", "--workers=1"])
    validate_local_deployment()
    assert Settings(_env_file=None).execution_mode == "PAPER"
    assert not Settings(_env_file=None).enable_hyperliquid_testnet_orders


@pytest.mark.parametrize("headers", [{"host": "remote.example"}, {"origin": "https://remote.example"}, {"origin": "null"}])
def test_remote_host_origin_http_and_websocket_rejected(headers):
    with TestClient(app) as client:
        assert client.post("/api/v1/strategy/start", headers=headers).status_code == 403
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/terminal", headers=headers):
                pass
        assert exc.value.code == 1008


def test_remote_peer_cannot_use_local_or_forwarded_headers():
    with TestClient(app, base_url="http://localhost", client=("203.0.113.9", 1000)) as client:
        assert client.get("/api/v1/health", headers={"x-forwarded-for": "127.0.0.1"}).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/terminal"):
                pass


@pytest.mark.asyncio
async def test_cached_readers_and_bounded_fanout_do_not_observe():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    assert await rt.terminal_state() is None
    queues = [rt.subscribe_terminal() for _ in range(32)]
    with pytest.raises(RuntimeError):
        rt.subscribe_terminal()
    await rt._publish_terminal_snapshot()
    observed = rt.terminal_service.sequence
    history = rt.terminal_service.history.query()
    events = rt.terminal_service.events()
    rt.terminal_service.observe = Mock(wraps=rt.terminal_service.observe)
    rt.accounting_service.observe_execution_fills = Mock(wraps=rt.accounting_service.observe_execution_fills)
    rt.market.snapshot = AsyncMock(wraps=rt.market.snapshot)
    for queue in queues:
        assert json.loads(queue.get_nowait())["sequence"] == observed
    a = await rt.terminal_state()
    a["sequence"] = -1
    assert (await rt.terminal_state())["sequence"] == observed
    assert rt.terminal_service.history.query() == history
    assert rt.terminal_service.events() == events
    rt.terminal_service.observe.assert_not_called()
    rt.accounting_service.observe_execution_fills.assert_not_called()
    rt.market.snapshot.assert_not_called()
    for _ in range(3):
        await rt._publish_terminal_snapshot()
    latest = await rt.terminal_state()
    for queue in queues:
        assert queue.qsize() == 1
        assert json.loads(queue.get_nowait()) == latest
        rt.unsubscribe_terminal(queue)
    assert not rt._terminal_clients
    assert rt.terminal_service.observe.call_count == 3


def test_two_websockets_share_cached_observation_and_cleanup():
    with TestClient(app) as client:
        rt = app.state.runtime
        with client.websocket_connect("/ws/terminal") as first:
            a = first.receive_json()
            with client.websocket_connect("/ws/terminal") as second:
                b = second.receive_json()
                assert a["sequence"] == b["sequence"]
                assert a["session_id"] == b["session_id"]
                assert a["process_id"] == b["process_id"]
                assert a["contract_version"] == "phase12-v1"
        assert not rt._terminal_clients


@pytest.mark.asyncio
async def test_publisher_runs_without_readers_at_controlled_cadence(monkeypatch):
    rt = HyperAmmRuntime(Settings(_env_file=None))
    rt._publish_terminal_snapshot = AsyncMock()
    sleeps = []

    async def cadence(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            rt._closing = True

    monkeypatch.setattr("app.runtime.asyncio.sleep", cadence)
    await rt._terminal_observer()
    assert rt._publish_terminal_snapshot.await_count == 3
    assert sleeps == [1, 1, 1]


@pytest.mark.asyncio
async def test_slow_socket_send_times_out_and_releases_subscription(monkeypatch):
    from types import SimpleNamespace
    from app.api.websocket import terminal
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt._publish_terminal_snapshot()
    block = asyncio.Event()
    ws = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(runtime=rt)),
        accept=AsyncMock(), close=AsyncMock(),
        send_text=AsyncMock(side_effect=lambda _: block.wait()),
        receive=AsyncMock(side_effect=block.wait),
    )
    # AsyncMock side effects must await the stalled send.
    async def stalled_send(_):
        await block.wait()
    ws.send_text = stalled_send
    real_wait_for = asyncio.wait_for
    budgets = []
    async def short_timeout(awaitable, timeout):
        budgets.append(timeout)
        return await real_wait_for(awaitable, 0.01)
    monkeypatch.setattr("app.api.websocket.asyncio.wait_for", short_timeout)
    await terminal(ws)
    assert budgets == [5]
    assert not rt._terminal_clients
    ws.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_services_cannot_start_a_second_publisher():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt.start_services()
    publisher = rt._terminal_task
    try:
        with pytest.raises(RuntimeError, match="already started"):
            await rt.start_services()
        assert rt._terminal_task is publisher
    finally:
        await rt.stop_services()
    assert publisher.done()
    assert rt._terminal_task is None


def test_local_loopback_request_and_browser_origin_work():
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1000)) as client:
        assert client.get("/api/v1/health", headers={"origin": "http://localhost:5173"}).status_code == 200
        with client.websocket_connect("ws://127.0.0.1/ws/terminal", headers={"origin": "http://localhost:5173"}) as ws:
            assert ws.receive_json()["contract_version"] == "phase12-v1"
