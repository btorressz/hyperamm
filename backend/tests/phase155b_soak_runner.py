"""Bounded OFFLINE public-SDK traffic soak; never opens a venue connection.

From backend: python tests/phase155b_soak_runner.py --seconds 30 --max-cycles 100
"""
import argparse
import asyncio
import json
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from phase155b_helpers import until
from test_phase152_live_streams import create
from test_phase151_live_markets import book
from app.simulation.market_profiles import MARKETS

async def run_soak(seconds=3, max_cycles=10):
    if not .1 <= seconds <= 300 or not 1 <= max_cycles <= 1000:
        raise ValueError('soak bounds: seconds 0.1..300, cycles 1..1000')
    started=time.monotonic();service,sdk,clock=create(live_stream_queue_capacity=8,live_stream_history_max_points=32)
    cycles=max_queue=0;retired_attempts=0;queues=[]
    report={'classification':'FAIL','evidence':'OFFLINE FAKE SDK — NOT VENUE DELIVERY',
        'requested_seconds':seconds,'max_cycles':max_cycles}
    try:
        await service.start();await until(lambda:all(s.context is not None for s in service.states.values()))
        while cycles<max_cycles and time.monotonic()-started<seconds:
            queues=[service.subscribe(m) for m in MARKETS]
            for q in queues:q.get_nowait()
            old=sdk.clients[-1];previous={m:service.states[m].dropped for m in MARKETS}
            for i in range(service.queue_capacity+3):
                clock.advance(.001)
                for m in MARKETS:
                    raw=book(m);raw['time']=int(clock().timestamp()*1000);sdk.books[m]=raw
                    sdk.emit(m,'l2Book')
                    max_queue=max(max_queue,len(service._inbox.queues[m]))
            await until(lambda:all(service.states[m].dropped>=previous[m]+3 for m in MARKETS))
            for m in MARKETS:
                sdk.emit(m,'activeAssetCtx');sdk.emit(m,'l2Book')
            await until(lambda:all(s.context is not None for s in service.states.values()))
            # Rejected malformed input retains valid evidence, and freshness
            # expires from source time without adding polling history.
            for m in MARKETS:
                before=service.states[m].context
                service.accept(m,'activeAssetCtx',{'coin':'OTHER','ctx':{}},service.states[m].generation,clock())
                assert service.states[m].context==before
            clock.advance(11)
            assert all(service.snapshot(m).status.l2_freshness=='STALE' for m in MARKETS)
            for _ in range(10):service.publish('BTC')
            assert queues[0].get_nowait() is None
            for q in queues:service.unsubscribe(q)
            queues=[]
            for m in MARKETS:sdk.books[m]['time']=int(clock().timestamp()*1000)
            old.broken=True;service._inbox.event.set()
            await until(lambda:sdk.clients[-1] is not old and all(s.context is not None for s in service.states.values()))
            assert old.closed
            before={m:service.snapshot(m) for m in MARKETS}
            for m in MARKETS:
                sdk.emit(m,'activeAssetCtx',client=old);retired_attempts+=1
            assert all(service.snapshot(m)==before[m] for m in MARKETS)
            assert sum(not c.closed for c in sdk.clients)==1
            cycles+=1
            # Yield on an explicit event-loop timer; this is workload pacing,
            # never a timing-based test assertion.
            await asyncio.sleep(min(.05,max(0,seconds-(time.monotonic()-started))))
        report.update(cycles_completed=cycles,maximum_observed_queue_size=max_queue,
            dropped_events=sum(s.dropped for s in service.states.values()),
            rejected_events=sum(s.rejected for s in service.states.values()),
            retired_callback_attempts=retired_attempts,history_retained={m:service.history.query(m).retained_point_count for m in MARKETS},
            history_gaps={m:service.history.query(m).gap_count for m in MARKETS})
    finally:
        for q in queues:service.unsubscribe(q)
        await service.close()
        report.update(duration_seconds=round(time.monotonic()-started,4),subscriber_count_after_shutdown=len(service._subscribers),
            remaining_owned_threads=sum(t.is_alive() for t in service._pool._threads),
            remaining_owned_tasks=sum(t is not None and not t.done() for t in (service._runner,service._close_task)),
            leaked_or_uncertain_sdk_resources=sum(not c.closed for c in sdk.clients),
            sdk_connections_created=len(sdk.clients))
    assert report['maximum_observed_queue_size']<=service.queue_capacity
    assert all(report[k]==0 for k in ('subscriber_count_after_shutdown','remaining_owned_threads','remaining_owned_tasks','leaked_or_uncertain_sdk_resources'))
    assert cycles>0
    report['classification']='PASS'
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=30);p.add_argument('--max-cycles',type=int,default=100)
    p.add_argument('--output',type=Path);args=p.parse_args()
    result=asyncio.run(run_soak(args.seconds,args.max_cycles));wire=json.dumps(result,indent=2)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(wire+'\n')
    print(wire)
