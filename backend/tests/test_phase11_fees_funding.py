from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from test_phase11_accounting import T, fill, service


@pytest.mark.parametrize("side", ["BID", "ASK"])
@pytest.mark.parametrize("liquidity,expected", [("MAKER", ".3"), ("TAKER", ".9"), (None, ".9")])
def test_paper_research_fee_exact_and_booked_once(side, liquidity, expected):
    accounting = service(paper_fee_model_enabled=True)
    event = fill(side, liquidity=liquidity)
    accounting.ingest_fill(event)
    accounting.ingest_fill(event)
    accounting.mark(D("3000"))
    vault = accounting.snapshot()
    assert vault.fees_quote == D(expected)
    assert vault.net_pnl_quote == -D(expected)
    assert vault.equity_quote == D("100000") - D(expected)
    fee = accounting.ledger.entries()[0]
    assert fee.source == "PAPER_CONFIG" and fee.simulated
    assert fee.cash_delta_quote == -D(expected)


def test_disabled_fee_is_explicit_configured_zero_fee_research():
    accounting = service()
    accounting.ingest_fill(fill())
    accounting.mark(D("3000"))
    assert accounting.snapshot().fees_quote == 0
    assert any("zero-fee research" in warning for warning in accounting.snapshot().warnings)


@pytest.mark.parametrize("side,rate,expected", [("BID", ".01", "-30"), ("ASK", ".01", "30"),
                                               ("BID", "-.01", "30"), ("ASK", "-.01", "-30")])
def test_funding_signed_cash_flow_and_interval_identity(side, rate, expected):
    accounting = service(paper_funding_accounting_enabled=True)
    accounting.ingest_fill(fill(side))
    args = dict(effective_at=T, mark=D("3000"), rate=D(rate), evidence_version=7)
    assert accounting.accrue_funding(**args)
    version = accounting.version
    assert not accounting.accrue_funding(**args)
    assert accounting.version == version
    accounting.mark(D("3000"))
    assert accounting.snapshot().funding_quote == D(expected)
    assert accounting.snapshot().equity_quote == D("100000") + D(expected)
    assert accounting.accrue_funding(**{**args, "effective_at": T + timedelta(hours=1)})
    accounting.mark(D("3000"))
    assert accounting.snapshot().funding_quote == D(expected) * 2


def test_flat_position_funding_zero_and_conflicting_interval_rejected():
    accounting = service(paper_funding_accounting_enabled=True)
    accounting.accrue_funding(effective_at=T, mark=D("3000"), rate=D(".01"))
    accounting.mark(D("3000"))
    assert accounting.snapshot().funding_quote == 0
    with pytest.raises(ValueError, match="conflicting accounting event"):
        accounting.accrue_funding(effective_at=T, mark=D("3000"), rate=D(".02"))
    assert accounting.ledger.version == 1


def test_refreshes_do_not_repeatedly_accrue_current_funding_signal():
    accounting = service(paper_funding_accounting_enabled=True)
    accounting.ingest_fill(fill())
    context = SimpleNamespace(updated_at=T, mark_price=D("3000"), funding_rate=D(".01"), version=1)
    accounting.observe_funding(context)
    for second in (5, 10, 59, 1000):
        context.updated_at = T + timedelta(seconds=second)
        accounting.observe_funding(context)
    assert accounting.ledger.version == 2
    context.updated_at = T + timedelta(hours=1)
    accounting.observe_funding(context)
    assert accounting.ledger.version == 3
    accounting.observe_funding(context)
    assert accounting.ledger.version == 3


def test_funding_gap_and_non_boundary_fail_without_interpolation():
    accounting = service(paper_funding_accounting_enabled=True)
    with pytest.raises(ValueError, match="explicit interval boundary"):
        accounting.accrue_funding(effective_at=T + timedelta(seconds=1), mark=D("3000"), rate=D(".01"))
    accounting = service(paper_funding_accounting_enabled=True)
    context = SimpleNamespace(updated_at=T, mark_price=D("3000"), funding_rate=D(".01"), version=1)
    accounting.observe_funding(context)
    context.updated_at += timedelta(hours=2)
    with pytest.raises(ValueError, match="interval gap"):
        accounting.observe_funding(context)
    assert accounting.ledger.version == 0
