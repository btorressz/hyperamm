"""In-memory Redis integration (including Lua) and engine boundary regressions."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from threading import Event
from unittest.mock import patch

import fakeredis
import fakeredis.aioredis
import pytest

from app.config import Settings
from app.infrastructure.redis import InfrastructureUnavailable, RedisInfrastructure, RENEW
from app.infrastructure.research import CoordinatedSimulationExecutor, ResearchUnavailableError, digest
from app.infrastructure.terminal_transport import RedisTerminalTransport
from app.market_data.mock import MockMarketDataAdapter
from app.runtime import HyperAmmRuntime
from app.simulation.config import SimulationConfig
from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.service import SimulationService


@pytest.fixture
async def infrastructure():
    server = fakeredis.FakeServer()
    client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    infra = RedisInfrastructure(Settings(_env_file=None, redis_enabled=True), client)
    await infra.start()
    yield infra, server
    await client.aclose()


async def observation(infra):
    rt = HyperAmmRuntime(Settings(_env_file=None))
    snapshot = await rt._publish_terminal_snapshot()
    transport = RedisTerminalTransport(infra, lambda: (rt.terminal_service.process_id, rt.terminal_service.session_id))
    return rt, snapshot, transport


async def eventually(predicate):
    async with asyncio.timeout(4):
        while not predicate():
            await asyncio.sleep(.01)


@pytest.mark.asyncio
async def test_pubsub_wire_cache_and_shared_admission(infrastructure):
    infra, _ = infrastructure
    rt, snapshot, transport = await observation(infra)
    await transport.start()
    queue, lease = await transport.subscribe()
    try:
        transport.offer(rt._terminal_wire)
        assert await asyncio.wait_for(queue.get(), 4) == rt._terminal_wire
        assert json.loads(await infra.call("get", transport.cache_key())) == snapshot
        assert 0 < await infra.call("ttl", transport.cache_key()) <= 30
        assert (await rt.terminal_state()) == snapshot
        assert rt.terminal_service.sequence == snapshot["sequence"]
        assert transport._sequence == snapshot["sequence"]
        assert set(json.loads(transport.local.latest)) == set(snapshot)
    finally:
        await transport.unsubscribe(queue, lease)
        await transport.close()
    assert await infra.call("zcard", infra.key("admission", "terminal-clients")) == 0


@pytest.mark.asyncio
async def test_relay_rejects_duplicate_regressed_delayed_wrong_session_and_malformed(infrastructure):
    infra, _ = infrastructure
    rt, snapshot, transport = await observation(infra)
    assert transport.relay(rt._terminal_wire)
    assert not transport.relay(rt._terminal_wire)
    for update in (
        {"sequence": 0},
        {"sequence": snapshot["sequence"] + 1, "emitted_at": (datetime.now(timezone.utc)-timedelta(seconds=6)).isoformat()},
        {"sequence": snapshot["sequence"] + 1, "emitted_at": (datetime.now(timezone.utc)+timedelta(seconds=6)).isoformat()},
        {"process_id": "other-engine"}, {"session_id": "previous-session"},
        {"contract_version": "unknown"}, {"redis": True},
    ):
        try:
            assert not transport.relay(json.dumps({**snapshot, **update}))
        except ValueError:
            pass
    for wire in ('{"sequence": 1}', 'broken', 'x' * 4_000_001):
        with pytest.raises(ValueError):
            transport.relay(wire)
    assert transport.local.latest == rt._terminal_wire
    previous = rt._terminal_wire
    await rt._publish_terminal_snapshot()
    assert transport.relay(rt._terminal_wire)
    assert not transport.relay(previous)
    regressed = json.loads(rt._terminal_wire)
    regressed["sequence"] += 1
    regressed["emitted_at"] = (transport._emitted_at - timedelta(milliseconds=1)).isoformat()
    assert not transport.relay(json.dumps(regressed))
    # A session reset still advances the engine-owned process-wide sequence.
    rt.terminal_service._context = None
    await rt._publish_terminal_snapshot()
    assert rt.terminal_service.session_id != snapshot["session_id"]
    assert transport.relay(rt._terminal_wire)
    with pytest.raises(ValueError, match="identity"):
        transport.relay(json.dumps(snapshot))


@pytest.mark.asyncio
async def test_stale_cache_and_memory_are_not_relayed(infrastructure):
    infra, _ = infrastructure
    rt, snapshot, transport = await observation(infra)
    await infra.cache(transport.cache_key(), rt._terminal_wire)
    transport.clock = lambda: datetime.fromisoformat(snapshot["emitted_at"]) + timedelta(seconds=6)
    transport.local.latest = rt._terminal_wire
    await transport.start()
    queue, lease = await transport.subscribe()
    try:
        await asyncio.sleep(.05)
        assert queue.empty()
        assert transport.local.latest is None
        assert transport._sequence == 0
    finally:
        await transport.unsubscribe(queue, lease)
        await transport.close()


@pytest.mark.asyncio
async def test_publisher_and_subscriber_reconnect_without_redating(infrastructure):
    infra, server = infrastructure
    rt, snapshot, transport = await observation(infra)
    await transport.start()
    queue, lease = await transport.subscribe()
    try:
        transport.offer(rt._terminal_wire)
        await asyncio.wait_for(queue.get(), 4)
        server.connected = False
        await rt._publish_terminal_snapshot()
        transport.offer(rt._terminal_wire)
        await eventually(lambda: infra.last_error is not None)
        # Let the subscription read fail as well as the publishing connection.
        await asyncio.sleep(1.1)
        server.connected = True
        expected = rt._terminal_wire
        assert await asyncio.wait_for(queue.get(), 4) == expected
        assert json.loads(expected)["emitted_at"] == (await rt.terminal_state())["emitted_at"]
        assert json.loads(expected)["sequence"] > snapshot["sequence"]
    finally:
        server.connected = True
        await transport.unsubscribe(queue, lease)
        await transport.close()


@pytest.mark.asyncio
async def test_cache_ttl_heartbeat_expiry_and_abandoned_capacity(infrastructure):
    infra, _ = infrastructure
    with patch("time.time", return_value=1000):
        await infra.cache(infra.key("test-cache", "process", "session"), "value")
        await infra.heartbeat("process")
        leases = await asyncio.gather(*(infra.acquire("terminal-clients", 32) for _ in range(33)))
        assert sum(x is not None for x in leases) == 32
        assert await infra.acquire("research", 1) is not None
        assert await infra.acquire("research", 1) is None
    with patch("time.time", return_value=1016):
        assert await infra.call("get", infra.key("worker", "process", infra.worker_id)) is None
        assert await infra.acquire("terminal-clients", 32) is not None
        assert await infra.acquire("research", 1) is not None
        assert await infra.call("get", infra.key("test-cache", "process", "session")) == "value"
    with patch("time.time", return_value=1031):
        assert await infra.call("get", infra.key("test-cache", "process", "session")) is None


@pytest.mark.asyncio
async def test_lease_renewal_failure_and_expiry_cannot_resurrect(infrastructure):
    infra, server = infrastructure
    with patch("time.time", return_value=2000):
        expired = await infra.acquire("terminal-clients", 32)
    with patch("time.time", return_value=2016):
        assert await infra.call("eval", RENEW, 1, expired.key, expired.token, 15000) == 0
    lease = await infra.acquire("research", 1)
    server.connected = False
    lease.ttl = .03
    lease.start()
    try:
        await asyncio.wait_for(lease.lost.wait(), 1)
    finally:
        server.connected = True
        await lease.close()


@pytest.mark.asyncio
async def test_optional_startup_failure_required_failure_and_sanitized_credentials(caplog):
    for required in (False, True):
        server = fakeredis.FakeServer()
        server.connected = False
        client = fakeredis.aioredis.FakeRedis(server=server)
        infra = RedisInfrastructure(Settings(_env_file=None, redis_enabled=True, redis_required=required,
            redis_url="rediss://user:password@host:6379/0"), client)
        if required:
            with pytest.raises(RuntimeError, match="Required Redis"):
                await infra.start()
        else:
            await infra.start()
        with pytest.raises(InfrastructureUnavailable):
            await infra.acquire("terminal-clients", 32)
        infra.diagnose(RuntimeError("rediss://user:password@host:6379/0 authorization=Bearer password token=password"))
        assert "password" not in infra.last_error
        assert "user:password" not in caplog.text
        assert "password" not in repr(infra.settings)
        await client.aclose()


@pytest.mark.asyncio
async def test_redis_failure_and_observations_cannot_replace_engine_authority(infrastructure):
    infra, server = infrastructure
    rt, _, transport = await observation(infra)
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(2))
    await rt.refresh_once()
    rt.strategy.running = True
    await rt._publish_terminal_snapshot()
    def authority():
        return (rt.config.model_dump(), rt.accounting_service.ledger.fingerprint,
                rt.accounting_service.position.model_dump(), rt.authorization.model_dump(),
                rt.market_history.version, rt.agent_telemetry.version)
    before = authority()
    malicious = json.loads(rt._terminal_wire)
    malicious["risk"]["kill_switch_active"] = False
    malicious["risk_authorization"]["authorized"] = True
    malicious["accounting"]["position"] = {"position_base": "999999"}
    malicious["strategy"]["config"]["levels_per_side"] = 1
    assert transport.relay(json.dumps(malicious))
    assert authority() == before
    rt.authorization = None
    server.connected = False
    rt.terminal_distribution = transport
    await rt._publish_terminal_snapshot()
    with pytest.raises(PermissionError, match="FinalQuoteAuthorization"):
        await rt._execution_authority()
    with pytest.raises(PermissionError, match="FinalQuoteAuthorization"):
        await rt.orders.reconcile("ETH", rt.quotes, Decimal("0"), Decimal("0"))
    assert not await rt.paper.get_open_orders()
    await rt.activate_kill()
    assert rt.risk.kill_switch_active
    assert not rt.strategy.running
    server.connected = True
    await rt._publish_terminal_snapshot()
    wire = json.loads(rt._terminal_wire)
    wire["risk"]["kill_switch_active"] = False
    wire["risk_authorization"]["authorized"] = True
    assert transport.relay(json.dumps(wire))
    assert rt.risk.kill_switch_active
    assert not await rt.paper.get_open_orders()


@pytest.mark.asyncio
async def test_research_status_result_identity_and_live_input_isolation(infrastructure):
    infra, _ = infrastructure
    rt = HyperAmmRuntime(Settings(_env_file=None))
    executor = CoordinatedSimulationExecutor(SimulationExecutor(), infra, lambda: ("process", "session"))
    before = (rt.config.model_dump(), rt.agent_config.model_dump(), rt.risk_config.model_dump())
    inputs = dict(scenario="QUIET", frames=3, strategy=rt.config, agents=rt.agent_config,
                  risk=rt.risk_config, simulation=SimulationConfig(max_frames=3))
    try:
        result = await executor.execute("run_scenario", **inputs)
        assert result.simulated
        keys = await infra.call("keys", infra.key("research-job", "process", "session", "*"))
        status = json.loads(await infra.call("get", keys[0]))
        assert status["status"] == "COMPLETED"
        assert len(status["job_id"]) == 32
        assert status["engine_version"] in status["result_key"]
        assert status["request_fingerprint"] in status["result_key"]
        assert "process:session" in status["result_key"]
        mirrored = json.loads(await infra.call("get", status["result_key"]))
        assert mirrored["result"] == result.model_dump(mode="json")
        assert result.dataset_fingerprint in json.dumps(mirrored)
        for key in (*keys, status["result_key"]):
            assert 0 < await infra.call("ttl", key) <= 30
        assert before == (rt.config.model_dump(), rt.agent_config.model_dump(), rt.risk_config.model_dump())
        assert digest(inputs) != digest({**inputs, "scenario": "TREND_UP"})
        assert digest(inputs) != digest({**inputs, "strategy": rt.config.model_copy(update={"levels_per_side": 1})})
    finally:
        await executor.shutdown()


@pytest.mark.asyncio
async def test_cancelled_request_retains_shared_slot_until_real_completion(infrastructure, monkeypatch):
    infra, server = infrastructure
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = Event()
    async def held(self, **inputs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5)
        return {"research": "done"}
    monkeypatch.setattr(SimulationService, "optimize", held)
    executor = CoordinatedSimulationExecutor(SimulationExecutor(), infra, lambda: ("p", "s"))
    first = asyncio.create_task(executor.execute("optimize"))
    try:
        await asyncio.wait_for(started.wait(), 4)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        with pytest.raises(ResearchBusyError):
            await executor.execute("optimize")
        server.connected = False
        with pytest.raises(ResearchUnavailableError):
            await executor.execute("optimize")
    finally:
        server.connected = True
        release.set()
        await executor.shutdown()
    assert await infra.acquire("research", 1) is not None


def test_disabled_mode_and_required_mode_validation():
    settings = Settings(_env_file=None)
    assert not settings.redis_enabled
    assert not settings.redis_research_enabled
    with pytest.raises(ValueError, match="require redis_enabled"):
        Settings(_env_file=None, redis_required=True)
    with pytest.raises(ValueError, match="Redis URL"):
        Settings(_env_file=None, redis_enabled=True, redis_url="https://example.com")
    with pytest.raises(ValueError):
        Settings(_env_file=None, redis_namespace="unbounded:key")
