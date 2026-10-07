from decimal import Decimal as D

import pytest

from app.config import Settings
from app.execution.models import OrderRequest
from app.market_data.mock import MockMarketDataAdapter
from app.references.models import PriceEvidence,ProviderId,ProviderStatus,ReferenceConsensus,ReferenceSnapshot,SourceType,utcnow
from app.risk.authorization import authorize
from app.runtime import HyperAmmRuntime


def insufficient_refs(market="ETH",version=99):
    now=utcnow();evidence={}
    for provider,stype in [
        (ProviderId.REDSTONE,SourceType.ORACLE),
        (ProviderId.HYPERLIQUID_ORACLE,SourceType.NATIVE_ORACLE),
        (ProviderId.KRAKEN,SourceType.VENUE_REFERENCE),
        (ProviderId.COINGECKO,SourceType.AGGREGATOR_REFERENCE),
        (ProviderId.HYPERLIQUID_MID,SourceType.EXECUTION_VENUE),
        (ProviderId.HYPERLIQUID_MARK,SourceType.PERP_MARK),
    ]:
        evidence[provider.value]=PriceEvidence(market=market,provider=provider,source_type=stype,observed_at=now,status=ProviderStatus.ERROR,healthy=False,version=version,error="fixture outage")
    consensus=ReferenceConsensus(market=market,healthy_sources=0,healthy_core_sources=0,confidence_state="INSUFFICIENT",source_statuses={k:"ERROR" for k in evidence},reasons=["fixture quorum lost"],version=version,updated_at=now)
    return ReferenceSnapshot(market=market,evidence=evidence,consensus=consensus,deviations_bps={"hl_mid_consensus":None,"hl_mark_consensus":None,"hl_oracle_consensus":None},deviation_magnitudes_bps={"hl_mid_consensus":None,"hl_mark_consensus":None,"hl_oracle_consensus":None},version=version,updated_at=now)


async def prepared_runtime(counter=3):
    rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(counter)
    await rt.market._accept(snap)
    await rt.refresh_once()
    return rt,snap


@pytest.mark.asyncio
async def test_demo_paper_runtime_builds_simulated_agent_authority():
    rt,_=await prepared_runtime()
    assert rt.agent_evidence is not None and rt.agent_evidence.simulated is True
    assert rt.agent_decision is not None and rt.agent_decision.simulated is True
    assert rt.authorization.agent_version==rt.agent_decision.version
    assert rt.authorization.agent_fingerprint==rt.agent_decision.fingerprint
    assert rt.risk.kill_switch_active is False


@pytest.mark.asyncio
async def test_phase8_halt_overrides_supervisory_agents(monkeypatch):
    rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    monkeypatch.setattr(rt.reference_service,"snapshot",lambda *args,**kwargs:insufficient_refs())
    await rt.refresh_once()
    assert rt.agent_decision is not None
    assert rt.risk_decision.state.value=="HALT"
    assert rt.quotes==[]
    assert rt.authorization.authorized is False
    assert rt.risk.kill_switch_active is False


@pytest.mark.asyncio
async def test_phase8_projected_exposure_uses_post_agent_candidate(monkeypatch):
    rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(12)
    await rt.market._accept(snap)
    original=rt.agent_supervisor.evaluate
    def cautious(**kwargs):
        d=original(**kwargs)
        changed=d.model_copy(update={"spread_multiplier":D("1.2"),"bid_size_multiplier":D(".5"),"ask_size_multiplier":D(".5"),"version":d.version+1,"fingerprint":"cautious-agent"})
        rt.agent_supervisor.version=changed.version
        rt.agent_supervisor.fingerprint=changed.fingerprint
        return changed
    monkeypatch.setattr(rt.agent_supervisor,"evaluate",cautious)
    await rt.refresh_once()
    base_bid=sum((q.size for q in rt.strategy_quotes if q.side=="BID"),D("0"))
    agent_bid=sum((q.size for q in rt.agent_quotes if q.side=="BID"),D("0"))
    assert agent_bid<=base_bid
    assert rt.risk_decision.exposure.bid_quantity==agent_bid


@pytest.mark.asyncio
async def test_agent_version_change_rejects_create_before_transmission():
    rt,_=await prepared_runtime()
    rt.strategy.running=True
    rt.agent_supervisor.version+=1
    async with rt.execution_lock:
        with pytest.raises(RuntimeError,match="agent decision changed"):
            await rt.orders.reconcile_locked(rt.config.market,rt.quotes,rt.config.replace_tolerance_bps,rt.config.size_tolerance)
    assert rt.paper.all_orders()==[]


@pytest.mark.asyncio
async def test_agent_version_change_rejects_replace_before_new_submission():
    rt,_=await prepared_runtime()
    desired=next(q for q in rt.quotes if q.side=="BID" and q.level_index==0)
    old=OrderRequest(client_order_id="old",market=rt.config.market,side="BID",price=desired.price-D("10"),size=desired.size,level_index=0)
    await rt.paper.submit_orders([old])
    rt.strategy.running=True
    rt.agent_supervisor.version+=1
    async with rt.execution_lock:
        with pytest.raises(RuntimeError,match="agent decision changed"):
            await rt.orders.reconcile_locked(rt.config.market,[desired],rt.config.replace_tolerance_bps,rt.config.size_tolerance)
    assert not any(o.client_order_id!="old" for o in rt.paper.all_orders())


@pytest.mark.asyncio
async def test_agent_fingerprint_change_rejects_old_authority():
    rt,_=await prepared_runtime()
    rt.strategy.running=True
    rt.agent_supervisor.fingerprint="materially-different-agent"
    with pytest.raises(RuntimeError,match="agent fingerprint changed"):
        await rt._execution_authority()


@pytest.mark.asyncio
async def test_same_quotes_different_material_agent_decision_changes_authorization():
    rt,_=await prepared_runtime()
    a1=rt.authorization
    changed=rt.agent_decision.model_copy(update={"version":rt.agent_decision.version+1,"fingerprint":"changed-agent-decision"})
    a2=authorize(rt.quotes,rt.references,rt.risk_decision,changed)
    assert a2.quote_fingerprint==a1.quote_fingerprint
    assert a2.agent_fingerprint!=a1.agent_fingerprint
    assert a2.authorization_fingerprint!=a1.authorization_fingerprint


@pytest.mark.asyncio
async def test_unchanged_agent_decision_has_stable_authorization_fingerprint():
    rt,_=await prepared_runtime()
    a1=authorize(rt.quotes,rt.references,rt.risk_decision,rt.agent_decision)
    a2=authorize(rt.quotes,rt.references,rt.risk_decision,rt.agent_decision)
    assert a1.agent_fingerprint==a2.agent_fingerprint
    assert a1.authorization_fingerprint==a2.authorization_fingerprint


@pytest.mark.asyncio
async def test_manual_kill_remains_absolute_with_agents_enabled():
    rt,snap=await prepared_runtime()
    await rt.activate_kill()
    assert rt.risk.kill_switch_active is True
    await rt.market._accept(snap)
    await rt.refresh_once()
    assert rt.risk.kill_switch_active is True
    assert rt.strategy.running is False
    assert rt.quotes==[]


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_name",["regime","toxic_flow","execution_quality"])
async def test_agent_software_error_remains_neutral_while_phase8_still_halts(monkeypatch,agent_name):
    rt=HyperAmmRuntime(Settings(_env_file=None))
    snap=MockMarketDataAdapter().snapshot_for(1)
    await rt.market._accept(snap)
    monkeypatch.setattr(rt.reference_service,"snapshot",lambda *args,**kwargs:insufficient_refs())
    monkeypatch.setattr(getattr(rt.agent_supervisor,agent_name),"evaluate",lambda *_:(_ for _ in ()).throw(RuntimeError("agent failure")))
    await rt.refresh_once()
    failed=getattr(rt.agent_decision,agent_name)
    assert failed.health.value=="ERROR"
    assert failed.spread_multiplier==1
    assert failed.bid_size_multiplier==failed.ask_size_multiplier==1
    assert rt.risk_decision.state.value=="HALT"
    assert rt.authorization.authorized is False
    assert rt.quotes==[]

    # A neutral ERROR cannot mint execution authority while Phase 8 denies it.
    rt.strategy.running=True
    with pytest.raises(PermissionError,match="Phase 8 FinalQuoteAuthorization"):
        await rt._execution_authority()
    assert rt.paper.all_orders()==[]
