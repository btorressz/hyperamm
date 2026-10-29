"""Deterministic Phase 15.5B fixtures using the existing Phase 15 SDK contracts."""
import asyncio
from app.market_data.live_streams import BoundedIngress
from app.market_data.live_models import LiveMarketMetadata
from app.market_data.hyperliquid_metadata import validate_native_metadata
from test_phase151_live_markets import native, book
from test_phase152_live_streams import create

async def until(predicate, timeout=3):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0)

async def prepared(**options):
    service, sdk, clock = create(**options)
    service._generation = 1
    service._inbox = BoundedIngress(asyncio.get_running_loop(), service.queue_capacity, clock)
    for item in validate_native_metadata(native(), clock()):
        state = service.states[item.market]
        state.generation, state.connection, state.barrier = 1, 'BOOTSTRAPPING', True
        state.metadata = LiveMarketMetadata(market=item.market, metadata_status=item.metadata_status,
            source='OFFICIAL_SDK_NATIVE_META', listed=True, asset_index=item.asset_index,
            sz_decimals=item.sz_decimals, observed_at=clock())
        assert service.accept(item.market, 'l2Book', book(item.market), 1, clock(), source='OFFICIAL_SDK_REST')
        assert service.accept(item.market, 'activeAssetCtx', sdk.ctx(item.market), 1, clock(), source='OFFICIAL_SDK_REST')
    return service, sdk, clock
