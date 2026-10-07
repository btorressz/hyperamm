from decimal import Decimal as D
import pytest
from app.amm.models import QuoteLevel, AmmModel
from app.execution.models import OrderRequest, StrategyOrder, OrderStatus
from app.execution.paper import PaperExecutionAdapter
from app.execution.quote_reconciler import reconcile_quotes, ReconcileActionType
from app.execution.hyperliquid import HyperliquidTestnetExecutionAdapter
from app.market_data.mock import MockMarketDataAdapter


def q(side='BID',price='2999',size='1',level=0):
    return QuoteLevel(side=side,price=D(price),size=D(size),level_index=level,distance_bps=D('3'),source_model=AmmModel.CONSTANT_PRODUCT)
def o(side='BID',price='2999',size='1',level=0,cid='x'):
    return StrategyOrder(client_order_id=cid,market='ETH',side=side,price=D(price),size=D(size),level_index=level)

def test_reconcile_keep(): assert reconcile_quotes([q()],[o()],D('1'),D('0.01'))[0].action==ReconcileActionType.KEEP
def test_reconcile_create(): assert reconcile_quotes([q()],[],D('1'),D('0.01'))[0].action==ReconcileActionType.CREATE
def test_reconcile_replace(): assert reconcile_quotes([q(price='2999')],[o(price='2900')],D('1'),D('0.01'))[0].action==ReconcileActionType.REPLACE
def test_reconcile_cancel(): assert reconcile_quotes([],[o()],D('1'),D('0.01'))[0].action==ReconcileActionType.CANCEL

@pytest.mark.asyncio
async def test_paper_order_lifecycle_and_fill():
    ex=PaperExecutionAdapter(); snap=MockMarketDataAdapter().snapshot_for(1); ex.update_market(snap)
    req=OrderRequest(client_order_id='cross',market='ETH',side='BID',price=snap.best_ask,size=D('1'),level_index=0)
    orders=await ex.submit_orders([req])
    assert orders[0].status==OrderStatus.FILLED
    assert ex.fills.all()[0].source=='SIMULATED PAPER FILL'

@pytest.mark.asyncio
async def test_paper_open_then_cancel():
    ex=PaperExecutionAdapter(); snap=MockMarketDataAdapter().snapshot_for(1); ex.update_market(snap)
    req=OrderRequest(client_order_id='rest',market='ETH',side='BID',price=snap.best_bid-D('10'),size=D('1'),level_index=0)
    await ex.submit_orders([req]); assert (await ex.get_open_orders())[0].status==OrderStatus.OPEN
    await ex.cancel_orders(['rest']); assert ex.orders['rest'].status==OrderStatus.CANCELLED

@pytest.mark.asyncio
async def test_no_testnet_submission_when_disabled():
    ex=HyperliquidTestnetExecutionAdapter(enabled=False,private_key=None,account_address=None,base_url='https://api.hyperliquid-testnet.xyz')
    with pytest.raises(PermissionError):
        await ex.submit_orders([OrderRequest(client_order_id='x',market='ETH',side='BID',price=D('1'),size=D('1'))])

def test_testnet_response_rejection_and_resting_normalization():
    ex=HyperliquidTestnetExecutionAdapter(enabled=False,private_key=None,account_address=None,base_url='https://api.hyperliquid-testnet.xyz')
    status,oid=ex._parse_order_response({'status':'ok','response':{'data':{'statuses':[{'resting':{'oid':123}}]}}})
    assert status==OrderStatus.OPEN and oid=='123'
    status,oid=ex._parse_order_response({'status':'ok','response':{'data':{'statuses':[{'error':'Post only would cross'}]}}})
    assert status==OrderStatus.REJECTED and oid is None

from app.execution.order_manager import OrderManager


class VenueFixture:
    """SDK-shaped synchronous fixture; no wallet credentials or network."""
    def __init__(self):
        self.opened=[]; self.results={}; self.callbacks={}
        self.asset_to_sz_decimals={0:4}
        self.cancel_response={'status':'ok','response':{'data':{'statuses':['success']}}}
        self.order_response={'status':'ok','response':{'data':{'statuses':[{'resting':{'oid':123}}]}}}
        self.transmissions=0
        self.arguments=[]
    def name_to_asset(self,market): return 0
    def open_orders(self,address): return self.opened
    def query_order_by_oid(self,address,oid): return self.results.get(str(oid),{'status':'unknownOid'})
    def query_order_by_cloid(self,address,cloid): return self.results.get('cloid',{'status':'unknownOid'})
    def subscribe(self,subscription,callback):
        self.callbacks[subscription['type']]=callback
        return len(self.callbacks)
    def disconnect_websocket(self): self.callbacks.clear()
    def order(self,*args):
        self.transmissions+=1
        self.arguments.append(args)
        if isinstance(self.order_response,Exception): raise self.order_response
        return self.order_response
    def cancel_by_cloid(self,*args): return self.cancel_response


def venue_adapter():
    venue=VenueFixture()
    adapter=HyperliquidTestnetExecutionAdapter(enabled=True,private_key='fixture-only',account_address='fixture-account',
        base_url='https://api.hyperliquid-testnet.xyz',venue_info=venue,exchange=venue)
    venue.info=venue
    async def fixture_authority(request):
        assert (request.market,request.side,request.price,request.size) == ('ETH','BID',D('2999'),D('1'))
    adapter.authority=fixture_authority
    order=o(cid='tracked'); order.venue_order_id='123'
    adapter._orders['tracked']=order
    return adapter,venue,order


def venue_update(status,remaining='0',oid=123):
    return {'status':'order','order':{'status':status,'statusTimestamp':1700000000000,
        'order':{'oid':oid,'coin':'ETH','sz':remaining,'origSz':'1'}}}


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected',[('filled',OrderStatus.FILLED),('canceled',OrderStatus.CANCELLED),('marginCanceled',OrderStatus.CANCELLED),('expired',OrderStatus.CANCELLED),('rejected',OrderStatus.REJECTED),('postOnlyRejected',OrderStatus.REJECTED)])
async def test_venue_missing_open_order_gets_authoritative_terminal_status(status,expected):
    adapter,venue,order=venue_adapter()
    venue.results['123']=venue_update(status,remaining='0' if status=='filled' else '1')
    await adapter.reconcile_venue()
    assert order.status==expected and order.venue_order_id=='123'
    assert order.filled_size==(D('1') if status=='filled' else D('0'))
    assert int(order.updated_at.timestamp())==1700000000
    assert not adapter._orders.active()
    assert adapter.has_unknown_exposure() == bool(adapter._needs_verification)
    before=order.model_copy(deep=True)
    await adapter.reconcile_venue()
    assert order==before


@pytest.mark.parametrize('asset,decimals',[(0,n) for n in range(7)]+[(10000,n) for n in range(9)])
@pytest.mark.parametrize('side',['BID','ASK'])
def test_decimal_venue_normalization_precision_and_idempotence(asset,decimals,side):
    from types import SimpleNamespace
    info=SimpleNamespace(name_to_asset=lambda market:asset,asset_to_sz_decimals={asset:decimals})
    exchange=SimpleNamespace(info=info)
    req=OrderRequest(client_order_id='stable-id',market='ETH',side=side,level_index=3,
                     price=D('1234.56789'),size=D('12.345678901'))
    normalized=HyperliquidTestnetExecutionAdapter.normalize_order_request(exchange,req)
    assert isinstance(normalized.price,D) and isinstance(normalized.size,D)
    assert normalized.price <= req.price if side == 'BID' else normalized.price >= req.price
    assert 0 < normalized.size <= req.size
    max_places=(8 if asset >= 10000 else 6)-decimals
    assert normalized.price == normalized.price.quantize(D(1).scaleb(-max_places))
    assert len(normalized.price.normalize().as_tuple().digits) <= 5 or normalized.price == normalized.price.to_integral_value()
    assert normalized.size == normalized.size.quantize(D(1).scaleb(-decimals))
    assert HyperliquidTestnetExecutionAdapter.normalize_order_request(exchange,normalized) == normalized
    assert (normalized.client_order_id,normalized.market,normalized.side,normalized.level_index) == ('stable-id','ETH',side,3)
    price,size=HyperliquidTestnetExecutionAdapter._normalize_for_sdk(exchange,normalized)
    from hyperliquid.utils.signing import float_to_wire
    assert D(float_to_wire(price)) == normalized.price and D(float_to_wire(size)) == normalized.size


@pytest.mark.parametrize('price',['2999.9','3000.1','123456','0.01'])
def test_valid_venue_economics_remain_unchanged(price):
    adapter,venue,_=venue_adapter()
    req=OrderRequest(client_order_id='stable',market='ETH',side='BID',price=D(price),size=D('.1234'))
    assert adapter.normalize_order_request(venue,req) == req


@pytest.mark.parametrize('field,value',[(field,value) for field in ('price','size')
                                     for value in ('NaN','Infinity','-Infinity','0','-1')])
def test_invalid_decimal_venue_economics_rejected(field,value):
    adapter,venue,_=venue_adapter()
    req=OrderRequest(client_order_id='invalid',market='ETH',side='BID',price=D('2999'),size=D('1'))
    req=req.model_copy(update={field:D(value)})
    with pytest.raises(ValueError,match='finite and positive'):
        adapter.normalize_order_request(venue,req)


def test_sub_quantum_size_rejected_and_audit_counterexample_closed():
    adapter,venue,_=venue_adapter()
    req=OrderRequest(client_order_id='audit',market='ETH',side='BID',price=D('2999.96'),size=D('.12349'))
    bid=adapter.normalize_order_request(venue,req)
    ask=adapter.normalize_order_request(venue,req.model_copy(update={'side':'ASK','price':D('3000.04')}))
    assert bid.price == D('2999.9') < D('2999.96')
    assert ask.price == D('3000.1') > D('3000.04')
    assert bid.price < ask.price and bid.size == ask.size == D('.1234')
    with pytest.raises(ValueError,match='zero'):
        adapter.normalize_order_request(venue,req.model_copy(update={'size':D('.00001')}))


def test_spot_perp_fractional_constraint_and_zero_bid_rejection():
    adapter,venue,_=venue_adapter()
    req=OrderRequest(client_order_id='precision',market='ETH',side='BID',price=D('.123456'),size=D('1'))
    assert adapter.normalize_order_request(venue,req).price == D('.12')
    venue.asset_to_sz_decimals[10000]=4
    venue.name_to_asset=lambda market:10000
    assert adapter.normalize_order_request(venue,req).price == D('.1234')
    venue.name_to_asset=lambda market:0
    with pytest.raises(ValueError,match='non-positive'):
        adapter.normalize_order_request(venue,req.model_copy(update={'price':D('.001')}))


@pytest.mark.asyncio
async def test_testnet_requires_concrete_authority_but_cancellation_does_not():
    adapter,venue,order=venue_adapter()
    adapter.authority=None
    with pytest.raises(PermissionError,match='authority is required'):
        await adapter.submit_orders([order])
    assert venue.transmissions == 0
    await adapter.cancel_all()
    assert order.status == OrderStatus.CANCELLED


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[{'price':D('2999.96')},{'size':D('.12349')}])
async def test_adapter_refuses_post_authorization_normalization(change):
    adapter,venue,_=venue_adapter()
    req=OrderRequest(client_order_id='new',market='ETH',side='BID',price=D('2999'),size=D('1'))
    with pytest.raises(ValueError,match='not already venue-normalized'):
        await adapter.submit_orders([req.model_copy(update=change)])
    assert venue.transmissions == 0 and 'new' not in adapter._orders


@pytest.mark.asyncio
async def test_sdk_round_trip_drift_fails_before_unknown_registration():
    adapter,venue,_=venue_adapter()
    req=OrderRequest(client_order_id='huge',market='ETH',side='BID',
                     price=D('9007199254740993'),size=D('1'))
    async def authorized(request): assert request == req
    adapter.authority=authorized
    with pytest.raises(ValueError,match='SDK serialization changes'):
        await adapter.submit_orders([req])
    assert venue.transmissions == 0 and 'huge' not in adapter._orders


@pytest.mark.asyncio
async def test_mutation_during_authority_fails_closed():
    adapter,venue,_=venue_adapter()
    req=OrderRequest(client_order_id='new',market='ETH',side='BID',price=D('2999'),size=D('1'))
    async def mutate(request): request.price=D('3000')
    adapter.authority=mutate
    with pytest.raises(ValueError,match='changed during final authority'):
        await adapter.submit_orders([req])
    assert venue.transmissions == 0 and 'new' not in adapter._orders


@pytest.mark.asyncio
async def test_partial_fill_unknown_orders_and_idempotence():
    adapter,venue,order=venue_adapter()
    venue.opened=[{'oid':123,'coin':'ETH','sz':'.6'}, {'oid':999,'coin':'BTC','sz':'50'}]
    await adapter.reconcile_venue()
    assert order.status==OrderStatus.PARTIALLY_FILLED and order.filled_size==D('.4')
    assert await adapter.get_open_orders()==[order]
    before=order.model_copy(deep=True)
    await adapter.reconcile_venue()
    assert order==before and len(adapter._orders)==1
    assert reconcile_quotes([q()],[order],D('1'),D('.01'))[0].action==ReconcileActionType.REPLACE
    await adapter.cancel_all()
    assert order.status==OrderStatus.CANCELLED and order.filled_size==D('.4')


@pytest.mark.asyncio
async def test_absence_without_terminal_evidence_is_unknown_and_blocks_reconcile():
    adapter,venue,order=venue_adapter()
    with pytest.raises(RuntimeError,match='unknown'):
        await OrderManager(adapter).reconcile('ETH',[q()],D('1'),D('.01'))
    assert order.status==OrderStatus.UNKNOWN
    assert venue.transmissions==0 and adapter.reconciliation_error
    assert await adapter.get_open_orders()==[order]
    await adapter.cancel_all()
    assert not adapter._orders.active()
    assert adapter.has_unknown_exposure() == bool(adapter._needs_verification)


@pytest.mark.asyncio
async def test_websocket_notifications_wake_authoritative_runtime_reconciliation():
    import asyncio
    from app.config import Settings
    from app.runtime import HyperAmmRuntime
    from app.strategy.models import ExecutionMode
    adapter,venue,order=venue_adapter()
    rt=HyperAmmRuntime(Settings())
    rt.testnet=adapter; rt.execution=adapter; rt.orders.execution=adapter
    rt.config.execution_mode=ExecutionMode.TESTNET
    venue.opened=[{'oid':123,'coin':'ETH','sz':'1'}]
    await adapter.reconcile_venue()
    task=asyncio.create_task(rt._venue_loop())
    try:
        venue.opened=[]; venue.results['123']=venue_update('filled')
        await asyncio.to_thread(venue.callbacks['userFills'],{'channel':'userFills','data':{}})
        async def completed():
            while order.status!=OrderStatus.FILLED: await asyncio.sleep(.001)
        await asyncio.wait_for(completed(),1)
        assert order.filled_size==D('1')
        assert set(venue.callbacks)=={'orderUpdates','userFills'}
    finally:
        rt._closing=True; adapter.venue_changed.set()
        await task; await adapter.close()


@pytest.mark.asyncio
async def test_cancel_rejection_preserves_active_exposure():
    adapter,venue,order=venue_adapter()
    venue.opened=[{'oid':123,'coin':'ETH','sz':'1'}]
    venue.cancel_response={'status':'ok','response':{'data':{'statuses':[{'error':'failed'}]}}}
    with pytest.raises(RuntimeError,match='confirm cancellation'): await adapter.cancel_all()
    assert order.status==OrderStatus.OPEN


@pytest.mark.asyncio
async def test_cancel_fill_race_uses_venue_evidence():
    adapter,venue,order=venue_adapter()
    venue.results['123']=venue_update('filled')
    venue.cancel_response={'status':'ok','response':{'data':{'statuses':[{'error':'already filled'}]}}}
    await adapter.cancel_all()
    assert order.status==OrderStatus.FILLED and order.filled_size==D('1')


@pytest.mark.asyncio
async def test_submission_timeout_retains_cancellable_unknown_order():
    adapter,venue,order=venue_adapter(); venue.order_response=TimeoutError('response lost')
    request=OrderRequest(client_order_id='new',market='ETH',side='BID',price=D('2999'),size=D('1'))
    with pytest.raises(TimeoutError): await adapter.submit_orders([request])
    assert adapter._orders['new'].status==OrderStatus.UNKNOWN
    await adapter.cancel_all()
    assert not adapter._orders.active()
    assert adapter.has_unknown_exposure() == bool(adapter._needs_verification)


@pytest.mark.asyncio
async def test_final_authority_check_after_sdk_setup_blocks_transmission():
    adapter,venue,order=venue_adapter()
    async def denied(request): raise PermissionError('kill switch is active')
    adapter.authority=denied
    with pytest.raises(PermissionError):
        await adapter.submit_orders([OrderRequest(client_order_id='new',market='ETH',side='BID',price=D('2999'),size=D('1'))])
    assert venue.transmissions==0


@pytest.mark.asyncio
@pytest.mark.parametrize('url',['https://api.hyperliquid.xyz','https://testnet.evil.example','https://api.hyperliquid-testnet.xyz.evil.example'])
async def test_only_official_testnet_endpoint_allowed(url):
    adapter,venue,order=venue_adapter(); adapter.base_url=url
    with pytest.raises(PermissionError): await adapter.submit_orders([order])
    assert venue.transmissions==0


@pytest.mark.asyncio
async def test_cancel_ack_is_followed_by_fill_quantity_verification():
    adapter,venue,order=venue_adapter()
    await adapter.cancel_all()
    assert order.status==OrderStatus.CANCELLED
    venue.results['123']=venue_update('canceled',remaining='.6')
    await adapter.reconcile_venue()
    assert order.status==OrderStatus.CANCELLED and order.filled_size==D('.4')


@pytest.mark.asyncio
async def test_malformed_submission_response_retains_unknown_exposure():
    adapter,venue,order=venue_adapter()
    venue.order_response={'status':'ok','response':{}}
    req=OrderRequest(client_order_id='new',market='ETH',side='BID',price=D('2999'),size=D('1'))
    with pytest.raises(RuntimeError,match='UNKNOWN'): await adapter.submit_orders([req])
    assert adapter._orders['new'].status==OrderStatus.UNKNOWN


@pytest.mark.asyncio
async def test_immediate_fill_records_full_filled_size():
    adapter,venue,order=venue_adapter()
    venue.order_response={'status':'ok','response':{'data':{'statuses':[{'filled':{'oid':321,'totalSz':'1'}}]}}}
    req=OrderRequest(client_order_id='new',market='ETH',side='BID',price=D('2999'),size=D('1'))
    placed=(await adapter.submit_orders([req]))[0]
    assert placed.status==OrderStatus.FILLED and placed.filled_size==placed.size
    assert placed.venue_order_id=='321'


@pytest.mark.asyncio
async def test_cancelled_sdk_waiter_cannot_outlive_kill_barrier():
    import asyncio
    import threading
    from app.risk.kill_switch import KillSwitch
    from app.risk.models import RiskStatus
    adapter,venue,order=venue_adapter()
    lock=asyncio.Lock(); entered=threading.Event(); release=threading.Event()
    def slow_order(*args):
        entered.set()
        assert release.wait(2)
        return venue.order_response
    venue.order=slow_order
    async def submit():
        async with lock:
            await adapter.submit_orders([OrderRequest(client_order_id='new',market='ETH',side='BID',price=D('2999'),size=D('1'))])
    task=asyncio.create_task(submit())
    assert await asyncio.to_thread(entered.wait,1)
    task.cancel()
    kill=asyncio.create_task(KillSwitch(RiskStatus(),lock).activate(adapter))
    try:
        await asyncio.sleep(0)
        assert not kill.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError): await task
    await asyncio.wait_for(kill,1)
    assert not adapter._orders.active()
    assert adapter.has_unknown_exposure() == bool(adapter._needs_verification)


@pytest.mark.parametrize('side', ['BID', 'ASK'])
@pytest.mark.parametrize('filled', ['0', '.25'])
@pytest.mark.parametrize('prices', [('100', '100'), ('100', '120')])
def test_duplicate_slot_exposure_and_capital_sum_every_remaining_order(side, filled, prices):
    from app.risk.firewall import exposure_metrics
    from app.accounting.vault import reserved_capital
    rows = [o(side=side, price=price, cid=str(index)) for index, price in enumerate(prices)]
    for row in rows:
        row.filled_size = D(filled)
        row.status = OrderStatus.PARTIALLY_FILLED if filled != '0' else OrderStatus.OPEN
    desired = [q(side=side, price='105')]
    exp = exposure_metrics(desired, D('0'), D('100'), D('10'), rows)
    quantity = D('2') * (D('1')-D(filled))
    notional = sum(D(price)*(D('1')-D(filled)) for price in prices)
    assert (exp.bid_quantity if side == 'BID' else exp.ask_quantity) == quantity
    assert (exp.bid_quote_notional if side == 'BID' else exp.ask_quote_notional) == notional
    assert exp.gross_quote_notional == notional
    assert reserved_capital(D('0'), D('100'), desired, rows) == notional


@pytest.mark.parametrize('side', ['BID', 'ASK'])
def test_reconciler_prefers_matching_keeper_and_cancels_every_surplus(side):
    valid = o(side=side, cid='valid', size='2')
    valid.filled_size = D('1')
    valid.status = OrderStatus.PARTIALLY_FILLED
    rows = [o(side=side, cid='bad', price='2500'), valid, o(side=side, cid='surplus')]
    actions = reconcile_quotes([q(side=side)], rows, D('1'), D('.01'))
    assert [(a.action, a.existing.client_order_id) for a in actions] == [
        (ReconcileActionType.CANCEL, 'bad'), (ReconcileActionType.CANCEL, 'surplus'),
        (ReconcileActionType.KEEP, 'valid')]


@pytest.mark.asyncio
@pytest.mark.parametrize('level', [None, -1, 0])
async def test_unknown_surplus_blocks_create_and_replace_and_remains_cancellable(level):
    adapter = PaperExecutionAdapter()
    keeper = o(cid='keeper')
    unknown = o(cid='unknown', level=level)
    unknown.status = OrderStatus.UNKNOWN
    adapter.orders[keeper.client_order_id] = keeper
    adapter.orders[unknown.client_order_id] = unknown
    with pytest.raises(RuntimeError, match='unresolved'):
        await OrderManager(adapter).reconcile('ETH', [q(price='2900'), q(level=1)], D('1'), D('.01'))
    assert adapter.orders['unknown'].status == OrderStatus.UNKNOWN
    assert not any(row.level_index == 1 for row in await adapter.get_open_orders())
    await adapter.cancel_all()
    assert all(row.status == OrderStatus.UNKNOWN for row in await adapter.get_open_orders())


@pytest.mark.asyncio
@pytest.mark.parametrize('level', [None, -1])
async def test_unmanaged_order_is_counted_and_cancelled_before_creation(level):
    from app.risk.firewall import exposure_metrics
    adapter = PaperExecutionAdapter()
    unmanaged = o(cid='unmanaged', level=level)
    adapter.orders[unmanaged.client_order_id] = unmanaged
    exp = exposure_metrics([q()], D('0'), D('3000'), D('10'), [unmanaged])
    assert exp.bid_quantity == D('2')
    actions = await OrderManager(adapter).reconcile('ETH', [q()], D('1'), D('.01'))
    assert actions[0].action == ReconcileActionType.CANCEL
    assert unmanaged.status == OrderStatus.CANCELLED
    assert len(await adapter.get_open_orders()) == 1


@pytest.mark.asyncio
async def test_single_slot_keep_replace_preserve_overlap_and_cancellation():
    from app.risk.firewall import exposure_metrics
    from app.accounting.vault import reserved_capital
    adapter = PaperExecutionAdapter()
    original = o(cid='original', price='100')
    adapter.orders[original.client_order_id] = original
    assert (await OrderManager(adapter).reconcile('ETH', [q(price='100')], D('1'), D('.01')))[0].action == ReconcileActionType.KEEP
    exp = exposure_metrics([q(price='110')], D('0'), D('100'), D('10'), [original])
    assert exp.bid_quantity == D('1') and exp.bid_quote_notional == D('110')
    assert reserved_capital(D('0'), D('100'), [q(price='110')], [original]) == D('110')
    assert (await OrderManager(adapter).reconcile('ETH', [q(price='110')], D('1'), D('.01')))[0].action == ReconcileActionType.REPLACE
    assert original.status == OrderStatus.CANCELLED
    assert len(await adapter.get_open_orders()) == 1


@pytest.mark.asyncio
async def test_unconfirmed_surplus_cancellation_blocks_creation():
    adapter = PaperExecutionAdapter()
    adapter.orders['a'] = o(cid='a')
    adapter.orders['b'] = o(cid='b')
    async def no_confirmation(_ids): return []
    adapter.cancel_orders = no_confirmation
    with pytest.raises(RuntimeError, match='unconfirmed'):
        await OrderManager(adapter).reconcile('ETH', [q(), q(level=1)], D('1'), D('.01'))
    assert set(adapter.orders) == {'a', 'b'}


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['PAPER', 'TESTNET'])
async def test_closed_history_limit_never_evicts_active_unknown_or_verification(mode):
    from app.execution.fills import CLOSED_ORDER_LIMIT
    if mode == 'PAPER':
        adapter = PaperExecutionAdapter()
        history = adapter.orders
    else:
        adapter, _, _ = venue_adapter()
        history = adapter._orders
    active = []
    for index, status in enumerate((OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED, OrderStatus.UNKNOWN)):
        order = o(cid='active'+str(index)); order.status = status
        history[order.client_order_id] = order
        active.append(order)
    if mode == 'TESTNET':
        adapter._needs_verification.add('verification')
        pinned = o(cid='verification'); pinned.status = OrderStatus.CANCELLED
        history[pinned.client_order_id] = pinned
    for index in range(CLOSED_ORDER_LIMIT+250):
        order = o(cid='closed'+str(index)); order.status = OrderStatus.CANCELLED
        history[order.client_order_id] = order
    assert all(history[order.client_order_id] is order for order in active)
    closed = [order for order in history.values() if order.status == OrderStatus.CANCELLED]
    assert len(closed) == CLOSED_ORDER_LIMIT + (mode == 'TESTNET')
    assert 'closed0' not in history and 'closed1249' in history
    recent = adapter.recent_orders(7)
    assert all(order in recent for order in active)
    assert len([order for order in recent if order.client_order_id.startswith('closed')]) == 7
    if mode == 'TESTNET':
        assert history['verification'] is pinned
        exposure = await adapter.get_open_orders()
        assert next(order for order in exposure if order.client_order_id == 'verification').status == OrderStatus.UNKNOWN
        adapter._needs_verification.clear(); history.prune()
        assert 'verification' not in history


@pytest.mark.asyncio
async def test_testnet_duplicate_unknown_cannot_transmit_and_surplus_is_cancelled():
    adapter, venue, keeper = venue_adapter()
    venue.opened=[{'oid':123, 'coin':'ETH', 'sz':'1', 'origSz':'1'}]
    duplicate=o(cid='surplus'); duplicate.venue_order_id='456'
    duplicate.status=OrderStatus.UNKNOWN
    adapter._orders[duplicate.client_order_id]=duplicate
    with pytest.raises(RuntimeError, match='unknown'):
        await OrderManager(adapter).reconcile('ETH', [q(level=1)], D('1'), D('.01'))
    assert adapter._orders['surplus'] is duplicate and venue.transmissions == 0
    with pytest.raises(RuntimeError, match='unresolved'):
        await adapter.submit_orders([OrderRequest(client_order_id='forbidden', market='ETH', side='BID', price=D('2999'), size=D('1'))])
    await adapter.cancel_all()
    assert keeper.status == duplicate.status == OrderStatus.CANCELLED
    assert adapter._needs_verification == {'tracked', 'surplus'}
    venue.opened=[]
    venue.results['123']=venue_update('canceled', remaining='1')
    venue.results['456']=venue_update('canceled', remaining='1', oid=456)
    await adapter.reconcile_venue()
    assert not adapter.has_unknown_exposure() and not await adapter.get_open_orders()
    await adapter.submit_orders([OrderRequest(client_order_id='resolved', market='ETH', side='BID', price=D('2999'), size=D('1'))])
    assert venue.transmissions == 1


@pytest.mark.asyncio
async def test_active_order_identity_cannot_be_overwritten():
    adapter=PaperExecutionAdapter()
    old=o(cid='same-id'); adapter.orders[old.client_order_id]=old
    with pytest.raises(ValueError, match='identity'):
        await adapter.submit_orders([OrderRequest(client_order_id=old.client_order_id, market='ETH', side='ASK', price=D('3100'), size=D('2'))])
    assert adapter.orders[old.client_order_id] is old and old.status == OrderStatus.OPEN


@pytest.mark.asyncio
async def test_testnet_closed_fill_evidence_waits_for_accounting_consumption():
    from datetime import timedelta
    from app.market_data.perp_context import PerpPositionContext
    adapter, venue, _ = venue_adapter()
    adapter._orders.clear()
    adapter._orders.limit = 2
    venue.order_response={'status':'ok','response':{'data':{'statuses':[{'filled':{'oid':123}}]}}}
    await adapter.submit_orders([OrderRequest(client_order_id='filled', market='ETH', side='BID', price=D('2999'), size=D('1'))])
    filled=adapter._orders['filled']
    assert filled.status == OrderStatus.FILLED and adapter._pending_accounting == {'filled'}
    for index in range(8):
        closed=o(cid=f'closed-{index}');closed.status=OrderStatus.CANCELLED
        adapter._orders[closed.client_order_id]=closed
    assert adapter._orders['filled'] is filled and len(adapter._orders) == 3
    with pytest.raises(RuntimeError, match='accounting'):
        await adapter.submit_orders([OrderRequest(client_order_id='blocked', market='ETH', side='BID', price=D('2999'), size=D('1'))])
    old=filled.updated_at-timedelta(seconds=1)
    position=PerpPositionContext(market='ETH', signed_position_base=D('1'), source='TESTNET', updated_at=old, version=1)
    account={'account_value':D('100000'), 'updated_at':old}
    adapter.acknowledge_accounting(position, account)
    assert 'filled' in adapter._pending_accounting
    fresh=filled.updated_at+timedelta(seconds=1)
    adapter.acknowledge_accounting(position.model_copy(update={'updated_at':fresh}), {**account,'updated_at':fresh})
    assert not adapter._pending_accounting and 'filled' not in adapter._orders
    assert len(adapter._orders) == 2
