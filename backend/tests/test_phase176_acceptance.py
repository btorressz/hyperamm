"""Independent final security, accounting and shared-worker acceptance."""
import asyncio
from datetime import timedelta
from decimal import Decimal, localcontext
from threading import Event

import httpx
import pytest

from app.main import app
from app.portfolio_research.aggregation import assemble_analysis
from app.portfolio_research.models import sealed
from app.portfolio_research.orchestration import execute_markets
from app.portfolio_research.terminal_models import ChartPoint, TerminalLeg, TerminalResult
from app.simulation.executor import SimulationExecutor, ResearchBusyError
from app.simulation.service import SimulationService
from phase173_fixtures import reseal
from test_phase14_research_vault import research_client, authority
from test_phase175_terminal import draft, terminal_request

URL = '/api/v1/portfolio-research/'
PATHS = ('preview', 'run', 'analyze', 'stress', 'terminal')


def payload(path):
    if path == 'preview':
        return draft(('BTC',)).model_dump(mode='json')
    q = terminal_request('CORRELATED_SELLOFF' if path == 'stress' else None,
                         markets=('BTC',)).model_dump(mode='json')
    if path != 'terminal':
        q.pop('contract_version'); q.pop('mode')
    if path == 'run':
        q.pop('risk_policy'); q.pop('scenario')
    elif path == 'analyze':
        q.pop('scenario')
    return q


@pytest.mark.parametrize('path', PATHS)
@pytest.mark.parametrize('field', ['receipt', 'baseline', 'charts', 'risk', 'source_result_fingerprint'])
def test_client_authority_rejected_by_every_route(research_client, monkeypatch, path, field):
    client, rt = research_client
    before = authority(rt)
    async def forbidden(*a, **kw):
        pytest.fail('untrusted evidence reached worker')
    monkeypatch.setattr(app.state.simulation_executor, 'execute', forbidden)
    q = payload(path); q[field] = {'authority': 'forged'}
    r = client.post(URL + path, json=q)
    assert r.status_code == 422 and r.headers['cache-control'] == 'no-store'
    assert authority(rt) == before


@pytest.mark.parametrize('path', PATHS)
@pytest.mark.parametrize('body', [b'{', b'{"budget":NaN}', b'{"budget":Infinity}', b'null'])
def test_malformed_json_and_nonfinite_bodies_are_sanitized(research_client, path, body):
    client, _ = research_client
    r = client.post(URL + path, content=body, headers={'Content-Type': 'application/json'})
    assert r.status_code == 422 and r.headers['cache-control'] == 'no-store'
    assert 'Traceback' not in r.text and '/workspace/' not in r.text


@pytest.mark.parametrize('path', PATHS)
@pytest.mark.parametrize('headers', [
    {'Host': 'attacker.invalid'}, {'Origin': 'https://attacker.invalid'},
    {'Origin': 'http://127.0.0.1:5999'}, {'X-Forwarded-For': '127.0.0.1'},
])
def test_all_routes_reject_unauthorized_boundary(research_client, path, headers):
    client, _ = research_client
    r = client.post(URL + path, content=b'{', headers=headers)
    assert r.status_code == 403 and r.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('path', PATHS)
async def test_nonlocal_peer_rejected_before_body(path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('192.0.2.1', 42)),
                                base_url='http://127.0.0.1') as client:
        r = await client.post(URL + path, content=b'x' * 65537)
        assert r.status_code == 403


@pytest.mark.parametrize('path', PATHS)
@pytest.mark.parametrize('chunked', [False, True])
def test_all_routes_keep_body_limit(research_client, path, chunked):
    client, _ = research_client
    body = iter([b'x' * 40000, b'x' * 25537]) if chunked else b'x' * 65537
    assert client.post(URL + path, content=body).status_code == 413


@pytest.mark.parametrize('markets', [('BTC',), ('ETH', 'SOL'), ('BTC', 'ETH', 'SOL')])
async def test_independent_native_economic_oracle(markets):
    q = terminal_request(markets=markets)
    receipts, evidence = await execute_markets(SimulationService(), q.config, collect_accounting=True)
    a = assemble_analysis(q.config, receipts, evidence, q.risk_policy)
    with localcontext() as ctx:
        ctx.prec = 80
        initial = q.config.budget.total_equity_quote
        reserve = initial - sum(x.allocated_equity_quote for x in q.config.allocations)
        equity = reserve + sum(r.vault.equity_quote for r in receipts)
        assert a.accounting.initial_capital_quote == initial
        assert a.accounting.reserve_quote == reserve
        assert a.accounting.equity_quote == equity
        assert a.accounting.pnl_quote == equity - initial
        assert a.accounting.session_loss_quote == max(Decimal(0), initial - equity)
        assert a.exposure.gross_exposure_quote == sum(abs(r.vault.position_base * r.vault.mark_price) for r in receipts)
        assert a.exposure.net_exposure_quote == sum(r.vault.position_base * r.vault.mark_price for r in receipts)
        for r, c in zip(receipts, a.accounting.contributions, strict=True):
            # Match existing native precision before summing exact portfolio contributions.
            with localcontext() as native_ctx:
                native_ctx.prec = 28
                pnl = r.vault.realized_pnl_quote + r.vault.unrealized_pnl_quote - r.vault.fees_quote + r.vault.funding_quote
            assert c.net_pnl_quote == pnl
        assert a.accounting.pnl_quote == sum(c.net_pnl_quote for c in a.accounting.contributions) + a.accounting.native_rounding_residual_quote
        assert a.accounting.capital_allocation_utilization == q.config.allocated_equity_quote / initial
        peak, maximum = initial, Decimal(0)
        for rows in zip(*(e.observations for e in evidence), strict=True):
            current = reserve + sum(p.equity_quote for p in rows)
            peak = max(peak, current)
            with localcontext() as ratio_ctx:
                ratio_ctx.prec = 50
                dd = (peak - current) / peak
                if dd.as_tuple().exponent < -60:
                    dd = dd.quantize(Decimal('1e-60'))
            maximum = max(maximum, dd)
        assert a.accounting.drawdown.max_drawdown_fraction == maximum


@pytest.fixture(scope='module')
def terminal_leg():
    return asyncio.run(SimulationService().terminal_portfolio_research(request=terminal_request())).baseline


@pytest.mark.parametrize('corruption', ['clock', 'risk_accounting', 'exposure_temporal', 'chart_maximum', 'risk_decision'])
def test_terminal_projection_rejects_inconsistent_resealed_sources(terminal_leg, corruption):
    raw = terminal_leg.model_dump()
    if corruption == 'clock':
        c = raw['charts']; c.pop('evidence_fingerprint')
        c['points'][1]['timestamp'] += timedelta(milliseconds=1)
        c['points'] = tuple(ChartPoint.model_validate(p) for p in c['points'])
        raw['charts'] = sealed(type(terminal_leg.charts), **c)
    elif corruption == 'risk_accounting':
        raw['risk'] = reseal(terminal_leg.risk, accounting_fingerprint='a'*64)
    elif corruption == 'exposure_temporal':
        raw['exposure'] = reseal(terminal_leg.exposure, temporal_fingerprint='a'*64)
    elif corruption == 'risk_decision':
        assert terminal_leg.risk.decision == 'HALT'
        raw['risk'] = reseal(terminal_leg.risk, decision='NORMAL', risk_compliant=True)
    else:
        c = raw['charts']; c.pop('evidence_fingerprint')
        for p in c['points']: p['drawdown_fraction'] = Decimal(0)
        c['points'] = tuple(ChartPoint.model_validate(p) for p in c['points'])
        raw['charts'] = sealed(type(terminal_leg.charts), **c)
    with pytest.raises(ValueError):
        TerminalLeg.model_validate(raw)


@pytest.fixture(scope='module')
def terminal_stress():
    return asyncio.run(SimulationService().terminal_portfolio_research(
        request=terminal_request('CORRELATED_SELLOFF')))


@pytest.mark.parametrize('corruption', ['comparison', 'risk_transition', 'configuration'])
def test_terminal_stress_rejects_resealed_comparison_substitutions(terminal_stress, corruption):
    r = terminal_stress
    if corruption == 'comparison':
        rows = list(r.metrics.comparisons)
        # Still arithmetically coherent, but not the source leg's native values.
        rows[0] = rows[0].model_copy(update={'baseline': Decimal(1), 'stressed': Decimal(2), 'difference': Decimal(1)})
        changes = {'metrics': r.metrics.model_copy(update={'comparisons': tuple(rows)})}
    elif corruption == 'risk_transition':
        changes = {'risk_transition': r.risk_transition.model_copy(update={'baseline_decision': 'NORMAL'})}
    else:
        changes = {'config_fingerprint': 'a'*64}
    with pytest.raises(ValueError):
        reseal(r, **changes)


COMPETITORS = ('run_portfolio_research', 'analyze_portfolio_research', 'stress_portfolio_research',
               'terminal_portfolio_research', 'run_scenario', 'optimize', 'replay_history',
               'compare_scenario_historical', 'compare_research_configs')


@pytest.mark.parametrize('active', ['run_portfolio_research', 'analyze_portfolio_research', 'stress_portfolio_research'])
async def test_native_portfolio_blocks_all_competitors_and_cancelled_shutdown(monkeypatch, active):
    loop = asyncio.get_running_loop()
    started, release = asyncio.Event(), Event()
    original = SimulationService.run_scenario
    calls = []
    async def held(self, **kw):
        calls.append(kw['strategy'].market)
        if len(calls) == 1:
            loop.call_soon_threadsafe(started.set)
            assert release.wait(30)
        return await original(self, **kw)
    monkeypatch.setattr(SimulationService, 'run_scenario', held)
    worker = SimulationExecutor()
    raw = payload({'run_portfolio_research':'run', 'analyze_portfolio_research':'analyze', 'stress_portfolio_research':'stress'}[active])
    first = asyncio.create_task(worker.execute(active, request=raw))
    closing = None
    try:
        await asyncio.wait_for(started.wait(), 15)
        for operation in COMPETITORS:
            with pytest.raises(ResearchBusyError): await worker.execute(operation)
        first.cancel()
        with pytest.raises(asyncio.CancelledError): await first
        assert worker._busy
        closing = asyncio.create_task(worker.shutdown())
        await asyncio.sleep(0)
        assert not closing.done()
        with pytest.raises(ResearchBusyError): await worker.execute('run_scenario')
    finally:
        release.set()
        if closing: await asyncio.wait_for(closing, 30)
        else: await worker.shutdown()
    assert calls == ['BTC']  # Stress leg uses the native dataset entry point, no duplicate baseline.
    assert not worker._busy and all(not t.is_alive() for t in worker._pool._threads)


@pytest.mark.parametrize('allow_demo', [False, True])
@pytest.mark.parametrize('bad_metadata', [None,
    {'universe':[{'name':'BTC','szDecimals':True}]},
    {'universe':[{'name':'BTC','szDecimals':5},{'name':'BTC','szDecimals':5}]},
])
async def test_real_catalog_invalid_metadata_is_explicit_and_has_no_authority(allow_demo, bad_metadata):
    from app.market_data.hyperliquid_metadata import HyperliquidMetadataCatalog
    from app.portfolio_research.preview import prepare
    catalog = HyperliquidMetadataCatalog(allow_demo=allow_demo, loader=lambda: bad_metadata)
    try:
        result = await catalog.catalog()
        assert tuple(m.market for m in result.markets) == ('BTC', 'ETH', 'SOL')
        assert all(m.metadata_status == ('DEMO_PROFILE' if allow_demo else 'UNAVAILABLE') for m in result.markets)
        assert all(m.unavailable_reason for m in result.markets)
        if allow_demo:
            selected = {m.market: await catalog.resolve(m.market) for m in result.markets}
            p = prepare(draft(), selected)
            assert p.authority == 'NONE'
            assert all(s.captured.inputs().market_profile.metadata_status == 'DEMO_PROFILE' for s in p.config.scenarios)
        else:
            for market in ('BTC', 'ETH', 'SOL'):
                with pytest.raises(ValueError, match='unavailable'):
                    await catalog.resolve(market)
    finally:
        await catalog.close()
