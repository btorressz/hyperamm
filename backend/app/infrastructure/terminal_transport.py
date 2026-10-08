"""Latest-only observational fanout; wire contract and identity are engine-owned."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.terminal.models import TerminalSnapshot
from .redis import InfrastructureUnavailable


class InProcessTerminalTransport:
    def __init__(self):
        self.clients = set()
        self.latest = None

    def publish(self, wire):
        self.latest = wire
        for queue in self.clients:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(wire)

    def subscribe(self):
        if len(self.clients) >= 32:
            raise RuntimeError("Local terminal client limit reached")
        queue = asyncio.Queue(maxsize=1)
        self.clients.add(queue)
        if self.latest is not None:
            queue.put_nowait(self.latest)
        return queue

    def unsubscribe(self, queue):
        self.clients.discard(queue)


class RedisTerminalTransport:
    """A publisher and validated relay pinned to an explicit engine identity.

    identity() is trusted local wiring, never Redis discovery. A future relay-only
    worker must supply its configured engine process/session through reviewed wiring.
    This class creates no HyperAmmRuntime, execution adapter or authority inputs.
    """
    def __init__(self, infrastructure, identity, clock=None):
        self.infrastructure = infrastructure
        self.identity = identity
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.local = InProcessTerminalTransport()
        self.pending = asyncio.Queue(maxsize=1)
        self._tasks = []
        self._sequence = 0
        self._emitted_at = None
        self._last_identity = None

    def channel(self):
        return self.infrastructure.key(self.infrastructure.settings.redis_terminal_channel, self.identity()[0])

    def cache_key(self, identity=None):
        return self.infrastructure.key("terminal-latest", *(identity or self.identity()))

    def offer(self, wire):
        # No I/O or await on the engine publisher/lock path.
        if self.pending.full():
            self.pending.get_nowait()
        self.pending.put_nowait(wire)

    def validate_wire(self, wire):
        if not isinstance(wire, (str, bytes)) or len(wire) > 4_000_000:
            raise ValueError("invalid bounded terminal wire")
        snapshot = TerminalSnapshot.model_validate_json(wire)
        identity = (snapshot.process_id, snapshot.session_id)
        if identity != self.identity():
            raise ValueError("terminal identity mismatch")
        age = (self.clock() - snapshot.emitted_at).total_seconds()
        if not 0 <= age <= 5:
            raise ValueError("expired or future terminal observation")
        return snapshot, identity

    def relay(self, wire):
        snapshot, identity = self.validate_wire(wire)
        # Sequence is process-wide and must advance even across session resets.
        if snapshot.sequence <= self._sequence or (self._emitted_at and snapshot.emitted_at < self._emitted_at):
            return False
        self._sequence, self._emitted_at = snapshot.sequence, snapshot.emitted_at
        self._last_identity = identity
        self.local.publish(wire.decode() if isinstance(wire, bytes) else wire)
        return True

    async def subscribe(self):
        # Acquire before local registration. Connection capacity fails closed.
        lease = await self.infrastructure.acquire("terminal-clients", 32)
        if lease is None:
            raise RuntimeError("Shared terminal client limit reached")
        try:
            if self.local.latest is not None:
                try:
                    self.validate_wire(self.local.latest)
                except ValueError:
                    self.local.latest = None
            queue = self.local.subscribe()
            return queue, lease.start()
        except BaseException:
            await lease.close()
            raise

    async def unsubscribe(self, queue, lease):
        self.local.unsubscribe(queue)
        await lease.close()

    async def start(self):
        self._tasks = [asyncio.create_task(fn(), name=name) for fn, name in (
            (self._publish, "redis-terminal-publisher"),
            (self._receive, "redis-terminal-subscriber"),
            (self._heartbeat, "redis-worker-heartbeat"),
        )]

    async def close(self):
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _publish(self):
        while True:
            wire = await self.pending.get()
            while True:
                try:
                    _, identity = self.validate_wire(wire)
                    await self.infrastructure.cache(self.cache_key(identity), wire)
                    await self.infrastructure.call("publish", self.channel(), wire)
                    break
                except ValueError:
                    break  # Never re-date an observation after an outage.
                except InfrastructureUnavailable:
                    await asyncio.sleep(1)
                    if not self.pending.empty():
                        wire = self.pending.get_nowait()

    async def _receive(self):
        while True:
            pubsub = None
            try:
                pubsub = self.infrastructure.client.pubsub()
                await asyncio.wait_for(pubsub.subscribe(self.channel()),
                                       self.infrastructure.settings.redis_operation_timeout_seconds)
                cached = await self.infrastructure.call("get", self.cache_key())
                if cached:
                    try:
                        self.relay(cached)
                    except ValueError:
                        pass
                while True:
                    message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True, timeout=1),
                                                    self.infrastructure.settings.redis_operation_timeout_seconds + 1)
                    if message and message.get("type") == "message":
                        try:
                            self.relay(message["data"])
                        except ValueError:
                            pass
            except Exception as exc:
                self.infrastructure.diagnose(exc)
            finally:
                if pubsub:
                    try:
                        await asyncio.wait_for(pubsub.aclose(), self.infrastructure.settings.redis_operation_timeout_seconds)
                    except Exception as exc:
                        self.infrastructure.diagnose(exc)
            await asyncio.sleep(1)

    async def _heartbeat(self):
        while True:
            try:
                await self.infrastructure.heartbeat(self.identity()[0])
            except InfrastructureUnavailable:
                pass
            await asyncio.sleep(self.infrastructure.settings.redis_worker_heartbeat_ttl_seconds / 3)
