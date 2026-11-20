from decimal import Decimal

import pytest

from app.amm.asset_policy_contracts import AssetResearchClassification
from app.market_data.history import MarketPriceHistory
from app.strategy.inventory import InventoryPolicy, build_inventory_state
from app.strategy.market_adaptation import MarketAdaptationPolicy
from app.strategy.perp_policy import PerpContextPolicy
from app.strategy.quote_engine import QuoteEngine
from test_phase182_generalized_paper import evidence
from test_phase185d_asset_paper import FEES_AND_FUNDING, assess_asset, asset_proposal

D = Decimal


def test_declared_families_change_provenance_without_numeric_presets():
    record = evidence(dex="xyz", name="OIL", precision=3)
    strategies, fingerprints = [], set()
    for family in ("UNKNOWN", "COMMODITY", "ENERGY", "INDEX", "EQUITY", "CRYPTO", "FX", "RATES", "OTHER"):
        proposal = asset_proposal(record, declaration={"classification": AssetResearchClassification(family=family)})
        admission, prepared = assess_asset(record, proposal)
        assert not proposal.asset_amm_policy.classification.exchange_class_verified
        strategies.append(prepared.strategy)
        fingerprints.add(admission.binding.configuration_fingerprint)
    assert all(strategy == strategies[0] for strategy in strategies)
    assert len(fingerprints) == len(strategies)


def test_existing_volatility_and_l2_policies_use_synthetic_evidence_and_keep_warmup():
    record = evidence(precision=3)
    def scenario(name, **settings):
        proposal = asset_proposal(record, scenario=name, frames=30, settings=settings)
        _, prepared = assess_asset(record, proposal)
        history = MarketPriceHistory()
        outcomes = []
        strategy = MarketAdaptationPolicy(prepared.strategy)
        for frame in prepared.dataset.frames:
            history.add_snapshot(frame.market)
            outcomes.append(strategy.decision(frame.market, history))
        return outcomes, strategy, prepared.dataset.frames[0].market

    quiet_strengths, _, _ = scenario("HIGH_VOLATILITY", volatility_spread_strength="0", volatility_size_strength="0")
    strong, policy, market = scenario("HIGH_VOLATILITY", volatility_spread_strength="1.2", volatility_size_strength="0.7")
    assert not strong[0].volatility_ready and strong[0].realized_volatility is None
    assert strong[0].spread_multiplier == 1
    assert strong[-1].realized_volatility == quiet_strengths[-1].realized_volatility
    assert strong[-1].volatility_sampling == "PER_ACCEPTED_OBSERVATION"
    assert strong[-1].spread_multiplier > quiet_strengths[-1].spread_multiplier
    assert strong[-1].global_size_multiplier < quiet_strengths[-1].global_size_multiplier

    shock, _, _ = scenario("LIQUIDITY_SHOCK")
    assert shock[5].bid_depth < shock[0].bid_depth and shock[5].ask_depth < shock[0].ask_depth
    bid_heavy, _, _ = scenario("BID_HEAVY_BOOK")
    assert bid_heavy[-1].book_imbalance > 0 and bid_heavy[-1].bid_size_multiplier < bid_heavy[-1].ask_size_multiplier
    with pytest.raises(ValueError, match="order book is required"):
        policy.decision(market.model_copy(update={"book": None}), MarketPriceHistory())


@pytest.mark.parametrize(("scenario", "sign"), [("POSITIVE_FUNDING_STRESS", 1), ("NEGATIVE_FUNDING_STRESS", -1)])
def test_explicit_funding_shift_uses_existing_policy_and_scheduled_synthetic_context(scenario, sign):
    record = evidence(precision=3)
    baseline = asset_proposal(record, scenario=scenario, economics=FEES_AND_FUNDING,
                              settings={"max_funding_reference_shift_bps": "0"})
    sensitive = asset_proposal(record, scenario=scenario, economics=FEES_AND_FUNDING,
                               settings={"max_funding_reference_shift_bps": "7"})
    _, original = assess_asset(record, baseline)
    _, adapted = assess_asset(record, sensitive)
    assert original.dataset == adapted.dataset
    _, _, frame, *_ = adapted.dataset.frames
    assert adapted.simulation.accounting.paper_funding_interval_seconds == 2
    assert frame.perp_context.funding_rate == sign * D("0.00045")
    flat = PerpContextPolicy(original.strategy).decision(frame.market.mid_price, frame.perp_context)
    shifted = PerpContextPolicy(adapted.strategy).decision(frame.market.mid_price, frame.perp_context)
    assert flat.funding_shift_bps == 0 and shifted.funding_shift_bps == -sign * 7
    assert (shifted.final_reference_price - flat.final_reference_price) * sign < 0
    rejected, _ = assess_asset(record, sensitive.model_copy(update={"economics": baseline.economics.model_copy(
        update={"funding_interval_seconds": None},
    )}))
    assert rejected.reason == "FUNDING_MODEL_UNSUPPORTED"


@pytest.mark.parametrize(("direction", "suppressed"), [(D(1), "BID"), (D(-1), "ASK")])
def test_existing_inventory_policy_uses_target_soft_limit_and_hard_side_suppression(direction, suppressed):
    record = evidence(precision=3)
    proposal = asset_proposal(record, settings={"target_inventory_base": direction * D("0.1"),
                                                "max_inventory_price_skew_bps": "30"})
    admission, prepared = assess_asset(record, proposal)
    assert prepared is not None, admission.reason
    strategy = prepared.strategy
    _, _, neutral = QuoteEngine().generate(strategy, prepared.dataset.frames[0].market)
    for limit in (strategy.soft_inventory_limit_base, strategy.hard_inventory_limit_base):
        state = build_inventory_state(
            market=strategy.market, position=strategy.target_inventory_base + direction * limit,
            target=strategy.target_inventory_base, soft_limit=strategy.soft_inventory_limit_base, source="PAPER",
        )
        quotes, decision = InventoryPolicy(strategy).apply(neutral, D(100), state)
        assert decision.inventory_ratio_effective == direction
        assert decision.price_skew_bps == -direction * 30
        assert any(quote.side == suppressed for quote in quotes) == (limit == strategy.soft_inventory_limit_base)
