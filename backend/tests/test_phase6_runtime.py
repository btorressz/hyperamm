from decimal import Decimal as D

import pytest

from app.config import Settings
from app.execution.models import OrderRequest
from app.execution.order_manager import OrderManager
from app.execution.paper import PaperExecutionAdapter
from app.market_data.history import MarketPriceHistory
from app.strategy.inventory import build_inventory_state
from app.strategy.models import StrategyConfig
from app.strategy.market_adaptation import MarketAdaptationPolicy
from app.strategy.quote_engine import QuoteEngine
from app.market_data.mock import MockMarketDataAdapter
from app.runtime import HyperAmmRuntime


@pytest.mark.asyncio
async def test_market_version_change_blocks_stale_transmission():
    rt=HyperAmmRuntime(Settings())
    snap1=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap1)
    rt.strategy.running=True
    rt.inventory=rt._paper_inventory()
    rt.market_history.add_snapshot(snap1)
    rt._expected_inventory_version=rt.inventory.version
    rt._expected_market_version=rt.market_history.version

    snap2=MockMarketDataAdapter().snapshot_for(2)
    rt.market_history.add_snapshot(snap2)
    with pytest.raises(RuntimeError,match="market/adaptation state changed"):
        await rt._execution_authority()


@pytest.mark.asyncio
async def test_refresh_exposes_warmup_adaptation_without_fake_volatility():
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    await rt.refresh_once()
    d=rt.market_adaptation_decision
    assert d is not None
    assert d.volatility_ready is False
    assert d.realized_volatility is None
    assert d.spread_multiplier==1
    assert d.global_size_multiplier==1
    assert rt.quotes


@pytest.mark.asyncio
async def test_invalid_adaptation_cancels_active_strategy_orders(monkeypatch):
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    rt.paper.update_market(snap)
    await rt.paper.submit_orders([
        OrderRequest(
            client_order_id="resting",
            market="ETH",
            side="BID",
            price=snap.best_bid-D("100"),
            size=D(".2"),
            level_index=0,
        )
    ])
    assert await rt.paper.get_open_orders()
    rt.strategy.running=True

    def fail(*args,**kwargs):
        raise ValueError("invalid Phase 6 math")

    monkeypatch.setattr(MarketAdaptationPolicy,"apply",fail)
    await rt.refresh_once()
    assert await rt.paper.get_open_orders()==[]
    assert rt.strategy.quote_health=="DEGRADED"
    assert "invalid Phase 6 math" in rt.strategy.last_error


@pytest.mark.asyncio
async def test_kill_switch_remains_authoritative_with_phase6():
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    rt.strategy.running=True
    await rt.activate_kill()
    await rt.refresh_once()
    assert rt.risk.kill_switch_active is True
    assert rt.strategy.quote_health=="HALTED"
    assert rt.quotes==[]


@pytest.mark.asyncio
async def test_market_adaptation_summary_serializes_warmup_state():
    rt=HyperAmmRuntime(Settings())
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    await rt.refresh_once()
    payload=await rt.market_adaptation_summary()
    assert payload["market"]=="ETH"
    assert payload["volatility_ready"] is False
    assert payload["realized_volatility"] is None
    assert payload["sample_count"]==1
    assert payload["source"]=="NORMALIZED_MID_L2"
    assert payload["volatility_sampling"]=="PER_ACCEPTED_OBSERVATION"


@pytest.mark.asyncio
async def test_meaningful_phase6_change_reuses_reconciliation_replace_actions():
    adapter=MockMarketDataAdapter()
    quiet=adapter.snapshot_for(1)
    later=adapter.snapshot_for(2)
    config=StrategyConfig(
        volatility_window_samples=2,
        volatility_min_samples=2,
        volatility_low_threshold=D("0"),
        volatility_high_threshold=D("0.0000001"),
        volatility_spread_strength=D("1"),
        volatility_size_strength=D(".5"),
        imbalance_spread_strength=D("0"),
        imbalance_size_strength=D("0"),
    )
    inventory=build_inventory_state(
        market="ETH",position=D("0"),target=D("0"),soft_limit=D("5"),source="PAPER"
    )
    engine=QuoteEngine()
    history=MarketPriceHistory()
    history.add_snapshot(quiet)
    _,_,quiet_quotes,_=engine.generate_inventory_aware(config,quiet,inventory)

    execution=PaperExecutionAdapter()
    execution.update_market(quiet)
    manager=OrderManager(execution)
    initial=await manager.reconcile("ETH",quiet_quotes,config.replace_tolerance_bps,config.size_tolerance)
    assert any(action.action=="CREATE" for action in initial)

    history.add_snapshot(later)
    _,_,adaptive,_,decision=engine.generate_market_adaptive(config,later,inventory,history)
    assert decision.spread_multiplier>1
    actions=await manager.reconcile("ETH",adaptive,config.replace_tolerance_bps,config.size_tolerance)
    assert any(action.action=="REPLACE" for action in actions)


@pytest.mark.asyncio
async def test_neutral_phase6_output_can_keep_existing_quotes():
    snap=MockMarketDataAdapter().snapshot_for(1)
    config=StrategyConfig(volatility_min_samples=10)
    inventory=build_inventory_state(
        market="ETH",position=D("0"),target=D("0"),soft_limit=D("5"),source="PAPER"
    )
    history=MarketPriceHistory(); history.add_snapshot(snap)
    _,_,quotes,_,decision=QuoteEngine().generate_market_adaptive(config,snap,inventory,history)
    assert decision.volatility_ready is False

    execution=PaperExecutionAdapter(); execution.update_market(snap)
    manager=OrderManager(execution)
    await manager.reconcile("ETH",quotes,config.replace_tolerance_bps,config.size_tolerance)
    actions=await manager.reconcile("ETH",quotes,config.replace_tolerance_bps,config.size_tolerance)
    assert actions and all(action.action=="KEEP" for action in actions)


@pytest.mark.asyncio
async def test_adaptive_quote_distance_risk_violation_fails_closed():
    rt=HyperAmmRuntime(Settings())
    rt.config.volatility_window_samples=2
    rt.config.volatility_min_samples=2
    rt.config.volatility_low_threshold=D("0")
    rt.config.volatility_high_threshold=D("0.0000001")
    rt.config.volatility_spread_strength=D("2")
    rt.config.imbalance_spread_strength=D("0")
    rt.risk.max_quote_distance_bps=D("120")

    adapter=MockMarketDataAdapter()
    first=adapter.snapshot_for(1)
    second=adapter.snapshot_for(2)
    await rt.market._accept(first)
    await rt.market._accept(second)
    rt.strategy.running=True
    await rt.refresh_once()

    assert rt.strategy.quote_health=="DEGRADED"
    assert rt.quotes==[]
    assert "quote distance exceeds limit" in rt.strategy.last_error


# Seconds from a common epoch; all identities are distinct and ordered.
SAMPLING_CADENCES = [
    [0, 1, 2, 3, 4],                  # regular
    [0, .001, .002, .003, .004],      # bursty
    [0, 3600, 7200, 10800, 14400],    # sparse
    [0, .001, 7, 7.002, 14400],       # irregular
]


def timed_sampling_snapshots(offsets):
    from datetime import datetime, timedelta, timezone
    from test_phase6_market_adaptation import snapshot

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prices = ["3000", "3030", "2970", "3000", "3000"]
    snapshots = []
    for i, (price, offset) in enumerate(zip(prices, offsets), 1):
        snap = snapshot(price, i)
        timestamp = start + timedelta(seconds=offset)
        snapshots.append(snap.model_copy(update={
            "latest_valid_update": timestamp,
            "book": snap.book.model_copy(update={"timestamp": timestamp}),
        }))
    return snapshots


@pytest.mark.parametrize("offsets", SAMPLING_CADENCES, ids=["regular", "bursty", "sparse", "irregular"])
def test_count_based_sampling_window_warmup_and_duplicates(offsets):
    from app.strategy.market_adaptation import calculate_realized_volatility

    history = MarketPriceHistory()
    config = StrategyConfig(volatility_window_samples=4, volatility_min_samples=3)
    policy = MarketAdaptationPolicy(config)
    snapshots = timed_sampling_snapshots(offsets)
    for count, snap in enumerate(snapshots, 1):
        assert history.add_snapshot(snap)
        assert not history.add_snapshot(snap)  # replay is not another sample
        decision = policy.decision(snap, history)
        assert decision.sample_count == min(count, 4)
        assert decision.volatility_ready == (count >= 3)
        assert decision.volatility_sampling == "PER_ACCEPTED_OBSERVATION"
        if count < 3:
            assert decision.realized_volatility is None
            assert decision.regime == "WARMING_UP"
            assert decision.volatility_score == 0
            assert decision.spread_multiplier == decision.global_size_multiplier == 1
        else:
            expected_prices = [s.mid_price for s in snapshots[:count]][-4:]
            assert history.prices(4) == expected_prices
            assert decision.realized_volatility == calculate_realized_volatility(expected_prices)
    assert history.prices(4)[-2:] == [D("3000"), D("3000")]
    regular_history = MarketPriceHistory()
    regular_snapshots = timed_sampling_snapshots(SAMPLING_CADENCES[0])
    for snap in regular_snapshots:
        regular_history.add_snapshot(snap)
    regular = policy.decision(regular_snapshots[-1], regular_history)
    assert (decision.realized_volatility, decision.volatility_score, decision.regime) == (
        regular.realized_volatility, regular.volatility_score, regular.regime,
    )


@pytest.mark.parametrize("sigma,expected_score,expected_regime", [
    ("0.000199999999", D("0"), "QUIET"),
    ("0.0002", D("0"), "QUIET"),
    ("0.000200000001", D("0.000000000001") / D("0.0018"), "NORMAL"),
    ("0.001999999999", D("0.001799999999") / D("0.0018"), "HIGH_VOLATILITY"),
    ("0.0020", D("1"), "HIGH_VOLATILITY"),
    ("0.002000000001", D("1"), "HIGH_VOLATILITY"),
    ("0.001099999999", D("0.000899999999") / D("0.0018"), "NORMAL"),
    ("0.0011", D("0.5"), "ELEVATED"),
    ("0.001100000001", D("0.000900000001") / D("0.0018"), "ELEVATED"),
    ("0.001729999999", D("0.001529999999") / D("0.0018"), "ELEVATED"),
    ("0.00173", D("0.85"), "HIGH_VOLATILITY"),
    ("0.001730000001", D("0.001530000001") / D("0.0018"), "HIGH_VOLATILITY"),
])
def test_default_thresholds_and_regime_boundaries_are_exact(monkeypatch, sigma, expected_score, expected_regime):
    import app.strategy.market_adaptation as adaptation

    snapshots = timed_sampling_snapshots(SAMPLING_CADENCES[0])
    history = MarketPriceHistory()
    for snap in snapshots:
        history.add_snapshot(snap)
    config = StrategyConfig(volatility_min_samples=2)
    # Separate exact Decimal score boundaries from approximate logarithms.
    monkeypatch.setattr(adaptation, "calculate_realized_volatility", lambda prices: D(sigma))
    decision = MarketAdaptationPolicy(config).decision(snapshots[-1], history)
    assert decision.volatility_score == expected_score
    assert decision.regime == expected_regime
    assert adaptation.calculate_volatility_score(D(sigma), config.volatility_low_threshold, config.volatility_high_threshold) == expected_score


@pytest.mark.parametrize("threshold,delta", [("0.0002", "-1e-10"), ("0.0002", "1e-10"), ("0.002", "-1e-10"), ("0.002", "1e-10")])
def test_real_log_estimator_on_both_sides_of_default_thresholds(threshold, delta):
    from app.strategy.market_adaptation import calculate_realized_volatility, calculate_volatility_score

    target = D(threshold) + D(delta)
    sigma = calculate_realized_volatility([D("1"), target.exp()])
    assert float(sigma) == pytest.approx(float(target), rel=1e-12, abs=1e-15)
    assert (sigma < D(threshold)) == (D(delta) < 0)
    score = calculate_volatility_score(sigma, D(".0002"), D(".002"))
    assert (score == 0) == (sigma <= D(".0002"))
    assert (score == 1) == (sigma >= D(".002"))


@pytest.mark.parametrize("scale", ["1e-999999", "1", "1e999998"])
def test_extreme_positive_prices_do_not_require_float_price_conversion(scale):
    from app.strategy.market_adaptation import calculate_realized_volatility

    multiplier = D(scale)
    prices = [multiplier, multiplier * D("1.1"), multiplier * D(".99")]
    sigma = calculate_realized_volatility(prices)
    ordinary = calculate_realized_volatility([D("1"), D("1.1"), D(".99")])
    assert sigma == ordinary and sigma.is_finite()


@pytest.mark.parametrize("ratio", ["1e-307", "1e307"])
def test_extreme_representable_ratios_are_finite(ratio):
    import math
    from app.strategy.market_adaptation import calculate_realized_volatility

    sigma = calculate_realized_volatility([D("1"), D(ratio)])
    assert sigma.is_finite()
    assert float(sigma) == pytest.approx(abs(math.log(float(ratio))), rel=1e-12, abs=1e-15)


@pytest.mark.parametrize("prices", [
    [], [D("1")], [D("0"), D("1")], [D("1"), D("0")],
    [D("-1"), D("1")], [D("1"), D("-1")],
    *[[bad, D("1")] for bad in map(D, ["NaN", "sNaN", "Infinity", "-Infinity"])],
    *[[D("1"), bad] for bad in map(D, ["NaN", "sNaN", "Infinity", "-Infinity"])],
    *[[D("1"), D(ratio)] for ratio in ["1e-308", "1e-324", "1e-400", "1e309", "1e400"]],
    [D("1e999999"), D("1e-999999")], [D("1e-999999"), D("1e999999")],
])
def test_invalid_prices_and_unrepresentable_ratios_reject_before_log(monkeypatch, prices):
    import app.strategy.market_adaptation as adaptation

    def unexpected_log(value):
        pytest.fail("invalid ratio reached math.log")
    monkeypatch.setattr(adaptation.math, "log", unexpected_log)
    with pytest.raises(ValueError):
        adaptation.calculate_realized_volatility(prices)


@pytest.mark.parametrize("operation", ["log", "sqrt", "fsum"])
@pytest.mark.parametrize("result", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_math_results_never_become_accepted_decisions(monkeypatch, operation, result):
    import app.strategy.market_adaptation as adaptation

    monkeypatch.setattr(adaptation.math, operation, lambda value: result)
    with pytest.raises(ValueError):
        adaptation.calculate_realized_volatility([D("1"), D("1.1")])


@pytest.mark.parametrize("operation,result", [("log", 1e-300), ("log", 1e-160), ("log", 1e308), ("sqrt", 0.0), ("sqrt", -1.0), ("fsum", 0.0), ("fsum", -1.0)])
def test_float_underflow_overflow_or_negative_sqrt_rejected(monkeypatch, operation, result):
    import app.strategy.market_adaptation as adaptation

    monkeypatch.setattr(adaptation.math, operation, lambda value: result)
    with pytest.raises(ValueError):
        adaptation.calculate_realized_volatility([D("1"), D("1.1")])


def test_decimal_context_overflow_and_underflow_fail_closed_even_with_traps_disabled():
    from decimal import localcontext, Overflow, Underflow
    from app.strategy.market_adaptation import calculate_realized_volatility

    with localcontext() as context:
        context.Emax = 9
        context.Emin = -9
        context.traps[Overflow] = False
        context.traps[Underflow] = False
        with pytest.raises(ValueError):
            calculate_realized_volatility([D("1e-9"), D("1e9")])
        with pytest.raises(ValueError):
            calculate_realized_volatility([D("1e9"), D("1e-99")])


@pytest.mark.asyncio
async def test_numerical_volatility_failure_cancels_resting_orders(monkeypatch):
    rt = HyperAmmRuntime(Settings())
    snap = MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    rt.paper.update_market(snap)
    await rt.paper.submit_orders([OrderRequest(
        client_order_id="numeric-resting", market="ETH", side="BID",
        price=snap.best_bid-D("100"), size=D(".2"), level_index=0,
    )])
    assert await rt.paper.get_open_orders()
    rt.strategy.running = True
    rt.config.volatility_min_samples = 2
    monkeypatch.setattr(rt.market_history, "prices", lambda window: [D("1"), D("1e400")])
    await rt.refresh_once()
    assert rt.quotes == [] and await rt.paper.get_open_orders() == []
    assert rt.market_adaptation_decision is None
    assert rt.strategy.quote_health == "DEGRADED"
    assert "volatility ratio" in rt.strategy.last_error


@pytest.mark.parametrize("converted", [0.0, 1e-320, float("nan"), float("inf"), float("-inf")])
def test_float_conversion_cannot_silently_accept_invalid_results(monkeypatch, converted):
    import app.strategy.market_adaptation as adaptation

    monkeypatch.setattr(adaptation, "float", lambda ratio: converted, raising=False)
    with pytest.raises(ValueError, match="float volatility ratio"):
        adaptation.calculate_realized_volatility([D("1"), D("1.1")])


@pytest.mark.parametrize("operation", ["float", "log", "fsum", "sqrt"])
def test_float_boundary_overflow_exceptions_are_normalized(monkeypatch, operation):
    import app.strategy.market_adaptation as adaptation

    def overflow(value):
        raise OverflowError("numeric overflow")
    target = adaptation if operation == "float" else adaptation.math
    monkeypatch.setattr(target, operation, overflow, raising=operation != "float")
    with pytest.raises(ValueError, match="safely"):
        adaptation.calculate_realized_volatility([D("1"), D("1.1")])


def test_near_unity_rounding_is_limited_to_descriptive_estimator():
    from app.strategy.market_adaptation import calculate_realized_volatility

    price = D("1.00000000000000000001")
    assert price > D("1")
    assert calculate_realized_volatility([D("1"), price]) == 0
    assert price - D("1") == D("1e-20")  # financial Decimal precision retained
