import asyncio
from threading import Event
from pathlib import Path

import pytest

from app.infrastructure.research import CoordinatedSimulationExecutor
from app.simulation.executor import SimulationExecutor,ResearchBusyError
from app.simulation.service import SimulationService
from app.simulation.models import stable_fingerprint
from phase174_fixtures import request_for
from test_redis_infrastructure import infrastructure


async def test_one_shared_admission_and_six_engine_calls(monkeypatch):
    from app.simulation.engine import SimulationEngine
    original=SimulationEngine.run;calls=[]
    async def observe(self,**kwargs):
        calls.append(kwargs["dataset"].market)
        return await original(self,**kwargs)
    monkeypatch.setattr(SimulationEngine,"run",observe)
    worker=SimulationExecutor();submit=worker._pool.submit;submissions=[]
    def counted(*args,**kwargs):submissions.append(args[1]);return submit(*args,**kwargs)
    monkeypatch.setattr(worker._pool,"submit",counted)
    try: await worker.execute("stress_portfolio_research",request=request_for())
    finally:await worker.shutdown()
    assert submissions==["stress_portfolio_research"]
    assert calls==["BTC","ETH","SOL","BTC","ETH","SOL"] and not worker._busy


async def test_cancellation_keeps_worker_until_both_legs_finish_and_shutdown_waits(monkeypatch):
    loop=asyncio.get_running_loop();started=asyncio.Event();release=Event();done=Event()
    original=SimulationService._run_portfolio_dataset
    async def held(self,**kwargs):
        loop.call_soon_threadsafe(started.set);assert release.wait(15)
        result=await original(self,**kwargs);done.set();return result
    monkeypatch.setattr(SimulationService,"_run_portfolio_dataset",held)
    worker=SimulationExecutor();closing=None
    first=asyncio.create_task(worker.execute("stress_portfolio_research",request=request_for(markets=("BTC",))))
    try:
        await asyncio.wait_for(started.wait(),10)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):await first
        with pytest.raises(ResearchBusyError):await worker.execute("run_scenario")
        closing=asyncio.create_task(worker.shutdown());await asyncio.sleep(0)
        assert not closing.done() and not done.is_set()
    finally:
        release.set()
        if closing:await asyncio.wait_for(closing,15)
        else:await worker.shutdown()
    assert done.is_set() and not worker._busy
    assert all(not t.is_alive() for t in worker._pool._threads)

@pytest.mark.parametrize("stage",["engine","dataset","accounting"])
async def test_stressed_failure_stops_releases_and_allows_next_job(monkeypatch,stage):
    original=SimulationService._run_portfolio_dataset;calls=[]
    async def broken(self,**kwargs):
        calls.append(kwargs["scenario"].market)
        if calls[-1]=="ETH":
            if stage=="engine":raise RuntimeError("synthetic failure")
            result=await original(self,**kwargs)
            if stage=="dataset": result.result.dataset_fingerprint="f"*64
            else: result.result.vault=None
            return result
        return await original(self,**kwargs)
    monkeypatch.setattr(SimulationService,"_run_portfolio_dataset",broken)
    worker=SimulationExecutor()
    try:
        with pytest.raises((ValueError,RuntimeError)):
            await worker.execute("stress_portfolio_research",request=request_for())
        assert calls==["BTC","ETH"] and not worker._busy
        monkeypatch.setattr(SimulationService,"_run_portfolio_dataset",original)
        assert (await worker.execute("stress_portfolio_research",request=request_for(markets=("BTC",)))).contract_version=="phase174-stress-v1"
    finally:await worker.shutdown()


async def test_redis_one_lease_and_release_after_stressed_leg(infrastructure,monkeypatch):
    infra,_=infrastructure;acquired=[];original=infra.acquire
    async def acquire(*args,**kwargs):acquired.append(args);return await original(*args,**kwargs)
    monkeypatch.setattr(infra,"acquire",acquire)
    worker=CoordinatedSimulationExecutor(SimulationExecutor(),infra,lambda:("p174","session"))
    try:
        await worker.execute("stress_portfolio_research",request=request_for(markets=("BTC",)))
        assert acquired==[("research",1)]
        assert await infra.call("zcard",infra.key("admission","research"))==0
        keys=await infra.call("keys",infra.key("research-result","*"))
        assert len(keys)==1
    finally:await worker.shutdown()


def test_stress_modules_have_no_operational_dependencies():
    root=Path(__file__).parents[1]/"app"/"portfolio_research"
    for name in ("scenarios.py","stress.py","metrics.py"):
        source=(root/name).read_text()
        assert all(s not in source for s in ("HyperAmmRuntime","OrderManager(","SimulationExecutor(","private_key","sign_transaction","submit_order("))
    assert "_run_portfolio_dataset" not in __import__('app.simulation.executor',fromlist=['RESEARCH_OPERATIONS']).RESEARCH_OPERATIONS
