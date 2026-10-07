"""Audit 1.0 local research boundary, not operator authentication."""
import ipaddress
import os
import sys
from urllib.parse import urlsplit
from starlette.responses import JSONResponse

BOUNDARY_MESSAGE = "HyperAMM supports local, single-operator, research-only execution. Remote/public and multi-worker deployment are unsupported."


def is_loopback(host):
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_local_deployment():
    for key in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        if key in os.environ and os.environ[key] != "1":
            raise RuntimeError(BOUNDARY_MESSAGE)
    for key in ("UVICORN_HOST",):
        if key in os.environ and not is_loopback(os.environ[key]):
            raise RuntimeError(BOUNDARY_MESSAGE)
    args = sys.argv[1:]
    for index, arg in enumerate(args):
        for flag in ("--host", "--workers", "-w", "--bind", "-b"):
            if arg == flag or arg.startswith(flag + "="):
                value = arg.split("=", 1)[1] if "=" in arg else (args[index + 1] if index + 1 < len(args) else "")
                if flag in ("--workers", "-w"):
                    valid = value == "1"
                else:
                    host = value if flag == "--host" else urlsplit("//" + value).hostname or ""
                    valid = is_loopback(host)
                if not valid:
                    raise RuntimeError(BOUNDARY_MESSAGE)


class LocalOnlyBoundary:
    """Check peer, Host and browser Origin; forwarded headers grant no access.

    Loopback proxies/tunnels remain unsupported. CORS is not authentication.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        peer = scope.get("client")
        headers = dict(scope.get("headers", []))
        try:
            host = urlsplit("//" + headers.get(b"host", b"").decode("latin1")).hostname
            origin = headers.get(b"origin")
            local_origin = origin is None or is_loopback(urlsplit(origin.decode("latin1")).hostname or "")
        except ValueError:
            host, local_origin = None, False
        # Starlette's in-process transport has no network peer.
        test_peer = peer and peer[0] == "testclient"
        local_peer = peer and (is_loopback(peer[0]) or test_peer)
        local_host = host and (is_loopback(host) or (test_peer and host == "testserver"))
        if not (local_peer and local_host and local_origin):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008, "reason": "Local research deployment only"})
            else:
                await JSONResponse({"detail": BOUNDARY_MESSAGE}, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)
