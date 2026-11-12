import asyncio
from threading import Event

import pytest

from app.infrastructure.research import CoordinatedSimulationExecutor, ResearchUnavailableError
from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.service import SimulationService
from phase172_fixtures import request_for
from test_redis_infrastructure import infrastructure

COMPETITORS = ("run_portfolio_research", "run_scenario", "optimize", "replay_history",
               "compare_scenario_historical", "compare_research_configs")


@pytest.mark.parametrize("competitor", COMPETITORS)
async def test_portfolio_holds_one_admission_against_every_research_operation(monkeypatch, competitor):
    loop = asyncio.get_running_loop()
    started, release = asyncio.Event(), Event()
    calls = []
    original = SimulationService.run_scenario
    async def held(self, **kwargs):
        calls.append(kwargs["strategy"].market)
        if len(calls) == 2:
            loop.call_soon_threadsafe(started.set)
            assert release.wait(10)
        return await original(self, **kwargs)
    monkeypatch.setattr(SimulationService, "run_scenario", held)
    worker = SimulationExecutor()
    submit = worker._pool.submit
    submissions = []
    def counted(*args, **kwargs):
        submissions.append(args[1])
        return submit(*args, **kwargs)
    monkeypatch.setattr(worker._pool, "submit", counted)
    first = asyncio.create_task(worker.execute("run_portfolio_research", request=request_for()))
    try:
        await asyncio.wait_for(started.wait(), 5)
        with pytest.raises(ResearchBusyError):
            await worker.execute(competitor)
        assert calls == ["BTC", "ETH"]
    finally:
        release.set()
        result = await first
        await worker.shutdown()
    assert calls == ["BTC", "ETH", "SOL"]
    assert submissions == ["run_portfolio_research"]
    assert result.status == "COMPLETED" and not worker._busy


@pytest.mark.parametrize("active", COMPETITORS[1:])
async def test_existing_operations_prevent_portfolio_admission(monkeypatch, active):
    loop = asyncio.get_running_loop()
    started, release = asyncio.Event(), Event()
    async def held(self, **kwargs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
    monkeypatch.setattr(SimulationService, active, held)
    worker = SimulationExecutor()
    first = asyncio.create_task(worker.execute(active))
    try:
        await asyncio.wait_for(started.wait(), 5)
        with pytest.raises(ResearchBusyError):
            await worker.execute("run_portfolio_research", request=request_for())
    finally:
        release.set()
        await first
        await worker.shutdown()


async def test_cancelled_portfolio_continues_and_shutdown_waits_for_actual_completion(monkeypatch):
    loop = asyncio.get_running_loop()
    started, release, completed = asyncio.Event(), Event(), Event()
    original = SimulationService.run_scenario
    markets = []
    async def held(self, **kwargs):
        markets.append(kwargs["strategy"].market)
        if len(markets) == 1:
            loop.call_soon_threadsafe(started.set)
            assert release.wait(10)
        value = await original(self, **kwargs)
        if len(markets) == 3: completed.set()
        return value
    monkeypatch.setattr(SimulationService, "run_scenario", held)
    worker = SimulationExecutor()
    first = asyncio.create_task(worker.execute("run_portfolio_research", request=request_for()))
    closing = None
    try:
        await asyncio.wait_for(started.wait(), 5)
        first.cancel()
        with pytest.raises(asyncio.CancelledError): await first
        with pytest.raises(ResearchBusyError): await worker.execute("run_scenario")
        closing = asyncio.create_task(worker.shutdown())
        await asyncio.sleep(0)
        assert not closing.done() and not completed.is_set()
        with pytest.raises(ResearchBusyError): await worker.execute("run_portfolio_research", request=request_for())
    finally:
        release.set()
        if closing: await asyncio.wait_for(closing, 5)
        else: await worker.shutdown()
    assert completed.is_set() and markets == ["BTC", "ETH", "SOL"]
    assert not worker._busy and all(not t.is_alive() for t in worker._pool._threads)


async def test_mid_market_failure_stops_and_releases_without_automatic_retry(monkeypatch):
    original = SimulationService.run_scenario
    markets = []
    async def broken(self, **kwargs):
        markets.append(kwargs["strategy"].market)
        if markets[-1] == "ETH": raise RuntimeError("synthetic failure")
        return await original(self, **kwargs)
    monkeypatch.setattr(SimulationService, "run_scenario", broken)
    worker = SimulationExecutor()
    try:
        with pytest.raises(RuntimeError): await worker.execute("run_portfolio_research", request=request_for())
        assert markets == ["BTC", "ETH"] and not worker._busy
        monkeypatch.setattr(SimulationService, "run_scenario", original)
        assert (await worker.execute("run_portfolio_research", request=request_for())).status == "COMPLETED"
    finally:
        await worker.shutdown()


async def test_redis_one_lease_bounded_result_mirror_and_unavailable_gate(infrastructure):
    infra, server = infrastructure
    worker = CoordinatedSimulationExecutor(SimulationExecutor(), infra, lambda: ("phase172", "session"))
    acquisitions = []
    original = infra.acquire
    async def acquire(*args, **kwargs):
        acquisitions.append(args)
        return await original(*args, **kwargs)
    infra.acquire = acquire
    try:
        result = await worker.execute("run_portfolio_research", request=request_for())
        assert acquisitions == [("research", 1)]
        assert result.status == "COMPLETED"
        assert await infra.call("zcard", infra.key("admission", "research")) == 0
        keys = await infra.call("keys", infra.key("research-result", "*"))
        assert len(keys) == 1
        assert len(await infra.call("get", keys[0])) < 200000
        server.connected = False
        with pytest.raises(ResearchUnavailableError):
            await worker.execute("run_portfolio_research", request=request_for())
    finally:
        server.connected = True
        await worker.shutdown()


async def test_cancelled_coordinated_portfolio_retains_lease_until_all_markets_finish(infrastructure, monkeypatch):
    infra, _ = infrastructure
    loop = asyncio.get_running_loop()
    started, release = asyncio.Event(), Event()
    original = SimulationService.run_scenario
    markets = []
    async def held(self, **kwargs):
        markets.append(kwargs["strategy"].market)
        if len(markets) == 2:
            loop.call_soon_threadsafe(started.set)
            assert release.wait(10)
        return await original(self, **kwargs)
    monkeypatch.setattr(SimulationService, "run_scenario", held)
    worker = CoordinatedSimulationExecutor(SimulationExecutor(), infra, lambda: ("p172", "s"))
    first = asyncio.create_task(worker.execute("run_portfolio_research", request=request_for()))
    try:
        await asyncio.wait_for(started.wait(), 5)
        first.cancel()
        with pytest.raises(asyncio.CancelledError): await first
        assert await infra.call("zcard", infra.key("admission", "research")) == 1
        with pytest.raises(ResearchBusyError): await worker.execute("optimize")
    finally:
        release.set()
        await worker.shutdown()
    assert markets == ["BTC", "ETH", "SOL"]
    assert await infra.call("zcard", infra.key("admission", "research")) == 0
