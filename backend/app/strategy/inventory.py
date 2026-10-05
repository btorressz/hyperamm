from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.amm.discretizer import normalize_price, normalize_size
from app.amm.models import QuoteLevel
from app.market_data.models import utcnow
from .models import StrategyConfig

BPS = Decimal("10000")


class HardInventoryLimitState(StrEnum):
    NORMAL = "NORMAL"
    LONG_LIMIT = "LONG_LIMIT"
    SHORT_LIMIT = "SHORT_LIMIT"


class InventoryIntent(StrEnum):
    INVENTORY_INCREASING = "INVENTORY_INCREASING"
    INVENTORY_REDUCING = "INVENTORY_REDUCING"
    NEUTRAL = "NEUTRAL"


class InventoryState(BaseModel):
    market: str
    position_base: Decimal
    target_base: Decimal
    deviation_base: Decimal
    inventory_ratio: Decimal
    source: Literal["PAPER", "TESTNET"]
    updated_at: datetime = Field(default_factory=utcnow)
    stale: bool = False
    version: int = Field(default=0, ge=0)
    error: str | None = None


class InventoryDecision(BaseModel):
    fair_value: Decimal
    reservation_price: Decimal
    price_skew_bps: Decimal
    inventory_ratio_effective: Decimal
    bid_size_multiplier: Decimal
    ask_size_multiplier: Decimal
    hard_limit_state: HardInventoryLimitState


def _finite(value: Decimal, name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


def calculate_inventory_ratio(position: Decimal, target: Decimal, soft_limit: Decimal) -> Decimal:
    _finite(position, "position")
    _finite(target, "target")
    _finite(soft_limit, "soft inventory limit")
    if soft_limit <= 0:
        raise ValueError("soft inventory limit must be positive")
    return (position - target) / soft_limit


def clamp_inventory_ratio(ratio: Decimal) -> Decimal:
    _finite(ratio, "inventory ratio")
    return max(Decimal("-1"), min(Decimal("1"), ratio))


def calculate_reservation_price(fair_value: Decimal, ratio: Decimal, max_skew_bps: Decimal) -> tuple[Decimal, Decimal]:
    _finite(fair_value, "fair value")
    _finite(max_skew_bps, "max inventory price skew")
    if fair_value <= 0 or max_skew_bps < 0:
        raise ValueError("invalid reservation-price inputs")
    r = clamp_inventory_ratio(ratio)
    shift_bps = -r * max_skew_bps
    reservation = fair_value * (Decimal("1") + shift_bps / BPS)
    if not reservation.is_finite() or reservation <= 0:
        raise ValueError("reservation price must be finite and positive")
    return reservation, shift_bps


def calculate_side_size_multipliers(
    ratio: Decimal,
    strength: Decimal,
    minimum: Decimal,
    maximum: Decimal,
) -> tuple[Decimal, Decimal]:
    for value, name in ((strength, "size skew strength"), (minimum, "minimum multiplier"), (maximum, "maximum multiplier")):
        _finite(value, name)
    if strength < 0 or minimum <= 0 or maximum < Decimal("1") or minimum > maximum:
        raise ValueError("invalid inventory size multiplier configuration")
    r = clamp_inventory_ratio(ratio)
    bid = Decimal("1") - strength * r
    ask = Decimal("1") + strength * r
    return max(minimum, min(maximum, bid)), max(minimum, min(maximum, ask))


def hard_limit_state(deviation: Decimal, hard_limit: Decimal) -> HardInventoryLimitState:
    _finite(deviation, "inventory deviation")
    _finite(hard_limit, "hard inventory limit")
    if hard_limit <= 0:
        raise ValueError("hard inventory limit must be positive")
    if deviation >= hard_limit:
        return HardInventoryLimitState.LONG_LIMIT
    if deviation <= -hard_limit:
        return HardInventoryLimitState.SHORT_LIMIT
    return HardInventoryLimitState.NORMAL


def classify_inventory_intent(side: str, deviation: Decimal) -> InventoryIntent:
    if side not in {"BID", "ASK"}:
        raise ValueError("quote side must be BID or ASK")
    _finite(deviation, "inventory deviation")
    if deviation == 0:
        return InventoryIntent.NEUTRAL
    if deviation > 0:
        return InventoryIntent.INVENTORY_INCREASING if side == "BID" else InventoryIntent.INVENTORY_REDUCING
    return InventoryIntent.INVENTORY_REDUCING if side == "BID" else InventoryIntent.INVENTORY_INCREASING


def build_inventory_state(
    *, market: str, position: Decimal, target: Decimal, soft_limit: Decimal,
    source: Literal["PAPER", "TESTNET"], updated_at: datetime | None = None,
    stale: bool = False, version: int = 0, error: str | None = None,
) -> InventoryState:
    ratio = calculate_inventory_ratio(position, target, soft_limit)
    return InventoryState(
        market=market,
        position_base=position,
        target_base=target,
        deviation_base=position-target,
        inventory_ratio=ratio,
        source=source,
        updated_at=updated_at or utcnow(),
        stale=stale,
        version=version,
        error=error,
    )


class InventoryPolicy:
    def __init__(self, config: StrategyConfig):
        self.config = config

    def decision(self, fair_value: Decimal, state: InventoryState) -> InventoryDecision:
        if state.market != self.config.market:
            raise ValueError("inventory market does not match strategy market")
        if state.stale or state.error:
            raise ValueError(state.error or "inventory state is stale")
        expected_ratio = calculate_inventory_ratio(
            state.position_base, self.config.target_inventory_base, self.config.soft_inventory_limit_base
        )
        if state.target_base != self.config.target_inventory_base or state.inventory_ratio != expected_ratio:
            raise ValueError("inventory state does not match current strategy configuration")
        effective = clamp_inventory_ratio(expected_ratio) if self.config.inventory_skew_enabled else Decimal("0")
        reservation, price_skew = calculate_reservation_price(
            fair_value, effective, self.config.max_inventory_price_skew_bps
        )
        bid_multiplier, ask_multiplier = calculate_side_size_multipliers(
            effective,
            self.config.inventory_size_skew_strength,
            self.config.min_inventory_size_multiplier,
            self.config.max_inventory_size_multiplier,
        )
        return InventoryDecision(
            fair_value=fair_value,
            reservation_price=reservation,
            price_skew_bps=price_skew,
            inventory_ratio_effective=effective,
            bid_size_multiplier=bid_multiplier,
            ask_size_multiplier=ask_multiplier,
            hard_limit_state=hard_limit_state(state.deviation_base, self.config.hard_inventory_limit_base),
        )

    def apply(self, neutral_quotes: list[QuoteLevel], fair_value: Decimal, state: InventoryState) -> tuple[list[QuoteLevel], InventoryDecision]:
        decision = self.decision(fair_value, state)
        price_factor = decision.reservation_price / fair_value
        quantum = Decimal(1).scaleb(-self.config.size_precision)
        final: list[QuoteLevel] = []
        for quote in neutral_quotes:
            intent = classify_inventory_intent(quote.side, state.deviation_base)
            if decision.hard_limit_state == HardInventoryLimitState.LONG_LIMIT and quote.side == "BID":
                continue
            if decision.hard_limit_state == HardInventoryLimitState.SHORT_LIMIT and quote.side == "ASK":
                continue

            price = quote.price
            size = quote.size
            effect = "NEUTRAL"
            if self.config.inventory_skew_enabled and decision.inventory_ratio_effective != 0:
                raw_price = quote.price * price_factor
                price = normalize_price(raw_price, self.config.tick_size, quote.side)
                if quote.side == "BID":
                    max_bid = normalize_price(fair_value - self.config.tick_size, self.config.tick_size, "BID")
                    if max_bid <= 0:
                        raise ValueError("tick size leaves no valid bid below fair value")
                    price = min(price, max_bid)
                    multiplier = decision.bid_size_multiplier
                else:
                    min_ask = normalize_price(fair_value + self.config.tick_size, self.config.tick_size, "ASK")
                    price = max(price, min_ask)
                    multiplier = decision.ask_size_multiplier
                raw_size = max(quote.size * multiplier, quantum)
                size = normalize_size(raw_size, self.config.size_precision)
                effect = "SKEWED"

            distance = quote.distance_bps if effect == "NEUTRAL" else abs(price - fair_value) / fair_value * BPS
            final.append(quote.model_copy(update={
                "price": price,
                "size": size,
                "distance_bps": distance,
                "neutral_price": quote.price,
                "neutral_size": quote.size,
                "inventory_intent": intent.value,
                "inventory_effect": effect,
            }))

        bids = sorted((q for q in final if q.side == "BID"), key=lambda q: q.price, reverse=True)
        asks = sorted((q for q in final if q.side == "ASK"), key=lambda q: q.price)
        if bids and asks and bids[0].price >= asks[0].price:
            raise ValueError("inventory-adjusted quote market is crossed")
        if any(not q.price.is_finite() or not q.size.is_finite() or q.price <= 0 or q.size <= 0 for q in final):
            raise ValueError("inventory-adjusted quotes must be finite and positive")
        return bids + asks, decision
