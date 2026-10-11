"""Loopback browser fixture server; never imported by the production entrypoint.

Production runtime and terminal remain genuine DEMO/PAPER. Only normalized live
observation responses/streams are injected here; both production switches stay
false, and no venue SDK client or network is constructed by these test routes.
"""
import asyncio
import copy
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from fastapi import APIRouter,Request,WebSocket,WebSocketDisconnect
from app.main import app
from app.api.websocket import terminal
from app.market_data.live_stream_models import LiveStreamSnapshot,LiveMarketStreamEnvelope,LiveMarketHistory
from app.references.live_provider_integrity import LiveProviderHealth,provider_health

ROOT=Path(__file__).resolve().parents[2]
RAW=json.loads((ROOT/'frontend/tests/phase153-fixtures.json').read_text())
BASE=max(datetime.fromisoformat(RAW[m]['envelope']['emitted_at'].replace('Z','+00:00')) for m in RAW)
mode={'kind':'disabled','observer':RAW['BTC']['snapshot']['status']['observer_instance_id'],'generation':1,'terminal_unavailable':False}
clients={};sequence=100
router=APIRouter()

def evidence(m,kind):
    value=copy.deepcopy(RAW[m][kind]);delta=datetime.now(timezone.utc)-BASE-timedelta(milliseconds=100)
    def walk(o):
        for key,v in list(o.items()) if isinstance(o,dict) else enumerate(o):
            if isinstance(v,str) and len(v)>10 and v[4]=='-' and v[10]=='T':o[key]=(datetime.fromisoformat(v.replace('Z','+00:00'))+delta).isoformat().replace('+00:00','Z')
            elif isinstance(v,(dict,list)):walk(v)
    walk(value)
    def identity(o):
        if isinstance(o,dict):
            if 'observer_instance_id' in o:o['observer_instance_id']=mode['observer']
            if 'connection_generation' in o:o['connection_generation']=mode['generation']
            for v in o.values():identity(v)
        elif isinstance(o,list):
            for v in o:identity(v)
    identity(value)
    return value

def snapshot(m):
    if mode['kind']=='disabled':return app.state.live_market_streams.snapshot(m)
    value=evidence(m,'bootstrap' if mode['kind']=='bootstrap' else 'snapshot')
    if mode['kind']=='unavailable':
        value=evidence(m,'disabled');value['status']['connection_state']='UNAVAILABLE';value['observation_status']='UNAVAILABLE'
    if mode['kind']=='stale':
        value['status']['l2_age_seconds']=20;value['status']['l2_freshness']='STALE';value['observation_status']='STALE'
    return LiveStreamSnapshot.model_validate(value)

def frame(m):
    global sequence
    sequence+=1;snap=snapshot(m)
    return LiveMarketStreamEnvelope(market=m,observer_instance_id=snap.status.observer_instance_id,
        connection_generation=snap.status.connection_generation,sequence=sequence,
        emitted_at=datetime.now(timezone.utc),observation_status=snap.observation_status,payload=snap)

@router.get('/api/v1/live-markets/{m}/stream-snapshot')
async def get_snapshot(m:str):return snapshot(m)
@router.get('/api/v1/live-markets/{m}/stream-status')
async def get_status(m:str):return snapshot(m).status
@router.get('/api/v1/live-markets/{m}/history')
async def get_history(m:str,limit:int=100):
    if mode['kind']=='disabled':return app.state.live_market_streams.history.query(m,limit)
    value=evidence(m,'history');value['points']=value['points'][-limit:]
    return LiveMarketHistory.model_validate(value)
@router.get('/api/v1/live-markets/{m}/references')
async def get_providers(m:str):
    if mode['kind'] in ['disabled','unavailable']:return provider_health(snapshot(m))
    return LiveProviderHealth.model_validate(evidence(m,'providers'))

@router.websocket('/ws/live-markets/{m}')
async def live_socket(ws:WebSocket,m:str):
    if m not in RAW or mode['kind'] in ['disabled','unavailable']:await ws.close(code=1013);return
    await ws.accept();clients[ws]=m
    try:
        await ws.send_text(frame(m).model_dump_json())
        while True:await ws.receive_text()
    except (WebSocketDisconnect,RuntimeError):pass
    finally:clients.pop(ws,None)

@router.websocket('/ws/terminal')
async def operational_socket(ws:WebSocket):
    if mode['terminal_unavailable']:await ws.close(code=1013);return
    await terminal(ws)

@router.post('/__fixture__/live-control')
async def control(request:Request):
    change=await request.json();action=change.pop('action',None);market=change.pop('market',None)
    for key in change:
        if key not in mode:raise ValueError('Unsupported test control')
    mode.update(change)
    for ws,m in list(clients.items()):
        if market and market!=m:continue
        try:
            if action=='close':await ws.close(code=1013,reason='Deterministic capacity/overflow fixture');clients.pop(ws,None)
            elif action=='publish':await ws.send_text(frame(m).model_dump_json())
        except (WebSocketDisconnect,RuntimeError):clients.pop(ws,None)
    return {'mode':mode,'clients':list(clients.values())}
@router.get('/__fixture__/clients')
async def client_status():return list(clients.values())

# Test-only overrides precede the production handlers, whose contracts and
# service defaults are untouched. The script owns the loopback Uvicorn process.
app.router.routes[0:0]=router.routes
