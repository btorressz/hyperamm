"""Seed real PAPER state while adversarial observational lifecycle runs independently."""
import pytest
from decimal import Decimal
from app.config import Settings
from app.runtime import HyperAmmRuntime
from app.execution.models import OrderRequest
from app.market_data.mock import MockMarketDataAdapter
from app.references.live_provider_integrity import provider_health
from test_phase14_research_vault import authority
from test_phase151_live_markets import book
from phase155b_helpers import prepared

@pytest.mark.parametrize('kill',[False,True])
async def test_invalid_and_disconnected_observations_preserve_all_seeded_authority(kill):
    rt=HyperAmmRuntime(Settings(_env_file=None));frame=MockMarketDataAdapter().snapshot_for(4)
    await rt.market._accept(frame);await rt.refresh_once()
    await rt.paper.submit_orders([OrderRequest(client_order_id='155b-seed',market='ETH',side='BID',price=frame.best_ask,size=Decimal('.1'))])
    await rt.refresh_once();rt.strategy.running=True;await rt._execution_authority()
    async with rt.execution_lock:
        await rt.orders.reconcile_locked(rt.config.market,rt.quotes,rt.config.replace_tolerance_bps,rt.config.size_tolerance)
    rt.accounting_service.reserve(rt.quotes,await rt.execution.get_open_orders())
    if kill:await rt.activate_kill();await rt.refresh_once()
    assert rt.paper.fills.all() and rt.accounting_service.ledger.version>1
    before=authority(rt);service,sdk,clock=await prepared()
    try:
        for market in ('BTC','ETH','SOL'):
            raw=book(market);raw['coin']='UNSUPPORTED'
            assert not service.accept(market,'l2Book',raw,1,clock())
            assert not service.accept(market,'activeAssetCtx',sdk.ctx(market),0,clock())
            provider_health(service.snapshot(market));service.history.query(market)
            service.states[market].connection='RECONNECTING'
            provider_health(service.snapshot(market))
            q=service.subscribe(market);service.publish(market);service.unsubscribe(q)
    finally:await service.close()
    assert authority(rt)==before
