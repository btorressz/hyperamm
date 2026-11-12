"""Pure reconciliation of native PAPER economics; no fill or ledger replay."""
from decimal import Decimal, localcontext

from app.accounting.models import PositionAccounting, VaultSnapshot
from app.accounting.pnl import pnl_breakdown, mark_position, drawdown
from app.simulation.models import stable_fingerprint
from .models import (MarketAccountingEvidence, NativeAccountingObservation,
    MarketEconomicContribution, PortfolioAccountingReport, PortfolioDrawdownEvidence,
    PortfolioMarketExecution, sealed)
from .config import portfolio_ratio

ZERO = Decimal("0")


def validate_native_accounting(receipt):
    """Reuse accounting's mark and PnL authority at its native precision."""
    vault = VaultSnapshot.model_validate_json(receipt.vault.model_dump_json())
    required = ("initial_equity_quote", "equity_quote", "position_base", "mark_price",
                "average_entry_price", "realized_pnl_quote", "unrealized_pnl_quote",
                "net_pnl_quote", "fees_quote", "funding_quote", "position_value_quote")
    if (vault.source != "PAPER_RESEARCH" or vault.mode != "PAPER" or vault.simulated is not True or
            vault.market != receipt.market or
            vault.stale or vault.accounting_complete != "COMPLETE" or
            any(getattr(vault, f) is None for f in required)):
        raise ValueError("complete native PAPER economics required")
    if (vault.mark_price <= 0 or vault.fees_quote < 0 or
            vault.updated_at != receipt.market_assumptions.representative_frame_timestamp or
            vault.mark_price != receipt.market_assumptions.mark_price):
        raise ValueError("native valuation identity mismatch")
    with localcontext() as ctx:
        ctx.prec = 28  # Existing AccountingService economic semantics.
        position = mark_position(PositionAccounting(market=vault.market,
            position_base=vault.position_base, average_entry_price=vault.average_entry_price,
            realized_pnl_quote=vault.realized_pnl_quote), vault.mark_price)
        pnl = pnl_breakdown(position, vault.fees_quote, vault.funding_quote)
        if (position.position_value_quote != vault.position_value_quote or
                position.unrealized_pnl_quote != vault.unrealized_pnl_quote or
                pnl.net_pnl != vault.net_pnl_quote or pnl.session_pnl != vault.session_pnl_quote or
                pnl.gross_trading_pnl != vault.gross_pnl_quote or
                vault.equity_quote != vault.initial_equity_quote + pnl.net_pnl):
            raise ValueError("native accounting reconciliation failed")
    metrics = receipt.metrics
    if (metrics.ending_equity != vault.equity_quote or metrics.session_pnl != vault.net_pnl_quote or
            metrics.ending_inventory_base != vault.position_base or
            metrics.realized_pnl != vault.realized_pnl_quote or
            metrics.unrealized_pnl != vault.unrealized_pnl_quote):
        raise ValueError("native metrics disagree with accounting")
    if vault.reserved_capital_quote is not None and (vault.reserved_capital_quote < 0 or
            vault.reservation_source != "SIMULATED_CAPITAL_RESERVATION"):
        raise ValueError("invalid native reservation evidence")
    return vault


def collect_native_accounting(execution, receipt):
    execution = PortfolioMarketExecution.model_validate(execution)
    result = execution.captured_result.result
    if (receipt.provenance != execution.captured_result.provenance or receipt.vault != result.vault or
            receipt.metrics != result.metrics or receipt.market_assumptions != result.research_assumptions):
        raise ValueError("native accounting projection substituted execution")
    v = validate_native_accounting(receipt)
    from .exposure import position_notional
    profile = execution.scenario.captured.inputs().market_profile
    points = tuple(NativeAccountingObservation(sequence=p.sequence, timestamp=p.timestamp,
        equity_quote=p.equity, session_pnl_quote=p.session_pnl,
        position_base=p.inventory_base, mark_price_quote=p.mark)
        for p in execution.captured_result.result.trace)
    for p in points:
        position_notional(market=receipt.market, base_currency=receipt.market, quote_currency="USDC",
            position_base=p.position_base, mark_price_quote=p.mark_price_quote, profile=profile)
    with localcontext() as ctx:
        ctx.prec = 28
        if any(p.equity_quote != v.initial_equity_quote + p.session_pnl_quote for p in points):
            raise ValueError("native trace accounting mismatch")
    if points and (points[-1].equity_quote != v.equity_quote or
            points[-1].session_pnl_quote != v.net_pnl_quote or
            points[-1].position_base != v.position_base or points[-1].mark_price_quote != v.mark_price):
        raise ValueError("native timeline endpoint mismatch")
    return sealed(MarketAccountingEvidence, market=receipt.market,
        market_receipt_fingerprint=receipt.receipt_fingerprint, observations=points)


def portfolio_drawdown(config, temporal, evidence):
    if temporal.classification != "MODELED_ALIGNED":
        return None
    if tuple(e.evidence_fingerprint for e in evidence) != tuple(
            c.native_evidence_fingerprint for c in temporal.clocks):
        raise ValueError("drawdown native source mismatch")
    with localcontext() as ctx:
        ctx.prec = 80
        initial = config.budget.total_equity_quote
        peak, maximum = initial, ZERO
        curve = []
        for points in zip(*(e.observations for e in evidence), strict=True):
            if len({p.timestamp for p in points}) != 1:
                raise ValueError("drawdown observations not aligned")
            equity = config.unallocated_reserve_quote + sum((p.equity_quote for p in points), ZERO)
            peak = max(peak, equity)
            amount, native_fraction = drawdown(equity, peak)  # Existing fraction convention.
            if native_fraction is None:
                raise ValueError("positive portfolio peak required")
            fraction = portfolio_ratio(amount, peak)
            maximum = max(maximum, fraction)
            curve.append((points[0].timestamp, equity))
        if not curve:
            raise ValueError("complete nonempty portfolio equity history required")
        return sealed(PortfolioDrawdownEvidence, observation_count=len(curve),
            equity_series_fingerprint=stable_fingerprint({"initial_equity": initial, "curve": curve}),
            native_evidence_fingerprints=tuple(e.evidence_fingerprint for e in evidence),
            peak_equity_quote=peak, ending_drawdown_fraction=fraction,
            max_drawdown_fraction=maximum)


def reconcile_accounting(config, receipts, temporal, *, drawdown_evidence=None):
    config = type(config).model_validate(config)
    by_market = {a.market: a.allocated_equity_quote for a in config.allocations}
    if (set(r.market for r in receipts) != set(by_market) or len(receipts) != len(by_market) or
            tuple(r.receipt_fingerprint for r in receipts) != tuple(c.market_receipt_fingerprint for c in temporal.clocks)):
        raise ValueError("missing or substituted market capital contribution")
    contributions = []
    for r in receipts:
        v = validate_native_accounting(r)
        if v.initial_equity_quote != by_market[r.market]:
            raise ValueError("native allocation mismatch")
        contributions.append(MarketEconomicContribution(market=r.market,
            market_receipt_fingerprint=r.receipt_fingerprint, equity_quote=v.equity_quote,
            net_pnl_quote=v.net_pnl_quote, realized_pnl_quote=v.realized_pnl_quote,
            unrealized_pnl_quote=v.unrealized_pnl_quote, fees_quote=v.fees_quote,
            funding_quote=v.funding_quote))
    supported = temporal.classification in {"MODELED_ALIGNED", "FINAL_ONLY"}
    if temporal.classification == "MODELED_ALIGNED":
        if (drawdown_evidence is None or drawdown_evidence.observation_count != temporal.clocks[0].frames or
                drawdown_evidence.native_evidence_fingerprints != tuple(c.native_evidence_fingerprint for c in temporal.clocks)):
            raise ValueError("complete drawdown evidence required for modeled alignment")
    elif drawdown_evidence is not None:
        raise ValueError("drawdown unavailable without complete aligned history")
    with localcontext() as ctx:
        ctx.prec = 80
        total, allocated, reserve = (config.budget.total_equity_quote,
            config.allocated_equity_quote, config.unallocated_reserve_quote)
        if total != allocated + reserve:
            raise ValueError("shared capital reconciliation failed")
        equity = reserve + sum((c.equity_quote for c in contributions), ZERO) if supported else None
        pnl = equity - total if supported else None
        residual = pnl - sum((c.net_pnl_quote for c in contributions), ZERO) if supported else None
        return sealed(PortfolioAccountingReport, config_fingerprint=config.fingerprint(),
            temporal_fingerprint=temporal.evidence_fingerprint, initial_capital_quote=total,
            allocated_capital_quote=allocated, reserve_quote=reserve,
            capital_allocation_utilization=portfolio_ratio(allocated, total), contributions=tuple(contributions),
            equity_quote=equity, pnl_quote=pnl, session_loss_quote=max(ZERO, -pnl) if supported else None,
            native_rounding_residual_quote=residual, drawdown=drawdown_evidence,
            status="SUPPORTED" if supported else "UNAVAILABLE")
