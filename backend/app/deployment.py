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


DEFAULT_BROWSER_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173", "http://[::1]:5173")


def parse_authority(value):
    """Parse an HTTP Host without forgiving userinfo, paths or ambiguous syntax."""
    if not value or any(ord(c) <= 32 or ord(c) >= 127 for c in value) or any(c in value for c in "@/\\?#%"):
        raise ValueError("invalid local authority")
    parsed = urlsplit("//" + value)
    port = parsed.port  # Validate the complete port, including range and syntax.
    if not parsed.hostname or parsed.netloc != value or value.endswith(":") or port == 0:
        raise ValueError("invalid local authority")
    return parsed.hostname.lower(), port


def parse_origin(value):
    """A serialized browser origin has only scheme, host and optional port."""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("invalid browser origin")
    host, port = parse_authority(parsed.netloc)
    # Require exact serialized-origin structure (no empty query/fragment suffix).
    if value != f"{parsed.scheme}://{parsed.netloc}":
        raise ValueError("invalid browser origin")
    return parsed.scheme, host, port or (443 if parsed.scheme == "https" else 80)


class LocalOnlyBoundary:
    """Loopback peer/Host and exact browser origins; no forwarding trust.

    This is the existing local single-operator boundary, not authentication.
    """
    def __init__(self, app, allowed_origins=DEFAULT_BROWSER_ORIGINS):
        self.app = app
        self.allowed_origins = frozenset(parse_origin(o) for o in allowed_origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        peer = scope.get("client")
        pairs = [(k.lower(), v) for k, v in scope.get("headers", [])]
        headers = dict(pairs)
        try:
            # Duplicate security headers must not be resolved differently by layers.
            if any(sum(k == name for k, _ in pairs) > 1 for name in (b"host", b"origin", b"sec-fetch-site")):
                raise ValueError("duplicate boundary header")
            if any(k == b"forwarded" or k.startswith(b"x-forwarded-") or k == b"x-real-ip" for k, _ in pairs):
                raise ValueError("forwarding is unsupported")
            host, port = parse_authority(headers.get(b"host", b"").decode("latin1"))
            test_peer = bool(peer and peer[0] == "testclient")
            local_peer = bool(peer and (is_loopback(peer[0]) or test_peer))
            local_host = is_loopback(host) or (test_peer and host == "testserver")
            origin = headers.get(b"origin")
            if origin is None:
                # Ordinary CLI/TestClient remain supported. Browser subresources
                # from unrelated localhost ports must not exploit absent Origin.
                local_origin = headers.get(b"sec-fetch-site", b"none") in (b"none", b"same-origin")
            else:
                parsed = parse_origin(origin.decode("latin1"))
                scheme = "https" if scope.get("scheme") in {"https", "wss"} else "http"
                same_origin = (scheme, host, port or (443 if scheme == "https" else 80))
                local_origin = parsed == same_origin or parsed in self.allowed_origins
            allowed = local_peer and local_host and local_origin
        except (ValueError, UnicodeError):
            allowed = False
        if not allowed:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008, "reason": "Local research deployment only"})
            else:
                await JSONResponse({"detail": BOUNDARY_MESSAGE}, status_code=403,
                                   headers={"Cache-Control": "no-store"})(scope, receive, send)
            return
        await self.app(scope, receive, send)
