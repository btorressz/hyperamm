import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/terminal")
async def terminal(ws: WebSocket):
    await ws.accept()
    rt = ws.app.state.runtime

    async def stream():
        while True:
            await ws.send_json(await rt.terminal_state())
            await asyncio.sleep(1)

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
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
