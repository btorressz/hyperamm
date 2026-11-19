from __future__ import annotations
from decimal import Decimal
from .models import *

CORE=[ProviderId.REDSTONE,ProviderId.HYPERLIQUID_ORACLE,ProviderId.KRAKEN]
ALL=[*CORE,ProviderId.COINGECKO]
# Material snapshot/terminal rows include venue mid and mark diagnostics too.
# Registered observational identities are deliberately outside this contract.
MATERIAL_PROVIDERS=(*ALL,ProviderId.HYPERLIQUID_MID,ProviderId.HYPERLIQUID_MARK)

def _price(e,p):
    x=e.get(p.value)
    return x.price if x and x.status==ProviderStatus.HEALTHY and x.price is not None else None
def _median(vals):
    vals=sorted(vals);n=len(vals)
    if not n:raise ValueError("median requires values")
    return vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/Decimal("2")

class ReferenceConsensusPolicy:
    def evaluate(self, market, evidence, *, agreement_bps, outlier_bps, version=0):
        evidence = {key: item for key, item in evidence.items()
                    if key == str(item.provider) and not item.is_generalized_paper}
        return self._evaluate(market, evidence, agreement_bps, outlier_bps, version)

    def evaluate_scenario(self, market, evidence, *, agreement_bps, outlier_bps, version=0):
        evidence = {key: PriceEvidence.model_validate(item.model_dump()) for key, item in evidence.items()}
        if not evidence or any(key != item.provider.value or item.market != market
                               or not item.is_generalized_paper for key, item in evidence.items()):
            raise ValueError("scenario consensus requires synthetic PAPER evidence")
        return self._evaluate(market, evidence, agreement_bps, outlier_bps, version, scenario=True)

    @staticmethod
    def _evaluate(market, evidence, agreement_bps, outlier_bps, version, *, scenario=False):
        primary, oracle, secondary, tertiary = (
            (ProviderId.SCENARIO_PRIMARY, ProviderId.SCENARIO_ORACLE,
             ProviderId.SCENARIO_SECONDARY, ProviderId.SCENARIO_TERTIARY) if scenario else ALL
        )
        labels = ("Scenario primary", "Scenario oracle", "Scenario secondary", "Scenario tertiary") if scenario else (
            "RedStone", "Hyperliquid native oracle", "Kraken", "CoinGecko",
        )
        primary_label, oracle_label, secondary_label, tertiary_label = labels
        core = (primary, oracle, secondary)
        healthy = {p: price for p in (*core, tertiary) if (price := _price(evidence, p)) is not None}
        out = []
        if len(healthy) >= 3:
            median = _median(list(healthy.values()))
            out = [p.value for p, v in healthy.items() if abs(deviation_bps(v, median)) > outlier_bps]
        eligible = [p for p in core if p in healthy and p.value not in out]
        prices = [healthy[p] for p in eligible]
        consensus = _median(prices) if len(prices) >= 2 else None
        maxdev = max(abs(deviation_bps(v, consensus)) for v in prices) if consensus else None
        reasons = []
        if len(eligible) < 2:
            conf = "INSUFFICIENT"
            reasons.append("fewer than two healthy core reference sources")
        elif maxdev is not None and maxdev > agreement_bps:
            conf = "CONFLICTED"
            reasons.append(f"core source disagreement {maxdev} bps exceeds tolerance")
        elif primary in eligible and secondary in eligible:
            conf = SYNTHETIC_AGREEMENT if scenario else "VERIFIED"
            if oracle not in eligible:
                reasons.append(f"{oracle_label} unavailable; {primary_label} + {secondary_label} quorum active")
        elif oracle in eligible and secondary in eligible:
            conf = "DEGRADED"
            reasons.append(f"{primary_label} unavailable; {oracle_label} + {secondary_label} fallback quorum active")
        else:
            conf = "DEGRADED"
            reasons.append(f"{secondary_label} unavailable; oracle-only degraded quorum active")
        if out:
            reasons.append("outlier sources: " + ", ".join(sorted(out)))
            if conf in {"VERIFIED", SYNTHETIC_AGREEMENT} and any(p.value in out for p in core):
                conf = "DEGRADED"
                reasons.append("core-source outlier prevents full scenario agreement" if scenario
                               else "core-source outlier prevents fully verified reference state")
        item = evidence.get(primary.value)
        if not scenario and item and item.transport == ReferenceTransport.PUBLIC_HTTP and primary in healthy:
            if conf == "VERIFIED":
                conf = "DEGRADED"
            reasons.append("RedStone Live unavailable; public HTTP fallback transport active")
        tertiary_price = _price(evidence, tertiary)
        if tertiary_price is not None and len(eligible) < 2:
            reasons.append(f"{tertiary_label} is tertiary evidence and cannot authorize NORMAL quoting")
        return ReferenceConsensus(
            market=market, primary_oracle_price=None if scenario else _price(evidence, primary),
            native_oracle_price=None if scenario else _price(evidence, oracle),
            exchange_reference_price=None if scenario else _price(evidence, secondary),
            aggregate_reference_price=None if scenario else tertiary_price,
            consensus_price=consensus, healthy_sources=sum(x.status == ProviderStatus.HEALTHY for x in evidence.values()),
            healthy_core_sources=len(eligible), confidence_state=conf, max_source_deviation_bps=maxdev,
            source_statuses={k: v.status.value for k, v in evidence.items()}, outliers=sorted(out),
            eligible_providers=[p.value for p in eligible], reasons=reasons, version=version, updated_at=utcnow(),
        )
