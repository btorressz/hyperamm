"""Actual PAPER authority and bounded worker cancellation, without venue calls."""
import asyncio
from decimal import Decimal as D
from threading import Event
import httpx
import pytest
from app.main import app
from app.config import Settings
from app.runtime import HyperAmmRuntime
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.live_streams import LiveMarketStreamService
from app.execution.models import OrderRequest
from app.simulation.executor import SimulationExecutor
from app.simulation.service import SimulationService
from test_phase14_research_vault import authority
from phase154_helpers import request


async def seeded(kill):
    rt=HyperAmmRuntime(Settings(_env_file=None));snapshot=MockMarketDataAdapter().snapshot_for(4)
    await rt.market._accept(snapshot);await rt.refresh_once()
    await rt.paper.submit_orders([OrderRequest(client_order_id='155a-seed',market='ETH',side='BID',price=snapshot.best_ask,size=D('.1'))])
    await rt.refresh_once();rt.strategy.running=True;await rt._execution_authority()
    async with rt.execution_lock:await rt.orders.reconcile_locked(rt.config.market,rt.quotes,rt.config.replace_tolerance_bps,rt.config.size_tolerance)
    rt.accounting_service.reserve(rt.quotes,await rt.execution.get_open_orders())
    if kill:await rt.activate_kill();await rt.refresh_once()
    await rt._publish_terminal_snapshot()
    assert rt.paper.fills.all() and rt.accounting_service.ledger.version>1
    return rt


@pytest.mark.parametrize('kill',[False,True])
async def test_read_only_gets_and_research_rejections_preserve_seeded_economic_authority(monkeypatch,kill):
    rt=await seeded(kill);before=authority(rt)
    service=LiveMarketStreamService(Settings(_env_file=None),client_factory=lambda *a:pytest.fail('comparison started SDK networking'))
    monkeypatch.setattr(app.state,'runtime',rt,raising=False);monkeypatch.setattr(app.state,'live_market_streams',service,raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as c:
        for path in ['/strategy','/risk','/risk/authorization','/accounting/pnl','/accounting/ledger','/orders','/positions','/agents','/terminal/history']:
            result=await c.get('/api/v1'+path)
            assert result.status_code==200,(path,result.text)
        for market in ['BTC','ETH','SOL']:
            data=request(market,market=market).model_dump(mode='json')
            assert (await c.post('/api/v1/research-market-comparison/compare',json=data)).status_code==200
            for injection in ['orders','strategy','risk','kill_switch','accounting','capital','execution_mode']:
                bad={**data,injection:{'enabled':True}}
                assert (await c.post('/api/v1/research-market-comparison/compare',json=bad)).status_code==422
        assert authority(rt)==before
    await service.close()


async def test_cancelled_http_research_keeps_capacity_until_actual_completion_and_comparison_stays_read_only(monkeypatch):
    rt=await seeded(True);before=authority(rt);loop=asyncio.get_running_loop();started=asyncio.Event();release=Event()
    original=SimulationService.run_scenario
    async def held(self,**inputs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(10)
        return await original(self,**inputs)
    monkeypatch.setattr(SimulationService,'run_scenario',held)
    worker=SimulationExecutor();service=LiveMarketStreamService(Settings(_env_file=None),client_factory=lambda *a:pytest.fail('SDK activation'))
    monkeypatch.setattr(app.state,'runtime',rt,raising=False);monkeypatch.setattr(app.state,'simulation_executor',worker,raising=False)
    monkeypatch.setattr(app.state,'live_market_streams',service,raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as c:
        first=asyncio.create_task(c.post('/api/v1/simulation/run',json={'frames':3}))
        try:
            await asyncio.wait_for(started.wait(),5);first.cancel()
            with pytest.raises(asyncio.CancelledError):await first
            blocked=await c.post('/api/v1/simulation/run',json={'frames':3})
            assert blocked.status_code==429
            assert (await c.post('/api/v1/research-market-comparison/compare',json=request().model_dump(mode='json'))).status_code==200
            assert authority(rt)==before and worker._busy
        finally:
            release.set();await worker.shutdown();await service.close()
    assert not worker._busy and authority(rt)==before
    assert all(not t.is_alive() for t in worker._pool._threads)
