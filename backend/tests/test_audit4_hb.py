import asyncio
from datetime import timedelta
from decimal import Decimal
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
import httpx
from pydantic import ValidationError
import pytest

from app.api import risk, strategy
from app.config import Settings
from app.dependencies import runtime
from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter, VenueReadiness
from app.execution.models import OrderRequest, OrderStatus
from app.execution.order_manager import OrderManager
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.models import MarketDataMode, utcnow
from app.runtime import HyperAmmRuntime
from app.strategy.models import ExecutionMode
from test_execution import FIXTURE_ACCOUNT, FIXTURE_TESTNET, q, venue_adapter, venue_row, venue_update


REQUEST = OrderRequest(client_order_id="new-fixture", market="ETH", side="BID",
                       price=Decimal("2999"), size=Decimal("1"))


async def wait_thread(event):
    assert await asyncio.to_thread(event.wait, 2)


@pytest.mark.parametrize("mode,source", [("DEMO", "synthetic"), ("LIVE", "Mainnet")])
@pytest.mark.parametrize("enabled", [False, True])
def test_initial_testnet_config_rejected(mode, source, enabled):
    options = dict(market_data_mode=mode, execution_mode="TESTNET",
                   enable_hyperliquid_testnet_orders=enabled, market_universe_network="TESTNET",
                   hyperliquid_private_key="redaction-fixture")
    with pytest.raises(ValidationError, match=source) as error:
        Settings(_env_file=None, **options)
    assert "redaction-fixture" not in str(error.value)
    with pytest.raises(PermissionError, match=source):
        HyperAmmRuntime(Settings(_env_file=None).model_copy(update=options))


@pytest.mark.parametrize("case", [
    "demo_verified", "mainnet", "stale_l2", "stale_perp", "stale_reference", "missing",
    "wrong_coin", "wrong_asset", "foreign_venue", "contradictory", "catalog_spoof",
])
async def test_unqualified_evidence_cannot_issue_testnet(case):
    adapter, venue, _ = venue_adapter(stub_source_gate=False)
    adapter._orders.clear()
    rt = HyperAmmRuntime(Settings(_env_file=None, market_universe_network="TESTNET",
                                market_data_mode="LIVE" if case == "mainnet" else "DEMO"))
    if case != "mainnet":
        await rt.market._accept(MockMarketDataAdapter().snapshot_for(1))
        await rt.refresh_once()
        assert rt.references.consensus.confidence_state == "VERIFIED"
        assert rt.authorization.authorized
    past = utcnow() - timedelta(seconds=300)
    if case == "stale_l2":
        rt.market._snapshot.latest_valid_update = past
    elif case == "stale_perp":
        rt.perp_context_service._context.updated_at = past
    elif case == "stale_reference":
        rt.references.updated_at = past
    elif case == "missing":
        rt.references = None
    elif case == "wrong_coin":
        rt.config.market = "BTC"
    elif case == "wrong_asset":
        venue.name_to_asset = lambda market: 120000
    elif case in {"foreign_venue", "contradictory", "catalog_spoof"}:
        rt.market._snapshot.message = case
        rt.market._snapshot.simulated = False
        rt.market._snapshot.mode = "LIVE"
    rt.config.execution_mode = ExecutionMode.TESTNET
    rt.testnet = rt.execution = rt.orders.execution = adapter
    rt.strategy.running = True
    adapter.authority = rt._execution_authority
    with pytest.raises(PermissionError, match="TESTNET execution blocked"):
        await rt._execution_authority(REQUEST)
    with pytest.raises(PermissionError, match="qualified Testnet Core source"):
        await adapter.submit_orders([REQUEST])
    assert venue.transmissions == 0 and not venue.inventory_calls and not venue.callbacks


async def test_http_direct_transition_and_forged_authority_are_rejected():
    rt = HyperAmmRuntime(Settings(_env_file=None, enable_hyperliquid_testnet_orders=True))
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(1))
    await rt.refresh_once()
    rt.strategy.running = True
    app = FastAPI()
    app.include_router(strategy.router)
    app.include_router(risk.router)
    app.dependency_overrides[runtime] = lambda: rt
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for mode in ("DEMO", "LIVE"):
            response = await client.put("/strategy", json={"execution_mode": "TESTNET", "market_data_mode": mode})
            assert response.status_code == 422
            assert "qualified Testnet Core source" in response.json()["detail"]
            assert rt.strategy.running and rt.execution is rt.paper and rt.authorization.authorized
        rt.config.execution_mode = ExecutionMode.TESTNET
        assert (await client.post("/strategy/start")).status_code == 403
        assert (await client.post("/risk/resume")).status_code == 403
        assert (await client.post("/risk/kill")).json()["kill_switch_active"]


async def test_service_start_fails_before_transport_after_programmatic_change(monkeypatch):
    rt = HyperAmmRuntime(Settings(_env_file=None))
    market_start = AsyncMock()
    monkeypatch.setattr(rt.market, "start", market_start)
    rt.config.execution_mode = ExecutionMode.TESTNET
    with pytest.raises(PermissionError, match="synthetic"):
        await rt.start_services()
    market_start.assert_not_awaited()
    assert rt.authorization is None


@pytest.mark.parametrize("scope,coin", [("", "ETH"), ("", "BTC"), ("", "@17"), ("xyz", "xyz:GOLD")])
@pytest.mark.parametrize("interrupted", ["submit", "cancel"])
async def test_restart_quarantines_unknown_inventory_until_fresh_empty_read(scope, coin, interrupted):
    adapter, venue, _ = venue_adapter()
    adapter._orders.clear()
    row = venue_row(999, coin)
    if interrupted == "submit":
        row["cloid"] = adapter._cloid("prior-process").to_raw()
    if scope:
        venue.other_dexs[scope] = [row]
    else:
        venue.opened = [row]
    assert adapter.reconciliation_readiness == VenueReadiness.NOT_CHECKED
    assert adapter.has_unknown_exposure()
    with pytest.raises(RuntimeError, match="unknown active orders"):
        await adapter.reconcile_venue()
    assert (FIXTURE_ACCOUNT, scope) in venue.inventory_calls
    assert adapter.reconciliation_readiness == VenueReadiness.BLOCKED
    assert adapter.unmanaged_order_count == 1
    assert not await adapter.get_open_orders()
    with pytest.raises(RuntimeError, match="unresolved"):
        await OrderManager(adapter).reconcile_locked("ETH", [q()], Decimal(0), Decimal(0), venue_reconciled=True)
    exchange_init = Mock(wraps=adapter._exchange_client)
    adapter._exchange_client = exchange_init
    with pytest.raises(RuntimeError, match="unknown active orders"):
        await adapter.submit_orders([REQUEST])
    exchange_init.assert_not_called()
    assert venue.transmissions == 0 and not venue.cancellations
    venue.opened.clear()
    if scope:
        venue.other_dexs[scope].clear()
    await adapter.reconcile_venue()
    assert adapter.reconciliation_readiness == VenueReadiness.VERIFIED
    assert adapter.unmanaged_order_count == 0 and not adapter.has_unknown_exposure()


async def test_empty_inventory_checked_and_stale_read_never_reports_verified(monkeypatch):
    adapter, venue, _ = venue_adapter()
    adapter._orders.clear()
    await adapter.reconcile_venue()
    assert venue.inventory_calls == [(FIXTURE_ACCOUNT, "")]
    assert adapter.reconciliation_readiness == VenueReadiness.VERIFIED
    monkeypatch.setattr("app.execution.hyperliquid.utcnow", lambda: adapter.last_reconciled_at + timedelta(seconds=11))
    assert adapter.reconciliation_readiness == VenueReadiness.NOT_CHECKED
    assert adapter.has_unknown_exposure()


@pytest.mark.parametrize("rows", [
    None, [venue_row(True)], [venue_row(-1)], [venue_row(), venue_row(price="3000")],
    [venue_row(remaining="NaN")], [venue_row(side="BUY")], [venue_row(price="Infinity")],
    [venue_row(user="different-account")], [venue_row(network="MAINNET")],
    [venue_row(status="not-open")], [venue_row(cloid="unqualified")],
    [venue_row(coin="xyz:GOLD")], [venue_row(reduceOnly=True)],
])
async def test_malformed_or_contradictory_inventory_does_not_publish_readiness(rows):
    adapter, venue, _ = venue_adapter()
    venue.opened = rows
    with pytest.raises(RuntimeError):
        await adapter.reconcile_venue()
    assert adapter.reconciliation_readiness == VenueReadiness.BLOCKED
    assert adapter.unmanaged_order_count is None and adapter.has_unknown_exposure()
    assert venue.transmissions == 0


async def test_known_cloid_reconciles_interrupted_submit_and_checks_fill_progress():
    adapter, venue, order = venue_adapter()
    order.venue_order_id = None
    order.status = OrderStatus.UNKNOWN
    venue.opened = [venue_row(remaining=".6", cloid=adapter._cloid(order.client_order_id).to_raw())]
    await adapter.reconcile_venue()
    assert order.venue_order_id == "123" and order.status == OrderStatus.PARTIALLY_FILLED
    assert order.filled_size == Decimal(".4")
    await adapter.reconcile_venue()
    assert adapter._pending_accounting == {order.client_order_id}
    venue.opened[0]["sz"] = ".7"
    with pytest.raises(RuntimeError):
        await adapter.reconcile_venue()
    assert order.filled_size == Decimal(".4") and adapter.has_unknown_exposure()


async def test_kill_preserves_external_order_and_pins_unconfirmed_cancel():
    adapter, venue, order = venue_adapter(stub_source_gate=False)
    venue.opened = [venue_row(), venue_row(999, "SOL")]
    with pytest.raises(RuntimeError, match="unknown active"):
        await adapter.reconcile_venue()
    rt = HyperAmmRuntime(Settings(_env_file=None))
    rt.config.execution_mode = ExecutionMode.TESTNET
    rt.testnet = rt.execution = rt.orders.execution = adapter
    rt.strategy.running = True
    await rt.activate_kill()
    await rt.activate_kill()
    assert not rt.strategy.running and rt.risk.kill_switch_active
    assert "exposure remains unresolved" in rt.risk.last_reason
    assert [(market, cloid.to_raw()) for market, cloid in venue.cancellations] == [
        (order.market, adapter._cloid(order.client_order_id).to_raw()),
    ]
    venue.opened.pop()
    with pytest.raises(RuntimeError, match="cancellation still open"):
        await adapter.reconcile_venue()
    assert adapter.has_unknown_exposure() and order.client_order_id in adapter._needs_verification
    venue.opened.clear()
    venue.results["123"] = venue_update("canceled", remaining="1")
    await adapter.reconcile_venue()
    assert not adapter.has_unknown_exposure()
    assert rt.risk.kill_switch_active and venue.transmissions == 0


async def test_close_during_inventory_read_retires_result():
    adapter, venue, order = venue_adapter(stub_source_gate=False)
    entered, release = Event(), Event()

    def slow_inventory(*args):
        entered.set()
        assert release.wait(2)
        return [venue_row(remaining=".6")]

    venue.frontend_open_orders = slow_inventory
    read = asyncio.create_task(adapter.reconcile_venue())
    await wait_thread(entered)
    assert adapter.reconciliation_readiness == VenueReadiness.CHECKING
    close = asyncio.create_task(adapter.close())
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(RuntimeError, match="session changed"):
        await read
    await close
    assert adapter.reconciliation_readiness == VenueReadiness.BLOCKED
    assert order.filled_size == 0 and not venue.cancellations and venue.transmissions == 0


async def test_venue_failure_and_foreign_endpoint_are_blocking():
    adapter, venue, _ = venue_adapter()
    adapter._orders.clear()
    venue.frontend_open_orders = Mock(side_effect=TimeoutError("private-fixture-data"))
    with pytest.raises(RuntimeError, match="inventory unavailable") as error:
        await adapter.reconcile_venue()
    assert "private-fixture-data" not in str(error.value)
    assert adapter.unmanaged_order_count is None
    venue.base_url = "https://api.hyperliquid.xyz"
    with pytest.raises(RuntimeError, match="endpoint mismatch"):
        await adapter.reconcile_venue()
    assert venue.transmissions == 0


class ThreadProbe:
    ident = 1

    def __init__(self):
        self.live = True
        self.stuck = False
        self.joins = []

    def join(self, *, timeout):
        self.joins.append(timeout)
        self.live = self.stuck

    def is_alive(self):
        return self.live


class ManagerProbe(ThreadProbe):
    def __init__(self):
        super().__init__()
        self.stop_event = Event()
        self.ws = SimpleNamespace(close=Mock())
        self.ping_sender = ThreadProbe()
        self.start = Mock()


@pytest.fixture
def owned_sdk(monkeypatch):
    from hyperliquid.api import API
    from hyperliquid.info import Info

    probe = SimpleNamespace(
        sessions=[], managers=[], callbacks={}, order=Mock(),
        spot=Mock(return_value={"universe": [], "tokens": []}),
        meta=Mock(return_value={"universe": [{"name": "ETH", "szDecimals": 4}]}),
        account=Mock(return_value={"assetPositions": []}),
        subscribe=Mock(), unsubscribe=Mock(return_value=True),
    )

    def session():
        item = SimpleNamespace(headers={}, close=Mock())
        probe.sessions.append(item)
        return item

    def manager(_base_url):
        item = ManagerProbe()
        probe.managers.append(item)
        return item

    def subscribe(_info, spec, callback):
        probe.subscribe(spec, callback)
        probe.callbacks[spec["type"]] = callback
        return len(probe.callbacks)

    monkeypatch.setattr("hyperliquid.api.requests.Session", session)
    monkeypatch.setattr("hyperliquid.info.WebsocketManager", manager)
    monkeypatch.setattr(Info, "spot_meta", lambda self: probe.spot())
    monkeypatch.setattr(Info, "meta", lambda self, dex: probe.meta(dex))
    monkeypatch.setattr(Info, "perp_dexs", lambda self: [None])
    monkeypatch.setattr(Info, "frontend_open_orders", lambda *args: [])
    monkeypatch.setattr(Info, "user_state", lambda self, *args: probe.account(*args))
    monkeypatch.setattr(Info, "subscribe", subscribe)
    monkeypatch.setattr(Info, "unsubscribe", lambda self, *args: probe.unsubscribe(*args))
    monkeypatch.setattr("hyperliquid.exchange.Exchange.order", probe.order)
    probe.api_init = API.__init__
    probe.adapter = HyperliquidTestnetExecutionAdapter(
        enabled=True, private_key=None, account_address=FIXTURE_ACCOUNT, base_url=FIXTURE_TESTNET)
    return probe


@pytest.mark.parametrize("failure", ["spot", "meta", "subscribe_first", "subscribe_second", "account"])
async def test_owned_info_partial_init_or_read_failure_closes_resources(owned_sdk, failure):
    probe = owned_sdk
    error = RuntimeError("private-fixture-data")
    if failure.startswith("subscribe"):
        probe.subscribe.side_effect = [error] if failure == "subscribe_first" else [None, error]
    else:
        getattr(probe, failure).side_effect = error
    operation = probe.adapter.refresh_position("ETH") if failure == "account" else probe.adapter.reconcile_venue()
    with pytest.raises(RuntimeError) as exc:
        await operation
    assert "private-fixture-data" not in str(exc.value)
    await probe.adapter.close()
    await probe.adapter.close()
    manager = probe.managers[0]
    manager.start.assert_called_once()
    assert manager.stop_event.is_set() and len(manager.joins) == len(manager.ping_sender.joins) == 1
    manager.ws.close.assert_called_once()
    probe.sessions[0].close.assert_called_once()
    assert probe.unsubscribe.call_count == {"subscribe_second": 1, "account": 2}.get(failure, 0)
    assert probe.adapter._info is None and probe.adapter._sdk_worker is None
    assert probe.adapter._cleanup_task is None and not probe.order.called


async def test_exchange_init_failure_closes_both_http_sessions(owned_sdk, monkeypatch):
    from hyperliquid.api import API
    from hyperliquid.exchange import Exchange

    probe = owned_sdk
    probe.adapter.private_key = "never-parsed-fixture"
    monkeypatch.setattr("eth_account.Account.from_key", lambda *_: object())

    def fail_exchange(client, *args, **kwargs):
        probe.api_init(client, *args, **kwargs)
        if isinstance(client, Exchange):
            raise RuntimeError("private-fixture-data")

    monkeypatch.setattr(API, "__init__", fail_exchange)
    await probe.adapter.reconcile_venue()
    with pytest.raises(RuntimeError, match="exchange initialization failed") as exc:
        await probe.adapter._venue_exchange()
    assert "private-fixture-data" not in str(exc.value)
    assert len(probe.sessions) == 2
    for session in probe.sessions:
        session.close.assert_called_once()
    assert probe.adapter._info is None and probe.adapter._exchange is None
    probe.order.assert_not_called()


async def test_cancelled_constructor_drains_before_replacement_and_disables_callbacks(owned_sdk):
    probe = owned_sdk
    entered, release = Event(), Event()

    def meta(_dex):
        entered.set()
        assert release.wait(2)
        return {"universe": []}

    probe.meta.side_effect = meta
    first = asyncio.create_task(probe.adapter.reconcile_venue())
    await wait_thread(entered)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(probe.adapter.reconcile_venue())
    await asyncio.sleep(0)
    assert len(probe.managers) == 1 and not second.done()
    release.set()
    await second
    assert len(probe.managers) == 2
    probe.managers[0].ws.close.assert_called_once()
    callback = probe.callbacks["orderUpdates"]
    await probe.adapter.close()
    await asyncio.to_thread(callback, {})
    await asyncio.sleep(0)
    assert not probe.adapter.venue_changed.is_set()
    assert probe.adapter._sdk_worker is None and probe.adapter._cleanup_task is None


async def test_cleanup_failure_retains_manager(owned_sdk):
    probe = owned_sdk
    await probe.adapter.reconcile_venue()
    manager = probe.managers[0]
    manager.ping_sender.stuck = True
    with pytest.raises(RuntimeError, match="cleanup unconfirmed"):
        await probe.adapter.close()
    assert probe.adapter._info.ws_manager is manager
    with pytest.raises(RuntimeError, match="unavailable"):
        await probe.adapter.reconcile_venue()
    assert len(probe.managers) == 1
    manager.ping_sender.stuck = False
    await probe.adapter.close()
    assert probe.adapter._info is None and not manager.ping_sender.is_alive()
    probe.sessions[0].close.assert_called_once()


async def test_borrowed_clients_are_never_closed_and_late_callbacks_are_ignored():
    adapter, venue, _ = venue_adapter(stub_source_gate=False)
    adapter._orders.clear()
    venue.session = SimpleNamespace(close=Mock())
    venue.disconnect_websocket = Mock()
    await adapter.reconcile_venue()
    callback = venue.callbacks["userFills"]
    await adapter.close()
    callback({})
    await asyncio.sleep(0)
    assert not adapter.venue_changed.is_set() and not venue.callbacks
    venue.session.close.assert_not_called()
    venue.disconnect_websocket.assert_not_called()


async def test_sdk_manager_and_ping_threads_join_with_local_socket_stub(owned_sdk, monkeypatch):
    from hyperliquid.websocket_manager import WebsocketManager

    started, stopped = Event(), Event()
    socket = SimpleNamespace(
        run_forever=lambda: (started.set(), stopped.wait(2)),
        close=Mock(side_effect=stopped.set),
    )
    monkeypatch.setattr("hyperliquid.info.WebsocketManager", WebsocketManager)
    monkeypatch.setattr("hyperliquid.websocket_manager.websocket.WebSocketApp", lambda *a, **kw: socket)
    await owned_sdk.adapter.reconcile_venue()
    await wait_thread(started)
    manager = owned_sdk.adapter._info.ws_manager
    assert manager.is_alive() and manager.ping_sender.is_alive()
    await owned_sdk.adapter.close()
    assert not manager.is_alive() and not manager.ping_sender.is_alive()
    socket.close.assert_called_once()


async def test_close_during_blocked_constructor_is_bounded_and_keeps_ownership(owned_sdk):
    probe = owned_sdk
    probe.adapter._sdk_timeout = .05
    entered, release = Event(), Event()

    def meta(_dex):
        entered.set()
        assert release.wait(2)
        return {"universe": []}

    probe.meta.side_effect = meta
    read = asyncio.create_task(probe.adapter.reconcile_venue())
    await wait_thread(entered)
    try:
        with pytest.raises(RuntimeError, match="cleanup unconfirmed"):
            await probe.adapter.close()
        assert probe.adapter._sdk_worker is not None
        assert probe.adapter._info.ws_manager is probe.managers[0]
    finally:
        release.set()
    with pytest.raises(RuntimeError, match="inventory unavailable"):
        await read
    await probe.adapter.close()
    assert len(probe.managers) == 1 and probe.adapter._sdk_worker is None
    probe.managers[0].ws.close.assert_called_once()


async def test_inventory_change_during_fake_final_authority_retires_readiness():
    adapter, venue, _ = venue_adapter()
    adapter._orders.clear()
    pending, authorized = asyncio.Event(), asyncio.Event()

    async def allow(_request):
        pending.set()
        await authorized.wait()

    adapter.authority = allow
    send = asyncio.create_task(adapter.submit_orders([REQUEST]))
    await asyncio.wait_for(pending.wait(), 2)
    venue.opened.append(venue_row(999, "BTC"))
    await asyncio.to_thread(venue.callbacks["orderUpdates"], {})
    await asyncio.sleep(0)
    authorized.set()
    with pytest.raises(RuntimeError, match="session or exposure changed"):
        await send
    assert adapter.has_unknown_exposure() and venue.transmissions == 0
    await adapter.close()


async def test_failed_testnet_transition_restart_exposure_and_sdk_cleanup(owned_sdk):
    rt = HyperAmmRuntime(Settings(_env_file=None, enable_hyperliquid_testnet_orders=True))
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(2))
    await rt.refresh_once()
    before = rt.authorization.authorization_fingerprint
    forbidden = rt.config.model_copy(update={"market_data_mode": MarketDataMode.LIVE, "execution_mode": ExecutionMode.TESTNET})
    with pytest.raises(ValueError, match="Hyperliquid Mainnet"):
        await rt.update_config(forbidden)
    assert rt.execution is rt.paper and rt.authorization.authorization_fingerprint == before

    adapter, venue, _ = venue_adapter(stub_source_gate=False)
    adapter._orders.clear()
    venue.opened = [venue_row(99, "BTC")]
    with pytest.raises(RuntimeError, match="unknown active"):
        await adapter.reconcile_venue()
    with pytest.raises(PermissionError, match="qualified Testnet Core source"):
        await adapter.submit_orders([REQUEST])
    assert venue.transmissions == 0

    owned_sdk.meta.side_effect = RuntimeError("fixture metadata failure")
    with pytest.raises(RuntimeError, match="inventory unavailable"):
        await owned_sdk.adapter.reconcile_venue()
    await owned_sdk.adapter.close()
    owned_sdk.managers[0].ws.close.assert_called_once()
    assert not owned_sdk.order.called
    await rt.activate_kill()
    assert rt.risk.kill_switch_active and not rt.strategy.running


async def test_runtime_attempts_sdk_shutdown_even_when_strategy_cancel_fails(owned_sdk):
    adapter = owned_sdk.adapter
    await adapter.reconcile_venue()
    rt = HyperAmmRuntime(Settings(_env_file=None))
    rt.testnet = rt.execution = rt.orders.execution = adapter
    rt.config.execution_mode = ExecutionMode.TESTNET
    adapter.cancel_all = AsyncMock(side_effect=RuntimeError("TESTNET cancellation unconfirmed"))
    with pytest.raises(RuntimeError, match="runtime transport shutdown unconfirmed"):
        await rt.stop_services()
    assert rt.risk.kill_switch_active and rt.lifecycle_state == "STOPPED"
    assert adapter._info is None and adapter._cleanup_task is None
    owned_sdk.managers[0].ws.close.assert_called_once()
