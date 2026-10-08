import asyncio
from contextlib import suppress
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.infrastructure.redis import InfrastructureUnavailable

router = APIRouter()


@router.websocket("/ws/terminal")
async def terminal(ws: WebSocket):
    rt = ws.app.state.runtime
    relay = getattr(ws.app.state, "terminal_relay", None)
    lease = None
    try:
        if relay is None:
            queue = rt.subscribe_terminal()
        else:
            queue, lease = await relay.subscribe()
    except (RuntimeError, InfrastructureUnavailable):
        reason = "Local terminal client limit reached" if relay is None else "Terminal admission unavailable or full"
        await ws.close(code=1013, reason=reason)
        return

    def detach():
        if relay is None:
            rt.unsubscribe_terminal(queue)
        else:
            relay.local.unsubscribe(queue)

    async def release():
        detach()
        if lease is not None:
            await lease.close()

    try:
        await ws.accept()
    except BaseException:
        await release()
        raise

    async def stream():
        while True:
            wire = await queue.get()
            if relay is not None:
                try:
                    relay.validate_wire(wire)
                except ValueError:
                    continue
            await asyncio.wait_for(ws.send_text(wire), timeout=5)

    async def disconnect():
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return

    tasks = [asyncio.create_task(stream()), asyncio.create_task(disconnect())]
    if lease is not None:
        tasks.append(asyncio.create_task(lease.lost.wait()))
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError, TimeoutError):
        return
    finally:
        # Detach before any await: cancellation during child-task drain must
        # never leave a local queue registered. Redis capacity also has a TTL.
        detach()
        for task in tasks:
            task.cancel()
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            if lease is not None:
                await lease.close()
        with suppress(RuntimeError, WebSocketDisconnect):
            await ws.close()
