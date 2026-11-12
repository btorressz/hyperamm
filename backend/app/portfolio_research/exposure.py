"""Filled-position exposure and explicit independent-capital denominators."""
from decimal import Decimal, localcontext

from app.market_data.live_models import financial_decimal
from app.simulation.market_profiles import validate_price
from .accounting import validate_native_accounting
from .models import (MarketExposure, PortfolioExposureReport, PortfolioAccountingReport,
    PortfolioTemporalReport, PortfolioMarketReceipt, sealed)
from .config import portfolio_ratio


def position_notional(*, market, base_currency, quote_currency, position_base, mark_price_quote, profile):
    """Exact signed base × quote/base, with explicit captured native units."""
    if market != profile.market or base_currency != market or quote_currency != "USDC":
        raise ValueError("market or base/quote units mismatch")
    with localcontext() as ctx:
        ctx.prec = 80
        position, mark = financial_decimal(position_base), financial_decimal(mark_price_quote)
        if not validate_price(mark, profile.sz_decimals):
            raise ValueError("market mark precision mismatch")
        if position != position.quantize(Decimal(1).scaleb(-profile.sz_decimals)):
            raise ValueError("position is not in captured market base units")
        return financial_decimal(position * mark)


def calculate_exposure(receipts, accounting, temporal):
    accounting = PortfolioAccountingReport.model_validate(accounting)
    temporal = PortfolioTemporalReport.model_validate(temporal)
    receipts = tuple(PortfolioMarketReceipt.model_validate(r) for r in receipts)
    identities = tuple(r.receipt_fingerprint for r in receipts)
    if (identities != tuple(c.market_receipt_fingerprint for c in accounting.contributions) or
            identities != tuple(c.market_receipt_fingerprint for c in temporal.clocks) or
            accounting.temporal_fingerprint != temporal.evidence_fingerprint):
        raise ValueError("exposure accounting/source identity mismatch")
    with localcontext() as ctx:
        ctx.prec = 80
        positions = []
        for r in receipts:
            v = validate_native_accounting(r)
            profile = r.provenance.captured.inputs().market_profile
            notional = position_notional(market=r.market, base_currency=r.market,
                quote_currency="USDC", position_base=v.position_base, mark_price_quote=v.mark_price, profile=profile)
            positions.append((r, v, notional))
        supported = accounting.status == "SUPPORTED" and temporal.classification in {"MODELED_ALIGNED", "FINAL_ONLY"}
        gross = sum((abs(n) for _, _, n in positions), Decimal("0")) if supported else None
        per_market = tuple(MarketExposure(market=r.market, base_currency=r.market,
            market_receipt_fingerprint=r.receipt_fingerprint,
            source_run_fingerprint=r.provenance.run_fingerprint,
            market_profile_fingerprint=r.provenance.captured.market_profile_fingerprint,
            valuation_at=v.updated_at, position_base=v.position_base, mark_price_quote=v.mark_price,
            signed_exposure_quote=n, gross_concentration=(portfolio_ratio(abs(n), gross) if gross else Decimal("0")) if supported else None)
            for r, v, n in positions)
        equity = accounting.equity_quote
        leverage = portfolio_ratio(gross, equity) if supported and equity is not None and equity > 0 else None
        # Native reservations may include existing and proposed quotes. They are
        # not filled inventory and are never inferred from omitted order history.
        reserved = (sum((v.reserved_capital_quote for _, v, _ in positions), Decimal("0"))
            if supported and all(v.reserved_capital_quote is not None for _, v, _ in positions) else None)
        return sealed(PortfolioExposureReport, temporal_fingerprint=temporal.evidence_fingerprint,
            accounting_fingerprint=accounting.evidence_fingerprint, positions=per_market,
            gross_exposure_quote=gross if supported else None,
            net_exposure_quote=sum((n for _, _, n in positions), Decimal("0")) if supported else None,
            max_inventory_concentration=max(p.gross_concentration for p in per_market) if supported else None,
            gross_notional_utilization=leverage, modeled_leverage=leverage,
            reserved_capital_quote=reserved,
            reserved_capital_utilization=portfolio_ratio(reserved, equity) if reserved is not None and equity is not None and equity > 0 else None)
