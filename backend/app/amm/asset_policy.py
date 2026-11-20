"""Map an explicit asset declaration to an existing PAPER research strategy."""

from decimal import Context, Decimal, localcontext

from app.amm.asset_policy_contracts import AssetAmmResearchPolicy
from app.amm.numeric import quantize_size
from app.market_data.market_universe_contracts import MarketUniverseMetadata
from app.market_data.models import MarketDataMode
from app.simulation.market_profiles import GeneralizedPrecisionError, validate_price
from app.strategy.models import ExecutionMode, StrategyConfig


CONTROL_FIELDS = (
    "amm_model", "virtual_base_reserve", "virtual_quote_reserve",
    "levels_per_side", "max_distance_bps", "base_order_size", "total_liquidity",
    "concentration_factor", "concentration_lower_bps", "concentration_upper_bps",
    "target_inventory_base", "soft_inventory_limit_base", "hard_inventory_limit_base",
    "max_inventory_price_skew_bps", "volatility_spread_strength",
    "volatility_size_strength", "max_funding_reference_shift_bps",
)


def apply_asset_research_policy(
    baseline_strategy: StrategyConfig,
    policy: AssetAmmResearchPolicy,
    *,
    metadata: MarketUniverseMetadata,
) -> StrategyConfig:
    """Validate and copy a synthetic strategy. PAPER admission remains separate."""
    with localcontext(Context(prec=28)):
        policy = AssetAmmResearchPolicy.model_validate(policy)
        metadata = MarketUniverseMetadata.model_validate(metadata)
        if (policy.identity != metadata.identity or policy.metadata_fingerprint != metadata.fingerprint()
                or metadata.metadata_status != "EXCHANGE_VERIFIED" or metadata.listed is not True
                or baseline_strategy.market != metadata.identity.stable_key
                or baseline_strategy.execution_mode != ExecutionMode.PAPER
                or baseline_strategy.market_data_mode != MarketDataMode.DEMO):
            raise ValueError("asset policy requires matching listed metadata and a synthetic PAPER strategy")

        precision = metadata.sz_decimals
        try:
            representable = validate_price(policy.simulated_reference_price, precision)
        except (ArithmeticError, ValueError):
            representable = False
        if not representable:
            raise GeneralizedPrecisionError("PRICE_UNREPRESENTABLE")

        controls = policy.controls
        if quantize_size(controls.base_order_size, precision) != controls.base_order_size:
            raise GeneralizedPrecisionError("SIZE_UNREPRESENTABLE")
        if abs(controls.target_inventory_base) >= controls.hard_inventory_limit_base:
            raise ValueError("inventory target leaves no two-sided capacity from flat")

        values = baseline_strategy.model_dump()
        values.update({name: getattr(controls, name) for name in CONTROL_FIELDS})
        # The compiler uses the finest decimal grid. PAPER then rounds at the
        # actual price magnitude of each level, including across decades.
        values.update(size_precision=precision, tick_size=Decimal(1).scaleb(precision - 6))
        return StrategyConfig.model_validate(values)
