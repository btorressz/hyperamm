"""Produce deterministic Pydantic-serialized evidence without external networking."""
import asyncio
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from test_phase152_live_streams import create,eventually
from app.references.live_provider_integrity import provider_health
from app.market_data.live_streams import LiveMarketStreamService
from app.config import Settings

async def evidence():
    service,sdk,clock=create()
    sdk.books['SOL']['levels'][0][0].update(px='150.12',sz='1.23')
    sdk.books['SOL']['levels'][1][0].update(px='150.13',sz='2.34')
    await service.start()
    try:
        await eventually(lambda:all(s.context is not None and s.barrier for s in service.states.values()))
        bootstrap={m:service.snapshot(m).model_dump(mode='json') for m in ['BTC','ETH','SOL']}
        # Distinct actual accepted fixture observations populate both time bases.
        for i in range(4):
            clock.advance(.25)
            for m in ['BTC','ETH','SOL']:
                sdk.books[m]['time']=int(clock().timestamp()*1000)
                sdk.emit(m,'l2Book')
                index=next(i for i,x in enumerate(sdk.metadata['universe']) if x['name']==m)
                sdk.contexts[1][index]['funding']=str(-.0001-i*.00001)
                sdk.emit(m,'activeAssetCtx')
            await asyncio.sleep(.02)
        await eventually(lambda:service.snapshot('BTC').observation_status=='AVAILABLE')
        result={m:{'snapshot':service.snapshot(m).model_dump(mode='json'),
            'envelope':service._envelope(m).model_dump(mode='json'),
            'history':service.history.query(m,1000).model_dump(mode='json'),
            'providers':provider_health(service.snapshot(m)).model_dump(mode='json'),
            'bootstrap':bootstrap[m]} for m in ['BTC','ETH','SOL']}
        disabled=LiveMarketStreamService(Settings(_env_file=None),clock=clock)
        try:
            for m in result:result[m]['disabled']=disabled.snapshot(m).model_dump(mode='json')
        finally:await disabled.close()
        return result
    finally:await service.close()

if __name__=='__main__':
    print(json.dumps(asyncio.run(evidence()),indent=2))
