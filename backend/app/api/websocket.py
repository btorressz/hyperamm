import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
router=APIRouter()

@router.websocket("/ws/terminal")
async def terminal(ws: WebSocket):
    await ws.accept(); rt=ws.app.state.runtime
    try:
        while True:
            await ws.send_json(await rt.terminal_state())
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
