"""Deterministic transport acceptance; all external responses here are mocked."""
import asyncio
from datetime import timedelta
from decimal import Decimal as D

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.models import MarketDataMode
from app.market_data.perp_context import demo_perp_context
from app.references.consensus import CORE, ReferenceConsensusPolicy
from app.references.models import ProviderId, ProviderStatus, ReferenceTransport, SourceType, TransportQuality, utcnow
from app.references.providers import RedStonePublicHttpTransport
from app.references.service import ReferenceService
from app.runtime import HyperAmmRuntime
from test_phase8_references import evidence, redstone_price, redstone_provider
from test_phase8_risk_firewall import evaluate, refs
from app.risk.firewall import RiskFirewall, RiskFirewallConfig, RiskState


def record(now=None, **overrides):
    now=now or utcnow().replace(microsecond=0)
    item={"symbol":"ETH", "value":"3000.25", "timestamp":int(now.timestamp()*1000)}
    item.update(overrides)
    return [item]


def transport(**overrides):
    args=dict(market="ETH",enabled=True,symbol="ETH",url="https://api.redstone.finance/prices")
    args.update(overrides)
    return RedStonePublicHttpTransport(**args)


def provider(**overrides):
    return redstone_provider(public_http_fallback_enabled=True,**overrides)


def test_http_normalizes_minimal_documented_record_and_provider_age():
    p=transport()
    now=utcnow().replace(microsecond=0)
    p.ingest(record(now-timedelta(seconds=7)),observed_at=now)
    e=p.snapshot(now)
    assert e.price==D("3000.25")
    assert e.source_timestamp==now-timedelta(seconds=7)
    assert e.observed_at==now and e.age_ms==7000
    assert e.provider==ProviderId.REDSTONE and e.source_type==SourceType.ORACLE
    assert e.source_id=="redstone-public-http:ETH"
    assert e.transport==ReferenceTransport.PUBLIC_HTTP
    assert e.transport_quality==TransportQuality.FALLBACK
    assert e.healthy and e.status==ProviderStatus.HEALTHY and not e.simulated


@pytest.mark.parametrize("payload",[
    [], {}, [None], ["price"], [{"symbol":"BTC","value":3000,"timestamp":1712345678000}],
    [{"timestamp":1712345678000}], [{"value":3000}],
    *[record(value=v) for v in [None,0,-1,"NaN","Infinity",True]],
    *[record(timestamp=t) for t in [None,"invalid",0,-1,True,"NaN","Infinity",1e100]],
])
def test_http_rejects_invalid_payloads(payload):
    with pytest.raises(ValueError): transport().ingest(payload)


def test_http_symbol_optional_legacy_fields_ignored_and_latest_selected():
    p=transport()
    now=utcnow().replace(microsecond=0)
    latest=record(now,provider="unused",signature="unused",source="unused")[0]
    latest.pop("symbol")
    p.ingest([latest,record(now-timedelta(seconds=1),value="2999")[0]],observed_at=now)
    assert p.snapshot(now).price==D("3000.25")


def test_http_rejects_future_and_regressed_or_conflicting_records():
    p=transport(); now=utcnow().replace(microsecond=0)
    with pytest.raises(ValueError,match="future"):
        p.ingest(record(now+timedelta(milliseconds=1)),observed_at=now)
    p.ingest(record(now),observed_at=now)
    with pytest.raises(ValueError,match="regressed"):
        p.ingest(record(now-timedelta(seconds=1)),observed_at=now)
    with pytest.raises(ValueError,match="conflicting replay"):
        p.ingest(record(now,value="3100"),observed_at=now)
    assert p.snapshot(now).price==D("3000.25")


def test_http_repeated_cache_record_recovers_without_rejuvenating_timestamp():
    p=transport(); now=utcnow().replace(microsecond=0)
    p.ingest(record(now),observed_at=now)
    v=p.state.version
    assert p.ingest(record(now),observed_at=now+timedelta(seconds=1)) is False
    assert p.state.version==v
    p.state.set_status(ProviderStatus.DEGRADED,"network failure")
    p.ingest(record(now),observed_at=now+timedelta(seconds=2))
    assert p.snapshot(now+timedelta(seconds=2)).healthy
    assert p.snapshot(now+timedelta(seconds=2)).age_ms==2000
    p.ingest(record(now),observed_at=now+timedelta(seconds=31))
    assert p.snapshot(now+timedelta(seconds=31)).status==ProviderStatus.STALE
    assert not p.snapshot(now+timedelta(seconds=31)).healthy


def test_http_repeated_submaterial_record_is_valid_without_economic_churn():
    p=transport(); now=utcnow().replace(microsecond=0)
    p.ingest(record(now,value="3000"),observed_at=now)
    version=p.state.version
    newer=now+timedelta(seconds=1)
    p.ingest(record(newer,value="3000.01"),observed_at=newer)
    p.ingest(record(newer,value="3000.01"),observed_at=newer+timedelta(seconds=1))
    assert p.snapshot(newer+timedelta(seconds=1)).healthy
    assert p.state.version==version and p.state.latest.source_timestamp==newer


def test_http_retry_delay_preserves_configured_slow_polling():
    p=transport(poll_interval_seconds=600)
    assert p.retry_delay()==600
    p.failures=8
    assert p.retry_delay()==600


@pytest.mark.asyncio
async def test_http_request_uses_no_auth_and_preserves_decimal_precision():
    requests=[]; now=utcnow().replace(microsecond=0)
    def respond(req):
        requests.append(req)
        return httpx.Response(200,text='[{"symbol":"ETH","value":3000.1234567890123456789,"timestamp":'+str(int(now.timestamp()*1000))+'}]')
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        p=transport(client=client)
        assert await p.poll_once()
        assert p.snapshot().price==D("3000.1234567890123456789")
        request=requests[0]
        assert dict(request.url.params)=={"symbol":"ETH","provider":"redstone","limit":"1"}
        assert "x-api-key" not in request.headers and "authorization" not in request.headers
        assert not p.snapshot().simulated


@pytest.mark.asyncio
@pytest.mark.parametrize("code,status",[(400,"ERROR"),(403,"ERROR"),(429,"DEGRADED"),(500,"DEGRADED")])
async def test_http_failure_severity_and_subsequent_recovery(code,status):
    calls=0
    def respond(req):
        nonlocal calls
        calls+=1
        return httpx.Response(code,json={"error":"secret must not be echoed"}) if calls==1 else httpx.Response(200,json=record())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        p=transport(client=client)
        assert not await p.poll_once()
        assert p.snapshot().status==status
        assert "secret" not in p.snapshot().model_dump_json()
        assert p.retry_delay()>=10
        assert await p.poll_once()
        assert p.snapshot().healthy and p.failures==0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure",[httpx.ReadTimeout("timeout"),httpx.ConnectError("connection error"),"malformed",[],{}])
async def test_http_transient_failures_back_off_without_disabling(failure):
    def respond(req):
        if isinstance(failure,Exception): raise failure
        return httpx.Response(200,text="{") if failure=="malformed" else httpx.Response(200,json=failure)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        p=transport(client=client)
        delays=[]
        for _ in range(10):
            assert not await p.poll_once()
            delays.append(p.retry_delay())
        assert p.state.enabled and p.snapshot().status==ProviderStatus.DEGRADED
        assert delays[:3]==[10,20,40] and max(delays)==300


@pytest.mark.asyncio
async def test_http_stale_response_stays_on_ordinary_poll_schedule():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=record(utcnow()-timedelta(seconds=40))))) as client:
        p=transport(client=client)
        assert not await p.poll_once()
        assert p.snapshot().status==ProviderStatus.STALE
        assert p.failures==0 and p.retry_delay()==10


@pytest.mark.parametrize("setting",[0,1,4.99,float("nan"),float("inf")])
def test_configuration_rejects_abusive_or_invalid_polling(setting):
    with pytest.raises(ValidationError): Settings(_env_file=None,redstone_public_http_poll_interval_seconds=setting)
    with pytest.raises(ValueError): transport(poll_interval_seconds=setting).validate_configuration()


@pytest.mark.parametrize("config",[{"symbol":None},{"url":"http://example.com"},{"url":"https://user:password@example.com"},{"provider":""},{"stale_after_seconds":0}])
@pytest.mark.asyncio
async def test_http_invalid_configuration_does_not_start(config):
    p=transport(**config)
    await p.start()
    assert p.task is None and p.snapshot().status==ProviderStatus.ERROR
    assert "password" not in p.snapshot().model_dump_json()


def test_live_preferred_with_both_transports_fresh():
    p=provider(); now=utcnow().replace(microsecond=0)
    p.ingest(redstone_price(now,value="3000"),observed_at=now)
    p.public_http.ingest(record(now,value="3001"),observed_at=now)
    e=p.snapshot(now)
    assert e.price==D("3000") and e.transport==ReferenceTransport.LIVE_WS
    assert e.transport_quality==TransportQuality.PRIMARY and e.healthy


@pytest.mark.parametrize("live_status",[ProviderStatus.ERROR,ProviderStatus.DEGRADED,ProviderStatus.DISABLED,ProviderStatus.STALE])
def test_http_failover_for_unusable_live_health(live_status):
    p=provider(); now=utcnow().replace(microsecond=0)
    p.ingest(redstone_price(now,value="3000"),observed_at=now)
    p.state.set_status(live_status)
    p.public_http.ingest(record(now,value="3001"),observed_at=now)
    e=p.snapshot(now)
    assert e.price==D("3001") and e.transport==ReferenceTransport.PUBLIC_HTTP
    assert e.transport_quality==TransportQuality.FALLBACK and e.healthy and not e.simulated


def test_live_staleness_selects_http_with_independent_threshold():
    p=provider(); now=utcnow().replace(microsecond=0)
    p.ingest(redstone_price(now),observed_at=now)
    p.public_http.ingest(record(now),observed_at=now)
    assert p.snapshot(now+timedelta(seconds=2)).transport==ReferenceTransport.PUBLIC_HTTP
    assert p.snapshot(now+timedelta(seconds=2)).healthy
    assert p.snapshot(now+timedelta(seconds=31)).status==ProviderStatus.STALE
    assert not p.snapshot(now+timedelta(seconds=31)).healthy


def test_live_recovery_and_round_trip_switches_advance_version_at_same_price():
    p=provider(); now=utcnow().replace(microsecond=0)
    p.public_http.ingest(record(now,value="3000"),observed_at=now)
    http=p.snapshot(now)
    p.ingest(redstone_price(now,value="3000"),observed_at=now)
    live=p.snapshot(now)
    assert live.transport==ReferenceTransport.LIVE_WS and live.version>http.version
    assert live.price==http.price
    assert p.snapshot(now).version==live.version
    p.state.set_status(ProviderStatus.ERROR)
    fallback=p.snapshot(now)
    assert fallback.transport==ReferenceTransport.PUBLIC_HTTP and fallback.version>live.version
    p.ingest(redstone_price(now+timedelta(milliseconds=1),value="3000"),observed_at=now+timedelta(milliseconds=1))
    recovered=p.snapshot(now+timedelta(milliseconds=1))
    assert recovered.transport==ReferenceTransport.LIVE_WS and recovered.version>fallback.version


@pytest.mark.asyncio
async def test_no_live_credentials_validate_and_start_http_and_stop_tasks():
    requested=asyncio.Event()
    def respond(req):
        requested.set()
        return httpx.Response(200,json=record())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        p=provider(api_key="",ws_url="",public_http_client=client)
        p.validate_configuration()
        try:
            await p.start()
            await asyncio.wait_for(requested.wait(),1)
            assert p.task is None and p.state.status==ProviderStatus.ERROR
            assert p.public_http.task and p.snapshot().healthy
            assert p.snapshot().transport==ReferenceTransport.PUBLIC_HTTP
        finally: await p.stop()
        assert p.public_http.task is None
        assert not client.is_closed  # Injected client belongs to its caller.


@pytest.mark.asyncio
async def test_http_owned_client_closed_and_disabled_provider_never_requests(monkeypatch):
    owned=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=record())))
    monkeypatch.setattr("app.references.providers.httpx.AsyncClient",lambda **kwargs:owned)
    p=transport()
    assert await p.poll_once()
    await p.stop()
    assert owned.is_closed and p.client is None
    disabled=provider(enabled=False)
    await disabled.start()
    assert not await disabled.public_http.poll_once()
    assert disabled.snapshot().status==ProviderStatus.DISABLED


def core_evidence(redstone):
    return {
        "REDSTONE":redstone,
        "HYPERLIQUID_ORACLE":evidence(ProviderId.HYPERLIQUID_ORACLE,"3000",source_type=SourceType.NATIVE_ORACLE),
        "KRAKEN":evidence(ProviderId.KRAKEN,"3000",source_type=SourceType.VENUE_REFERENCE),
        "COINGECKO":evidence(ProviderId.COINGECKO,"3000",source_type=SourceType.AGGREGATOR_REFERENCE),
    }


def test_single_provider_vote_live_verified_http_degraded_and_coingecko_tertiary():
    p=provider(); now=utcnow().replace(microsecond=0)
    p.ingest(redstone_price(now,value="3000"),observed_at=now)
    p.public_http.ingest(record(now,value="3000"),observed_at=now)
    policy=ReferenceConsensusPolicy()
    live=policy.evaluate("ETH",core_evidence(p.snapshot(now)),agreement_bps=D("30"),outlier_bps=D("75"))
    assert CORE==[ProviderId.REDSTONE,ProviderId.HYPERLIQUID_ORACLE,ProviderId.KRAKEN]
    assert live.confidence_state=="VERIFIED"
    assert live.eligible_providers.count("REDSTONE")==1 and live.healthy_core_sources==3 and live.healthy_sources==4
    p.state.set_status(ProviderStatus.ERROR)
    fallback=policy.evaluate("ETH",core_evidence(p.snapshot(now)),agreement_bps=D("30"),outlier_bps=D("75"))
    assert fallback.confidence_state=="DEGRADED" and fallback.consensus_price==D("3000")
    assert fallback.healthy_core_sources==3 and fallback.healthy_sources==4
    assert "COINGECKO" not in fallback.eligible_providers
    assert any("public HTTP fallback" in r for r in fallback.reasons)


def test_http_cap_does_not_upgrade_conflicted_or_insufficient_evidence():
    p=provider(); now=utcnow().replace(microsecond=0)
    p.public_http.ingest(record(now,value="3000"),observed_at=now)
    e=core_evidence(p.snapshot(now))
    e["KRAKEN"]=evidence(ProviderId.KRAKEN,"3050")
    c=ReferenceConsensusPolicy().evaluate("ETH",e,agreement_bps=D("1"),outlier_bps=D("1000"))
    assert c.confidence_state=="CONFLICTED"
    c=ReferenceConsensusPolicy().evaluate("ETH",{"REDSTONE":e["REDSTONE"]},agreement_bps=D("30"),outlier_bps=D("75"))
    assert c.confidence_state=="INSUFFICIENT"


def test_http_confidence_cap_preserves_existing_firewall_posture():
    p=provider(); now=utcnow().replace(microsecond=0)
    p.public_http.ingest(record(now,value="3000"),observed_at=now)
    r=refs()
    r.evidence=core_evidence(p.snapshot(now))
    r.consensus=ReferenceConsensusPolicy().evaluate("ETH",r.evidence,agreement_bps=D("30"),outlier_bps=D("75"))
    fw=RiskFirewall(RiskFirewallConfig(max_projected_long_base=D("20"),max_projected_short_base=D("20")))
    assert evaluate(fw,r).state==RiskState.REDUCE


@pytest.mark.asyncio
async def test_demo_starts_no_external_transport_and_labels_demo_provenance():
    settings=Settings(_env_file=None,redstone_enabled=True,redstone_public_http_symbol="ETH")
    service=ReferenceService(settings,market="ETH",mode=MarketDataMode.DEMO)
    await service.start()
    assert service.redstone.task is None and service.redstone.public_http.task is None
    assert service.redstone.public_http.client is None
    snap=MockMarketDataAdapter().snapshot_for(0)
    e=service.snapshot(snap,demo_perp_context(snap),agreement_bps=D("30"),outlier_bps=D("75")).evidence["REDSTONE"]
    assert e.transport==ReferenceTransport.DEMO and e.transport_quality==TransportQuality.SIMULATED and e.simulated
    await service.stop()


@pytest.mark.asyncio
async def test_same_price_transport_switch_invalidates_reference_and_final_authorization():
    # Local market fixtures are offline evidence only; no network or orders are sent.
    rt=HyperAmmRuntime(Settings(_env_file=None))
    now=utcnow().replace(microsecond=0)
    snap=MockMarketDataAdapter().snapshot_for(0)
    await rt.market._accept(snap)
    service=ReferenceService(Settings(_env_file=None,redstone_enabled=True,redstone_feed_id="ETH",kraken_reference_enabled=True,kraken_symbol="ETH/USD"),market="ETH",mode=MarketDataMode.LIVE)
    rt.reference_service=service
    price=str(snap.mid_price)
    service.redstone.ingest(redstone_price(now,value=price),observed_at=now)
    service.redstone.public_http.ingest(record(now,value=price),observed_at=now)
    service.kraken.state.accept(snap.mid_price,now,now)
    await rt.refresh_once()
    old=rt.authorization
    assert old.authorized and rt.references.evidence["REDSTONE"].transport==ReferenceTransport.LIVE_WS
    rt.strategy.running=True
    service.redstone.state.set_status(ProviderStatus.ERROR)
    with pytest.raises(RuntimeError,match="reference evidence changed"):
        await rt._execution_authority()
    assert service._version>old.reference_version
    await rt.refresh_once()
    assert rt.references.evidence["REDSTONE"].transport==ReferenceTransport.PUBLIC_HTTP
    assert rt.references.evidence["REDSTONE"].price==snap.mid_price
    assert rt.authorization.evidence_fingerprint!=old.evidence_fingerprint
    assert rt.authorization.authorization_fingerprint!=old.authorization_fingerprint


def test_reference_fingerprint_explicitly_binds_transport_even_at_fixed_provider_version(monkeypatch):
    settings=Settings(_env_file=None)
    service=ReferenceService(settings,market="ETH",mode=MarketDataMode.LIVE)
    snap=MockMarketDataAdapter().snapshot_for(0)
    perp=demo_perp_context(snap)
    e=evidence(ProviderId.REDSTONE,str(snap.mid_price))
    e.transport=ReferenceTransport.LIVE_WS; e.transport_quality=TransportQuality.PRIMARY
    monkeypatch.setattr(service.redstone,"snapshot",lambda:e)
    first=service.snapshot(snap,perp,agreement_bps=D("30"),outlier_bps=D("75"))
    e.transport=ReferenceTransport.PUBLIC_HTTP; e.transport_quality=TransportQuality.FALLBACK
    second=service.snapshot(snap,perp,agreement_bps=D("30"),outlier_bps=D("75"))
    assert first.version<second.version
    assert first.evidence["REDSTONE"].version==second.evidence["REDSTONE"].version


def test_fastapi_serializes_single_effective_http_evidence_without_live_credentials(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main
    def runtime(settings):
        rt=HyperAmmRuntime(settings)
        rt.reference_service=ReferenceService(Settings(
            _env_file=None,redstone_enabled=True,redstone_public_http_symbol="ETH",
            redstone_api_key="",redstone_live_ws_url="",
        ),market="ETH",mode=MarketDataMode.LIVE)
        # Deterministic offline response fixture only; do not start networking.
        async def no_network(): pass
        rt.reference_service.start=no_network
        rt.reference_service.redstone.public_http.ingest(record(value="3000"))
        return rt
    monkeypatch.setattr(main,"HyperAmmRuntime",runtime)
    with TestClient(main.app) as client:
        r=client.get("/api/v1/references")
        assert r.status_code==200
        payload=r.json()
        assert set(payload["evidence"])=={p.value for p in ProviderId}
        e=payload["evidence"]["REDSTONE"]
        assert e["transport"]=="PUBLIC_HTTP" and e["transport_quality"]=="FALLBACK"
        assert e["status"]=="HEALTHY" and e["price"]=="3000"
        assert e["source_timestamp"] and e["age_ms"]>=0 and not e["simulated"]
        assert e["source_id"]=="redstone-public-http:ETH"
        raw=r.text.lower()
        assert "x-api-key" not in raw and "authorization" not in raw and "redstone_api_key" not in raw
