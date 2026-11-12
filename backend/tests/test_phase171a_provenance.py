"""Phase 17.1A: deterministic configuration fingerprints; never exchange authentication."""
import pytest
from pydantic import ValidationError

from app.portfolio_research.models import PortfolioResearchConfig
from app.portfolio_research.provenance import (
    PortfolioResearchProvenance, capture_portfolio_provenance)
from phase171a_fixtures import config, market_scenario


def test_receipt_is_deterministic_normalized_and_roundtrippable():
    p=config()
    r=capture_portfolio_provenance(p)
    assert len(r.config_fingerprint)==64
    assert len(r.allocation_fingerprint)==64
    assert len(r.provenance_fingerprint)==64
    assert len(r.market_capture_fingerprints)==3
    assert r.config_fingerprint==p.fingerprint()
    assert r.source_authenticated is False
    assert r.results_engine_attested is False
    assert r.synchronized_market_windows_verified is False
    assert r.authority=="NONE"
    assert PortfolioResearchProvenance.model_validate_json(r.model_dump_json())==r


def test_reordered_markets_generate_equal_provenance():
    original=config()
    data=original.model_dump(mode="json")
    data["allocations"].reverse()
    data["scenarios"].reverse()
    shuffled=PortfolioResearchConfig.model_validate(data)
    assert capture_portfolio_provenance(original).provenance_fingerprint == (
        capture_portfolio_provenance(shuffled).provenance_fingerprint)


@pytest.mark.parametrize("field,value",[
    ("total_equity_quote","100001"),
    ("minimum_reserve_quote","100"),
])
def test_budget_updates_change_fingerprint_or_fail_reconciliation(field,value):
    p=config().model_dump(mode="json")
    p["budget"][field]=value
    changed=PortfolioResearchConfig.model_validate(p)
    assert config().fingerprint()!=changed.fingerprint()


def test_provenance_cannot_hide_changed_market_capture():
    p=config()
    original=capture_portfolio_provenance(p)
    assert original.market_capture_fingerprints[0] != original.market_capture_fingerprints[1]
    altered=config().model_dump(mode="json")
    altered["scenarios"][0]["scenario"]="HIGH_VOLATILITY"
    changed=PortfolioResearchConfig.model_validate(altered)
    assert original.config_fingerprint != changed.fingerprint()
    with pytest.raises(ValueError,match="does not bind"):
        original.verify_config(changed)


def test_tampering_with_receipt_or_embedded_config_is_rejected():
    r=capture_portfolio_provenance(config())
    raw=r.model_dump(mode="json")
    raw["allocation_fingerprint"]="0"*64
    with pytest.raises(ValidationError,match="fingerprint"):
        PortfolioResearchProvenance.model_validate(raw)
    raw=r.model_dump(mode="json")
    raw["config"]["allocations"][0]["allocated_equity_quote"]="41000"
    with pytest.raises(ValidationError):
        PortfolioResearchProvenance.model_validate(raw)


def test_decimal_equivalents_have_identical_config_identity():
    p=config()
    raw=p.model_dump(mode="json")
    raw["allocations"][0]["allocated_equity_quote"]="40000.000"
    raw["budget"]["total_equity_quote"]="100000.00"
    equiv=PortfolioResearchConfig.model_validate(raw)
    assert p.fingerprint()==equiv.fingerprint()


def test_unknown_or_unverified_source_label_cannot_upgrade_authenticity():
    p=config().model_dump(mode="json")
    p["scenarios"][0]["source_authenticated"]=True
    with pytest.raises(ValidationError):
        PortfolioResearchConfig.model_validate(p)
