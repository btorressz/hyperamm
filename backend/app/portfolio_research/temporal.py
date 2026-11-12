"""Defined hypothetical clocks, never inferred real exchange synchronization."""
from datetime import timedelta

from app.simulation.scenarios import DEFAULT_START
from .models import MarketObservationClock, PortfolioTemporalReport, sealed


def observation_clocks(receipts, evidence):
    if tuple(e.market for e in evidence) != tuple(r.market for r in receipts):
        raise ValueError("native timeline market set or order mismatch")
    clocks = []
    for r, e in zip(receipts, evidence):
        e = type(e).model_validate(e)
        if e.market_receipt_fingerprint != r.receipt_fingerprint:
            raise ValueError("native timeline substituted receipt")
        n = r.metrics.frame_count
        simulation = r.provenance.captured.inputs().simulation
        expected = min(n, simulation.trace_max_points) if simulation.record_trace else 0
        points = e.observations
        # The existing scenario generator uses sequences 1..n, DEFAULT_START,
        # one-second intervals, no resets. Validate that exact contract, including
        # retained suffixes. Equal terminal timestamps alone are insufficient.
        valid = (len(points) == expected and all(
            p.sequence == n - len(points) + i + 1 and
            p.timestamp == DEFAULT_START + timedelta(seconds=p.sequence - 1)
            for i, p in enumerate(points)))
        end = r.market_assumptions.representative_frame_timestamp
        valid = valid and end == DEFAULT_START + timedelta(seconds=n - 1)
        clocks.append(sealed(MarketObservationClock, market=r.market,
            market_receipt_fingerprint=r.receipt_fingerprint,
            native_evidence_fingerprint=e.evidence_fingerprint,
            scenario=r.provenance.requested_scenario, engine_version=r.provenance.engine_version, frames=n,
            expected_retained=expected, retained=len(points), start_at=DEFAULT_START,
            final_at=end, complete=valid and len(points) == n, valid=valid))
    return tuple(clocks)


def classify_clocks(clocks):
    clocks = tuple(MarketObservationClock.model_validate(c) for c in clocks)
    if not clocks or len({c.market for c in clocks}) != len(clocks):
        raise ValueError("unique selected market clocks required")
    if any(not c.valid for c in clocks):
        classification, reason = "UNAVAILABLE", "MISSING_OR_INVALID_NATIVE_TIMELINE"
    elif len({(c.clock, c.engine_version, c.scenario, c.frames, c.start_at, c.final_at) for c in clocks}) != 1:
        classification, reason = "INCOMPARABLE", "ENGINE_SCENARIO_OR_OBSERVATION_WINDOW_MISMATCH"
    elif all(c.complete for c in clocks):
        classification, reason = "MODELED_ALIGNED", "COMPLETE_COMMON_HYPOTHETICAL_SCENARIO_CLOCK"
    else:
        classification, reason = "FINAL_ONLY", "INDEPENDENT_ENDPOINTS_ONLY_RETAINED_HISTORY_INCOMPLETE"
    return sealed(PortfolioTemporalReport, classification=classification,
                  clocks=clocks, reasons=(reason,))


def evaluate_temporal(receipts, evidence):
    return classify_clocks(observation_clocks(receipts, evidence))
