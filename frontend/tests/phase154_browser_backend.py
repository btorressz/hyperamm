"""Test-only real PAPER runtime with normalized live fixtures; zero venue networking."""
from contextlib import asynccontextmanager
from datetime import timedelta
import asyncio,json
from pathlib import Path
import app.main as main
import phase153_browser_backend as fixture
from app.market_data.live_stream_models import LiveStreamSnapshot
from app.simulation.market_profiles import ResearchMarketCatalog, ResearchPerpMarketMetadata, profile

# Replace only test fixture snapshots with five levels produced by the actual
# Phase 15 normalizers in phase154-fixtures.py; existing Phase 15.3 artifacts stay intact.
raw154=json.loads((Path(__file__).parent/'phase154-fixtures.json').read_text())
for m in raw154:fixture.RAW[m]['snapshot']=raw154[m]['response']['observed']['snapshot']
app=main.app
original_lifespan=app.router.lifespan_context
base_snapshot=fixture.snapshot

class OfflineCatalog:
    async def catalog(self):
        return ResearchMarketCatalog(markets=tuple(profile(ResearchPerpMarketMetadata(market=m,
            sz_decimals={'BTC':5,'ETH':4,'SOL':2}[m],metadata_status='DEMO_PROFILE',metadata_source='PINNED_RESEARCH_FIXTURE')) for m in ('BTC','ETH','SOL')))
    async def resolve(self,m):return next(p for p in (await self.catalog()).markets if p.market==m)
    async def close(self):pass

main.HyperliquidMetadataCatalog=lambda **kwargs:OfflineCatalog()

@asynccontextmanager
async def lifespan(application):
    async with original_lifespan(application):
        service=app.state.live_market_streams
        disabled_snapshot=service.snapshot
        def snapshot(m):
            if fixture.mode['kind']=='disabled':return disabled_snapshot(m)
            snap=base_snapshot(m)
            data=snap.model_dump()
            if fixture.mode['kind']=='stale_context':
                stamp=data['perp_context']['observed_at']-timedelta(seconds=60)
                data['perp_context']['observed_at']=stamp
                data['status']['last_perp_observed_at']=stamp
                data['status']['perp_age_seconds']=60.1;data['status']['perp_freshness']='STALE';data['observation_status']='STALE'
            if fixture.mode['kind']=='missing_depth':
                data['order_book']['bids']=data['order_book']['bids'][:1];data['order_book']['asks']=data['order_book']['asks'][:1]
            return LiveStreamSnapshot.model_validate(data)
        # Production comparison handler reads the exact same server-owned fixture
        # snapshot as HTTP/WS; the comparison route itself is not replaced.
        fixture.snapshot=snapshot
        service.snapshot=snapshot
        yield
app.router.lifespan_context=lifespan
