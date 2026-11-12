"""Phase 17.1A: read-only portfolio contracts, no computation or API."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.portfolio_research.models import (
    PortfolioCapitalBudget, PortfolioExposureSnapshot, PortfolioResearchResult,
    PortfolioRiskLimits, PortfolioResearchConfig,
)
from phase171a_fixtures import config


def test_supported_three_market_portfolio_and_exact_unallocated_reserve():
    portfolio = config(minimum_reserve="5000")
    assert portfolio.contract_version == "phase17-portfolio-research-v1"
    assert portfolio.allocated_equity_quote == Decimal("95000")
    assert portfolio.unallocated_reserve_quote == Decimal("5000")
    assert tuple(a.market for a in portfolio.allocations) == ("BTC","ETH","SOL")
    assert portfolio.execution_mode == "PAPER"
    assert portfolio.read_only and portfolio.authority == "NONE"
    assert PortfolioResearchConfig.model_validate_json(portfolio.model_dump_json()) == portfolio


@pytest.mark.parametrize("invalid",[
    {"execution_mode":"TESTNET"}, {"simulated":False}, {"authority":"PAPER"},
    {"read_only":False}, {"contract_version":"phase17-portfolio-research-v2"},
    {"extra_wallet":"secret"},
])
def test_portfolio_rejects_authority_and_unknown_fields(invalid):
    source=config().model_dump(mode="json")
    source.update(invalid)
    with pytest.raises(ValidationError):
        PortfolioResearchConfig.model_validate(source)


@pytest.mark.parametrize("invalid",[
    {"quote_currency":"USD"}, {"total_equity_quote":0},
    {"total_equity_quote":"1000000000001"}, {"minimum_reserve_quote":"-1"},
    {"total_equity_quote":"NaN"}, {"total_equity_quote":float("inf")},
    {"total_equity_quote":0.1}, {"total_equity_quote":"1e9999999"},
])
def test_budget_rejects_unsupported_or_unsafe_money(invalid):
    raw={"total_equity_quote":"100000",**invalid}
    with pytest.raises(ValidationError):
        PortfolioCapitalBudget.model_validate(raw)


def test_exposure_contract_does_not_create_verified_aggregate():
    data=dict(market="BTC",source_run_fingerprint="a"*64,
              as_of="2026-11-11T00:00:00Z",position_base="-0.25",
              mark_price_quote="60000",gross_exposure_quote="15000",
              signed_exposure_quote="-15000")
    value=PortfolioExposureSnapshot(**data)
    assert value.portfolio_aggregate_verified is False
    assert value.authority == "NONE"
    with pytest.raises(ValidationError):
        PortfolioExposureSnapshot(**data, portfolio_aggregate_verified=True)


def test_result_is_nonexecuted_placeholder_with_no_aggregated_metrics():
    c=config()
    result=PortfolioResearchResult(config_fingerprint=c.fingerprint())
    assert result.status == "NOT_EXECUTED"
    assert result.aggregate_equity_quote is None and result.aggregate_pnl_quote is None
    with pytest.raises(ValidationError):
        PortfolioResearchResult(config_fingerprint=c.fingerprint(),status="COMPLETED")
    with pytest.raises(ValidationError):
        PortfolioResearchResult(config_fingerprint=c.fingerprint(),aggregate_pnl_quote="15")


def test_risk_ceilings_are_static_research_configuration_only():
    with pytest.raises(ValidationError):
        PortfolioRiskLimits(max_gross_exposure_quote="100",
            max_abs_net_exposure_quote="100",max_session_loss_quote="10",
            max_drawdown_fraction="1.1",max_capital_utilization="1",
            max_inventory_concentration="0.5",modeled_leverage_ceiling="2")
