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
