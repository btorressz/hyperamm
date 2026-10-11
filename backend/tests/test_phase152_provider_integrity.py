"""No borrowed mappings, synthetic health or new operational quorum votes."""
import pytest
from pydantic import ValidationError
from app.references.models import ProviderId, PriceEvidence
from app.references.live_provider_mappings import (LiveProviderMapping, external_mappings, validate_provider_evidence,
    SYMBOLS, ROLES, EXTERNAL)
from app.references.live_provider_integrity import provider_health
from test_phase152_live_streams import streams, create
from test_phase151_live_markets import NOW
from app.simulation.market_profiles import MARKETS

@pytest.mark.parametrize('market',MARKETS)
async def test_native_roles_one_source_and_external_disabled(streams,market):
    service,_,_=streams;health=provider_health(service.snapshot(market))
    assert health.market==market and len(health.providers)==7 and health.authority=='NONE'
    assert health.consensus_price is None and health.independent_usable_external_sources==0
    native=health.providers[:3];external=health.providers[3:]
    assert {x.independent_source_group for x in native}=={'HYPERLIQUID'}
    assert native[0].status=='HEALTHY' and native[0].event_time_verified
    assert all(x.status=='DEGRADED' and x.error=='EVENT_TIME_UNKNOWN' and x.source_timestamp is None for x in native[1:])
    assert all(not x.enabled and x.price is None and x.status=='DISABLED' and x.authority=='NONE' for x in external)
    assert all(x.mapping.native_symbol is None and x.mapping.last_validated_configuration is None for x in external)
    assert len([x for x in external if x.provider=='REDSTONE'])==1
    if market=='SOL':assert external[-1].mapping.mapping_status=='UNAVAILABLE'

@pytest.mark.parametrize('provider',EXTERNAL)
@pytest.mark.parametrize('market',MARKETS)
def test_wrong_or_unsupported_asset_mapping_rejected(provider,market):
    with pytest.raises(ValidationError):
        LiveProviderMapping(market=market,provider=provider,native_symbol='wrong:secret',transport='LIVE_WS',mapping_status='UNVERIFIED')
    mappings=external_mappings(market)
    assert all(x.market==market and not x.enabled for x in mappings)

@pytest.mark.parametrize('market',MARKETS)
@pytest.mark.parametrize('transport',['LIVE_WS','PUBLIC_HTTP'])
def test_redstone_ws_http_validated_as_one_provider(market,transport):
    source=f'redstone-primary-prod:{market}' if transport=='LIVE_WS' else f'redstone-public-http:{market}'
    mapping=LiveProviderMapping(market=market,provider='REDSTONE',native_symbol=market,expected_source_id=source,
        transport=transport,mapping_status='VALIDATED',last_validated_configuration=NOW)
    evidence=PriceEvidence(market=market,provider='REDSTONE',source_type='ORACLE',price='100',observed_at=NOW,
        source_timestamp=NOW,status='HEALTHY',source_id=source,transport=transport)
    assert validate_provider_evidence(mapping,evidence) is evidence
    assert mapping.authority=='NONE' and not mapping.enabled
    with pytest.raises(ValidationError):LiveProviderMapping(**{**mapping.model_dump(),'enabled':True})

@pytest.mark.parametrize('patch',[{'market':'ETH'},{'provider':'KRAKEN'},{'source_id':'ETH/USD'},
    {'source_type':'AGGREGATOR_REFERENCE'},{'transport':'REST'},{'simulated':True}])
def test_wrong_provider_evidence_not_admitted(patch):
    mapping=LiveProviderMapping(market='BTC',provider='KRAKEN',native_symbol='BTC/USD',expected_source_id='BTC/USD',
        transport='LIVE_WS',mapping_status='VALIDATED',last_validated_configuration=NOW)
    values=dict(market='BTC',provider='KRAKEN',source_type='VENUE_REFERENCE',price='100',observed_at=NOW,
        source_timestamp=NOW,status='HEALTHY',source_id='BTC/USD',transport='LIVE_WS')
    # Changing to another provider is distinct from a correct source ID.
    if patch=={'provider':'KRAKEN'}:patch={'provider':'REDSTONE'}
    with pytest.raises(ValueError):validate_provider_evidence(mapping,PriceEvidence(**{**values,**patch}))

@pytest.mark.parametrize('provider,market',[(p,m) for p in EXTERNAL for m in MARKETS if m in SYMBOLS[p]])
def test_explicit_provider_role_and_validation_requirements(provider,market):
    symbol=SYMBOLS[provider][market];transport='REST' if provider=='COINGECKO' else 'LIVE_WS'
    source=f'redstone-primary-prod:{symbol}' if provider=='REDSTONE' else symbol
    values=dict(market=market,provider=provider,native_symbol=symbol,expected_source_id=source,transport=transport,
        mapping_status='VALIDATED',last_validated_configuration=NOW)
    mapping=LiveProviderMapping(**values)
    assert mapping.authority=='NONE'
    with pytest.raises(ValidationError):LiveProviderMapping(**{**values,'last_validated_configuration':None})
    with pytest.raises(ValidationError):LiveProviderMapping(**{**values,'expected_source_id':'wrong-provider'})
    assert ROLES[provider]==('VENUE_REFERENCE' if provider=='KRAKEN' else 'ORACLE' if provider=='REDSTONE' else 'AGGREGATOR_REFERENCE')

async def test_aging_context_stale_book_fresh_and_disconnection_unavailable(streams):
    service,sdk,clock=streams;clock.advance(31)
    raw=sdk.books['BTC'].copy();raw['time']=int(clock().timestamp()*1000)
    service.accept('BTC','l2Book',raw,1,clock())
    health=provider_health(service.snapshot('BTC'))
    assert health.providers[0].status=='HEALTHY' and all(x.status=='STALE' for x in health.providers[1:3])
    await service.close();health=provider_health(service.snapshot('BTC'))
    assert all(x.status=='ERROR' and x.price is None for x in health.providers[:3])

async def test_disabled_service_has_no_healthy_native_evidence():
    service,_,_=create();service.enabled=False
    try:
        health=provider_health(service.snapshot('BTC'))
        assert all(x.price is None and x.status!='HEALTHY' for x in health.providers)
    finally:await service.close()
