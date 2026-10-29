"""Phase 16.1A immutable recorded/synthetic historical contract regression tests."""
from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from app.research_replay.models import (
    HistoricalBook, HistoricalDataset, HistoricalGap, HistoricalObservation,
    HistoricalPerpContext, HistoricalSource,
)
from app.research_replay.provenance import describe_provenance

T = datetime(2026, 10, 1, tzinfo=timezone.utc)


def sample(*, native=True, gaps=False):
    source = HistoricalSource(market="BTC", source_kind="RECORDED_NATIVE" if native else "SYNTHETIC_FIXTURE",
        provider="HYPERLIQUID" if native else "SYNTHETIC", source_id="recording:btc-v1",
        collection_method="RECORDED_FILE_IMPORT" if native else "SYNTHETIC_GENERATOR",
        use_attestation="USER_ASSERTED_PERMITTED_USE" if native else "SYNTHETIC_LOCAL_ONLY")
    book = HistoricalBook(bids=({"price":"60000","size":"1"},), asks=({"price":"60001","size":"2"},))
    points = (
        HistoricalObservation(market="BTC", sequence=1, kind="L2", received_at=T,
            source_timestamp=T-timedelta(milliseconds=10), source_event_time_verified=native,
            observer_instance_id="session-1", connection_generation=1, order_book=book),
        HistoricalObservation(market="BTC", sequence=2, kind="PERP_CONTEXT", received_at=T+timedelta(seconds=3),
            source_event_time_verified=False, observer_instance_id="session-1", connection_generation=1,
            perp_context=HistoricalPerpContext(mark_price="60000", funding_rate="0.0001")),
    )
    return HistoricalDataset(dataset_id="btc-capture", market="BTC", source=source,
        simulated=not native, observations=points, coverage_start=points[0].received_at,
        coverage_end=points[-1].received_at, gaps=(HistoricalGap(start_at=T+timedelta(seconds=1),
          end_at=T+timedelta(seconds=2),reason="DROPPED"),) if gaps else ())


def test_recorded_and_synthetic_provenance():
    recorded, synthetic = sample(gaps=True), sample(native=False)
    assert recorded.simulated is False and synthetic.simulated is True
    assert recorded.source.source_authenticated is False
    assert recorded.dataset_fingerprint != synthetic.dataset_fingerprint
    p = describe_provenance(recorded)
    assert p.observation_count == 2 and p.l2_count == 1 and p.gap_count == 1
    assert p.authority == "NONE" and p.licensing_independently_verified is False
    assert p.dataset_fingerprint == recorded.dataset_fingerprint
    assert p.source_event_time_policy == "RECORDED_L2_VERIFIED_CONTEXT_RECEIPT_ONLY"
    assert describe_provenance(synthetic).source_event_time_policy == "SYNTHETIC_TIMES_NOT_EXCHANGE_VERIFIED"


def test_deterministic_identity_and_serialization():
    a = sample()
    b = HistoricalDataset.model_validate(a.model_dump(mode="json"))
    assert b.dataset_fingerprint == a.dataset_fingerprint
    assert b.model_dump(mode="json")["observations"][0]["order_book"]["bids"][0]["price"] == "60000"
    mutated = a.model_dump(mode="json")
    mutated["observations"][0]["order_book"]["bids"][0]["size"] = "3"
    with pytest.raises(ValidationError,match="fingerprint"):
        HistoricalDataset.model_validate(mutated)


@pytest.mark.parametrize("change", [
    {"market":"SOL"}, {"simulated":True}, {"coverage_status":"COMPLETE"},
    {"continuous_history_verified":True}, {"read_only":False},
    {"authority":"TRADE"},
])
def test_rejected_dataset_status_changes(change):
    data = sample().model_dump(mode="json")
    data.update(change)
    with pytest.raises(ValidationError): HistoricalDataset.model_validate(data)


def test_rejected_missing_source_time_and_faked_perp_event_time():
    data = sample().model_dump(mode="json")
    data["observations"][0]["source_timestamp"] = None
    with pytest.raises(ValidationError): HistoricalDataset.model_validate(data)
    data = sample().model_dump(mode="json")
    data["observations"][1]["source_event_time_verified"] = True
    with pytest.raises(ValidationError): HistoricalDataset.model_validate(data)


def test_rejected_synthetic_source_promotion_and_unknown_native_l2_is_partial():
    d = sample(native=False).model_dump(mode="json")
    d["source"]["provider"] = "HYPERLIQUID"
    with pytest.raises(ValidationError): HistoricalDataset.model_validate(d)
    d = sample().model_dump(mode="json")
    d["observations"][0]["source_event_time_verified"] = False
    d["observations"][0]["source_timestamp"] = None
    d["dataset_fingerprint"] = None
    partial = HistoricalDataset.model_validate(d)
    assert describe_provenance(partial).source_event_time_policy == "RECORDED_L2_UNVERIFIED_OR_MISSING"
    assert describe_provenance(partial).verified_l2_event_time_count == 0


def test_rejected_out_of_order_and_mixed_market():
    for key,value in [("sequence",0),("market","SOL"),("connection_generation",-1)]:
        d = sample().model_dump(mode="json")
        d["observations"][1][key] = value
        with pytest.raises(ValidationError): HistoricalDataset.model_validate(d)


def test_bad_book_and_gap():
    with pytest.raises(ValidationError):
        HistoricalBook(bids=({"price":"2","size":"1"},),asks=({"price":"2","size":"1"},))
    with pytest.raises(ValidationError):
        HistoricalGap(start_at=T+timedelta(seconds=2),end_at=T+timedelta(seconds=1),reason="DISCONNECT")
    with pytest.raises(ValidationError):
        HistoricalPerpContext()
