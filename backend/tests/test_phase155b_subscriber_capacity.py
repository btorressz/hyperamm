import asyncio
import pytest
from app.market_data.live_streams import BoundedIngress, bounded_callback_wire, MAX_WIRE_BYTES
from app.api.live_market_streams import live_market_stream
from phase155b_helpers import prepared
from test_phase152_runtime_isolation import socket

@pytest.mark.parametrize('raw',[{'x':'x'*(MAX_WIRE_BYTES+1)}, {'x':[None]*9000}, {'x':10**1000}, {'x':float('nan')}, {1:'bad key'}])
def test_adversarial_ingress_is_bounded_before_serialization(raw):
    with pytest.raises(ValueError):bounded_callback_wire(raw)

def test_deep_and_cyclic_payloads_are_bounded():
    raw={};raw['cycle']=raw
    with pytest.raises(ValueError):bounded_callback_wire(raw)

async def test_burst_is_market_fair_and_releases_retired_ingress():
    service,sdk,clock=await prepared(live_stream_queue_capacity=4)
    try:
        inbox=service._inbox
        for _ in range(12):inbox.offer('BTC','activeAssetCtx',1,sdk.ctx('BTC'))
        inbox.offer('ETH','activeAssetCtx',1,sdk.ctx('ETH'))
        inbox.offer('SOL','activeAssetCtx',1,sdk.ctx('SOL'))
        values,losses=inbox.take()
        assert [len(values[m]) for m in ('BTC','ETH','SOL')]==[4,1,1]
        assert losses=={'BTC':8,'ETH':0,'SOL':0}
        inbox.close();inbox.offer('BTC','activeAssetCtx',1,object())
        assert all(not q for q in inbox.queues.values()) and not any(inbox.dropped.values())
    finally:await service.close()

async def test_slow_btc_subscriber_does_not_block_eth_and_sol():
    service,_,_=await prepared()
    queues={m:service.subscribe(m) for m in ('BTC','ETH','SOL')}
    try:
        for q in queues.values():q.get_nowait()
        for _ in range(12):
            for m in queues:service.publish(m)
            for m in ('ETH','SOL'):assert queues[m].get_nowait() is not None
        assert queues['BTC'].get_nowait() is None
        assert len(service._slow_subscribers)==1
    finally:
        for q in queues.values():service.unsubscribe(q)
        await service.close()

@pytest.mark.parametrize('failure',['send','accept','cancel','disconnect'])
async def test_failed_browser_owners_release_subscriber_and_child_tasks(failure):
    service,_,_=await prepared();ws,incoming,_,sending,children=socket(service,blocked=failure=='cancel')
    async def fail(*args):raise RuntimeError('fixture transport failure')
    if failure=='send':ws.send_text=fail
    elif failure=='accept':ws.accept=fail
    serving=asyncio.create_task(live_market_stream(ws,'BTC'))
    try:
        if failure in ('cancel','disconnect'):
            await asyncio.wait_for(sending.wait(),1)
            if failure=='cancel':serving.cancel()
            else:incoming.put_nowait({'type':'websocket.disconnect'})
        if failure=='cancel':
            with pytest.raises(asyncio.CancelledError):await serving
        elif failure in ('send','accept'):
            with pytest.raises((RuntimeError,ExceptionGroup)):await serving
        else:await serving
        assert not service._subscribers and all(t.done() for t in children)
    finally:await service.close()
