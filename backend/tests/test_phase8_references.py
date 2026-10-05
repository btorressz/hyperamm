from datetime import timedelta
from decimal import Decimal as D

import pytest

from app.config import Settings
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.perp_context import demo_perp_context
from app.references.consensus import ReferenceConsensusPolicy
from app.references.models import PriceEvidence,ProviderId,ProviderStatus,SourceType,utcnow
from app.references.providers import CoinGeckoProvider,KrakenProvider,RedStoneProvider,backoff
from app.references.service import ReferenceService


def evidence(provider,price,status=ProviderStatus.HEALTHY,source_type=SourceType.ORACLE):
    now=utcnow()
    return PriceEvidence(market="ETH",provider=provider,source_type=source_type,price=D(price) if price is not None else None,observed_at=now,source_timestamp=now if price is not None else None,healthy=status==ProviderStatus.HEALTHY,stale=status==ProviderStatus.STALE,status=status,version=1)


def test_redstone_normalization_replay_validation_and_freshness():
    p=RedStoneProvider(market="ETH",enabled=True,api_key="secret",ws_url="wss://example.invalid",data_service_id="redstone-primary-prod",feed_id="ETH",stale_after_seconds=1)
    now=utcnow()
    msg={"feedId":"ETH","type":"price","dataServiceId":"redstone-primary-prod","dataPackageId":"pkg","timestamp":int(now.timestamp()*1000),"value":"3000.25"}
    assert p.ingest(msg,observed_at=now) is True
    assert p.snapshot().price==D("3000.25")
    assert p.snapshot().source_id=="pkg"
    assert p.ingest(msg,observed_at=now+timedelta(milliseconds=1)) is False
    newer={**msg,"timestamp":int((now+timedelta(milliseconds=10)).timestamp()*1000)}
    assert p.ingest(newer,observed_at=now+timedelta(milliseconds=10)) is False
    assert p.state.version==1
    assert p.state.snapshot(now+timedelta(seconds=2)).status==ProviderStatus.STALE
    with pytest.raises(ValueError,match="wrong RedStone feed"):
        p.normalize({**msg,"feedId":"BTC"})
    with pytest.raises(ValueError,match="wrong RedStone data service"):
        p.normalize({**msg,"dataServiceId":"wrong"})
    with pytest.raises(ValueError,match="finite and positive"):
        p.normalize({**msg,"value":"NaN"})


def test_redstone_backoff_is_bounded_and_auth_errors_map_to_error():
    assert backoff(0,0)==1
    assert backoff(99,0)==30
    p=RedStoneProvider(market="ETH",enabled=True,api_key="x",ws_url="wss://x",data_service_id="redstone-primary-prod",feed_id="ETH",stale_after_seconds=1)
    assert p.auth_headers()=={"x-api-key":"x"}
    assert p.classify_connection_error(RuntimeError("HTTP 401"))==ProviderStatus.ERROR
    assert p.classify_connection_error(RuntimeError("HTTP 403"))==ProviderStatus.ERROR
    assert p.classify_connection_error(RuntimeError("HTTP 429"))==ProviderStatus.DEGRADED


def test_kraken_ticker_bbo_midpoint_and_invalid_book():
    p=KrakenProvider(market="ETH",enabled=True,symbol="ETH/USD",stale_after_seconds=5)
    now=utcnow()
    raw={"channel":"ticker","type":"snapshot","data":[{"symbol":"ETH/USD","bid":2999.5,"ask":3000.5,"timestamp":now.isoformat().replace("+00:00","Z")}]}
    assert p.ingest(raw,observed_at=now)
    assert p.snapshot().price==D("3000.0")
    sub=p.subscription()
    assert sub["params"]["event_trigger"]=="bbo" and sub["params"]["snapshot"] is True
    with pytest.raises(ValueError,match="crossed"):
        p.normalize({"channel":"ticker","data":[{"symbol":"ETH/USD","bid":3001,"ask":3000,"timestamp":now.isoformat()}]})
    with pytest.raises(ValueError,match="wrong Kraken symbol"):
        p.normalize({"channel":"ticker","data":[{"symbol":"BTC/USD","bid":1,"ask":2,"timestamp":now.isoformat()}]})


def test_coingecko_normalization_auth_headers_and_timestamp():
    demo=CoinGeckoProvider(market="ETH",enabled=True,coin_id="ethereum",api_key="k",api_base_url="https://api.coingecko.com/api/v3",poll_interval_seconds=20,stale_after_seconds=90)
    pro=CoinGeckoProvider(market="ETH",enabled=True,coin_id="ethereum",api_key="k",api_base_url="https://pro-api.coingecko.com/api/v3",poll_interval_seconds=20,stale_after_seconds=90)
    assert demo.headers()=={"x-cg-demo-api-key":"k"}
    assert pro.headers()=={"x-cg-pro-api-key":"k"}
    ts=int(utcnow().timestamp())
    price,source_ts=demo.normalize({"ethereum":{"usd":3000.1,"last_updated_at":ts}})
    assert price==D("3000.1") and int(source_ts.timestamp())==ts
    with pytest.raises(ValueError,match="last_updated_at"):
        demo.normalize({"ethereum":{"usd":3000}})


def test_consensus_roles_quorum_outlier_and_coingecko_restriction():
    policy=ReferenceConsensusPolicy()
    base={
        ProviderId.REDSTONE.value:evidence(ProviderId.REDSTONE,"3000"),
        ProviderId.HYPERLIQUID_ORACLE.value:evidence(ProviderId.HYPERLIQUID_ORACLE,"3001",source_type=SourceType.NATIVE_ORACLE),
        ProviderId.KRAKEN.value:evidence(ProviderId.KRAKEN,"3002",source_type=SourceType.VENUE_REFERENCE),
        ProviderId.COINGECKO.value:evidence(ProviderId.COINGECKO,"3001",source_type=SourceType.AGGREGATOR_REFERENCE),
    }
    c=policy.evaluate("ETH",base,agreement_bps=D("30"),outlier_bps=D("75"),version=1)
    assert c.confidence_state=="VERIFIED" and c.healthy_core_sources==3
    out=dict(base);out[ProviderId.HYPERLIQUID_ORACLE.value]=evidence(ProviderId.HYPERLIQUID_ORACLE,"3150",source_type=SourceType.NATIVE_ORACLE)
    c=policy.evaluate("ETH",out,agreement_bps=D("30"),outlier_bps=D("75"),version=2)
    assert ProviderId.HYPERLIQUID_ORACLE.value in c.outliers
    fallback=dict(base);fallback[ProviderId.REDSTONE.value]=evidence(ProviderId.REDSTONE,None,ProviderStatus.ERROR)
    c=policy.evaluate("ETH",fallback,agreement_bps=D("30"),outlier_bps=D("75"),version=3)
    assert c.confidence_state=="DEGRADED"
    weak={
        ProviderId.REDSTONE.value:evidence(ProviderId.REDSTONE,None,ProviderStatus.ERROR),
        ProviderId.HYPERLIQUID_ORACLE.value:evidence(ProviderId.HYPERLIQUID_ORACLE,None,ProviderStatus.STALE,SourceType.NATIVE_ORACLE),
        ProviderId.KRAKEN.value:evidence(ProviderId.KRAKEN,None,ProviderStatus.ERROR,SourceType.VENUE_REFERENCE),
        ProviderId.COINGECKO.value:evidence(ProviderId.COINGECKO,"3000",source_type=SourceType.AGGREGATOR_REFERENCE),
    }
    c=policy.evaluate("ETH",weak,agreement_bps=D("30"),outlier_bps=D("75"),version=4)
    assert c.confidence_state=="INSUFFICIENT"
    assert any("cannot authorize NORMAL" in reason for reason in c.reasons)


def test_demo_reference_service_labels_all_external_sources_simulated():
    settings=Settings(_env_file=None)
    service=ReferenceService(settings,market="ETH",mode=settings.market_data_mode)
    snap=MockMarketDataAdapter().snapshot_for(3)
    refs=service.snapshot(snap,demo_perp_context(snap),agreement_bps=D("30"),outlier_bps=D("75"))
    assert refs.consensus.confidence_state=="VERIFIED"
    for provider in ("REDSTONE","KRAKEN","COINGECKO"):
        assert refs.evidence[provider].simulated is True


def test_kraken_down_with_redstone_and_native_is_degraded_not_normal():
    policy=ReferenceConsensusPolicy()
    base={
        ProviderId.REDSTONE.value:evidence(ProviderId.REDSTONE,"3000"),
        ProviderId.HYPERLIQUID_ORACLE.value:evidence(ProviderId.HYPERLIQUID_ORACLE,"3001",source_type=SourceType.NATIVE_ORACLE),
        ProviderId.KRAKEN.value:evidence(ProviderId.KRAKEN,None,ProviderStatus.ERROR,SourceType.VENUE_REFERENCE),
        ProviderId.COINGECKO.value:evidence(ProviderId.COINGECKO,"3000",source_type=SourceType.AGGREGATOR_REFERENCE),
    }
    c=policy.evaluate("ETH",base,agreement_bps=D("30"),outlier_bps=D("75"),version=9)
    assert c.confidence_state=="DEGRADED"
    assert any("Kraken unavailable" in reason for reason in c.reasons)
