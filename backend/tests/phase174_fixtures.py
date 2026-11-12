"""Bounded native stress request builders."""
from app.portfolio_research.models import PortfolioStressRequest, PortfolioStressScenario
from phase172_fixtures import portfolio, AMOUNTS
from app.accounting.config import AccountingConfig


def request_for(kind="CORRELATED_SELLOFF", markets=("BTC", "ETH", "SOL"), *, frames=12,
                onset=4, duration=None, overrides=None, assumptions=None, selected=None, scenario="FLASH_MOVE", recovery="STEP_WINDOW"):
    overrides = overrides or {}
    changes = {}
    for m in markets:
        changes[m] = {"simulation": {"accounting": {
            "ledger_max_entries": 5000, "event_max_entries": 125,
            "paper_funding_accounting_enabled": True, "paper_funding_interval_seconds": 1}}}
        for domain, values in overrides.get(m, {}).items():
            values = dict(values)
            if domain == "simulation" and "accounting" in values:
                values["accounting"] = {**changes[m]["simulation"]["accounting"], **values["accounting"]}
            changes[m].setdefault(domain, {}).update(values)
        account = {**AccountingConfig(paper_initial_equity_quote=AMOUNTS[m]).model_dump(mode="json"),
                   **changes[m]["simulation"]["accounting"]}
        changes[m]["simulation"]["accounting"] = AccountingConfig.model_validate(account).model_dump(mode="json")
    p = portfolio(markets, frames=frames, scenario=scenario, overrides=changes)
    selected = selected or markets
    values = {
        "CORRELATED_SELLOFF": {"price_shocks": tuple({"market": m, "decline_fraction": "0.06"} for m in selected)},
        "BTC_LED_VOLATILITY": {"btc_decline_fraction": "0.06", **{f"{m.lower()}_transmission": "1.5" if m == "ETH" else "2" for m in selected if m != "BTC"}},
        "LIQUIDITY_SHOCK": {"bid_depth_multiplier": "0.1", "ask_depth_multiplier": "0.2", "spread_multiplier": "3"},
        "FUNDING_STRESS": {"funding_shocks": tuple({"market": m, "adjustment": "0.001"} for m in selected)},
        "ORACLE_DEGRADATION": {"reference_mode": "MISSING", "reference_source": "redstone"},
        "CONCENTRATION_STRESS": {"concentration_decline_fraction": "0.1"},
    }
    stress = PortfolioStressScenario(scenario_type=kind, selected_markets=selected, onset_frame=onset,
        duration_frames=duration or frames-onset, recovery_profile=recovery, assumptions=assumptions or values[kind])
    return PortfolioStressRequest(config=p, config_fingerprint=p.fingerprint(), scenario=stress)


import asyncio
import pytest
from app.simulation.service import SimulationService

KINDS = ("CORRELATED_SELLOFF", "BTC_LED_VOLATILITY", "LIQUIDITY_SHOCK", "FUNDING_STRESS", "ORACLE_DEGRADATION", "CONCENTRATION_STRESS")

@pytest.fixture(scope="session", params=KINDS)
def native174(request):
    return asyncio.run(SimulationService().stress_portfolio_research(request=request_for(
        request.param, onset=7 if request.param == "CONCENTRATION_STRESS" else 4)))

@pytest.fixture(scope="session")
def selloff174():
    return asyncio.run(SimulationService().stress_portfolio_research(request=request_for()))

@pytest.fixture(scope="session")
def concentration174():
    return asyncio.run(SimulationService().stress_portfolio_research(request=request_for("CONCENTRATION_STRESS",onset=7)))
