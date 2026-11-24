"""Bounded, on-demand observations from Hyperliquid's public info API."""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from time import monotonic
from typing import Literal

from app.accounting.config import bounded_exact_decimal
from app.agents.advisory_evidence import captured_source
from app.risk.market_risk_engine import RISK_CONTEXT

from .market_universe_contracts import MarketUniverseMetadata, Network, _utc, evaluate_discovery
from .market_universe_discovery import (
    RATE_LIMIT_BACKOFF,
    DiscoveryFailure,
    FailureCode,
    OfficialMetadataClient,
    _failure_code,
    normalize_metadata,
)
from .models import utcnow
from .provider_budget import ProviderWaiters
from .public_perp_financials import (
    HYPERLIQUID_INTERVAL_SECONDS, collateral_matches, context_binding, context_row_error,
    has_quote_unit_claim, hourly_funding_rate, public_price,
)

HISTORY_HOURS = 24
MAX_BOOK_AGE = timedelta(seconds=10)
MAX_SOURCE_SKEW = timedelta(seconds=10)
CURRENT_MAX_AGE = timedelta(seconds=30)
REQUEST_BUDGET_SECONDS = 12
MAX_CONCURRENT_MARKETS = 3
CACHE_CAPACITY = 64
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

Operation = Literal["metaAndAssetCtxs", "l2Book", "fundingHistory"]
Status = Literal["AVAILABLE", "INSUFFICIENT_DATA", "STALE", "UNSUPPORTED", "ERROR"]


class _OfficialPublicClient(OfficialMetadataClient):
    _operations = frozenset({"metaAndAssetCtxs", "l2Book", "fundingHistory"})

    def request(self, operation: Operation, identity, deadline: float, *, start=None, end=None):
        if operation == "metaAndAssetCtxs":
            return self(operation, identity.dex, deadline)

        def call(info):
            info.name_to_coin[identity.exchange_coin] = identity.exchange_coin
            if operation == "l2Book":
                return info.l2_snapshot(identity.exchange_coin)
            if operation == "fundingHistory":
                return info.funding_history(identity.exchange_coin, start, end)
            raise DiscoveryFailure("UNSUPPORTED_METADATA")

        return self._public_request(deadline, call)


@dataclass(frozen=True)
class FundingHistoryPoint:
    observed_at: datetime
    funding_rate: Decimal
    premium: Decimal | None


@dataclass(frozen=True)
class _Point:
    category: str
    operation: Operation
    value: Decimal | tuple[FundingHistoryPoint, ...]
    captured_at: datetime
    unit: str
    observed_at: datetime | None = None
    details: tuple = ()

    def source(self, metadata):
        source_ids = {
            "metaAndAssetCtxs": "HYPERLIQUID_META_AND_ASSET_CTXS",
            "l2Book": "HYPERLIQUID_L2_BOOK",
            "fundingHistory": "HYPERLIQUID_FUNDING_HISTORY",
        }
        value = (tuple((row.observed_at, row.funding_rate, row.premium) for row in self.value)
                 if isinstance(self.value, tuple) else self.value)
        expiry = (self.observed_at + MAX_BOOK_AGE if self.operation == "l2Book"
                  else self.captured_at + CURRENT_MAX_AGE)
        return captured_source(
            metadata=metadata, value=(value, self.details),
            category=self.category, provenance="EXCHANGE_OBSERVED", source_id=source_ids[self.operation],
            captured_at=self.captured_at, observed_at=self.observed_at,
            observation_clock="PROVIDER_EVENT" if self.observed_at is not None else "LOCAL_RECEIPT",
            valid_until=expiry, unit=self.unit,
            limitations=(("Provider does not report an event timestamp for this field.",)
                         if self.observed_at is None else ()),
        )


@dataclass(frozen=True, init=False)
class OfficialPerpObservation:
    """Created by the configured backend adapter. No wire deserializer."""

    metadata: MarketUniverseMetadata
    status: Status
    points: tuple[_Point, ...]
    limitations: tuple[str, ...]
    failure_code: FailureCode | None
    catalog_fingerprint: str | None

    @classmethod
    def _from_acquisition(cls, metadata, status, points=(), limitations=(), *, failure_code=None,
                          catalog_fingerprint=None):
        capture = object.__new__(cls)
        object.__setattr__(capture, "metadata", metadata)
        object.__setattr__(capture, "status", status)
        object.__setattr__(capture, "points", tuple(points))
        object.__setattr__(capture, "limitations", tuple(limitations))
        object.__setattr__(capture, "failure_code", failure_code)
        object.__setattr__(capture, "catalog_fingerprint", catalog_fingerprint)
        return capture

    def source_evidence(self):
        return tuple(point.source(self.metadata) for point in self.points)

    def point(self, category):
        return next((point for point in self.points if point.category == category), None)


def _exact(value, *, positive=False, nonnegative=False):
    result = bounded_exact_decimal(value)
    if (positive and result <= 0) or (nonnegative and result < 0):
        raise ValueError("provider Decimal outside field bounds")
    return result


def _time_ms(value):
    if type(value) is not int or not 0 < value <= 253402300799999:
        raise ValueError("invalid provider timestamp")
    return EPOCH + timedelta(milliseconds=value)


def _epoch_ms(timestamp):
    delta = timestamp - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


class _UnsupportedQuoteUnit(ValueError):
    pass


def _current(raw, metadata, captured_at, financial, namespace_records):
    identity = metadata.identity
    if not isinstance(raw, list) or len(raw) != 2 or not isinstance(raw[1], list):
        raise DiscoveryFailure("INVALID_DATA")
    records = normalize_metadata(raw[0], network=identity.network, dex=identity.dex, observed_at=captured_at)
    if len(records) != len(raw[1]):
        raise DiscoveryFailure("INVALID_DATA")
    if namespace_records is not None and tuple(map(context_binding, records)) != tuple(
            map(context_binding, namespace_records)):
        raise DiscoveryFailure("NAMESPACE_CONFLICT")
    match = next((record for record in records if record.identity == identity), None)
    if match is None:
        raise DiscoveryFailure("MISSING_METADATA")
    if context_binding(match) != context_binding(metadata):
        raise DiscoveryFailure("NAMESPACE_CONFLICT")
    if financial is not None and financial.metadata != metadata:
        raise DiscoveryFailure("NAMESPACE_CONFLICT")
    index = financial.collateral_token_index if financial is not None else None
    if not collateral_matches(raw[0], index):
        raise _UnsupportedQuoteUnit("Public collateral token conflicts with discovery metadata.")
    if has_quote_unit_claim(raw[0]):
        raise _UnsupportedQuoteUnit("Public context contains an unsupported quote-unit claim.")
    row = raw[1][match.universe_index]
    if row is None:
        return [], ["Public context row is missing."]
    if error := context_row_error(row, match):
        raise DiscoveryFailure(error)
    if has_quote_unit_claim(row):
        raise _UnsupportedQuoteUnit("Public context contains an unsupported quote-unit claim.")
    fields = (
        ("funding", "FUNDING", "RATE_PER_HOUR"),
        ("markPx", "MARK_PRICE", "PRICE_QUOTE_PER_BASE"),
        ("oraclePx", "ORACLE_PRICE", "PRICE_QUOTE_PER_BASE"),
        ("openInterest", "OPEN_INTEREST", "BASE"),
    )
    points = []
    issues = []
    for field, category, unit in fields:
        if row.get(field) is None:
            issues.append(f"{category} unavailable in public response.")
            continue
        try:
            if field == "funding":
                value = hourly_funding_rate(row[field])
            elif field in {"markPx", "oraclePx"}:
                value = public_price(row[field])
            else:
                value = _exact(row[field], nonnegative=True)
        except ValueError:
            issues.append(f"{category} is invalid in public response.")
            continue
        details = (HYPERLIQUID_INTERVAL_SECONDS,) if field == "funding" else ()
        points.append(_Point(category, "metaAndAssetCtxs", value, captured_at, unit, details=details))
    return points, issues


def _book(raw, identity, captured_at, current_at):
    if not isinstance(raw, dict) or raw.get("coin") != identity.exchange_coin:
        raise DiscoveryFailure("NAMESPACE_CONFLICT")
    if raw.get("network", identity.network) != identity.network:
        raise DiscoveryFailure("NETWORK_MISMATCH")
    if raw.get("dex", identity.dex) != identity.dex:
        raise DiscoveryFailure("NAMESPACE_CONFLICT")
    observed_at = _time_ms(raw.get("time"))
    if (not timedelta(0) <= captured_at - observed_at < MAX_BOOK_AGE
            or abs(observed_at - current_at) > MAX_SOURCE_SKEW):
        raise ValueError("book event time is stale, future-dated or misaligned")
    levels = raw.get("levels")
    if (not isinstance(levels, list) or len(levels) != 2
            or any(not isinstance(side, list) or not side or not isinstance(side[0], dict) for side in levels)):
        raise ValueError("both book sides are required")
    if has_quote_unit_claim(raw) or any(has_quote_unit_claim(side[0]) for side in levels):
        raise _UnsupportedQuoteUnit("Public book contains an unsupported quote-unit claim.")
    bid, ask = (public_price(side[0].get("px")) for side in levels)
    for side in levels:
        _exact(side[0].get("sz"), positive=True)
    if bid >= ask:
        raise ValueError("book is locked or crossed")
    with localcontext(RISK_CONTEXT):
        mid = (bid + ask) / 2
    return _Point("MID_PRICE", "l2Book", mid, captured_at, "PRICE_QUOTE_PER_BASE",
                  observed_at, (bid, ask))


def _history(raw, identity, captured_at, start, end):
    # Allow the provider's inclusive start/end to yield up to one extra row.
    if not isinstance(raw, list) or len(raw) > HISTORY_HOURS + 1:
        raise ValueError("invalid or unbounded funding history")
    by_hour = {}
    for row in raw:
        if not isinstance(row, dict) or row.get("coin") != identity.exchange_coin:
            raise DiscoveryFailure("NAMESPACE_CONFLICT")
        if row.get("network", identity.network) != identity.network:
            raise DiscoveryFailure("NETWORK_MISMATCH")
        if row.get("dex", identity.dex) != identity.dex:
            raise DiscoveryFailure("NAMESPACE_CONFLICT")
        at = _time_ms(row.get("time"))
        if not start <= _epoch_ms(at) <= end or at > captured_at:
            raise ValueError("funding history outside requested time range")
        # This endpoint returns realized one-hour rates, under the same
        # venue cap as the current hourly rate. The PAPER schedule is separate.
        rate = hourly_funding_rate(row.get("fundingRate"))
        premium = _exact(row["premium"]) if row.get("premium") is not None else None
        row = FundingHistoryPoint(at, rate, premium)
        hour = _epoch_ms(at) // 3_600_000
        if hour in by_hour and by_hour[hour] != row:
            raise ValueError("conflicting observations for one funding interval")
        by_hour[hour] = row
    rows = tuple(by_hour[key] for key in sorted(by_hour)[-HISTORY_HOURS:])
    if not rows:
        return None
    return _Point("FUNDING_HISTORY", "fundingHistory", rows, captured_at, "REALIZED_RATE_PER_HOUR",
                  rows[-1].observed_at, (start, end, HYPERLIQUID_INTERVAL_SECONDS))


class AdvisoryMarketObservations:
    """One event-loop owner for bounded single-flight public observations."""

    def __init__(self, *, network: Network, clock=utcnow, budget=None, max_metadata_age_seconds: int = 60):
        if type(max_metadata_age_seconds) is not int or not 1 <= max_metadata_age_seconds <= 86400:
            raise ValueError("invalid advisory metadata freshness budget")
        self._network = network
        self._client = _OfficialPublicClient(network) if budget is None else None
        self._budget = budget
        self._clock = clock
        self._metadata_age = max_metadata_age_seconds
        self._tasks = {}
        self._waiters = {}
        self._cache = OrderedDict()
        self._backoff_until = 0.0
        self._closed = False

    async def observe(self, metadata: MarketUniverseMetadata, *, financial=None,
                      namespace_records=None, catalog_fingerprint=None) -> OfficialPerpObservation:
        metadata = MarketUniverseMetadata.model_validate(metadata)

        def failure(status, **fields):
            return OfficialPerpObservation._from_acquisition(
                metadata, status, catalog_fingerprint=catalog_fingerprint, **fields,
            )

        if metadata.identity.network != self._network:
            raise DiscoveryFailure("NETWORK_MISMATCH")
        if self._closed:
            return failure("ERROR", limitations=("Observation adapter is closed.",))
        now = _utc(self._clock())
        discovery = evaluate_discovery(metadata, evaluated_at=now, max_age_seconds=self._metadata_age)
        if not discovery.discovery_eligible:
            status = {
                "NOT_LISTED": "UNSUPPORTED", "STALE_METADATA": "STALE",
                "FUTURE_TIMESTAMP": "ERROR", "METADATA_ERROR": "ERROR",
            }.get(discovery.reason, "INSUFFICIENT_DATA")
            return failure(status, limitations=(discovery.reason,))
        key = (catalog_fingerprint, metadata.fingerprint(), financial.fingerprint() if financial is not None else None)
        cached = self._cache.get(key)
        if cached is not None and now < cached[0] and all(point.captured_at <= now for point in cached[1].points):
            self._cache.move_to_end(key)
            if self._budget is not None:
                self._budget.cache_hit("advisory")
            return cached[1]
        if monotonic() < self._backoff_until:
            return failure("ERROR", limitations=("Public provider rate-limit backoff is active.",),
                           failure_code="RATE_LIMITED")
        task = self._tasks.get(key)
        if task is None:
            if len(self._tasks) >= MAX_CONCURRENT_MARKETS:
                return failure("ERROR", limitations=("Public observation capacity is busy.",))
            if self._budget is not None:
                self._waiters[key] = ProviderWaiters(self._budget)
            deadline = monotonic() + REQUEST_BUDGET_SECONDS
            task = self._tasks[key] = asyncio.create_task(
                self._refresh(key, metadata, financial, namespace_records, deadline),
            )
        # Cancellation of one caller does not cancel a shared bounded acquisition.
        try:
            waiters = self._waiters.get(key)
            with waiters.waiting() if waiters else nullcontext():
                capture = await asyncio.wait_for(asyncio.shield(task), REQUEST_BUDGET_SECONDS)
            now = _utc(self._clock())
            if any(point.captured_at > now for point in capture.points):
                return failure("ERROR", limitations=("Public observation receipt is future-dated.",),
                               failure_code="INVALID_DATA")
            return capture
        except TimeoutError:
            return failure("ERROR", limitations=("Public observation timed out.",), failure_code="TIMEOUT")

    async def _refresh(self, key, metadata, financial, namespace_records, deadline):
        try:
            waiters = self._waiters.get(key)
            capture, limited = await asyncio.to_thread(
                self._collect, metadata, financial, namespace_records, key[0], deadline, waiters,
            )
            if limited:
                self._backoff_until = monotonic() + RATE_LIMIT_BACKOFF
            if not self._closed and capture.status == "AVAILABLE":
                first_receipt = min(point.captured_at for point in capture.points)
                self._cache[key] = (first_receipt + timedelta(seconds=10), capture)
                self._cache.move_to_end(key)
                while len(self._cache) > CACHE_CAPACITY:
                    self._cache.popitem(last=False)
            return capture
        finally:
            self._tasks.pop(key, None)
            self._waiters.pop(key, None)

    def _collect(self, metadata, financial, namespace_records, catalog_fingerprint, deadline, waiters):
        client = self._client if self._client is not None else _OfficialPublicClient(
            self._network, budget=self._budget, owner="advisory", cancel=waiters.cancelled)
        identity = metadata.identity

        def acquired(status, points=(), limitations=(), **fields):
            return OfficialPerpObservation._from_acquisition(
                metadata, status, points, limitations, catalog_fingerprint=catalog_fingerprint, **fields,
            )

        def request(operation, **kwargs):
            response = client.request(operation, identity, deadline, **kwargs)
            if monotonic() >= deadline:
                raise DiscoveryFailure("TIMEOUT")
            return response, _utc(self._clock())

        try:
            raw, current_at = request("metaAndAssetCtxs")
            points, issues = _current(raw, metadata, current_at, financial, namespace_records)
        except _UnsupportedQuoteUnit as exc:
            return acquired("UNSUPPORTED", limitations=(str(exc),), failure_code="UNSUPPORTED_METADATA"), False
        except Exception as exc:
            code = "INVALID_DATA" if isinstance(exc, (ValueError, KeyError)) else _failure_code(exc)
            status = {"MISSING_METADATA": "INSUFFICIENT_DATA", "UNSUPPORTED_METADATA": "UNSUPPORTED"}.get(code, "ERROR")
            return acquired(status, limitations=(f"Public current context: {code}",),
                            failure_code=code), code == "RATE_LIMITED"

        if not {"FUNDING", "MARK_PRICE", "ORACLE_PRICE"} <= {point.category for point in points}:
            return acquired("INSUFFICIENT_DATA", points, issues), False

        # The documented mark, oracle and in-market book relationship gives
        # relative like-for-like prices for the qualified contract. Resolve the
        # market's collateral token as a consistency check, never as its price unit.
        if (financial is None or financial.collateral_status != "SOURCE_OBSERVED"
                or financial.collateral.observed_at > current_at):
            issues.insert(0, "Public price-unit compatibility requires current collateral metadata.")
            return acquired("INSUFFICIENT_DATA", points, issues), False

        current_ms = _epoch_ms(current_at)
        start = current_ms - HISTORY_HOURS * 3_600_000
        for operation in ("l2Book", "fundingHistory"):
            try:
                if operation == "l2Book":
                    raw, captured_at = request(operation)
                    point = _book(raw, identity, captured_at, current_at)
                else:
                    raw, captured_at = request(operation, start=start, end=current_ms)
                    point = _history(raw, identity, captured_at, start, current_ms)
                if point is None:
                    issues.append("No funding history in the requested window.")
                else:
                    points.append(point)
            except Exception as exc:
                code = "INVALID_DATA" if isinstance(exc, ValueError) else _failure_code(exc)
                issues.append(str(exc) if isinstance(exc, _UnsupportedQuoteUnit)
                              else f"{operation} unavailable: {code}")
                if code in {"NAMESPACE_CONFLICT", "NETWORK_MISMATCH"}:
                    return acquired("ERROR", limitations=issues, failure_code=code), False
                if code == "RATE_LIMITED":
                    return acquired("AVAILABLE", points, issues, failure_code=code), True
                if code == "TIMEOUT":
                    break
        return acquired("AVAILABLE", points, issues), False

    async def close(self):
        self._closed = True
        for waiters in self._waiters.values():
            waiters.retire()
        self._cache.clear()
        if self._tasks:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._tasks.values())))
