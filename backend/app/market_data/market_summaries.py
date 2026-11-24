"""On-demand, read-only snapshots of official perpetual asset contexts."""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from time import monotonic
from typing import Annotated, Literal

from pydantic import Field, StrictBool, field_validator

from app.accounting.config import bounded_exact_decimal
from app.risk.market_risk_engine import RISK_CONTEXT
from app.simulation.models import stable_fingerprint

from .live_models import Evidence
from .market_universe_contracts import MarketInstrumentIdentity, Network, UtcDatetime, _utc
from .market_universe_discovery import (
    RATE_LIMIT_BACKOFF, DiscoveryFailure, FailureCode, OfficialMetadataClient,
    _failure_code, normalize_metadata,
)
from .models import utcnow
from .provider_budget import ProviderWaiters
from .public_perp_financials import (
    HYPERLIQUID_INTERVAL_SECONDS, collateral_matches, context_binding, context_row_error,
    has_quote_unit_claim, hourly_funding_rate, public_price,
)

MAX_SELECTION = 13  # Explorer page + previously selected Details card.
MAX_ACTIVE = 3
CACHE_CAPACITY = 24
# metaAndAssetCtxs has weight 20. Budget at most 480 weight per minute.
MAX_REQUESTS_PER_MINUTE = 24
REQUEST_SECONDS = 6
CACHE_SECONDS = 15
MIN_REFRESH_SECONDS = 5
MAX_AGE = timedelta(seconds=30)
Fingerprint = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Status = Literal["CURRENT", "STALE", "UNAVAILABLE", "UNSUPPORTED", "ERROR"]
SummaryFailure = FailureCode | Literal["CAPACITY", "CATALOG_CHANGED", "QUOTE_UNIT_MISMATCH"]


class MarketSummaryRequest(Evidence):
    network: Network
    catalog_fingerprint: Fingerprint
    market_keys: tuple[Annotated[str, Field(min_length=1, max_length=150)], ...] = Field(
        min_length=1, max_length=MAX_SELECTION,
    )
    refresh: StrictBool = False

    @field_validator("market_keys")
    @classmethod
    def unique_keys(cls, keys):
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate market key")
        return keys


class MarketSummary(Evidence):
    identity: MarketInstrumentIdentity
    universe_index: int
    metadata_fingerprint: Fingerprint
    status: Status
    error: SummaryFailure | None = None
    mark_price: str | None = None
    oracle_price: str | None = None
    previous_day_price: str | None = None
    funding_rate: str | None = None
    funding_interval_seconds: Literal[3600] = HYPERLIQUID_INTERVAL_SECONDS
    day_notional_volume: str | None = None
    open_interest_base: str | None = None
    mark_change_vs_previous_day_percent: str | None = None
    price_unit: Literal["PROVIDER_QUOTE_PER_BASE"] = "PROVIDER_QUOTE_PER_BASE"
    notional_unit: Literal["PROVIDER_NOTIONAL_QUOTE"] = "PROVIDER_NOTIONAL_QUOTE"
    open_interest_unit: Literal["BASE"] = "BASE"
    funding_unit: Literal["RATE_PER_INTERVAL"] = "RATE_PER_INTERVAL"
    source: Literal["HYPERLIQUID_INFO_META_AND_ASSET_CTXS"] = "HYPERLIQUID_INFO_META_AND_ASSET_CTXS"
    observed_at: UtcDatetime | None = None
    provider_event_at: None = None
    observation_clock: Literal["LOCAL_RECEIPT"] = "LOCAL_RECEIPT"
    valid_until: UtcDatetime | None = None
    observation_fingerprint: Fingerprint | None = None
    limitations: tuple[str, ...] = Field(default=(), max_length=8)
    read_only: Literal[True] = True
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"


class MarketSummaryResponse(Evidence):
    schema_version: Literal["phase186h-v1"] = "phase186h-v1"
    network: Network
    catalog_fingerprint: Fingerprint
    evaluated_at: UtcDatetime
    valid_until: UtcDatetime
    results: tuple[MarketSummary, ...] = Field(max_length=MAX_SELECTION)
    read_only: Literal[True] = True
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"


# Relative move compares two prices from the same context. The provider
# does not document a common quote denomination across all namespaces.
FIELDS = (
    ("mark_price", "markPx", "positive"),
    ("oracle_price", "oraclePx", "positive"),
    ("previous_day_price", "prevDayPx", "positive"),
    ("funding_rate", "funding", "funding"),
    ("day_notional_volume", "dayNtlVlm", "nonnegative"),
    ("open_interest_base", "openInterest", "nonnegative"),
)


def _values(row):
    values, issues = {}, []
    for name, field, rule in FIELDS:
        if row.get(field) is None:
            issues.append(f"{field}:MISSING")
            continue
        try:
            if rule == "funding":
                value = hourly_funding_rate(row[field])
            elif rule == "positive":
                value = public_price(row[field])
            else:
                value = bounded_exact_decimal(row[field])
                if value < 0:
                    raise ValueError("invalid context value")
        except ValueError:
            issues.append(f"{field}:INVALID")
        else:
            values[name] = value
    if "mark_price" in values and "previous_day_price" in values:
        previous = values["previous_day_price"]
        with localcontext(RISK_CONTEXT):
            try:
                values["mark_change_vs_previous_day_percent"] = bounded_exact_decimal(
                    ((values["mark_price"] - previous) / previous * 100).quantize(Decimal("0.00000001"))
                )
            except ValueError:
                issues.append("mark_vs_prevDayPx:OUT_OF_RANGE")
    return {k: format(v, "f") for k, v in values.items()}, tuple(issues)


@dataclass(frozen=True)
class ContextRow:
    values: dict[str, str]
    limitations: tuple[str, ...]
    error: SummaryFailure | None = None


@dataclass(frozen=True)
class Capture:
    observed_at: datetime | None = None
    rows: tuple[ContextRow, ...] = ()
    error: SummaryFailure | None = None


def _normalize(raw, *, records, collateral_index, observed_at):
    identity = records[0].identity
    if not isinstance(raw, list) or len(raw) != 2 or not isinstance(raw[1], list):
        raise DiscoveryFailure("INVALID_DATA")
    try:
        actual = normalize_metadata(raw[0], network=identity.network, dex=identity.dex, observed_at=observed_at)
    except DiscoveryFailure as exc:
        if exc.code == "MISSING_METADATA":
            return Capture(error="CATALOG_CHANGED")
        raise
    if tuple(map(context_binding, actual)) != tuple(map(context_binding, records)):
        return Capture(error="CATALOG_CHANGED")
    if len(actual) != len(raw[1]):
        # A shortened positional array cannot prove which context is missing.
        raise DiscoveryFailure("INVALID_DATA")
    if not collateral_matches(raw[0], collateral_index) or has_quote_unit_claim(raw[0]):
        return Capture(error="QUOTE_UNIT_MISMATCH")
    rows = []
    for record, row in zip(actual, raw[1], strict=True):
        if row is None:
            rows.append(ContextRow({}, ("CONTEXT_MISSING",)))
        elif error := context_row_error(row, record):
            rows.append(ContextRow({}, (), error))
        elif has_quote_unit_claim(row):
            # Unsupported denomination claims cannot establish comparable prices.
            rows.append(ContextRow({}, (), "QUOTE_UNIT_MISMATCH"))
        else:
            rows.append(ContextRow(*_values(row)))
    return Capture(observed_at, tuple(rows))


class MarketSummaryObservations:
    """Bounded namespace cache with single-flight acquisitions on the app loop."""

    def __init__(self, network: Network, *, client=None, budget=None, clock=utcnow, timer=monotonic):
        self.network = network
        self._client = client if client is not None or budget is not None else OfficialMetadataClient(network)
        self._budget = budget
        self.clock = clock
        self._timer = timer
        self._cache = OrderedDict()
        self._tasks = {}
        self._waiters = {}
        self._starts = deque()
        self._backoff_until = 0.
        self._closed = False

    async def _acquire(self, key, records, collateral_index, refresh):
        if self._closed:
            return Capture(error="CLOSED")
        now = self._timer()
        cached = self._cache.get(key)
        if cached:
            stored, capture = cached
            ttl = MIN_REFRESH_SECONDS if refresh or capture.error else CACHE_SECONDS
            if now - stored < ttl:
                self._cache.move_to_end(key)
                if self._budget is not None:
                    self._budget.cache_hit("summary")
                return capture
        task = self._tasks.get(key)
        if task is None:
            if now < self._backoff_until:
                return Capture(error="RATE_LIMITED")
            while self._starts and now - self._starts[0] >= 60:
                self._starts.popleft()
            if len(self._starts) >= MAX_REQUESTS_PER_MINUTE:
                return Capture(error="RATE_LIMITED")
            if len(self._tasks) >= MAX_ACTIVE:
                if cached and not capture.error and now - stored < MAX_AGE.total_seconds():
                    return capture
                return Capture(error="CAPACITY")
            self._starts.append(now)
            if self._budget is not None:
                self._waiters[key] = ProviderWaiters(self._budget)
            task = self._tasks[key] = asyncio.create_task(
                self._refresh(key, records, collateral_index, monotonic() + REQUEST_SECONDS), name="market-summary-context",
            )
        # A disconnected waiter releases its wait. Concurrent readers share the
        # bounded SDK call, whose session closes even if every waiter disconnects.
        try:
            waiters = self._waiters.get(key)
            with waiters.waiting() if waiters else nullcontext():
                return await asyncio.wait_for(asyncio.shield(task), REQUEST_SECONDS)
        except TimeoutError:
            return Capture(error="TIMEOUT")

    async def _refresh(self, key, records, collateral_index, deadline):
        waiters = self._waiters.get(key)

        def collect():
            client = self._client if self._client is not None else OfficialMetadataClient(
                self.network, budget=self._budget, owner="summary", cancel=waiters.cancelled)
            raw = client("metaAndAssetCtxs", key[1], deadline)
            if monotonic() >= deadline:
                raise DiscoveryFailure("TIMEOUT")
            return _normalize(raw, records=records, collateral_index=collateral_index,
                              observed_at=_utc(self.clock()))

        try:
            try:
                capture = await asyncio.to_thread(collect)
            except Exception as exc:
                capture = Capture(error="INVALID_DATA" if isinstance(exc, ValueError) else _failure_code(exc))
            if capture.error == "RATE_LIMITED":
                self._backoff_until = self._timer() + RATE_LIMIT_BACKOFF
            if not self._closed and capture.error != "CLOSED":
                self._cache[key] = (self._timer(), capture)
                self._cache.move_to_end(key)
                if len(self._cache) > CACHE_CAPACITY:
                    self._cache.popitem(last=False)
            return capture
        finally:
            self._tasks.pop(key, None)
            self._waiters.pop(key, None)

    async def summarize(self, body, catalog, discovery, generation):
        if body.network != self.network or catalog.network != self.network:
            raise DiscoveryFailure("NETWORK_MISMATCH")
        records = catalog.catalog.records
        by_key = {item.identity.stable_key: item for item in records}
        selected = [by_key[k] for k in body.market_keys]
        decisions = {item.identity.stable_key: item for item in catalog.eligibility}
        wanted = {r.identity.dex for r in selected if decisions[r.identity.stable_key].discovery_eligible}
        namespaces = defaultdict(list)
        for record in records:
            if record.identity.dex in wanted:
                namespaces[record.identity.dex].append(record)

        async def acquire(dex, rows):
            ordered = tuple(sorted(rows, key=lambda r: r.universe_index))
            financial = discovery.financial_observation(body.catalog_fingerprint, ordered[0].identity)
            collateral_index = financial.collateral_token_index if financial else None
            return dex, await self._acquire((body.catalog_fingerprint, dex), ordered, collateral_index, body.refresh)

        # Prefer namespaces with no capture or the oldest cache entry so mixed
        # pages can make progress on the next refresh after a partial response.
        ordered_namespaces = sorted(namespaces, key=lambda dex: self._cache.get(
            (body.catalog_fingerprint, dex), (-1., None),
        )[0])
        captures = dict(await asyncio.gather(*(acquire(dex, namespaces[dex]) for dex in ordered_namespaces)))
        now = _utc(self.clock())
        deadline, current = generation
        if not current() or now >= deadline:
            raise DiscoveryFailure("MISSING_METADATA")

        results = []
        for record in selected:
            identity = record.identity
            decision = decisions[identity.stable_key]
            fields = dict(identity=identity, metadata_fingerprint=decision.metadata_fingerprint,
                          universe_index=record.universe_index)
            if not decision.discovery_eligible:
                status = "UNSUPPORTED" if decision.reason == "NOT_LISTED" else "STALE"
                results.append(MarketSummary(**fields, status=status, limitations=(decision.reason,)))
                continue
            capture = captures[identity.dex]
            error = "CLOSED" if self._closed else capture.error
            if error:
                status = "UNAVAILABLE" if error in {"CAPACITY", "CATALOG_CHANGED"} else "ERROR"
                results.append(MarketSummary(**fields, status=status, error=error))
                continue
            observed = capture.observed_at
            valid_until = min(observed + MAX_AGE, deadline)
            row = capture.rows[record.universe_index]
            if observed > now or now >= valid_until:
                results.append(MarketSummary(**fields, status="STALE", observed_at=observed,
                                             valid_until=valid_until))
                continue
            if row.error:
                results.append(MarketSummary(**fields, status="ERROR", error=row.error))
                continue
            summary = MarketSummary(**fields, **row.values, status="CURRENT" if row.values else "UNAVAILABLE",
                                    observed_at=observed, valid_until=valid_until, limitations=row.limitations)
            fingerprint = stable_fingerprint({
                "catalog_fingerprint": body.catalog_fingerprint,
                **summary.model_dump(mode="json", exclude={"observation_fingerprint"}),
            })
            results.append(summary.model_copy(update={"observation_fingerprint": fingerprint}))

        return MarketSummaryResponse(network=self.network, catalog_fingerprint=body.catalog_fingerprint,
                                     evaluated_at=now, valid_until=deadline, results=tuple(results))

    async def close(self):
        self._closed = True
        for waiters in self._waiters.values():
            waiters.retire()
        self._cache.clear()
        if self._tasks:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._tasks.values())))
