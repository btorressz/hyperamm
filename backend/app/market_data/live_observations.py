"""Bounded, opt-in REST observer. No operational runtime or signing dependencies."""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from time import monotonic
from threading import Event

from app.config import Settings
from app.market_data.hyperliquid_metadata import validate_native_metadata
from app.market_data.live_models import (LiveBookLevel, LiveBookObservation, LiveFreshness,
    LiveMarketMetadata, LiveMarketOverview, LiveMarketSnapshot, LiveObservationError,
    LiveObservationStatus, LivePerpObservation, financial_decimal)
from app.market_data.perp_context import normalize_meta_and_asset_ctxs
from app.simulation.market_profiles import MARKETS, validate_price

log = logging.getLogger(__name__)

MESSAGES = {
    "DISABLED": "Live observations are disabled.", "CLOSED": "Live observer is closed.",
    "CAPACITY": "Live observer capacity reached; retry later.",
    "TIMEOUT": "Public market request timed out.", "FORBIDDEN": "Public market access denied.",
    "RATE_LIMITED": "Public market source rate limited; retry later.",
    "UPSTREAM_ERROR": "Public market source unavailable.",
    "SDK_UNAVAILABLE": "Read-only SDK is unavailable.",
    "NETWORK_ERROR": "Public market connection unavailable.",
    "INVALID_DATA": "Public market evidence failed validation.",
    "NOT_LISTED": "Selected native perpetual is missing or delisted.",
    "TEMPORAL_DISCREPANCY": "Book and context acquisition times exceed the coherence budget.",
    "CLEANUP_ERROR": "Read-only SDK cleanup incomplete.",
}


def error(component, code):
    return LiveObservationError(component=component, code=code, message=MESSAGES[code])


def classify(exc):
    # Never include SDK exception strings, wire bodies, request headers or URLs.
    from requests.exceptions import RequestException, Timeout
    if isinstance(exc, Timeout):
        return "TIMEOUT"
    status = getattr(exc, "status_code", None)
    if status == 403:
        return "FORBIDDEN"
    if status == 429:
        return "RATE_LIMITED"
    if type(status) is int:
        return "UPSTREAM_ERROR"
    if isinstance(exc, ImportError):
        return "SDK_UNAVAILABLE"
    if isinstance(exc, RequestException):
        return "NETWORK_ERROR"
    return "INVALID_DATA"


def open_read_only_info(metadata, timeout):
    from hyperliquid.info import Info
    from hyperliquid.utils.constants import MAINNET_API_URL
    info = Info.__new__(Info)
    try:
        # The bootstrap is metadata-only. A second client uses actual validated
        # universe metadata, allowing the SDK itself to populate symbol mappings.
        Info.__init__(info, MAINNET_API_URL, skip_ws=True, timeout=timeout,
                      meta=metadata, spot_meta={"universe": [], "tokens": []})
    except BaseException:
        session = getattr(info, "session", None)
        if session is not None:
            session.close()
        raise
    return info


def normalize_book(raw, metadata, observed_at, *, future_tolerance, max_levels):
    if not isinstance(raw, dict) or raw.get("coin") != metadata.market:
        raise ValueError("L2 requires explicit matching native coin")
    stamp = raw.get("time")
    if type(stamp) is not int or stamp <= 0:
        raise ValueError("invalid exchange milliseconds")
    source = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=stamp)
    if (source - observed_at).total_seconds() > future_tolerance:
        raise ValueError("future exchange timestamp")
    sides = raw.get("levels")
    if not isinstance(sides, list) or len(sides) != 2:
        raise ValueError("invalid book sides")
    normalized = []
    for side, entries in enumerate(sides):
        if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
            raise ValueError("invalid bounded book depth")
        levels = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("invalid book level")
            price = financial_decimal(entry.get("px"))
            size = financial_decimal(entry.get("sz"))
            if not validate_price(price, metadata.sz_decimals):
                raise ValueError("invalid native price precision")
            if size != size.quantize(Decimal(1).scaleb(-metadata.sz_decimals)):
                raise ValueError("invalid native size precision")
            level = LiveBookLevel(price=price, size=size, order_count=entry.get("n", 0))
            if levels and ((side == 0 and levels[-1].price <= price) or
                           (side == 1 and levels[-1].price >= price)):
                raise ValueError("unordered or duplicate levels")
            levels.append(level)
        normalized.append(tuple(levels[:max_levels]))
    bid, ask = normalized[0][0].price, normalized[1][0].price
    mid = (bid + ask) / 2
    return LiveBookObservation(market=metadata.market, bids=normalized[0], asks=normalized[1],
        source_timestamp=source, observed_at=observed_at, best_bid=bid, best_ask=ask,
        midpoint=mid, spread=ask-bid, spread_bps=(ask-bid)/mid*Decimal("10000"),
        truncated=any(len(entries) > max_levels for entries in sides))


def normalize_context(raw, metadata, observed_at):
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError("invalid native context structure")
    meta, contexts = raw
    validated = validate_native_metadata(meta, observed_at)
    selected = next(item for item in validated if item.market == metadata.market)
    if (selected.metadata_status != "EXCHANGE_VERIFIED" or
        selected.asset_index != metadata.asset_index or selected.sz_decimals != metadata.sz_decimals):
        raise ValueError("context native index/precision/listing changed")
    if not isinstance(contexts, list) or len(contexts) != len(meta["universe"]):
        raise ValueError("universe/context cardinality mismatch")
    ctx = contexts[selected.asset_index]
    if not isinstance(ctx, dict) or ctx.get("coin", metadata.market) != metadata.market:
        raise ValueError("context identity mismatch")
    for name in ("markPx", "oraclePx", "funding", "openInterest"):
        financial_decimal(ctx.get(name))
    for name in ("midPx", "premium"):
        if ctx.get(name) is not None:
            financial_decimal(ctx[name])
    # The existing pure normalizer supplies financial formulas. Its synthetic
    # fallback market_mid is never exposed: missing provider mid means null bases.
    normalized = normalize_meta_and_asset_ctxs(raw, metadata.market, updated_at=observed_at)
    values = {name: getattr(normalized, name) for name in (
        "mark_price", "oracle_price", "funding_rate", "open_interest_base",
        "open_interest_notional", "provider_mid_price", "premium", "mark_oracle_basis_bps")}
    has_mid = normalized.provider_mid_price is not None
    return LivePerpObservation(market=metadata.market, observed_at=observed_at, **values,
        mark_mid_basis_bps=normalized.mark_mid_basis_bps if has_mid else None,
        oracle_mid_basis_bps=normalized.oracle_mid_basis_bps if has_mid else None)


class LiveMarketObservationService:
    def __init__(self, settings: Settings, *, info_factory=open_read_only_info,
                 clock=lambda: datetime.now(timezone.utc), timer=monotonic):
        # Capture only the public observation options; no credential-bearing settings retained.
        self.enabled = settings.live_observations_enabled
        self.timeout = settings.live_observation_http_timeout_seconds
        self.ttl = settings.live_observation_cache_ttl_seconds
        self.stale_after = settings.live_observation_stale_after_seconds
        self.metadata_stale_after = settings.live_observation_metadata_stale_after_seconds
        self.capacity = settings.live_observation_max_concurrent_requests
        self.coherence = settings.live_observation_coherence_seconds
        self.future_tolerance = settings.live_observation_future_tolerance_seconds
        self.max_levels = settings.live_observation_book_levels
        self.request_deadline = self.timeout * 6 + 5
        self.shutdown_deadline = self.request_deadline + 5
        self._factory, self._clock, self._timer = info_factory, clock, timer
        self._pool = ThreadPoolExecutor(max_workers=self.capacity, thread_name_prefix="live-observer")
        self._tasks, self._cache, self._expires, self._last_success, self._book_watermarks = {}, {}, {}, {}, {}
        self._closed = False
        self._close_task = None
        self._cleanup_failed = Event()
        self._failed_sessions = {}

    def _empty(self, market, code):
        return LiveMarketSnapshot(market=market, display_name=f"{market}-PERP",
            observation_status="DISABLED" if code == "DISABLED" else "UNAVAILABLE",
            metadata=LiveMarketMetadata(market=market, metadata_status="UNAVAILABLE", source="NONE"),
            generated_at=self._clock(), last_successful_observed_at=self._last_success.get(market),
            errors=(error("service", code),))

    def _observe_sync(self, market):
        metadata = LiveMarketMetadata(market=market, metadata_status="UNAVAILABLE", source="NONE")
        errors, book, context = [], None, None
        info = bootstrap = None
        try:
            bootstrap = self._factory({"universe": []}, self.timeout)
            raw_meta = bootstrap.meta(dex="")
            received = self._clock()
            selected = next(item for item in validate_native_metadata(raw_meta, received) if item.market == market)
            metadata = LiveMarketMetadata(market=market, metadata_status=selected.metadata_status,
                source="OFFICIAL_SDK_NATIVE_META", sz_decimals=selected.sz_decimals,
                asset_index=selected.asset_index, listed=selected.listed, observed_at=received)
            if selected.metadata_status != "EXCHANGE_VERIFIED":
                errors.append(error("metadata", "NOT_LISTED"))
            else:
                # Close the bootstrap before constructing the mapped client.
                bootstrap.session.close()
                bootstrap = None
                info = self._factory(raw_meta, self.timeout)
                if (info.name_to_coin.get(market) != market or
                    info.coin_to_asset.get(market) != metadata.asset_index or
                    info.asset_to_sz_decimals.get(metadata.asset_index) != metadata.sz_decimals):
                    raise ValueError("SDK native symbol mappings do not match validated metadata")
                try:
                    raw_book = info.l2_snapshot(market)
                    book = normalize_book(raw_book, metadata, self._clock(),
                        future_tolerance=self.future_tolerance, max_levels=self.max_levels)
                except Exception as exc:
                    errors.append(error("order_book", classify(exc)))
                try:
                    raw_context = info.meta_and_asset_ctxs()
                    context = normalize_context(raw_context, metadata, self._clock())
                except Exception as exc:
                    errors.append(error("perp_context", classify(exc)))
        except Exception as exc:
            errors.append(error("metadata", classify(exc)))
            metadata = LiveMarketMetadata(market=market, metadata_status="ERROR", source="NONE")
            book, context = None, None
        finally:
            for client in (bootstrap, info):
                if client is not None:
                    try:
                        client.session.close()
                    except Exception:
                        self._cleanup_failed.set()
                        self._failed_sessions.setdefault(market, []).append(client.session)
                        errors.append(error("service", "CLEANUP_ERROR"))
                        log.error("Live observer SDK session cleanup incomplete")
        now = self._clock()
        observed = [item.observed_at for item in (book, context) if item is not None]
        return LiveMarketSnapshot(market=market, display_name=f"{market}-PERP",
            observation_status="PARTIAL" if book or context else "UNAVAILABLE",
            metadata=metadata, order_book=book, perp_context=context,
            observed_at=max(observed) if observed else None, generated_at=now,
            cache_stored_at=now, errors=tuple(errors))

    def _present(self, snapshot, cache_age):
        now = self._clock()
        metadata, book, ctx = snapshot.metadata, snapshot.order_book, snapshot.perp_context
        age = lambda stamp: (now-stamp).total_seconds() if stamp is not None else None
        ma, ba, ca = age(metadata.observed_at), age(book.source_timestamp) if book else None, age(ctx.observed_at) if ctx else None
        state = lambda value, budget, tolerance=0: ("UNAVAILABLE" if value is None else
            "FRESH" if -tolerance <= value <= budget else "STALE")
        ms = state(ma, self.metadata_stale_after) if metadata.metadata_status in {"EXCHANGE_VERIFIED", "STALE"} else "UNAVAILABLE"
        bs, cs = state(ba, self.stale_after, self.future_tolerance), state(ca, self.stale_after)
        if ms == "STALE":
            metadata = metadata.model_copy(update={"metadata_status": "STALE"})
        gap = abs((book.observed_at-ctx.observed_at).total_seconds()) if book and ctx else None
        coherent = gap <= self.coherence if gap is not None else None
        errors = tuple(item for item in snapshot.errors if item.code != "TEMPORAL_DISCREPANCY")
        if coherent is False:
            errors += (error("snapshot", "TEMPORAL_DISCREPANCY"),)
        if snapshot.observation_status == LiveObservationStatus.DISABLED:
            status = "DISABLED"
        elif book is None and ctx is None:
            status = "UNAVAILABLE"
        elif "STALE" in (ms, bs, cs):
            status = "STALE"
        elif book is None or ctx is None:
            status = "PARTIAL"
        elif errors or coherent is False:
            status = "DEGRADED"
        else:
            status = "AVAILABLE"
        return LiveMarketSnapshot(**snapshot.model_dump(exclude={"generated_at", "freshness", "metadata",
            "observation_status", "errors", "cache_age_seconds", "last_successful_observed_at"}),
            generated_at=now, metadata=metadata, observation_status=status, errors=errors,
            cache_age_seconds=cache_age, last_successful_observed_at=self._last_success.get(snapshot.market),
            freshness=LiveFreshness(metadata_age_seconds=ma, l2_source_age_seconds=ba,
                perp_observation_age_seconds=ca, metadata=ms, order_book=bs, perp_context=cs,
                acquisition_gap_seconds=gap, acquisition_coherent=coherent))

    async def _refresh(self, market):
        try:
            snapshot = await asyncio.get_running_loop().run_in_executor(self._pool, self._observe_sync, market)
            previous = self._book_watermarks.get(market)
            book = snapshot.order_book
            if book is not None:
                # Repeated identical event-time evidence is allowed but never retimed.
                # Regressions and changed economics at the same source time are rejected.
                identity = (book.bids, book.asks)
                if previous and (book.source_timestamp < previous[0] or
                                 (book.source_timestamp == previous[0] and identity != previous[1])):
                    snapshot = snapshot.model_copy(update={"order_book": None,
                        "observed_at": snapshot.perp_context.observed_at if snapshot.perp_context else None,
                        "errors": snapshot.errors + (error("order_book", "INVALID_DATA"),)})
                else:
                    self._book_watermarks[market] = (book.source_timestamp, identity)
            snapshot = self._present(snapshot, 0)
            if snapshot.observation_status == LiveObservationStatus.AVAILABLE:
                self._last_success[market] = snapshot.observed_at
            stored = self._timer()
            self._cache[market] = (snapshot, stored)
            codes = {item.code for item in snapshot.errors}
            cooldown = 30 if codes & {"RATE_LIMITED", "FORBIDDEN"} else 5 if codes else 0
            self._expires[market] = stored + max(self.ttl, cooldown)
            return snapshot
        finally:
            self._tasks.pop(market, None)

    async def snapshot(self, market):
        if not isinstance(market, str) or market not in MARKETS:
            raise ValueError("unsupported live market")
        if self._closed:
            return self._empty(market, "CLOSED")
        if not self.enabled:
            return self._empty(market, "DISABLED")
        if self._cleanup_failed.is_set():
            return self._empty(market, "CLEANUP_ERROR")
        cached = self._cache.get(market)
        if cached is not None and self._timer() < self._expires[market]:
            return self._present(cached[0], max(0, self._timer()-cached[1]))
        task = self._tasks.get(market)
        if task is None:
            # All admission happens before an await, on this service's event loop.
            # No executor queue: at most capacity owned operations are submitted.
            if len(self._tasks) >= self.capacity:
                return self._empty(market, "CAPACITY")
            task = asyncio.create_task(self._refresh(market), name=f"live-observe-{market}")
            self._tasks[market] = task
        try:
            snapshot = await asyncio.wait_for(asyncio.shield(task), timeout=self.request_deadline)
        except TimeoutError:
            # A response deadline does not terminate synchronous work or release capacity.
            return self._empty(market, "TIMEOUT")
        return self._present(snapshot, max(0, self._timer()-self._cache[market][1]))

    async def overview(self):
        # Fixed three-market sequential acquisition also works with capacity=1;
        # concurrent independent callers remain bounded and may see CAPACITY.
        values = []
        for market in MARKETS:
            values.append((await self.snapshot(market), self._timer()))
        # Re-evaluate freshness after the entire acquisition, not at each early read.
        presented = tuple(self._present(item, item.cache_age_seconds + max(0, self._timer()-returned)
            if item.cache_age_seconds is not None else None) for item, returned in values)
        return LiveMarketOverview(generated_at=self._clock(), markets=presented)

    async def _drain(self):
        try:
            await asyncio.gather(*tuple(self._tasks.values()), return_exceptions=False)
            if self._failed_sessions:
                def retry_session_cleanup():
                    failed = False
                    for sessions in self._failed_sessions.values():
                        for session in sessions:
                            try:
                                session.close()
                            except Exception:
                                failed = True
                    if failed:
                        raise RuntimeError("Live observer SDK session cleanup incomplete")
                    self._failed_sessions.clear()
                await asyncio.to_thread(retry_session_cleanup)
        finally:
            # Workers own session close. Never close their clients from the event loop.
            await asyncio.to_thread(self._pool.shutdown, wait=True, cancel_futures=True)

    async def close(self):
        self._closed = True
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._drain(), name="live-observer-shutdown")
        # Retain shutdown ownership if any reader/shutdown caller is cancelled.
        try:
            await asyncio.wait_for(asyncio.shield(self._close_task), timeout=self.shutdown_deadline)
        except TimeoutError:
            raise RuntimeError("Live observer shutdown incomplete; owned workers are still draining") from None
