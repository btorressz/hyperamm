"""Actual loopback HTTP/uvicorn configuration acceptance; generated evidence only."""
from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import time
import httpx
import pytest
from app.research_replay.storage import HistoricalStorage
from phase1641_fixtures import admit, dataset
from test_phase162_replay import request_for

BACKEND=Path(__file__).resolve().parents[1]
PREFIX='/api/v1/historical-replay/'

@contextmanager
def local_server(tmp_path, *, root=None, required=False, coordination=False, redis=False, invalid=False):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'MARKET_DATA_MODE':'DEMO','EXECUTION_MODE':'PAPER',
         'ENABLE_HYPERLIQUID_TESTNET_ORDERS':'false','LIVE_STREAMS_ENABLED':'false',
         'LIVE_OBSERVATIONS_ENABLED':'false','REDIS_ENABLED':str(redis).lower(),
         'REDIS_REQUIRED':str(required).lower(),'REDIS_RESEARCH_ENABLED':str(coordination).lower(),
         'REDIS_URL':'redis://127.0.0.1:1/0','REDIS_OPERATION_TIMEOUT_SECONDS':'0.1',
         'WEB_CONCURRENCY':'2' if invalid else '1','UVICORN_WORKERS':'1','UVICORN_HOST':'127.0.0.1'}
    env.pop('HISTORICAL_REPLAY_ROOT',None)
    if root is not None:env['HISTORICAL_REPLAY_ROOT']=str(root)
    with (tmp_path/f'server-{port}.log').open('w') as log:
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],
                              cwd=BACKEND,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=30,trust_env=False) as client:
                deadline=time.monotonic()+20
                while proc.poll() is None and time.monotonic()<deadline:
                    try:
                        if client.get('/api/v1/health').status_code==200:break
                    except httpx.TransportError:pass
                    time.sleep(.05)
                if required or invalid:
                    assert proc.wait(timeout=10)!=0
                    yield None
                else:
                    assert proc.poll() is None
                    assert client.get('/api/v1/health').status_code==200
                    yield client
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    code=proc.wait(timeout=20)
                    # Uvicorn re-raises SIGTERM after completing its lifespan.
                    assert code in (0,-signal.SIGTERM)
                    assert 'Application shutdown complete.' in Path(log.name).read_text()
                except subprocess.TimeoutExpired:
                    proc.kill();proc.wait(timeout=5)
                    pytest.fail('normal local shutdown did not finish')


def test_real_unconfigured_storage_health_and_boundary(tmp_path):
    with local_server(tmp_path) as client:
        assert client.get('/api/v1/health').json()['redis']['status']=='DISABLED'
        for path in ['datasets','dataset-summaries','provenance?dataset_id=missing']:
            assert client.get(PREFIX+path).status_code==503
        for headers in [{'Host':'attacker.invalid'},{'Origin':'https://attacker.invalid'},
                        {'Origin':'http://127.0.0.1:5999'},{'X-Forwarded-For':'127.0.0.1'}]:
            assert client.get('/api/v1/health',headers=headers).status_code==403
        assert client.get('/api/v1/health',headers={'Origin':'http://127.0.0.1:5173'}).status_code==200


def test_real_storage_admission_removal_changed_provenance_and_recovery(tmp_path):
    root=tmp_path/'vault';root.mkdir(mode=0o700)
    vault=HistoricalStorage(root)
    with local_server(tmp_path,root=root) as client:
        assert client.get(PREFIX+'datasets').json()==[]
        assert client.get(PREFIX+'dataset-summaries').json()==[]
        stored=admit(vault,tmp_path/'incoming',dataset())
        request=request_for(stored,max_frames=4).model_dump(mode='json')
        assert client.get(PREFIX+'datasets').json()==[stored.dataset_id]
        assert client.get(PREFIX+'dataset-summaries').json()[0]['dataset_fingerprint']==stored.dataset_fingerprint
        assert client.get(PREFIX+'provenance',params={'dataset_id':stored.dataset_id}).status_code==200
        before=client.get('/api/v1/strategy').json()
        result=client.post(PREFIX+'run',json=request)
        assert result.status_code==200 and result.json()['read_only']
        comparison={'scenario':'QUIET','frames':4,'research_market':'BTC','historical':request,'include_traces':True,'trace_point_limit':4}
        reply=client.post('/api/v1/research-comparison/scenario-historical',json=comparison)
        assert reply.status_code==200,reply.text
        assert reply.json()['receipt']['foundation']['classification']=='CONTEXT_ONLY'
        assert client.get('/api/v1/strategy').json()==before
        changed=deepcopy(request);changed['dataset_fingerprint']='f'*64
        assert client.post(PREFIX+'run',json=changed).status_code==422
        assert client.post(PREFIX+'run',content=b' '*65537,headers={'Content-Type':'application/json'}).status_code==413
        assert client.post(PREFIX+'run',json={**request,'max_frames':5001}).status_code==422
        filename=next(root.glob('*.json'));raw=filename.read_bytes();filename.unlink()
        assert client.get(PREFIX+'dataset-summaries').json()==[]
        assert client.post(PREFIX+'run',json=request).status_code==422
        filename.write_bytes(raw);filename.chmod(0o600);filename.write_bytes(b'{}')
        invalid=client.get(PREFIX+'dataset-summaries')
        assert invalid.status_code==422 and str(root) not in invalid.text
        filename.write_bytes(raw);root.chmod(0o755)
        try:assert client.get(PREFIX+'dataset-summaries').status_code==422
        finally:root.chmod(0o700)
        assert client.post(PREFIX+'run',json=request).status_code==200


@pytest.mark.parametrize('kind',['missing','symlink','inaccessible'])
def test_real_invalid_storage_fails_closed(tmp_path,kind):
    root=tmp_path/'vault'
    if kind!='missing':root.mkdir(mode=0o700)
    if kind=='symlink':
        link=tmp_path/'link';link.symlink_to(root,target_is_directory=True);root=link
    if kind=='inaccessible':root.chmod(0)
    try:
        with local_server(tmp_path,root=root) as client:
            response=client.get(PREFIX+'dataset-summaries')
            assert response.status_code in (422,503) and str(root) not in response.text
    finally:
        if kind=='inaccessible':root.chmod(0o700)


@pytest.mark.parametrize('coordination',[False,True])
def test_real_optional_redis_outage_reports_degraded_and_honors_admission(tmp_path,coordination):
    root=tmp_path/'vault';root.mkdir(mode=0o700)
    with local_server(tmp_path,root=root,redis=True,coordination=coordination) as client:
        health=client.get('/api/v1/health').json()['redis']
        assert health['status']=='DEGRADED' and health['research_enabled']==coordination
        assert client.get(PREFIX+'dataset-summaries').status_code==(503 if coordination else 200)
        assert client.post('/api/v1/simulation/run',json={'frames':3}).status_code==(503 if coordination else 200)


def test_real_required_redis_outage_prevents_startup(tmp_path):
    with local_server(tmp_path,redis=True,required=True,coordination=True):pass


def test_real_unsupported_multiworker_config_prevents_startup(tmp_path):
    with local_server(tmp_path,invalid=True):pass
