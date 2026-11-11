"""Local test harness only. Production routes, importer, storage, engine and PAPER."""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from fastapi import APIRouter, Request, WebSocket
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend/tests'))
import app.main as main
from app.api.websocket import terminal
from app.simulation.engine import SimulationEngine
from app.simulation.market_profiles import ResearchMarketCatalog, ResearchPerpMarketMetadata, profile, MARKETS
from app.research_replay.storage import HistoricalStorage
from phase1641_fixtures import admit, dataset

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(os.environ.get('PHASE1641_FIXTURE_ROOT',str(ROOT/'work/browser1641')));WORK.mkdir(parents=True,exist_ok=True)
mode={'delay':0,'terminal':False,'runs':0,'provenance_delay':0}
class OfflineCatalog:
    async def catalog(self):
        return ResearchMarketCatalog(markets=tuple(profile(ResearchPerpMarketMetadata(market=m,
            sz_decimals={'BTC':5,'ETH':4,'SOL':2}[m],metadata_status='DEMO_PROFILE',metadata_source='PINNED_RESEARCH_FIXTURE')) for m in MARKETS))
    async def resolve(self,m):return next(x for x in (await self.catalog()).markets if x.market==m)
    async def close(self):pass
main.HyperliquidMetadataCatalog=lambda **_:OfflineCatalog()
app=main.app;original=app.router.lifespan_context;run_engine=SimulationEngine.run
async def delayed_engine(self,**kwargs):
    mode['runs']+=1
    await asyncio.sleep(mode['delay'])
    return await run_engine(self,**kwargs)
SimulationEngine.run=delayed_engine

@asynccontextmanager
async def lifespan(application):
    for name in ('vault','empty'):(WORK/name).mkdir(mode=0o700,exist_ok=True)
    vault=HistoricalStorage(WORK/'vault')
    for m in MARKETS:
        for kind in ('complete','gap','generation','missing','crossing'):
            if f'{m}-{kind}-fixture' not in vault.list_ids():admit(vault,WORK/'incoming',dataset(kind,m))
    if os.environ.get('PHASE165D_LARGE_FIXTURES') == '1':
        from phase165d_fixtures import bounded_dataset
        generated = bounded_dataset(1000)
        if generated.dataset_id not in vault.list_ids():admit(vault,WORK/'incoming',generated)
    async with original(application):
        application.state.historical_replay_root=str(WORK/'vault')
        yield
app.router.lifespan_context=lifespan
router=APIRouter()
@router.websocket('/ws/terminal')
async def socket(ws:WebSocket):
    if not mode['terminal']:await ws.close(code=1013);return
    await terminal(ws)
app.router.routes[0:0]=router.routes

@app.middleware('http')
async def delayed_provenance(request,call_next):
    if request.url.path.endswith('/historical-replay/provenance'):await asyncio.sleep(mode['provenance_delay'])
    return await call_next(request)

@app.post('/__fixture__/replay-control')
async def control(request:Request):
    change=await request.json()
    for k in ('delay','terminal','provenance_delay'):
        if k in change:mode[k]=change[k]
    if 'fixture_reference_firewall' in change:
        # Explicit test setup, never a browser/product request or public API.
        rt=app.state.runtime
        rt.risk_config=rt.risk_config.model_copy(update={'enabled':change['fixture_reference_firewall']})
    if 'storage' in change:
        app.state.historical_replay_root=None if change['storage']=='disabled' else str(WORK/change['storage'])
    return status()

def status():
    rt=app.state.runtime
    return dict(**mode,busy=app.state.simulation_executor._busy,
        authority=dict(config=rt.config.model_dump(mode='json'),risk=rt.risk_config.model_dump(mode='json'),
            kill=rt.risk.kill_switch_active,orders=[o.model_dump(mode='json') for o in rt.paper.all_orders()],
            inventory=rt.inventory.snapshot().model_dump(mode='json') if hasattr(rt.inventory,'snapshot') else None,
            ledger=rt.accounting_service.ledger.fingerprint,testnet=rt.testnet.enabled),
        subscriptions=len(app.state.live_market_streams._subscribers))
@app.get('/__fixture__/replay-status')
async def fixture_status():return status()
