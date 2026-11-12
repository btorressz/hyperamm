"""Phase 17.1A: exact shared-budget validation, no simulated equity aggregation."""
from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.portfolio_research.allocation import allocation_totals
from app.portfolio_research.models import PortfolioCapitalBudget, PortfolioResearchConfig
from phase171a_fixtures import config, market_scenario


def test_partial_and_full_allocations_are_distinct():
    p=config()
    assert p.unallocated_reserve_quote == Decimal("5000")
    full=config(amounts=("40000","35000","25000"))
    assert full.unallocated_reserve_quote == 0
    assert p.fingerprint()!=full.fingerprint()


def test_allocation_order_is_semantic_not_ordinal():
    p=config()
    swapped=p.model_dump(mode="json")
    swapped["allocations"].reverse()
    swapped["scenarios"].reverse()
    q=PortfolioResearchConfig.model_validate(swapped)
    assert p.canonical_payload()==q.canonical_payload()
    assert p.fingerprint()==q.fingerprint()


@pytest.mark.parametrize("market",["DOGE","XRP","ETH-PERP",""])
def test_unsupported_markets_fail_closed(market):
    p=config().model_dump(mode="json")
    p["allocations"][0]["market"]=market
    with pytest.raises(ValidationError):
        PortfolioResearchConfig.model_validate(p)


def test_duplicate_allocation_rejected_before_aggregation():
    p=config().model_dump(mode="json")
    p["allocations"][1]["market"]="BTC"
    with pytest.raises(ValidationError):
        PortfolioResearchConfig.model_validate(p)


def test_overbudget_allocations_are_rejected():
    p=config().model_dump(mode="json")
    p["allocations"][2]["allocated_equity_quote"]="25001"
    with pytest.raises(ValidationError,match="budget"):
        PortfolioResearchConfig.model_validate(p)


def test_reserve_floor_must_be_satisfied():
    with pytest.raises(ValidationError,match="reserve"):
        config(minimum_reserve="5000.0001")


@pytest.mark.parametrize("amount",["0","-1","NaN","Infinity","1e9999",0.5,True])
def test_invalid_allocation_money_rejected(amount):
    p=config().model_dump(mode="json")
    p["allocations"][0]["allocated_equity_quote"]=amount
    with pytest.raises(ValidationError):
        PortfolioResearchConfig.model_validate(p)


def test_scenario_markets_must_match_allocation_set():
    p=config().model_dump(mode="json")
    p["scenarios"].pop()
    with pytest.raises(ValidationError,match="scenario markets"):
        PortfolioResearchConfig.model_validate(p)


def test_allocation_capital_must_match_simulation_and_accounting():
    p=config().model_dump(mode="json")
    p["allocations"][0]["allocated_equity_quote"]="41000"
    with pytest.raises(ValidationError,match="simulation capital"):
        PortfolioResearchConfig.model_validate(p)


def test_exact_18_digit_fraction_reconciles_without_default_decimal_rounding():
    full=Decimal("999999999999.999999999999999999")
    amounts=[("BTC",Decimal("999999999998.999999999999999999")),
             ("ETH",Decimal("0.000000000000000001"))]
    allocated, reserve=allocation_totals(full,amounts)
    assert allocated == Decimal("999999999999.000000000000000000")
    assert reserve == Decimal("0.999999999999999999")


def test_overprecision_fails_closed_before_fingerprinting():
    with pytest.raises(ValidationError):
        PortfolioCapitalBudget(total_equity_quote="1.0000000000000000001")
