import asyncio
import ast
from pathlib import Path
from decimal import Decimal as D
import httpx
import pytest
from app.main import app
from app.config import Settings
from app.runtime import HyperAmmRuntime
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.live_streams import LiveMarketStreamService
from app.execution.models import OrderRequest
from test_phase14_research_vault import authority
from test_phase152_live_streams import streams
from phase154_helpers import request

@pytest.mark.parametrize('kill',[False,True])
async def test_seeded_actual_runtime_all_assets_concurrency_cancel_expiry_restart(streams,monkeypatch,kill):
    service,_,clock=streams;rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(4)
    await rt.market._accept(snap);await rt.refresh_once()
    await rt.paper.submit_orders([OrderRequest(client_order_id='comparison-seed',market='ETH',side='BID',price=snap.best_ask,size=D('.1'))])
    await rt.refresh_once();rt.strategy.running=True;await rt._execution_authority()
    async with rt.execution_lock:await rt.orders.reconcile_locked(rt.config.market,rt.quotes,rt.config.replace_tolerance_bps,rt.config.size_tolerance)
    rt.accounting_service.reserve(rt.quotes,await rt.execution.get_open_orders())
    if kill:await rt.activate_kill();await rt.refresh_once()
    assert rt.paper.fills.all() and rt.accounting_service.ledger.version>1
    before=authority(rt);identities=tuple(id(x) for x in (rt.market,rt.perp_context_service,rt.reference_service))
    monkeypatch.setattr(app.state,'runtime',rt,raising=False)
    monkeypatch.setattr(app.state,'live_market_streams',service,raising=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as c:
        async def run(m):return await c.post('/api/v1/research-market-comparison/compare',json=request(m,market=m).model_dump(mode='json'))
        for _ in range(2):assert all(r.status_code==200 for r in await asyncio.gather(*(run(m) for m in ('BTC','ETH','SOL'))))
        cancelled=asyncio.create_task(run('BTC'));cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):await cancelled
        assert (await c.post('/api/v1/research-market-comparison/compare',json={'strategy':'forbidden'})).status_code==422
        clock.advance(60);assert (await run('BTC')).json()['comparison_status']=='UNAVAILABLE'
        disabled=LiveMarketStreamService(Settings(_env_file=None),client_factory=lambda *a:pytest.fail('SDK activation'))
        monkeypatch.setattr(app.state,'live_market_streams',disabled)
        for m in ('BTC','ETH','SOL'):assert (await run(m)).json()['comparison_status']=='UNAVAILABLE'
        await disabled.close()
    assert authority(rt)==before
    assert identities==tuple(id(x) for x in (rt.market,rt.perp_context_service,rt.reference_service))


def test_no_authority_or_network_edges():
    for path in [*Path('app/research_comparison').glob('*.py'),Path('app/api/research_market_comparison.py')]:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.Attribute):assert node.attr not in ('runtime','update_config','start_strategy','place_order','order','refresh','execute','hyperliquid_private_key')
            if isinstance(node,ast.ImportFrom):assert not any(n.name in ('HyperAmmRuntime','Exchange','RiskFirewall','FinalQuoteAuthorization','MarketDataService','ReferenceService') for n in node.names)
    paths={k:v for k,v in app.openapi()['paths'].items() if '/research-market-comparison/' in k}
    assert len(paths)==1 and set(next(iter(paths.values())))=={'post'}
