"""Receipt-order adapter to existing SimulationFrame, never a second engine."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from itertools import groupby

from app.market_data.models import (
    MarketConnectionState, MarketDataMode, MarketLevel, MarketSnapshot, OrderBookSnapshot,
)
from app.market_data.perp_context import PerpMarketContext
from app.simulation.models import SimulationFrame, SimulationReferencePrices, stable_fingerprint
from app.simulation.replay import build_dataset
from .contracts import (
    MAX_SEGMENTS, HistoricalReplayRequest, ReplayFrameEvidence, ReplayIssue,
    ReplayRejected, ReplayRejection,
)


@dataclass(frozen=True)
class ReplaySegment:
    reset_reason: str
    frames: tuple[SimulationFrame, ...]
    evidence: tuple[ReplayFrameEvidence, ...]


def reject(request, issues):
    raise ReplayRejected(ReplayRejection(request_fingerprint=stable_fingerprint(request),
        dataset_fingerprint=request.dataset_fingerprint, issues=tuple(issues)))


def simulation_frame(book_point, context_point, *, timestamp, sequence):
    """Only arithmetic derivations; original observations remain in the receipt."""
    book, context = book_point.order_book, context_point.perp_context
    bid, ask = book.bids[0].price, book.asks[0].price
    mid = (bid + ask) / Decimal(2)
    mark, oracle, oi = context.mark_price, context.oracle_price, context.open_interest_base
    snapshot = MarketSnapshot(market=book_point.market, best_bid=bid, best_ask=ask,
        mid_price=mid, book=OrderBookSnapshot(market=book_point.market,
            bids=[MarketLevel(**x.model_dump()) for x in book.bids],
            asks=[MarketLevel(**x.model_dump()) for x in book.asks],
            timestamp=timestamp, sequence=sequence), latest_valid_update=timestamp,
        connection_state=MarketConnectionState.CONNECTED, mode=MarketDataMode.DEMO,
        simulated=True, stale=False, message="Historical evidence evaluated on a PAPER receipt clock")
    perp = PerpMarketContext(market=book_point.market, market_mid=mid,
        mark_price=mark, oracle_price=oracle, funding_rate=context.funding_rate,
        open_interest_base=oi, open_interest_notional=oi * mark,
        mark_oracle_basis_bps=(mark - oracle) / oracle * 10000,
        mark_mid_basis_bps=(mark - mid) / mid * 10000,
        oracle_mid_basis_bps=(oracle - mid) / mid * 10000,
        updated_at=timestamp, version=context_point.sequence, source="DEMO", simulated=True)
    return SimulationFrame(sequence=sequence, timestamp=timestamp, market=snapshot,
        perp_context=perp, reference_prices=SimulationReferencePrices())


def prepare_replay(dataset, request: HistoricalReplayRequest):
    if (dataset.dataset_id != request.dataset_id or dataset.market != request.market or
            dataset.dataset_fingerprint != request.dataset_fingerprint):
        reject(request, [ReplayIssue(code="IDENTITY_MISMATCH")])
    points = tuple(p for p in dataset.observations
        if (request.start_at is None or p.received_at >= request.start_at)
        and (request.end_at is None or p.received_at <= request.end_at))
    segments, issues = [], []
    frames, evidence = [], []
    book = context = previous = None
    reset_reason = "WINDOW_START"
    age = timedelta(milliseconds=request.policy.max_component_age_ms)
    interval = timedelta(milliseconds=request.policy.max_frame_interval_ms)

    def flush():
        if len(frames) >= 2:
            segments.append(ReplaySegment(reset_reason, tuple(frames), tuple(evidence)))
        elif frames:
            issues.append(ReplayIssue(code="SHORT_SEGMENT", frame_count=len(frames),
                sequence=frames[0].sequence, received_at=frames[0].timestamp))
        frames.clear()
        evidence.clear()

    # Admitted receipt order already has strictly increasing sequence numbers.
    # Finish each equal-time batch in sequence order; emit at most one frame.
    key = lambda p: (p.received_at, p.observer_instance_id, p.connection_generation)
    for (timestamp, observer, generation), batch_iter in groupby(points, key=key):
        batch = tuple(batch_iter)
        barrier = None
        if previous is not None:
            if (previous.observer_instance_id, previous.connection_generation) != (observer, generation):
                barrier = "OBSERVER_CHANGE"
            elif any(previous.received_at <= g.start_at < g.end_at <= timestamp for g in dataset.gaps):
                barrier = "DECLARED_GAP"
            elif timestamp - previous.received_at > interval:
                barrier = "RECEIPT_INTERVAL"
        if barrier:
            flush()
            book = context = None
            reset_reason = barrier
        for point in batch:
            if point.kind == "L2":
                book = point
            else:
                # A partial new context replaces the old context in its entirety.
                context = point
        missing = []
        if book is None:
            missing.append("order_book")
        elif any(level.size <= 0 for level in (*book.order_book.bids, *book.order_book.asks)):
            missing.append("positive_l2_sizes")
        if context is None:
            missing.append("perp_context")
        else:
            missing.extend(field for field in ("mark_price", "oracle_price", "funding_rate", "open_interest_base")
                           if getattr(context.perp_context, field) is None)
        stale = any(timestamp - p.received_at > age for p in (book, context) if p is not None)
        if missing or stale:
            issues.append(ReplayIssue(code="INCOMPLETE_FRAME" if missing else "COMPONENT_TOO_OLD",
                sequence=batch[-1].sequence, received_at=timestamp, missing_fields=tuple(missing)))
            # No order, funding, telemetry or history may bridge unavailable frames.
            flush()
            reset_reason = "UNAVAILABLE_FRAME"
        else:
            frames.append(simulation_frame(book, context, timestamp=timestamp, sequence=batch[-1].sequence))
            evidence.append(ReplayFrameEvidence(sequence=batch[-1].sequence, evaluated_at=timestamp,
                receipt_batch_sequences=tuple(p.sequence for p in batch), book_observation=book,
                context_observation=context, economics=("SYNTHETIC_FIXTURE_VALUES" if dataset.simulated else "RECORDED_VALUES")))
        previous = batch[-1]
    flush()
    count = sum(len(segment.frames) for segment in segments)
    if not count:
        reject(request, [*issues, ReplayIssue(code="NO_VIABLE_FRAMES", frame_count=0)])
    if count > request.max_frames:
        reject(request, [*issues, ReplayIssue(code="FRAME_LIMIT", frame_count=count)])
    if len(segments) > MAX_SEGMENTS:
        reject(request, [*issues, ReplayIssue(code="SEGMENT_LIMIT", frame_count=count)])
    return tuple(segments), tuple(issues), len(points)


def segment_dataset(segment, request):
    # Existing replay.py owns construction and SimulationDataset validation.
    return build_dataset(market=request.market, frames=list(segment.frames),
        source=f"historical:{request.dataset_fingerprint}:{stable_fingerprint(request.policy)}")
