"""Official SDK ownership guards and bounded teardown without venue access."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.market_data.live_streams import SDKObservationClient
from test_phase151_live_markets import NOW, native
from phase155b_helpers import until
from test_phase152_live_streams import create

@pytest.mark.parametrize('market,kind',[('DOGE','l2Book'),('BTC','trades'),('xyz:ETH','activeAssetCtx')])
def test_subscription_scope_is_enforced_before_sdk(market,kind):
    client=SDKObservationClient(1,1);client.info=SimpleNamespace(subscribe=Mock())
    with pytest.raises(ValueError):client.subscribe(market,kind,lambda _:None)
    client.info.subscribe.assert_not_called()

def test_duplicate_subscription_and_owner_open_are_rejected():
    client=SDKObservationClient(1,1);client.info=SimpleNamespace(subscribe=Mock(return_value=1))
    client.subscribe('BTC','l2Book',lambda _:None)
    with pytest.raises(RuntimeError):client.subscribe('BTC','l2Book',lambda _:None)
    with pytest.raises(RuntimeError):client.open()
    assert client.info.subscribe.call_count==1

@pytest.mark.parametrize('stuck',[False,True])
def test_cleanup_joins_are_bounded_and_uncertain_owner_retained(stuck):
    client=SDKObservationClient(1,.01)
    threads=[SimpleNamespace(ident=1,join=Mock(),is_alive=lambda:stuck) for _ in range(2)]
    manager,ping=threads
    manager.ping_sender=ping;manager.stop_event=SimpleNamespace(set=Mock());manager.ws=SimpleNamespace(close=Mock())
    info=SimpleNamespace(ws_manager=manager,session=SimpleNamespace(close=Mock()),disconnect_websocket=Mock(side_effect=AssertionError('unbounded stop')))
    client.info=info
    if stuck:
        with pytest.raises(RuntimeError,match='cleanup incomplete'):client.close()
        assert client.info is info
    else:
        client.close();client.close();assert client.info is None
    for thread in threads:thread.join.assert_called_once_with(timeout=.01)
    manager.stop_event.set.assert_called_once();info.disconnect_websocket.assert_not_called()
    info.session.close.assert_called_once()

async def test_failure_after_partial_subscription_retires_before_replacement():
    service,sdk,_=create();base=sdk.factory
    def factory(*args):
        client=base(*args);subscribe=client.subscribe
        def partial(m,k,cb):
            if len(sdk.clients)==1 and len(client.handles)==3:raise ConnectionError('private subscription failure')
            return subscribe(m,k,cb)
        client.subscribe=partial;return client
    service._factory=factory
    try:
        await service.start();await until(lambda:len(sdk.clients)>1 and all(s.barrier for s in service.states.values()))
        assert sdk.clients[0].closed and len(sdk.clients[0].handles)==3
        assert len(sdk.clients[1].handles)==6 and len(set(sdk.clients[1].handles))==6
    finally:await service.close()
