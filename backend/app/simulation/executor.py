"""One lifespan-owned, non-queued research worker; no live runtime state."""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any

from .service import SimulationService

logger = logging.getLogger(__name__)
RESEARCH_OPERATIONS = frozenset({"run_scenario", "optimize", "compare_research_configs",
                                 "historical_catalog", "historical_summaries", "historical_provenance", "replay_history",
                                 "compare_scenario_historical", "run_portfolio_research", "analyze_portfolio_research"})


class ResearchBusyError(Exception):
    pass


def _run(operation: str, inputs: dict[str, Any]):
    async def workload():
        # Construct every async execution component in this worker's loop.
        service = SimulationService()
        return await getattr(service, operation)(**inputs)

    try:
        return asyncio.run(workload())
    except ValueError:
        raise
    except Exception:
        logger.exception("Phase 10 research worker failed: %s", operation)
        raise


class SimulationExecutor:
    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="phase10-research")
        self._lock = Lock()
        self._busy = False
        self._closed = False

    def _finished(self, future):
        with self._lock:
            self._busy = False

    async def execute(self, operation: str, **inputs):
        if operation not in RESEARCH_OPERATIONS:
            raise ValueError("unknown research operation")
        with self._lock:
            if self._closed:
                raise ResearchBusyError("Phase 10 research worker is shutting down")
            if self._busy:
                raise ResearchBusyError("Phase 10 research is already running")
            self._busy = True
            try:
                # Admission owns detached inputs even for direct service callers.
                future = self._pool.submit(_run, operation, deepcopy(inputs))
            except Exception:
                self._busy = False
                raise
        # Release only on actual worker completion, never request cancellation.
        future.add_done_callback(self._finished)
        wrapped = asyncio.wrap_future(future)
        # Retrieve detached failures too if the request stops awaiting its job.
        wrapped.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        return await asyncio.shield(wrapped)

    async def shutdown(self):
        with self._lock:
            self._closed = True
        # Keep the live loop responsive while the bounded active job finishes.
        await asyncio.to_thread(self._pool.shutdown, wait=True, cancel_futures=True)
