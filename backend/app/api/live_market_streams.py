"""Separate read-only browser stream; one service-owned SDK connection."""
import asyncio
import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.simulation.market_profiles import MARKETS

router = APIRouter()


@router.websocket('/ws/live-markets/{market}')
async def live_market_stream(ws: WebSocket, market: str):
    if market not in MARKETS:
        await ws.close(code=1008, reason='Unsupported live market')
        return
    service = ws.app.state.live_market_streams
    try:
        queue = service.subscribe(market)
    except RuntimeError:
        await ws.close(code=1013, reason='Live observation unavailable or at capacity')
        return
    disconnected = False
    accepted = False
    try:
        await ws.accept()
        accepted = True
        async with anyio.create_task_group() as group:
            async def send():
                nonlocal disconnected
                try:
                    while True:
                        wire = await queue.get()
                        if wire is None:
                            return
                        await asyncio.wait_for(ws.send_text(wire), timeout=5)
                except WebSocketDisconnect:
                    disconnected = True
                except TimeoutError:
                    pass
                finally:
                    group.cancel_scope.cancel()

            async def receive():
                nonlocal disconnected
                try:
                    while True:
                        message = await ws.receive()
                        if message['type'] == 'websocket.disconnect':
                            disconnected = True
                            return
                finally:
                    group.cancel_scope.cancel()
            group.start_soon(send)
            group.start_soon(receive)
    finally:
        service.unsubscribe(queue)
        if accepted and not disconnected:
            with anyio.move_on_after(1, shield=True):
                try:
                    await ws.close(code=1013, reason='Stream ended; reconnect for a current snapshot')
                except WebSocketDisconnect:
                    pass
