"""Browser-consumable boundaries and unchanged seeded operational authority."""
import copy
import pytest
import httpx
from app.main import app
from app.references.live_provider_integrity import provider_health
from app.runtime import HyperAmmRuntime
from app.config import Settings
from app.market_data.mock import MockMarketDataAdapter
from test_phase152_live_streams import streams, create, eventually
from test_phase14_research_vault import authority
from app.market_data.live_streams import LiveMarketStreamService

@pytest.mark.parametrize('market',['BTC','ETH','SOL'])
async def test_http_ws_history_identity_and_configured_freshness_boundary(streams,monkeypatch,market):
    service,sdk,clock=streams
    monkeypatch.setattr(app.state,'live_market_streams',service,raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
        snapshot=(await client.get(f'/api/v1/live-markets/{market}/stream-snapshot')).json()
        status=snapshot['status']
        assert status['observer_instance_id']==service.instance_id
        assert status['evaluated_at']==clock().isoformat().replace('+00:00','Z')
        assert status['l2_stale_after_seconds']==service.l2_budget
        assert status['perp_stale_after_seconds']==service.perp_budget
        assert status['metadata_stale_after_seconds']==service.metadata_budget
        assert snapshot['order_book']['source']=='OFFICIAL_SDK_REST'
        assert status['connection_state']=='BOOTSTRAPPING'
        refs=(await client.get(f'/api/v1/live-markets/{market}/references')).json()
        assert refs['providers'][0]['status']=='HEALTHY'
        assert refs['authority']=='NONE' and refs['consensus_price'] is None
        queue=service.subscribe(market)
        import json
        frame=json.loads(queue.get_nowait());service.unsubscribe(queue)
        assert frame['observer_instance_id']==status['observer_instance_id']==(await client.get(f'/api/v1/live-markets/{market}/history')).json()['observer_instance_id']
        assert frame['payload']['status']['connection_generation']==frame['connection_generation']

async def test_custom_budgets_emission_age_and_restart_identity():
    old,sdk,clock=create(live_stream_l2_stale_after_seconds=2,live_stream_perp_stale_after_seconds=8,live_observation_metadata_stale_after_seconds=50)
    await old.start()
    try:
        await eventually(lambda:old.states['BTC'].context is not None)
        original=old.snapshot('BTC');clock.advance(3)
        aged=old.snapshot('BTC')
        assert aged.status.l2_stale_after_seconds==2 and aged.status.perp_stale_after_seconds==8
        assert aged.status.metadata_stale_after_seconds==50
        assert aged.status.evaluated_at>original.status.evaluated_at
        assert aged.status.last_l2_source_timestamp==original.status.last_l2_source_timestamp
        assert aged.status.l2_freshness=='STALE' and aged.status.perp_freshness=='FRESH'
        new=LiveMarketStreamService(Settings(_env_file=None))
        try:
            assert new.snapshot('BTC').status.observer_instance_id!=old.instance_id
            assert not new.history.query('BTC').points
            assert new.snapshot('BTC').status.connection_state=='DISABLED'
        finally:await new.close()
    finally:await old.close()

@pytest.mark.parametrize('kill',[False,True])
async def test_terminal_browsing_preserves_actual_runtime_authority(streams,monkeypatch,kill):
    service,sdk,clock=streams
    rt=HyperAmmRuntime(Settings(_env_file=None))
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(4));await rt.refresh_once()
    if kill:await rt.activate_kill();await rt.refresh_once()
    before=authority(rt)
    identities=tuple(id(x) for x in [rt.market,rt.perp_context_service,rt.reference_service,rt.orders,rt.accounting_service,rt.execution])
    monkeypatch.setattr(app.state,'runtime',rt,raising=False)
    monkeypatch.setattr(app.state,'live_market_streams',service,raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
        for market in ['BTC','ETH','SOL','BTC']:
            for path in ['stream-status','stream-snapshot','history?limit=1000','references']:
                assert (await client.get(f'/api/v1/live-markets/{market}/{path}')).status_code==200
            sdk.emit(market,'l2Book');sdk.emit(market,'activeAssetCtx')
            queue=service.subscribe(market);assert queue.get_nowait();service.unsubscribe(queue)
    assert before==authority(rt)
    assert identities==tuple(id(x) for x in [rt.market,rt.perp_context_service,rt.reference_service,rt.orders,rt.accounting_service,rt.execution])
