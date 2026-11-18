"""Portfolio shock feasibility uses the same quantities as native execution."""
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.portfolio_research.preview import prepare
from app.portfolio_research.scenarios import (
    LiquidityDepthError, baseline_dataset, transform_dataset, validate_liquidity_depth,
)
from app.simulation.engine import SimulationEngine
from app.simulation.service import SimulationService
from phase174_fixtures import request_for
from test_phase175_terminal import URL, authority, draft, offline_catalog, profiles, research_client


def liquidity(*, bid, ask="1", markets=("SOL",), **kwargs):
    return request_for("LIQUIDITY_SHOCK", markets=markets, assumptions={
        "bid_depth_multiplier": bid, "ask_depth_multiplier": ask, "spread_multiplier": "3",
    }, **kwargs)


@pytest.mark.parametrize(("market", "precision", "below", "exact", "above"), [
    ("BTC", 5, "0.001999", "0.002", "0.002001"),
    ("ETH", 4, "0.000999", "0.001", "0.001001"),
    ("SOL", 2, "0.004999", "0.005", "0.005001"),
])
@pytest.mark.parametrize("side", ["bid", "ask"])
def test_depth_quantum_boundaries(market, precision, below, exact, above, side):
    def make(multiplier):
        return liquidity(markets=(market,), scenario="LIQUIDITY_SHOCK", onset=4, duration=1,
                         **({"bid": multiplier} if side == "bid" else {"bid": "1", "ask": multiplier}))

    with pytest.raises(LiquidityDepthError, match=rf"{market} {side.upper()}.*{precision} decimal"):
        validate_liquidity_depth(make(below))
    for multiplier in (exact, above):
        request = make(multiplier)
        validate_liquidity_depth(request)
        scenario, = request.config.scenarios
        original = baseline_dataset(scenario)
        stressed = transform_dataset(original, scenario, request.scenario)
        levels = getattr(stressed.frames[4].market.book, side + "s")
        assert levels[-1].size == Decimal(1).scaleb(-precision)
        assert stressed.frames[:4] == original.frames[:4]
        assert stressed.frames[5:] == original.frames[5:]


@pytest.mark.parametrize(("recovery", "sizes"), [
    ("STEP_WINDOW", ("0.24", "0.02", "0.02")),
    ("LINEAR_TO_BASELINE", ("0.24", "1.01", "2.00")),
])
def test_actual_onset_and_recovery_window(recovery, sizes):
    request = liquidity(bid="0.01", markets=("BTC", "SOL"), selected=("SOL",),
                        scenario="LIQUIDITY_SHOCK", onset=3, duration=3, recovery=recovery)
    validate_liquidity_depth(request)
    btc, sol = request.config.scenarios
    unchanged = baseline_dataset(btc)
    assert transform_dataset(unchanged, btc, request.scenario) == unchanged
    original = baseline_dataset(sol)
    stressed = transform_dataset(original, sol, request.scenario)
    assert tuple(f.market.book.bids[-1].size for f in stressed.frames[3:6]) == tuple(map(Decimal, sizes))
    assert stressed.frames[:3] == original.frames[:3]
    assert stressed.frames[6:] == original.frames[6:]


def test_recovered_shallow_frame_passes_only_linear_profile():
    options = dict(bid="0.0009", scenario="LIQUIDITY_SHOCK", onset=3, duration=2)
    with pytest.raises(LiquidityDepthError, match="SOL BID"):
        validate_liquidity_depth(liquidity(**options))
    validate_liquidity_depth(liquidity(**options, recovery="LINEAR_TO_BASELINE"))


@pytest.mark.asyncio
async def test_canonical_assumptions_preserve_native_identity():
    first = liquidity(bid="0.005", ask="0.0050", scenario="LIQUIDITY_SHOCK", onset=4, duration=1)
    second = liquidity(bid="0.005000", ask="0.005", scenario="LIQUIDITY_SHOCK", onset=4, duration=1)
    a = await SimulationService().stress_portfolio_research(request=first)
    b = await SimulationService().stress_portfolio_research(request=second)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")


def test_preview_and_both_native_routes_reject_before_baseline(research_client, monkeypatch):
    client, runtime = research_client
    invalid = liquidity(bid="0.000001", ask="0.000001")
    draft_body = draft(("SOL",), stress=invalid.scenario)
    with pytest.raises(LiquidityDepthError, match="SOL BID.*2 decimal places"):
        prepare(draft_body, profiles())
    run_engine = SimulationEngine.run
    spy = AsyncMock(side_effect=run_engine)

    async def counted(self, **kwargs):
        return await spy(self, **kwargs)

    monkeypatch.setattr(SimulationEngine, "run", counted)
    before = authority(runtime)
    wire = invalid.model_dump(mode="json")
    for path, body in (("preview", draft_body.model_dump(mode="json")), ("stress", wire),
                       ("terminal", {**wire, "mode": "STRESS"})):
        response = client.post(URL + path, json=body)
        assert response.status_code == 422, response.text
        assert response.headers["cache-control"] == "no-store"
        detail = response.json()["detail"]
        assert {key: detail[key] for key in ("code", "market", "side", "size_decimals")} == {
            "code": "LIQUIDITY_DEPTH_PRECISION", "market": "SOL", "side": "BID", "size_decimals": 2,
        }
        spy.assert_not_awaited()
    assert authority(runtime) == before

    tiny = liquidity(bid="1e-18", ask="1")
    with pytest.raises(LiquidityDepthError, match="SOL BID"):
        validate_liquidity_depth(tiny)

    corrected = liquidity(bid="0.005", ask="0.005")
    response = client.post(URL + "stress", json=corrected.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    assert spy.await_count == 2
    assert authority(runtime) == before
