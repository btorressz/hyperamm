"""Test-only real production stream service fed by deterministic SDK callbacks."""
import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime,timezone
from pathlib import Path
from fastapi import Request
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend/tests'))
import app.main as main
from app.config import Settings
from app.market_data.live_streams import LiveMarketStreamService
from app.simulation.market_profiles import ResearchMarketCatalog,ResearchPerpMarketMetadata,profile,MARKETS
from test_phase151_live_markets import Clock
from test_phase152_live_streams import FakeClients

clock=Clock();clock.now=datetime.now(timezone.utc);sdk=FakeClients(clock)
for raw in sdk.books.values():raw['time']=int(clock().timestamp()*1000)
mode={'kind':'active'}
class OfflineCatalog:
    async def catalog(self):
        return ResearchMarketCatalog(markets=tuple(profile(ResearchPerpMarketMetadata(market=m,
            sz_decimals={'BTC':5,'ETH':4,'SOL':2}[m],metadata_status='DEMO_PROFILE',metadata_source='PINNED_RESEARCH_FIXTURE')) for m in MARKETS))
    async def resolve(self,m):return next(x for x in (await self.catalog()).markets if x.market==m)
    async def close(self):pass
main.HyperliquidMetadataCatalog=lambda **_:OfflineCatalog()
main.LiveMarketStreamService=lambda _:LiveMarketStreamService(Settings(_env_file=None,
    live_observations_enabled=True,live_streams_enabled=True,live_stream_reconnect_initial_seconds=.5,
    live_stream_reconnect_max_seconds=1),client_factory=sdk.factory,clock=clock)
app=main.app;original=app.router.lifespan_context

@asynccontextmanager
async def lifespan(application):
    async with original(application):
        async def pump():
            while True:
                clock.now=datetime.now(timezone.utc)
                if sdk.clients:
                    client=sdk.clients[-1]
                    for m in MARKETS:
                        sdk.books[m]['time']=int(clock().timestamp()*1000)
                        if mode['kind']=='degraded' and m=='BTC' or mode['kind']=='paused':continue
                        for k in ('l2Book','activeAssetCtx'):
                            if (m,k) in client.callbacks and not client.closed:sdk.emit(m,k,client=client)
                await asyncio.sleep(.2)
        task=asyncio.create_task(pump(),name='155b-fixture-pump')
        try:yield
        finally:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
app.router.lifespan_context=lifespan

@app.post('/__fixture__/phase155b')
async def control(request:Request):
    change=await request.json();service=app.state.live_market_streams
    kind=change.get('kind','active');mode['kind']=kind
    if kind=='reconnect':
        mode['kind']='active';sdk.clients[-1].broken=True;service._inbox.event.set()
    elif kind=='degraded':
        raw=sdk.ctx('BTC');raw['channel']='trades'
        service.accept('BTC','activeAssetCtx',raw,service.states['BTC'].generation,clock())
    return {'kind':mode['kind'],'generation':service._generation}

@app.get('/__fixture__/phase155b-resources')
async def resources():
    service=app.state.live_market_streams
    return {'subscribers':len(service._subscribers),'generation':service._generation,
        'sdk_clients':len(sdk.clients),'active_sdk_clients':sum(not c.closed for c in sdk.clients),
        'retired_clients_closed':all(c.closed for c in sdk.clients[:-1])}
