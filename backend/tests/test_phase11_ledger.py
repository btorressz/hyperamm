from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from app.accounting.models import fingerprint
from test_phase11_accounting import T, fill, service


def test_fill_replay_deduplicates_trade_and_fee():
    accounting = service(paper_fee_model_enabled=True)
    event = fill()
    assert accounting.ingest_fill(event)
    accounting.mark(D("3000"))
    accounting.reserve()
    before = accounting.snapshot()
    assert not accounting.ingest_fill(event.model_copy(deep=True))
    assert accounting.snapshot() == before
    assert accounting.ledger.version == 2


@pytest.mark.parametrize("update", [{"price": D("3100")}, {"size": D("2")}, {"side": "ASK"}, {"liquidity": "MAKER"}])
def test_same_identity_changed_economics_fails_atomically(update):
    accounting = service(paper_fee_model_enabled=True)
    event = fill()
    accounting.ingest_fill(event)
    before = accounting.ledger.entries()
    with pytest.raises(ValueError, match="conflicting fill replay"):
        accounting.ingest_fill(event.model_copy(update=update))
    assert accounting.ledger.entries() == before
    assert accounting.position.position_base == 1
    assert accounting.error


def test_ledger_chain_sequence_and_replay_are_deterministic():
    services = [service(), service()]
    for accounting in services:
        for index, event in enumerate([fill(), fill("ASK", "3100", identity="b", seconds=1)]):
            accounting.ingest_fill(event)
        accounting.mark(D("3100"))
    a, b = services
    assert a.ledger.entries() == b.ledger.entries()
    assert a.snapshot() == b.snapshot()
    previous = a.ledger.genesis_fingerprint
    for entry in reversed(a.ledger.entries()):
        assert entry.previous_ledger_fingerprint == previous
        payload = entry.model_dump(exclude={"ledger_fingerprint"})
        assert fingerprint(payload) == entry.ledger_fingerprint
        previous = entry.ledger_fingerprint
    assert [entry.sequence for entry in a.ledger.entries()] == [4, 3, 2, 1]
    assert previous == a.ledger.fingerprint


def test_entries_and_events_are_immutable():
    accounting = service()
    accounting.ingest_fill(fill())
    entry = accounting.ledger.entries()[0]
    with pytest.raises(ValidationError):
        entry.cash_balance_quote = D("1")
    with pytest.raises(TypeError):
        accounting.ledger.entries()[0] = entry
    with pytest.raises(ValidationError):
        accounting.events()[0].message = "mutated"


def test_capacity_failure_never_prunes_or_partially_books_fee():
    accounting = service(ledger_max_entries=3, event_max_entries=2)
    accounting.ingest_fill(fill())
    before = accounting.ledger.entries()
    with pytest.raises(ValueError, match="retention capacity"):
        accounting.ingest_fill(fill(identity="b", seconds=1))
    assert accounting.ledger.version == 2
    assert accounting.ledger.entries() == before
    assert accounting.position.position_base == D("1")
    assert len(accounting.events()) <= 2
    assert accounting.ledger.retention_policy == "HALT_WHEN_FULL"


def test_naive_timestamps_and_out_of_order_fills_fail():
    accounting = service()
    with pytest.raises(ValueError, match="timezone-aware"):
        accounting.ingest_fill(fill().model_copy(update={"timestamp": T.replace(tzinfo=None)}))
    accounting = service()
    accounting.ingest_fill(fill(seconds=2))
    with pytest.raises(ValueError, match="out-of-order"):
        accounting.ingest_fill(fill(identity="b", seconds=1))


def test_genesis_does_not_depend_on_wall_clock_and_config_is_bound():
    assert service().ledger.genesis_fingerprint == service().ledger.genesis_fingerprint
    assert service().ledger.genesis_fingerprint != service(paper_taker_fee_bps=D("4")).ledger.genesis_fingerprint
