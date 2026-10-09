"""Optional research observation. This module is not referenced by quote authority."""
from __future__ import annotations
import asyncio
import importlib
from datetime import timedelta
from decimal import Decimal
from .models import ProviderId, ProviderStatus, SourceType, ReferenceTransport, decimal_price, parse_timestamp, deviation_bps, utcnow
from .providers import EvidenceState, backoff

SYMBOLS={"ETH":"ETH-USD","BTC":"BTC-USD"}

class YahooFinanceProvider:
    def __init__(self,*,market,enabled,symbol,stale_after_seconds=30,websocket_factory=None):
        self.market=market
        self.symbol=symbol
        self.websocket_factory=websocket_factory
        self.state=EvidenceState(market,ProviderId.YAHOO_FINANCE,SourceType.AGGREGATOR_REFERENCE,symbol,stale_after_seconds,enabled,material_change_bps=Decimal("0"),transport=ReferenceTransport.LIVE_WS)
        self.task=None
        self.closing=False
        self.last_receipt=None

    def validate_configuration(self):
        if self.state.enabled and SYMBOLS.get(self.market)!=self.symbol:
            raise ValueError("Yahoo requires a supported explicit startup-market mapping")

    def normalize(self,frame,observed_at=None):
        if not isinstance(frame,dict) or frame.get("id")!=self.symbol:
            raise ValueError("Yahoo symbol mismatch")
        price=decimal_price(frame.get("price"),"Yahoo price")
        value=frame.get("time")
        if isinstance(value,bool) or not isinstance(value,(int,str)) or not str(value).isdigit():
            raise ValueError("Yahoo source time missing")
        ms=int(value)
        if not 10**12<=ms<10**13:
            raise ValueError("Yahoo source time must be milliseconds")
        ts=parse_timestamp(ms,"Yahoo time")
        now=observed_at or utcnow()
        if ts>now+timedelta(seconds=5) or now-ts>timedelta(seconds=self.state.stale_after_seconds):
            raise ValueError("Yahoo source time outside freshness bounds")
        return price,ts

    def ingest(self,frame,observed_at=None):
        now=observed_at or utcnow()
        p,t=self.normalize(frame,now)
        changed=self.state.accept(p,t,now,self.symbol)
        if self.state.snapshot(now).healthy:
            self.last_receipt=now
        return changed

    def _handle(self,frame):
        try:self.ingest(frame)
        except (ValueError,TypeError,OverflowError):
            if self.state.latest is None:
                self.state.set_status(ProviderStatus.DEGRADED,"Yahoo frame invalid")

    def _socket(self):
        if self.websocket_factory:return self.websocket_factory()
        return importlib.import_module("yfinance").AsyncWebSocket()

    async def start(self):
        if not self.state.enabled or self.task:return
        try:
            self.validate_configuration()
            if self.websocket_factory is None and not hasattr(importlib.import_module("yfinance"),"AsyncWebSocket"):
                raise ImportError("AsyncWebSocket unavailable")
        except (ValueError,ImportError):
            self.state.set_status(ProviderStatus.ERROR,"Yahoo configuration or optional dependency unavailable")
            return
        self.closing=False
        self.task=asyncio.create_task(self._run(),name="yahoo-observational-reference")

    async def _listen(self,socket):
        await socket.listen(self._handle)
        if not self.closing:raise ConnectionError("Yahoo listener ended")

    async def _watch(self):
        started=utcnow()
        while not self.closing:
            await asyncio.sleep(1)
            last=self.last_receipt or started
            if (utcnow()-last).total_seconds()>max(10,self.state.stale_after_seconds):
                raise TimeoutError("Yahoo observational frames unavailable")

    async def _run(self):
        failures=0
        while not self.closing:
            listen=None;watch=None
            try:
                self.last_receipt=None
                self.state.set_status(ProviderStatus.DEGRADED,"Yahoo connecting")
                async with self._socket() as ws:
                    await asyncio.wait_for(ws.subscribe([self.symbol]),timeout=10)
                    listen=asyncio.create_task(self._listen(ws))
                    watch=asyncio.create_task(self._watch())
                    done,_=await asyncio.wait((listen,watch),return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        await task
            except asyncio.CancelledError:
                break
            except Exception:
                self.state.set_status(ProviderStatus.DEGRADED,"Yahoo connection unavailable")
                if self.closing:break
                try:await asyncio.sleep(backoff(failures,rand=0))
                except asyncio.CancelledError:break
                failures+=1
            finally:
                for task in (listen,watch):
                    if task:task.cancel()
                await asyncio.gather(*(task for task in (listen,watch) if task),return_exceptions=True)

    async def stop(self):
        self.closing=True
        if self.task:
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
            self.task=None

    def snapshot(self):
        return self.state.snapshot()

    def observation(self,material=None):
        now=utcnow()
        e=self.state.snapshot(now)
        deviations={k:None for k in ("yahoo_vs_redstone_bps","yahoo_vs_hyperliquid_oracle_bps","yahoo_vs_kraken_bps","yahoo_vs_coingecko_bps","yahoo_vs_core_consensus_bps")}
        if material is not None and e.healthy and not e.stale:
            for k,p in (("yahoo_vs_redstone_bps",ProviderId.REDSTONE),("yahoo_vs_hyperliquid_oracle_bps",ProviderId.HYPERLIQUID_ORACLE),("yahoo_vs_kraken_bps",ProviderId.KRAKEN),("yahoo_vs_coingecko_bps",ProviderId.COINGECKO)):
                other=material.evidence.get(p.value)
                if other and other.healthy and not other.stale and other.price is not None and other.source_timestamp is not None and 0<=(now-other.source_timestamp).total_seconds()<=30:
                    deviations[k]=str(deviation_bps(e.price,other.price))
            if material.consensus.consensus_price is not None and material.consensus.healthy_core_sources>=2 and (now-material.updated_at).total_seconds()<=30:
                deviations["yahoo_vs_core_consensus_bps"]=str(deviation_bps(e.price,material.consensus.consensus_price))
        return {"role":"OBSERVATIONAL","authority":"NONE","symbol":self.symbol,**e.model_dump(mode="json"),"deviations_bps":deviations}
