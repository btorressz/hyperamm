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
        if isinstance(self.order_response,Exception): raise self.order_response
        return self.order_response
    def cancel_by_cloid(self,*args): return self.cancel_response


def venue_adapter():
    venue=VenueFixture()
    adapter=HyperliquidTestnetExecutionAdapter(enabled=True,private_key='fixture-only',account_address='fixture-account',
        base_url='https://api.hyperliquid-testnet.xyz',venue_info=venue,exchange=venue)
    venue.info=venue
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
    assert not await adapter.get_open_orders()
    before=order.model_copy(deep=True)
    await adapter.reconcile_venue()
    assert order==before


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
    assert not await adapter.get_open_orders()


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
    assert not await adapter.get_open_orders()


@pytest.mark.asyncio
async def test_final_authority_check_after_sdk_setup_blocks_transmission():
    adapter,venue,order=venue_adapter()
    async def denied(): raise PermissionError('kill switch is active')
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
    assert not await adapter.get_open_orders()
