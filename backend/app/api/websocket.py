import asyncio
import sys
import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.infrastructure.redis import InfrastructureUnavailable

router = APIRouter()


@router.websocket("/ws/terminal")
async def terminal(ws: WebSocket):
    """Own all connection operations through one structured cancellation scope."""
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

    transport = rt.terminal_transport if relay is None else relay.local
    peer_disconnected = False
    accepted = False
    try:
        await ws.accept()
        accepted = True

        async with anyio.create_task_group() as operations:
            async def stream():
                nonlocal peer_disconnected
                try:
                    while True:
                        wire = await queue.get()
                        if wire is None:  # Transport shutdown; never a terminal frame.
                            break
                        if relay is not None:
                            try:
                                relay.validate_wire(wire)
                            except ValueError:
                                continue
                        await asyncio.wait_for(ws.send_text(wire), timeout=5)
                except WebSocketDisconnect:
                    peer_disconnected = True
                except TimeoutError:
                    pass  # Existing bounded slow-client termination.
                finally:
                    operations.cancel_scope.cancel()

            async def disconnect():
                nonlocal peer_disconnected
                try:
                    while True:
                        message = await ws.receive()
                        if message["type"] == "websocket.disconnect":
                            peer_disconnected = True
                            return
                finally:
                    operations.cancel_scope.cancel()

            async def lease_loss():
                await lease.lost.wait()
                operations.cancel_scope.cancel()

            operations.start_soon(stream, name="terminal-send")
            operations.start_soon(disconnect, name="terminal-disconnect")
            if lease is not None:
                operations.start_soon(lease_loss, name="terminal-lease-loss")
    finally:
        # The group has joined every child before resources are released. Shield
        # only owned cleanup from AnyIO's repeated (level) cancellation. Parent
        # cancellation still propagates after this bounded scope completes.
        original_error = sys.exception()
        try:
            with anyio.fail_after(6, shield=True):
                try:
                    if lease is not None:
                        await lease.close()
                    if accepted and not peer_disconnected:
                        try:
                            with anyio.fail_after(1):
                                await ws.close()
                        except WebSocketDisconnect:
                            pass
                finally:
                    transport.unsubscribe(queue)
        except Exception as cleanup_error:
            if original_error is not None:
                raise BaseExceptionGroup("WebSocket operation and cleanup failed", [original_error, cleanup_error]) from None
            raise
