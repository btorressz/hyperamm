"""Deterministic connection ownership, cancellation and resource regressions."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import anyio
import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import app.main as main
from app.api.websocket import terminal
from app.config import Settings
from app.infrastructure.redis import RedisInfrastructure
from app.infrastructure.terminal_transport import RedisTerminalTransport
from app.runtime import HyperAmmRuntime
from test_redis_lifespan import wire_infrastructure


def socket(rt, *, relay=None, send=None, accept=None):
    incoming, sent, accepted = asyncio.Queue(), asyncio.Event(), asyncio.Event()
    children = []
    async def transmit(wire):
        children.append(asyncio.current_task())
        sent.set()
        if send:
            await send(wire)
    async def receive():
        children.append(asyncio.current_task())
        return await incoming.get()
    async def admission():
        accepted.set()
        if accept:
            await accept()
    ws = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=rt, terminal_relay=relay)),
                         accept=admission, close=AsyncMock(), send_text=transmit, receive=receive)
    return ws, incoming, sent, accepted, children


@pytest.mark.parametrize('redis', [False, True])
@pytest.mark.parametrize('order', [(0, 1), (1, 0)])
def test_nested_clients_disconnect_in_both_orders(monkeypatch, redis, order):
    if redis:
        wire_infrastructure(monkeypatch)
    with TestClient(main.app) as client:
        rt = main.app.state.runtime
        transport = main.app.state.terminal_relay.local if redis else rt.terminal_transport
        managers = [client.websocket_connect('/ws/terminal') for _ in range(2)]
        sockets = [manager.__enter__() for manager in managers]
        try:
            frames = [ws.receive_json() for ws in sockets]
            assert frames[0]['session_id'] == frames[1]['session_id']
            assert frames[0]['process_id'] == frames[1]['process_id']
            managers[order[0]].__exit__(None, None, None)
            assert len(transport.clients) == 1
            assert sockets[order[1]].receive_json()['contract_version'] == 'phase12-v1'
        finally:
            managers[order[1]].__exit__(None, None, None)
        assert not transport.clients
        if redis:
            infra = main.app.state.redis_infrastructure
            assert client.portal.call(infra.call, 'zcard', infra.key('admission', 'terminal-clients')) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('published', [False, True])
async def test_early_and_blocked_send_disconnect(published):
    rt = HyperAmmRuntime(Settings(_env_file=None))
    send_finished = asyncio.Event()
    async def blocked(_):
        try:
            await asyncio.Event().wait()
        finally:
            send_finished.set()
    ws, incoming, sent, accepted, children = socket(rt, send=blocked)
    if published:
        await rt._publish_terminal_snapshot()
    task = asyncio.create_task(terminal(ws))
    await asyncio.wait_for((sent if published else accepted).wait(), 1)
    incoming.put_nowait({'type': 'websocket.disconnect'})
    await asyncio.wait_for(task, 1)
    assert not rt._terminal_clients
    assert all(child.done() for child in children)
    assert send_finished.is_set() == published
    ws.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_level_cancellation_joins_children_before_releasing_lease():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt._publish_terminal_snapshot()
    drain_started, allow_drain = asyncio.Event(), asyncio.Event()
    lease = SimpleNamespace(lost=asyncio.Event(), close=AsyncMock())
    relay = SimpleNamespace(local=rt.terminal_transport, validate_wire=lambda _: None)
    relay.subscribe = AsyncMock(side_effect=lambda: (rt.subscribe_terminal(), lease))
    async def blocked(_):
        try:
            await asyncio.Event().wait()
        finally:
            with anyio.CancelScope(shield=True):
                drain_started.set()
                await allow_drain.wait()
    ws, _, sent, _, children = socket(rt, relay=relay, send=blocked)
    finished = asyncio.Event()
    scope = anyio.CancelScope()
    async def run():
        with scope:
            await terminal(ws)
        finished.set()
    with anyio.fail_after(2):
        async with anyio.create_task_group() as group:
            group.start_soon(run)
            await sent.wait()
            scope.cancel()
            await drain_started.wait()
            lease.close.assert_not_awaited()
            assert rt._terminal_clients
            allow_drain.set()
            await finished.wait()
    lease.close.assert_awaited_once()
    assert all(child.done() for child in children)
    assert not rt._terminal_clients


@pytest.mark.asyncio
async def test_native_parent_cancellation_is_not_swallowed():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt._publish_terminal_snapshot()
    ws, _, sent, _, children = socket(rt)
    task = asyncio.create_task(terminal(ws))
    await asyncio.wait_for(sent.wait(), 1)
    task.cancel('external shutdown')
    with pytest.raises(asyncio.CancelledError, match='external shutdown'):
        await asyncio.wait_for(task, 1)
    assert not rt._terminal_clients
    assert all(child.done() for child in children)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [RuntimeError('send implementation defect'), ValueError('bad operation')])
async def test_unexpected_send_failure_remains_visible(failure):
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt._publish_terminal_snapshot()
    async def fail(_):
        raise failure
    ws, _, _, _, children = socket(rt, send=fail)
    with pytest.raises(ExceptionGroup) as caught:
        await asyncio.wait_for(terminal(ws), 1)
    assert failure in caught.value.exceptions
    assert not rt._terminal_clients
    assert all(child.done() for child in children)


@pytest.mark.asyncio
async def test_transport_send_disconnect_has_no_duplicate_close():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt._publish_terminal_snapshot()
    async def fail(_):
        raise WebSocketDisconnect(code=1006)
    ws, _, _, _, children = socket(rt, send=fail)
    await asyncio.wait_for(terminal(ws), 1)
    assert not rt._terminal_clients
    assert all(child.done() for child in children)
    ws.close.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('redis', [False, True])
async def test_accept_failure_and_lease_loss_release_once(redis):
    rt = HyperAmmRuntime(Settings(_env_file=None))
    infra = RedisInfrastructure(Settings(_env_file=None, redis_enabled=True), fakeredis.aioredis.FakeRedis())
    relay = RedisTerminalTransport(infra, lambda: (rt.terminal_service.process_id, rt.terminal_service.session_id)) if redis else None
    ws, _, _, _, _ = socket(rt, relay=relay, accept=AsyncMock(side_effect=RuntimeError('accept failed')))
    with pytest.raises(RuntimeError, match='accept failed'):
        await terminal(ws)
    assert not (relay.local.clients if redis else rt._terminal_clients)
    if redis:
        key = infra.key('admission', 'terminal-clients')
        assert await infra.call('zcard', key) == 0
        queue, lease = await relay.subscribe()
        release = lease.close = AsyncMock(wraps=lease.close)
        relay.subscribe = AsyncMock(return_value=(queue, lease))
        lease.lost.set()
        ws, _, _, _, children = socket(rt, relay=relay)
        await asyncio.wait_for(terminal(ws), 1)
        release.assert_awaited_once()
        assert await infra.call('zcard', key) == 0
        assert lease._task is None and all(child.done() for child in children)
        assert not relay.local.clients
        ws.close.assert_awaited_once()
    await infra.client.aclose()


@pytest.mark.asyncio
async def test_concurrent_lease_close_is_idempotent():
    infra = RedisInfrastructure(Settings(_env_file=None, redis_enabled=True), fakeredis.aioredis.FakeRedis())
    lease = (await infra.acquire('terminal-clients', 32)).start()
    call = infra.call = AsyncMock(wraps=infra.call)
    await asyncio.gather(lease.close(), lease.close(), lease.close())
    assert sum(c.args[0] == 'zrem' for c in call.await_args_list) == 1
    assert lease._task is None
    with pytest.raises(RuntimeError):
        lease.start()
    await infra.client.aclose()


@pytest.mark.parametrize('redis', [False, True])
def test_runtime_shutdown_with_client_and_repeated_lifespans(monkeypatch, redis):
    if redis:
        wire_infrastructure(monkeypatch)
    sessions = set()
    for _ in range(3):
        with TestClient(main.app) as client:
            rt = main.app.state.runtime
            publisher, venue = rt._terminal_task, rt._venue_task
            with client.websocket_connect('/ws/terminal') as ws:
                sessions.add(ws.receive_json()['session_id'])
                client.portal.call(rt.stop_services)
                with pytest.raises(WebSocketDisconnect) as closed:
                    ws.receive_json()
                assert closed.value.code == 1000
            assert publisher.done() and venue.done()
            assert not rt._terminal_clients
            with pytest.raises(RuntimeError, match='stopped'):
                rt.subscribe_terminal()
            if redis:
                relay = main.app.state.terminal_relay
                assert not relay.local.clients
        assert rt._terminal_task is None
        if redis:
            assert not relay._tasks
    assert len(sessions) == 3


@pytest.mark.parametrize('kill', [False, True])
def test_connect_disconnect_does_not_mutate_frozen_authority(kill):
    with TestClient(main.app) as client:
        rt = main.app.state.runtime
        async def freeze():
            rt._terminal_task.cancel()
            await asyncio.gather(rt._terminal_task, return_exceptions=True)
            await rt.market.stop()
            await rt.reference_service.stop()
            from app.market_data.mock import MockMarketDataAdapter
            await rt.market._accept(MockMarketDataAdapter().snapshot_for(4))
            await rt.refresh_once()
            assert rt.references is not None and rt.authorization is not None
            rt.strategy.running = True
            await rt._execution_authority()
            async with rt.execution_lock:
                await rt.orders.reconcile_locked(rt.config.market, rt.quotes,
                    rt.config.replace_tolerance_bps, rt.config.size_tolerance)
            assert rt.paper.all_orders()
            if kill:
                await rt.activate_kill()
                await rt.refresh_once()
                assert rt.authorization is None and rt.risk.kill_switch_active
            await rt._publish_terminal_snapshot()
        client.portal.call(freeze)
        def authority():
            return (rt.references.model_dump(), rt.authorization.model_dump() if rt.authorization else None, rt.risk_decision.model_dump(),
                    rt.accounting_service.snapshot().model_dump(), [o.model_dump() for o in rt.paper.all_orders()],
                    rt.risk.kill_switch_active, rt.strategy.running)
        before = authority()
        for _ in range(3):
            with client.websocket_connect('/ws/terminal') as ws:
                assert ws.receive_json()['contract_version'] == 'phase12-v1'
            assert not rt._terminal_clients
            assert authority() == before


@pytest.mark.asyncio
async def test_cancellation_during_accept_releases_real_redis_capacity():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    infra = RedisInfrastructure(Settings(_env_file=None, redis_enabled=True), fakeredis.aioredis.FakeRedis())
    relay = RedisTerminalTransport(infra, lambda: (rt.terminal_service.process_id, rt.terminal_service.session_id))
    entered, finished = asyncio.Event(), asyncio.Event()
    scope = anyio.CancelScope()
    async def blocked_accept():
        entered.set()
        await asyncio.Event().wait()
    ws, _, _, _, _ = socket(rt, relay=relay, accept=blocked_accept)
    async def run():
        with scope:
            await terminal(ws)
        finished.set()
    with anyio.fail_after(2):
        async with anyio.create_task_group() as group:
            group.start_soon(run)
            await entered.wait()
            scope.cancel()
            await finished.wait()
    assert not relay.local.clients
    assert await infra.call('zcard', infra.key('admission', 'terminal-clients')) == 0
    ws.close.assert_not_awaited()
    await infra.client.aclose()


@pytest.mark.asyncio
async def test_redis_relay_duplicate_start_and_identity_replay_rejection():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt._publish_terminal_snapshot()
    infra = RedisInfrastructure(Settings(_env_file=None, redis_enabled=True), fakeredis.aioredis.FakeRedis())
    relay = RedisTerminalTransport(infra, lambda: (rt.terminal_service.process_id, rt.terminal_service.session_id))
    await relay.start()
    workers = tuple(relay._tasks)
    try:
        with pytest.raises(RuntimeError, match='already started'):
            await relay.start()
        assert tuple(relay._tasks) == workers
        assert relay.relay(rt._terminal_wire)
        assert not relay.relay(rt._terminal_wire)
        import json
        for field in ('session_id', 'process_id'):
            wire = json.loads(rt._terminal_wire)
            wire[field] = 'retired-identity'
            with pytest.raises(ValueError, match='identity'):
                relay.relay(json.dumps(wire))
    finally:
        await asyncio.wait_for(relay.close(), 2)
        await infra.client.aclose()
    assert all(task.done() for task in workers) and not relay._tasks


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_mask_original_send_failure():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt._publish_terminal_snapshot()
    original, cleanup = ValueError('send defect'), RuntimeError('close defect')
    async def fail(_):
        raise original
    ws, _, _, _, children = socket(rt, send=fail)
    ws.close.side_effect = cleanup
    with pytest.raises(ExceptionGroup) as caught:
        await asyncio.wait_for(terminal(ws), 1)
    def leaves(error):
        if isinstance(error, ExceptionGroup):
            return [leaf for child in error.exceptions for leaf in leaves(child)]
        return [error]
    assert leaves(caught.value) == [original, cleanup]
    assert not rt._terminal_clients and all(child.done() for child in children)
