"""Immutable single-native-perp research inputs; never execution eligibility."""
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.amm.numeric import quantize_size
from app.market_data.models import MarketDataMode
from app.strategy.models import ExecutionMode, StrategyConfig

ResearchPerpMarketId = Literal["BTC", "ETH", "SOL"]
MARKETS = ("BTC", "ETH", "SOL")
PROFILE_VERSION = "phase146-v1"
# Hypothetical anchors, not live quotes. Precision here is fixture evidence only.
DEMO_PROFILES = {"BTC": (Decimal("60000"), 5), "ETH": (Decimal("3000"), 4),
                 "SOL": (Decimal("150"), 2)}


class ResearchPerpMarketMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    market: ResearchPerpMarketId
    sz_decimals: StrictInt | None = Field(default=None, ge=0, le=6)
    asset_index: StrictInt | None = Field(default=None, ge=0)
    listed: bool | None = None
    metadata_status: Literal["EXCHANGE_VERIFIED", "DEMO_PROFILE", "UNAVAILABLE"]
    metadata_source: str
    metadata_observed_at: datetime | None = None
    metadata_age_seconds: float | None = None
    unavailable_reason: str | None = None


class ResearchPerpMarketProfile(ResearchPerpMarketMetadata):
    display_name: str
    exchange: Literal["HYPERLIQUID"] = "HYPERLIQUID"
    dex: Literal[""] = ""
    market_type: Literal["PERPETUAL"] = "PERPETUAL"
    research_supported: bool
    profile_version: str = PROFILE_VERSION
    profile_fingerprint: str
    simulated_reference_price: Decimal = Field(gt=0)
    research_price_rules: str = "Noninteger prices: at most 5 significant figures and 6 - szDecimals decimal places; integer prices are exempt from significant-figure limits."
    limitations: tuple[str, ...] = ("PAPER research only; metadata grants no trading authority.",
        "Fixed hypothetical reference price is not a current Hyperliquid quote.")

    def evidence(self):
        return {"research_market": self.market, "market_profile_version": self.profile_version,
                "market_profile_fingerprint": self.profile_fingerprint,
                "metadata_source": self.metadata_source, "metadata_status": self.metadata_status}


class ResearchMarketCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    catalog_version: str = PROFILE_VERSION
    research_only: Literal[True] = True
    execution_mode: Literal["PAPER"] = "PAPER"
    markets: tuple[ResearchPerpMarketProfile, ...]


def profile(metadata: ResearchPerpMarketMetadata) -> ResearchPerpMarketProfile:
    from .models import stable_fingerprint
    anchor = DEMO_PROFILES[metadata.market][0]
    # Observation times/age do not change deterministic economic identity.
    semantic = {**metadata.model_dump(exclude={"metadata_observed_at", "metadata_age_seconds", "unavailable_reason"}),
                "profile_version": PROFILE_VERSION, "simulated_reference_price": anchor}
    return ResearchPerpMarketProfile(**metadata.model_dump(), display_name=f"{metadata.market}-PERP",
        research_supported=metadata.metadata_status != "UNAVAILABLE" and metadata.listed is not False,
        simulated_reference_price=anchor, profile_fingerprint=stable_fingerprint(semantic),
        limitations=ResearchPerpMarketProfile.model_fields["limitations"].default +
        (("Simulated fixture metadata; current listing and live trading eligibility are unverified.",)
         if metadata.metadata_status == "DEMO_PROFILE" else ()))


def price_quantum(price: Decimal, sz_decimals: int) -> Decimal:
    if not price.is_finite() or price <= 0 or type(sz_decimals) is not int or not 0 <= sz_decimals <= 6:
        raise ValueError("invalid native perpetual price/precision")
    # At price >= 10000 every integer is valid, regardless of significant figures.
    return Decimal(1).scaleb(max(-(6 - sz_decimals), min(0, price.adjusted() - 4)))


def normalize_price(price: Decimal, sz_decimals: int, *, up=False) -> Decimal:
    value = price.quantize(price_quantum(price, sz_decimals), rounding=ROUND_UP if up else ROUND_DOWN)
    if value <= 0:
        raise ValueError("price is below the supported research precision")
    return value


def validate_price(price: Decimal, sz_decimals: int) -> bool:
    return normalize_price(price, sz_decimals) == price


def research_strategy(config: StrategyConfig, selected: ResearchPerpMarketProfile) -> StrategyConfig:
    if not selected.research_supported or selected.sz_decimals is None:
        raise ValueError("selected research market is unavailable")
    payload = config.model_dump()
    # Preserve quote-notional interpretation of the configured virtual pool.
    source_reference = config.virtual_quote_reserve / config.virtual_base_reserve
    ratio = source_reference / selected.simulated_reference_price
    payload.update(market=selected.market, market_data_mode=MarketDataMode.DEMO,
                   execution_mode=ExecutionMode.PAPER, size_precision=selected.sz_decimals,
                   tick_size=price_quantum(selected.simulated_reference_price, selected.sz_decimals),
                   virtual_base_reserve=config.virtual_quote_reserve / selected.simulated_reference_price)
    for name in ("base_order_size", "total_liquidity"):
        payload[name] = quantize_size(getattr(config, name) * ratio, selected.sz_decimals)
    # Inventory and risk limits are deliberately unchanged. Feasibility may fail.
    return StrategyConfig.model_validate(payload)


def normalize_quotes(quotes, selected: ResearchPerpMarketProfile):
    normalized = []
    for quote in quotes:
        price = normalize_price(quote.price, selected.sz_decimals, up=quote.side == "ASK")
        # Outward price rounding must not increase any order's proposed notional.
        ceiling = min(quote.size, quote.price * quote.size / price)
        size = quantize_size(ceiling, selected.sz_decimals)
        if size > 0:
            normalized.append(quote.model_copy(update={"price": price, "size": size}))
    return normalized
