"""Process-wide admission for official public Hyperliquid Info requests."""
from collections import Counter, deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Condition, Event
from time import monotonic

WINDOW_SECONDS = 60
HTTP_429_BACKOFF = 30
# Info time-range pagination is capped at 500 returned items. Round up each group of 20.
FUNDING_PAGE_LIMIT = 500
WEIGHTS = {
    "l2Book": 2, "meta": 20, "spotMeta": 20, "perpDexs": 20, "metaAndAssetCtxs": 20,
    "fundingHistory": 20 + FUNDING_PAGE_LIMIT // 20,
}
OWNERS = frozenset({"discovery", "summary", "advisory", "research_metadata",
                    "native_rest", "native_stream", "native_repair", "operational"})
LIVE_OWNERS = frozenset({"native_stream", "native_repair", "operational"})


class ProviderAdmissionError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(eq=False)
class _Waiter:
    weight: int
    live: bool
    since: float


@dataclass
class _Attempt:
    at: float
    weight: int
    live: bool


class ProviderWaiters:
    """A shared acquisition can issue while at least one application waiter owns it."""

    def __init__(self, budget):
        self._budget = budget
        self._readers = 0
        self.cancelled = Event()

    def retire(self):
        self.cancelled.set()
        self._budget.wake()

    @contextmanager
    def waiting(self):
        self._readers += 1
        try:
            yield
        finally:
            self._readers -= 1
            if not self._readers:
                self.retire()


class HyperliquidBudget:
    """Admit at the send boundary on existing workers, with no background task."""

    def __init__(self, ceiling=900, *, clock=monotonic):
        if type(ceiling) is not int or not 60 <= ceiling <= 1150:
            raise ValueError("invalid Hyperliquid request-weight ceiling")
        self.ceiling = ceiling
        self.reserve = min(80, ceiling // 4)
        self._clock = clock
        self._condition = Condition()
        self._attempts = deque()
        self._waiting = []
        self._cooldown = 0.
        self._closed = False
        self._active = 0
        self._variable_active = 0
        self._rolling_peak = 0
        self._metrics = Counter()

    def close(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def wake(self):
        """Recheck an owner's cancellation signal or an advanced fixture clock."""
        with self._condition:
            self._condition.notify_all()

    def _usage(self, now):
        while self._attempts and now - self._attempts[0].at >= WINDOW_SECONDS:
            self._attempts.popleft()
        return (sum(attempt.weight for attempt in self._attempts),
                sum(attempt.weight for attempt in self._attempts if not attempt.live))

    def cache_hit(self, owner):
        if owner in OWNERS:
            with self._condition:
                self._metrics[owner, "cache_reuse"] += 1

    def metrics(self):
        with self._condition:
            usage, _ = self._usage(self._clock())
            return {"rolling_weight": usage, "peak_rolling_weight": self._rolling_peak,
                    "waiting": len(self._waiting), "active": self._active,
                    "counts": self._metrics.copy()}

    def rate_limited(self, retry_after=None):
        delay = HTTP_429_BACKOFF
        if isinstance(retry_after, str) and len(retry_after) <= 64:
            if retry_after.isascii() and retry_after.isdecimal():
                delay = max(delay, int(retry_after))
            else:
                try:
                    delay = max(delay, (parsedate_to_datetime(retry_after) -
                                        datetime.now(timezone.utc)).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    pass
        with self._condition:
            self._cooldown = max(self._cooldown, self._clock() + delay)
            self._condition.notify_all()

    def _admit(self, owner, operation, deadline, cancel):
        weight = WEIGHTS[operation]
        live = owner in LIVE_OWNERS
        prefix = (owner, operation)
        with self._condition:
            waiter = _Waiter(weight, live, self._clock())

            def deny(code, reason):
                self._metrics[(*prefix, reason)] += 1
                raise ProviderAdmissionError(code)

            # Leave four waiting slots for established live owners.
            if len(self._waiting) >= (24 if live else 20):
                deny("RATE_LIMITED", "queue_full")
            self._waiting.append(waiter)
            try:
                while True:
                    now = self._clock()
                    if self._closed or (cancel is not None and cancel.is_set()):
                        deny("CLOSED", "cancelled")
                    if now >= deadline:
                        deny("RATE_LIMITED", "deadline")
                    if now < self._cooldown:
                        # Fail fast in every owner so no queue accumulates across a 429.
                        deny("RATE_LIMITED", "cooldown")

                    used, ordinary = self._usage(now)
                    ordinary_cap = self.ceiling - self.reserve
                    candidates = [entry for entry in self._waiting
                                  if entry.live or ordinary + entry.weight <= ordinary_cap]
                    # FIFO for live requests and for ordinary work aged a second.
                    # Once eligible ordinary work ages in the queue, hold available
                    # capacity for it even if a smaller live request could fit first.
                    first = min(candidates, key=lambda entry: (not (entry.live or now - entry.since >= 1),
                                                               entry.since), default=None)
                    if first is waiter and used + weight <= self.ceiling:
                        attempt = _Attempt(now, weight, live)
                        self._attempts.append(attempt)
                        self._active += 1
                        self._variable_active += operation == "fundingHistory"
                        self._rolling_peak = max(self._rolling_peak, used + weight)
                        self._metrics[(*prefix, "issued")] += 1
                        self._metrics[(*prefix, "reserved_weight")] += weight
                        return attempt, deadline - now

                    next_expiry = self._attempts[0].at + WINDOW_SECONDS if self._attempts else now
                    capacity_blocked = used + weight > self.ceiling or (not live and ordinary + weight > ordinary_cap)
                    if capacity_blocked and next_expiry >= deadline and not self._variable_active:
                        deny("RATE_LIMITED", "capacity")
                    self._condition.wait(min(.1, deadline - now))
            finally:
                self._metrics[(*prefix, "wait_ms")] += round((self._clock() - waiter.since) * 1000)
                self._waiting.remove(waiter)
                self._condition.notify_all()

    def request(self, owner, operation, deadline, send, *, cancel=None):
        if type(owner) is not str or type(operation) is not str or owner not in OWNERS or operation not in WEIGHTS:
            raise ProviderAdmissionError("UNSUPPORTED_METADATA")
        attempt, remaining = self._admit(owner, operation, deadline, cancel)
        weight = attempt.weight
        try:
            response = send(remaining)
            if operation == "fundingHistory" and isinstance(response, list) and len(response) <= FUNDING_PAGE_LIMIT:
                weight = 20 + (len(response) + 19) // 20
            with self._condition:
                if self._closed or (cancel is not None and cancel.is_set()):
                    raise ProviderAdmissionError("CLOSED")
            return response
        finally:
            # Never refund failed or timed-out sends. Only a successfully parsed,
            # documented response count can release unused funding reservation.
            with self._condition:
                attempt.weight = weight
                self._active -= 1
                self._variable_active -= operation == "fundingHistory"
                self._metrics[owner, operation, "charged_weight"] += weight
                self._condition.notify_all()

    def bind_sdk(self, info, owner, timeout, *, deadline=None, cancel=None):
        """Guard SDK /info, including calls inside Info.__init__."""
        post = info.post

        def issue(path, payload=None):
            if path != "/info" or not isinstance(payload, dict):
                raise ProviderAdmissionError("UNSUPPORTED_METADATA")

            def send(remaining):
                # Install the hook before SDK parsing. An intermediary can emit
                # a 429 body that does not match the SDK error schema.
                session = info.session
                session.max_redirects = 0
                original_timeout = info.timeout
                info.timeout = min(timeout, remaining)
                limited = False

                def observe(response, **_):
                    nonlocal limited
                    if response.status_code == 429:
                        self.rate_limited(response.headers.get("Retry-After"))
                        limited = True
                    return response

                session.hooks["response"].append(observe)
                try:
                    return post(path, payload)
                except Exception as exc:
                    if limited:
                        raise ProviderAdmissionError("RATE_LIMITED") from None
                    if getattr(exc, "status_code", None) == 429:
                        headers = getattr(exc, "header", None) or getattr(exc, "error_data", None)
                        self.rate_limited(headers.get("Retry-After") if hasattr(headers, "get") else None)
                    raise
                finally:
                    session.hooks["response"].remove(observe)
                    info.timeout = original_timeout

            until = self._clock() + timeout
            if deadline is not None:
                until = min(deadline, until)
            return self.request(owner() if callable(owner) else owner, payload.get("type"), until, send, cancel=cancel)

        info.post = issue
