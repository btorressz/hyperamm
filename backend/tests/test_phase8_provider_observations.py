"""Provider hardening and strictly observational Yahoo acceptance fixtures."""
from datetime import timedelta
from decimal import Decimal as D
import json
import pytest

from app.config import Settings
from app.market_data.mock import MockMarketDataAdapter
from app.market_data.models import MarketDataMode
from app.market_data.perp_context import demo_perp_context
from app.references.consensus import CORE,ALL
from app.references.models import ProviderId,ProviderStatus,utcnow
from app.references.providers import CoinGeckoProvider
from app.references.service import ReferenceService
from app.references.yahoo import YahooFinanceProvider


def gecko(**kwargs):
    data=dict(market="ETH",enabled=True,coin_id="ethereum",api_key="demo-secret",
              api_base_url="https://api.coingecko.com/api/v3",
              poll_interval_seconds=20,stale_after_seconds=90)
    data.update(kwargs)
    return CoinGeckoProvider(**data)


@pytest.mark.parametrize("url,header",[
    ("https://api.coingecko.com/api/v3","x-cg-demo-api-key"),
    ("https://pro-api.coingecko.com/api/v3","x-cg-pro-api-key"),
])
def test_coingecko_allowlisted_headers(url,header):
    p=gecko(api_base_url=url)
    assert p.headers()=={header:"demo-secret"}
    assert "demo-secret" not in json.dumps(p.snapshot().model_dump(mode="json"))


@pytest.mark.parametrize("url",[
    "https://pro-api.coingecko.com.evil.com/api/v3",
    "https://evil.com/pro-api.coingecko.com/api/v3",
    "http://api.coingecko.com/api/v3",
    "https://api.coingecko.com:444/api/v3",
    "https://api.coingecko.com/api/v3?token=1",
    "https://demo-secret@api.coingecko.com/api/v3",
])
def test_coingecko_rejects_untrusted_hosts(url):
    with pytest.raises(ValueError):
        gecko(api_base_url=url).headers()


@pytest.mark.asyncio
@pytest.mark.parametrize("change",[
    {"api_key":None},{"api_key":"  "},{"coin_id":""},
    {"api_base_url":"https://api.coingecko.com.evil.com/api/v3"},
])
async def test_coingecko_invalid_enabled_stops_without_network(change):
    p=gecko(**change)
    await p.start()
    assert p.task is None
    assert p.client is None
    assert p.snapshot().status==ProviderStatus.ERROR


@pytest.mark.asyncio
async def test_coingecko_disabled_never_requires_credentials():
    p=gecko(enabled=False,api_key=None)
    assert p.headers()=={}
    await p.start()
    assert p.task is None
    assert p.client is None
    assert p.snapshot().status==ProviderStatus.DISABLED


class FakeClient:
    def __init__(self,status,payload=None):
        self.status=status;self.payload=payload;self.calls=[]
    async def get(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        class Response:
            def __init__(self,status,payload):self.status_code=status;self.payload=payload
            def json(self):return self.payload
        return Response(self.status,self.payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected",[
    (400,ProviderStatus.ERROR),(401,ProviderStatus.ERROR),(403,ProviderStatus.ERROR),
    (429,ProviderStatus.DEGRADED),(500,ProviderStatus.DEGRADED),
])
async def test_coingecko_status_classification(status,expected):
    client=FakeClient(status)
    p=gecko(client=client)
    retry=await p.poll_once()
    assert p.snapshot().status==expected
    assert retry==(expected==ProviderStatus.DEGRADED)
    assert len(client.calls)==1
    assert client.calls[0][1]["headers"]=={"x-cg-demo-api-key":"demo-secret"}


def yahoo(**changes):
    params=dict(market="ETH",enabled=True,symbol="ETH-USD",
                stale_after_seconds=30,websocket_factory=lambda:None)
    params.update(changes)
    return YahooFinanceProvider(**params)


def frame(now,price="3000",offset=0,symbol="ETH-USD"):
    return {"id":symbol,"price":price,"time":int((now+timedelta(seconds=offset)).timestamp()*1000)}


def test_yahoo_normalization_timestamps_duplicates_stale_and_errors():
    p=yahoo()
    t=utcnow().replace(microsecond=0)
    assert p.ingest(frame(t),observed_at=t)
    version=p.state.version
    assert not p.ingest(frame(t),observed_at=t+timedelta(seconds=1))
    assert p.state.version==version
    assert p.ingest(frame(t,offset=1),observed_at=t+timedelta(seconds=1)) is False
    assert p.state.snapshot(t+timedelta(seconds=1)).healthy
    assert p.snapshot().provider==ProviderId.YAHOO_FINANCE
    for bad in [frame(t,symbol="BTC-USD"),frame(t,price="0"),frame(t,price="-1"),
                frame(t,price="NaN"),{"id":"ETH-USD","price":3000},
                {"id":"ETH-USD","price":3000,"time":int(t.timestamp())},
                frame(t,offset=6)]:
        with pytest.raises(ValueError):
            p.normalize(bad,observed_at=t)
    with pytest.raises(ValueError):
        p.normalize(frame(t,offset=-31),observed_at=t)


def test_yahoo_disabled_or_bad_mapping_is_nonblocking():
    assert yahoo(enabled=False,symbol="garbage").snapshot().status==ProviderStatus.DISABLED
    with pytest.raises(ValueError):
        yahoo(symbol="BTC-USD").validate_configuration()


@pytest.mark.asyncio
async def test_yahoo_disabled_never_connects():
    calls=[]
    p=yahoo(enabled=False,websocket_factory=lambda:calls.append(True))
    await p.start()
    assert p.task is None and not calls


@pytest.mark.asyncio
async def test_yahoo_missing_optional_dependency_is_observational_error(monkeypatch):
    import app.references.yahoo as mod
    original=mod.importlib.import_module
    def missing(name):
        if name=="yfinance":raise ImportError("missing")
        return original(name)
    monkeypatch.setattr(mod.importlib,"import_module",missing)
    p=yahoo(websocket_factory=None)
    await p.start()
    assert p.snapshot().status==ProviderStatus.ERROR
    assert p.task is None


def test_yahoo_material_reference_identity_is_unchanged():
    assert ProviderId.YAHOO_FINANCE not in CORE
    assert ProviderId.YAHOO_FINANCE not in ALL
    settings=Settings(_env_file=None,yfinance_reference_enabled=True)
    service=ReferenceService(settings,market="ETH",mode=MarketDataMode.DEMO)
    market=MockMarketDataAdapter().snapshot_for(4)
    perp=demo_perp_context(market)
    first=service.snapshot(market,perp,agreement_bps=D("30"),outlier_bps=D("75"))
    p=service.yahoo
    for change in ("0.5","1","1.5"):
        at=utcnow().replace(microsecond=0)
        p.state.latest=None
        p.state._last_source_timestamp=None
        p.ingest(frame(at,price=str(D("3000")*D(change))),observed_at=at)
        output=service.observations(first)
        assert output["authority"]=="NONE"
        assert output["observations"][0]["authority"]=="NONE"
        again=service.snapshot(market,perp,agreement_bps=D("30"),outlier_bps=D("75"))
        assert again.version==first.version
        assert again.evidence==first.evidence
        assert again.consensus.consensus_price==first.consensus.consensus_price
        assert again.consensus.confidence_state==first.consensus.confidence_state
        assert "YAHOO_FINANCE" not in again.evidence
