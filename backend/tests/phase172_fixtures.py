"""Reuse the native 17.1A builders and existing runtime/HTTP fixtures."""
from app.portfolio_research.models import PortfolioResearchConfig, PortfolioResearchRunRequest
from app.research_replay.comparison import ComparisonConfigSnapshot
from phase171a_fixtures import config

AMOUNTS = {"BTC": "40000", "ETH": "35000", "SOL": "20000"}


def portfolio(markets=("BTC", "ETH", "SOL"), *, frames=4, scenario="QUIET", overrides=None):
    p = config(markets=markets, amounts=tuple(AMOUNTS[m] for m in markets))
    raw = p.model_dump()
    for s in raw["scenarios"]:
        n = frames[s["market"]] if isinstance(frames, dict) else frames
        s["frames"] = n
        s["scenario"] = scenario[s["market"]] if isinstance(scenario, dict) else scenario
        payload = s["captured"].copy()
        payload = ComparisonConfigSnapshot.model_validate(payload).inputs().model_dump(mode="json")
        payload["simulation"].update(max_frames=n, trace_max_points=min(n, 120))
        for domain, changes in (overrides or {}).get(s["market"], {}).items():
            payload[domain].update(changes)
        s["captured"] = ComparisonConfigSnapshot.from_payload(payload)
    return PortfolioResearchConfig.model_validate(raw)


def request_for(p=None):
    p = p or portfolio()
    return PortfolioResearchRunRequest(config=p, config_fingerprint=p.fingerprint())


async def standalone(service, scenario):
    i = scenario.captured.inputs()
    return await service.run_scenario(scenario=scenario.scenario.value, frames=scenario.frames,
        strategy=i.strategy, agents=i.agents, risk=i.risk, simulation=i.simulation,
        market_profile=i.market_profile, preserve_captured_strategy=True,
        include_comparison_provenance=True)
