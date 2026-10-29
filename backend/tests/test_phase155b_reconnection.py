import asyncio
import copy
import pytest
from phase155b_helpers import prepared,until
from test_phase152_live_streams import create
from app.simulation.market_profiles import MARKETS

@pytest.mark.parametrize('failure',['refused','metadata_timeout','bootstrap_context'])
async def test_reconnection_failures_recover_with_one_owned_client(failure):
    service,sdk,_=create()
    if failure=='refused':sdk.error=ConnectionRefusedError('fixture')
    elif failure=='metadata_timeout':sdk.error=TimeoutError('fixture')
    else:sdk.context_error=TimeoutError('fixture')
    try:
        await service.start()
        if failure=='bootstrap_context':
            await until(lambda:all(s.book is not None for s in service.states.values()))
            for market in MARKETS:sdk.emit(market,'l2Book');sdk.emit(market,'activeAssetCtx')
        else:
            await until(lambda:sdk.clients and sdk.clients[0].closed);sdk.error=None
        await until(lambda:all(s.book is not None and s.context is not None for s in service.states.values()))
        assert sum(not c.closed for c in sdk.clients)==1
    finally:await service.close()

async def test_failed_bootstrap_keeps_barrier_closed_even_with_retained_evidence():
    service,sdk,_=await prepared()
    class Broken:
        def book(self,market):raise TimeoutError('fixture')
        def close(self):pass
    service._client=Broken()
    try:
        before=service.states['BTC'].book
        with pytest.raises(TimeoutError):await service._bootstrap_book('BTC')
        assert not service.states['BTC'].barrier and service.states['BTC'].book==before
    finally:await service.close()

async def test_one_market_rest_recovery_failure_does_not_retire_other_markets():
    service,sdk,_=create();base=sdk.factory
    def factory(*args):
        client=base(*args);fetch=client.book
        def partial(m):
            if m=='BTC':raise TimeoutError('fixture')
            return fetch(m)
        client.book=partial;return client
    service._factory=factory
    try:
        await service.start();await until(lambda:service.states['SOL'].context is not None)
        for m in ('ETH','SOL'):sdk.emit(m,'l2Book');sdk.emit(m,'activeAssetCtx')
        await until(lambda:all(service.snapshot(m).observation_status=='AVAILABLE' for m in ('ETH','SOL')))
        assert len(sdk.clients)==1 and not service.states['BTC'].barrier
    finally:await service.close()

async def test_changed_metadata_revalidated_before_resubscription():
    service,sdk,_=create()
    try:
        await service.start();await until(lambda:all(s.context is not None for s in service.states.values()))
        sdk.metadata['universe'][1]['isDelisted']=True
        old=sdk.clients[0];old.broken=True
        await until(lambda:len(sdk.clients)==2 and service.states['SOL'].error=='NOT_LISTED')
        assert old.closed and all(m!='SOL' for m,_ in sdk.clients[1].handles)
        assert service.snapshot('SOL').order_book is None
    finally:await service.close()
