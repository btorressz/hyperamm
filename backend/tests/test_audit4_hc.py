"""Deterministic public transport and operational recovery regressions."""
import asyncio
import copy
import json
from datetime import timedelta
from threading import Event
from time import monotonic

import pytest

from app.config import Settings
from app.market_data.live_stream_models import LiveMarketStreamEnvelope
from app.market_data.models import MarketConnectionState, MarketDataMode
from app.market_data.service import MarketDataService
from app.simulation.market_profiles import MARKETS
from test_integration import sdk_market  # noqa: F401
from test_phase152_live_streams import create, eventually
from test_phase181_market_discovery import WireResponse, meta, row


def emit_current(sdk, clock, market, *, book=True, context=True):
    if book:
        raw = copy.deepcopy(sdk.books[market])
        raw['time'] = int(clock().timestamp() * 1000)
        sdk.emit(market, 'l2Book', {'data': raw})
    if context:
        sdk.emit(market, 'activeAssetCtx')


@pytest.mark.parametrize(('market', 'component'), [('BTC', 'l2'), ('ETH', 'perp'), ('SOL', 'metadata')])
async def test_isolated_native_stall_preserves_sibling_generation(market, component):
    service, sdk, clock = create(live_stream_l2_stale_after_seconds=.05,
                                 live_stream_perp_stale_after_seconds=.05,
                                 live_observation_metadata_stale_after_seconds=1)
    queue = None
    try:
        await service.start()
        await eventually(lambda: all(s.barrier and s.context for s in service.states.values()))
        for name in MARKETS:
            emit_current(sdk, clock, name)
        await eventually(lambda: all(service.snapshot(m).observation_status == 'AVAILABLE' for m in MARKETS))
        await asyncio.sleep(.06)  # Pass the original global startup grace.
        other = next(name for name in MARKETS if name != market)
        queue = service.subscribe(other)
        queue.get_nowait()
        clock.advance(.1)
        for name in MARKETS:
            emit_current(sdk, clock, name, book=name != market or component != 'l2',
                         context=name != market or component != 'perp')
        if component == 'metadata':
            state = service.states[market]
            state.metadata = state.metadata.model_copy(update={'observed_at': clock() - timedelta(seconds=2)})
        await asyncio.sleep(.4)
        assert len(sdk.clients) == 1, f"{len(sdk.clients)} SDK generations"
        frame = LiveMarketStreamEnvelope.model_validate_json(queue.get_nowait())
        assert frame.connection_generation == 1 and frame.observation_status == 'AVAILABLE'
        assert all(service.snapshot(m).observation_status == 'AVAILABLE' for m in MARKETS if m != market)
        if component != 'metadata':
            assert service.snapshot(market).observation_status != 'AVAILABLE'
    finally:
        if queue is not None:
            service.unsubscribe(queue)
        await service.close()


@pytest.mark.parametrize("traffic", ["book", "context", "alternating"])
async def test_operational_burst_bounds_loop_wakeups_and_retires_old_callback(sdk_market, monkeypatch, traffic):
    adapter = sdk_market.adapter
    if traffic != "book":
        adapter.add_perp_listener(lambda _: None)
    entered, release = asyncio.Event(), asyncio.Event()
    states = []
    service = MarketDataService(adapter.market, MarketDataMode.LIVE)
    service._adapter = adapter

    async def accept(snapshot):
        await service._accept(snapshot)
        states.append(snapshot)
        if len(states) == 1:
            entered.set()
            await release.wait()

    task = asyncio.create_task(adapter.start(accept))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        loop = asyncio.get_running_loop()
        schedule = loop.call_soon_threadsafe
        scheduled = []

        def count(callback, *args, **kwargs):
            scheduled.append(callback)
            return schedule(callback, *args, **kwargs)

        monkeypatch.setattr(loop, 'call_soon_threadsafe', count)
        handles = sdk_market.instances[0].ws_manager.active_subscriptions
        old = handles['l2Book:eth'][0].callback
        for i in range(512):
            if traffic == "book" or (traffic == "alternating" and i % 2 == 0):
                old({'channel': 'l2Book', 'data': sdk_market.book()})
            else:
                handles['activeAssetCtx:eth'][0].callback({
                    'channel': 'activeAssetCtx', 'data': {'coin': 'ETH', 'ctx': sdk_market.ctx}})
        assert len(scheduled) == 1
        assert adapter._ingress.metrics()[0] <= adapter.INGRESS_CAPACITY
        assert adapter.ingress_gap
        effective = await service.snapshot()
        assert effective.connection_state == MarketConnectionState.DEGRADED and effective.stale
        assert effective.book is None
        assert adapter._ingress.metrics() == (8, 1, 504)
        release.set()
        await eventually(lambda: any(s.connection_state == MarketConnectionState.DEGRADED for s in states))
        assert any(s.stale and s.book is None for s in states)
        await eventually(lambda: len(sdk_market.instances) >= 2 and states[-1].connection_state == 'CONNECTED')
        count_before = len(scheduled)
        old({'data': sdk_market.book()})
        assert len(scheduled) == count_before
    finally:
        release.set()
        await adapter.stop()
        await task


async def test_legal_catalog_cannot_burst_over_process_ceiling(monkeypatch, record_property):
    from requests.adapters import HTTPAdapter
    from app import main

    calls = []

    def send(_adapter, request, **_options):
        payload = json.loads(request.body)
        calls.append(payload["type"])
        if payload["type"] == "perpDexs":
            body = [None, *({"name": f"d{i:02}"} for i in range(63))]
        elif payload["type"] == "spotMeta":
            body = {"universe": [], "tokens": []}
        else:
            dex = payload["dex"]
            body = {**meta(row(f"{dex}:BTC" if dex else "BTC")), "collateralToken": 0}
        return WireResponse(body=json.dumps(body).encode())

    monkeypatch.setattr(HTTPAdapter, "send", send)
    monkeypatch.setattr(main, "settings", Settings(_env_file=None, market_universe_enabled=True))
    async with main.lifespan(main.app):
        state = main.app.state
        result = await state.market_universe_discovery.catalog()
        weight = 20 * len(calls)
        record_property("attempted_calls", len(calls))
        record_property("attempted_weight", weight)
        assert weight <= 900, f"{len(calls)} sends and {weight} weight"
        assert result.availability in {"PARTIAL", "UNAVAILABLE"}
        assert len(result.namespaces) == 64 and result.catalog is None
        assert any(item.error == "RATE_LIMITED" for item in result.namespaces)
        assert state.hyperliquid_budget.metrics()["rolling_weight"] == weight


class MonotonicClock:
    now = 0.

    def __call__(self):
        return self.now


@pytest.mark.parametrize(("at", "admitted"), [(59.999, False), (60., True), (60.001, True)])
def test_rolling_window_boundary(at, admitted):
    from app.market_data.provider_budget import HyperliquidBudget, ProviderAdmissionError

    clock = MonotonicClock()
    budget = HyperliquidBudget(60, clock=clock)
    for _ in range(3):
        budget.request("operational", "meta", 1, lambda _: None)
    clock.now = at
    if admitted:
        budget.request("native_repair", "l2Book", at + .0005, lambda _: None)
        assert budget.metrics()["rolling_weight"] == 2
    else:
        with pytest.raises(ProviderAdmissionError, match="RATE_LIMITED"):
            budget.request("native_repair", "l2Book", at + .0005, lambda _: pytest.fail("denied request sent"))
        assert budget.metrics()["rolling_weight"] == 60


def test_mixed_owners_reservation_and_funding_weight():
    from app.market_data.provider_budget import HyperliquidBudget, ProviderAdmissionError

    clock = MonotonicClock()
    budget = HyperliquidBudget(120, clock=clock)
    budget.request("discovery", "meta", 1, lambda _: None)
    budget.request("advisory", "metaAndAssetCtxs", 1, lambda _: None)
    budget.request("advisory", "l2Book", 1, lambda _: None)
    # A 24-row response is charged at the conservative maximum for the returned count.
    budget.request("advisory", "fundingHistory", 1, lambda _: [{"time": i} for i in range(24)])
    budget.request("summary", "metaAndAssetCtxs", 1, lambda _: None)
    assert budget.metrics()["rolling_weight"] == 84
    with pytest.raises(ProviderAdmissionError, match="RATE_LIMITED"):
        budget.request("summary", "metaAndAssetCtxs", 1, lambda _: pytest.fail("ordinary reserve bypass"))
    budget.request("operational", "spotMeta", 1, lambda _: None)
    budget.request("native_repair", "l2Book", 1, lambda _: None)
    counts = budget.metrics()["counts"]
    assert counts["advisory", "fundingHistory", "reserved_weight"] == 45
    assert counts["advisory", "fundingHistory", "charged_weight"] == 22
    assert counts["advisory", "l2Book", "charged_weight"] == 2
    assert counts["native_repair", "l2Book", "charged_weight"] == 2
    assert budget.metrics()["rolling_weight"] == 106


async def test_aged_ordinary_waiter_admitted_ahead_of_live_work():
    from app.market_data.provider_budget import HyperliquidBudget, ProviderAdmissionError

    clock = MonotonicClock()
    budget = HyperliquidBudget(60, clock=clock)
    for _ in range(3):
        budget.request("native_stream", "meta", 1, lambda _: None)
    clock.now = 58.
    ordinary = asyncio.create_task(asyncio.to_thread(
        budget.request, "advisory", "fundingHistory", 62., lambda _: None))
    await eventually(lambda: budget.metrics()["waiting"] == 1)
    clock.now = 59.5
    live = asyncio.create_task(asyncio.to_thread(budget.request, "operational", "meta", 62., lambda _: None))
    try:
        await eventually(lambda: budget.metrics()["waiting"] == 2)
        clock.now = 60.
        budget.wake()
        await asyncio.wait_for(ordinary, 2)
        assert budget.metrics()["rolling_weight"] == 45
        with pytest.raises(ProviderAdmissionError, match="RATE_LIMITED"):
            await asyncio.wait_for(live, 2)
        assert budget.metrics()["counts"]["operational", "meta", "capacity"] == 1
        with pytest.raises(ProviderAdmissionError, match="RATE_LIMITED"):
            budget.request("operational", "meta", 60., lambda _: pytest.fail("expired request sent"))
        assert budget.metrics()["counts"]["operational", "meta", "deadline"] == 1
    finally:
        budget.close()
        await asyncio.gather(ordinary, live, return_exceptions=True)


async def test_shutdown_cancels_queued_while_timed_out_send_stays_charged():
    from app.market_data.provider_budget import HyperliquidBudget, ProviderAdmissionError

    clock = MonotonicClock()
    budget = HyperliquidBudget(60, clock=clock)
    entered, release = Event(), Event()

    def send(_remaining):
        entered.set()
        assert release.wait(5)

    running = asyncio.create_task(asyncio.to_thread(budget.request, "operational", "meta", 5, send))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(running), .01)
        assert budget.metrics()["active"] == 1 and budget.metrics()["rolling_weight"] == 20
        for _ in range(2):
            budget.request("native_stream", "meta", 5, lambda _: None)
        queued = asyncio.create_task(asyncio.to_thread(
            budget.request, "native_repair", "l2Book", 65, lambda _: pytest.fail("shutdown request sent")))
        await eventually(lambda: budget.metrics()["waiting"] == 1)
        budget.close()
        with pytest.raises(ProviderAdmissionError, match="CLOSED"):
            await asyncio.wait_for(queued, 2)
        assert budget.metrics()["rolling_weight"] == 60 and budget.metrics()["waiting"] == 0
    finally:
        budget.close()
        release.set()
        with pytest.raises(ProviderAdmissionError, match="CLOSED"):
            await running
    assert budget.metrics()["active"] == 0 and budget.metrics()["rolling_weight"] == 60


async def test_summary_last_waiter_cancellation_before_send(monkeypatch):
    from requests.adapters import HTTPAdapter
    from app.market_data import market_summaries
    from app.market_data.provider_budget import HyperliquidBudget

    clock = MonotonicClock()
    monkeypatch.setattr(market_summaries, "monotonic", clock)
    monkeypatch.setattr(HTTPAdapter, "send", lambda *_a, **_k: pytest.fail("cancelled refresh sent"))
    budget = HyperliquidBudget(80, clock=clock)
    summary = market_summaries.MarketSummaryObservations("MAINNET", budget=budget, timer=clock)
    for _ in range(4):
        budget.request("operational", "meta", 1, lambda _: None)
    clock.now = 55.
    task = asyncio.create_task(summary._acquire(("MAINNET", "", "catalog"), (), None, False))
    try:
        await eventually(lambda: budget.metrics()["waiting"] == 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await eventually(lambda: not summary._tasks)
        clock.now = 60.
        assert budget.metrics()["counts"]["summary", "metaAndAssetCtxs", "cancelled"] == 1
        assert budget.metrics()["counts"]["summary", "metaAndAssetCtxs", "issued"] == 0
    finally:
        await summary.close()


def test_shared_http_429_backoff_and_exact_network_urls(monkeypatch):
    from requests.adapters import HTTPAdapter
    from app.market_data import market_universe_discovery as discovery
    from app.market_data.provider_budget import HyperliquidBudget, ProviderAdmissionError

    calls = []
    clock = MonotonicClock()
    monkeypatch.setattr(discovery, "monotonic", clock)

    def send(_adapter, request, **_options):
        calls.append(request.url)
        if len(calls) == 1:
            return WireResponse(status=429, headers={"Retry-After": "45"})
        return WireResponse(body=b"[null]")

    monkeypatch.setattr(HTTPAdapter, "send", send)
    budget = HyperliquidBudget(clock=clock)
    main = discovery.OfficialMetadataClient("MAINNET", budget=budget)
    testnet = discovery.OfficialMetadataClient("TESTNET", budget=budget, owner="summary")
    with pytest.raises(discovery.DiscoveryFailure, match="RATE_LIMITED"):
        main("perpDexs", "", 5)
    clock.now = 44.999
    with pytest.raises(ProviderAdmissionError, match="RATE_LIMITED"):
        testnet("perpDexs", "", 47)
    assert len(calls) == 1
    clock.now = 45.
    assert testnet("perpDexs", "", 47) == [None]
    assert calls == ["https://api.hyperliquid.xyz/info", "https://api.hyperliquid-testnet.xyz/info"]
    assert budget.metrics()["rolling_weight"] == 40


async def test_actual_sdk_native_and_operational_bootstrap_and_repair_share_budget(sdk_market, monkeypatch):
    from hyperliquid import info as sdk
    from requests import Session
    from types import SimpleNamespace
    from app.market_data.live_streams import LiveMarketStreamService, utcnow
    from app.market_data.provider_budget import HyperliquidBudget
    from test_phase151_live_markets import book, native, contexts

    # Keep the existing fixture socket and use the unmodified SDK Info implementation.
    monkeypatch.setattr(sdk, "Info", sdk.Info.__base__)
    calls = []

    def post(session, url, *, json, timeout):
        assert url == "https://api.hyperliquid.xyz/info" and session.max_redirects == 0
        operation = json["type"]
        calls.append(operation)
        if operation == "l2Book":
            data = book(json["coin"])
            data["time"] = int(utcnow().timestamp() * 1000)
        else:
            data = {"meta": native(), "spotMeta": {"universe": [], "tokens": []},
                    "metaAndAssetCtxs": contexts()}[operation]
        return SimpleNamespace(status_code=200, json=lambda: data)

    monkeypatch.setattr(Session, "post", post)
    adapter = sdk_market.adapter
    adapter._budget = budget = HyperliquidBudget()
    adapter.add_perp_listener(lambda _: None)
    streams = LiveMarketStreamService(Settings(_env_file=None, live_streams_enabled=True,
        live_observations_enabled=True, live_stream_queue_capacity=2), budget=budget)
    states = []

    async def capture(state):
        states.append(state)

    task = asyncio.create_task(adapter.start(capture))
    try:
        await eventually(lambda: states and states[-1].connection_state == MarketConnectionState.CONNECTED)
        assert calls == ["spotMeta", "meta", "metaAndAssetCtxs", "l2Book"]
        assert budget.metrics()["rolling_weight"] == 62
        info = adapter._info
        await streams.start()
        await eventually(lambda: all(s.barrier and s.context for s in streams.states.values()))
        assert budget.metrics()["rolling_weight"] == 108
        generation = streams.states["BTC"].generation
        stream_info = streams._client.info
        raw = book("BTC")
        raw["time"] = int(utcnow().timestamp() * 1000)
        for _ in range(3):
            stream_info.ws_manager.ws.emit("l2Book", raw)
        await eventually(lambda: budget.metrics()["counts"]["native_repair", "l2Book", "charged_weight"] == 2)
        assert budget.metrics()["rolling_weight"] == 110
        assert streams.states["BTC"].generation == generation
        assert states[-1].connection_state == MarketConnectionState.CONNECTED
    finally:
        await streams.close()
        await adapter.stop()
        await task
    assert not info.ws_manager.is_alive() and not info.ws_manager.ping_sender.is_alive()
    assert budget.metrics()["active"] == 0


async def test_native_scoped_repair_keeps_processing_siblings_and_drains_on_disconnect():
    service, sdk, clock = create()
    entered, release = Event(), Event()
    try:
        await service.start()
        await eventually(lambda: all(s.barrier and s.context for s in service.states.values()))
        client = sdk.clients[0]
        book = client.book

        def block(market):
            if market == "BTC":
                entered.set()
                assert release.wait(4)
            return book(market)

        client.book = block
        for market in MARKETS:
            emit_current(sdk, clock, market)
        await eventually(lambda: all(service.snapshot(m).observation_status == "AVAILABLE" for m in MARKETS))
        for _ in range(service.queue_capacity + 1):
            emit_current(sdk, clock, "BTC", context=False)
        assert await asyncio.to_thread(entered.wait, 2)
        assert service.snapshot("BTC").observation_status != "AVAILABLE"
        before = service.snapshot("ETH").order_book.source_timestamp
        clock.advance(.01)
        emit_current(sdk, clock, "ETH")
        await eventually(lambda: service.snapshot("ETH").order_book.source_timestamp > before)
        assert service.snapshot("ETH").observation_status == "AVAILABLE"
        assert service.snapshot("SOL").observation_status == "AVAILABLE"
        client.broken = True
        await eventually(lambda: service.snapshot("ETH").status.connection_state == "RECONNECTING")
        assert not client.closed and len(sdk.clients) == 1
        emit_current(sdk, clock, "ETH")
        assert service.snapshot("ETH").order_book is None
        release.set()
        await eventually(lambda: len(sdk.clients) >= 2)
        assert client.closed
    finally:
        release.set()
        await service.close()
    assert all(client.closed for client in sdk.clients)
    assert not any(thread.is_alive() for thread in service._pool._threads)


async def test_verified_native_binding_change_retires_generation():
    service, sdk, clock = create(live_observation_metadata_stale_after_seconds=.05)
    try:
        await service.start()
        await eventually(lambda: all(s.barrier and s.context for s in service.states.values()))
        first = sdk.clients[0]
        # Same known market at a different index is a shared SDK mapping change.
        for metadata in (sdk.metadata, sdk.contexts[0]):
            universe = metadata["universe"]
            universe[1], universe[2] = universe[2], universe[1]
        context = sdk.contexts[1]
        context[1], context[2] = context[2], context[1]
        clock.advance(.06)
        emit_current(sdk, clock, "ETH")
        await eventually(lambda: len(sdk.clients) >= 2 and service.states["SOL"].metadata.asset_index == 2)
        assert first.closed and service.states["SOL"].generation == 2
        assert service.snapshot("SOL").observation_status != "AVAILABLE"
    finally:
        await service.close()


async def test_one_unavailable_subscription_leaves_other_owned_market_handles():
    service, sdk, clock = create()
    factory = sdk.factory

    def fail_one(*args):
        client = factory(*args)
        subscribe = client.subscribe

        def subscribe_one(market, kind, callback):
            if market == "BTC" and kind == "activeAssetCtx":
                raise ValueError("fixture subscription rejected")
            return subscribe(market, kind, callback)

        client.subscribe = subscribe_one
        return client

    service._factory = fail_one
    try:
        await service.start()
        await eventually(lambda: all(service.states[m].barrier for m in ("ETH", "SOL")))
        for market in ("ETH", "SOL"):
            emit_current(sdk, clock, market)
        await eventually(lambda: all(service.snapshot(m).observation_status == "AVAILABLE" for m in ("ETH", "SOL")))
        assert len(sdk.clients) == 1
        assert service.snapshot("BTC").status.last_error_code == "SDK_UNAVAILABLE"
        assert service.snapshot("BTC").observation_status == "UNAVAILABLE"
    finally:
        await service.close()


def test_sdk_429_unrecognized_body_enforces_shared_cooldown(monkeypatch):
    from hyperliquid.info import Info
    from requests import Response
    from requests.adapters import HTTPAdapter
    from app.market_data.provider_budget import HyperliquidBudget, ProviderAdmissionError

    clock = MonotonicClock()
    budget = HyperliquidBudget(clock=clock)

    def send(_adapter, request, **_options):
        response = Response()
        response.status_code = 429
        response.headers["Retry-After"] = "42"
        response._content = b'{"unexpected": "provider error format"}'
        response.request, response.url = request, request.url
        return response

    monkeypatch.setattr(HTTPAdapter, "send", send)
    info = Info.__new__(Info)
    budget.bind_sdk(info, "operational", 10)
    try:
        with pytest.raises(ProviderAdmissionError, match="RATE_LIMITED"):
            Info.__init__(info, "https://api.hyperliquid.xyz", skip_ws=True, timeout=10)
        clock.now = 41.
        with pytest.raises(ProviderAdmissionError, match="RATE_LIMITED"):
            budget.request("discovery", "perpDexs", 43., lambda _: pytest.fail("shared cooldown bypass"))
        assert budget.metrics()["rolling_weight"] == 20
    finally:
        info.session.close()


async def test_denied_operational_sdk_bootstrap_opens_no_socket(sdk_market, monkeypatch):
    from hyperliquid import info as sdk
    from hyperliquid import websocket_manager
    from requests import Session
    from app.market_data.provider_budget import HyperliquidBudget

    monkeypatch.setattr(sdk, "Info", sdk.Info.__base__)
    monkeypatch.setattr(websocket_manager, "WebsocketManager", lambda *_: pytest.fail("denied socket opened"))
    monkeypatch.setattr(Session, "post", lambda *_a, **_k: pytest.fail("denied SDK REST send"))
    budget = sdk_market.adapter._budget = HyperliquidBudget(60)
    for _ in range(3):
        budget.request("native_stream", "meta", monotonic() + 1, lambda _: None)
    states = []

    async def capture(state):
        states.append(state)

    adapter = sdk_market.adapter
    task = asyncio.create_task(adapter.start(capture))
    try:
        await eventually(lambda: any(s.connection_state == MarketConnectionState.DEGRADED for s in states))
        assert budget.metrics()["counts"]["operational", "spotMeta", "capacity"] == 1
        assert all(s.connection_state != MarketConnectionState.CONNECTED for s in states)
    finally:
        await adapter.stop()
        await task
