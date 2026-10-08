"""Small bounded Redis client and resource leases; no execution locks."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import urlsplit, unquote
from uuid import uuid4

from app.diagnostics import sanitize_public_text

log = logging.getLogger(__name__)

# Server time avoids worker clock skew. Sorted sets expire both individual
# abandoned tokens and the whole key. Renew never resurrects an expired token.
ACQUIRE = """
local t = redis.call('TIME')
local now = t[1]*1000 + math.floor(t[2]/1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then return 0 end
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[3]), ARGV[1])
redis.call('PEXPIRE', KEYS[1], ARGV[3])
return 1
"""
RENEW = """
local t = redis.call('TIME')
local now = t[1]*1000 + math.floor(t[2]/1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if not redis.call('ZSCORE', KEYS[1], ARGV[1]) then return 0 end
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[2]), ARGV[1])
redis.call('PEXPIRE', KEYS[1], ARGV[2])
return 1
"""


class InfrastructureUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("Redis infrastructure unavailable")


class RedisInfrastructure:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client
        self._owns_client = client is None
        self.last_error = None
        self.worker_id = uuid4().hex

    def key(self, *parts):
        return ":".join((self.settings.redis_namespace, *parts))

    def diagnose(self, exc):
        url = self.settings.redis_url
        parsed = urlsplit(url)
        secrets = (url, unquote(parsed.password or ""), unquote(parsed.username or ""))
        message = re.sub(r"rediss?://[^\s<>\"']+", "[provider URL]", str(exc))
        self.last_error = sanitize_public_text(message, secrets=secrets)
        log.warning("Redis infrastructure degraded: %s", self.last_error)

    async def call(self, method, *args, **kwargs):
        try:
            if self.client is None:
                raise InfrastructureUnavailable()
            result = await asyncio.wait_for(getattr(self.client, method)(*args, **kwargs),
                                            self.settings.redis_operation_timeout_seconds)
            return result
        except Exception as exc:
            self.diagnose(exc)
            raise InfrastructureUnavailable() from None

    async def start(self):
        if self.client is None:
            try:
                from redis.asyncio import Redis
                self.client = Redis.from_url(
                    self.settings.redis_url, decode_responses=True,
                    socket_connect_timeout=self.settings.redis_operation_timeout_seconds,
                    socket_timeout=self.settings.redis_operation_timeout_seconds,
                    max_connections=64,
                )
            except Exception as exc:
                self.diagnose(exc)
                # A missing optional dependency/configuration is not reconnectable.
                raise RuntimeError("Redis enabled: install hyperamm[redis] and check Redis configuration") from None
        try:
            await self.call("ping")
        except InfrastructureUnavailable:
            if self.settings.redis_required:
                raise RuntimeError("Required Redis infrastructure unavailable at startup") from None

    async def close(self):
        if self.client is not None and self._owns_client:
            try:
                await asyncio.wait_for(self.client.aclose(), self.settings.redis_operation_timeout_seconds)
            except Exception as exc:
                self.diagnose(exc)

    async def cache(self, key, value):
        await self.call("set", key, value, ex=self.settings.redis_default_ttl_seconds)

    async def acquire(self, resource, limit):
        if resource not in {"terminal-clients", "research"} or not 1 <= limit <= 32:
            raise ValueError("unsupported bounded infrastructure resource")
        token = uuid4().hex
        key = self.key("admission", resource)
        ttl = self.settings.redis_worker_heartbeat_ttl_seconds
        accepted = await self.call("eval", ACQUIRE, 1, key, token, limit, ttl * 1000)
        return RedisLease(self, key, token, ttl) if accepted else None

    async def heartbeat(self, process_id):
        await self.call("set", self.key("worker", process_id, self.worker_id),
                        json.dumps({"process_id": process_id, "worker_id": self.worker_id,
                                    "role": "local-api-ws-research", "observational": True}),
                        ex=self.settings.redis_worker_heartbeat_ttl_seconds)


class RedisLease:
    """Admission only. Losing a research lease never grants trading permission."""
    def __init__(self, infrastructure, key, token, ttl):
        self.infrastructure, self.key, self.token, self.ttl = infrastructure, key, token, ttl
        self.lost = asyncio.Event()
        self._task = None

    def start(self):
        self._task = asyncio.create_task(self._renew(), name="redis-admission-renewal")
        return self

    async def _renew(self):
        while True:
            await asyncio.sleep(self.ttl / 3)
            try:
                ok = await self.infrastructure.call("eval", RENEW, 1, self.key, self.token, self.ttl * 1000)
                if ok:
                    continue
            except InfrastructureUnavailable:
                pass
            self.lost.set()
            return

    async def close(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        try:
            await self.infrastructure.call("zrem", self.key, self.token)
        except InfrastructureUnavailable:
            pass  # Expiry recovers abandoned capacity.
