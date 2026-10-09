from __future__ import annotations
from datetime import datetime
from decimal import Decimal

from app.market_data.models import MarketDataMode, MarketSnapshot
from app.market_data.perp_context import PerpMarketContext
from .consensus import ReferenceConsensusPolicy
from .models import (
    PriceEvidence, ProviderId, ProviderStatus, ReferenceSnapshot, SourceType, ReferenceTransport, TransportQuality,
    deviation_bps, utcnow,
)
from .providers import CoinGeckoProvider, KrakenProvider, RedStoneProvider
from .yahoo import YahooFinanceProvider


class ReferenceService:
    def __init__(self, settings, *, market: str, mode: MarketDataMode, wakeup=None):
        self.settings=settings; self.market=market; self.mode=mode; self.wakeup=wakeup
        if mode==MarketDataMode.LIVE and market!=settings.market and (
            settings.redstone_enabled or settings.kraken_reference_enabled or settings.coingecko_reference_enabled
        ):
            raise ValueError("LIVE reference mappings are bound to the configured startup MARKET; restart with explicit mappings for the new market")
        def changed():
            if self.wakeup is not None: self.wakeup.set()
        live=mode==MarketDataMode.LIVE
        self.redstone=RedStoneProvider(
            market=market,enabled=live and settings.redstone_enabled,
            api_key=settings.redstone_api_key,ws_url=settings.redstone_live_ws_url,
            data_service_id=settings.redstone_data_service_id,feed_id=settings.redstone_feed_id,
            stale_after_seconds=settings.redstone_stale_after_seconds,on_update=changed,
            public_http_fallback_enabled=settings.redstone_public_http_fallback_enabled,
            public_http_url=settings.redstone_public_http_url,
            public_http_provider=settings.redstone_public_http_provider,
            public_http_symbol=settings.redstone_public_http_symbol,
            public_http_poll_interval_seconds=settings.redstone_public_http_poll_interval_seconds,
            public_http_stale_after_seconds=settings.redstone_public_http_stale_after_seconds,
        )
        self.kraken=KrakenProvider(
            market=market,enabled=live and settings.kraken_reference_enabled,
            symbol=settings.kraken_symbol,stale_after_seconds=settings.kraken_stale_after_seconds,
            ws_url=settings.kraken_ws_url,on_update=changed,
        )
        self.coingecko=CoinGeckoProvider(
            market=market,enabled=live and settings.coingecko_reference_enabled,
            coin_id=settings.coingecko_coin_id,api_key=settings.coingecko_api_key,
            api_base_url=settings.coingecko_api_base_url,
            poll_interval_seconds=settings.coingecko_poll_interval_seconds,
            stale_after_seconds=settings.coingecko_stale_after_seconds,on_update=changed,
        )
        self.yahoo=YahooFinanceProvider(market=market,enabled=settings.yfinance_reference_enabled,symbol=settings.yfinance_symbol,stale_after_seconds=settings.yfinance_stale_after_seconds)
        self.consensus_policy=ReferenceConsensusPolicy()
        self._version=0; self._fingerprint=None

    async def start(self):
        await self.yahoo.start()
        if self.mode==MarketDataMode.DEMO:return
        await self.redstone.start(); await self.kraken.start(); await self.coingecko.start()

    async def stop(self):
        await self.yahoo.stop()
        await self.redstone.stop(); await self.kraken.stop(); await self.coingecko.stop()

    def observations(self,material=None):
        return {"market":self.market,"authority":"NONE","observations":[self.yahoo.observation(material)]}

    @staticmethod
    def _evidence(*,market,provider,source_type,price,timestamp,version,simulated=False,source_id=None):
        now=utcnow(); age=max(0,int((now-timestamp).total_seconds()*1000))
        return PriceEvidence(market=market,provider=provider,source_type=source_type,price=price,observed_at=now,source_timestamp=timestamp,age_ms=age,healthy=True,stale=False,status=ProviderStatus.HEALTHY,source_id=source_id,simulated=simulated,version=version,transport=ReferenceTransport.DEMO if simulated else ReferenceTransport.NATIVE,transport_quality=TransportQuality.SIMULATED if simulated else None)

    def _native(self,snapshot:MarketSnapshot,perp:PerpMarketContext)->dict[str,PriceEvidence]:
        ts=perp.updated_at
        mid_ts=snapshot.latest_valid_update or ts
        return {
            ProviderId.HYPERLIQUID_ORACLE.value:self._evidence(market=self.market,provider=ProviderId.HYPERLIQUID_ORACLE,source_type=SourceType.NATIVE_ORACLE,price=perp.oracle_price,timestamp=ts,version=perp.version,simulated=perp.simulated,source_id="oraclePx"),
            ProviderId.HYPERLIQUID_MID.value:self._evidence(market=self.market,provider=ProviderId.HYPERLIQUID_MID,source_type=SourceType.EXECUTION_VENUE,price=snapshot.mid_price,timestamp=mid_ts,version=snapshot.book.sequence if snapshot.book else 0,simulated=snapshot.simulated,source_id="l2-mid"),
            ProviderId.HYPERLIQUID_MARK.value:self._evidence(market=self.market,provider=ProviderId.HYPERLIQUID_MARK,source_type=SourceType.PERP_MARK,price=perp.mark_price,timestamp=ts,version=perp.version,simulated=perp.simulated,source_id="markPx"),
        }

    def _demo_external(self,snapshot:MarketSnapshot)->dict[str,PriceEvidence]:
        if snapshot.mid_price is None or snapshot.book is None: raise ValueError("DEMO references require valid market midpoint")
        mid=snapshot.mid_price; seq=snapshot.book.sequence; ts=snapshot.latest_valid_update or snapshot.book.timestamp
        offsets={
            ProviderId.REDSTONE:Decimal((seq%5)-2)*Decimal("0.08"),
            ProviderId.KRAKEN:Decimal((seq%7)-3)*Decimal("0.10"),
            ProviderId.COINGECKO:Decimal((seq%3)-1)*Decimal("0.12"),
        }
        types={ProviderId.REDSTONE:SourceType.ORACLE,ProviderId.KRAKEN:SourceType.VENUE_REFERENCE,ProviderId.COINGECKO:SourceType.AGGREGATOR_REFERENCE}
        return {p.value:self._evidence(market=self.market,provider=p,source_type=types[p],price=mid*(Decimal("1")+bps/Decimal("10000")),timestamp=ts,version=seq,simulated=True,source_id=("redstone-demo" if p==ProviderId.REDSTONE else "kraken-demo" if p==ProviderId.KRAKEN else "coingecko-demo")) for p,bps in offsets.items()}

    def snapshot(self,snapshot:MarketSnapshot,perp:PerpMarketContext,*,agreement_bps:Decimal,outlier_bps:Decimal)->ReferenceSnapshot:
        if snapshot.stale: raise RuntimeError("market snapshot is stale")
        if perp.stale: raise RuntimeError("perpetual context is stale")
        evidence=self._native(snapshot,perp)
        if self.mode==MarketDataMode.DEMO:evidence.update(self._demo_external(snapshot))
        else:
            evidence.update({
                ProviderId.REDSTONE.value:self.redstone.snapshot(),
                ProviderId.KRAKEN.value:self.kraken.snapshot(),
                ProviderId.COINGECKO.value:self.coingecko.snapshot(),
            })
        core=(evidence[ProviderId.REDSTONE.value].version,evidence[ProviderId.KRAKEN.value].version,evidence[ProviderId.COINGECKO.value].version,evidence[ProviderId.HYPERLIQUID_ORACLE.value].version,evidence[ProviderId.HYPERLIQUID_MID.value].version,evidence[ProviderId.HYPERLIQUID_MARK.value].version)
        fp=(core,tuple((k,str(v.price),v.status.value,v.stale,v.transport,v.transport_quality) for k,v in sorted(evidence.items())))
        if fp!=self._fingerprint:self._version+=1;self._fingerprint=fp
        consensus=self.consensus_policy.evaluate(self.market,evidence,agreement_bps=agreement_bps,outlier_bps=outlier_bps,version=self._version)
        ref=consensus.consensus_price
        def d(provider):
            item=evidence.get(provider.value)
            return deviation_bps(item.price,ref) if ref is not None and item and item.price is not None else None
        deviations={
            "hl_mid_consensus":d(ProviderId.HYPERLIQUID_MID),
            "hl_mark_consensus":d(ProviderId.HYPERLIQUID_MARK),
            "hl_oracle_consensus":d(ProviderId.HYPERLIQUID_ORACLE),
            "redstone_consensus":d(ProviderId.REDSTONE),
            "kraken_consensus":d(ProviderId.KRAKEN),
            "coingecko_consensus":d(ProviderId.COINGECKO),
        }
        pairs=[
            ("redstone_kraken",ProviderId.REDSTONE,ProviderId.KRAKEN),
            ("redstone_hl_oracle",ProviderId.REDSTONE,ProviderId.HYPERLIQUID_ORACLE),
            ("redstone_coingecko",ProviderId.REDSTONE,ProviderId.COINGECKO),
            ("kraken_hl_oracle",ProviderId.KRAKEN,ProviderId.HYPERLIQUID_ORACLE),
            ("kraken_coingecko",ProviderId.KRAKEN,ProviderId.COINGECKO),
            ("hl_mark_hl_oracle",ProviderId.HYPERLIQUID_MARK,ProviderId.HYPERLIQUID_ORACLE),
            ("hl_mid_hl_mark",ProviderId.HYPERLIQUID_MID,ProviderId.HYPERLIQUID_MARK),
            ("hl_mid_hl_oracle",ProviderId.HYPERLIQUID_MID,ProviderId.HYPERLIQUID_ORACLE),
        ]
        for name,a,b in pairs:
            av=evidence[a.value].price;bv=evidence[b.value].price
            deviations[name]=deviation_bps(av,bv) if av is not None and bv is not None else None
        magnitudes={k:(abs(v) if v is not None else None) for k,v in deviations.items()}
        return ReferenceSnapshot(market=self.market,evidence=evidence,consensus=consensus,deviations_bps=deviations,deviation_magnitudes_bps=magnitudes,version=self._version,updated_at=utcnow())
