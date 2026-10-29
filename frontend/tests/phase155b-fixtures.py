"""Generate integration fixtures through the real backend observation contracts."""
import asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from phase155b_helpers import prepared
from app.references.live_provider_integrity import provider_health
from test_phase151_live_markets import book

async def main():
    service,sdk,clock=await prepared();result={}
    try:
        for m in ('BTC','ETH','SOL'):
            service.accept(m,'l2Book',book(m),1,clock())
            service.accept(m,'activeAssetCtx',sdk.ctx(m),1,clock())
            active=service._envelope(m)
            raw=sdk.ctx(m);raw['channel']='trades'
            service.accept(m,'activeAssetCtx',raw,1,clock())
            degraded=service._envelope(m)
            result[m]={'active':active.model_dump(mode='json'),'degraded':degraded.model_dump(mode='json'),
                'health':provider_health(service.snapshot(m)).model_dump(mode='json'),
                'history':service.history.query(m).model_dump(mode='json')}
    finally:await service.close()
    Path(__file__).with_name('phase155b-fixtures.json').write_text(json.dumps(result,indent=2)+'\n')
asyncio.run(main())
