from __future__ import annotations
from decimal import Decimal
from .models import *

CORE=[ProviderId.REDSTONE,ProviderId.HYPERLIQUID_ORACLE,ProviderId.KRAKEN]
ALL=[*CORE,ProviderId.COINGECKO]

def _price(e,p):
    x=e.get(p.value)
    return x.price if x and x.status==ProviderStatus.HEALTHY and x.price is not None else None
def _median(vals):
    vals=sorted(vals);n=len(vals)
    if not n:raise ValueError("median requires values")
    return vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/Decimal("2")

class ReferenceConsensusPolicy:
    def evaluate(self,market,evidence,*,agreement_bps,outlier_bps,version=0):
        healthy={p:_price(evidence,p) for p in ALL};healthy={p:v for p,v in healthy.items() if v is not None}
        out=[]
        if len(healthy)>=3:
            m=_median(list(healthy.values()))
            out=[p.value for p,v in healthy.items() if abs(deviation_bps(v,m))>outlier_bps]
        eligible=[p for p in CORE if p in healthy and p.value not in out]
        prices=[healthy[p] for p in eligible];consensus=_median(prices) if len(prices)>=2 else None
        maxdev=max([abs(deviation_bps(v,consensus)) for v in prices],default=None) if consensus else None
        red=ProviderId.REDSTONE in eligible;native=ProviderId.HYPERLIQUID_ORACLE in eligible;kra=ProviderId.KRAKEN in eligible
        reasons=[]
        if len(eligible)<2:conf="INSUFFICIENT";reasons.append("fewer than two healthy core reference sources")
        elif maxdev is not None and maxdev>agreement_bps:conf="CONFLICTED";reasons.append(f"core source disagreement {maxdev} bps exceeds tolerance")
        elif red and kra:conf="VERIFIED";reasons+= ([] if native else ["Hyperliquid native oracle unavailable; RedStone + Kraken quorum active"])
        elif native and kra:conf="DEGRADED";reasons.append("RedStone unavailable; Hyperliquid native oracle + Kraken fallback quorum active")
        elif red and native:conf="DEGRADED";reasons.append("Kraken unavailable; oracle-only degraded quorum active")
        else:conf="INSUFFICIENT";reasons.append("institutional quorum requirements are not satisfied")
        if out:
            reasons.append("outlier sources: "+", ".join(sorted(out)))
            if conf=="VERIFIED" and any(provider.value in out for provider in CORE):
                conf="DEGRADED"
                reasons.append("core-source outlier prevents fully verified reference state")
        cg=_price(evidence,ProviderId.COINGECKO)
        if cg is not None and len(eligible)<2:reasons.append("CoinGecko is tertiary evidence and cannot authorize NORMAL quoting")
        return ReferenceConsensus(market=market,primary_oracle_price=_price(evidence,ProviderId.REDSTONE),native_oracle_price=_price(evidence,ProviderId.HYPERLIQUID_ORACLE),exchange_reference_price=_price(evidence,ProviderId.KRAKEN),aggregate_reference_price=cg,consensus_price=consensus,healthy_sources=sum(1 for x in evidence.values() if x.status==ProviderStatus.HEALTHY),healthy_core_sources=len(eligible),confidence_state=conf,max_source_deviation_bps=maxdev,source_statuses={k:v.status.value for k,v in evidence.items()},outliers=sorted(out),eligible_providers=[p.value for p in eligible],reasons=reasons,version=version,updated_at=utcnow())
