from datetime import timedelta
from decimal import Decimal as D

import pytest

from app.accounting import AccountingConfig, AccountingService
from app.config import Settings
from app.execution.models import OrderRequest
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.perp_context import PerpPositionContext
from app.risk.firewall import RiskState
from app.runtime import HyperAmmRuntime
from app.strategy.models import ExecutionMode
from test_phase11_accounting import T, fill


async def runtime(**config):
    rt = HyperAmmRuntime(Settings(_env_file=None))
    rt.accounting_config = AccountingConfig(**config)
    rt.accounting_service = AccountingService("ETH", config=rt.accounting_config)
    snapshot = MockMarketDataAdapter().snapshot_for(2)
    await rt.market._accept(snapshot)
    await rt.refresh_once()
    return rt, snapshot


@pytest.mark.asyncio
async def test_fill_callback_books_telemetry_and_accounting_and_wakes_same_loop():
    rt, snap = await runtime()
    rt._strategy_wakeup.clear()
    await rt.paper.submit_orders([OrderRequest(client_order_id="cross", market="ETH", side="BID",
                                               price=snap.best_ask, size=D(".1"))])
    assert rt.accounting_service.ledger.version == 2
    assert rt.agent_telemetry.summary()["fill_observations"] == 1
    assert rt._strategy_wakeup.is_set()
    assert rt.accounting_service.position.position_base == D(".1")


@pytest.mark.asyncio
async def test_accounting_version_and_fingerprint_are_final_authority_bound():
    rt, _ = await runtime()
    rt.strategy.running = True
    original = rt.authorization
    assert original.accounting_version == rt.accounting_service.version
    assert original.accounting_fingerprint == rt.accounting_service.fingerprint
    rt.accounting_service.reserve()
    with pytest.raises(RuntimeError, match="accounting changed after quote authorization"):
        await rt._execution_authority()
    await rt.refresh_once()
    assert rt.authorization.authorized
    await rt._execution_authority()
    assert rt.authorization.accounting_version > original.accounting_version
    assert rt.authorization.authorization_fingerprint != original.authorization_fingerprint


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["CREATE", "REPLACE"])
async def test_order_manager_rejects_stale_accounting_before_submit(action, monkeypatch):
    rt, _ = await runtime()
    rt.strategy.running = True
    if action == "REPLACE":
        q = rt.quotes[0]
        await rt.paper.submit_orders([OrderRequest(client_order_id="old", market="ETH", side=q.side,
                  price=q.price * D(".99") if q.side == "BID" else q.price * D("1.01"), size=q.size, level_index=q.level_index)])
    rt.accounting_service.reserve()
    submissions = []
    original = rt.paper.submit_orders
    async def submit(orders):
        submissions.extend(orders)
        return await original(orders)
    monkeypatch.setattr(rt.paper, "submit_orders", submit)
    with pytest.raises(RuntimeError, match="accounting changed"):
        await rt.orders.reconcile("ETH", rt.quotes, D("0"), D("0"))
    assert submissions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["STALE", "ERROR", "UNKNOWN"])
async def test_accounting_failure_blocks_create_but_cancel_remains_possible(failure):
    rt, snap = await runtime()
    rt.strategy.running = True
    await rt.paper.submit_orders([OrderRequest(client_order_id="rest", market="ETH", side="BID",
                                               price=snap.best_bid - D("100"), size=D(".1"), level_index=0)])
    if failure == "STALE":
        rt.accounting_service.clock = lambda: snap.latest_valid_update + timedelta(seconds=60)
    elif failure == "ERROR":
        rt.accounting_service.fail("fixture accounting error")
    else:
        rt.accounting_service._updated_at = None
    with pytest.raises(RuntimeError, match="accounting stale, error or unavailable"):
        await rt._execution_authority()
    await rt.orders.reconcile("ETH", [], D("0"), D("0"))
    assert not await rt.paper.get_open_orders()
    assert not rt.risk.kill_switch_active


@pytest.mark.asyncio
async def test_capital_insufficiency_is_phase8_input_and_cancels_existing():
    rt, snap = await runtime(paper_initial_equity_quote=D("1"))
    assert rt.risk_decision.state == RiskState.HALT
    assert not rt.authorization.authorized and rt.quotes == []
    assert "SIMULATED CAPITAL RESERVATION" in "; ".join(rt.risk_decision.reasons)
    await rt.paper.submit_orders([OrderRequest(client_order_id="rest", market="ETH", side="BID",
                                               price=snap.best_bid - D("100"), size=D(".1"), level_index=0)])
    rt.strategy.running = True
    await rt.refresh_once()
    assert not await rt.paper.get_open_orders()
    assert rt.accounting_service.snapshot().reserved_capital_quote == 0


@pytest.mark.asyncio
async def test_phase8_drawdown_and_session_loss_come_from_shared_accounting():
    rt, snap = await runtime(paper_initial_equity_quote=D("1000"))
    # A settled losing round trip; account mark/market stay unchanged.
    expected_peak = D("1000") + max(D("0"), rt.accounting_service.position.mark_price - D("3000"))
    rt.accounting_service.ingest_fill(fill(price="3000"))
    rt.accounting_service.ingest_fill(fill("ASK", "2800", identity="b", seconds=1))
    await rt.refresh_once()
    assert rt.risk_decision.state == RiskState.HALT
    evidence = rt.risk_decision.pnl_drawdown
    assert evidence.current_equity == D("800")
    assert evidence.peak_equity == expected_peak
    assert evidence.session_pnl == D("-200")
    assert evidence.drawdown_pct == (expected_peak - D("800")) / expected_peak
    assert "critical drawdown" in rt.risk_decision.reasons


@pytest.mark.asyncio
async def test_repeated_economic_refresh_does_not_churn_accounting_authority():
    rt, _ = await runtime()
    before = rt.accounting_service.snapshot()
    await rt.refresh_once()
    after = rt.accounting_service.snapshot()
    assert after.accounting_version == before.accounting_version
    assert after.accounting_fingerprint == before.accounting_fingerprint


@pytest.mark.asyncio
async def test_perp_feed_updates_vault_while_strategy_is_stopped():
    rt, snap = await runtime()
    before = rt.accounting_service.snapshot()
    context = rt.perp_context_service._context.model_copy(update={
        "mark_price": before.mark_price + D("1"),
        "updated_at": rt.perp_context_service._context.updated_at + timedelta(microseconds=1),
    })
    await rt._on_perp_context(context)
    assert rt.accounting_service.snapshot().mark_price == context.mark_price
    assert rt.accounting_service.version > before.accounting_version
    assert not rt.strategy.running


@pytest.mark.asyncio
async def test_testnet_equity_change_at_same_position_version_blocks_transmission(monkeypatch):
    rt, snap = await runtime()
    rt.config = rt.config.model_copy(update={"execution_mode": ExecutionMode.TESTNET})
    rt.accounting_service = AccountingService("ETH", mode="TESTNET", config=rt.accounting_config)
    rt.execution = rt.testnet
    rt.orders.execution = rt.testnet
    rt.testnet._positions = {"ETH": D("0")}
    rt.testnet._position_updated_at = snap.latest_valid_update
    rt.testnet._perp_position = PerpPositionContext(market="ETH", signed_position_base=D("0"),
                     source="TESTNET", updated_at=snap.latest_valid_update, version=0)
    rt.testnet._account_value = D("100000")
    rt.testnet._total_margin_used = D("0")
    from types import SimpleNamespace
    info=SimpleNamespace(name_to_asset=lambda market:0, asset_to_sz_decimals={0:4})
    monkeypatch.setattr(rt.testnet, "_exchange_client", lambda:SimpleNamespace(info=info))
    monkeypatch.setattr(rt.testnet, "_require_enabled", lambda: None)
    async def reconcile(): pass
    async def refresh(market): return D("0")
    monkeypatch.setattr(rt.testnet, "reconcile_venue", reconcile)
    monkeypatch.setattr(rt.testnet, "refresh_position", refresh)
    await rt.refresh_once()
    assert rt.authorization.authorized
    rt.strategy.running = True
    await rt._execution_authority()
    rt.testnet._account_value = D("90000")
    with pytest.raises(RuntimeError, match="accounting changed after quote authorization"):
        await rt._execution_authority()


@pytest.mark.asyncio
async def test_cancel_all_untracked_orders_remains_possible_with_accounting_error():
    rt, snap = await runtime()
    await rt.paper.submit_orders([OrderRequest(client_order_id="untracked", market="ETH", side="BID",
                                                price=snap.best_bid - D("100"), size=D(".1"))])
    rt.accounting_service.fail("fixture error")
    await rt.orders.cancel_all()
    assert not await rt.paper.get_open_orders()


@pytest.mark.asyncio
async def test_disabled_accounting_does_not_misreport_confirmed_cancellation():
    rt, snap = await runtime()
    await rt.paper.submit_orders([OrderRequest(client_order_id="untracked", market="ETH", side="BID",
                                                price=snap.best_bid - D("100"), size=D(".1"))])
    rt.accounting_config = AccountingConfig(enabled=False)
    rt.accounting_service.config = rt.accounting_config
    await rt.stop_strategy()
    assert not await rt.paper.get_open_orders()
    assert not rt.risk.kill_switch_active
    assert "cancellation unconfirmed" not in rt.strategy.last_error


@pytest.mark.asyncio
async def test_paper_testnet_and_market_transitions_rebind_under_execution_lock():
    rt, snap = await runtime()
    await rt.paper.submit_orders([OrderRequest(client_order_id="cross", market="ETH", side="BID",
                                               price=snap.best_ask, size=D(".1"))])
    assert rt.accounting_service.ledger.version > 0
    paper_genesis = rt.accounting_service.ledger.genesis_fingerprint
    config = rt.config.model_copy(update={"execution_mode": ExecutionMode.TESTNET})
    await rt.update_config(config)
    assert rt.accounting_service.mode == "TESTNET"
    assert rt.accounting_service.ledger.version == 0
    assert rt.accounting_service.snapshot().equity_quote is None
    assert rt.accounting_service.ledger.genesis_fingerprint != paper_genesis
    await rt.update_config(config.model_copy(update={"execution_mode": ExecutionMode.PAPER}))
    assert rt.paper.fills.all() == []
    assert rt.accounting_service.position.position_base == 0
    # Avoid starting services during this focused configuration test.
    async def no_start(): pass
    rt.market.start = no_start
    rt.reference_service.start = no_start
    await rt.update_config(rt.config.model_copy(update={"market": "BTC"}))
    assert rt.accounting_service.market == "BTC"
    assert rt.accounting_service.ledger.version == 0
    await rt.market.stop()
    await rt.reference_service.stop()


@pytest.mark.parametrize("with_account", [False, True])
def test_testnet_authoritative_evidence_preserves_unknown_economics(with_account):
    accounting = AccountingService("ETH", mode="TESTNET", clock=lambda: T)
    pos = PerpPositionContext(market="ETH", signed_position_base=D("1"), entry_price=D("3000"),
            position_value=D("3100"), unrealized_pnl=D("100"), margin_used=D("300"),
            liquidation_price=D("2000"), return_on_equity=D(".3"), source="TESTNET", updated_at=T)
    account = {"account_value": D("10000"), "total_margin_used": D("300"),
               "withdrawable": D("9700"), "updated_at": T} if with_account else None
    accounting.observe_testnet(pos, account, mark=D("3100"))
    vault = accounting.snapshot()
    assert vault.accounting_complete == "PARTIAL" and not vault.simulated
    assert vault.position_base == 1 and vault.unrealized_pnl_quote == 100
    for name in ("settled_capital_quote", "fees_quote", "funding_quote", "realized_pnl_quote",
                 "available_capital_quote", "reserved_capital_quote", "net_pnl_quote"):
        assert getattr(vault, name) is None
    assert vault.equity_quote == (D("10000") if with_account else None)
    assert accounting.ledger.version == 0
    with pytest.raises(ValueError, match="TESTNET full fill accounting"):
        accounting.ingest_fill(fill())


def test_testnet_account_equity_is_bound_when_position_version_is_unchanged():
    accounting = AccountingService("ETH", mode="TESTNET", clock=lambda: T)
    pos = PerpPositionContext(market="ETH", signed_position_base=D("0"), source="TESTNET", updated_at=T)
    account = {"account_value": D("10000"), "updated_at": T}
    accounting.observe_testnet(pos, account)
    version = accounting.version
    accounting.observe_testnet(pos, {**account, "account_value": D("9000")})
    assert accounting.version > version
    assert accounting.snapshot().drawdown_pct == D(".1")
    assert accounting.snapshot().session_pnl_quote == D("-1000")


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["CREATE", "REPLACE"])
async def test_executed_callback_failure_diverges_and_revokes_old_authority(action, monkeypatch):
    rt, snap = await runtime()
    rt.strategy.running = True
    old = rt.authorization
    if action == "REPLACE":
        q = rt.quotes[0]
        await rt.paper.submit_orders([OrderRequest(client_order_id="rest", market="ETH", side=q.side,
            price=q.price * (D(".99") if q.side == "BID" else D("1.01")), size=q.size, level_index=q.level_index)])
    def interrupted(fill):
        raise RuntimeError("temporary callback interruption")
    monkeypatch.setattr(rt.accounting_service, "ingest_fill", interrupted)
    rt._strategy_wakeup.clear()
    await rt.paper.submit_orders([OrderRequest(client_order_id="cross", market="ETH", side="BID",
                                               price=snap.best_ask, size=D(".1"))])
    assert len(rt.paper.fills.all()) == 1 and rt.accounting_service.ledger.version == 0
    state = rt.accounting_service.snapshot()
    consistency = state.execution_accounting
    assert consistency.status == "DIVERGED" and consistency.execution_accounting_consistent is False
    assert consistency.execution_fill_count == consistency.unaccounted_fill_count == 1
    assert consistency.accounted_fill_count == 0
    assert consistency.oldest_unaccounted_fill_at == consistency.latest_unaccounted_fill_at == rt.paper.fills.all()[0].timestamp
    assert state.accounting_complete == "UNAVAILABLE"
    assert state.accounting_version > old.accounting_version
    assert state.accounting_fingerprint != old.accounting_fingerprint
    assert rt.agent_telemetry.summary()["fill_observations"] == 1 and rt._strategy_wakeup.is_set()
    submitted = []
    original = rt.paper.submit_orders
    async def submit(orders):
        submitted.extend(orders)
        return await original(orders)
    monkeypatch.setattr(rt.paper, "submit_orders", submit)
    with pytest.raises(RuntimeError, match="accounting stale, error or unavailable"):
        await rt.orders.reconcile("ETH", rt.quotes, D("0"), D("0"))
    assert not submitted
    await rt.orders.reconcile("ETH", [], D("0"), D("0"))
    assert not await rt.paper.get_open_orders()
    # Callback failure is latched, even if the callback becomes usable again.
    monkeypatch.undo()
    rt._sync_paper_fills_locked()
    assert rt.accounting_service.error and rt.accounting_service.ledger.version == 0
    assert rt.accounting_service.snapshot().execution_accounting.status == "DIVERGED"


@pytest.mark.asyncio
async def test_real_crossing_fill_capacity_failure_preserves_atomic_state_and_cancel():
    rt, snap = await runtime(ledger_max_entries=3, paper_fee_model_enabled=True)
    await rt.paper.submit_orders([OrderRequest(client_order_id="open", market="ETH", side="BID",
                                               price=snap.best_ask, size=D(".1"))])
    await rt.paper.submit_orders([OrderRequest(client_order_id="rest", market="ETH", side="BID",
                                               price=snap.best_bid - D("100"), size=D(".1"))])
    before = rt.accounting_service.snapshot()
    await rt.paper.submit_orders([OrderRequest(client_order_id="close", market="ETH", side="ASK",
                                               price=snap.best_bid, size=D(".1"))])
    after = rt.accounting_service.snapshot()
    assert len(rt.paper.fills.all()) == 2 and rt.accounting_service.ledger.version == 2
    assert not any(e.source_reference == "close" for e in rt.accounting_service.ledger.entries())
    for field in ("position_base", "settled_capital_quote", "fees_quote", "peak_equity_quote", "ledger_fingerprint"):
        assert getattr(after, field) == getattr(before, field)
    assert after.execution_accounting.status == "DIVERGED"
    assert after.execution_accounting.accounted_fill_count == after.execution_accounting.unaccounted_fill_count == 1
    assert after.accounting_complete == "UNAVAILABLE"
    error = rt.accounting_service.error
    await rt.refresh_once()
    assert rt.accounting_service.error == error
    assert rt.authorization is None or not rt.authorization.authorized
    rt._sync_paper_fills_locked()
    assert rt.accounting_service.ledger.version == 2
    await rt.orders.cancel_all()
    assert not await rt.paper.get_open_orders()


@pytest.mark.asyncio
async def test_sync_never_skips_failed_fill_or_books_later_fill(monkeypatch):
    rt, snap = await runtime()
    rt.paper.on_fill = None
    for cid in ("first", "second", "third"):
        await rt.paper.submit_orders([OrderRequest(client_order_id=cid, market="ETH", side="BID",
                                                   price=snap.best_ask, size=D(".1"))])
    attempts = []
    def interrupted(event):
        attempts.append(event.client_order_id)
        raise RuntimeError("interruption")
    monkeypatch.setattr(rt.accounting_service, "ingest_fill", interrupted)
    rt._sync_paper_fills_locked()
    rt._sync_paper_fills_locked()
    assert attempts == ["first"]
    state = rt.accounting_service.snapshot().execution_accounting
    assert state.unaccounted_fill_count == 3 and state.accounted_fill_count == 0


@pytest.mark.asyncio
async def test_pending_unfailed_evidence_reconciles_once_and_changes_provenance():
    rt, snap = await runtime(paper_fee_model_enabled=True)
    rt.paper.on_fill = None
    await rt.paper.submit_orders([OrderRequest(client_order_id="pending", market="ETH", side="BID",
                                               price=snap.best_ask, size=D(".1"))])
    state = rt.accounting_service.observe_execution_fills(rt.paper.fills.all())
    assert state.status == "DIVERGED"
    before = rt.accounting_service.snapshot()
    rt._sync_paper_fills_locked()
    after = rt.accounting_service.snapshot()
    assert after.execution_accounting.status == "CONSISTENT"
    assert after.accounting_version > before.accounting_version
    assert after.accounting_fingerprint != before.accounting_fingerprint
    assert after.position_base == D(".1")
    assert after.fees_quote == snap.best_ask * D(".1") * D("3") / D("10000")
    assert after.peak_equity_quote >= after.equity_quote
    assert rt.accounting_service.ledger.version == 2
    rt._sync_paper_fills_locked()
    assert rt.accounting_service.snapshot() == after
    await rt.refresh_once()
    assert rt.authorization.authorized
    assert rt.authorization.accounting_fingerprint == rt.accounting_service.fingerprint


@pytest.mark.asyncio
async def test_runtime_conflicting_identity_remains_diverged_with_equal_fill_counts():
    rt, snap = await runtime()
    await rt.paper.submit_orders([OrderRequest(client_order_id="cross", market="ETH", side="BID",
                                               price=snap.best_ask, size=D(".1"))])
    event = rt.paper.fills.all()[0]
    rt.paper.fills._fills[0] = event.model_copy(update={"price": event.price + D("1")})
    rt._sync_paper_fills_locked()
    state = rt.accounting_service.snapshot()
    assert state.execution_accounting.status == "DIVERGED"
    assert "conflicting" in state.error and state.accounting_complete == "UNAVAILABLE"
    await rt.refresh_once()
    assert rt.authorization is None or not rt.authorization.authorized
    assert rt.accounting_service.ledger.version == 2


@pytest.mark.asyncio
async def test_execution_retention_keeps_ledger_truth_and_unconsumed_evidence(monkeypatch):
    from app.execution.fills import FILL_HISTORY_LIMIT
    rt, snap = await runtime()
    rt.paper.fills.limit = 5
    rt.paper.orders.limit = 5
    first = None
    for index in range(18):
        await rt.paper.submit_orders([OrderRequest(client_order_id=f'fill-{index}', market='ETH', side='BID',
                                                   price=snap.best_ask, size=D('.01'))])
        if index == 0:
            first = rt.paper.fills.all()[0]
    assert FILL_HISTORY_LIMIT == 1000
    assert len(rt.paper.fills.all()) == len(rt.paper.fills.recent()) == 5
    assert rt.paper.fills.retired_count == 13
    assert not rt.paper.fills.pending()
    assert len(rt.paper.orders) == 5
    assert rt.paper.inventory_version == 18
    assert rt.paper.position_base('ETH') == rt.accounting_service.position.position_base == D('.18')
    assert rt.accounting_service.ledger.version == 36
    assert 'fill:'+rt.accounting_service.fill_identity(first) in rt.accounting_service.ledger.fill_evidence()
    rt._sync_paper_fills_locked()
    before = rt.accounting_service.snapshot()
    assert before.execution_accounting.execution_fill_count == before.execution_accounting.accounted_fill_count == 18
    rt._sync_paper_fills_locked()
    assert rt.accounting_service.snapshot() == before
    class NoLedgerIteration(list):
        def __iter__(self): raise AssertionError('full ledger scan')
    rt.accounting_service.ledger._entries = NoLedgerIteration(rt.accounting_service.ledger._entries)
    monkeypatch.setattr(rt.paper, 'all_orders', lambda: pytest.fail('full order history observation'))
    terminal = await rt.terminal_state()
    assert len(terminal['fills']) == 5 and len(terminal['orders']) == 5
    assert terminal['execution_summary']['fill_count'] == 18
    assert D(terminal['execution_summary']['filled_notional']) == rt.paper.fills.filled_notional
    assert rt.accounting_payload()['execution_accounting']['accounted_fill_count'] == 18
    rt.paper.on_fill = None
    await rt.paper.submit_orders([OrderRequest(client_order_id='unaccounted', market='ETH', side='BID',
                                               price=snap.best_ask, size=D('.01'))])
    pending = rt.paper.fills.pending()[0]
    assert not rt.paper.fills.acknowledge(pending, rt.accounting_service, agent_consumed=True)
    for index in range(20):
        await rt.paper.submit_orders([OrderRequest(client_order_id=f'cancel-{index}', market='ETH', side='BID',
                                                   price=snap.best_bid-D('10'), size=D('.01'))])
        await rt.paper.cancel_orders([f'cancel-{index}'])
    assert 'unaccounted' in rt.paper.orders
    state = rt.accounting_service.observe_execution_fills(rt.paper.fills.all(), retired_count=rt.paper.fills.retired_count)
    assert state.unaccounted_fill_count == 1 and state.accounted_fill_count == 18
    assert pending in rt.paper.fills.all() and rt.paper.fills.pending() == [pending]
    with pytest.raises(ValueError, match='conflicting'):
        rt.accounting_service.ingest_fill(first.model_copy(update={'price': first.price+D('1')}))
    assert rt.accounting_service.error and rt.accounting_service.ledger.version == 36


@pytest.mark.asyncio
async def test_fill_capacity_blocks_new_orders_without_losing_pending_or_cancellation():
    rt, snap = await runtime()
    rt.paper.fills.limit = 2
    rt.paper.on_fill = None
    await rt.paper.submit_orders([OrderRequest(client_order_id='rest', market='ETH', side='BID',
                                               price=snap.best_bid-D('10'), size=D('.01'))])
    for index in range(2):
        await rt.paper.submit_orders([OrderRequest(client_order_id=f'pending-{index}', market='ETH', side='BID',
                                                   price=snap.best_ask, size=D('.01'))])
    with pytest.raises(RuntimeError, match='capacity'):
        await rt.paper.submit_orders([OrderRequest(client_order_id='forbidden', market='ETH', side='BID',
                                                   price=snap.best_ask, size=D('.01'))])
    assert len(rt.paper.fills.pending()) == 2 and rt.accounting_service.ledger.version == 0
    await rt.paper.cancel_all()
    assert not await rt.paper.get_open_orders() and len(rt.paper.fills.all()) == 2


@pytest.mark.asyncio
async def test_fill_retention_requires_agent_and_matching_accounting_consumption():
    from app.execution.models import Fill
    rt, snap = await runtime()
    rt.paper.fills.limit = 1
    rt.paper.on_fill = None
    for cid in ['one', 'two']:
        rt.paper.fills.add(Fill(client_order_id=cid, market='ETH', side='BID', price=snap.best_ask, size=D('.01')))
    first, second = rt.paper.fills.all()
    rt.accounting_service.ingest_fill(first)
    assert not rt.paper.fills.acknowledge(first, rt.accounting_service, agent_consumed=False)
    assert len(rt.paper.fills.pending()) == 2
    assert rt.paper.fills.acknowledge(first, rt.accounting_service, agent_consumed=True)
    assert rt.paper.fills.pending() == [second]
    assert first in rt.paper.fills.all() and second in rt.paper.fills.all()
    rt.accounting_service.ingest_fill(second)
    assert rt.paper.fills.acknowledge(second, rt.accounting_service, agent_consumed=True)
    assert rt.paper.fills.all() == [second] and rt.paper.fills.retired_count == 1


@pytest.mark.asyncio
async def test_evicted_fill_identity_cannot_be_executed_twice():
    rt, snap = await runtime()
    rt.paper.fills.limit = 1
    for cid in ['first', 'second']:
        await rt.paper.submit_orders([OrderRequest(client_order_id=cid, market='ETH', side='BID',
                                                   price=snap.best_ask, size=D('.01'))])
        if cid == 'first':
            first = rt.paper.fills.all()[0]
    assert first not in rt.paper.fills.all()
    replay = first.model_copy(deep=True)
    rt.paper.fills.add(replay)
    rt._on_paper_fill(replay)
    assert 'duplicate execution fill identity' in rt.accounting_service.error
    assert replay in rt.paper.fills.pending()
    rt._sync_paper_fills_locked()
    state = rt.accounting_service.snapshot().execution_accounting
    assert state.unaccounted_fill_count == 1 and state.status == 'DIVERGED'
    assert rt.accounting_service.ledger.version == 4
