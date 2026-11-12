"""Joint hypothetical inputs, applied before the sole native PAPER engine."""
from decimal import Decimal, localcontext

from app.amm.numeric import quantize_size
from app.market_data.perp_context import build_perp_market_context
from app.simulation.market_profiles import normalize_price, validate_price
from app.simulation.models import SimulationDataset, SimulationFrame
from app.simulation.scenarios import DEFAULT_START, generate_scenario


def workload(config):
    inputs = [s.captured.inputs() for s in config.scenarios]
    return (sum(s.frames for s in config.scenarios),
        sum(s.frames * i.strategy.levels_per_side for s, i in zip(config.scenarios, inputs)),
        sum(min(s.frames, i.simulation.trace_max_points) if i.simulation.record_trace else 0
            for s, i in zip(config.scenarios, inputs)),
        sum(i.simulation.accounting.ledger_max_entries for i in inputs),
        sum(i.simulation.accounting.event_max_entries for i in inputs))


def validate_joint_config(config, scenario):
    markets = {s.market for s in config.scenarios}
    if not set(scenario.selected_markets) <= markets:
        raise ValueError("stress market outside portfolio")
    if len({(s.scenario, s.frames) for s in config.scenarios}) != 1:
        raise ValueError("joint stress requires a common baseline scenario and window")
    a = scenario.assumptions
    for s in config.scenarios:
        sim = s.captured.inputs().simulation
        if scenario.scenario_type == "CONCENTRATION_STRESS" and (
                not sim.record_trace or sim.trace_max_points < s.frames):
            raise ValueError("concentration selection requires complete native position histories")
        if s.market not in scenario.selected_markets:
            continue
        lag = (a.propagation_lag_frames or 0) if scenario.scenario_type == "BTC_LED_VOLATILITY" and s.market != "BTC" else 0
        if scenario.onset_frame + lag + scenario.duration_frames > s.frames:
            raise ValueError("shock window exceeds the captured scenario clock")
        if scenario.scenario_type == "FUNDING_STRESS":
            interval = sim.accounting.paper_funding_interval_seconds
            # The first observation initializes native funding; a fully
            # recovered final frame also carries no adjustment to accrue.
            end = scenario.onset_frame + scenario.duration_frames - (scenario.recovery_profile == "LINEAR_TO_BASELINE")
            if not sim.accounting.paper_funding_accounting_enabled or not any(
                    int(DEFAULT_START.timestamp() + i) % interval == 0
                    for i in range(max(1, scenario.onset_frame), end)):
                raise ValueError("funding stress requires native accounting and an observed funding boundary")


def baseline_dataset(scenario):
    profile = scenario.captured.inputs().market_profile
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = "ROUND_HALF_EVEN"
        return generate_scenario(scenario.scenario, frames=scenario.frames,
                                 market=scenario.market, market_profile=profile)


def validate_dataset(dataset, scenario):
    # JSON round-trip revalidates mutable nested native models and forged copies.
    dataset = SimulationDataset.model_validate_json(dataset.model_dump_json())
    from datetime import timedelta
    p = scenario.captured.inputs().market_profile
    if dataset.market != scenario.market or len(dataset.frames) != scenario.frames or dataset.simulated is not True:
        raise ValueError("stress dataset market/count/simulation mismatch")
    for i, f in enumerate(dataset.frames):
        if (f.sequence != i + 1 or f.timestamp != DEFAULT_START + timedelta(seconds=i) or
                f.market.mode.value != "DEMO" or f.market.simulated is not True or
                f.perp_context.source != "DEMO" or f.perp_context.simulated is not True):
            raise ValueError("stress dataset clock or source mismatch")
        for side, levels in (("BID", f.market.book.bids), ("ASK", f.market.book.asks)):
            if not levels or any(not validate_price(v.price, p.sz_decimals) or
                    not v.size.is_finite() or v.size <= 0 or
                    v.size != quantize_size(v.size, p.sz_decimals) for v in levels):
                raise ValueError("invalid stress book price/size precision")
            if any((x.price < y.price if side == "BID" else x.price > y.price)
                   for x, y in zip(levels, levels[1:])):
                raise ValueError("stress book levels are unsorted")
        c = f.perp_context
        if (not validate_price(c.mark_price, p.sz_decimals) or not validate_price(c.oracle_price, p.sz_decimals)
                or not c.funding_rate.is_finite() or abs(c.funding_rate) > Decimal("0.02")):
            raise ValueError("invalid stress perp inputs")
    return dataset


def transform_dataset(dataset, market_scenario, stress, *, concentration_market=None, concentration_position=None):
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = "ROUND_HALF_EVEN"
        return _transform_dataset(dataset, market_scenario, stress,
            concentration_market=concentration_market, concentration_position=concentration_position)


def _transform_dataset(dataset, market_scenario, stress, *, concentration_market, concentration_position):
    dataset = validate_dataset(dataset, market_scenario)
    if dataset.fingerprint != baseline_dataset(market_scenario).fingerprint:
        raise ValueError("stress must start from the canonical baseline dataset")
    market = market_scenario.market
    if market not in stress.selected_markets or (stress.scenario_type == "CONCENTRATION_STRESS" and market != concentration_market):
        return dataset
    a, kind = stress.assumptions, stress.scenario_type
    lag = (a.propagation_lag_frames or 0) if kind == "BTC_LED_VOLATILITY" and market != "BTC" else 0
    onset = stress.onset_frame + lag
    p = market_scenario.captured.inputs().market_profile
    frames = []
    for i, original in enumerate(dataset.frames):
        if not onset <= i < onset + stress.duration_frames:
            frames.append(original)
            continue
        strength = (Decimal(1) - Decimal(i - onset) / Decimal(stress.duration_frames - 1)
                    if stress.recovery_profile == "LINEAR_TO_BASELINE" else Decimal(1))
        factor = Decimal(1)
        if kind == "CORRELATED_SELLOFF":
            factor -= next(s.decline_fraction for s in a.price_shocks if s.market == market) * strength
        elif kind == "BTC_LED_VOLATILITY":
            transmission = Decimal(1) if market == "BTC" else getattr(a, f"{market.lower()}_transmission")
            factor -= a.btc_decline_fraction * transmission * strength
        elif kind == "CONCENTRATION_STRESS":
            if concentration_position is None or not concentration_position:
                raise ValueError("concentration stress requires a validated nonzero pre-onset position")
            # Price down hurts a long; price up hurts a short.
            factor += (-1 if concentration_position > 0 else 1) * a.concentration_decline_fraction * strength
        raw = original.model_dump()
        mid = original.market.mid_price
        for side, up in (("bids", False), ("asks", True)):
            for level in raw["market"]["book"][side]:
                price = level["price"] * factor
                if kind == "LIQUIDITY_SHOCK":
                    price = mid + (price - mid) * (1 + (a.spread_multiplier - 1) * strength)
                    multiplier = a.bid_depth_multiplier if side == "bids" else a.ask_depth_multiplier
                    level["size"] = quantize_size(level["size"] * (1 + (multiplier - 1) * strength), p.sz_decimals)
                level["price"] = normalize_price(price, p.sz_decimals, up=up)
        bid, ask = raw["market"]["book"]["bids"][0]["price"], raw["market"]["book"]["asks"][0]["price"]
        new_mid = (bid + ask) / 2
        raw["market"].update(best_bid=bid, best_ask=ask, mid_price=new_mid)
        ratio = new_mid / mid
        old = original.perp_context
        mark = normalize_price(old.mark_price * ratio, p.sz_decimals)
        oracle = normalize_price(old.oracle_price * ratio, p.sz_decimals)
        rate = old.funding_rate
        if kind == "FUNDING_STRESS":
            rate += next(s.adjustment for s in a.funding_shocks if s.market == market) * strength
        raw["perp_context"] = build_perp_market_context(market=market, market_mid=new_mid,
            provider_mid_price=new_mid, mark_price=mark, oracle_price=oracle, funding_rate=rate,
            open_interest_base=old.open_interest_base, premium=(mark - oracle) / oracle,
            updated_at=original.timestamp, source="DEMO", simulated=True, version=original.sequence).model_dump()
        raw["reference_prices"] = {name: (normalize_price(value * ratio, p.sz_decimals) if ratio != 1 else value) if value is not None else None
                                   for name, value in original.reference_prices.model_dump().items()}
        if kind == "ORACLE_DEGRADATION":
            source = a.reference_source
            if a.reference_mode == "MISSING":
                raw["reference_prices"][source] = None
            else:
                value = original.reference_prices.model_dump()[source]
                if value is None:
                    raise ValueError("cannot diverge a missing baseline reference source")
                raw["reference_prices"][source] = normalize_price(value * (1 + a.reference_divergence_fraction), p.sz_decimals, up=True)
        frames.append(SimulationFrame.model_validate(raw))
    # The source binds assumptions even when rounding produces the same prices.
    result = SimulationDataset(market=market, frames=tuple(frames), simulated=True,
        source=f"{dataset.source}:phase174:{stress.fingerprint()}")
    return validate_dataset(result, market_scenario)
