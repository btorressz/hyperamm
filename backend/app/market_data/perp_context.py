from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import MarketSnapshot, utcnow

BPS = Decimal("10000")


class PerpMarketContext(BaseModel):
    market: str
    market_mid: Decimal = Field(gt=0)
    provider_mid_price: Decimal | None = Field(default=None, gt=0)
    mark_price: Decimal = Field(gt=0)
    oracle_price: Decimal = Field(gt=0)
    funding_rate: Decimal
    open_interest_base: Decimal = Field(ge=0)
    open_interest_notional: Decimal = Field(ge=0)
    mark_oracle_basis_bps: Decimal
    mark_mid_basis_bps: Decimal
    oracle_mid_basis_bps: Decimal
    premium: Decimal | None = None
    updated_at: datetime = Field(default_factory=utcnow)
    stale: bool = False
    version: int = Field(default=0, ge=0)
    source: Literal["HYPERLIQUID", "DEMO"]
    simulated: bool = False


class PerpPositionContext(BaseModel):
    market: str
    signed_position_base: Decimal
    entry_price: Decimal | None = None
    leverage_type: str | None = None
    leverage_value: Decimal | None = None
    liquidation_price: Decimal | None = None
    margin_used: Decimal | None = None
    position_value: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    return_on_equity: Decimal | None = None
    updated_at: datetime = Field(default_factory=utcnow)
    stale: bool = False
    version: int = Field(default=0, ge=0)
    source: Literal["PAPER", "TESTNET"]


def _decimal(value: Any, name: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"invalid {name}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite {name}")
    if positive and result <= 0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _optional_decimal(value: Any, name: str, *, positive: bool = False) -> Decimal | None:
    if value is None or value == "":
        return None
    text = str(value)
    if text.lower() in {"none", "null"}:
        return None
    result = _decimal(value, name)
    if positive and result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _basis(numerator: Decimal, denominator: Decimal) -> Decimal:
    return (numerator - denominator) / denominator * BPS


def build_perp_market_context(
    *,
    market: str,
    market_mid: Decimal,
    mark_price: Decimal,
    oracle_price: Decimal,
    funding_rate: Decimal,
    open_interest_base: Decimal,
    premium: Decimal | None,
    provider_mid_price: Decimal | None,
    updated_at: datetime,
    source: Literal["HYPERLIQUID", "DEMO"],
    simulated: bool,
    version: int = 0,
    stale: bool = False,
) -> PerpMarketContext:
    for value, name in (
        (market_mid, "market mid"),
        (mark_price, "mark price"),
        (oracle_price, "oracle price"),
        (funding_rate, "funding rate"),
        (open_interest_base, "open interest"),
    ):
        if not value.is_finite():
            raise ValueError(f"non-finite {name}")
    if market_mid <= 0 or mark_price <= 0 or oracle_price <= 0:
        raise ValueError("perp prices must be positive")
    if open_interest_base < 0:
        raise ValueError("open interest must be non-negative")
    if premium is not None and not premium.is_finite():
        raise ValueError("non-finite premium")
    if provider_mid_price is not None and (not provider_mid_price.is_finite() or provider_mid_price <= 0):
        raise ValueError("invalid provider mid price")
    oi_notional = open_interest_base * mark_price
    return PerpMarketContext(
        market=market,
        market_mid=market_mid,
        provider_mid_price=provider_mid_price,
        mark_price=mark_price,
        oracle_price=oracle_price,
        funding_rate=funding_rate,
        open_interest_base=open_interest_base,
        open_interest_notional=oi_notional,
        mark_oracle_basis_bps=_basis(mark_price, oracle_price),
        mark_mid_basis_bps=_basis(mark_price, market_mid),
        oracle_mid_basis_bps=_basis(oracle_price, market_mid),
        premium=premium,
        updated_at=updated_at,
        stale=stale,
        version=version,
        source=source,
        simulated=simulated,
    )


def normalize_active_asset_ctx(payload: dict[str, Any], market: str, *, updated_at: datetime | None = None) -> PerpMarketContext:
    data = payload.get("data", payload)
    if not isinstance(data, dict) or data.get("coin") != market or not isinstance(data.get("ctx"), dict):
        raise ValueError("activeAssetCtx market/context mismatch")
    ctx = data["ctx"]
    mark = _decimal(ctx.get("markPx"), "mark price", positive=True)
    oracle = _decimal(ctx.get("oraclePx"), "oracle price", positive=True)
    funding = _decimal(ctx.get("funding"), "funding rate")
    oi = _decimal(ctx.get("openInterest"), "open interest", nonnegative=True)
    provider_mid = _optional_decimal(ctx.get("midPx"), "provider mid price", positive=True)
    premium = _optional_decimal(ctx.get("premium"), "premium")
    initial_mid = provider_mid or mark
    return build_perp_market_context(
        market=market,
        market_mid=initial_mid,
        provider_mid_price=provider_mid,
        mark_price=mark,
        oracle_price=oracle,
        funding_rate=funding,
        open_interest_base=oi,
        premium=premium,
        updated_at=updated_at or utcnow(),
        source="HYPERLIQUID",
        simulated=False,
    )


def normalize_meta_and_asset_ctxs(payload: Any, market: str, *, updated_at: datetime | None = None) -> PerpMarketContext:
    if not isinstance(payload, (list, tuple)) or len(payload) != 2:
        raise ValueError("invalid metaAndAssetCtxs response")
    meta, contexts = payload
    if not isinstance(meta, dict) or not isinstance(meta.get("universe"), list) or not isinstance(contexts, list):
        raise ValueError("malformed metaAndAssetCtxs response")
    matches = [i for i, asset in enumerate(meta["universe"]) if isinstance(asset, dict) and asset.get("name") == market]
    if len(matches) != 1:
        raise ValueError("missing or duplicate configured market in Hyperliquid universe")
    index = matches[0]
    if index >= len(contexts) or not isinstance(contexts[index], dict):
        raise ValueError("configured market asset context is missing")
    return normalize_active_asset_ctx(
        {"data": {"coin": market, "ctx": contexts[index]}},
        market,
        updated_at=updated_at,
    )


def demo_perp_context(snapshot: MarketSnapshot) -> PerpMarketContext:
    if snapshot.mid_price is None or snapshot.book is None or snapshot.stale:
        raise ValueError("valid market snapshot required for demo perp context")
    mid = snapshot.mid_price
    sequence = snapshot.book.sequence
    mark_bps = Decimal((sequence % 7) - 3) * Decimal("0.35")
    oracle_bps = Decimal((sequence % 5) - 2) * Decimal("0.20")
    funding = Decimal((sequence % 5) - 2) * Decimal("0.00001")
    mark = mid * (Decimal("1") + mark_bps / BPS)
    oracle = mid * (Decimal("1") + oracle_bps / BPS)
    oi = Decimal("250000") + Decimal(sequence % 1000)
    premium = (mark - oracle) / oracle
    return build_perp_market_context(
        market=snapshot.market,
        market_mid=mid,
        provider_mid_price=mid,
        mark_price=mark,
        oracle_price=oracle,
        funding_rate=funding,
        open_interest_base=oi,
        premium=premium,
        updated_at=snapshot.latest_valid_update or snapshot.book.timestamp,
        source="DEMO",
        simulated=True,
    )


def normalize_user_position_context(
    user_state: Any,
    market: str,
    *,
    updated_at: datetime | None = None,
    version: int = 0,
) -> PerpPositionContext:
    if not isinstance(user_state, dict) or not isinstance(user_state.get("assetPositions"), list):
        raise ValueError("Hyperliquid user state missing assetPositions")
    matches: list[dict[str, Any]] = []
    for item in user_state["assetPositions"]:
        if not isinstance(item, dict) or not isinstance(item.get("position"), dict):
            raise ValueError("malformed Hyperliquid asset position")
        if item["position"].get("coin") == market:
            matches.append(item["position"])
    if len(matches) > 1:
        raise ValueError("duplicate Hyperliquid positions for configured market")
    if not matches:
        return PerpPositionContext(
            market=market,
            signed_position_base=Decimal("0"),
            updated_at=updated_at or utcnow(),
            version=version,
            source="TESTNET",
        )
    raw = matches[0]
    signed = _decimal(raw.get("szi"), "signed base position")
    leverage = raw.get("leverage")
    leverage_type = None
    leverage_value = None
    if leverage is not None:
        if not isinstance(leverage, dict) or leverage.get("type") not in {"cross", "isolated"}:
            raise ValueError("invalid Hyperliquid leverage context")
        leverage_type = str(leverage["type"])
        leverage_value = _optional_decimal(leverage.get("value"), "leverage value", positive=True)
    return PerpPositionContext(
        market=market,
        signed_position_base=signed,
        entry_price=_optional_decimal(raw.get("entryPx"), "entry price", positive=True),
        leverage_type=leverage_type,
        leverage_value=leverage_value,
        liquidation_price=_optional_decimal(raw.get("liquidationPx"), "liquidation price", positive=True),
        margin_used=_optional_decimal(raw.get("marginUsed"), "margin used"),
        position_value=_optional_decimal(raw.get("positionValue"), "position value"),
        unrealized_pnl=_optional_decimal(raw.get("unrealizedPnl"), "unrealized PnL"),
        return_on_equity=_optional_decimal(raw.get("returnOnEquity"), "return on equity"),
        updated_at=updated_at or utcnow(),
        version=version,
        source="TESTNET",
    )


class PerpContextService:
    def __init__(self, market: str, stale_after_seconds: float):
        self.market = market
        self.stale_after_seconds = stale_after_seconds
        self._context: PerpMarketContext | None = None
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def clear(self) -> None:
        self._context = None
        self._version += 1

    def accept(self, context: PerpMarketContext) -> bool:
        if context.market != self.market:
            raise ValueError("perp context market mismatch")
        fingerprint = (
            context.mark_price,
            context.oracle_price,
            context.funding_rate,
            context.open_interest_base,
            context.premium,
            context.provider_mid_price,
            context.source,
        )
        if self._context is not None:
            current = (
                self._context.mark_price,
                self._context.oracle_price,
                self._context.funding_rate,
                self._context.open_interest_base,
                self._context.premium,
                self._context.provider_mid_price,
                self._context.source,
            )
            if context.updated_at <= self._context.updated_at:
                return False
            if fingerprint == current:
                self._context = self._context.model_copy(
                    update={"updated_at": context.updated_at, "stale": False}
                )
                return False
        self._version += 1
        self._context = context.model_copy(update={"version": self._version, "stale": False})
        return True

    def snapshot(self, market_mid: Decimal, *, now: datetime | None = None) -> PerpMarketContext:
        if self._context is None:
            raise RuntimeError("perpetual market context is unavailable")
        current = now or datetime.now(timezone.utc)
        age = (current - self._context.updated_at).total_seconds()
        stale = age < 0 or age > self.stale_after_seconds
        context = build_perp_market_context(
            market=self._context.market,
            market_mid=market_mid,
            provider_mid_price=self._context.provider_mid_price,
            mark_price=self._context.mark_price,
            oracle_price=self._context.oracle_price,
            funding_rate=self._context.funding_rate,
            open_interest_base=self._context.open_interest_base,
            premium=self._context.premium,
            updated_at=self._context.updated_at,
            source=self._context.source,
            simulated=self._context.simulated,
            version=self._context.version,
            stale=stale,
        )
        if context.stale:
            raise RuntimeError("perpetual market context is stale")
        return context
