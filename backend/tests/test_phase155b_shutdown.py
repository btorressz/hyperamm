import asyncio
import threading
import pytest
from phase155b_helpers import until
from test_phase152_live_streams import create

async def test_runner_cancellation_during_open_keeps_worker_owned_and_drains_pool():
    service,sdk,_=create();sdk.open_gate=threading.Event()
    try:
        await service.start();assert await asyncio.to_thread(sdk.started.wait,1)
        service._runner.cancel()
        closing=asyncio.create_task(service.close())
        await until(lambda:service._closed)
        assert not closing.done() and not sdk.clients[0].closed
        sdk.open_gate.set();await asyncio.wait_for(closing,2)
        assert sdk.clients[0].closed and all(not t.is_alive() for t in service._pool._threads)
        await service.close()
    finally:
        sdk.open_gate.set();await service.close()

async def test_cancelled_shutdown_reader_does_not_cancel_retained_cleanup():
    service,sdk,_=create();sdk.close_gate=threading.Event()
    await service.start();await until(lambda:all(s.context is not None for s in service.states.values()))
    closing=asyncio.create_task(service.close());await until(lambda:service._close_task is not None)
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):await closing
    assert not service._close_task.cancelled()
    sdk.close_gate.set();await service.close()
    assert not service._subscribers and all(c.closed for c in sdk.clients)

async def test_shutdown_interrupts_backoff_without_replacement():
    service,sdk,_=create();service.retry_initial=30;sdk.error=ConnectionRefusedError('fixture')
    await service.start();await until(lambda:sdk.clients and sdk.clients[0].closed)
    await asyncio.wait_for(service.close(),1)
    assert len(sdk.clients)==1 and service._runner.done() and service._close_task.done()

@pytest.mark.parametrize('cycle',range(3))
async def test_fresh_start_stop_releases_all_owned_workers(cycle):
    service,sdk,_=create();await service.start()
    await until(lambda:all(s.context is not None for s in service.states.values()))
    await asyncio.gather(service.close(),service.close())
    assert all(c.closed for c in sdk.clients) and all(not t.is_alive() for t in service._pool._threads)
    with pytest.raises(RuntimeError):await service.start()
