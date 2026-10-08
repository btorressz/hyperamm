"""Shared research admission around the unchanged local PAPER worker.

No queued payloads, result reuse, candidate deployment or live runtime references.
Status/results are expiring operational mirrors, not durable research records.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
from uuid import uuid4

from pydantic import TypeAdapter

from app.simulation.executor import ResearchBusyError
from app.simulation.version import SIMULATION_ENGINE_VERSION
from .redis import InfrastructureUnavailable


class ResearchUnavailableError(RuntimeError):
    def __init__(self):
        super().__init__("Redis research admission unavailable")


def digest(value):
    payload = TypeAdapter(object).dump_python(value, mode="json")
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CoordinatedSimulationExecutor:
    def __init__(self, local, infrastructure, identity):
        self.local, self.infrastructure, self.identity = local, infrastructure, identity
        self._tasks = set()
        self._closed = False

    async def execute(self, operation, **inputs):
        if operation not in {"run_scenario", "optimize"}:
            raise ValueError("unknown research operation")
        if self._closed:
            raise ResearchBusyError("Phase 10 research worker is shutting down")
        inputs = deepcopy(inputs)
        process_id, session_id = self.identity()
        request_digest = digest({"operation": operation, "inputs": inputs,
                                 "engine_version": SIMULATION_ENGINE_VERSION})
        try:
            lease = await self.infrastructure.acquire("research", 1)
        except InfrastructureUnavailable:
            raise ResearchUnavailableError() from None
        if lease is None:
            raise ResearchBusyError("Phase 10 research is already running")
        job_id = uuid4().hex
        metadata = {"job_id": job_id, "process_id": process_id, "session_id": session_id,
                    "request_fingerprint": request_digest, "engine_version": SIMULATION_ENGINE_VERSION,
                    "operation": operation, "observational": True}
        status_key = self.infrastructure.key("research-job", process_id, session_id, job_id)
        try:
            await self.infrastructure.cache(status_key, json.dumps({**metadata, "status": "RUNNING"}))
        except BaseException as exc:
            await lease.close()
            if isinstance(exc, InfrastructureUnavailable):
                raise ResearchUnavailableError() from None
            raise
        if self._closed:
            await lease.close()
            raise ResearchBusyError("Phase 10 research worker is shutting down")
        # Detached task owns admission until the real worker finishes. A cancelled
        # HTTP waiter must not release capacity or cancel the thread's calculation.
        task = asyncio.create_task(self._work(operation, inputs, metadata, status_key, lease.start()),
                                   name="redis-coordinated-research")
        self._tasks.add(task)
        def finished(future):
            self._tasks.discard(future)
            if not future.cancelled():
                future.exception()
        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def _work(self, operation, inputs, metadata, status_key, lease):
        async def refresh_status():
            while True:
                await asyncio.sleep(lease.ttl / 3)
                try:
                    await self.infrastructure.cache(status_key, json.dumps({**metadata, "status": "RUNNING"}))
                except InfrastructureUnavailable:
                    pass
        refresh = asyncio.create_task(refresh_status(), name="redis-research-status")
        status = "FAILED"
        result_key = None
        try:
            result = await self.local.execute(operation, **inputs)
            # Store by full input identity and isolated result/dataset identity;
            # no lookup ever substitutes cached output for a fresh calculation.
            payload = TypeAdapter(object).dump_python(result, mode="json")
            result_key = self.infrastructure.key("research-result", metadata["process_id"],
                metadata["session_id"], SIMULATION_ENGINE_VERSION,
                metadata["request_fingerprint"], digest(payload))
            try:
                if not lease.lost.is_set():
                    await self.infrastructure.cache(result_key, json.dumps({**metadata, "result": payload}))
                else:
                    result_key = None
            except InfrastructureUnavailable:
                result_key = None
            status = "LEASE_LOST" if lease.lost.is_set() else "COMPLETED"
            return result
        finally:
            refresh.cancel()
            await asyncio.gather(refresh, return_exceptions=True)
            try:
                await self.infrastructure.cache(status_key, json.dumps({**metadata, "status": status,
                                                                       "result_key": result_key}))
            except InfrastructureUnavailable:
                pass
            await lease.close()

    async def shutdown(self):
        self._closed = True
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.local.shutdown()
