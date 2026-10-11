"""Extract existing immutable scenario evidence; never generate another dataset."""
from decimal import Decimal
from app.simulation.models import ResearchMarketAssumptions, stable_fingerprint


def capture_assumptions(dataset, frames, scenario, market_profile=None):
    # Legacy caller-provided nonnative datasets remain valid simulation inputs.
    if dataset.market not in ('BTC', 'ETH', 'SOL') or not scenario or not scenario.replace('_', '').isalpha() or not scenario.isupper():
        return None
    frame = frames[-1]
    book, perp = frame.market.book, frame.perp_context
    bids = tuple({'price': x.price, 'size': x.size} for x in book.bids[:5])
    asks = tuple({'price': x.price, 'size': x.size} for x in book.asks[:5])
    spread = frame.market.best_ask - frame.market.best_bid
    values = dict(contract_version='phase154-v1', market=dataset.market,
        market_profile_version=market_profile.profile_version if market_profile else None,
        market_profile_fingerprint=market_profile.profile_fingerprint if market_profile else None,
        dataset_fingerprint=dataset.fingerprint, scenario=scenario, frame_count=len(frames), simulated=True,
        representative_frame='LAST_CONSUMED_DATASET_FRAME', representative_frame_sequence=frame.sequence,
        representative_frame_timestamp=frame.timestamp, midpoint=frame.market.mid_price,
        best_bid=frame.market.best_bid, best_ask=frame.market.best_ask,
        spread_quote=spread, spread_bps=spread / frame.market.mid_price * Decimal('10000'),
        mark_price=perp.mark_price, oracle_price=perp.oracle_price, funding_rate=perp.funding_rate,
        funding_convention='RAW_RATE_PER_SAMPLED_RESEARCH_INTERVAL', open_interest_base=perp.open_interest_base,
        bid_levels=bids, ask_levels=asks,
        bid_depth_base=sum((x['size'] for x in bids), Decimal(0)),
        ask_depth_base=sum((x['size'] for x in asks), Decimal(0)),
        depth_level_count=min(len(bids), len(asks)), depth_measurement_method='TOP_5_LEVELS_PER_SIDE_BASE',
        reference_source=perp.source,
        limitations=('Last consumed dataset frame only; not a scenario aggregate or historical live replay.',
            'Visible synthetic depth does not establish queue priority or executable fill probability.',
            'Funding is a sampled research rate; accounting interval is separate captured configuration.'))
    return ResearchMarketAssumptions(**values, assumption_fingerprint=stable_fingerprint(values))
