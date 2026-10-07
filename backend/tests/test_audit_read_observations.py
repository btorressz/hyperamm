"""A1-011: API reads never initialize or advance domain authority."""
import copy
from unittest.mock import AsyncMock, Mock
import httpx
import pytest
from fastapi import FastAPI
from app.api import accounting, agents, health, markets, orders, positions, risk, strategy, terminal
from app.config import Settings
from app.runtime import HyperAmmRuntime
from app.market_data.mock import MockMarketDataAdapter


def authoritative(rt):
    names = ('strategy', 'fair_value', 'pool', 'quotes', 'strategy_quotes', 'agent_quotes',
             'inventory', 'inventory_decision', 'market_adaptation_decision', 'perp_context',
             'perp_reference_decision', 'perp_position', 'references', 'risk_decision',
             'authorization', 'agent_evidence', 'agent_decision', 'vault_snapshot')
    return copy.deepcopy({**{n: getattr(rt, n) for n in names},
        'accounting': {k:v for k,v in rt.accounting_service.__dict__.items() if not isinstance(v, Mock) and k != 'ledger'},
        'ledger': rt.accounting_service.ledger.__dict__,
        'market_history': rt.market_history.__dict__,
        'perp_service': {k:v for k,v in rt.perp_context_service.__dict__.items() if not isinstance(v, Mock)},
        'reference_version': (rt.reference_service._version, rt.reference_service._fingerprint),
        'firewall_version': rt.firewall.version,
        'supervisor_version': rt.agent_supervisor.version,
        'telemetry': rt.agent_telemetry.__dict__,
        'orders': rt.paper.all_orders(), 'fills': rt.paper.fills.all(),
        'terminal_history': rt.terminal_service.history.query(),
        'terminal_events': rt.terminal_service.events(),
        'terminal_sequence': rt.terminal_service.sequence})


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['PAPER', 'TESTNET'])
@pytest.mark.parametrize('initialized', [False, True])
async def test_repeated_gets_do_not_advance_authority(mode, initialized):
    rt = HyperAmmRuntime(Settings(_env_file=None, execution_mode=mode))
    if initialized:
        await rt.market._accept(MockMarketDataAdapter().snapshot_for(2))
        if mode == 'PAPER':
            await rt.refresh_once()
    # No route may call any update machinery, even with absent evidence.
    for owner, name in [(rt, 'refresh_once'), (rt.testnet, 'refresh_position'),
                        (rt.testnet, 'reconcile_venue'), (rt, '_inventory_state_locked')]:
        setattr(owner, name, AsyncMock(side_effect=AssertionError(f'read called {name}')))
    for owner, name in [(rt, '_mark_accounting_locked'), (rt.reference_service, 'snapshot'),
                        (rt.perp_context_service, 'accept'), (rt.accounting_service, 'reserve'),
                        (rt.accounting_service, 'observe_execution_fills')]:
        setattr(owner, name, Mock(side_effect=AssertionError(f'read called {name}')))
    app = FastAPI()
    app.state.runtime = rt
    for module in (accounting, agents, health, markets, orders, positions, risk, strategy, terminal):
        app.include_router(module.router, prefix='/api')
    before = authoritative(rt)
    paths = ['/amm/curve', '/amm/state', '/amm/quotes', '/strategy', '/market-adaptation',
             '/perp-context', '/references', '/risk/evidence', '/risk', '/risk/events',
             '/risk/authorization', '/agents', '/agents/events', '/vault', '/accounting/pnl',
             '/accounting/position', '/accounting/ledger', '/accounting/events', '/positions',
             '/orders', '/fills', '/health', '/markets/ETH', '/markets/ETH/book',
             '/terminal/history', '/terminal/events']
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for _ in range(3):
            for path in paths:
                response = await client.get('/api'+path)
                assert response.status_code == 200, (path, response.text)
                if not initialized and path in ('/market-adaptation', '/perp-context', '/references', '/positions'):
                    assert response.json() is None
    assert authoritative(rt) == before
    for _ in range(3):
        await rt.terminal_state()
    assert authoritative(rt) == before
    assert rt.accounting_service.observe_execution_fills.call_count == 0


@pytest.mark.asyncio
async def test_reading_pending_fill_evidence_does_not_repair_accounting():
    from decimal import Decimal
    from app.execution.models import Fill
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt.market._accept(MockMarketDataAdapter().snapshot_for(2))
    await rt.refresh_once()
    rt.paper.fills.add(Fill(client_order_id='pending-evidence', market='ETH', side='BID',
                           price=Decimal('3000'), size=Decimal('0.1')))
    before = authoritative(rt)
    for _ in range(3):
        await rt.inventory_summary()
        await rt.vault_summary()
        rt.accounting_payload()
        await rt._publish_terminal_snapshot()
        cached = await rt.terminal_state()
        cached['sequence'] = -1  # Caller-owned copy cannot corrupt the cache.
    after = authoritative(rt)
    for key in ('terminal_history', 'terminal_events', 'terminal_sequence'):
        after.pop(key)
        before.pop(key)
    assert after == before
    assert (await rt.terminal_state())['sequence'] > 0
    assert rt.accounting_service.position.position_base == 0
    assert rt.paper.fills.pending()
    # Explicit ticks still consume fills, preserving accounting/execution authority.
    await rt.refresh_once()
    assert rt.accounting_service.position.position_base == Decimal('0.1')
    assert not rt.paper.fills.pending()
