"""Opt-in genuine public SDK acceptance. Never imported/executed by pytest.

python tests/phase155b_live_readonly_acceptance.py --allow-public-network \
    --seconds 20 --reconnect --output ../docs/acceptance/phase155b/external-results.json

Run only where venue/network policy permits public Hyperliquid access. A denial
stops the attempt; this runner never changes routes, proxies, TLS or security.
"""
import argparse
import asyncio
import importlib.metadata
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.market_data.hyperliquid_metadata import load_sdk_metadata,validate_native_metadata
from app.market_data.live_streams import SDKObservationClient,LiveMarketStreamService
from app.market_data.live_observations import classify,normalize_book,normalize_context
from app.market_data.live_models import LiveMarketMetadata
from app.references.live_provider_integrity import provider_health
from app.simulation.market_profiles import MARKETS

async def run(seconds, reconnect):
    report={'classification':'FAIL','evidence':'GENUINE PUBLIC READ-ONLY SDK ATTEMPT',
        'execution_platform':platform.platform(),'python':platform.python_version(),
        'sdk_version':importlib.metadata.version('hyperliquid-python-sdk'),
        'started_at':datetime.now(timezone.utc).isoformat(),'authority':'NONE','read_only':True,
        'independent_source_groups':['HYPERLIQUID'],'trading_readiness':'NOT APPLICABLE',
        'checks':{'sdk_import':'PASS'},'observations':{},'subscriptions':[]}
    started=time.monotonic();service=None;clients=[]
    try:
        # One metadata attempt before starting retries or opening a WS. A denied
        # destination ends external acceptance immediately.
        metadata=validate_native_metadata(await asyncio.to_thread(load_sdk_metadata),datetime.now(timezone.utc))
        assert all(m.metadata_status=='EXCHANGE_VERIFIED' for m in metadata)
        report['checks']['native_metadata']='PASS'
        report['metadata']=[m.model_dump(mode='json') for m in metadata]
        class RecordingClient(SDKObservationClient):
            def open(self):
                result=super().open();self.native=result;return result
            def subscribe(self,m,k,callback):
                result=super().subscribe(m,k,callback)
                report['subscriptions'].append({'connection':len(clients),'market':m,'channel':k})
                return result
            def book(self,m):
                raw,received=super().book(m)
                item=next(x for x in validate_native_metadata(self.native[0],self.native[1]) if x.market==m)
                meta=LiveMarketMetadata(market=m,metadata_status=item.metadata_status,source='OFFICIAL_SDK_NATIVE_META',
                    listed=item.listed,asset_index=item.asset_index,sz_decimals=item.sz_decimals,observed_at=self.native[1])
                normalize_book(raw,meta,received,future_tolerance=1,max_levels=20)
                report['checks'][f'{m}_l2_rest']='PASS';return raw,received
            def context(self):
                raw,received=super().context()
                for item in validate_native_metadata(self.native[0],self.native[1]):
                    meta=LiveMarketMetadata(market=item.market,metadata_status=item.metadata_status,source='OFFICIAL_SDK_NATIVE_META',
                        listed=item.listed,asset_index=item.asset_index,sz_decimals=item.sz_decimals,observed_at=self.native[1])
                    normalize_context(raw,meta,received)
                report['checks']['perpetual_context_rest']='PASS';return raw,received
        def factory(*args):
            client=RecordingClient(*args);clients.append(client);return client
        settings=Settings(_env_file=None,market_data_mode='DEMO',execution_mode='PAPER',
            live_observations_enabled=True,live_streams_enabled=True,enable_hyperliquid_testnet_orders=False)
        service=LiveMarketStreamService(settings,client_factory=factory)
        await service.start();deadline=time.monotonic()+seconds;disconnected=False
        while time.monotonic()<deadline:
            for market in MARKETS:
                snap=service.snapshot(market);state=service.states[market]
                if state.seen=={'l2Book','activeAssetCtx'} and snap.order_book and snap.perp_context:
                    report['observations'][market]={'snapshot':snap.model_dump(mode='json'),
                        'provider_health':provider_health(snap).model_dump(mode='json')}
                    report['checks'][f'{market}_validated_ws_delivery']='PASS'
            if all(m in report['observations'] for m in MARKETS):
                if reconnect and not disconnected:
                    report['initial_generation']=service._generation
                    # Controlled public socket disconnect; normal owner retires
                    # subscriptions, joins resources and creates the replacement.
                    await service._call(service._client.info.ws_manager.ws.close)
                    disconnected=True
                elif not reconnect or service._generation>report['initial_generation'] and all(
                    s.seen=={'l2Book','activeAssetCtx'} for s in service.states.values()):
                    report['checks']['controlled_reconnect']='PASS' if reconnect else 'NOT RUN'
                    report['classification']='PASS';break
            if any(s.error in {'FORBIDDEN','CLEANUP_ERROR'} for s in service.states.values()):
                report['classification']='BLOCKED';break
            await asyncio.sleep(.05)
        if report['classification']=='FAIL':report['failure']='No complete accepted native delivery within the bounded window.'
    except Exception as exc:
        report.update(classification='BLOCKED',error_type=type(exc).__name__,error_code=classify(exc))
        report['sanitized_failure']='Configured proxy CONNECT returned 403 Forbidden.' if '403 Forbidden' in str(exc) else 'Public SDK access or evidence validation failed; no alternate route attempted.'
        report['checks'].setdefault('native_metadata','BLOCKED')
    finally:
        if service:
            try:
                await service.close();report['checks']['sdk_cleanup']='PASS'
                report['post_shutdown_status']={m:service.snapshot(m).status.model_dump(mode='json') for m in MARKETS}
                report['remaining_owned_threads']=sum(t.is_alive() for t in service._pool._threads)
                report['remaining_owned_tasks']=sum(not t.done() for t in (service._runner,service._close_task) if t)
                report['subscriber_count_after_shutdown']=len(service._subscribers)
            except Exception:
                report['checks']['sdk_cleanup']='FAIL';report['classification']='FAIL'
        else:report['checks']['sdk_cleanup']='NOT APPLICABLE'
        report['duration_seconds']=round(time.monotonic()-started,3)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--allow-public-network',action='store_true',required=True)
    p.add_argument('--seconds',type=float,default=20);p.add_argument('--reconnect',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args()
    if not 5<=args.seconds<=120:p.error('--seconds must be 5..120')
    result=asyncio.run(run(args.seconds,args.reconnect));wire=json.dumps(result,indent=2)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(wire+'\n')
    print(wire);sys.exit(0 if result['classification']=='PASS' else 2)
