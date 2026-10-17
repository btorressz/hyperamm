"""Optional real Redis acceptance using existing production infrastructure.

Run explicitly with --redis-server. No default pytest or production registration.
"""
import argparse,json,socket,subprocess,tempfile,time
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
import redis
import app.main as main
from app.config import Settings
ROOT=Path(__file__).resolve().parents[2]

def run(args):
    report={'classification':'FAIL','checks':[],'fixture_notice':'Actual local Redis; DEMO/PAPER only; no venue requests'}
    started=time.monotonic();proc=None;original=main.settings
    with tempfile.TemporaryDirectory(prefix='redis155a-',dir=ROOT/'work') as directory:
        log=open(Path(directory)/'redis.log','w')
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        client=redis.Redis(host='127.0.0.1',port=port,decode_responses=True,socket_timeout=1)
        def start():
            p=subprocess.Popen([args.redis_server,'--bind','127.0.0.1','--port',str(port),'--save','','--appendonly','no','--dir',directory],stdout=log,stderr=subprocess.STDOUT)
            for _ in range(100):
                if p.poll() is not None:raise RuntimeError('Redis exited during startup')
                try:
                    if client.ping():return p
                except redis.RedisError:pass
                time.sleep(.05)
            p.terminate();p.wait(timeout=5);raise RuntimeError('Redis startup timeout')
        def passed(name):report['checks'].append(name);print(name,flush=True)
        try:
            proc=start();report['redis_version']=client.info()['redis_version']
            main.settings=Settings(_env_file=None,redis_enabled=True,redis_required=True,redis_research_enabled=True,
                redis_url=f'redis://127.0.0.1:{port}/0',redis_namespace='phase155a-'+uuid4().hex,
                redis_worker_heartbeat_ttl_seconds=10,redis_operation_timeout_seconds=.3)
            with TestClient(main.app) as c:
                rt=main.app.state.runtime;infra=main.app.state.redis_infrastructure;config=rt.config.model_dump(mode='json')
                assert c.get('/api/v1/health').json()['redis']['status']=='CONNECTED'
                passed('Actual Redis startup, PING and application health CONNECTED')
                with c.websocket_connect('/ws/terminal') as a:
                    first=a.receive_json()
                    with c.websocket_connect('/ws/terminal') as b:
                        second=b.receive_json()
                        assert first['process_id']==second['process_id'] and first['session_id']==second['session_id'] and second['sequence']>=first['sequence']
                assert not main.app.state.terminal_relay.local.clients
                passed('Two actual Pub/Sub terminal sockets share identity and release all clients')
                response=c.post('/api/v1/simulation/run',json={'frames':3})
                assert response.status_code==200 and response.json()['simulated'] is True
                assert rt.config.model_dump(mode='json')==config and not rt.strategy.running
                passed('Coordinated actual PAPER worker preserves operational configuration')
                async def resources():
                    key=infra.key('acceptance','cache');await infra.cache(key,'observational')
                    assert await infra.call('get',key)=='observational' and 0<await infra.call('ttl',key)<=30
                    lease=await infra.acquire('research',1);assert lease is not None
                    assert await infra.acquire('research',1) is None
                    assert await infra.call('pttl',lease.key)>0
                    await lease.close();again=await infra.acquire('research',1);assert again is not None;await again.close()
                    keys=await infra.call('keys',infra.key('worker','*'));assert keys
                    ttls=[await infra.call('ttl',key) for key in keys];assert all(t>0 for t in ttls)
                c.portal.call(resources)
                passed('Actual TTL cache, Lua capacity rejection/release and expiring worker heartbeat')
                proc.terminate();proc.wait(timeout=5);proc=None
                assert c.post('/api/v1/simulation/run',json={'frames':3}).status_code==503
                assert c.get('/api/v1/health').json()['redis']['status']=='DEGRADED'
                assert c.post('/api/v1/risk/kill').status_code==200 and rt.risk.kill_switch_active
                passed('Actual Redis outage rejects research, reports DEGRADED and preserves manual kill')
                proc=start();c.portal.call(infra.call,'ping')
                assert c.get('/api/v1/health').json()['redis']['status']=='CONNECTED'
                assert rt.risk.kill_switch_active and not rt.strategy.running and rt.config.model_dump(mode='json')==config
                passed('Actual Redis recovery cannot clear kill or change strategy')
            passed('Application, relay and research lifespan shutdown completes')
            report['classification']='PASS'
        finally:
            main.settings=original
            if proc is not None and proc.poll() is None:proc.terminate();proc.wait(timeout=5)
            client.close();log.close();report['elapsed_seconds']=round(time.monotonic()-started,2)
            path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--redis-server',default='redis-server')
    parser.add_argument('--output',default=str(ROOT/'docs/acceptance/phase155a/redis-results.json'))
    run(parser.parse_args())
