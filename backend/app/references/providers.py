from __future__ import annotations
import asyncio, json, random
from datetime import timedelta
from decimal import Decimal
import httpx
from .models import *

class EvidenceState:
    def __init__(self,market,provider,source_type,source_id,stale_after_seconds,enabled,on_update=None,material_change_bps=Decimal("0.25")):
        self.market=market; self.provider=provider; self.source_type=source_type; self.source_id=source_id
        self.stale_after_seconds=stale_after_seconds; self.enabled=enabled; self.on_update=on_update
        self.material_change_bps=material_change_bps; self.latest=None; self.version=0
        self.status=ProviderStatus.DISABLED if not enabled else ProviderStatus.DEGRADED; self.error=None
    def _notify(self):
        if self.on_update: self.on_update()
    def accept(self,price,source_timestamp,observed_at=None,source_id=None,simulated=False):
        observed=observed_at or utcnow(); price=decimal_price(price)
        if source_timestamp>observed+timedelta(seconds=5): raise ValueError("provider timestamp too far in future")
        if self.latest and self.latest.source_timestamp and source_timestamp<=self.latest.source_timestamp: return False
        if self.latest and self.latest.price is not None:
            d=abs((price-self.latest.price)/self.latest.price*Decimal("10000"))
            if d<self.material_change_bps:
                self.latest=self.latest.model_copy(update={"observed_at":observed,"source_timestamp":source_timestamp,"age_ms":max(0,int((observed-source_timestamp).total_seconds()*1000)),"healthy":True,"stale":False,"status":ProviderStatus.HEALTHY,"error":None})
                self.status=ProviderStatus.HEALTHY; self.error=None; return False
        self.version+=1; self.status=ProviderStatus.HEALTHY; self.error=None
        self.latest=PriceEvidence(market=self.market,provider=self.provider,source_type=self.source_type,price=price,observed_at=observed,source_timestamp=source_timestamp,age_ms=max(0,int((observed-source_timestamp).total_seconds()*1000)),healthy=True,stale=False,status=ProviderStatus.HEALTHY,source_id=source_id or self.source_id,simulated=simulated,version=self.version)
        self._notify(); return True
    def set_status(self,status,error=None):
        if not self.enabled and status!=ProviderStatus.DISABLED: status=ProviderStatus.DISABLED
        if status!=self.status or error!=self.error:
            self.version+=1; self.status=status; self.error=error
            if self.latest: self.latest=self.latest.model_copy(update={"status":status,"healthy":False,"error":error,"version":self.version})
            self._notify()
    def snapshot(self,now=None):
        now=now or utcnow()
        if not self.enabled:
            return PriceEvidence(market=self.market,provider=self.provider,source_type=self.source_type,observed_at=now,status=ProviderStatus.DISABLED,source_id=self.source_id,version=self.version)
        if not self.latest:
            return PriceEvidence(market=self.market,provider=self.provider,source_type=self.source_type,observed_at=now,status=self.status,source_id=self.source_id,version=self.version,error=self.error or "provider has no accepted price")
        age=max(0,int((now-self.latest.source_timestamp).total_seconds()*1000)) if self.latest.source_timestamp else 0
        stale=age>int(self.stale_after_seconds*1000); status=ProviderStatus.STALE if stale else self.status
        return self.latest.model_copy(update={"age_ms":age,"stale":stale,"healthy":status==ProviderStatus.HEALTHY and not stale,"status":status,"error":"provider price is stale" if stale else self.error})

def backoff(attempt,rand=None):
    base=min(30.0,2**max(0,min(attempt,5))); r=random.random() if rand is None else rand; return base*(1+0.2*r)

class RedStoneProvider:
    def __init__(self,*,market,enabled,api_key,ws_url,data_service_id,feed_id,stale_after_seconds,on_update=None,websocket_factory=None):
        self.api_key=api_key; self.ws_url=ws_url; self.data_service_id=data_service_id; self.feed_id=feed_id; self.websocket_factory=websocket_factory
        self.state=EvidenceState(market,ProviderId.REDSTONE,SourceType.ORACLE,feed_id,stale_after_seconds,enabled,on_update); self.task=None; self.closing=False
    def normalize(self,raw):
        if isinstance(raw,str): raw=json.loads(raw)
        if not isinstance(raw,dict): raise ValueError("malformed RedStone message")
        data=raw["data"] if isinstance(raw.get("data"),dict) else raw
        if data.get("dataServiceId")!=self.data_service_id: raise ValueError("wrong RedStone data service")
        feed=data.get("feedId") or data.get("feed")
        if self.feed_id and feed!=self.feed_id: raise ValueError("wrong RedStone feed")
        if "timestamp" not in data: raise ValueError("RedStone missing timestamp")
        return decimal_price(data.get("value"),"RedStone price"),parse_timestamp(data["timestamp"],"RedStone timestamp"),data.get("dataPackageId") or feed
    def ingest(self,raw,observed_at=None):
        p,t,s=self.normalize(raw); return self.state.accept(p,t,observed_at,s)
    def auth_headers(self):
        return {"x-api-key":self.api_key} if self.api_key else {}
    def classify_connection_error(self,exc):
        text=str(exc)
        if "401" in text or "403" in text:return ProviderStatus.ERROR
        if "429" in text:return ProviderStatus.DEGRADED
        return ProviderStatus.DEGRADED
    async def start(self):
        if not self.state.enabled or self.task: return
        if not self.ws_url or not self.api_key or not self.feed_id: self.state.set_status(ProviderStatus.ERROR,"RedStone enabled but URL/API key/feed ID is missing"); return
        self.closing=False; self.task=asyncio.create_task(self._run(),name="redstone-live-reference")
    async def _run(self):
        attempt=0
        while not self.closing:
            try:
                self.state.set_status(ProviderStatus.DEGRADED,"connecting/reconnecting")
                if self.websocket_factory: conn=self.websocket_factory(self.ws_url,self.api_key)
                else:
                    import websockets
                    try: conn=websockets.connect(self.ws_url,additional_headers=self.auth_headers(),open_timeout=10,ping_interval=20,ping_timeout=20,close_timeout=5)
                    except TypeError: conn=websockets.connect(self.ws_url,extra_headers=self.auth_headers(),open_timeout=10,ping_interval=20,ping_timeout=20,close_timeout=5)
                async with conn as ws:
                    await ws.send(json.dumps({"feedId":self.feed_id,"type":"price","dataServiceId":self.data_service_id})); attempt=0
                    async for msg in ws:
                        try:self.ingest(msg)
                        except Exception as exc:self.state.set_status(ProviderStatus.DEGRADED,f"invalid RedStone message: {exc}")
            except asyncio.CancelledError: break
            except Exception as exc:
                self.state.set_status(self.classify_connection_error(exc),str(exc)); await asyncio.sleep(backoff(attempt)); attempt+=1
    async def stop(self):
        self.closing=True
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
            self.task=None
    def snapshot(self): return self.state.snapshot()

class KrakenProvider:
    def __init__(self,*,market,enabled,symbol,stale_after_seconds,on_update=None,ws_url="wss://ws.kraken.com/v2",websocket_factory=None):
        self.symbol=symbol; self.ws_url=ws_url; self.websocket_factory=websocket_factory
        self.state=EvidenceState(market,ProviderId.KRAKEN,SourceType.VENUE_REFERENCE,symbol,stale_after_seconds,enabled,on_update); self.task=None; self.closing=False
    def subscription(self): return {"method":"subscribe","params":{"channel":"ticker","symbol":[self.symbol],"event_trigger":"bbo","snapshot":True},"req_id":1}
    def normalize(self,raw):
        if isinstance(raw,str): raw=json.loads(raw)
        if not isinstance(raw,dict) or raw.get("channel")!="ticker": raise ValueError("unknown Kraken message type")
        data=raw.get("data")
        if not isinstance(data,list) or not data or not isinstance(data[0],dict): raise ValueError("malformed Kraken ticker")
        tick=data[0]
        if tick.get("symbol")!=self.symbol: raise ValueError("wrong Kraken symbol")
        bid=decimal_price(tick.get("bid"),"Kraken bid"); ask=decimal_price(tick.get("ask"),"Kraken ask")
        if bid>=ask: raise ValueError("Kraken BBO crossed")
        return (bid+ask)/Decimal("2"),parse_timestamp(tick.get("timestamp"),"Kraken timestamp")
    def ingest(self,raw,observed_at=None):
        p,t=self.normalize(raw); return self.state.accept(p,t,observed_at,self.symbol)
    async def start(self):
        if not self.state.enabled or self.task:return
        if not self.symbol:self.state.set_status(ProviderStatus.ERROR,"Kraken enabled but symbol mapping missing");return
        self.closing=False; self.task=asyncio.create_task(self._run(),name="kraken-reference")
    async def _run(self):
        attempt=0
        while not self.closing:
            try:
                self.state.set_status(ProviderStatus.DEGRADED,"connecting/reconnecting")
                if self.websocket_factory: conn=self.websocket_factory(self.ws_url)
                else:
                    import websockets; conn=websockets.connect(self.ws_url,open_timeout=10,ping_interval=20,ping_timeout=20,close_timeout=5)
                async with conn as ws:
                    await ws.send(json.dumps(self.subscription())); attempt=0
                    async for msg in ws:
                        parsed=json.loads(msg) if isinstance(msg,str) else msg
                        if isinstance(parsed,dict) and parsed.get("method")=="subscribe":
                            if not parsed.get("success",False): raise RuntimeError(parsed.get("error") or "Kraken subscription rejected")
                            continue
                        try:self.ingest(parsed)
                        except Exception as exc:self.state.set_status(ProviderStatus.DEGRADED,f"invalid Kraken update: {exc}")
            except asyncio.CancelledError:break
            except Exception as exc:self.state.set_status(ProviderStatus.DEGRADED,str(exc));await asyncio.sleep(backoff(attempt));attempt+=1
    async def stop(self):
        self.closing=True
        if self.task:
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
            self.task=None
    def snapshot(self):return self.state.snapshot()

class CoinGeckoProvider:
    def __init__(self,*,market,enabled,coin_id,api_key,api_base_url,poll_interval_seconds,stale_after_seconds,on_update=None,client=None):
        self.coin_id=coin_id;self.api_key=api_key;self.api_base_url=api_base_url.rstrip("/");self.poll_interval_seconds=poll_interval_seconds;self.client=client;self.owns_client=client is None
        self.state=EvidenceState(market,ProviderId.COINGECKO,SourceType.AGGREGATOR_REFERENCE,coin_id,stale_after_seconds,enabled,on_update,Decimal("1"));self.task=None;self.closing=False
    def headers(self):
        if not self.api_key:return {}
        return {("x-cg-pro-api-key" if "pro-api.coingecko.com" in self.api_base_url else "x-cg-demo-api-key"):self.api_key}
    def normalize(self,payload):
        if not isinstance(payload,dict) or not self.coin_id or not isinstance(payload.get(self.coin_id),dict):raise ValueError("CoinGecko missing configured coin ID")
        item=payload[self.coin_id]
        if item.get("last_updated_at") is None:raise ValueError("CoinGecko missing last_updated_at")
        return decimal_price(item.get("usd"),"CoinGecko USD price"),parse_timestamp(item["last_updated_at"],"CoinGecko last_updated_at")
    def ingest(self,payload,observed_at=None):
        p,t=self.normalize(payload);return self.state.accept(p,t,observed_at,self.coin_id)
    async def poll_once(self):
        if self.client is None:self.client=httpx.AsyncClient(timeout=10)
        r=await self.client.get(f"{self.api_base_url}/simple/price",params={"ids":self.coin_id,"vs_currencies":"usd","include_last_updated_at":"true","precision":"full"},headers=self.headers())
        if r.status_code==429:self.state.set_status(ProviderStatus.DEGRADED,"CoinGecko rate limited (429)");return
        r.raise_for_status();self.ingest(r.json())
    async def start(self):
        if not self.state.enabled or self.task:return
        if not self.coin_id:self.state.set_status(ProviderStatus.ERROR,"CoinGecko enabled but coin ID mapping missing");return
        self.closing=False;self.task=asyncio.create_task(self._run(),name="coingecko-reference")
    async def _run(self):
        while not self.closing:
            try:await self.poll_once()
            except asyncio.CancelledError:break
            except httpx.HTTPStatusError as exc:self.state.set_status(ProviderStatus.ERROR,f"CoinGecko HTTP {exc.response.status_code}")
            except Exception as exc:self.state.set_status(ProviderStatus.DEGRADED,str(exc))
            try:await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:break
    async def stop(self):
        self.closing=True
        if self.task:
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
            self.task=None
        if self.client is not None and self.owns_client:await self.client.aclose();self.client=None
    def snapshot(self):return self.state.snapshot()
