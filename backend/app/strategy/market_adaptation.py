from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from app.amm.discretizer import normalize_price, normalize_size
from app.amm.models import QuoteLevel
from app.market_data.models import MarketSnapshot, utcnow
from app.market_data.history import MarketPriceHistory
from .inventory import InventoryDecision
from .models import StrategyConfig

BPS = Decimal("10000")


class VolatilityRegime(StrEnum):
    WARMING_UP = "WARMING_UP"
    QUIET = "QUIET"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


class ImbalanceState(StrEnum):
    BALANCED = "BALANCED"
    BID_HEAVY = "BID_HEAVY"
    ASK_HEAVY = "ASK_HEAVY"


class MarketAdaptationDecision(BaseModel):
    market: str
    realized_volatility: Decimal | None = None
    volatility_score: Decimal = Field(ge=0, le=1)
    volatility_ready: bool
    sample_count: int = Field(ge=0)
    bid_depth: Decimal = Field(ge=0)
    ask_depth: Decimal = Field(ge=0)
    book_imbalance: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    spread_multiplier: Decimal = Field(gt=0)
    global_size_multiplier: Decimal = Field(gt=0)
    bid_imbalance_multiplier: Decimal = Field(gt=0)
    ask_imbalance_multiplier: Decimal = Field(gt=0)
    bid_size_multiplier: Decimal = Field(gt=0)
    ask_size_multiplier: Decimal = Field(gt=0)
    regime: VolatilityRegime
    imbalance_state: ImbalanceState
    updated_at: datetime
    stale: bool = False
    source: str = "NORMALIZED_MID_L2"
    version: int = Field(ge=0)


def _finite(value: Decimal, name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


def calculate_realized_volatility(prices: list[Decimal]) -> Decimal:
    """RMS log return: sqrt(mean(log(P_t/P_t-1)^2))."""
    if len(prices) < 2:
        raise ValueError("at least two prices are required")
    returns: list[float] = []
    for previous, current in zip(prices, prices[1:]):
        _finite(previous, "previous price")
        _finite(current, "current price")
        if previous <= 0 or current <= 0:
            raise ValueError("volatility prices must be positive")
        value = math.log(float(current / previous))
        if not math.isfinite(value):
            raise ValueError("non-finite log return")
        returns.append(value)
    sigma = math.sqrt(sum(value * value for value in returns) / len(returns))
    if not math.isfinite(sigma):
        raise ValueError("non-finite realized volatility")
    return Decimal(str(sigma))


def calculate_volatility_score(sigma: Decimal, low: Decimal, high: Decimal) -> Decimal:
    for value, name in ((sigma, "realized volatility"), (low, "low threshold"), (high, "high threshold")):
        _finite(value, name)
    if sigma < 0 or low < 0 or high <= low:
        raise ValueError("invalid volatility score inputs")
    if sigma <= low:
        return Decimal("0")
    if sigma >= high:
        return Decimal("1")
    return (sigma - low) / (high - low)


def calculate_book_imbalance(snapshot: MarketSnapshot, levels: int) -> tuple[Decimal, Decimal, Decimal]:
    if levels < 1:
        raise ValueError("book imbalance levels must be >= 1")
    book = snapshot.book
    if book is None or not book.bids or not book.asks:
        raise ValueError("non-empty normalized order book is required")
    if book.bids[0].price >= book.asks[0].price:
        raise ValueError("order book is crossed")
    selected_bids = book.bids[:levels]
    selected_asks = book.asks[:levels]
    for level in (*selected_bids, *selected_asks):
        if not level.price.is_finite() or level.price <= 0:
            raise ValueError("invalid order-book price")
        if not level.size.is_finite() or level.size < 0:
            raise ValueError("invalid order-book size")
    bid_depth = sum((level.size for level in selected_bids), Decimal("0"))
    ask_depth = sum((level.size for level in selected_asks), Decimal("0"))
    total = bid_depth + ask_depth
    if total <= 0:
        raise ValueError("selected order-book depth is zero")
    imbalance = (bid_depth - ask_depth) / total
    if not imbalance.is_finite() or imbalance < -1 or imbalance > 1:
        raise ValueError("invalid book imbalance")
    return bid_depth, ask_depth, imbalance


def calculate_spread_multiplier(config: StrategyConfig, volatility_score: Decimal, imbalance: Decimal) -> Decimal:
    _finite(volatility_score, "volatility score")
    _finite(imbalance, "book imbalance")
    if volatility_score < 0 or volatility_score > 1 or imbalance < -1 or imbalance > 1:
        raise ValueError("market adaptation inputs are out of bounds")
    raw = (
        Decimal("1")
        + config.volatility_spread_strength * volatility_score
        + config.imbalance_spread_strength * abs(imbalance)
    )
    return max(config.min_spread_multiplier, min(config.max_spread_multiplier, raw))


def calculate_size_multipliers(
    config: StrategyConfig, volatility_score: Decimal, imbalance: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    _finite(volatility_score, "volatility score")
    _finite(imbalance, "book imbalance")
    if volatility_score < 0 or volatility_score > 1 or imbalance < -1 or imbalance > 1:
        raise ValueError("market adaptation inputs are out of bounds")
    global_multiplier = max(
        config.min_market_size_multiplier,
        min(Decimal("1"), Decimal("1") - config.volatility_size_strength * volatility_score),
    )
    bid_imbalance = max(
        config.min_market_size_multiplier,
        min(Decimal("1"), Decimal("1") - config.imbalance_size_strength * max(imbalance, Decimal("0"))),
    )
    ask_imbalance = max(
        config.min_market_size_multiplier,
        min(Decimal("1"), Decimal("1") - config.imbalance_size_strength * max(-imbalance, Decimal("0"))),
    )
    return global_multiplier, bid_imbalance, ask_imbalance


def _regime(ready: bool, score: Decimal) -> VolatilityRegime:
    if not ready:
        return VolatilityRegime.WARMING_UP
    if score == 0:
        return VolatilityRegime.QUIET
    if score < Decimal("0.50"):
        return VolatilityRegime.NORMAL
    if score < Decimal("0.85"):
        return VolatilityRegime.ELEVATED
    return VolatilityRegime.HIGH_VOLATILITY


def _imbalance_state(value: Decimal) -> ImbalanceState:
    if value > Decimal("0.10"):
        return ImbalanceState.BID_HEAVY
    if value < Decimal("-0.10"):
        return ImbalanceState.ASK_HEAVY
    return ImbalanceState.BALANCED


class MarketAdaptationPolicy:
    def __init__(self, config: StrategyConfig):
        self.config = config

    def decision(
        self,
        snapshot: MarketSnapshot,
        history: MarketPriceHistory,
    ) -> MarketAdaptationDecision:
        bid_depth, ask_depth, imbalance = calculate_book_imbalance(snapshot, self.config.book_imbalance_levels)
        prices = history.prices(self.config.volatility_window_samples)
        sample_count = len(prices)
        ready = sample_count >= self.config.volatility_min_samples

        sigma = calculate_realized_volatility(prices) if ready else None
        score = (
            calculate_volatility_score(
                sigma,
                self.config.volatility_low_threshold,
                self.config.volatility_high_threshold,
            )
            if sigma is not None
            else Decimal("0")
        )

        if not self.config.market_adaptation_enabled or not ready:
            spread = Decimal("1")
            global_size = Decimal("1")
            bid_imbalance = Decimal("1")
            ask_imbalance = Decimal("1")
        else:
            spread = calculate_spread_multiplier(self.config, score, imbalance)
            global_size, bid_imbalance, ask_imbalance = calculate_size_multipliers(self.config, score, imbalance)

        bid_size = max(self.config.min_market_size_multiplier, global_size * bid_imbalance)
        ask_size = max(self.config.min_market_size_multiplier, global_size * ask_imbalance)
        for value, name in (
            (spread, "spread multiplier"),
            (global_size, "global size multiplier"),
            (bid_size, "bid size multiplier"),
            (ask_size, "ask size multiplier"),
        ):
            _finite(value, name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")

        return MarketAdaptationDecision(
            market=snapshot.market,
            realized_volatility=sigma,
            volatility_score=score,
            volatility_ready=ready,
            sample_count=sample_count,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            book_imbalance=imbalance,
            spread_multiplier=spread,
            global_size_multiplier=global_size,
            bid_imbalance_multiplier=bid_imbalance,
            ask_imbalance_multiplier=ask_imbalance,
            bid_size_multiplier=bid_size,
            ask_size_multiplier=ask_size,
            regime=_regime(ready, score),
            imbalance_state=_imbalance_state(imbalance),
            updated_at=snapshot.latest_valid_update or utcnow(),
            stale=snapshot.stale,
            version=history.version,
        )

    def apply(
        self,
        inventory_quotes: list[QuoteLevel],
        inventory_decision: InventoryDecision,
        snapshot: MarketSnapshot,
        history: MarketPriceHistory,
    ) -> tuple[list[QuoteLevel], MarketAdaptationDecision]:
        decision = self.decision(snapshot, history)
        if snapshot.stale:
            raise ValueError("market adaptation state is stale")

        neutral_adaptation = (
            not self.config.market_adaptation_enabled
            or not decision.volatility_ready
            or (
                decision.spread_multiplier == 1
                and decision.bid_size_multiplier == 1
                and decision.ask_size_multiplier == 1
            )
        )
        center = inventory_decision.reservation_price
        fair = inventory_decision.fair_value
        quantum = Decimal(1).scaleb(-self.config.size_precision)
        final: list[QuoteLevel] = []

        for quote in inventory_quotes:
            if neutral_adaptation:
                price = quote.price
                size = quote.size
            else:
                distance = abs(quote.price - center)
                widened = distance * decision.spread_multiplier
                if quote.side == "BID":
                    raw_price = center - widened
                    price = normalize_price(raw_price, self.config.tick_size, "BID")
                    multiplier = decision.bid_size_multiplier
                elif quote.side == "ASK":
                    raw_price = center + widened
                    price = normalize_price(raw_price, self.config.tick_size, "ASK")
                    multiplier = decision.ask_size_multiplier
                else:
                    raise ValueError("quote side must be BID or ASK")

                variable_size = max(Decimal("0"), quote.size - self.config.base_order_size)
                raw_size = max(self.config.base_order_size + variable_size * multiplier, quantum)
                size = normalize_size(raw_size, self.config.size_precision)

            if not price.is_finite() or not size.is_finite() or price <= 0 or size <= 0:
                raise ValueError("market-adapted quotes must be finite and positive")

            distance_bps = (
                quote.distance_bps
                if neutral_adaptation
                else abs(price - fair) / fair * BPS
            )
            final.append(
                quote.model_copy(
                    update={
                        "price": price,
                        "size": size,
                        "distance_bps": distance_bps,
                        "pre_market_adaptation_price": quote.price,
                        "pre_market_adaptation_size": quote.size,
                        "market_spread_multiplier": decision.spread_multiplier,
                        "market_size_multiplier": (
                            decision.bid_size_multiplier if quote.side == "BID" else decision.ask_size_multiplier
                        ),
                        "volatility_effect": (
                            "WARMUP"
                            if not decision.volatility_ready
                            else ("WIDENED" if decision.spread_multiplier > 1 else "NEUTRAL")
                        ),
                        "imbalance_effect": decision.imbalance_state.value,
                    }
                )
            )

        bids = sorted((quote for quote in final if quote.side == "BID"), key=lambda quote: quote.price, reverse=True)
        asks = sorted((quote for quote in final if quote.side == "ASK"), key=lambda quote: quote.price)
        if bids and asks and bids[0].price >= asks[0].price:
            raise ValueError("market-adapted quote market is crossed")
        return bids + asks, decision
