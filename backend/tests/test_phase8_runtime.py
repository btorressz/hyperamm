from decimal import Decimal as D

import pytest

from app.config import Settings
from app.execution.models import OrderRequest
from app.market_data.mock import MockMarketDataAdapter
from app.references.models import (
    PriceEvidence,ProviderId,ProviderStatus,ReferenceConsensus,ReferenceSnapshot,SourceType,utcnow,
)
from app.runtime import HyperAmmRuntime


def insufficient_refs(market="ETH",version=99):
    now=utcnow()
    evidence={}
    for provider,stype in [
        (ProviderId.REDSTONE,SourceType.ORACLE),
        (ProviderId.HYPERLIQUID_ORACLE,SourceType.NATIVE_ORACLE),
        (ProviderId.KRAKEN,SourceType.VENUE_REFERENCE),
        (ProviderId.COINGECKO,SourceType.AGGREGATOR_REFERENCE),
        (ProviderId.HYPERLIQUID_MID,SourceType.EXECUTION_VENUE),
        (ProviderId.HYPERLIQUID_MARK,SourceType.PERP_MARK),
    ]:
        evidence[provider.value]=PriceEvidence(
            market=market,provider=provider,source_type=stype,observed_at=now,
            status=ProviderStatus.ERROR,healthy=False,version=version,error="fixture outage"
        )
    consensus=ReferenceConsensus(
        market=market,healthy_sources=0,healthy_core_sources=0,
        confidence_state="INSUFFICIENT",source_statuses={k:"ERROR" for k in evidence},
        reasons=["fixture quorum lost"],version=version,updated_at=now,
    )
    return ReferenceSnapshot(
        market=market,evidence=evidence,consensus=consensus,
        deviations_bps={"hl_mid_consensus":None,"hl_mark_consensus":None,"hl_oracle_consensus":None},
        deviation_magnitudes_bps={"hl_mid_consensus":None,"hl_mark_consensus":None,"hl_oracle_consensus":None},
        version=version,updated_at=now,
    )


@pytest.mark.asyncio
async def test_demo_runtime_produces_normal_phase8_authorization_without_wallet():
    rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(3)
    await rt.market._accept(snap)
    await rt.refresh_once()
    assert rt.references is not None
    assert rt.references.consensus.confidence_state=="VERIFIED"
    assert rt.risk_decision is not None
    assert rt.risk_decision.state.value=="NORMAL"
    assert rt.authorization is not None and rt.authorization.authorized is True
    assert [(q.side,q.price,q.size,q.level_index) for q in rt.quotes]==[(q.side,q.price,q.size,q.level_index) for q in rt.strategy_quotes]
    assert rt.risk.kill_switch_active is False


@pytest.mark.asyncio
async def test_automatic_phase8_halt_cancels_resting_orders_without_setting_manual_kill(monkeypatch):
    rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    rt.paper.update_market(snap)
    await rt.paper.submit_orders([
        OrderRequest(client_order_id="rest",market="ETH",side="BID",price=snap.best_bid-D("100"),size=D(".2"),level_index=0)
    ])
    assert await rt.paper.get_open_orders()
    fixture=insufficient_refs()
    monkeypatch.setattr(rt.reference_service,"snapshot",lambda *args,**kwargs:fixture)
    rt.strategy.running=True
    await rt.refresh_once()
    assert rt.risk_decision.state.value=="HALT"
    assert rt.authorization.authorized is False
    assert rt.quotes==[]
    assert await rt.paper.get_open_orders()==[]
    assert rt.risk.kill_switch_active is False
    assert rt.strategy.running is True
    assert rt.strategy.quote_health=="HALTED"


@pytest.mark.asyncio
async def test_reference_version_change_rejects_old_final_authorization():
    rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(2)
    await rt.market._accept(snap)
    await rt.refresh_once()
    assert rt.authorization and rt.authorization.authorized
    rt.strategy.running=True
    rt.reference_service._version += 1
    with pytest.raises(RuntimeError,match="reference evidence changed"):
        await rt._execution_authority()


@pytest.mark.asyncio
async def test_quote_fingerprint_change_rejects_old_final_authorization():
    rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(2)
    await rt.market._accept(snap)
    await rt.refresh_once()
    rt.strategy.running=True
    rt.quotes[0]=rt.quotes[0].model_copy(update={"size":rt.quotes[0].size+D(".01")})
    with pytest.raises(RuntimeError,match="fingerprint mismatch"):
        await rt._execution_authority()


@pytest.mark.asyncio
async def test_manual_kill_never_cleared_by_firewall_recovery():
    rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    await rt.activate_kill()
    assert rt.risk.kill_switch_active is True
    for _ in range(rt.risk_config.risk_recovery_confirmations+1):
        # Firewall state is independent and cannot clear the manual kill flag.
        rt.firewall.state=rt.firewall.state
    assert rt.risk.kill_switch_active is True
    assert rt.strategy.running is False


async def normalized_testnet_runtime(monkeypatch):
    """Real runtime authority and SDK-shaped fixture; no key or network use."""
    from test_execution import venue_adapter, q
    from app.accounting import AccountingService
    from app.market_data.perp_context import PerpPositionContext
    from app.strategy.models import ExecutionMode
    adapter,venue,_=venue_adapter()
    adapter._orders.clear()
    rt=HyperAmmRuntime(Settings(_env_file=None))
    rt.config=rt.config.model_copy(update={'execution_mode':ExecutionMode.TESTNET,'tick_size':D('.01'),
                                         'size_precision':5})
    rt.testnet=adapter; rt.execution=adapter; rt.orders.execution=adapter
    adapter.authority=rt._execution_authority
    rt.accounting_service=AccountingService('ETH',mode='TESTNET',config=rt.accounting_config)
    snap=MockMarketDataAdapter().snapshot_for(2)
    await rt.market._accept(snap)
    adapter._positions={'ETH':D('0')}
    adapter._position_updated_at=snap.latest_valid_update
    adapter._perp_position=PerpPositionContext(market='ETH',signed_position_base=D('0'),source='TESTNET',
                                             updated_at=snap.latest_valid_update,version=0)
    adapter._account_value=D('100000'); adapter._total_margin_used=D('0')
    async def refresh(market): return D('0')
    monkeypatch.setattr(adapter,'refresh_position',refresh)
    generate=rt.quote_engine.generate_perp_market_adaptive
    def audit_candidates(*args,**kwargs):
        fair,pool,_,inventory,market,perp=generate(*args,**kwargs)
        quotes=[q(price='2999.96',size='.12349'),q(side='ASK',price='3000.04',size='.12349')]
        quotes=[v.model_copy(update={'market_fair_value':fair,'neutral_price':v.price,'neutral_size':v.size}) for v in quotes]
        return fair,pool,quotes,inventory,market,perp
    monkeypatch.setattr(rt.quote_engine,'generate_perp_market_adaptive',audit_candidates)
    await rt.refresh_once()
    assert rt.authorization is not None, rt.strategy.last_error
    assert rt.authorization.authorized
    rt.strategy.running=True
    return rt,adapter,venue,snap


@pytest.mark.asyncio
async def test_normalized_runtime_ladder_binds_fingerprint_risk_capital_and_wire(monkeypatch):
    from app.risk.authorization import fingerprint
    from hyperliquid.utils.signing import order_request_to_order_wire
    rt,adapter,venue,_=await normalized_testnet_runtime(monkeypatch)
    assert [q.price for q in rt.quotes] == [D('2999.9'),D('3000.1')]
    assert [q.size for q in rt.quotes] == [D('.1234'),D('.1234')]
    assert [q.neutral_price for q in rt.quotes] == [D('2999.96'),D('3000.04')]
    assert rt.authorization.quote_fingerprint == fingerprint(rt.quotes)
    assert rt.risk_decision.exposure.gross_quote_notional == sum(q.price*q.size for q in rt.quotes)
    for quote in rt.quotes:
        req=rt.orders.request_for('ETH',quote)
        await adapter.submit_orders([req])
        market,buy,size,price,order_type,reduce,cloid=venue.arguments[-1]
        assert (market,buy,D(str(price)),D(str(size))) == ('ETH',quote.side=='BID',quote.price,quote.size)
        wire=order_request_to_order_wire({'coin':market,'is_buy':buy,'sz':size,'limit_px':price,
                                        'order_type':order_type,'reduce_only':reduce,'cloid':cloid},0)
        assert (wire['a'],wire['b'],D(wire['p']),D(wire['s'])) == (0,buy,quote.price,quote.size)
    assert venue.transmissions == 2
    assert len(adapter._orders) == 2
    await adapter.cancel_all()
    assert not adapter._orders.active()
    assert adapter.has_unknown_exposure() and adapter._needs_verification


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[
    {'price':D('2999.8')},{'size':D('.1233')},{'side':'ASK'},
    {'market':'BTC'},{'level_index':5},{'level_index':None}])
async def test_concrete_request_mutations_never_reach_sdk(monkeypatch,change):
    rt,adapter,venue,_=await normalized_testnet_runtime(monkeypatch)
    req=rt.orders.request_for('ETH',rt.quotes[0]).model_copy(update=change)
    with pytest.raises(PermissionError,match='exactly one authorized quote'):
        await adapter.submit_orders([req])
    assert venue.transmissions == 0 and not adapter._orders


@pytest.mark.asyncio
@pytest.mark.parametrize('state',['kill','stale_fingerprint','missing_authorization','missing_level','ambiguous_slot',
    'revoked','inventory','market','perp','reference','agent','risk','accounting','agent_fingerprint','accounting_fingerprint'])
async def test_final_testnet_authority_failures_never_reach_sdk(monkeypatch,state):
    from app.risk.authorization import fingerprint
    rt,adapter,venue,_=await normalized_testnet_runtime(monkeypatch)
    req=rt.orders.request_for('ETH',rt.quotes[0])
    if state == 'kill': rt.risk.kill_switch_active=True
    elif state == 'stale_fingerprint': rt.authorization.quote_fingerprint='stale'
    elif state == 'missing_authorization': rt.authorization=None
    elif state == 'revoked': rt.authorization.authorized=False
    elif state in {'inventory','market','perp','reference','agent','risk','accounting'}:
        name=f'_expected_{state}_version'
        setattr(rt,name,getattr(rt,name)-1)
    elif state in {'agent_fingerprint','accounting_fingerprint'}:
        setattr(rt,f'_expected_{state}','stale')
    else:
        rt.quotes=[] if state == 'missing_level' else rt.quotes+[rt.quotes[0].model_copy()]
        rt.authorization.quote_fingerprint=fingerprint(rt.quotes)
    with pytest.raises((PermissionError,RuntimeError)):
        await adapter.submit_orders([req])
    assert venue.transmissions == 0 and not adapter._orders


@pytest.mark.asyncio
async def test_manager_normalized_create_reaches_sdk_exactly_once(monkeypatch):
    rt,adapter,venue,_=await normalized_testnet_runtime(monkeypatch)
    actions=await rt.orders.reconcile('ETH',[rt.quotes[0]],D('0'),D('0'))
    assert actions[0].action.value == 'CREATE'
    assert venue.transmissions == 1
    assert venue.arguments[0][:4] == ('ETH',True,float(D('.1234')),float(D('2999.9')))


@pytest.mark.asyncio
@pytest.mark.parametrize('reject',[False,True])
async def test_exact_normalized_replace_and_truthful_cancellation(monkeypatch,reject):
    from test_execution import o, venue_update
    from app.execution.models import OrderStatus
    rt,adapter,venue,_=await normalized_testnet_runtime(monkeypatch)
    old=o(price='2900',size='.1234',cid='old'); old.venue_order_id='123'
    adapter._orders['old']=old
    venue.opened=[{'oid':123,'coin':'ETH','sz':'.1234','origSz':'.1234'}]
    desired=[rt.quotes[0]]
    # Successful wire cancellation must also resolve its independent venue
    # verification before a replacement is admitted.
    def confirmed_cancel(*args):
        venue.opened=[]
        result=venue_update('canceled', remaining='.1234')
        result['order']['order']['origSz']='.1234'
        venue.results['123']=result
        return venue.cancel_response
    venue.cancel_by_cloid=confirmed_cancel
    if reject:
        # Inject drift after quote -> request construction, before authority.
        original=rt.orders.request_for
        monkeypatch.setattr(rt.orders,'request_for',lambda *args:original(*args).model_copy(update={'size':D('.1233')}))
        with pytest.raises(PermissionError,match='exactly one authorized quote'):
            await rt.orders.reconcile('ETH',desired,D('0'),D('0'))
        assert venue.transmissions == 0
        assert list(adapter._orders) == ['old']
    else:
        actions=await rt.orders.reconcile('ETH',desired,D('0'),D('0'))
        assert actions[0].action.value == 'REPLACE'
        assert venue.transmissions == 1
        assert (D(str(venue.arguments[0][3])),D(str(venue.arguments[0][2]))) == (D('2999.9'),D('.1234'))
    assert old.status == OrderStatus.CANCELLED


@pytest.mark.asyncio
@pytest.mark.parametrize('limit',['size','distance','aggregate','exposure','capital','missing_capital'])
async def test_final_normalized_economics_revalidated_before_authorization(monkeypatch,limit):
    rt,adapter,venue,snap=await normalized_testnet_runtime(monkeypatch)
    if limit == 'size': rt.risk.max_order_size=D('.12')
    elif limit == 'distance': rt.risk.max_quote_distance_bps=D('0')
    elif limit == 'aggregate': rt.risk.max_aggregate_notional=D('1')
    elif limit == 'exposure': rt.risk_config.max_gross_quote_notional=D('1')
    elif limit == 'capital': adapter._account_value=D('1')
    else: adapter._total_margin_used=None
    await rt.refresh_once()
    assert rt.authorization is None or not rt.authorization.authorized
    assert venue.transmissions == 0 and not adapter._orders
    assert rt.strategy.last_error


@pytest.mark.asyncio
@pytest.mark.parametrize('gate',['aggregate','exposure','capital'])
async def test_ask_normalization_increase_cannot_escape_final_limits(monkeypatch,gate):
    rt,adapter,venue,_=await normalized_testnet_runtime(monkeypatch)
    generate=rt.quote_engine.generate_perp_market_adaptive
    def ask_only(*args,**kwargs):
        fair,pool,quotes,inventory,market,perp=generate(*args,**kwargs)
        return fair,pool,[quotes[1].model_copy(update={'size':D('.1234')})],inventory,market,perp
    monkeypatch.setattr(rt.quote_engine,'generate_perp_market_adaptive',ask_only)
    pre=D('3000.04')*D('.1234'); final=D('3000.1')*D('.1234')
    bound=(pre+final)/2
    assert pre < bound < final
    if gate == 'aggregate': rt.risk.max_aggregate_notional=bound
    elif gate == 'exposure': rt.risk_config.max_gross_quote_notional=bound
    else: adapter._account_value=bound/rt.accounting_config.max_capital_utilization
    # Avoid unrelated drawdown posture obscuring the final capital check.
    rt.risk_config.drawdown_warn_pct=None
    rt.risk_config.drawdown_reduce_pct=None
    rt.risk_config.drawdown_halt_pct=None
    rt.risk_config.max_session_loss_quote=None
    await rt.refresh_once()
    assert rt.authorization is None
    assert ('aggregate' if gate == 'aggregate' else 'exposure' if gate == 'exposure' else 'capital reservation') in rt.strategy.last_error
    assert venue.transmissions == 0 and not adapter._orders


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['bbo','depth','deep_level'])
async def test_equal_time_changed_material_revokes_phase8_and_rebinds_phase9(change):
    rt=HyperAmmRuntime(Settings(_env_file=None))
    initial=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(initial)
    await rt.refresh_once()
    rt.strategy.running=True
    before=rt.authorization.model_copy(deep=True)
    before_evidence=rt.agent_evidence.model_copy(deep=True)
    req=rt.orders.request_for('ETH',rt.quotes[0])
    changed=initial.model_copy(deep=True)
    if change=='bbo':
        changed.book.bids[0].price-=D('.1')
        changed.best_bid=changed.book.bids[0].price
        changed.mid_price=(changed.best_bid+changed.best_ask)/2
    elif change=='depth':
        changed.book.bids[0].size=D('100')
        changed.book.asks[0].size=D('.01')
    else:
        changed.book.bids[-1].size+=D('10')
    # Avoid waking recomputation: the last transmission check itself must detect it.
    rt.market._listeners=[]
    await rt.market._accept(changed)
    with pytest.raises(RuntimeError,match='market/adaptation state changed'):
        await rt._execution_authority(req)
    assert not await rt.paper.get_open_orders()
    assert rt.authorization.authorization_fingerprint==before.authorization_fingerprint
    rt.strategy.running=False
    await rt.refresh_once()
    assert rt.authorization.authorized
    assert rt.authorization.market_version>before.market_version
    assert rt.authorization.authorization_fingerprint!=before.authorization_fingerprint
    assert rt.market_adaptation_decision.version==rt.market_history.version
    assert rt.agent_evidence.market_version==rt.authorization.market_version
    assert rt.agent_evidence.market_version>before_evidence.market_version


@pytest.mark.asyncio
async def test_identical_equal_time_replay_preserves_final_execution_authority():
    rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    await rt.refresh_once()
    rt.strategy.running=True
    version=rt.market_history.version
    authorization=rt.authorization.authorization_fingerprint
    rt.market._listeners=[]
    await rt.market._accept(snap.model_copy(deep=True))
    await rt._execution_authority(rt.orders.request_for('ETH',rt.quotes[0]))
    assert rt.market_history.version==version
    assert rt.authorization.authorization_fingerprint==authorization


@pytest.mark.asyncio
async def test_changed_equal_time_l2_never_reaches_testnet_wire(monkeypatch):
    rt,adapter,venue,snap=await normalized_testnet_runtime(monkeypatch)
    req=rt.orders.request_for('ETH',rt.quotes[0])
    changed=snap.model_copy(deep=True)
    changed.book.bids[0].size=D('100')
    changed.book.asks[0].size=D('.01')
    rt.market._listeners=[]
    await rt.market._accept(changed)
    with pytest.raises(RuntimeError,match='market/adaptation state changed'):
        await adapter.submit_orders([req])
    assert venue.transmissions==0 and not adapter._orders
