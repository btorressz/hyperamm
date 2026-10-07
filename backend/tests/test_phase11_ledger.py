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


def test_failed_realization_cannot_change_peak_position_or_balances():
    accounting = service(ledger_max_entries=3, paper_fee_model_enabled=True)
    accounting.ingest_fill(fill())
    accounting.mark(D("3100"))
    before = accounting.snapshot()
    with pytest.raises(ValueError, match="retention capacity"):
        accounting.ingest_fill(fill("ASK", "3200", identity="b", seconds=1))
    after = accounting.snapshot()
    for field in ("position_base", "settled_capital_quote", "fees_quote", "peak_equity_quote", "equity_quote", "ledger_fingerprint"):
        assert getattr(after, field) == getattr(before, field)


def test_consistency_uses_ledger_trade_economics_not_private_input_cache():
    accounting = service()
    event = fill()
    accounting.mark(D("3000"))
    accounting._fill_inputs[accounting.fill_identity(event)] = "fake cursor evidence"
    before = accounting.snapshot()
    state = accounting.observe_execution_fills([event])
    assert state.status == "DIVERGED" and state.unaccounted_fill_count == 1
    after = accounting.snapshot()
    assert after.accounting_complete == "UNAVAILABLE"
    assert after.accounting_version > before.accounting_version
    assert after.accounting_fingerprint != before.accounting_fingerprint
    accounting.observe_execution_fills([event])
    assert accounting.snapshot() == after


@pytest.mark.parametrize("update", [{"price": D("3100")}, {"size": D("2")}, {"liquidity": "MAKER"}])
def test_equal_fill_counts_with_conflicting_economics_diverge(update):
    accounting = service(paper_fee_model_enabled=True)
    event = fill()
    accounting.ingest_fill(event)
    accounting.mark(D("3000"))
    state = accounting.observe_execution_fills([event.model_copy(update=update)])
    assert state.execution_fill_count == 1 and state.accounted_fill_count == 0
    assert state.unaccounted_fill_count == 1 and state.status == "DIVERGED"
    assert "conflicting" in state.reason
    assert accounting.error and accounting.snapshot().accounting_complete == "UNAVAILABLE"


def test_fee_funding_rows_do_not_count_as_fills_and_duplicate_execution_is_detected():
    accounting = service(paper_funding_accounting_enabled=True)
    event = fill()
    accounting.ingest_fill(event)
    accounting.mark(D("3000"))
    accounting.accrue_funding(effective_at=T, mark=D("3000"), rate=D("-.01"))
    state = accounting.observe_execution_fills([event])
    assert accounting.ledger.version == 3
    assert state.execution_fill_count == state.accounted_fill_count == 1
    assert state.unaccounted_fill_count == 0 and state.status == "CONSISTENT"
    state = accounting.observe_execution_fills([event, event])
    assert state.status == "DIVERGED" and state.unaccounted_fill_count == 1


def test_reconciliation_uses_all_ledger_rows_beyond_public_page_limit():
    accounting = service()
    fills = [fill(identity=str(n), seconds=n) for n in range(251)]
    for event in fills:
        accounting.ingest_fill(event)
    state = accounting.observe_execution_fills(fills)
    assert state.status == "CONSISTENT" and state.accounted_fill_count == 251
    assert accounting.ledger.version == 502


@pytest.mark.parametrize("newer_evidence", ["mark", "funding"])
def test_pending_replay_before_newer_evidence_is_nonrecoverable(newer_evidence):
    from datetime import timedelta
    accounting = service(paper_funding_accounting_enabled=True)
    if newer_evidence == "mark":
        accounting.mark(D("3000"), observed_at=T + timedelta(seconds=1))
    else:
        accounting.accrue_funding(effective_at=T + timedelta(hours=1), mark=D("3000"), rate=D("0"))
    before = accounting.ledger.entries()
    state = accounting.reconcile_paper_fills([fill()])
    assert state.status == "DIVERGED" and state.unaccounted_fill_count == 1
    assert "irreversible" in accounting.error
    assert accounting.ledger.entries() == before
    accounting.reconcile_paper_fills([fill()])
    assert accounting.ledger.entries() == before


def test_pending_replay_config_mismatch_latches_without_booking():
    accounting = service()
    accounting.config = accounting.config.model_copy(update={"paper_fee_model_enabled": True})
    state = accounting.reconcile_paper_fills([fill()])
    assert state.status == "DIVERGED" and state.unaccounted_fill_count == 1
    assert "configuration mismatch" in accounting.error
    assert accounting.ledger.version == 0 and accounting.position.position_base == 0
    accounting.reconcile_paper_fills([fill()])
    assert accounting.ledger.version == 0
