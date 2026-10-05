from __future__ import annotations

from app.amm.discretizer import compile_quotes
from app.amm.models import QuoteLevel
from app.amm.virtual_reserves import initialize_virtual_pool, recenter_pool
from app.market_data.models import MarketSnapshot
from app.market_data.history import MarketPriceHistory
from .fair_value import calculate_fair_value
from .inventory import InventoryDecision, InventoryPolicy, InventoryState
from .market_adaptation import MarketAdaptationDecision, MarketAdaptationPolicy
from .perp_policy import PerpContextPolicy, PerpReferenceDecision
from app.market_data.perp_context import PerpMarketContext
from .models import StrategyConfig


class QuoteEngine:
    def generate(self, config: StrategyConfig, snapshot: MarketSnapshot) -> tuple[object, object, list[QuoteLevel]]:
        """Generate the accepted neutral Phase 4.1 ladder."""
        fair = calculate_fair_value(snapshot)
        pool = initialize_virtual_pool(config.virtual_base_reserve, config.virtual_quote_reserve)
        pool = recenter_pool(pool, fair)
        quotes = compile_quotes(
            pool=pool, fair_value=fair, model=config.amm_model, levels_per_side=config.levels_per_side,
            max_distance_bps=config.max_distance_bps, total_liquidity=config.total_liquidity,
            tick_size=config.tick_size, size_precision=config.size_precision,
            concentration_factor=config.concentration_factor, lower_bound_bps=config.concentration_lower_bps,
            upper_bound_bps=config.concentration_upper_bps, base_order_size=config.base_order_size,
        )
        return fair, pool, quotes

    def generate_at_reference(
        self, config: StrategyConfig, snapshot: MarketSnapshot, reference_price
    ) -> tuple[object, object, list[QuoteLevel]]:
        market_fair = calculate_fair_value(snapshot)
        if not reference_price.is_finite() or reference_price <= 0:
            raise ValueError("strategy reference price must be finite and positive")
        pool = initialize_virtual_pool(config.virtual_base_reserve, config.virtual_quote_reserve)
        pool = recenter_pool(pool, reference_price)
        quotes = compile_quotes(
            pool=pool, fair_value=reference_price, model=config.amm_model,
            levels_per_side=config.levels_per_side, max_distance_bps=config.max_distance_bps,
            total_liquidity=config.total_liquidity, tick_size=config.tick_size,
            size_precision=config.size_precision, concentration_factor=config.concentration_factor,
            lower_bound_bps=config.concentration_lower_bps,
            upper_bound_bps=config.concentration_upper_bps,
            base_order_size=config.base_order_size,
        )
        return market_fair, pool, quotes

    def generate_inventory_aware(
        self, config: StrategyConfig, snapshot: MarketSnapshot, inventory: InventoryState
    ) -> tuple[object, object, list[QuoteLevel], InventoryDecision]:
        fair, pool, neutral = self.generate(config, snapshot)
        quotes, decision = InventoryPolicy(config).apply(neutral, fair, inventory, fair)
        return fair, pool, quotes, decision


    def generate_market_adaptive(
        self,
        config: StrategyConfig,
        snapshot: MarketSnapshot,
        inventory: InventoryState,
        history: MarketPriceHistory,
    ) -> tuple[object, object, list[QuoteLevel], InventoryDecision, MarketAdaptationDecision]:
        fair, pool, inventory_quotes, inventory_decision = self.generate_inventory_aware(
            config, snapshot, inventory
        )
        final_quotes, market_decision = MarketAdaptationPolicy(config).apply(
            inventory_quotes, inventory_decision, snapshot, history
        )
        return fair, pool, final_quotes, inventory_decision, market_decision


    def generate_perp_market_adaptive(
        self,
        config: StrategyConfig,
        snapshot: MarketSnapshot,
        inventory: InventoryState,
        history: MarketPriceHistory,
        perp_context: PerpMarketContext,
    ) -> tuple[
        object,
        object,
        list[QuoteLevel],
        InventoryDecision,
        MarketAdaptationDecision,
        PerpReferenceDecision,
    ]:
        market_fair = calculate_fair_value(snapshot)
        perp_decision = PerpContextPolicy(config).decision(market_fair, perp_context)
        reference = perp_decision.final_reference_price
        fair, pool, neutral = self.generate_at_reference(config, snapshot, reference)
        inventory_quotes, inventory_decision = InventoryPolicy(config).apply(
            neutral, fair, inventory, reference
        )
        final_quotes, market_decision = MarketAdaptationPolicy(config).apply(
            inventory_quotes, inventory_decision, snapshot, history
        )
        return fair, pool, final_quotes, inventory_decision, market_decision, perp_decision
