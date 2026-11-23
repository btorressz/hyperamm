"""Lifespan-owned research execution and PAPER preflight; no live runtime state."""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any

from .service import SimulationService

logger = logging.getLogger(__name__)
RESEARCH_OPERATIONS = frozenset({"run_scenario", "run_generalized_paper", "optimize", "compare_research_configs",
                                 "historical_catalog", "historical_summaries", "historical_provenance", "replay_history",
                                 "compare_scenario_historical", "run_portfolio_research", "analyze_portfolio_research", "stress_portfolio_research", "terminal_portfolio_research"})
PAPER_PREFLIGHT_SLOTS = 2
PAPER_PREFLIGHT_LIMIT = 4


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
        self._preflight_pool = ThreadPoolExecutor(max_workers=PAPER_PREFLIGHT_SLOTS, thread_name_prefix="paper-preflight")
        self._preflights = set()
        self._lock = Lock()
        self._busy = False
        self._closed = False

    def _finished(self, future):
        with self._lock:
            self._busy = False

    async def preflight(self, compile_scenario):
        # At most two active calculations and two waiting for a pool thread.
        if self._closed or len(self._preflights) >= PAPER_PREFLIGHT_LIMIT:
            raise ResearchBusyError("Local PAPER preflight capacity is busy")
        future = asyncio.get_running_loop().run_in_executor(self._preflight_pool, compile_scenario)
        self._preflights.add(future)

        def finished(done):
            self._preflights.discard(done)
            if not done.cancelled():
                done.exception()

        future.add_done_callback(finished)
        # Keep queued submissions accounted for until the pool consumes them.
        # Canceled waiters cannot make room for more queued work.
        return await asyncio.shield(future)

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
                # The completed scenario is freshly constructed for this request.
                # Keep copying caller-owned arguments without walking its frames on the loop.
                preflighted = inputs.pop("preflighted", None) if operation == "run_generalized_paper" else None
                detached = deepcopy(inputs)
                if preflighted is not None:
                    detached["preflighted"] = preflighted
                future = self._pool.submit(_run, operation, detached)
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
        try:
            await asyncio.to_thread(self._preflight_pool.shutdown, wait=True, cancel_futures=True)
        finally:
            await asyncio.to_thread(self._pool.shutdown, wait=True, cancel_futures=True)
