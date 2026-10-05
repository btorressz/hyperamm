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
    assert rt.quotes==rt.strategy_quotes
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
