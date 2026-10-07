import asyncio
from threading import Event

import pytest

from app.simulation.executor import ResearchBusyError, SimulationExecutor
from app.simulation.service import SimulationService


@pytest.mark.asyncio
async def test_request_cancellation_retains_slot_and_shutdown_waits_for_worker(monkeypatch):
    loop=asyncio.get_running_loop()
    started=asyncio.Event()
    finished=Event()
    release=Event()
    async def held(self,**inputs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        finished.set()
        return "done"
    monkeypatch.setattr(SimulationService,"optimize",held)
    executor=SimulationExecutor()
    first=asyncio.create_task(executor.execute("optimize"))
    shutdown=None
    try:
        await asyncio.wait_for(started.wait(),5)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        with pytest.raises(ResearchBusyError,match="already running"):
            await executor.execute("optimize")
        shutdown=asyncio.create_task(executor.shutdown())
        # Synchronize on shutdown admission closure without CPU timing claims.
        await asyncio.sleep(0)
        with pytest.raises(ResearchBusyError,match="shutting down"):
            await executor.execute("run_scenario")
        assert not shutdown.done()
        assert not finished.is_set()
    finally:
        release.set()
        if shutdown is not None:
            await asyncio.wait_for(shutdown,5)
        else:
            await executor.shutdown()
    assert finished.is_set()
    assert not executor._busy
    assert all(not thread.is_alive() for thread in executor._pool._threads)


@pytest.mark.asyncio
async def test_submit_failure_releases_admission(monkeypatch):
    executor=SimulationExecutor()
    original=executor._pool.submit
    def broken(*args,**kwargs):
        raise RuntimeError("submit failed")
    monkeypatch.setattr(executor._pool,"submit",broken)
    try:
        with pytest.raises(RuntimeError,match="submit failed"):
            await executor.execute("optimize")
        assert not executor._busy
        monkeypatch.setattr(executor._pool,"submit",original)
        async def succeed(self,**inputs):
            return "recovered"
        monkeypatch.setattr(SimulationService,"optimize",succeed)
        assert await executor.execute("optimize")=="recovered"
    finally:
        await executor.shutdown()
