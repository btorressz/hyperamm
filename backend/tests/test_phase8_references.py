import asyncio
import json
from datetime import timedelta
from decimal import Decimal as D

import pytest

import app.references.providers as providers_module
from app.config import Settings
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.models import MarketDataMode
from app.market_data.perp_context import build_perp_market_context, demo_perp_context
from app.references.consensus import ReferenceConsensusPolicy
from app.references.models import PriceEvidence,ProviderId,ProviderStatus,SourceType,deviation_bps,utcnow
from app.references.providers import CoinGeckoProvider,KrakenProvider,RedStoneProvider,backoff
from app.references.service import ReferenceService


def evidence(provider,price,status=ProviderStatus.HEALTHY,source_type=SourceType.ORACLE):
    now=utcnow()
    return PriceEvidence(market="ETH",provider=provider,source_type=source_type,price=D(price) if price is not None else None,observed_at=now,source_timestamp=now if price is not None else None,healthy=status==ProviderStatus.HEALTHY,stale=status==ProviderStatus.STALE,status=status,version=1)


def redstone_provider(**overrides):
    args=dict(
        market="ETH",
        enabled=True,
        api_key="secret",
        ws_url="wss://example.invalid",
        data_service_id="redstone-primary-prod",
        feed_id="ETH",
        stale_after_seconds=1,
    )
    args.update(overrides)
    return RedStoneProvider(**args)


def redstone_price(timestamp, value="3000.25", **overrides):
    msg={
        "type":"price",
        "dataServiceId":"redstone-primary-prod",
        "dataPackageId":"ETH",
        "timestamp":int(timestamp.timestamp()*1000),
        "value":value,
    }
    msg.update(overrides)
    return msg


def test_redstone_subscription_matches_current_live_protocol():
    p=redstone_provider()
    assert p.subscription()=={
        "op":"subscribe",
        "items":[{
            "feedId":"ETH",
            "type":"price",
            "dataServiceId":"redstone-primary-prod",
        }],
    }


@pytest.mark.asyncio
async def test_redstone_incomplete_enabled_configuration_fails_without_starting_reconnect_loop():
    p=redstone_provider(api_key=None,ws_url=None,feed_id=None,data_service_id="")
    await p.start()
    snap=p.snapshot()
    assert p.task is None
    assert snap.status==ProviderStatus.ERROR
    assert "API key" in snap.error
    assert "WebSocket URL" in snap.error
    assert "feed ID" in snap.error
    assert "data service ID" in snap.error


def test_redstone_documented_price_normalization_and_source_identity():
    p=redstone_provider()
    now=utcnow().replace(microsecond=0)
    msg=redstone_price(now)
    assert p.ingest(msg,observed_at=now) is True
    snap=p.snapshot()
    assert snap.provider==ProviderId.REDSTONE
    assert snap.source_type==SourceType.ORACLE
    assert snap.price==D("3000.25")
    assert snap.source_timestamp==now
    assert snap.status==ProviderStatus.HEALTHY
    assert snap.healthy is True
    assert snap.source_id=="redstone-primary-prod:ETH"


@pytest.mark.parametrize("raw,match",[
    ('{',"malformed RedStone JSON"),
    ([],"expected JSON object"),
    ({"dataServiceId":"redstone-primary-prod","dataPackageId":"ETH","timestamp":1,"value":"3000"},"missing type"),
    ({"type":"something_else"},"wrong RedStone message type"),
])
def test_redstone_rejects_malformed_or_wrong_message_type(raw,match):
    p=redstone_provider()
    with pytest.raises(ValueError,match=match):
        p.normalize(raw)


def test_redstone_wrong_data_package_and_service_are_rejected():
    p=redstone_provider()
    now=utcnow()
    with pytest.raises(ValueError,match="wrong RedStone feed"):
        p.normalize(redstone_price(now,dataPackageId="BTC"))
    with pytest.raises(ValueError,match="wrong RedStone data service"):
        p.normalize(redstone_price(now,dataServiceId="wrong"))


@pytest.mark.parametrize("mutation,match",[
    ({"timestamp":None},""),
    ({"value":None},"invalid RedStone price"),
    ({"value":"0"},"finite and positive"),
    ({"value":"-1"},"finite and positive"),
    ({"value":"NaN"},"finite and positive"),
    ({"value":"Infinity"},"finite and positive"),
])
def test_redstone_invalid_timestamp_or_price_is_rejected(mutation,match):
    p=redstone_provider()
    now=utcnow()
    msg=redstone_price(now)
    msg.update(mutation)
    if mutation.get("timestamp","present") is None:
        with pytest.raises(ValueError):
            p.normalize(msg)
    else:
        with pytest.raises(ValueError,match=match):
            p.normalize(msg)


def test_redstone_missing_timestamp_and_value_are_rejected():
    p=redstone_provider()
    now=utcnow()
    missing_timestamp=redstone_price(now);missing_timestamp.pop("timestamp")
    missing_value=redstone_price(now);missing_value.pop("value")
    with pytest.raises(ValueError,match="missing timestamp"):
        p.normalize(missing_timestamp)
    with pytest.raises(ValueError,match="missing value"):
        p.normalize(missing_value)


def test_redstone_future_replay_and_older_timestamps_do_not_create_economic_updates():
    p=redstone_provider()
    t0=utcnow().replace(microsecond=0)
    assert p.ingest(redstone_price(t0),observed_at=t0)
    assert p.state.version==1

    assert p.ingest(redstone_price(t0),observed_at=t0+timedelta(milliseconds=10)) is False
    assert p.ingest(redstone_price(t0-timedelta(seconds=1)),observed_at=t0+timedelta(milliseconds=20)) is False
    assert p.state.version==1
    assert p.snapshot().source_timestamp==t0

    with pytest.raises(ValueError,match="too far in future"):
        p.ingest(redstone_price(t0+timedelta(seconds=6)),observed_at=t0)


def test_redstone_identical_newer_tick_refreshes_freshness_without_version_churn():
    p=redstone_provider(stale_after_seconds=2)
    t0=utcnow().replace(microsecond=0)
    t1=t0+timedelta(seconds=1)
    assert p.ingest(redstone_price(t0,value="3000.00"),observed_at=t0)
    version=p.state.version
    assert p.ingest(redstone_price(t1,value="3000.00"),observed_at=t1) is False
    assert p.state.version==version
    snap=p.state.snapshot(t1+timedelta(milliseconds=500))
    assert snap.source_timestamp==t1
    assert snap.status==ProviderStatus.HEALTHY
    assert snap.healthy is True


def test_redstone_staleness_transitions_healthy_to_stale_without_disconnect():
    p=redstone_provider(stale_after_seconds=1)
    t0=utcnow().replace(microsecond=0)
    p.ingest(redstone_price(t0),observed_at=t0)
    fresh=p.state.snapshot(t0+timedelta(milliseconds=500))
    stale=p.state.snapshot(t0+timedelta(seconds=2))
    assert fresh.status==ProviderStatus.HEALTHY and fresh.healthy is True
    assert stale.status==ProviderStatus.STALE and stale.healthy is False


def test_redstone_documented_error_frame_and_transient_error_handling():
    p=redstone_provider()
    permanent={
        "type":"error",
        "code":"TOPIC_LIMIT_EXCEEDED",
        "message":"Subscribe rejected: exceeds the 50-topic limit for this connection",
        "limit":50,
    }
    assert p.message_type(permanent)=="error"
    assert p.handle_error_frame(permanent)==ProviderStatus.ERROR
    assert p.snapshot().status==ProviderStatus.ERROR

    q=redstone_provider()
    temporary={"type":"error","code":"PROVIDER_TEMPORARY","message":"temporary provider issue"}
    assert q.handle_error_frame(temporary)==ProviderStatus.DEGRADED
    assert q.snapshot().status==ProviderStatus.DEGRADED


def test_redstone_handshake_severity_auth_rate_limit_and_error_sanitization():
    p=redstone_provider()
    assert backoff(0,0)==1
    assert backoff(99,0)==30
    assert p.auth_headers()=={"x-api-key":"secret"}
    assert p.classify_connection_error(RuntimeError("HTTP 401 unauthorized"))==ProviderStatus.ERROR
    assert p.classify_connection_error(RuntimeError("HTTP 403 forbidden"))==ProviderStatus.ERROR
    assert p.classify_connection_error(RuntimeError("HTTP 429 rate limit"))==ProviderStatus.DEGRADED
    assert p.classify_connection_error(RuntimeError("HTTP 403 connection-open rate limit"))==ProviderStatus.DEGRADED

    p.handle_error_frame({"type":"error","code":"PROVIDER_TEMPORARY","message":"temporary x-api-key: secret"})
    error=p.snapshot().error
    assert "secret" not in error
    assert "x-api-key" not in error.lower()


class FakeWebSocket:
    def __init__(self,messages,sent,on_exhausted=None):
        self.messages=list(messages);self.sent=sent;self.on_exhausted=on_exhausted
    async def __aenter__(self): return self
    async def __aexit__(self,exc_type,exc,tb): return False
    async def send(self,payload): self.sent.append(json.loads(payload))
    def __aiter__(self): return self
    async def __anext__(self):
        if self.messages:
            item=self.messages.pop(0)
            if isinstance(item,Exception): raise item
            return item
        if self.on_exhausted:self.on_exhausted()
        raise StopAsyncIteration


@pytest.mark.asyncio
async def test_redstone_reconnects_and_resubscribes_after_provider_disconnect(monkeypatch):
    sent=[]; statuses=[]
    p=None
    t0=utcnow().replace(microsecond=0)
    sockets=[
        FakeWebSocket([ConnectionError("provider recycle")],sent),
        FakeWebSocket([redstone_price(t0)],sent,on_exhausted=lambda:setattr(p,"closing",True)),
    ]
    def factory(url,headers):
        assert url=="wss://example.invalid"
        assert headers=={"x-api-key":"secret"}
        return sockets.pop(0)
    p=redstone_provider(websocket_factory=factory)

    async def no_wait(_delay):
        statuses.append(p.state.status)
    monkeypatch.setattr(providers_module.asyncio,"sleep",no_wait)

    await p._run()
    assert sent==[p.subscription(),p.subscription()]
    assert ProviderStatus.DEGRADED in statuses
    assert p.snapshot().status==ProviderStatus.HEALTHY
    assert p.snapshot().price==D("3000.25")


def test_redstone_price_evidence_never_contains_api_key():
    p=redstone_provider()
    now=utcnow().replace(microsecond=0)
    p.ingest(redstone_price(now),observed_at=now)
    serialized=str(p.snapshot().model_dump())
    assert "secret" not in serialized
    assert "x-api-key" not in serialized.lower()


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


def test_corrected_redstone_parser_flows_through_reference_service_and_consensus():
    settings=Settings(
        _env_file=None,
        market="ETH",
        market_data_mode="LIVE",
        redstone_enabled=True,
        redstone_api_key="secret",
        redstone_live_ws_url="wss://example.invalid",
        redstone_feed_id="ETH",
        redstone_data_service_id="redstone-primary-prod",
        kraken_reference_enabled=True,
        kraken_symbol="ETH/USD",
        coingecko_reference_enabled=False,
    )
    service=ReferenceService(settings,market="ETH",mode=MarketDataMode.LIVE)
    base=MockMarketDataAdapter(start_price=D("3000")).snapshot_for(0)
    now=utcnow().replace(microsecond=0)
    snap=base.model_copy(update={
        "mode":MarketDataMode.LIVE,
        "simulated":False,
        "latest_valid_update":now,
        "book":base.book.model_copy(update={"timestamp":now}),
    })
    perp=build_perp_market_context(
        market="ETH",
        market_mid=snap.mid_price,
        provider_mid_price=snap.mid_price,
        mark_price=D("3001"),
        oracle_price=D("3001"),
        funding_rate=D("0"),
        open_interest_base=D("100"),
        premium=D("0"),
        updated_at=now,
        source="HYPERLIQUID",
        simulated=False,
        version=1,
    )
    assert service.redstone.ingest(redstone_price(now,value="3000"),observed_at=now)
    assert service.kraken.ingest({
        "channel":"ticker",
        "type":"snapshot",
        "data":[{"symbol":"ETH/USD","bid":3001,"ask":3003,"timestamp":now.isoformat().replace("+00:00","Z")}],
    },observed_at=now)

    refs=service.snapshot(snap,perp,agreement_bps=D("30"),outlier_bps=D("75"))
    redstone=refs.evidence[ProviderId.REDSTONE.value]
    assert redstone.status==ProviderStatus.HEALTHY
    assert redstone.price==D("3000")
    assert redstone.source_id=="redstone-primary-prod:ETH"
    assert refs.consensus.primary_oracle_price==D("3000")
    assert refs.consensus.native_oracle_price==D("3001")
    assert refs.consensus.exchange_reference_price==D("3002")
    assert refs.consensus.confidence_state=="VERIFIED"


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


def test_exact_signed_deviation_examples():
    assert deviation_bps(D("3003"),D("3000"))==D("10")
    assert deviation_bps(D("2997"),D("3000"))==D("-10")
    assert deviation_bps(D("3000"),D("3000"))==D("0")
