import pytest
from app.portfolio_research.models import PortfolioStressResult
from phase174_fixtures import native174,selloff174,request_for


def test_modeled_relationship_does_not_claim_empirical_evidence(native174):
    r=native174
    assert r.request.scenario.assumptions.relationship_source=="EXPLICIT_HYPOTHETICAL_ASSUMPTIONS"
    assert r.cross_market_correlation is None and not r.empirical_correlation_verified
    assert not r.historical_market_synchronization_verified and not r.source_authenticated
    for leg in (r.baseline,r.stressed):
        assert leg.temporal.cross_market_correlation is None
        assert not leg.temporal.empirical_correlation_verified
        assert not leg.temporal.historical_market_synchronization_verified

@pytest.mark.parametrize("field,value",[("empirical_correlation_verified",True),("historical_market_synchronization_verified",True),("cross_market_correlation",[[1]]),("source_authenticated",True),("authority","LIVE")])
def test_unsupported_provenance_claims_rejected(selloff174,field,value):
    raw=selloff174.model_dump();raw[field]=value
    with pytest.raises(ValueError): PortfolioStressResult.model_validate(raw)
