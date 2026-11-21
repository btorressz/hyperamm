"""Emit compact fixed-clock PAPER captures for comparison across Git trees.

Run with both backend and backend/tests on PYTHONPATH. Stdout contains only
the compact JSON capture in the requested mode, including full receipts.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import sys

from app.amm.models import AmmModel
from app.simulation import engine, generalized_market_profiles as paper
from app.simulation.scenarios import ScenarioName
from test_phase182_generalized_paper import admit, proposal_for
from test_phase183b_market_risk_metadata import market_wire, observation
from test_phase183c_market_risk_calculations import hypothetical, sourced
from test_phase185d_asset_paper import CATALOG, FEES_AND_FUNDING, asset_proposal


NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
SCENARIOS = (ScenarioName.QUIET, ScenarioName.HIGH_VOLATILITY, ScenarioName.FLASH_MOVE)
STRESS = {
    "name": "fall", "price_shock_bps": "-2000", "collateral_loss_bps": "300",
    "capital_reduction_bps": "50", "funding_cost_bps": "15", "fees_bps": "10",
}


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)


async def capture(asset_aware):
    pairs = []
    for coin, dex, precision, price, model in (
        ("DOGE", "", 2, "0.1234", AmmModel.CONSTANT_PRODUCT),
        ("xyz:GOLD", "xyz", 3, "2500", AmmModel.CONCENTRATED),
    ):
        raw = market_wire(dex, coin=coin, index=268 if dex else 0,
                          mode="noCross" if dex else "strictIsolated")
        raw["universe"][0]["szDecimals"] = precision
        source = observation(dex=dex, raw=raw, now=NOW)
        metadata = source.metadata
        risk_modes = (
            None,
            hypothetical(capital_paper_quote="10000", stresses=[STRESS]),
            sourced(source, capital_paper_quote="10000", stresses=[STRESS]),
        )
        for risk in risk_modes:
            scenarios = SCENARIOS if asset_aware or risk is not None else tuple(ScenarioName)
            for scenario in scenarios:
                inputs = {"price": price, "frames": 40, "scenario": scenario,
                          "economics": FEES_AND_FUNDING, "research_risk": risk}
                proposal = (asset_proposal(metadata, settings={"amm_model": model}, **inputs)
                            if asset_aware else proposal_for(metadata, **inputs))
                binding = {
                    "catalog_valid_until": NOW + timedelta(seconds=60),
                    "risk_source": source if risk is risk_modes[2] else None,
                }
                admission, _ = admit(metadata, proposal, catalog_fingerprint=CATALOG, **binding)
                assert admission.status == "ELIGIBLE", (coin, scenario, risk, admission.reason)
                result = await paper.execute_paper(
                    engine.SimulationEngine(), proposal=proposal, metadata=metadata,
                    network=metadata.identity.network, expected=admission.binding,
                    max_age_seconds=60, catalog_guard=lambda: True, **binding,
                )
                pairs.append((admission.model_dump_json(), result.model_dump_json()))
    assert len(pairs) == (18 if asset_aware else 38)
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("standard", "asset"))
    args = parser.parse_args()
    original = paper.datetime
    paper.datetime = FixedClock
    try:
        json.dump(asyncio.run(capture(args.mode == "asset")), sys.stdout, separators=(",", ":"))
    finally:
        paper.datetime = original


if __name__ == "__main__":
    main()
