"""Phase 12.2 adversarial economics and observation acceptance; no live orders."""
from decimal import Decimal as D
from itertools import product

import pytest
from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.amm.discretizer import compile_quotes, normalize_price, normalize_size
from app.amm.diagnostics import effective_liquidity
from app.amm.liquidity_curve import sample_curve
from app.amm.models import AmmModel
from app.amm.virtual_reserves import initialize_virtual_pool, recenter_pool
from app.config import Settings
from app.execution.order_manager import OrderManager
from app.execution.paper import PaperExecutionAdapter
from app.market_data.mock import MockMarketDataAdapter
from app.risk.authorization import fingerprint
from app.risk.limits import validate_quotes
from app.risk.models import RiskStatus
from app.runtime import HyperAmmRuntime
from app.strategy.models import StrategyConfig
from app.strategy.quote_engine import QuoteEngine


def snapshot():
    return MockMarketDataAdapter().snapshot_for(0).model_copy(update={
        'best_bid': D('2999'), 'best_ask': D('3001'), 'mid_price': D('3000')})


def ladder(*, tick='.1', distance='.2', levels=50, model=AmmModel.CONSTANT_PRODUCT):
    return compile_quotes(initialize_virtual_pool(D('100'), D('300000')), D('3000'),
        model, levels, D(distance), D('5'), D(tick), 4, base_order_size=D('.05'))


@pytest.mark.parametrize('model', list(AmmModel))
@pytest.mark.parametrize('tick', ['.1', '2000', '1e-24'])
def test_executable_distance_comes_from_tick_price_and_curve_lineage_is_separate(model, tick):
    quotes = ladder(tick=tick, model=model)
    assert all(q.distance_bps == abs(q.price-D('3000'))/D('3000')*D('10000') for q in quotes)
    points = sample_curve(initialize_virtual_pool(D('100'), D('300000')), D('3000'), 50, D('.2'), model)
    assert max(p.distance_bps for p in points) == D('.2')
    if tick == '2000':
        assert all(q.distance_bps > D('3333') for q in quotes)
        with pytest.raises(ValueError, match='quote distance exceeds limit'):
            validate_quotes(quotes, snapshot(), RiskStatus())
    else:
        validate_quotes(quotes, snapshot(), RiskStatus())


@pytest.mark.parametrize('side,price,expected', [
    ('BID','3000','.1'), ('ASK','3000','.1'),
    ('BID','3000.09','.1'), ('ASK','3000.01','.1')])
def test_tick_direction_and_exact_boundaries(side, price, expected):
    price = D(price)
    normalized = normalize_price(price, D(expected), side)
    assert (normalized <= price if side == 'BID' else normalized >= price)
    if price == 3000:
        assert normalized == price


@pytest.mark.parametrize('side,tick', [('BID','4000'), ('ASK','0'), ('OTHER','.1')])
def test_invalid_or_nonpositive_ticks_fail_predictably(side, tick):
    with pytest.raises(ValueError):
        normalize_price(D('3000'), D(tick), side)


@pytest.mark.parametrize('metadata', ['0', '.2', 'NaN'])
def test_spoofed_distance_and_quote_reference_cannot_bypass_global_risk(metadata):
    quotes = [q.model_copy(update={'distance_bps': D(metadata),
        'market_fair_value': q.price, 'perp_reference_price': q.price}) for q in ladder(tick='2000')]
    with pytest.raises(ValueError, match='quote distance exceeds limit'):
        validate_quotes(quotes, snapshot(), RiskStatus())


@pytest.mark.parametrize('final_venue', [False, True])
def test_crossed_final_ladders_rejected_in_both_paths(final_venue):
    quotes = ladder(levels=1)
    quotes[0] = quotes[0].model_copy(update={'price': quotes[-1].price})
    with pytest.raises(ValueError, match='crossed'):
        validate_quotes(quotes, snapshot(), RiskStatus(), final_venue=final_venue)


@pytest.mark.parametrize('precision', [0, 2, 4, 8])
def test_rounded_floor_feasibility_and_budget(precision):
    quantum = D(1).scaleb(-precision)
    base = quantum * D('1.0001')
    with pytest.raises(ValidationError, match='Normalized minimum'):
        StrategyConfig(base_order_size=base, total_liquidity=base*4,
                       levels_per_side=4, size_precision=precision)
    config = StrategyConfig(base_order_size=base, total_liquidity=quantum*8,
                            levels_per_side=4, size_precision=precision)
    _, _, quotes = QuoteEngine().generate(config, snapshot())
    for side in ('BID', 'ASK'):
        assert sum(q.size for q in quotes if q.side == side) <= config.total_liquidity
        assert all(q.size >= quantum*2 for q in quotes if q.side == side)


def test_audit_precision_matrix_rejects_tiny_distances_and_preserves_ordinary_domain():
    # The audit's exact 120 combinations, with both models and a valid funding floor.
    passed = rejected = 0
    for reserve, fair, levels, distance in product(
            ['1e-50','1e-12','100','1e50','1e100'], ['1e-12','.01','3000','1e12'],
            [1,50], ['.001','2500','1e-26']):
        for model in AmmModel:
            if distance == '1e-26':
                with pytest.raises(ValidationError, match='representable'):
                    StrategyConfig(virtual_base_reserve=D(reserve), virtual_quote_reserve=D(reserve)*D(fair),
                        levels_per_side=levels, max_distance_bps=D(distance), amm_model=model,
                        total_liquidity=D('5'), base_order_size=D('.05'))
                rejected += 1
            else:
                config = StrategyConfig(virtual_base_reserve=D(reserve), virtual_quote_reserve=D(reserve)*D(fair),
                    levels_per_side=levels, max_distance_bps=D(distance), amm_model=model,
                    total_liquidity=D('5'), base_order_size=D('.05'), tick_size=D(fair)*D('1e-8'))
                pool = recenter_pool(initialize_virtual_pool(config.virtual_base_reserve, config.virtual_quote_reserve), D(fair))
                points = sample_curve(pool, D(fair), levels, D(distance), model)
                assert pool.reserve_base > 0 and pool.reserve_quote > 0
                assert abs(pool.reserve_base*pool.reserve_quote-pool.k) <= D('1e-18')*max(pool.k, D(1))
                for side in ('BID','ASK'):
                    values = [p for p in points if p.side == side]
                    assert all(p.incremental_base > 0 for p in values)
                    assert abs(sum(p.weight for p in values)-1) < D('1e-24')
                    assert [p.cumulative_base for p in values] == sorted(p.cumulative_base for p in values)
                quotes = compile_quotes(pool,D(fair),model,levels,D(distance),D(5),config.tick_size,4,base_order_size=D('.05'))
                assert all(q.price > 0 and q.size > 0 for q in quotes)
                passed += 1
    assert (passed, rejected) == (160,80)


@pytest.mark.parametrize('size', ['1e30', '1e1000'])
def test_large_size_quantization_errors_become_specific_validation_errors(size):
    with pytest.raises(ValidationError, match='representable'):
        StrategyConfig(base_order_size=D(size), total_liquidity=D(size)*8)
    with pytest.raises(ValueError, match='representable'):
        normalize_size(D(size),4)
    with pytest.raises(ValueError, match='representable'):
        compile_quotes(initialize_virtual_pool(D(100), D(300000)),D(3000),AmmModel.CONSTANT_PRODUCT,
            4,D(100),D(size)*4,D('.1'),4,base_order_size=D(size))


@pytest.mark.asyncio
async def test_runtime_coarse_tick_fails_before_paper_reconciliation(monkeypatch):
    rt = HyperAmmRuntime(Settings(_env_file=None))
    rt.config = StrategyConfig(levels_per_side=50, max_distance_bps=D('.2'), tick_size=D('2000'),
        total_liquidity=D(5), base_order_size=D('.05'), inventory_skew_enabled=False,
        market_adaptation_enabled=False, perp_context_enabled=False)
    rt.strategy.config = rt.config
    rt.agent_config.agents_enabled = False
    rt.strategy.running = True
    await rt.market._accept(snapshot())
    def no_reconcile(*args, **kwargs):
        pytest.fail('invalid economics reached reconciliation')
    monkeypatch.setattr(rt.orders, 'reconcile_locked', no_reconcile)
    await rt.refresh_once()
    assert rt.quotes == [] and rt.authorization is None
    assert 'quote distance exceeds limit' in rt.strategy.last_error
    assert not await rt.paper.get_open_orders()


@pytest.mark.asyncio
async def test_testnet_final_normalization_and_pretransmission_recheck(monkeypatch):
    from test_phase8_runtime import normalized_testnet_runtime
    rt, adapter, venue, snap = await normalized_testnet_runtime(monkeypatch)
    rt.risk.max_quote_distance_bps = D('.1')  # actual normalized distance is > .3 bps
    rt.quotes = [q.model_copy(update={'distance_bps': D(0)}) for q in rt.quotes]
    # Rebind fingerprint to prove the economic check is independent of identity.
    rt.authorization.quote_fingerprint = fingerprint(rt.quotes)
    with pytest.raises(ValueError, match='quote distance exceeds limit'):
        rt._validate_final_testnet(rt.quotes, snap, rt.inventory, rt.perp_context,
            rt.references, [], rt.accounting_service.snapshot())
    with pytest.raises(ValueError, match='quote distance exceeds limit'):
        await adapter.submit_orders([rt.orders.request_for('ETH',rt.quotes[0])])
    assert venue.transmissions == 0


@pytest.mark.asyncio
async def test_paper_revalidates_tightened_distance_before_transmission():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt.market._accept(snapshot())
    await rt.refresh_once()
    assert rt.authorization.authorized
    rt.strategy.running = True
    rt.risk.max_quote_distance_bps = D('1')
    with pytest.raises(ValueError, match='quote distance exceeds limit'):
        await rt._execution_authority()
    assert not await rt.paper.get_open_orders()


@pytest.mark.parametrize('changes', [
    {'base_order_size':'.10001','size_precision':2,'levels_per_side':4,'total_liquidity':'.40004'},
    {'max_distance_bps':'1e-26'}, {'base_order_size':'1e30','total_liquidity':'8e30'},
    {'tick_size':'4000'}])
def test_api_422_rejection_is_atomic_with_current_market(changes):
    from app.api.strategy import router
    from app.dependencies import runtime
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    rt = HyperAmmRuntime(Settings(_env_file=None))
    app.dependency_overrides[runtime] = lambda: rt
    with TestClient(app) as client:
        client.portal.call(rt.market._accept, snapshot())
        client.portal.call(rt.refresh_once)
        before = rt.strategy.model_dump(mode='json')
        identity = (rt.config, rt.market, rt.paper, rt.authorization, rt.lifecycle_state)
        config = before['config'] | changes
        response = client.put('/api/v1/strategy',json=config)
        assert response.status_code == 422, response.text
        assert rt.strategy.model_dump(mode='json') == before
        assert (rt.config, rt.market, rt.paper, rt.authorization, rt.lifecycle_state) == identity
        assert client.get('/api/v1/amm/curve').status_code == 200


@pytest.mark.asyncio
async def test_failed_runtime_preflight_preserves_running_orders_and_accounting():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt.market._accept(snapshot())
    rt.paper.update_market(snapshot())
    rt.strategy.running = True
    await rt.refresh_once()
    before_orders = [o.model_dump() for o in await rt.paper.get_open_orders()]
    before_quotes = fingerprint(rt.quotes)
    before_auth = rt.authorization.model_dump()
    before_accounting = rt.accounting_service.snapshot().model_dump()
    assert before_orders
    with pytest.raises(ValueError, match='normalized price'):
        await rt.update_config(StrategyConfig(tick_size=D(4000)))
    assert rt.strategy.running and rt.lifecycle_state == 'READY'
    assert [o.model_dump() for o in await rt.paper.get_open_orders()] == before_orders
    assert fingerprint(rt.quotes) == before_quotes and rt.authorization.model_dump() == before_auth
    assert rt.accounting_service.snapshot().model_dump() == before_accounting


@pytest.mark.asyncio
async def test_unavailable_preflight_evidence_accepts_static_valid_config_but_never_orders():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    config = StrategyConfig(tick_size=D(4000))
    await rt.update_config(config)  # No fresh market exists to decide tick feasibility.
    assert rt.config == config and rt.authorization is None
    assert not await rt.paper.get_open_orders()
    await rt.market._accept(snapshot())
    await rt.refresh_once()
    assert not rt.quotes and rt.authorization is None
    assert 'normalized price' in rt.strategy.last_error


def test_valid_api_update_keeps_200_behavior():
    from app.api.strategy import router
    from app.dependencies import runtime
    app=FastAPI();app.include_router(router,prefix='/api/v1')
    rt=HyperAmmRuntime(Settings(_env_file=None))
    app.dependency_overrides[runtime]=lambda:rt
    config=StrategyConfig(concentration_factor=D('10'))
    with TestClient(app) as client:
        client.portal.call(rt.market._accept,snapshot())
        response=client.put('/api/v1/strategy',json=config.model_dump(mode='json'))
        assert response.status_code==200,response.text
    assert rt.config==config and rt.strategy.config==config


@pytest.mark.parametrize('levels,tick,expected', [(4,'.001',8),(4,'1',2),(4,'10',2),(50,'.1',2)])
def test_side_price_groups_aggregate_exact_quantity_notional_and_lineage(levels,tick,expected):
    quotes = ladder(levels=levels,tick=tick)
    before = fingerprint(quotes)
    diag = effective_liquidity(quotes)
    assert fingerprint(quotes) == before
    assert diag['logical_slots'] == levels*2
    assert diag['unique_executable_prices'] == expected
    assert sum(g['logical_slots'] for g in diag['price_groups']) == len(quotes)
    assert sum(g['quantity'] for g in diag['price_groups']) == sum(q.size for q in quotes)
    assert sum(g['notional'] for g in diag['price_groups']) == sum(q.price*q.size for q in quotes)
    for group in diag['price_groups']:
        members = [q for q in quotes if (q.side,q.price) == (group['side'],group['price'])]
        assert group['level_indices'] == sorted(q.level_index for q in members)
        assert group['quantity'] == sum(q.size for q in members)
        assert group['notional'] == sum(q.price*q.size for q in members)
    assert diag['effective_bid_levels'] == diag['effective_ask_levels'] == expected//2
    assert bool(diag['warnings']) == (expected < levels*2)


def test_partial_collapse_and_suppressed_side_only_count_survivors():
    quotes = ladder(levels=4,tick='.03')
    diag = effective_liquidity(quotes)
    assert 2 < diag['unique_executable_prices'] < 8
    survivor = [q for q in quotes if q.side == 'ASK' and q.level_index < 2]
    diag = effective_liquidity(survivor)
    assert diag['logical_slots'] == 2 and diag['effective_bid_levels'] == 0
    assert diag['total_bid_quantity'] == 0
    assert diag['total_ask_quantity'] == sum(q.size for q in survivor)
    assert effective_liquidity([])['collapse_ratio'] == 0


@pytest.mark.parametrize('mutation', [{'price':D(0)}, {'size':D('NaN')}, {'side':'OTHER'}])
def test_invalid_ladders_cannot_be_reported_as_active_depth(mutation):
    quotes = ladder(levels=1)
    quotes[0] = quotes[0].model_copy(update=mutation)
    with pytest.raises(ValueError):
        effective_liquidity(quotes)


def test_crossed_or_duplicate_logical_slots_have_no_effective_depth():
    quotes = ladder(levels=1)
    with pytest.raises(ValueError):
        effective_liquidity(quotes+[quotes[0]])
    quotes[0] = quotes[0].model_copy(update={'price':quotes[-1].price})
    with pytest.raises(ValueError,match='uncrossed'):
        effective_liquidity(quotes)


@pytest.mark.asyncio
async def test_100_slot_two_price_reconciliation_and_existing_depth_are_independent():
    quotes = ladder()
    paper = PaperExecutionAdapter()
    manager = OrderManager(paper)
    before = fingerprint(quotes)
    actions = await manager.reconcile('ETH',quotes,D('.5'),D('.0001'))
    assert [a.action.value for a in actions] == ['CREATE']*100
    existing = await paper.get_open_orders()
    ids = {o.client_order_id for o in existing}
    assert len(ids) == 100
    diag = effective_liquidity(quotes)
    assert diag['logical_slots'] == 100 and diag['unique_executable_prices'] == 2
    actions = await manager.reconcile('ETH',quotes,D('.5'),D('.0001'))
    assert [a.action.value for a in actions] == ['KEEP']*100
    assert {o.client_order_id for o in await paper.get_open_orders()} == ids
    assert fingerprint(quotes) == before
    # Diagnostics of a new proposal do not claim those cancelled/resting orders
    # have already acquired the new proposal's price or quantity.
    next_quotes = [q.model_copy(update={'price':q.price+(D('-1') if q.side=='BID' else D('1'))})
                   for q in quotes if q.level_index < 49]
    effective_liquidity(next_quotes)
    assert {o.client_order_id for o in await paper.get_open_orders()} == ids
    actions = await manager.reconcile('ETH',next_quotes,D('.5'),D('.0001'))
    assert sum(a.action.value == 'CANCEL' for a in actions) == 2
    assert sum(a.action.value == 'REPLACE' for a in actions) == 98
    assert len(await paper.get_open_orders()) == 98


@pytest.mark.parametrize('state', ['NORMAL','WIDEN','REDUCE','HALT'])
@pytest.mark.asyncio
async def test_final_distance_survives_risk_transforms_and_halt_never_restores_slots(state):
    from app.risk.firewall import RiskState
    rt = HyperAmmRuntime(Settings(_env_file=None))
    await rt.market._accept(snapshot())
    await rt.refresh_once()
    decision = rt.risk_decision.model_copy(update={'state':RiskState(state),
        'allow_quotes':state!='HALT','spread_multiplier':D('2'), 'size_multiplier':D('.5'),
        'max_levels':2 if state=='REDUCE' else None})
    upstream = [q for q in rt.agent_quotes if q.side=='ASK']
    final = rt.firewall.transform(upstream,decision,center=rt.inventory_decision.reservation_price,
        tick_size=rt.config.tick_size,size_precision=rt.config.size_precision,base_order_size=rt.config.base_order_size)
    assert all(q.side=='ASK' for q in final) and len(final) <= len(upstream)
    if state=='HALT':
        assert final==[]
    else:
        rt.risk.max_quote_distance_bps=D('1')
        final=[q.model_copy(update={'distance_bps':D(0)}) for q in final]
        with pytest.raises(ValueError,match='quote distance exceeds limit'):
            validate_quotes(final,snapshot(),rt.risk)


@pytest.mark.parametrize('position', ['0','4','11','-11'])
@pytest.mark.asyncio
async def test_inventory_adaptation_and_agents_cannot_bypass_independent_distance(position):
    from app.strategy.inventory import build_inventory_state
    from app.agents.supervisor import transform_quotes
    from app.market_data.history import MarketPriceHistory
    from app.market_data.models import utcnow
    rt = HyperAmmRuntime(Settings(_env_file=None))
    snap = snapshot()
    await rt.market._accept(snap)
    await rt.refresh_once()
    inventory=build_inventory_state(market='ETH',position=D(position),target=D(0),
        soft_limit=D(5),source='PAPER',updated_at=utcnow(),stale=False,version=1)
    history=MarketPriceHistory();history.add_snapshot(snap)
    _,_,adapted,inv,_=rt.quote_engine.generate_market_adaptive(rt.config,snap,inventory,history)
    advice=rt.agent_decision.model_copy(update={'spread_multiplier':D(2),
        'bid_size_multiplier':D('.5'),'ask_size_multiplier':D('.5')})
    final=transform_quotes(adapted,advice,center=inv.reservation_price,
        tick_size=rt.config.tick_size,size_precision=rt.config.size_precision)
    if D(position)>10:
        assert all(q.side=='ASK' for q in final)
    elif D(position)<-10:
        assert all(q.side=='BID' for q in final)
    assert {(q.side,q.level_index) for q in final} <= {(q.side,q.level_index) for q in adapted}
    spoofed=[q.model_copy(update={'distance_bps':D(0)}) for q in final]
    with pytest.raises(ValueError,match='quote distance exceeds limit'):
        validate_quotes(spoofed,snap,RiskStatus(max_quote_distance_bps=D(1)))


@pytest.mark.asyncio
async def test_collapsed_paper_cohort_fills_account_once_and_kill_remains_authoritative():
    rt = HyperAmmRuntime(Settings(_env_file=None))
    rt.config=StrategyConfig(levels_per_side=50,max_distance_bps=D('.2'),total_liquidity=D(5),base_order_size=D('.05'))
    rt.strategy.config=rt.config
    rt.agent_config.agents_enabled=False
    rt.strategy.running=True
    snap=snapshot()
    await rt.market._accept(snap)
    rt.paper.update_market(snap)
    await rt.refresh_once()
    assert rt.authorization.authorized and len(await rt.paper.get_open_orders())==100
    before=fingerprint(rt.quotes)
    desired=effective_liquidity(rt.quotes)
    bid_total=desired['total_bid_quantity']
    rt.paper.update_market(snap.model_copy(update={'best_bid':D('2999.7'),'best_ask':D('2999.8'),'mid_price':D('2999.75')}))
    assert len(rt.paper.fills.all())==50
    rt._sync_paper_fills_locked()
    assert rt.accounting_service.position.position_base==bid_total
    ledger_version=rt.accounting_service.ledger.version
    rt._sync_paper_fills_locked()
    assert rt.accounting_service.ledger.version==ledger_version
    assert fingerprint(rt.quotes)==before
    assert desired['logical_slots']==100 and len(await rt.paper.get_open_orders())==50
    await rt.activate_kill()
    assert rt.authorization is None and not rt.quotes
    assert not await rt.paper.get_open_orders()
    with pytest.raises(PermissionError,match='kill switch'):
        await rt._execution_authority()


def test_curve_api_exposes_separate_stage_depth_without_authority_mutation():
    from app.api.strategy import router
    from app.dependencies import runtime
    app=FastAPI();app.include_router(router,prefix='/api/v1')
    rt=HyperAmmRuntime(Settings(_env_file=None))
    app.dependency_overrides[runtime]=lambda:rt
    rt.strategy_quotes=ladder()
    rt.agent_quotes=[q for q in rt.strategy_quotes if q.side=='ASK']
    rt.quotes=rt.agent_quotes[:2]
    before=fingerprint(rt.quotes)
    with TestClient(app) as client:
        data=client.get('/api/v1/amm/curve').json()['effective_liquidity']
    assert data['strategy']['logical_slots']==100
    assert data['agent']['logical_slots']==50
    assert data['authorized']['logical_slots']==2
    assert data['authorized']['effective_bid_levels']==0
    assert data['authorized']['total_ask_quantity']==str(sum(q.size for q in rt.quotes))
    assert isinstance(data['authorized']['price_groups'][0]['price'],str)
    assert isinstance(data['authorized']['price_groups'][0]['notional'],str)
    assert rt.authorization is None and fingerprint(rt.quotes)==before


def test_feasible_large_side_budget_is_not_quantized_as_one_order():
    config=StrategyConfig(levels_per_side=50,total_liquidity=D('1e25'),base_order_size=D('.05'))
    _,_,quotes=QuoteEngine().generate(config,snapshot())
    assert len(quotes)==100
    assert all(q.size>0 for q in quotes)
    for side in ('BID','ASK'):
        assert sum(q.size for q in quotes if q.side==side)<=config.total_liquidity
    # Executable-size feasibility does not grant permission to exceed risk size.
    with pytest.raises(ValueError,match='order size exceeds limit'):
        validate_quotes(quotes,snapshot(),RiskStatus())
