"""Seeded actual runtime authority and structured read-only WS ownership."""
import asyncio
import ast
import copy
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import app.main as main
from app.config import Settings
from app.runtime import HyperAmmRuntime
from app.execution.models import OrderRequest
from app.market_data.mock import MockMarketDataAdapter
from app.api.live_market_streams import live_market_stream
from app.market_data.live_stream_models import LiveMarketStreamEnvelope
from test_phase152_live_streams import streams, create, eventually, FakeClients
from test_phase151_live_markets import Clock
from test_phase14_research_vault import authority
from app.simulation.market_profiles import MARKETS, DEMO_PROFILES

@pytest.mark.parametrize('kill',[False,True])
async def test_all_observation_actions_preserve_seeded_authority(streams,monkeypatch,kill):
    service,sdk,clock=streams;rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(4)
    await rt.market._accept(snap);await rt.refresh_once()
    await rt.paper.submit_orders([OrderRequest(client_order_id='seed-fill',market='ETH',side='BID',price=snap.best_ask,size=D('.1'))])
    await rt.refresh_once();rt.strategy.running=True;await rt._execution_authority()
    async with rt.execution_lock:
        await rt.orders.reconcile_locked(rt.config.market,rt.quotes,rt.config.replace_tolerance_bps,rt.config.size_tolerance)
    rt.accounting_service.reserve(rt.quotes,await rt.execution.get_open_orders())
    if kill:await rt.activate_kill();await rt.refresh_once()
    assert rt.paper.fills.all() and rt.accounting_service.ledger.version>1
    before=authority(rt);identities=(id(rt.market),id(rt.perp_context_service),id(rt.reference_service))
    position=rt.paper.position_base('ETH');anchors=copy.deepcopy(DEMO_PROFILES)
    monkeypatch.setattr(main.app.state,'runtime',rt,raising=False)
    monkeypatch.setattr(main.app.state,'live_market_streams',service,raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://127.0.0.1') as client:
        for m in MARKETS:
            for path in ('stream-status','stream-snapshot','history','references'):
                result=await client.get(f'/api/v1/live-markets/{m}/{path}')
                assert result.status_code==200 and result.json()['market']==m and result.headers['cache-control']=='no-store'
                assert (await client.post(f'/api/v1/live-markets/{m}/{path}')).status_code==405
            queue=service.subscribe(m);LiveMarketStreamEnvelope.model_validate_json(queue.get_nowait());service.unsubscribe(queue)
            sdk.emit(m,'l2Book');sdk.emit(m,'activeAssetCtx')
        assert (await client.get('/api/v1/live-markets/BTC/history?limit=1001')).status_code==422
        assert (await client.get('/api/v1/live-markets/secret-value/history')).status_code==422
        assert (await client.get('/api/v1/markets/BTC')).status_code==404
    await eventually(lambda:service.snapshot('BTC').observation_status=='AVAILABLE')
    service.accept('BTC','activeAssetCtx',{'coin':'ETH','ctx':{}},1,clock())
    sdk.clients[0].broken=True
    await eventually(lambda:service.states['BTC'].generation==2 and service.states['BTC'].context is not None)
    await service.close()
    assert authority(rt)==before and position==rt.paper.position_base('ETH') and DEMO_PROFILES==anchors
    assert identities==(id(rt.market),id(rt.perp_context_service),id(rt.reference_service))


def socket(service,blocked=False):
    incoming=asyncio.Queue();sent=[];sending=asyncio.Event();children=[]
    async def send(wire):
        children.append(asyncio.current_task());sent.append(wire);sending.set()
        if blocked:await asyncio.Event().wait()
    async def receive():children.append(asyncio.current_task());return await incoming.get()
    ws=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(live_market_streams=service)),
        accept=AsyncMock(),close=AsyncMock(),send_text=send,receive=receive)
    return ws,incoming,sent,sending,children

@pytest.mark.parametrize('blocked',[False,True])
async def test_browser_disconnect_joins_sender_and_releases_queue(streams,blocked):
    service,_,_=streams;ws,incoming,sent,sending,children=socket(service,blocked)
    task=asyncio.create_task(live_market_stream(ws,'BTC'));await asyncio.wait_for(sending.wait(),1)
    frame=LiveMarketStreamEnvelope.model_validate_json(sent[0]);assert frame.market=='BTC' and frame.observation_status!='AVAILABLE'
    incoming.put_nowait({'type':'websocket.disconnect'});await asyncio.wait_for(task,1)
    assert not service._subscribers and all(t.done() for t in children);ws.close.assert_not_awaited()

async def test_browser_parent_cancellation_and_overflow(streams):
    service,_,_=streams;ws,_,_,sending,children=socket(service)
    task=asyncio.create_task(live_market_stream(ws,'BTC'));await asyncio.wait_for(sending.wait(),1)
    for _ in range(20):service.publish('BTC')
    await asyncio.wait_for(task,1)
    assert not service._subscribers and all(t.done() for t in children)
    ws,_,_,sending,children=socket(service,True)
    task=asyncio.create_task(live_market_stream(ws,'BTC'));await asyncio.wait_for(sending.wait(),1);task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert not service._subscribers and all(t.done() for t in children)

@pytest.mark.parametrize('market',['DOGE','btc','BTC-PERP'])
async def test_browser_invalid_symbol_does_not_admit(streams,market):
    service,_,_=streams;ws,_,_,_,_=socket(service);await live_market_stream(ws,market)
    assert not service._subscribers;ws.accept.assert_not_awaited();assert ws.close.call_args.kwargs['code']==1008

async def test_browser_disabled_and_capacity_rejected(streams):
    service,_,_=streams;service.enabled=False;ws,_,_,_,_=socket(service)
    await live_market_stream(ws,'BTC');ws.accept.assert_not_awaited()
    assert ws.close.call_args.kwargs['code']==1013
    service.enabled=True;queues=[service.subscribe('BTC') for _ in range(service.max_subscribers)]
    ws,_,_,_,_=socket(service);await live_market_stream(ws,'ETH');ws.accept.assert_not_awaited()
    for q in queues:service.unsubscribe(q)

@pytest.mark.parametrize('enabled',[False,True])
def test_real_fastapi_ws_lifespan_and_restart(monkeypatch,enabled):
    clock=Clock();sdk=FakeClients(clock);created=[]
    settings=Settings(_env_file=None,live_observations_enabled=enabled,live_streams_enabled=enabled)
    monkeypatch.setattr(main,'settings',settings)
    def factory(settings):
        from app.market_data.live_streams import LiveMarketStreamService
        value=LiveMarketStreamService(settings,client_factory=sdk.factory,clock=clock);created.append(value);return value
    monkeypatch.setattr(main,'LiveMarketStreamService',factory)
    for _ in range(2):
        with TestClient(main.app) as client:
            if enabled:
                with client.websocket_connect('/ws/live-markets/BTC') as ws:
                    frame=ws.receive_json();assert frame['market']=='BTC' and frame['contract_version']=='phase152-v1'
                    assert frame['payload']['status']['connection_generation']>=0
            else:
                with pytest.raises(WebSocketDisconnect):
                    with client.websocket_connect('/ws/live-markets/BTC'):pass
            assert main.app.state.runtime.config.market=='ETH'
        assert created[-1]._closed and not created[-1]._subscribers
    assert created[0].instance_id!=created[1].instance_id and all(c.closed for c in sdk.clients)


def test_call_graph_excludes_operational_trading_edges():
    forbidden={'Exchange','HyperAmmRuntime','MarketDataService','ReferenceService','RiskFirewall','ReferenceConsensusPolicy',
        'FinalQuoteAuthorization','OrderManager','AccountingService','signing'}
    paths=['app/market_data/live_streams.py','app/market_data/live_stream_models.py','app/market_data/live_history.py',
        'app/references/live_provider_integrity.py','app/references/live_provider_mappings.py','app/api/live_market_streams.py','app/api/live_markets.py']
    for path in paths:
        for node in ast.walk(ast.parse(Path(path).read_text())):
            if isinstance(node,ast.ImportFrom):assert not forbidden.intersection(x.name for x in node.names)
            if isinstance(node,ast.Attribute):assert node.attr not in {'runtime','update_config','start_strategy','order','cancel_by_cloid',
                'update_leverage','update_isolated_margin','withdraw','transfer','hyperliquid_private_key'}
    paths={p:v for p,v in main.app.openapi()['paths'].items() if '/live-markets/' in p}
    assert len(paths)==6 and all(set(v)=={'get'} for v in paths.values())

async def test_service_shutdown_waits_for_socket_owner_cleanup(streams):
    service,_,_=streams;ws,incoming,_,sending,children=socket(service,True)
    serving=asyncio.create_task(live_market_stream(ws,'BTC'));await asyncio.wait_for(sending.wait(),1)
    closing=asyncio.create_task(service.close());await eventually(lambda:service._closed)
    assert not closing.done() and service._subscribers
    incoming.put_nowait({'type':'websocket.disconnect'})
    await asyncio.wait_for(serving,1);await asyncio.wait_for(closing,1)
    assert not service._subscribers and all(child.done() for child in children)
