"""Lifespan-owned discovery of public Hyperliquid perpetual metadata."""
from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import cached_property
from threading import Event
from time import monotonic
from typing import Callable, Literal

from pydantic import Field, field_validator, model_validator
from requests import Request
from urllib3.exceptions import HTTPError, TimeoutError as HTTPTimeout

from app.market_data.live_observations import classify
from app.market_data.market_universe_contracts import (
    MAX_CATALOG_RECORDS,
    DiscoveryEligibility,
    MarketInstrumentIdentity,
    MarketUniverseCatalog,
    MarketUniverseEvidence,
    MarketUniverseMetadata,
    Network,
    UtcDatetime,
    _strict_bool,
    evaluate_discovery,
)

log = logging.getLogger(__name__)
MAX_NAMESPACES = 64  # Includes Core.
MAX_PROVIDER_BYTES = 1_048_576
MAX_JSON_DEPTH = 32
MAX_CONCURRENCY = 3
HTTP_TIMEOUT = 5.0
REFRESH_TIMEOUT = 15.0
CACHE_SECONDS = 60
RATE_LIMIT_BACKOFF = 30
RESPONSE_VERSION = "phase181-v1"

FailureCode = Literal[
    "DISABLED", "CLOSED", "TIMEOUT", "RATE_LIMITED", "FORBIDDEN", "UPSTREAM_ERROR",
    "NETWORK_ERROR", "SDK_UNAVAILABLE", "CLEANUP_ERROR", "MISSING_METADATA",
    "INVALID_DATA", "NETWORK_MISMATCH", "NAMESPACE_CONFLICT", "UNSUPPORTED_METADATA",
    "RESPONSE_TOO_LARGE", "CATALOG_CAPACITY",
]
Availability = Literal["AVAILABLE", "PARTIAL", "STALE", "UNAVAILABLE", "DISABLED"]


class MetadataCheck(MarketUniverseEvidence):
    status: Literal["REFRESHED", "FAILED", "SKIPPED"]
    observed_at: UtcDatetime | None = None
    error: FailureCode | None = None

    @model_validator(mode="after")
    def validate_observation(self):
        if self.status == "REFRESHED":
            if self.observed_at is None or self.error is not None:
                raise ValueError("successful refresh requires an observation without an error")
        elif self.observed_at is not None or self.error is None:
            raise ValueError("unsuccessful refresh requires a bounded reason")
        return self


class NamespaceCheck(MetadataCheck):
    dex: str = Field(max_length=32)


class MarketUniverseResponse(MarketUniverseEvidence):
    schema_version: Literal["phase181-v1"] = RESPONSE_VERSION
    network: Network
    availability: Availability
    catalog: MarketUniverseCatalog | None = None
    catalog_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    eligibility: tuple[DiscoveryEligibility, ...] = Field(default=(), max_length=MAX_CATALOG_RECORDS)
    evaluated_at: UtcDatetime
    max_age_seconds: int = Field(ge=1, le=86400)
    inventory: MetadataCheck | None = None
    namespaces: tuple[NamespaceCheck, ...] = Field(default=(), max_length=MAX_NAMESPACES)
    error: FailureCode | None = None
    limitations: tuple[Literal["METADATA_ONLY"], Literal["NO_PAPER_RESEARCH"], Literal["NO_EXECUTION"]] = (
        "METADATA_ONLY", "NO_PAPER_RESEARCH", "NO_EXECUTION",
    )
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"
    paper_research_eligible: Literal[False] = False
    execution_eligible: Literal[False] = False

    _validate_flags = field_validator(
        "read_only", "paper_research_eligible", "execution_eligible", mode="before"
    )(_strict_bool)


class DiscoveryFailure(Exception):
    def __init__(self, code: FailureCode):
        super().__init__(code)
        self.code = code


def _failure_code(exc: Exception) -> FailureCode:
    if isinstance(exc, DiscoveryFailure):
        return exc.code
    if isinstance(exc, (TimeoutError, HTTPTimeout)):
        return "TIMEOUT"
    if isinstance(exc, HTTPError):
        return "NETWORK_ERROR"
    return classify(exc)


def _unique_object(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise DiscoveryFailure("INVALID_DATA")
    return obj


def _reject_constant(_value):
    raise DiscoveryFailure("INVALID_DATA")


def _validate_json_depth(value, depth=1):
    if depth > MAX_JSON_DEPTH:
        raise DiscoveryFailure("INVALID_DATA")
    if isinstance(value, dict):
        value = value.values()
    elif not isinstance(value, list):
        return
    for child in value:
        _validate_json_depth(child, depth + 1)


class OfficialMetadataClient:
    """Use SDK Info methods with a size-limited, public-only HTTP transport."""

    def __init__(self, network: Network, *, endpoint: str | None = None):
        from hyperliquid.utils.constants import MAINNET_API_URL, TESTNET_API_URL

        official = {"MAINNET": MAINNET_API_URL, "TESTNET": TESTNET_API_URL}.get(network)
        if official is None or (endpoint is not None and endpoint != official):
            raise DiscoveryFailure("NETWORK_MISMATCH")
        self.endpoint = official

    def __call__(self, method: Literal["perpDexs", "meta"], dex: str, deadline: float):
        from hyperliquid.info import Info

        info = Info.__new__(Info)
        try:
            # Prevent constructor-side requests, asset mappings, or a WebSocket.
            Info.__init__(info, self.endpoint, skip_ws=True, timeout=HTTP_TIMEOUT,
                          meta={"universe": []}, spot_meta={"universe": [], "tokens": []})
            # Keep the SDK's public /info methods and payload definitions.
            info.post = lambda path, payload: self._post(info.session, path, payload, deadline)
            if method == "perpDexs":
                return info.perp_dexs()
            if method == "meta":
                return info.meta(dex=dex)
            raise DiscoveryFailure("UNSUPPORTED_METADATA")
        finally:
            session = getattr(info, "session", None)
            if session is not None:
                try:
                    session.close()
                except Exception:
                    log.warning("Market-universe SDK session cleanup failed")
                    raise DiscoveryFailure("CLEANUP_ERROR") from None

    def _post(self, session, path, payload, deadline):
        if path != "/info" or payload.get("type") not in {"perpDexs", "meta"}:
            raise DiscoveryFailure("UNSUPPORTED_METADATA")
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise DiscoveryFailure("TIMEOUT")
        url = self.endpoint + path
        request = Request("POST", url, json=payload, headers={
            "Accept": "application/json", "Accept-Encoding": "identity",
        }).prepare()
        environment = session.merge_environment_settings(url, {}, True, None, None)
        # One direct adapter send avoids netrc and Requests' redirect body buffering.
        with session.get_adapter(url).send(
            request, stream=True, timeout=min(HTTP_TIMEOUT, remaining),
            verify=environment["verify"], proxies=environment["proxies"],
        ) as response:
            status = response.status_code
            if status != 200:
                raise DiscoveryFailure({403: "FORBIDDEN", 429: "RATE_LIMITED"}.get(status, "UPSTREAM_ERROR"))
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise DiscoveryFailure("UNSUPPORTED_METADATA")
            length = response.headers.get("Content-Length")
            if length is not None:
                if not length.isascii() or not length.isdecimal():
                    raise DiscoveryFailure("INVALID_DATA")
                if len(length) > 10 or int(length) > MAX_PROVIDER_BYTES:
                    raise DiscoveryFailure("RESPONSE_TOO_LARGE")

            read = getattr(response.raw, "read1", None) or response.raw.read
            body = bytearray()
            while True:
                if monotonic() >= deadline:
                    raise DiscoveryFailure("TIMEOUT")
                chunk = read(min(65536, MAX_PROVIDER_BYTES + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > MAX_PROVIDER_BYTES:
                    raise DiscoveryFailure("RESPONSE_TOO_LARGE")
            if length is not None and len(body) != int(length):
                raise DiscoveryFailure("INVALID_DATA")
            try:
                payload = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                                     parse_constant=_reject_constant)
            except (ValueError, RecursionError):
                raise DiscoveryFailure("INVALID_DATA") from None
            _validate_json_depth(payload)
            return payload


def normalize_inventory(raw, network: Network) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw or raw[0] is not None:
        raise DiscoveryFailure("INVALID_DATA")
    if len(raw) > MAX_NAMESPACES:
        raise DiscoveryFailure("CATALOG_CAPACITY")
    names = {""}
    for row in raw[1:]:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise DiscoveryFailure("INVALID_DATA")
        dex = row["name"]
        if dex in names:
            raise DiscoveryFailure("NAMESPACE_CONFLICT")
        # Apply the same namespace grammar as the canonical identity contract.
        MarketInstrumentIdentity(network=network, instrument_type="HIP3_PERP", dex=dex, instrument_name="0")
        names.add(dex)
    return tuple(sorted(names))


def normalize_metadata(raw, *, network: Network, dex: str,
                       observed_at: datetime) -> tuple[MarketUniverseMetadata, ...]:
    if not isinstance(raw, dict):
        raise DiscoveryFailure("INVALID_DATA")
    if raw.get("network", network) != network:
        raise DiscoveryFailure("NETWORK_MISMATCH")
    if raw.get("dex", dex) != dex:
        raise DiscoveryFailure("NAMESPACE_CONFLICT")
    instrument_type = "HIP3_PERP" if dex else "CORE_PERP"
    if raw.get("instrumentType", instrument_type) != instrument_type:
        raise DiscoveryFailure("UNSUPPORTED_METADATA")
    universe = raw.get("universe")
    if universe is None or universe == []:
        raise DiscoveryFailure("MISSING_METADATA")
    if not isinstance(universe, list):
        raise DiscoveryFailure("INVALID_DATA")
    if len(universe) > MAX_CATALOG_RECORDS:
        raise DiscoveryFailure("CATALOG_CAPACITY")

    records = []
    names = set()
    for index, entry in enumerate(universe):
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise DiscoveryFailure("INVALID_DATA")
        if entry.get("network", network) != network:
            raise DiscoveryFailure("NETWORK_MISMATCH")
        if entry.get("dex", dex) != dex:
            raise DiscoveryFailure("NAMESPACE_CONFLICT")
        if entry.get("instrumentType", instrument_type) != instrument_type:
            raise DiscoveryFailure("UNSUPPORTED_METADATA")
        coin = entry["name"]
        if len(coin) > 97:
            raise DiscoveryFailure("INVALID_DATA")
        namespace, separator, instrument_name = coin.partition(":")
        if (dex and (not separator or namespace != dex)) or (not dex and separator):
            raise DiscoveryFailure("NAMESPACE_CONFLICT")
        if not dex:
            instrument_name = coin
        if instrument_name in names:
            raise DiscoveryFailure("NAMESPACE_CONFLICT")
        names.add(instrument_name)
        reported_index = entry.get("universeIndex", index)
        if type(reported_index) is not int or reported_index != index:
            raise DiscoveryFailure("INVALID_DATA")
        delisted = entry.get("isDelisted", False)
        if type(delisted) is not bool:
            raise DiscoveryFailure("INVALID_DATA")

        records.append(MarketUniverseMetadata(
            identity=MarketInstrumentIdentity(
                network=network, instrument_type=instrument_type, dex=dex, instrument_name=instrument_name,
            ),
            source_coin=coin, universe_index=index, sz_decimals=entry["szDecimals"], listed=not delisted,
            metadata_status="EXCHANGE_VERIFIED",
            metadata_source="OFFICIAL_SDK_HIP3_META" if dex else "OFFICIAL_SDK_CORE_META",
            observed_at=observed_at,
        ))
    return tuple(records)


@dataclass(frozen=True)
class Refresh:
    availability: Availability
    inventory: MetadataCheck | None = None
    namespaces: tuple[NamespaceCheck, ...] = ()
    error: FailureCode | None = None

    @property
    def rate_limited(self) -> bool:
        return "RATE_LIMITED" in (
            self.error, self.inventory.error if self.inventory else None, *(item.error for item in self.namespaces),
        )


@dataclass(frozen=True)
class Snapshot:
    catalog: MarketUniverseCatalog
    retired: Event = field(default_factory=Event, compare=False, repr=False)

    @cached_property
    def fingerprint(self) -> str:
        return self.catalog.fingerprint()

    @cached_property
    def observation_range(self) -> tuple[datetime, datetime]:
        times = tuple(record.observed_at for record in self.catalog.records)
        return min(times), max(times)

    @cached_property
    def stale(self) -> Snapshot:
        return Snapshot(MarketUniverseCatalog(records=tuple(
            record.model_copy(update={"metadata_status": "STALE"}) for record in self.catalog.records
        )))


class MarketUniverseDiscovery:
    def __init__(self, *, enabled: bool, network: Network,
                 client: Callable | None = None, cache_seconds: int = CACHE_SECONDS,
                 refresh_timeout: float = REFRESH_TIMEOUT,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        if network not in ("MAINNET", "TESTNET"):
            raise DiscoveryFailure("NETWORK_MISMATCH")
        if type(cache_seconds) is not int or not 1 <= cache_seconds <= 86400:
            raise ValueError("invalid discovery cache duration")
        if not 0 < refresh_timeout <= REFRESH_TIMEOUT:
            raise ValueError("invalid discovery refresh deadline")
        self.enabled, self.network = enabled, network
        self._client = client
        self._cache_seconds, self._refresh_timeout, self._clock = cache_seconds, refresh_timeout, clock
        self._pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY, thread_name_prefix="market-universe")
        self._task: asyncio.Task | None = None
        self._close_task: asyncio.Task | None = None
        self._snapshot: Snapshot | None = None
        self._refresh_result = Refresh("UNAVAILABLE")
        self._deadline = self._expires = 0.0
        self._failed_attempts = 0
        self._closed = False

    async def _collect(self, deadline: float) -> tuple[Refresh, Snapshot | None]:
        def capture(method, dex):
            raw = client(method, dex, deadline)
            return raw, self._clock()

        async def get(method, dex=""):
            if self._closed:
                raise DiscoveryFailure("CLOSED")
            if monotonic() >= deadline:
                raise DiscoveryFailure("TIMEOUT")
            evidence = await asyncio.get_running_loop().run_in_executor(self._pool, capture, method, dex)
            if monotonic() >= deadline:
                raise DiscoveryFailure("TIMEOUT")
            return evidence

        try:
            client = self._client if self._client is not None else OfficialMetadataClient(self.network)
            raw, observed_at = await get("perpDexs")
            dexes = normalize_inventory(raw, self.network)
        except Exception as exc:
            return Refresh("UNAVAILABLE", inventory=MetadataCheck(status="FAILED", error=_failure_code(exc))), None

        inventory = MetadataCheck(status="REFRESHED", observed_at=observed_at)
        checks: dict[str, NamespaceCheck] = {}
        records: list[MarketUniverseMetadata] = []
        targets = iter(dexes)
        rate_limited = over_capacity = False

        async def collect_namespaces():
            nonlocal rate_limited, over_capacity
            for dex in targets:
                if over_capacity or rate_limited:
                    code = "CATALOG_CAPACITY" if over_capacity else "RATE_LIMITED"
                    checks[dex] = NamespaceCheck(dex=dex, status="SKIPPED", error=code)
                    continue
                try:
                    raw, observed_at = await get("meta", dex)
                    rows = normalize_metadata(raw, network=self.network, dex=dex, observed_at=observed_at)
                except Exception as exc:
                    code = _failure_code(exc)
                    checks[dex] = NamespaceCheck(dex=dex, status="FAILED", error=code)
                    if code == "RATE_LIMITED":
                        rate_limited = True
                    if code == "CATALOG_CAPACITY":
                        over_capacity = True
                    continue
                if len(records) + len(rows) > MAX_CATALOG_RECORDS:
                    over_capacity = True
                else:
                    records.extend(rows)
                checks[dex] = NamespaceCheck(dex=dex, status="REFRESHED", observed_at=observed_at)

        worker_count = min(MAX_CONCURRENCY, len(dexes))
        outcomes = await asyncio.gather(*(collect_namespaces() for _ in range(worker_count)), return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
        namespaces = tuple(checks[dex] for dex in dexes)
        if over_capacity:
            return Refresh("UNAVAILABLE", inventory, namespaces, "CATALOG_CAPACITY"), None
        if any(check.status != "REFRESHED" for check in namespaces):
            availability = "PARTIAL" if namespaces[0].status == "REFRESHED" else "UNAVAILABLE"
            return Refresh(availability, inventory, namespaces), None
        return Refresh("AVAILABLE", inventory, namespaces), Snapshot(MarketUniverseCatalog(records=tuple(records)))

    async def _refresh(self, started: float):
        try:
            result, snapshot = await self._collect(self._deadline)
        except Exception as exc:
            result, snapshot = Refresh("UNAVAILABLE", error=_failure_code(exc)), None
        now = monotonic()
        if now >= self._deadline:
            result = Refresh("UNAVAILABLE", result.inventory, result.namespaces, "TIMEOUT")
            snapshot = None
        if snapshot is not None:
            self._snapshot = snapshot
            self._failed_attempts = 0
            self._expires = started + self._cache_seconds
        else:
            self._failed_attempts = min(self._failed_attempts + 1, 5)
            delay = min(60, 5 * 2 ** (self._failed_attempts - 1))
            if result.rate_limited:
                delay = max(RATE_LIMIT_BACKOFF, delay)
            self._expires = now + delay
        self._refresh_result = result

    def _view(self, result: Refresh, snapshot: Snapshot | None) -> MarketUniverseResponse:
        now = self._clock()
        availability = result.availability
        if snapshot is not None and availability == "AVAILABLE":
            oldest, newest = snapshot.observation_range
            if newest > now or now - oldest > timedelta(seconds=self._cache_seconds):
                availability = "STALE"
        if snapshot is not None and availability != "AVAILABLE":
            snapshot = snapshot.stale
        decisions = () if snapshot is None else tuple(
            evaluate_discovery(record, evaluated_at=now, max_age_seconds=self._cache_seconds)
            for record in snapshot.catalog.records
        )
        return MarketUniverseResponse(
            network=self.network, availability=availability, evaluated_at=now, max_age_seconds=self._cache_seconds,
            catalog=snapshot.catalog if snapshot else None,
            catalog_fingerprint=snapshot.fingerprint if snapshot else None,
            eligibility=decisions, inventory=result.inventory, namespaces=result.namespaces, error=result.error,
        )

    async def catalog(self) -> MarketUniverseResponse:
        if self._closed:
            return self._view(Refresh("UNAVAILABLE", error="CLOSED"), None)
        if not self.enabled:
            return self._view(Refresh("DISABLED", error="DISABLED"), None)
        # Task selection/publication has no suspension points on the owning loop.
        now = monotonic()
        if now >= self._expires and (self._task is None or self._task.done()):
            if self._snapshot is not None:
                self._snapshot.retired.set()
            self._deadline = now + self._refresh_timeout
            self._task = asyncio.create_task(self._refresh(now), name="market-universe-refresh")
        if self._task is not None and not self._task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._task), max(0, self._deadline - monotonic()))
            except TimeoutError:
                if not self._closed:
                    return self._view(Refresh("UNAVAILABLE", error="TIMEOUT"), self._snapshot)
        if self._closed:
            return self._view(Refresh("UNAVAILABLE", error="CLOSED"), None)
        return self._view(self._refresh_result, self._snapshot)

    def paper_generation(self, fingerprint: str):
        """Capture the current generation's deadline and thread-safe validity check."""
        snapshot = self._snapshot
        if (self._closed or snapshot is None or snapshot.retired.is_set()
                or snapshot.fingerprint != fingerprint):
            return None
        deadline = snapshot.observation_range[0] + timedelta(seconds=self._cache_seconds)
        return deadline, lambda: not snapshot.retired.is_set()

    async def _drain(self):
        try:
            if self._task is not None:
                await self._task
        finally:
            await asyncio.to_thread(self._pool.shutdown, wait=True, cancel_futures=True)

    async def close(self):
        self._closed = True
        if self._snapshot is not None:
            self._snapshot.retired.set()
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._drain(), name="market-universe-shutdown")
        await asyncio.shield(self._close_task)
