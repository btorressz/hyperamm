from decimal import Decimal
from itertools import combinations, permutations

import pytest
from pydantic import ValidationError

from app.portfolio_research.models import PortfolioExecutedResult, PortfolioResearchRunRequest
from app.simulation.service import SimulationService
from phase172_fixtures import AMOUNTS, portfolio, request_for

SELECTIONS = [x for n in (1, 2, 3) for x in combinations(AMOUNTS, n)]


@pytest.mark.parametrize("markets", SELECTIONS)
async def test_all_market_selections_are_native_exact_and_repeatable(markets):
    request = request_for(portfolio(markets))
    service = SimulationService()
    one = await service.run_portfolio_research(request=request)
    two = await service.run_portfolio_research(request=request)
    assert one == two
    assert one.selected_markets == markets
    assert PortfolioExecutedResult.model_validate_json(one.model_dump_json()) == one
    for r in one.markets:
        assert r.metrics.starting_equity == r.vault.initial_equity_quote == Decimal(AMOUNTS[r.market])
        assert r.provenance.captured.inputs().market_profile.market == r.market
        assert r.market_assumptions.market == r.market
        assert r.provenance.result_fingerprint != r.provenance.captured.fingerprint
    assert one.unallocated_reserve_quote == Decimal("100000") - sum(Decimal(AMOUNTS[m]) for m in markets)


@pytest.mark.parametrize("order", list(permutations(AMOUNTS)))
async def test_request_order_does_not_change_complete_evidence(order):
    service = SimulationService()
    expected = await service.run_portfolio_research(request=request_for())
    actual = await service.run_portfolio_research(request=request_for(portfolio(order)))
    assert actual == expected
    assert tuple(r.market for r in actual.markets) == ("BTC", "ETH", "SOL")


async def test_captured_custom_pool_and_all_domains_are_preserved():
    # Deliberately non-anchor pool reference; normal profile adaptation would
    # replace this pool. Both AMM models remain native engine configurations.
    p = portfolio(("BTC",), overrides={"BTC": {
        "strategy": {"virtual_base_reserve": "6", "amm_model": "CONCENTRATED"},
        "agents": {"agents_enabled": False},
        "risk": {"enabled": False},
    }})
    result = await SimulationService().run_portfolio_research(request=request_for(p))
    assert result.markets[0].provenance.captured == p.scenarios[0].captured


@pytest.mark.parametrize("kind", ["unsupported", "profile", "capture", "fingerprint", "forged"])
async def test_execution_boundary_rejects_invalid_and_copied_inputs(kind):
    r = request_for()
    raw = r.model_dump()
    if kind == "unsupported": raw["config"]["scenarios"][0]["market"] = "DOGE"
    elif kind == "profile": raw["config"]["scenarios"][0]["captured"]["market_profile_fingerprint"] = "0" * 64
    elif kind == "capture": raw["config"]["scenarios"][0]["captured"] = raw["config"]["scenarios"][1]["captured"]
    elif kind == "fingerprint": raw["config_fingerprint"] = "0" * 64
    else:
        raw = r.model_copy(update={"config": r.config.model_copy(update={"authority": "MAINNET"})})
    with pytest.raises(ValueError):
        await SimulationService().run_portfolio_research(request=raw)


@pytest.mark.parametrize("frames", [1001, 5000])
def test_total_frame_budget_is_applied_across_markets(frames):
    with pytest.raises(ValidationError, match="budget"):
        request_for(portfolio(frames=frames))


def test_quote_work_and_accounting_retention_budgets_are_independent():
    from app.accounting.config import AccountingConfig
    with pytest.raises(ValueError, match="budget"):
        request_for(portfolio(("BTC",), frames=481, overrides={"BTC": {
            "strategy": {"levels_per_side": 50, "total_liquidity": "1"}}}))
    for field, value in (("ledger_max_entries", 30001), ("event_max_entries", 751)):
        account = AccountingConfig(paper_initial_equity_quote="40000", **{field: value})
        with pytest.raises(ValueError, match="budget"):
            request_for(portfolio(("BTC",), overrides={"BTC": {
                "simulation": {"accounting": account.model_dump(mode="json")}}}))


@pytest.mark.parametrize("domain,updates", [
    ("simulation", {"trace_max_points": 3000}),
    ("simulation", {"accounting": None}),
])
def test_resource_controls_are_never_silently_rewritten(domain, updates):
    if updates.get("accounting", "missing") is None:
        with pytest.raises(ValueError):
            portfolio(overrides={"BTC": {domain: updates}})
    else:
        # Three 600-frame full traces exceed the total retained trace budget.
        with pytest.raises(ValueError, match="budget"):
            request_for(portfolio(frames=600, overrides={m: {domain: updates} for m in AMOUNTS}))
