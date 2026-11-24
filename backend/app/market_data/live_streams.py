"""Owned public SDK streams. No operational runtime, reference or signing edge."""
from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event
from uuid import uuid4

from app.market_data.history import BoundedIngress, MAX_WIRE_BYTES
from app.market_data.history import bounded_callback_wire as bounded_callback_wire
from app.market_data.hyperliquid import HyperliquidMarketDataAdapter
from app.market_data.hyperliquid_metadata import validate_native_metadata
from app.market_data.live_models import LiveMarketMetadata, financial_decimal
from app.market_data.live_observations import (open_read_only_info, normalize_book,
    normalize_context, context_observation_values, book_economic_identity, classify)
from app.market_data.perp_context import normalize_active_asset_ctx
from app.market_data.live_stream_models import (StreamBookObservation, StreamPerpObservation,
    LiveMarketStreamStatus, LiveStreamSnapshot, LiveMarketStreamEnvelope, LiveHistoryPoint)
from app.market_data.live_history import LiveObservationHistory
from app.simulation.market_profiles import MARKETS

log = logging.getLogger(__name__)
SUBSCRIBER_QUEUE_CAPACITY = 8


def utcnow():
    return datetime.now(timezone.utc)


class SDKObservationClient:
    """One serialized worker owns sessions, six handles and partial SDK initialization."""
    def __init__(self, timeout, shutdown_timeout, *, budget=None, cancel=None):
        self.timeout, self.shutdown_timeout = timeout, shutdown_timeout
        self.info = self.bootstrap = None
        self.budget, self.cancel = budget, cancel
        self.owner = 'native_stream'
        self.handles = []

    def open(self):
        if self.info is not None or self.bootstrap is not None:
            raise RuntimeError('SDK client already owns resources')
        from hyperliquid.info import Info
        from hyperliquid.utils.constants import MAINNET_API_URL
        self.bootstrap = open_read_only_info({'universe': []}, self.timeout, budget=self.budget,
                                              owner=self.owner, cancel=self.cancel)
        metadata = self.bootstrap.meta(dex='')
        received = utcnow()
        validate_native_metadata(metadata, received)
        self.bootstrap.session.close()
        self.bootstrap = None
        # Own the object BEFORE its constructor starts the manager/ping threads.
        self.info = Info.__new__(Info)
        if self.budget is not None:
            self.budget.bind_sdk(self.info, lambda: self.owner, self.timeout, cancel=self.cancel)
        Info.__init__(self.info, MAINNET_API_URL, skip_ws=False, meta=metadata,
                      spot_meta={'universe': [], 'tokens': []}, timeout=self.timeout)
        for item in validate_native_metadata(metadata, received):
            if item.metadata_status != 'EXCHANGE_VERIFIED':
                continue
            if (self.info.name_to_coin.get(item.market) != item.market or
                self.info.coin_to_asset.get(item.market) != item.asset_index or
                self.info.asset_to_sz_decimals.get(item.asset_index) != item.sz_decimals):
                raise ValueError('SDK native mapping mismatch')
        return metadata, received

    def ready(self):
        return HyperliquidMarketDataAdapter._socket_ready(self.info)

    def subscribe(self, market, kind, callback):
        if market not in MARKETS or kind not in {'l2Book', 'activeAssetCtx'}:
            raise ValueError('unsupported observation subscription')
        subscription = {'type': kind, 'coin': market}
        if any(existing == subscription for existing, _ in self.handles):
            raise RuntimeError('duplicate observation subscription')
        handle = self.info.subscribe(subscription.copy(), callback)
        self.handles.append((subscription, handle))
        return handle

    def book(self, market):
        raw = self.info.l2_snapshot(market)
        return raw, utcnow()

    def context(self):
        raw = self.info.meta_and_asset_ctxs()
        return raw, utcnow()

    def close(self):
        errors = []
        if self.info is not None:
            for subscription, handle in self.handles:
                try:
                    self.info.unsubscribe(subscription.copy(), handle)
                except Exception:
                    # A dead socket can reject unsubscribe; verified manager teardown
                    # still retires all of that connection's handles.
                    log.warning('Observation subscription release required socket teardown')
            manager = getattr(self.info, 'ws_manager', None)
            if manager is not None:
                try:
                    # SDK 0.24 stop() joins the ping sender without a deadline.
                    # Use its same stop primitives, then verify BOTH bounded joins.
                    manager.stop_event.set()
                    manager.ws.close()
                except Exception:
                    errors.append('socket stop failed')
                for thread in (manager, getattr(manager, 'ping_sender', None)):
                    if thread is not None:
                        try:
                            if thread.ident is not None:
                                thread.join(timeout=self.shutdown_timeout)
                            if thread.is_alive():
                                errors.append('SDK thread still running')
                        except Exception:
                            errors.append('SDK thread join failed')
        for client in (self.bootstrap, self.info):
            session = getattr(client, 'session', None)
            if session is not None:
                try:
                    session.close()
                except Exception:
                    errors.append('session close failed')
        if errors:
            raise RuntimeError('Read-only SDK cleanup incomplete')
        self.bootstrap = self.info = None
        self.handles.clear()


@dataclass
class MarketState:
    metadata: LiveMarketMetadata
    connection: str = 'DISABLED'
    subscription: str = 'NONE'
    generation: int = 0
    book: StreamBookObservation | None = None
    context: StreamPerpObservation | None = None
    watermark: tuple | None = None
    seen: set = field(default_factory=set)
    barrier: bool = False
    reconnects: int = 0
    rejected: int = 0
    dropped: int = 0
    error: str | None = None
    recovery_after: float = 0
    recovery_failures: int = 0
    metadata_gap: bool = False


class LiveMarketStreamService:
    def __init__(self, settings, *, client_factory=SDKObservationClient, clock=utcnow, budget=None):
        self.enabled = settings.live_streams_enabled and settings.live_observations_enabled
        self.queue_capacity = settings.live_stream_queue_capacity
        self.max_subscribers = settings.live_stream_max_subscribers
        self.l2_budget = settings.live_stream_l2_stale_after_seconds
        self.perp_budget = settings.live_stream_perp_stale_after_seconds
        self.metadata_budget = settings.live_observation_metadata_stale_after_seconds
        self.http_timeout = settings.live_observation_http_timeout_seconds
        self.connect_timeout = settings.live_stream_connect_timeout_seconds
        self.retry_initial = settings.live_stream_reconnect_initial_seconds
        self.retry_max = settings.live_stream_reconnect_max_seconds
        self.shutdown_timeout = settings.live_stream_shutdown_timeout_seconds
        self.future_tolerance = settings.live_observation_future_tolerance_seconds
        self.max_levels = settings.live_observation_book_levels
        self.instance_id = str(uuid4())
        self._factory, self._clock, self._budget = client_factory, clock, budget
        self._binding = {}
        self._repair = self._generation_cancel = None
        self.history = LiveObservationHistory(self.instance_id, settings.live_stream_history_max_points)
        self.states = {m: MarketState(LiveMarketMetadata(market=m,
            metadata_status='UNAVAILABLE', source='NONE'),
            connection='CONNECTING' if self.enabled else 'DISABLED') for m in MARKETS}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='live-stream-sdk')
        self._runner = self._client = self._inbox = self._close_task = None
        self._stop = asyncio.Event()
        self._closed = False
        self._generation = self._sequence = 0
        self._subscribers = {}
        self._slow_subscribers = set()
        self._empty_subscribers = asyncio.Event()
        self._empty_subscribers.set()

    def _market(self, market):
        if not isinstance(market, str) or market not in MARKETS:
            raise ValueError('unsupported live market')
        return self.states[market]

    async def _call(self, method, *args):
        future = asyncio.get_running_loop().run_in_executor(self._pool, method, *args)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # Cancellation does not stop synchronous SDK work. Keep its ownership.
            while not future.done():
                try:
                    await asyncio.shield(future)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not future.cancelled():
                future.exception()
            raise

    async def start(self):
        if self._closed or self._runner is not None:
            raise RuntimeError('stream observer already started or closed')
        if self.enabled:
            self._runner = asyncio.create_task(self._run(), name='live-stream-observer')

    async def _pause(self, seconds):
        try:
            await asyncio.wait_for(self._stop.wait(), seconds)
        except TimeoutError:
            pass

    def snapshot(self, market):
        state = self._market(market)
        now = self._clock()
        def age(stamp):
            return (now - stamp).total_seconds() if stamp else None
        def fresh(value, budget, tolerance=0):
            return 'UNAVAILABLE' if value is None else 'FRESH' if -tolerance <= value <= budget else 'STALE'
        ba = age(state.book.source_timestamp) if state.book else None
        ca = age(state.context.observed_at) if state.context else None
        ma = age(state.metadata.observed_at)
        bs, cs = fresh(ba, self.l2_budget, self.future_tolerance), fresh(ca, self.perp_budget)
        ms = fresh(ma, self.metadata_budget) if state.metadata.metadata_status == 'EXCHANGE_VERIFIED' else 'UNAVAILABLE'
        if state.book and fresh(age(state.book.observed_at), self.l2_budget) != 'FRESH':
            bs = 'STALE'
        connection = state.connection
        if connection == 'CONNECTED' and 'STALE' in (bs, cs, ms):
            connection = 'STALE'
        if connection == 'DISABLED':
            observation = 'DISABLED'
        elif connection in {'STOPPED', 'CONNECTING', 'RECONNECTING', 'UNAVAILABLE'}:
            observation = 'UNAVAILABLE'
        elif 'STALE' in (bs, cs, ms):
            observation = 'STALE'
        elif self._inbox is not None and self._inbox.has_loss(market):
            connection, observation = 'DEGRADED', 'DEGRADED'
        elif state.error and (state.book is not None or state.context is not None):
            observation = 'DEGRADED'
        elif connection == 'CONNECTED' and bs == cs == ms == 'FRESH':
            observation = 'AVAILABLE'
        elif state.book is not None or state.context is not None:
            observation = 'DEGRADED' if state.error else 'PARTIAL'
        else:
            observation = 'UNAVAILABLE'
        status = LiveMarketStreamStatus(market=market, connection_state=connection,
            observer_instance_id=self.instance_id, evaluated_at=now,
            l2_stale_after_seconds=self.l2_budget, perp_stale_after_seconds=self.perp_budget,
            metadata_stale_after_seconds=self.metadata_budget,
            subscription_state=state.subscription, connection_generation=state.generation,
            last_l2_source_timestamp=state.book.source_timestamp if state.book else None,
            last_l2_observed_at=state.book.observed_at if state.book else None,
            last_perp_observed_at=state.context.observed_at if state.context else None,
            l2_age_seconds=ba, perp_age_seconds=ca, metadata_age_seconds=ma,
            l2_freshness=bs, perp_freshness=cs, metadata_freshness=ms,
            reconnect_count=state.reconnects, rejected_update_count=state.rejected,
            dropped_update_count=state.dropped, last_error_code=state.error)
        return LiveStreamSnapshot(market=market, status=status, observation_status=observation,
            metadata=state.metadata.model_copy(update={'metadata_status': 'STALE'}) if ms == 'STALE' else state.metadata,
            order_book=state.book, perp_context=state.context)

    def _envelope(self, market):
        payload = self.snapshot(market)
        self._sequence += 1  # Publication ordering only, never an exchange sequence.
        return LiveMarketStreamEnvelope(market=market, observer_instance_id=self.instance_id,
            connection_generation=payload.status.connection_generation, sequence=self._sequence,
            emitted_at=self._clock(), observation_status=payload.observation_status, payload=payload)

    def publish(self, market):
        wire = self._envelope(market).model_dump_json()
        if len(wire.encode('utf-8')) > MAX_WIRE_BYTES:
            raise RuntimeError('normalized stream envelope exceeds bound')
        for queue, selected in tuple(self._subscribers.items()):
            if selected != market or queue in self._slow_subscribers:
                continue
            if queue.full():
                # Close slow subscriber; it must establish a new snapshot boundary.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
                # Retain admission until the socket owner releases its queue.
                self._slow_subscribers.add(queue)
            else:
                queue.put_nowait(wire)

    def subscribe(self, market):
        self._market(market)
        if not self.enabled or self._closed:
            raise RuntimeError('stream observation disabled or stopped')
        if len(self._subscribers) >= self.max_subscribers:
            raise RuntimeError('stream subscriber limit reached')
        queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_CAPACITY)
        # Recompute current status rather than sending unqualified cached evidence.
        queue.put_nowait(self._envelope(market).model_dump_json())
        self._subscribers[queue] = market
        self._empty_subscribers.clear()
        return queue

    def unsubscribe(self, queue):
        self._subscribers.pop(queue, None)
        self._slow_subscribers.discard(queue)
        if not self._subscribers:
            self._empty_subscribers.set()

    def _ready_state(self, state):
        if state.barrier and state.book is not None and state.context is not None and state.seen == {'l2Book', 'activeAssetCtx'}:
            state.connection, state.subscription, state.error = 'CONNECTED', 'OBSERVED', None

    def accept(self, market, kind, raw, generation, observed_at, *, source='OFFICIAL_SDK_WEBSOCKET', publish_update=True):
        state = self._market(market)
        publish = (lambda: self.publish(market)) if publish_update else (lambda: None)
        if self._closed or generation != state.generation or self._inbox is None or self._inbox.closed:
            return False  # Retired callback cannot mutate even counters/current errors.
        if isinstance(raw, dict) and raw.get('channel') == 'subscriptionResponse':
            return False  # An acknowledgement is not usable economic evidence.
        try:
            if not isinstance(raw, dict) or ('channel' in raw and raw['channel'] != kind):
                raise ValueError('stream channel mismatch')
            if observed_at > self._clock():
                raise ValueError('future receipt timestamp')
            data = raw.get('data', raw)
            if not isinstance(data, dict) or any(
                key in data and (type(data[key]) is not int or data[key] != state.metadata.asset_index)
                for key in ('asset', 'assetIndex')
            ):
                raise ValueError('stream asset identity mismatch')
            if kind == 'l2Book':
                if not state.barrier:
                    return False
                book = normalize_book(raw.get('data', raw), state.metadata, observed_at,
                    future_tolerance=self.future_tolerance, max_levels=self.max_levels)
                if (observed_at - book.source_timestamp).total_seconds() > self.l2_budget:
                    raise ValueError('stale L2')
                identity = book_economic_identity(raw.get('data', raw))
                previous = state.watermark
                if previous and book.source_timestamp < previous[0]:
                    state.rejected += 1
                    state.error = 'REPLAY'
                    publish()
                    return False
                if previous and book.source_timestamp == previous[0]:
                    if identity != previous[1]:
                        state.error = 'CONFLICT'
                        raise ValueError('same source time conflicts')
                    # Identical packets never renew source or receipt or history.
                    if source == 'OFFICIAL_SDK_WEBSOCKET':
                        state.seen.add(kind)
                        self._ready_state(state)
                        publish()
                    return False
                state.watermark = (book.source_timestamp, identity)
                state.book = StreamBookObservation(**book.model_dump(exclude={'source'}), source=source)
                point = dict(kind='L2', source_timestamp=book.source_timestamp, midpoint=book.midpoint,
                    best_bid=book.best_bid, best_ask=book.best_ask, spread=book.spread)
            elif kind == 'activeAssetCtx':
                if state.context is not None and observed_at < state.context.observed_at:
                    state.rejected += 1
                    state.error = 'REPLAY'
                    publish()
                    return False  # Buffered receipt must not replace a later acquisition.
                if data.get('coin') != market or not isinstance(data.get('ctx'), dict):
                    raise ValueError('context market mismatch')
                for name in ('markPx', 'oraclePx', 'funding', 'openInterest'):
                    financial_decimal(data['ctx'].get(name))
                for name in ('midPx', 'premium'):
                    if data['ctx'].get(name) is not None:
                        financial_decimal(data['ctx'][name])
                normalized = normalize_active_asset_ctx(raw, market, updated_at=observed_at)
                state.context = StreamPerpObservation(market=market, observed_at=observed_at, source=source,
                    **context_observation_values(normalized))
                point = dict(kind='PERP_CONTEXT', source_timestamp=None, mark=normalized.mark_price,
                    oracle=normalized.oracle_price, funding=normalized.funding_rate,
                    open_interest=normalized.open_interest_base)
            else:
                raise ValueError('unsupported stream channel')
            if source == 'OFFICIAL_SDK_WEBSOCKET':
                state.seen.add(kind)
            self._ready_state(state)
            self.history.append(LiveHistoryPoint(market=market, observer_instance_id=self.instance_id,
                connection_generation=generation, source=source, observed_at=observed_at,
                observation_status=self.snapshot(market).observation_status, **point))
            publish()
            return True
        except (ValueError, TypeError, KeyError, ArithmeticError, AttributeError):
            state.rejected += 1
            state.error = 'CONFLICT' if state.error == 'CONFLICT' else 'INVALID_DATA'
            state.connection = 'DEGRADED'
            state.seen.discard(kind)
            if kind == 'l2Book':
                state.barrier = False
            self.history.gap(market)
            # Keep the last accepted values and their original timestamps for
            # historical display. Invalid input cannot overwrite that evidence.
            publish()
            return False

    async def _bootstrap_book(self, market, *, scoped=False):
        state = self.states[market]
        state.barrier = False
        try:
            raw, received = await self._call(self._client.book, market)
            if self._stop.is_set() or self._inbox.closed:
                return
            state.barrier = True
            self.accept(market, 'l2Book', raw, state.generation, received, source='OFFICIAL_SDK_REST')
            # Only a fresh accepted event or an identical watermark establishes
            # the boundary; retaining older evidence does not establish recovery.
            book = normalize_book(raw, state.metadata, received,
                future_tolerance=self.future_tolerance, max_levels=self.max_levels)
            if (not state.barrier or (book.source_timestamp, book_economic_identity(raw)) != state.watermark
                or not -self.future_tolerance <= (received-book.source_timestamp).total_seconds() <= self.l2_budget):
                raise ValueError('missing valid recovery book')
            if state.book is None:
                state.book = StreamBookObservation(**book.model_dump(exclude={'source'}), source='OFFICIAL_SDK_REST')
            if scoped:
                self.publish(market)
        except BaseException:
            state.barrier = False
            raise

    @staticmethod
    def _identity(item):
        return item.asset_index, item.sz_decimals, item.listed

    @staticmethod
    def _metadata(item, received):
        return LiveMarketMetadata(market=item.market, metadata_status=item.metadata_status,
            source='OFFICIAL_SDK_NATIVE_META', sz_decimals=item.sz_decimals, asset_index=item.asset_index,
            listed=item.listed, observed_at=received)

    def _check_binding(self, metadata):
        if {item.market: self._identity(item) for item in metadata} != self._binding:
            raise ConnectionError('native SDK asset bindings changed')

    async def _refresh_metadata(self):
        raw, received = await self._call(self._client.context)
        if self._stop.is_set() or self._inbox.closed:
            return
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise ValueError('invalid native metadata response')
        metadata = validate_native_metadata(raw[0], received)
        self._check_binding(metadata)
        for item in metadata:
            self.states[item.market].metadata = self._metadata(item, received)

    async def _recover(self, market):
        # SDK 0.24 registers the callback before it attempts a subscription send.
        # Keep the working transport and owned handles during REST repair; a
        # duplicate subscribe on an uncertain handle would accumulate callbacks.
        client, inbox = self._client, self._inbox
        if isinstance(client, SDKObservationClient):
            client.owner = 'native_repair'
        try:
            if market is None:
                await self._refresh_metadata()
            else:
                await self._bootstrap_book(market, scoped=True)
        finally:
            if isinstance(client, SDKObservationClient):
                client.owner = 'native_stream'
            inbox.event.set()

    def _finish_repair(self, market, now, failures):
        try:
            self._repair.result()
        except ConnectionError:
            raise
        except Exception as exc:
            count = min(failures + 1, 8)
            if market is not None:
                state = self.states[market]
                state.recovery_failures = count
                state.connection = 'DEGRADED'
                if state.error != 'OVERFLOW':
                    state.error = self._failure(exc)
            delay = min(max(.25, self.retry_max), max(.25, self.retry_initial) * 2 ** count)
            if classify(exc) == 'RATE_LIMITED':
                delay = max(delay, 30)
            return now + delay, count
        if market is not None:
            self.states[market].recovery_failures = 0
        return now + max(.25, self.retry_initial), 0

    @staticmethod
    def _failure(exc):
        if isinstance(exc, TimeoutError):
            return 'TIMEOUT'
        code = classify(exc)
        return 'NETWORK_ERROR' if isinstance(exc, ConnectionError) or code == 'CLOSED' else code

    async def _attempt(self):
        self._generation += 1
        generation = self._generation
        self._inbox = BoundedIngress(asyncio.get_running_loop(), self.queue_capacity, self._clock, MARKETS)
        inbox = self._inbox
        self._generation_cancel = Event()
        for market, state in self.states.items():
            state.generation = generation
            state.connection, state.subscription = 'CONNECTING', 'NONE'
            state.metadata = LiveMarketMetadata(market=market, metadata_status='UNAVAILABLE', source='NONE')
            state.error = None
            state.book = state.context = None
            state.barrier = False
            state.recovery_after = state.recovery_failures = 0
            state.metadata_gap = False
            state.seen.clear()
            if generation > 1:
                state.reconnects += 1
                self.history.gap(market)
            self.publish(market)
        if self._budget is not None and isinstance(self._factory, type) and issubclass(self._factory, SDKObservationClient):
            self._client = self._factory(self.http_timeout, self.shutdown_timeout,
                                         budget=self._budget, cancel=self._generation_cancel)
        else:
            self._client = self._factory(self.http_timeout, self.shutdown_timeout)
        raw_meta, received = await self._call(self._client.open)
        metadata = validate_native_metadata(raw_meta, received)
        eligible = []
        for item in metadata:
            state = self.states[item.market]
            identity = self._identity(item)
            if item.market in self._binding and identity != self._binding[item.market]:
                state.watermark = None
            self._binding[item.market] = identity
            state.metadata = self._metadata(item, received)
            if item.metadata_status == 'EXCHANGE_VERIFIED':
                eligible.append(item.market)
                state.connection = 'BOOTSTRAPPING'
            else:
                state.connection, state.error = 'UNAVAILABLE', 'NOT_LISTED'
                self.publish(item.market)
        if not eligible:
            raise ValueError('no supported native listings')
        deadline = asyncio.get_running_loop().time() + self.connect_timeout
        while not self._client.ready():
            if self._stop.is_set():
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError('socket connect timeout')
            await self._pause(.1)
        if self._stop.is_set():
            return
        for market in tuple(eligible):
            try:
                for kind in ('l2Book', 'activeAssetCtx'):
                    if self._stop.is_set():
                        return
                    await self._call(self._client.subscribe, market, kind,
                        lambda raw, m=market, k=kind: inbox.offer(m, k, generation, raw))
                self.states[market].subscription = 'REQUESTED'
            except ConnectionError:
                raise
            except Exception:
                # The SDK cannot roll back an ambiguous registration safely.
                # Keep its callback bounded and exclude that market for this generation.
                if not self._client.ready():
                    raise ConnectionError('SDK connection unavailable during subscription') from None
                eligible.remove(market)
                state = self.states[market]
                state.connection, state.error = 'UNAVAILABLE', 'SDK_UNAVAILABLE'
                self.publish(market)
        if not eligible:
            raise ConnectionError('no native subscriptions available')
        for market in eligible:
            if self._stop.is_set():
                return
            try:
                await self._bootstrap_book(market)
            except Exception:
                self.states[market].connection = 'DEGRADED'
                self.states[market].error = 'INVALID_DATA'
                self.publish(market)
        try:
            raw_context, context_at = await self._call(self._client.context)
            if not isinstance(raw_context, (list, tuple)) or len(raw_context) != 2:
                raise ValueError('invalid native context response')
            context_metadata = validate_native_metadata(raw_context[0], context_at)
        except Exception:
            raw_context, context_at = None, self._clock()
        else:
            self._check_binding(context_metadata)
        for market in eligible:
            state = self.states[market]
            try:
                context = normalize_context(raw_context, state.metadata, context_at)
                # Reuse strict REST mapping and actual financial normalizer; keep REST source.
                index = state.metadata.asset_index
                self.accept(market, 'activeAssetCtx', {'coin': market, 'ctx': raw_context[1][index]},
                    generation, context.observed_at, source='OFFICIAL_SDK_REST')
            except Exception:
                state.error, state.connection = 'INVALID_DATA', 'DEGRADED'
                self.publish(market)
        loop = asyncio.get_running_loop()
        started = loop.time()
        repair_market = None
        metadata_after = metadata_failures = 0
        while not self._stop.is_set():
            if not self._client.ready():
                raise ConnectionError('SDK connection not ready')
            now = loop.time()
            if self._repair is not None and self._repair.done():
                failures = metadata_failures if repair_market is None else self.states[repair_market].recovery_failures
                retry_at, count = self._finish_repair(repair_market, now, failures)
                if repair_market is None:
                    metadata_after, metadata_failures = retry_at, count
                else:
                    self.states[repair_market].recovery_after = retry_at
                self._repair = None
            values, losses = inbox.take()
            repair_candidates = []
            metadata_stale = False
            for market in eligible:
                state = self.states[market]
                if losses[market]:
                    state.dropped += losses[market]
                    state.connection, state.error, state.barrier = 'DEGRADED', 'OVERFLOW', False
                    state.book = state.context = None
                    state.seen.clear()
                    self.history.gap(market)
                else:
                    for kind, old_generation, wire, observed in values[market]:
                        # Keep sibling publication and history running during a repair.
                        self.accept(market, kind, json.loads(wire), old_generation, observed, publish_update=False)
                status = self.snapshot(market).status
                expired_metadata = status.metadata_freshness == 'STALE'
                if expired_metadata and not state.metadata_gap:
                    self.history.gap(market)
                state.metadata_gap = expired_metadata
                metadata_stale |= expired_metadata
                if now - started > max(self.l2_budget, self.perp_budget):
                    lost_book = status.l2_freshness != 'FRESH' and state.barrier
                    lost_context = status.perp_freshness != 'FRESH' and 'activeAssetCtx' in state.seen
                    if lost_book or lost_context:
                        state.connection, state.error = 'DEGRADED', 'TIMEOUT'
                        self.history.gap(market)
                    if lost_book:
                        state.barrier = False
                        state.seen.discard('l2Book')
                    if lost_context:
                        state.seen.discard('activeAssetCtx')
                if not state.barrier and state.recovery_after <= now:
                    repair_candidates.append(market)
                self.publish(market)
            if self._repair is None:
                if metadata_stale and metadata_after <= now:
                    repair_market = None
                    self._repair = asyncio.create_task(self._recover(None), name='native-metadata-repair')
                elif repair_candidates:
                    repair_market = min(repair_candidates, key=lambda m: self.states[m].recovery_after)
                    self._repair = asyncio.create_task(self._recover(repair_market), name='native-book-repair')
            try:
                await asyncio.wait_for(inbox.event.wait(), timeout=.25)
            except TimeoutError:
                pass

    async def _run(self):
        retry = self.retry_initial
        while not self._stop.is_set():
            code = None
            started = asyncio.get_running_loop().time()
            try:
                await self._attempt()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                code = self._failure(exc)
            finally:
                if self._inbox is not None:
                    self._inbox.close()
                for market, state in self.states.items():
                    state.connection = 'STOPPED' if self._stop.is_set() else 'RECONNECTING'
                    state.subscription = 'RETIRED'
                    state.barrier = False
                    state.book = state.context = None
                    state.error = code
                    self.publish(market)
                if self._generation_cancel is not None:
                    self._generation_cancel.set()
                    if self._budget is not None:
                        self._budget.wake()
                if self._repair is not None:
                    self._repair.cancel()
                    await asyncio.gather(self._repair, return_exceptions=True)
                    self._repair = None
                if self._client is not None:
                    try:
                        await self._call(self._client.close)
                    except Exception:
                        for market, state in self.states.items():
                            state.connection, state.error = 'UNAVAILABLE', 'CLEANUP_ERROR'
                            self.publish(market)
                        # Retain client; no replacement until shutdown retries cleanup.
                        return
                    self._client = None
            if not self._stop.is_set():
                if asyncio.get_running_loop().time() - started > max(self.l2_budget, self.perp_budget) * 2:
                    retry = self.retry_initial
                await self._pause(max(retry, 30 if code in {'RATE_LIMITED', 'FORBIDDEN'} else 0))
                retry = min(retry * 2, self.retry_max)

    async def _drain(self):
        if self._runner is not None:
            try:
                await asyncio.shield(self._runner)
            except asyncio.CancelledError:
                if not self._runner.cancelled():
                    raise
        if self._client is not None:
            try:
                await self._call(self._client.close)
            except Exception:
                raise RuntimeError('Read-only stream SDK cleanup incomplete') from None
            self._client = None
        await asyncio.to_thread(self._pool.shutdown, wait=True, cancel_futures=True)
        # ASGI socket owners join their structured send/receive operations before
        # unsubscribe. Retain the drain task if the shutdown caller times out.
        await self._empty_subscribers.wait()
        for market, state in self.states.items():
            state.connection, state.subscription = 'STOPPED', 'RETIRED'
            state.book = state.context = None

    async def close(self):
        self._closed = True
        self._stop.set()
        if self._generation_cancel is not None:
            self._generation_cancel.set()
            if self._budget is not None:
                self._budget.wake()
        for state in self.states.values():
            state.connection = 'STOPPED'
        if self._inbox is not None:
            self._inbox.close()
        for queue in tuple(self._subscribers):
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(None)
        if self._close_task is None or (self._close_task.done() and self._close_task.exception() is not None):
            self._close_task = asyncio.create_task(self._drain(), name='live-stream-shutdown')
        try:
            await asyncio.wait_for(asyncio.shield(self._close_task), self.shutdown_timeout)
        except TimeoutError:
            raise RuntimeError('Stream shutdown incomplete; owned SDK worker still draining') from None
