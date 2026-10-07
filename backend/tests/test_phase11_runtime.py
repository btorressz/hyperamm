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
    rt.accounting_service.ingest_fill(fill(price="3000"))
    rt.accounting_service.ingest_fill(fill("ASK", "2800", identity="b", seconds=1))
    await rt.refresh_once()
    assert rt.risk_decision.state == RiskState.HALT
    evidence = rt.risk_decision.pnl_drawdown
    assert evidence.current_equity == D("800")
    assert evidence.peak_equity == D("1000")
    assert evidence.session_pnl == D("-200")
    assert evidence.drawdown_pct == D(".2")
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
    rt.testnet._account_value = D("10000")
    monkeypatch.setattr(rt.testnet, "_require_enabled", lambda: None)
    async def reconcile(): pass
    async def refresh(market): return D("0")
    monkeypatch.setattr(rt.testnet, "reconcile_venue", reconcile)
    monkeypatch.setattr(rt.testnet, "refresh_position", refresh)
    await rt.refresh_once()
    assert rt.authorization.authorized
    rt.strategy.running = True
    await rt._execution_authority()
    rt.testnet._account_value = D("9000")
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
