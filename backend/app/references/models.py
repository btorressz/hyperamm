from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from pydantic import BaseModel, Field, model_validator

class ProviderId(StrEnum):
    REDSTONE="REDSTONE"; HYPERLIQUID_ORACLE="HYPERLIQUID_ORACLE"; KRAKEN="KRAKEN"; COINGECKO="COINGECKO"; HYPERLIQUID_MID="HYPERLIQUID_MID"; HYPERLIQUID_MARK="HYPERLIQUID_MARK"

class SourceType(StrEnum):
    ORACLE="ORACLE"; NATIVE_ORACLE="NATIVE_ORACLE"; VENUE_REFERENCE="VENUE_REFERENCE"; EXECUTION_VENUE="EXECUTION_VENUE"; PERP_MARK="PERP_MARK"; AGGREGATOR_REFERENCE="AGGREGATOR_REFERENCE"

class ProviderStatus(StrEnum):
    HEALTHY="HEALTHY"; DEGRADED="DEGRADED"; STALE="STALE"; ERROR="ERROR"; DISABLED="DISABLED"

class ReferenceTransport(StrEnum):
    LIVE_WS="LIVE_WS"; PUBLIC_HTTP="PUBLIC_HTTP"; NATIVE="NATIVE"; REST="REST"; DEMO="DEMO"

class TransportQuality(StrEnum):
    PRIMARY="PRIMARY"; FALLBACK="FALLBACK"; SIMULATED="SIMULATED"

class PriceEvidence(BaseModel):
    market:str
    provider:ProviderId
    source_type:SourceType
    price:Decimal|None=None
    observed_at:datetime
    source_timestamp:datetime|None=None
    age_ms:int=Field(default=0,ge=0)
    healthy:bool=False
    stale:bool=False
    status:ProviderStatus
    source_id:str|None=None
    transport:ReferenceTransport|None=None
    transport_quality:TransportQuality|None=None
    simulated:bool=False
    version:int=Field(default=0,ge=0)
    error:str|None=None
    @model_validator(mode="after")
    def valid(self):
        if self.price is not None and (not self.price.is_finite() or self.price<=0):
            raise ValueError("price evidence price must be finite and positive")
        if self.status==ProviderStatus.HEALTHY and self.price is None:
            raise ValueError("healthy evidence requires price")
        return self

class ReferenceConsensus(BaseModel):
    market:str
    primary_oracle_price:Decimal|None=None
    native_oracle_price:Decimal|None=None
    exchange_reference_price:Decimal|None=None
    aggregate_reference_price:Decimal|None=None
    consensus_price:Decimal|None=None
    healthy_sources:int=0
    healthy_core_sources:int=0
    confidence_state:str
    max_source_deviation_bps:Decimal|None=None
    source_statuses:dict[str,str]
    outliers:list[str]=[]
    eligible_providers:list[str]=[]
    reasons:list[str]=[]
    version:int=0
    updated_at:datetime

class ReferenceSnapshot(BaseModel):
    market:str
    evidence:dict[str,PriceEvidence]
    consensus:ReferenceConsensus
    deviations_bps:dict[str,Decimal|None]
    deviation_magnitudes_bps:dict[str,Decimal|None]
    version:int=0
    updated_at:datetime

def utcnow(): return datetime.now(timezone.utc)
def decimal_price(value,name="price"):
    try: result=Decimal(str(value))
    except Exception as exc: raise ValueError(f"invalid {name}") from exc
    if not result.is_finite() or result<=0: raise ValueError(f"{name} must be finite and positive")
    return result
def parse_timestamp(value,name="timestamp"):
    if isinstance(value,datetime): result=value
    elif isinstance(value,(int,float,Decimal)):
        n=float(value); n=n/1000 if n>10_000_000_000 else n; result=datetime.fromtimestamp(n,timezone.utc)
    elif isinstance(value,str):
        s=value.strip()
        if not s: raise ValueError(f"missing {name}")
        if s.isdigit(): return parse_timestamp(int(s),name)
        result=datetime.fromisoformat(s.replace("Z","+00:00"))
    else: raise ValueError(f"invalid {name}")
    if result.tzinfo is None: result=result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)
def deviation_bps(source_price:Decimal,reference_price:Decimal)->Decimal:
    if not source_price.is_finite() or not reference_price.is_finite() or reference_price<=0: raise ValueError("invalid deviation prices")
    return (source_price-reference_price)/reference_price*Decimal("10000")
