import pytest
from pydantic import ValidationError
from app.references.live_provider_mappings import LiveProviderMapping, external_mappings, EXTERNAL
from app.simulation.market_profiles import MARKETS
from test_phase151_live_markets import NOW

@pytest.mark.parametrize('market',MARKETS)
@pytest.mark.parametrize('provider',EXTERNAL)
def test_mapping_cannot_activate_external_collection(market,provider):
    mapping=next(m for m in external_mappings(market) if m.provider==provider)
    assert mapping.authority=='NONE' and not mapping.enabled
    with pytest.raises(ValidationError):LiveProviderMapping(**{**mapping.model_dump(),'enabled':True})

@pytest.mark.parametrize('market',MARKETS)
def test_native_identity_cannot_borrow_another_market(market):
    with pytest.raises(ValidationError):LiveProviderMapping(market=market,provider='HYPERLIQUID_MID',native_symbol='OTHER',
        expected_source_id=f'hyperliquid:{market}:HYPERLIQUID_MID',transport='NATIVE',mapping_status='VALIDATED',
        last_validated_configuration=NOW)
