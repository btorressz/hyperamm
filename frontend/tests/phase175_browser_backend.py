"""Offline acceptance harness only; real routes, worker and native PAPER engines."""
import asyncio
from fastapi import Request,WebSocket,APIRouter
import app.main as main
from app.api.websocket import terminal
from app.simulation.engine import SimulationEngine
from app.simulation.market_profiles import ResearchMarketCatalog,ResearchPerpMarketMetadata,profile,MARKETS,DEMO_PROFILES

class OfflineCatalog:
    async def catalog(self):return ResearchMarketCatalog(markets=tuple(profile(ResearchPerpMarketMetadata(market=m,
        sz_decimals=DEMO_PROFILES[m][1],metadata_status='DEMO_PROFILE',metadata_source='PINNED_RESEARCH_FIXTURE')) for m in MARKETS))
    async def resolve(self,m):return next(x for x in (await self.catalog()).markets if x.market==m)
    async def close(self):pass
main.HyperliquidMetadataCatalog=lambda **_:OfflineCatalog()
app=main.app
control={'delay':0,'failure':False,'terminal':False,'runs':0}
original_run=SimulationEngine.run
async def controlled(self,**kw):
    control['runs']+=1
    await asyncio.sleep(control['delay'])
    if control['failure']:raise RuntimeError('/private/secret fixture failure')
    return await original_run(self,**kw)
SimulationEngine.run=controlled
router=APIRouter()
@router.websocket('/ws/terminal')
async def socket(ws:WebSocket):
    if control['terminal']:await terminal(ws)
    else:await ws.accept();await ws.close(code=1013)
app.router.routes[0:0]=router.routes
@app.post('/__fixture__/portfolio-control')
async def change(request:Request):
    raw=await request.json()
    for k in ('delay','failure','terminal'):
        if k in raw:control[k]=raw[k]
    return status()
def status():
    rt=app.state.runtime
    return dict(**control,busy=app.state.simulation_executor._busy,authority=dict(
        config=rt.config.model_dump(mode='json'),risk=rt.risk_config.model_dump(mode='json'),kill=rt.risk.kill_switch_active,
        orders=[o.model_dump(mode='json') for o in rt.paper.all_orders()],ledger=rt.accounting_service.ledger.fingerprint,
        signing=rt.testnet.enabled))
@app.get('/__fixture__/portfolio-status')
async def current():return status()
