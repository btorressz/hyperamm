"""Native 17.2 execution and bounded 17.3 projections, shared by focused tests."""
import asyncio

import pytest

from app.portfolio_research.aggregation import assemble_analysis
from app.portfolio_research.models import PortfolioAnalysisRequest, PortfolioRiskPolicy, sealed
from app.portfolio_research.orchestration import execute_markets
from app.simulation.service import SimulationService
from phase172_fixtures import portfolio, AMOUNTS


def request_for(p=None, **kwargs):
    p = p or portfolio()
    return PortfolioAnalysisRequest(config=p, config_fingerprint=p.fingerprint(), **kwargs)


async def native(p):
    markets, evidence = await execute_markets(SimulationService(), p, collect_accounting=True)
    return p, markets, evidence, assemble_analysis(p, markets, evidence, PortfolioRiskPolicy())


@pytest.fixture(scope="session")
def native173():
    return asyncio.run(native(portfolio(frames=12, scenario="FLASH_MOVE")))


def reseal(value, **changes):
    payload = {name: getattr(value, name) for name in type(value).model_fields if name != "evidence_fingerprint"}
    payload.update(changes)
    return sealed(type(value), **payload)
