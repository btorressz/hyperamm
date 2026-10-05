from __future__ import annotations

from app.amm.discretizer import compile_quotes
from app.amm.models import QuoteLevel
from app.amm.virtual_reserves import initialize_virtual_pool, recenter_pool
from app.market_data.models import MarketSnapshot
from .fair_value import calculate_fair_value
from .inventory import InventoryDecision, InventoryPolicy, InventoryState
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

    def generate_inventory_aware(
        self, config: StrategyConfig, snapshot: MarketSnapshot, inventory: InventoryState
    ) -> tuple[object, object, list[QuoteLevel], InventoryDecision]:
        fair, pool, neutral = self.generate(config, snapshot)
        quotes, decision = InventoryPolicy(config).apply(neutral, fair, inventory)
        return fair, pool, quotes, decision
