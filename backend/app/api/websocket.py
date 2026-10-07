import asyncio
from contextlib import suppress
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/terminal")
async def terminal(ws: WebSocket):
    rt = ws.app.state.runtime
    try:
        queue = rt.subscribe_terminal()
    except RuntimeError:
        await ws.close(code=1013, reason="Local terminal client limit reached")
        return
    try:
        await ws.accept()
    except BaseException:
        rt.unsubscribe_terminal(queue)
        raise

    async def stream():
        while True:
            await asyncio.wait_for(ws.send_text(await queue.get()), timeout=5)

    async def disconnect():
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return

    tasks = [asyncio.create_task(stream()), asyncio.create_task(disconnect())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError, TimeoutError):
        return
    finally:
        rt.unsubscribe_terminal(queue)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        with suppress(RuntimeError, WebSocketDisconnect):
            await ws.close()
