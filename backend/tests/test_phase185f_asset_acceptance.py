from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, localcontext
from fractions import Fraction

import pytest

from app.amm.models import AmmModel, QuoteLevel
from app.execution.research import PaperExecutionAssumptions
from app.market_data.history import MarketPriceHistory
from app.simulation import engine
from app.simulation.market_profiles import GeneralizedPrecisionError, round_level
from app.strategy.market_adaptation import MarketAdaptationPolicy
from test_phase182_generalized_paper import evidence
from test_phase183b_market_risk_metadata import market_wire, observation, tier
from test_phase183c_market_risk_calculations import hypothetical, sourced
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401
from test_phase185d_asset_paper import FEES_AND_FUNDING, assess_asset, asset_proposal, run_asset

D = Decimal


@pytest.mark.parametrize(("precision", "reference", "raw", "bid", "ask"), [
    (0, "0.001", "0.001234567", "0.001234", "0.001235"),
    (1, "0.0123", "0.01234567", "0.01234", "0.01235"),
    (2, "0.1234", "0.1234567", "0.1234", "0.1235"),
    (3, "9.999", "9.99999", "9.999", "10.000"),
    (4, "99.99", "99.9999", "99.99", "100.00"),
    (5, "1000.1", "9999.999", "9999.9", "10000"),
    (6, "1000000", "1000000.999", "1000000", "1000001"),
])
@pytest.mark.parametrize("model", list(AmmModel))
async def test_precision_matrix_exact_notional_and_real_ladders(precision, reference, raw, bid, ask, model,
                                                               monkeypatch, offline_boundaries):
    lot = D(10) ** -precision
    for proposed_size in (lot / 2, lot, lot * D("1000.75")):
        for up, expected in ((False, D(bid)), (True, D(ask))):
            price, size = round_level(D(raw), proposed_size, precision, up=up)
            # Maximum whole lots subject to both the submitted size and original notional.
            base_limit = min(Fraction(proposed_size), Fraction(raw) * Fraction(proposed_size) / Fraction(expected))
            assert price == expected
            assert size == (base_limit // Fraction(lot)) * lot
            assert price * size <= D(raw) * proposed_size and size >= 0

    record = evidence(name="ASSET", dex="xyz", precision=precision)
    proposal = asset_proposal(record, price=reference, settings={"amm_model": model})
    admission, prepared = assess_asset(record, proposal)
    assert prepared is not None, admission.reason
    final = []
    original = engine.authorize

    def capture(quotes, *args, **kwargs):
        final.append(tuple(quotes))
        return original(quotes, *args, **kwargs)

    monkeypatch.setattr(engine, "authorize", capture)
    outcome = await run_asset(record, proposal, admission)
    assert outcome.execution_mode == "PAPER" and outcome.admission.authority == "NONE"
    assert any(final)
    for ladder in final:
        bids, asks = ([q for q in ladder if q.side == side] for side in ("BID", "ASK"))
        if bids and asks:
            assert max(q.price for q in bids) < min(q.price for q in asks)
        for side in (bids, asks):
            assert sum(q.size for q in side) <= proposal.asset_amm_policy.controls.total_liquidity
            assert len({q.price for q in side}) == len(side)
            assert all(q.size > 0 and q.size % lot == 0 and q.price > 0 and
                       q.price * q.size >= proposal.minimum_order_notional for q in side)


def test_exact_notional_boundary_duplicate_prices_and_retired_sub_lot():
    record = evidence(precision=3)
    admission, _ = assess_asset(record, asset_proposal(record))
    profile = admission.profile
    bid = QuoteLevel(side="BID", price=D(100), size=D(".200"), level_index=0,
                     distance_bps=D(10), source_model=AmmModel.CONCENTRATED)
    ask = bid.model_copy(update={"side": "ASK", "price": D(101)})
    minimum = D(20)
    arguments = dict(minimum_order_notional=minimum, side_liquidity=D(1))
    assert profile.normalize_quotes([bid, ask], D("100.5"), preflight=True, **arguments)[0].size == D(".200")
    smaller = bid.model_copy(update={"size": D(".199")})
    with pytest.raises(GeneralizedPrecisionError, match="ORDER_NOTIONAL_TOO_SMALL"):
        profile.normalize_quotes([smaller, ask], D("100.5"), preflight=True, **arguments)
    duplicate = bid.model_copy(update={"price": D("100.001"), "level_index": 1})
    reduced = ask.model_copy(update={"level_index": 1, "pre_risk_size": D(".001"), "risk_size_multiplier": D(".99")})
    executable = profile.normalize_quotes([bid, duplicate, ask, reduced], D("100.5"), **arguments)
    assert [(quote.side, quote.level_index) for quote in executable] == [("BID", 0), ("ASK", 0)]


@pytest.mark.parametrize("scenario", ["QUIET", "HIGH_VOLATILITY", "LIQUIDITY_SHOCK", "BID_HEAVY_BOOK", "FLASH_MOVE"])
def test_adaptation_preserves_per_observation_rms_at_extreme_valid_settings(scenario):
    record = evidence(precision=3)
    proposal = asset_proposal(record, scenario=scenario, frames=30, settings={
        "volatility_spread_strength": "10", "volatility_size_strength": "1",
        "base_order_size": "0.5", "total_liquidity": "2.4",
    })
    admission, prepared = assess_asset(record, proposal)
    assert prepared is not None, admission.reason
    decision = MarketAdaptationPolicy(prepared.strategy)
    prices, observations = [], []
    history = MarketPriceHistory()
    for frame in prepared.dataset.frames:
        if history.add_snapshot(frame.market):
            prices.append(frame.market.mid_price)
        observations.append(decision.decision(frame.market, history))
    assert not observations[0].volatility_ready and observations[0].realized_volatility is None
    with localcontext() as context:
        context.prec = 60
        squares = [((right / left).ln()) ** 2 for left, right in zip(prices, prices[1:])]
        rms = (sum(squares) / len(squares)).sqrt()
    assert abs(observations[-1].realized_volatility - rms) < D("1e-15")
    assert all(D(1) <= item.spread_multiplier <= D("2.5") for item in observations)
    assert all(D(".35") <= item.global_size_multiplier <= 1 for item in observations)
    if scenario == "BID_HEAVY_BOOK":
        assert observations[-1].bid_size_multiplier < observations[-1].ask_size_multiplier
    if scenario == "LIQUIDITY_SHOCK":
        assert observations[5].bid_depth < observations[0].bid_depth


@pytest.mark.parametrize("mode", ["modeled_partial_fills", "hypothetical", "source"])
async def test_replay_fills_reservations_and_margin_with_independent_accounting(mode, monkeypatch, offline_boundaries):
    source = observation(now=datetime.now(timezone.utc))
    record = source.metadata
    settings = {"modeled_partial_fills": None, "hypothetical": hypothetical(), "source": sourced(source)}[mode]
    proposal = asset_proposal(record, scenario="HIGH_VOLATILITY", frames=40, economics=FEES_AND_FUNDING,
                              research_risk=settings)
    used_source = source if mode == "source" else None
    admission, prepared = assess_asset(record, proposal, risk_source=used_source)
    assert prepared is not None, admission.reason
    ladders = []
    original = engine.authorize

    def capture(quotes, *args, **kwargs):
        ladders.append(tuple(quotes))
        return original(quotes, *args, **kwargs)

    monkeypatch.setattr(engine, "authorize", capture)
    if mode == "modeled_partial_fills":
        # Generalized PAPER's public route uses crossing-only fills. Exercise
        # the same mapped strategy with the existing engine's modeled matcher.
        execution = PaperExecutionAssumptions(mode="MODELED_CROSSING", max_fill_fraction="0.5")
        result = await engine.SimulationEngine().run(
            dataset=prepared.dataset, strategy_config=prepared.strategy, agent_config=prepared.agents,
            risk_config=prepared.risk, simulation_config=prepared.simulation.model_copy(update={"execution": execution}),
            generalized_profile=admission.profile, minimum_order_notional=proposal.minimum_order_notional,
        )
        research_risk = None
    else:
        outcome = await run_asset(record, proposal, admission, risk_source=used_source)
        result, research_risk = outcome.result, outcome.research_risk
        assert research_risk is not None
    fills = iter(result.fills)
    initial, signed, basis, realized, signed_notional, fees, funding = Fraction(100_000), 0, 0, 0, 0, 0, 0
    pending_fee = None
    reversed_position = False
    contexts = {frame.timestamp: frame.perp_context for frame in prepared.dataset.frames}
    for line in reversed(result.accounting_ledger):
        if line.event_type == "TRADE_FILL":
            fill = next(fills)
            amount, price = Fraction(fill["size"]), Fraction(fill["price"])
            assert (line.side, Fraction(line.size), Fraction(line.price)) == (fill["side"], amount, price)
            delta = amount if fill["side"] == "BID" else -amount
            signed_notional += delta * price
            if signed * delta < 0:
                closed = min(abs(signed), amount)
                prior_average = basis / signed
                realized += closed * (price - prior_average) * (1 if signed > 0 else -1)
                basis -= prior_average * closed * (1 if signed > 0 else -1)
                basis += (amount - closed) * price * (1 if delta > 0 else -1)
            else:
                basis += price * delta
            reversed_position |= signed * (signed + delta) < 0
            signed += delta
            pending_fee = amount * price * (7 if fill["liquidity"] == "MAKER" else 13) / 10000
        elif line.event_type == "FEE":
            assert Fraction(line.fee_delta_quote) == pending_fee
            fees += pending_fee
            pending_fee = None
        elif line.event_type == "FUNDING":
            frame = contexts[line.timestamp]
            assert int(line.timestamp.timestamp()) % 2 == 0
            payment = -signed * Fraction(frame.mark_price) * Fraction(frame.funding_rate)
            assert Fraction(line.funding_delta_quote) == payment
            funding += payment
        assert Fraction(line.position_base) == signed
        assert abs(Fraction(line.cash_balance_quote) - (initial + realized - fees + funding)) < Fraction("1e-19")

    assert next(fills, None) is None and pending_fee is None and len(result.fills) > 0
    vault = result.vault
    final_mark = Fraction(prepared.dataset.frames[-1].perp_context.mark_price)
    assert vault.initial_equity_quote == 100_000
    assert Fraction(vault.position_base) == signed
    assert Fraction(vault.fees_quote) == fees and Fraction(vault.funding_quote) == funding
    assert abs(Fraction(vault.realized_pnl_quote) - realized) < Fraction("1e-20")
    unrealized = signed * final_mark - basis
    assert abs(Fraction(vault.unrealized_pnl_quote) - unrealized) < Fraction("1e-20")
    net = signed * final_mark - signed_notional - fees + funding
    assert abs(Fraction(vault.net_pnl_quote) - net) < Fraction("1e-20")
    assert abs(Fraction(vault.equity_quote) - (initial + net)) < Fraction("1e-19")
    resting = defaultdict(Fraction)
    pending_base = defaultdict(Fraction)
    has_partial_fill = False
    for order in result.orders:
        fill_amount, size = Fraction(order["filled_size"]), Fraction(order["size"])
        has_partial_fill |= 0 < fill_amount < size
        if order["status"] in {"OPEN", "PARTIALLY_FILLED"}:
            resting[order["side"], order["level_index"]] += (size - fill_amount) * Fraction(order["price"])
            pending_base[order["side"]] += size - fill_amount
    for quote in ladders[-1]:
        key = quote.side, quote.level_index
        resting[key] = max(resting[key], Fraction(quote.price) * Fraction(quote.size))
    assert Fraction(vault.reserved_capital_quote) == abs(signed) * final_mark + sum(resting.values())
    assert reversed_position
    if mode == "modeled_partial_fills":
        assert has_partial_fill
    if research_risk:
        margin = research_risk.final_snapshot.margin
        # In these fixtures one source tier uses 10x maximum and 5x selected
        # leverage, so initial fractions are 0.20 in both modes.
        projected = max(abs(signed), abs(signed + pending_base["BID"]), abs(signed - pending_base["ASK"]))
        with localcontext() as context:
            context.prec = 60
            required = projected * final_mark / 5
            initial_margin = (D(required.numerator) / D(required.denominator)).quantize(D(".00000001"), rounding=ROUND_CEILING)
        assert margin.projected_initial == initial_margin
        assert abs(Fraction(margin.projected_headroom) - (1000 + net - Fraction(initial_margin))) < Fraction("1e-20")


@pytest.mark.parametrize(("reason", "settings"), [
    ("RISK_CAPITAL_INSUFFICIENT", {"capital_paper_quote": "1"}),
    ("RISK_LEVERAGE_UNSUPPORTED", {"leverage": "11"}),
])
def test_bound_asset_settings_cannot_override_research_risk(reason, settings):
    source = observation(now=datetime.now(timezone.utc))
    if "leverage" in settings:
        proposal = asset_proposal(source.metadata, research_risk=sourced(source, **settings))
    else:
        proposal = asset_proposal(source.metadata, research_risk=hypothetical(**settings))
    admission, prepared = assess_asset(source.metadata, proposal, risk_source=source)
    assert prepared is None and admission.reason == reason and admission.binding is None


def test_unsupported_hip3_collateral_denomination_has_no_asset_policy_exception():
    source = observation(dex="xyz", now=datetime.now(timezone.utc),
                         raw=market_wire("xyz", index=268, table=56, tiers=[tier("0", 10), tier("1000", 5)]))
    proposal = asset_proposal(source.metadata, research_risk=sourced(source))
    admission, prepared = assess_asset(source.metadata, proposal, risk_source=source)
    assert prepared is None and admission.reason == "RISK_SOURCE_UNSUPPORTED"
