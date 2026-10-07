from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.terminal.history import TerminalHistory
from app.terminal.models import TerminalHistoryPoint

T = datetime(2026, 10, 6, tzinfo=timezone.utc)


def point(sequence, seconds=0):
    return TerminalHistoryPoint(
        sequence=sequence,
        timestamp=T + timedelta(seconds=seconds),
        mid_price=Decimal("3000.123"),
        risk_state="NORMAL",
        simulated=True,
        execution_mode="PAPER",
    )


def test_bounded_eviction_and_chronological_decimation():
    h = TerminalHistory(4)
    for i in range(7):
        h.append(point(i + 1, i))
    assert [p.sequence for p in h.query()] == [4, 5, 6, 7]
    assert [p.sequence for p in h.query(limit=2)] == [4, 7]
    assert h.metadata()["retained_points"] == 4
    assert h.query(limit=1)[0].sequence == 7


def test_range_queries_are_relative_to_observations_and_preserve_span():
    h = TerminalHistory()
    for i in range(400):
        h.append(point(i + 1, i))
    assert len(h.query(range="1m")) == 61
    assert h.query(range="5m")[0].sequence == 100
    assert h.metadata()["available_ranges"] == ["1m", "5m", "session"]
    assert h.query(limit=5)[-1].timestamp == T + timedelta(seconds=399)


@pytest.mark.parametrize("limit", [0, -1, 1001])
def test_query_limit_rejected(limit):
    with pytest.raises(ValueError):
        TerminalHistory().query(limit=limit)


@pytest.mark.parametrize("range", ["4h", "1d", "24h", "bogus"])
def test_unsupported_range_rejected(range):
    with pytest.raises(ValueError):
        TerminalHistory().query(range=range)


def test_same_timestamp_is_ordered_by_sequence_and_bad_order_is_rejected():
    h = TerminalHistory()
    h.append(point(1))
    h.append(point(2))
    assert [p.sequence for p in h.query()] == [1, 2]
    with pytest.raises(ValueError):
        h.append(point(2, 1))
    with pytest.raises(ValueError):
        h.append(point(3, -1))
    h.clear()
    assert h.query() == []


@pytest.mark.parametrize("size", [0, 3601])
def test_invalid_storage_size_rejected(size):
    with pytest.raises(ValueError):
        TerminalHistory(size)


def test_history_decimal_and_timezone_contract():
    assert point(1).model_dump(mode="json")["mid_price"] == "3000.123"
    with pytest.raises(ValidationError):
        point(1).model_validate(
            {**point(1).model_dump(), "timestamp": T.replace(tzinfo=None)}
        )
