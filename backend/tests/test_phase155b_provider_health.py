import pytest
from app.references.live_provider_integrity import provider_health
from phase155b_helpers import prepared
from test_phase151_live_markets import book

@pytest.mark.parametrize('connection',['RECONNECTING','CONNECTING','STOPPED','UNAVAILABLE'])
async def test_retained_prices_never_keep_disconnected_source_healthy(connection):
    service,_,_=await prepared()
    try:
        service.states['BTC'].connection=connection
        health=provider_health(service.snapshot('BTC'))
        assert all(p.status=='ERROR' and p.price is None and not p.event_time_verified for p in health.providers[:3])
        assert health.authority=='NONE' and health.read_only and health.consensus_price is None
    finally:await service.close()

async def test_invalid_update_marks_retained_native_health_degraded():
    service,_,clock=await prepared()
    try:
        raw=book('BTC');raw['coin']='ETH'
        service.accept('BTC','l2Book',raw,1,clock())
        health=provider_health(service.snapshot('BTC'))
        assert health.providers[0].status=='DEGRADED' and health.providers[0].price is not None
        assert len({p.independent_source_group for p in health.providers[:3]})==1
        assert all(not p.event_time_verified and p.source_timestamp is None for p in health.providers[1:3])
    finally:await service.close()

async def test_disabled_native_status_uses_existing_disabled_contract():
    service,_,_=await prepared()
    try:
        for s in service.states.values():s.connection='DISABLED'
        assert all(p.status=='DISABLED' and p.price is None for p in provider_health(service.snapshot('BTC')).providers)
    finally:await service.close()

async def test_metadata_expiry_invalidates_native_prices():
    service,_,clock=await prepared()
    try:
        clock.advance(301)
        health=provider_health(service.snapshot('BTC'))
        assert all(p.status=='ERROR' and p.price is None and not p.mapping.enabled for p in health.providers[:3])
    finally:await service.close()

@pytest.mark.parametrize('module',['app.market_data.live_models','app.references.live_provider_integrity','app.market_data.live_streams'])
def test_standalone_observation_imports_do_not_initialize_simulation_engine(module):
    import subprocess,sys
    code=f'''import importlib,sys
importlib.import_module({module!r})
assert 'app.simulation.engine' not in sys.modules
from app.simulation import SimulationEngine,SimulationService,SimulationConfig
from app.simulation.engine import SimulationEngine as ActualEngine
assert SimulationEngine is ActualEngine
'''
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
