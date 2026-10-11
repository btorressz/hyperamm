"""Pure calculations over validated captured evidence. No service/network ownership."""
from datetime import datetime, timezone
from decimal import Decimal
from .models import ObservedMarketEvidence, ComparisonMetric, MarketResearchComparisonResult
from .explainability import explain, LIMITATIONS
from .provenance import provenance


def capture_observed(snapshot):
    s, b, p = snapshot.status, snapshot.order_book, snapshot.perp_context
    connected = s.connection_state in ('BOOTSTRAPPING', 'CONNECTED', 'DEGRADED', 'STALE')
    metadata = connected and snapshot.metadata.metadata_status == 'EXCHANGE_VERIFIED' and s.metadata_freshness == 'FRESH'
    book = bool(metadata and b and s.l2_freshness == 'FRESH')
    context = bool(metadata and p and s.perp_freshness == 'FRESH')
    levels = min(5, len(b.bids), len(b.asks)) if b else 0
    return ObservedMarketEvidence(snapshot=snapshot,
        acquisition_gap_seconds=abs((b.observed_at-p.observed_at).total_seconds()) if b and p else None,
        bid_depth_base=sum((x.size for x in b.bids[:5]), Decimal(0)) if b else None,
        ask_depth_base=sum((x.size for x in b.asks[:5]), Decimal(0)) if b else None,
        depth_level_count=levels, book_eligible=book, context_eligible=context)


def compare(request, snapshot, *, generated_at=None):
    if snapshot.market != request.market:
        raise ValueError('observer market mismatch')
    observed = capture_observed(snapshot)
    a = request.research.assumptions
    b, p = snapshot.order_book, snapshot.perp_context
    mismatch = request.market != request.research.research_market
    values = (
        ('midpoint', b.midpoint if b else None, 'quote/base', observed.book_eligible, 'PRICE'),
        ('best_bid', b.best_bid if b else None, 'quote/base', observed.book_eligible, 'PRICE'),
        ('best_ask', b.best_ask if b else None, 'quote/base', observed.book_eligible, 'PRICE'),
        ('mark_price', p.mark_price if p else None, 'quote/base', observed.context_eligible, 'PRICE'),
        ('oracle_price', p.oracle_price if p else None, 'quote/base', observed.context_eligible, 'PRICE'),
        ('spread_quote', b.spread if b else None, 'quote', observed.book_eligible, 'SPREAD'),
        ('spread_bps', b.spread_bps if b else None, 'bps', observed.book_eligible, 'SPREAD_BPS'),
        ('funding_rate', p.funding_rate if p else None, 'raw rate', observed.context_eligible, 'FUNDING'),
        ('bid_depth_base', observed.bid_depth_base, 'base', observed.book_eligible, 'DEPTH'),
        ('ask_depth_base', observed.ask_depth_base, 'base', observed.book_eligible, 'DEPTH'),
        ('open_interest_base', p.open_interest_base if p else None, 'base', observed.context_eligible, 'OI'),
    )
    metrics = []
    for name, live, unit, eligible, kind in values:
        research = getattr(a, name, None) if a else None
        status, reason = 'COMPARABLE', 'Captured observed minus last hypothetical frame; different economic contexts.'
        if mismatch:
            status, reason = 'NOT_COMPARABLE', 'Observed and research markets differ; no cross-asset delta.'
        elif a is None:
            status, reason = 'UNAVAILABLE', 'Research assumption detail unavailable for this prior result'
        elif live is None or research is None:
            status, reason = 'UNAVAILABLE', 'Source does not contain the required captured evidence.'
        elif not eligible:
            status, reason = 'UNAVAILABLE', 'Required component or metadata is stale, disconnected or unavailable; retained values are historical.'
        elif kind == 'DEPTH' and (observed.depth_level_count != 5 or a.depth_level_count != 5 or len({x.price for x in a.bid_levels}) != 5 or len({x.price for x in a.ask_levels}) != 5):
            status, reason = 'NOT_COMPARABLE', 'Top five valid levels per side in matching base units are required.'
        elif kind == 'FUNDING':
            status, reason = 'PARTIAL', 'Raw rate subtraction only: native hourly rate vs sampled research interval; not comparable settled payments.'
        elif kind == 'OI':
            status, reason = 'PARTIAL', 'Native reported base OI vs actual modeled frame OI; descriptive synthetic assumption only.'
        delta = live - research if status in ('COMPARABLE', 'PARTIAL') else None
        difference_bps = (delta / research * Decimal('10000') if delta is not None and kind == 'PRICE'
                          else delta if delta is not None and kind == 'SPREAD_BPS' else None)
        metrics.append(ComparisonMetric(metric_name=name, observed_value=live, research_assumed_value=research,
            absolute_difference=delta, difference_bps=difference_bps, unit=unit, comparison_status=status, reason=reason))
    metrics = tuple(metrics)
    explainability = explain(metrics)
    status = ('NOT_COMPARABLE' if mismatch else 'UNAVAILABLE' if not explainability.available_metrics else
              'PARTIAL' if explainability.missing_metrics or any(x.comparison_status == 'PARTIAL' for x in metrics) else 'COMPARABLE')
    extra = () if request.research.research_configuration else ('Research accounting configuration provenance unavailable for this legacy result; no preset inferred.',)
    return MarketResearchComparisonResult(market=request.market, generated_at=generated_at or datetime.now(timezone.utc),
        comparison_status=status, research=request.research, observed=observed, metrics=metrics,
        explainability=explainability, provenance=provenance(request, observed, metrics),
        limitations=LIMITATIONS + extra + snapshot.limitations + (a.limitations if a else ()))
