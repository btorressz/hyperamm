from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.market_data.perp_context import PerpMarketContext
from .models import StrategyConfig

BPS = Decimal("10000")


class PerpReferenceDecision(BaseModel):
    market_fair_value: Decimal = Field(gt=0)
    mark_price: Decimal = Field(gt=0)
    oracle_price: Decimal = Field(gt=0)
    mid_weight: Decimal = Field(ge=0, le=1)
    mark_weight: Decimal = Field(ge=0, le=1)
    oracle_weight: Decimal = Field(ge=0, le=1)
    blended_reference_price: Decimal = Field(gt=0)
    funding_score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    funding_shift_bps: Decimal
    candidate_reference_price: Decimal = Field(gt=0)
    final_reference_price: Decimal = Field(gt=0)
    final_reference_shift_bps: Decimal
    mark_oracle_basis_bps: Decimal
    mark_mid_basis_bps: Decimal
    oracle_mid_basis_bps: Decimal
    version: int = Field(ge=0)
    enabled: bool


def _finite(value: Decimal, name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


def clamp(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    _finite(value, "clamp value")
    _finite(minimum, "clamp minimum")
    _finite(maximum, "clamp maximum")
    if maximum < minimum:
        raise ValueError("invalid clamp bounds")
    return max(minimum, min(maximum, value))


def calculate_funding_score(funding_rate: Decimal, reference_abs_rate: Decimal) -> Decimal:
    _finite(funding_rate, "funding rate")
    _finite(reference_abs_rate, "funding reference")
    if reference_abs_rate <= 0:
        raise ValueError("funding reference must be positive")
    return clamp(funding_rate / reference_abs_rate, Decimal("-1"), Decimal("1"))


def calculate_funding_shift_bps(score: Decimal, maximum_shift_bps: Decimal) -> Decimal:
    _finite(score, "funding score")
    _finite(maximum_shift_bps, "max funding shift")
    if score < -1 or score > 1 or maximum_shift_bps < 0:
        raise ValueError("invalid funding shift inputs")
    return -score * maximum_shift_bps


def calculate_blended_reference(
    market_fair: Decimal,
    mark_price: Decimal,
    oracle_price: Decimal,
    mark_weight: Decimal,
    oracle_weight: Decimal,
) -> tuple[Decimal, Decimal]:
    for value, name in (
        (market_fair, "market fair"),
        (mark_price, "mark price"),
        (oracle_price, "oracle price"),
        (mark_weight, "mark weight"),
        (oracle_weight, "oracle weight"),
    ):
        _finite(value, name)
    if market_fair <= 0 or mark_price <= 0 or oracle_price <= 0:
        raise ValueError("reference prices must be positive")
    if mark_weight < 0 or oracle_weight < 0 or mark_weight + oracle_weight > 1:
        raise ValueError("invalid perp reference weights")
    mid_weight = Decimal("1") - mark_weight - oracle_weight
    result = market_fair * mid_weight + mark_price * mark_weight + oracle_price * oracle_weight
    if not result.is_finite() or result <= 0:
        raise ValueError("invalid blended perp reference")
    return result, mid_weight


def clamp_reference_shift(
    market_fair: Decimal,
    candidate_reference: Decimal,
    max_shift_bps: Decimal,
) -> tuple[Decimal, Decimal]:
    for value, name in (
        (market_fair, "market fair"),
        (candidate_reference, "candidate reference"),
        (max_shift_bps, "max perp reference shift"),
    ):
        _finite(value, name)
    if market_fair <= 0 or candidate_reference <= 0 or max_shift_bps < 0:
        raise ValueError("invalid reference-shift inputs")
    raw_shift = (candidate_reference - market_fair) / market_fair * BPS
    final_shift = clamp(raw_shift, -max_shift_bps, max_shift_bps)
    final_reference = market_fair * (Decimal("1") + final_shift / BPS)
    if not final_reference.is_finite() or final_reference <= 0:
        raise ValueError("invalid final perp reference")
    return final_reference, final_shift


class PerpContextPolicy:
    def __init__(self, config: StrategyConfig):
        self.config = config

    def decision(self, market_fair: Decimal, context: PerpMarketContext) -> PerpReferenceDecision:
        _finite(market_fair, "market fair")
        if market_fair <= 0:
            raise ValueError("market fair must be positive")
        if context.market != self.config.market:
            raise ValueError("perp context market does not match strategy market")
        if context.stale:
            raise ValueError("perpetual market context is stale")

        if not self.config.perp_context_enabled:
            return PerpReferenceDecision(
                market_fair_value=market_fair,
                mark_price=context.mark_price,
                oracle_price=context.oracle_price,
                mid_weight=Decimal("1"),
                mark_weight=Decimal("0"),
                oracle_weight=Decimal("0"),
                blended_reference_price=market_fair,
                funding_score=Decimal("0"),
                funding_shift_bps=Decimal("0"),
                candidate_reference_price=market_fair,
                final_reference_price=market_fair,
                final_reference_shift_bps=Decimal("0"),
                mark_oracle_basis_bps=context.mark_oracle_basis_bps,
                mark_mid_basis_bps=context.mark_mid_basis_bps,
                oracle_mid_basis_bps=context.oracle_mid_basis_bps,
                version=context.version,
                enabled=False,
            )

        blended, mid_weight = calculate_blended_reference(
            market_fair,
            context.mark_price,
            context.oracle_price,
            self.config.perp_mark_weight,
            self.config.perp_oracle_weight,
        )
        score = calculate_funding_score(context.funding_rate, self.config.funding_reference_abs_rate)
        funding_shift = calculate_funding_shift_bps(score, self.config.max_funding_reference_shift_bps)
        candidate = blended * (Decimal("1") + funding_shift / BPS)
        final_reference, final_shift = clamp_reference_shift(
            market_fair,
            candidate,
            self.config.max_perp_reference_shift_bps,
        )
        return PerpReferenceDecision(
            market_fair_value=market_fair,
            mark_price=context.mark_price,
            oracle_price=context.oracle_price,
            mid_weight=mid_weight,
            mark_weight=self.config.perp_mark_weight,
            oracle_weight=self.config.perp_oracle_weight,
            blended_reference_price=blended,
            funding_score=score,
            funding_shift_bps=funding_shift,
            candidate_reference_price=candidate,
            final_reference_price=final_reference,
            final_reference_shift_bps=final_shift,
            mark_oracle_basis_bps=context.mark_oracle_basis_bps,
            mark_mid_basis_bps=context.mark_mid_basis_bps,
            oracle_mid_basis_bps=context.oracle_mid_basis_bps,
            version=context.version,
            enabled=True,
        )
