"""Targeted Audit 3.0 regressions for preflight, Kraken controls and unsupported assets.

No venue transmission, wallet signing or external network access.
"""
import asyncio
import json
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace

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
from app.runtime import HyperAmmRuntime


def test_a3_002_stale_perp_preflight_returns_422_without_mutation():
    rt = HyperAmmRuntime(Settings(_env_file=None))
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
        response = client.put("/api/v1/strategy", json=before | {"concentration_factor": "9"})
        assert response.status_code == 422
        assert "stale" in str(response.json()).lower()
        assert rt.config.model_dump(mode="json") == before
        assert rt.lifecycle_state == "READY"


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
