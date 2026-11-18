"""Targeted Audit 3.0 regressions for preflight, Kraken controls and unsupported assets.

No venue transmission, wallet signing or external network access.
"""
import asyncio
import json
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.strategy import router as strategy_router
from app.config import Settings
from app.dependencies import runtime
from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
from app.execution.models import OrderRequest
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.models import utcnow
from app.market_data.perp_context import demo_perp_context
from app.references.providers import KrakenProvider
from app.references.consensus import ReferenceConsensusPolicy
from app.references.models import ProviderId, ProviderStatus, SourceType
from app.runtime import HyperAmmRuntime
from test_phase8_references import evidence


def test_a3_002_stale_perp_preflight_returns_422_without_mutation(monkeypatch):
    rt = HyperAmmRuntime(Settings(_env_file=None))
    invalidate = AsyncMock(wraps=rt._invalidate_locked)
    cancel = AsyncMock(wraps=rt.execution.cancel_all)
    monkeypatch.setattr(rt, "_invalidate_locked", invalidate)
    monkeypatch.setattr(rt.execution, "cancel_all", cancel)
    app = FastAPI()
    app.include_router(strategy_router, prefix="/api/v1")
    app.dependency_overrides[runtime] = lambda: rt
    with TestClient(app, raise_server_exceptions=False) as client:
        snap = MockMarketDataAdapter().snapshot_for(0)
        client.portal.call(rt.market._accept, snap)
        stale = demo_perp_context(snap).model_copy(update={
            "updated_at": snap.latest_valid_update - timedelta(seconds=60),
        })
        rt.perp_context_service._context = stale
        before = rt.config.model_dump(mode="json")
        authorization = rt.authorization_summary()
        response = client.put("/api/v1/strategy", json=before | {"concentration_factor": "9"})
        assert response.status_code == 422
        assert response.json() == {"detail": "perpetual market context is stale"}
        assert rt.config.model_dump(mode="json") == before
        assert rt.authorization_summary() == authorization
        assert rt.lifecycle_state == "READY"
        invalidate.assert_not_awaited()
        cancel.assert_not_awaited()

        rt.perp_context_service._context = demo_perp_context(snap)
        assert client.put("/api/v1/strategy", json=before | {"concentration_factor": "9"}).status_code == 200
        assert rt.config.concentration_factor == D("9")
        assert rt.lifecycle_state == "READY"

        # Until the first context arrives, the established static preflight
        # admits configuration without creating execution authorization.
        rt.perp_context_service._context = None
        assert client.put("/api/v1/strategy", json=before).status_code == 200
        assert rt.config.model_dump(mode="json") == before
        assert rt.authorization_summary()["authorized"] is False


@pytest.mark.parametrize("asset", [10_000, 110_000, -1])
def test_a3_004_unsupported_asset_ids_fail_closed_without_transmission(asset):
    info = SimpleNamespace(name_to_asset=lambda _: asset, asset_to_sz_decimals={asset: 2})
    request = OrderRequest(client_order_id="audit-only", market="audit:TEST",
                           side="BID", price=D("0.00123456"), size=D("1"))
    with pytest.raises(ValueError, match="unsupported Hyperliquid instrument class"):
        HyperliquidTestnetExecutionAdapter.normalize_order_request(SimpleNamespace(info=info), request)


def test_a3_004_native_perp_precision_is_unchanged():
    info = SimpleNamespace(name_to_asset=lambda _: 0, asset_to_sz_decimals={0: 2})
    request = OrderRequest(client_order_id="audit-only", market="ETH",
                           side="BID", price=D("0.00123456"), size=D("1"))
    result = HyperliquidTestnetExecutionAdapter.normalize_order_request(
        SimpleNamespace(info=info), request
    )
    assert result.price == D("0.0012")
    assert result.size == request.size


@pytest.mark.asyncio
async def test_a3_007_heartbeat_is_control_only_and_does_not_refresh_price():
    consumed = asyncio.Event()

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def send(self, _):
            return None

        def __aiter__(self):
            return self.messages()

        async def messages(self):
            yield json.dumps({"channel": "ticker", "data": [{
                "symbol": "ETH/USD", "bid": 3000, "ask": 3001,
                "timestamp": utcnow().isoformat(),
            }]})
            yield json.dumps({"channel": "heartbeat"})
            yield json.dumps({"channel": "unexpected"})
            consumed.set()
            await asyncio.Event().wait()

    provider = KrakenProvider(
        market="ETH", enabled=True, symbol="ETH/USD", stale_after_seconds=5,
        websocket_factory=lambda _: Connection(),
    )
    try:
        await provider.start()
        await asyncio.wait_for(consumed.wait(), timeout=2)
        # Allow the final queued invalid frame to be processed.
        for _ in range(50):
            snapshot = provider.snapshot()
            if snapshot.status.value == "DEGRADED":
                break
            await asyncio.sleep(0.01)
        assert snapshot.status.value == "DEGRADED"
        assert snapshot.price == D("3000.5")
        assert "unknown Kraken message type" in snapshot.error
    finally:
        await provider.stop()


@pytest.mark.asyncio
async def test_a3_007_valid_heartbeat_preserves_health_and_source_timestamp():
    consumed = asyncio.Event()

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def send(self, _):
            return None

        def __aiter__(self):
            return self.messages()

        async def messages(self):
            yield json.dumps({"channel": "ticker", "data": [{
                "symbol": "ETH/USD", "bid": 3000, "ask": 3001,
                "timestamp": utcnow().isoformat(),
            }]})
            consumed.set()
            yield json.dumps({"channel": "heartbeat"})
            await asyncio.Event().wait()

    provider = KrakenProvider(
        market="ETH", enabled=True, symbol="ETH/USD", stale_after_seconds=5,
        websocket_factory=lambda _: Connection(),
    )
    try:
        await provider.start()
        await asyncio.wait_for(consumed.wait(), timeout=2)
        # Once the accepted ticker is observed, heartbeat must not replace it.
        for _ in range(20):
            await asyncio.sleep(0.005)
        result = provider.snapshot()
        assert result.healthy and result.status.value == "HEALTHY"
        assert not result.stale
        assert result.price == D("3000.5")
        assert result.source_timestamp is not None
        assert result.version >= 1
    finally:
        await provider.stop()


async def test_a3_007_heartbeat_quorum_age_and_transport_recovery(monkeypatch):
    import app.references.providers as providers

    now = utcnow()
    monkeypatch.setattr(providers, "utcnow", lambda: now)
    monkeypatch.setattr(providers, "backoff", lambda _: 0)
    frames = asyncio.Queue()
    processed = asyncio.Queue()
    subscriptions = asyncio.Queue()
    connections = []

    class Connection:
        async def __aenter__(self):
            connections.append(self)
            return self

        async def __aexit__(self, *_):
            self.closed = True

        async def send(self, message):
            subscriptions.put_nowait(json.loads(message))

        async def __aiter__(self):
            while True:
                frame = await frames.get()
                try:
                    yield json.dumps(frame)
                finally:
                    processed.put_nowait(frame)

    provider = KrakenProvider(market="ETH", enabled=True, symbol="ETH/USD",
        stale_after_seconds=5, websocket_factory=lambda _: Connection())

    async def push(frame):
        await frames.put(frame)
        assert await asyncio.wait_for(processed.get(), timeout=2) == frame

    def ticker():
        return {"channel": "ticker", "data": [{"symbol": "ETH/USD", "bid": 3000,
            "ask": 3001, "timestamp": now.isoformat()}]}

    def quorum(price):
        sources = {"REDSTONE": evidence(ProviderId.REDSTONE, "3000"),
            "HYPERLIQUID_ORACLE": evidence(ProviderId.HYPERLIQUID_ORACLE, "3001", source_type=SourceType.NATIVE_ORACLE),
            "KRAKEN": price}
        return ReferenceConsensusPolicy().evaluate("ETH", sources, agreement_bps=D("30"), outlier_bps=D("75"))

    try:
        await provider.start()
        assert await asyncio.wait_for(subscriptions.get(), timeout=2) == provider.subscription()
        await push(ticker())
        original = provider.snapshot()
        assert quorum(original).confidence_state == "VERIFIED"
        for elapsed in (1, 2, 3):
            now = original.source_timestamp + timedelta(seconds=elapsed)
            await push({"channel": "heartbeat"})
            current = provider.snapshot()
            assert current.model_dump(exclude={"age_ms"}) == original.model_dump(exclude={"age_ms"})
            assert current.age_ms == elapsed * 1000
            assert quorum(current).healthy_core_sources == 3

        now = original.source_timestamp + timedelta(seconds=6)
        await push({"channel": "heartbeat"})
        stale = provider.snapshot()
        assert stale.status == ProviderStatus.STALE and stale.age_ms == 6000
        assert stale.source_timestamp == original.source_timestamp
        assert quorum(stale).healthy_core_sources == 2
        await push(ticker())
        assert quorum(provider.snapshot()).healthy_core_sources == 3
        await push({"channel": "heartbeat", "data": []})
        assert provider.snapshot().status == ProviderStatus.DEGRADED
        assert provider.snapshot().source_timestamp == now

        await push({"method": "subscribe", "success": False, "error": "fixture subscription rejected"})
        assert await asyncio.wait_for(subscriptions.get(), timeout=2) == provider.subscription()
        assert connections[0].closed and len(connections) == 2
        assert provider.snapshot().status == ProviderStatus.DEGRADED
        now += timedelta(seconds=1)
        await push(ticker())
        assert provider.snapshot().status == ProviderStatus.HEALTHY
    finally:
        await provider.stop()
    assert connections[-1].closed and provider.task is None
