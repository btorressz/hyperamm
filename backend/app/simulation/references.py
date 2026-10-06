from __future__ import annotations

from decimal import Decimal

from app.references.consensus import ReferenceConsensusPolicy
from app.references.models import (
    PriceEvidence,ProviderId,ProviderStatus,ReferenceSnapshot,ReferenceTransport,SourceType,TransportQuality,
    deviation_bps,
)


def build_simulated_references(frame,*,agreement_bps:Decimal,outlier_bps:Decimal,version:int)->ReferenceSnapshot:
    market=frame.market.market;ts=frame.timestamp;mid=frame.market.mid_price;perp=frame.perp_context
    prices={
        ProviderId.REDSTONE:frame.reference_prices.redstone,
        ProviderId.HYPERLIQUID_ORACLE:perp.oracle_price,
        ProviderId.KRAKEN:frame.reference_prices.kraken,
        ProviderId.COINGECKO:frame.reference_prices.coingecko,
        ProviderId.HYPERLIQUID_MID:mid,
        ProviderId.HYPERLIQUID_MARK:perp.mark_price,
    }
    types={
        ProviderId.REDSTONE:SourceType.ORACLE,
        ProviderId.HYPERLIQUID_ORACLE:SourceType.NATIVE_ORACLE,
        ProviderId.KRAKEN:SourceType.VENUE_REFERENCE,
        ProviderId.COINGECKO:SourceType.AGGREGATOR_REFERENCE,
        ProviderId.HYPERLIQUID_MID:SourceType.EXECUTION_VENUE,
        ProviderId.HYPERLIQUID_MARK:SourceType.PERP_MARK,
    }
    source_ids={
        ProviderId.REDSTONE:"simulation:redstone",ProviderId.HYPERLIQUID_ORACLE:"simulation:hl-oracle",
        ProviderId.KRAKEN:"simulation:kraken",ProviderId.COINGECKO:"simulation:coingecko",
        ProviderId.HYPERLIQUID_MID:"simulation:hl-mid",ProviderId.HYPERLIQUID_MARK:"simulation:hl-mark",
    }
    evidence={}
    for provider,price in prices.items():
        healthy=price is not None
        evidence[provider.value]=PriceEvidence(
            market=market,provider=provider,source_type=types[provider],price=price,observed_at=ts,
            source_timestamp=ts if healthy else None,age_ms=0,healthy=healthy,stale=False,
            status=ProviderStatus.HEALTHY if healthy else ProviderStatus.ERROR,source_id=source_ids[provider],
            transport=ReferenceTransport.DEMO,transport_quality=TransportQuality.SIMULATED,
            simulated=True,version=version,error=None if healthy else "simulation source unavailable",
        )
    consensus=ReferenceConsensusPolicy().evaluate(
        market,evidence,agreement_bps=agreement_bps,outlier_bps=outlier_bps,version=version
    ).model_copy(update={"updated_at":ts})
    ref=consensus.consensus_price
    def dev(provider):
        item=evidence[provider.value]
        return deviation_bps(item.price,ref) if ref is not None and item.price is not None else None
    deviations={
        "hl_mid_consensus":dev(ProviderId.HYPERLIQUID_MID),
        "hl_mark_consensus":dev(ProviderId.HYPERLIQUID_MARK),
        "hl_oracle_consensus":dev(ProviderId.HYPERLIQUID_ORACLE),
        "redstone_consensus":dev(ProviderId.REDSTONE),
        "kraken_consensus":dev(ProviderId.KRAKEN),
        "coingecko_consensus":dev(ProviderId.COINGECKO),
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
    return ReferenceSnapshot(
        market=market,evidence=evidence,consensus=consensus,deviations_bps=deviations,
        deviation_magnitudes_bps={k:(abs(v) if v is not None else None) for k,v in deviations.items()},
        version=version,updated_at=ts,
    )
