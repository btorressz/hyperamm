"""Lifespan-owned, single-flight, read-only official SDK native metadata cache."""
import asyncio
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import partial
from time import monotonic

from app.market_data.provider_budget import ProviderWaiters
from app.simulation.market_profiles import (MARKETS, DEMO_PROFILES, ResearchPerpMarketMetadata,
    ResearchMarketCatalog, profile)

def validate_native_metadata(raw, observed_at):
    if not isinstance(raw, dict) or raw.get("dex", "") != "" or not isinstance(raw.get("universe"), list):
        raise ValueError("malformed native perpetual metadata")
    universe = raw["universe"]
    if not universe or len(universe) > 10000:
        raise ValueError("invalid metadata universe bounds")
    names, found = set(), {}
    for index, entry in enumerate(universe):
        if not isinstance(entry, dict):
            raise ValueError("malformed metadata entry")
        name, precision = entry.get("name"), entry.get("szDecimals")
        if not isinstance(name, str) or not name or any(c in name for c in ":/@") or name in names:
            raise ValueError("duplicate or incompatible native asset identity")
        names.add(name)
        if type(precision) is not int or not 0 <= precision <= 6:
            raise ValueError("invalid szDecimals")
        if "isDelisted" in entry and type(entry["isDelisted"]) is not bool:
            raise ValueError("invalid delisting flag")
        if name in MARKETS:
            listed = not entry.get("isDelisted", False)
            found[name] = ResearchPerpMarketMetadata(market=name, sz_decimals=precision,
                asset_index=index, listed=listed,
                metadata_status="EXCHANGE_VERIFIED" if listed else "UNAVAILABLE",
                metadata_source="OFFICIAL_SDK_NATIVE_META", metadata_observed_at=observed_at,
                unavailable_reason=None if listed else "Native perpetual explicitly delisted")
    for name in MARKETS:
        if name not in found:
            found[name] = ResearchPerpMarketMetadata(market=name, listed=False,
                metadata_status="UNAVAILABLE", metadata_source="OFFICIAL_SDK_NATIVE_META",
                metadata_observed_at=observed_at, unavailable_reason="Not present in native perpetual universe")
    return tuple(found[name] for name in MARKETS)


def load_sdk_metadata(*, budget=None, deadline=None, cancel=None):
    from hyperliquid.info import Info
    from hyperliquid.utils.constants import MAINNET_API_URL
    # Supply empty initialization maps to avoid constructor-side spot/HIP-3 calls.
    # No exchange facts are inferred from these maps; only the actual meta response is validated.
    info = Info.__new__(Info)
    try:
        if budget is not None:
            budget.bind_sdk(info, "research_metadata", 5, deadline=deadline, cancel=cancel)
        Info.__init__(info, MAINNET_API_URL, skip_ws=True, timeout=5,
                      meta={"universe": []}, spot_meta={"universe": [], "tokens": []})
        return info.meta(dex="")
    finally:
        session = getattr(info, "session", None)
        if session is not None:
            session.close()


class HyperliquidMetadataCatalog:
    def __init__(self, *, allow_demo=False, loader=None, ttl_seconds=300, budget=None):
        self.allow_demo, self.ttl_seconds = allow_demo, ttl_seconds
        self.loader = loader
        self._waiters = None
        self._budget = budget
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-metadata")
        self._lock = asyncio.Lock()
        self._task = None
        self._snapshot = None
        self._expires = 0
        self._closed = False

    async def _refresh(self, deadline):
        waiters = self._waiters
        try:
            loader = self.loader if self.loader is not None else partial(
                load_sdk_metadata, budget=self._budget, deadline=deadline,
                cancel=waiters.cancelled if waiters else None)
            raw = await asyncio.get_running_loop().run_in_executor(self._pool, loader)
            snapshot = validate_native_metadata(raw, datetime.now(timezone.utc))
        except Exception:
            # Avoid exposing network wire errors or accidentally retaining stale verified eligibility.
            snapshot = tuple(ResearchPerpMarketMetadata(market=name,
                sz_decimals=DEMO_PROFILES[name][1] if self.allow_demo else None,
                metadata_status="DEMO_PROFILE" if self.allow_demo else "UNAVAILABLE",
                metadata_source="PINNED_RESEARCH_FIXTURE" if self.allow_demo else "NONE",
                unavailable_reason="Official SDK metadata unavailable or invalid; exchange listing unverified")
                for name in MARKETS)
        if not self._closed and (waiters is None or not waiters.cancelled.is_set()):
            self._snapshot, self._expires = snapshot, monotonic() + self.ttl_seconds
        return snapshot

    async def catalog(self):
        async with self._lock:
            if self._closed:
                raise ValueError("research market catalog is closed")
            if self._snapshot is None or monotonic() >= self._expires:
                if self._task is None or self._task.done():
                    self._waiters = ProviderWaiters(self._budget) if self._budget is not None else None
                    self._task = asyncio.create_task(self._refresh(monotonic() + 5))
                task = self._task
            else:
                if self._budget is not None:
                    self._budget.cache_hit("research_metadata")
                task = None
        if task is not None:
            with self._waiters.waiting() if self._waiters else nullcontext():
                snapshot = await asyncio.shield(task)
        else:
            snapshot = self._snapshot
        if self._closed:
            raise ValueError("research market catalog is closed")
        now = datetime.now(timezone.utc)
        return ResearchMarketCatalog(markets=tuple(profile(item.model_copy(update={
            "metadata_age_seconds": max(0, (now-item.metadata_observed_at).total_seconds())
                if item.metadata_observed_at else None})) for item in snapshot))

    async def resolve(self, market):
        if market not in MARKETS:
            raise ValueError("unsupported research market")
        selected = next(item for item in (await self.catalog()).markets if item.market == market)
        if not selected.research_supported:
            raise ValueError(f"{market} research unavailable: {selected.unavailable_reason}")
        return selected

    async def close(self):
        async with self._lock:
            self._closed = True
            if self._waiters is not None:
                self._waiters.retire()
            task = self._task
        if task is not None:
            await asyncio.shield(task)
        await asyncio.to_thread(self._pool.shutdown, wait=True, cancel_futures=True)
