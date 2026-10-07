from __future__ import annotations

from datetime import datetime,timezone
from decimal import Decimal
from enum import Enum
import hashlib,json

from pydantic import BaseModel,ConfigDict,Field,model_validator

from app.market_data.models import MarketSnapshot
from app.market_data.perp_context import PerpMarketContext
from app.accounting.models import LedgerEntry, VaultSnapshot


def _canonical(value):
    if isinstance(value,Decimal):return format(value,"f")
    if isinstance(value,datetime):return value.astimezone(timezone.utc).isoformat()
    if isinstance(value,Enum):return value.value
    if hasattr(value,"model_dump"):return _canonical(value.model_dump())
    if isinstance(value,dict):return {str(k):_canonical(v) for k,v in sorted(value.items(),key=lambda x:str(x[0]))}
    if isinstance(value,(list,tuple)):return [_canonical(v) for v in value]
    return value


def stable_fingerprint(value)->str:
    raw=json.dumps(_canonical(value),sort_keys=True,separators=(",",":"),ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


class SimulationReferencePrices(BaseModel):
    model_config=ConfigDict(frozen=True)
    redstone:Decimal|None=None
    kraken:Decimal|None=None
    coingecko:Decimal|None=None

    @model_validator(mode="after")
    def validate_prices(self):
        for name in ("redstone","kraken","coingecko"):
            value=getattr(self,name)
            if value is not None and (not value.is_finite() or value<=0):
                raise ValueError(f"{name} reference must be finite and positive")
        return self


class SimulationFrame(BaseModel):
    model_config=ConfigDict(frozen=True)
    sequence:int=Field(ge=0)
    timestamp:datetime
    market:MarketSnapshot
    perp_context:PerpMarketContext
    reference_prices:SimulationReferencePrices

    @model_validator(mode="after")
    def validate_frame(self):
        if self.market.market!=self.perp_context.market:
            raise ValueError("simulation market/perp market mismatch")
        if self.market.book is None or self.market.mid_price is None or self.market.best_bid is None or self.market.best_ask is None:
            raise ValueError("simulation frame requires complete market snapshot")
        if self.market.book.sequence!=self.sequence:
            raise ValueError("simulation frame/book sequence mismatch")
        if self.market.book.timestamp!=self.timestamp:
            raise ValueError("simulation frame/book timestamp mismatch")
        for name,value in (("best bid",self.market.best_bid),("best ask",self.market.best_ask),("mid",self.market.mid_price)):
            if not value.is_finite() or value<=0:
                raise ValueError(f"simulation {name} must be finite and positive")
        if self.market.best_bid>=self.market.best_ask:
            raise ValueError("simulation BBO is crossed")
        if self.market.best_bid!=self.market.book.bids[0].price or self.market.best_ask!=self.market.book.asks[0].price:
            raise ValueError("simulation BBO must match top order-book levels")
        expected_mid=(self.market.best_bid+self.market.best_ask)/Decimal("2")
        if self.market.mid_price!=expected_mid:
            raise ValueError("simulation mid must equal BBO midpoint")
        if self.timestamp.tzinfo is None:
            raise ValueError("simulation timestamp must be timezone-aware")
        if self.market.stale:
            raise ValueError("simulation market snapshot cannot be stale")
        if self.perp_context.stale:
            raise ValueError("simulation perp context cannot be stale")
        if self.perp_context.updated_at!=self.timestamp:
            raise ValueError("simulation perp timestamp must equal frame timestamp")
        return self


class SimulationDataset(BaseModel):
    model_config=ConfigDict(frozen=True)
    market:str
    frames:tuple[SimulationFrame,...]
    source:str
    simulated:bool=True
    fingerprint:str=""

    @model_validator(mode="after")
    def validate_dataset(self):
        if not self.frames:
            raise ValueError("simulation dataset cannot be empty")
        previous_sequence=None;previous_timestamp=None
        for frame in self.frames:
            if frame.market.market!=self.market:
                raise ValueError("simulation dataset market mismatch")
            if previous_sequence is not None and frame.sequence<=previous_sequence:
                raise ValueError("simulation sequence must strictly increase")
            if previous_timestamp is not None and frame.timestamp<=previous_timestamp:
                raise ValueError("simulation timestamp must strictly increase")
            previous_sequence=frame.sequence;previous_timestamp=frame.timestamp
        semantic={"market":self.market,"source":self.source,"simulated":self.simulated,"frames":self.frames}
        expected=stable_fingerprint(semantic)
        if self.fingerprint and self.fingerprint!=expected:
            raise ValueError("simulation dataset fingerprint mismatch")
        object.__setattr__(self,"fingerprint",expected)
        return self


class SimulationTracePoint(BaseModel):
    sequence:int
    timestamp:datetime
    mid:Decimal
    mark:Decimal
    oracle:Decimal
    inventory_base:Decimal
    session_pnl:Decimal
    equity:Decimal
    drawdown_pct:Decimal
    reference_confidence:str
    agent_regime:str
    toxic_flow_state:str
    execution_quality_state:str
    risk_state:str
    desired_quote_count:int
    agent_quote_count:int
    authorized_quote_count:int
    open_order_count:int
    fill_count:int


class SimulationMetrics(BaseModel):
    frame_count:int
    starting_equity:Decimal
    ending_equity:Decimal
    session_pnl:Decimal
    return_pct:Decimal
    realized_pnl:Decimal
    unrealized_pnl:Decimal
    max_drawdown_pct:Decimal
    fill_count:int
    buy_fill_count:int
    sell_fill_count:int
    quoted_notional:Decimal
    filled_notional:Decimal
    fill_activity_ratio:Decimal|None
    ending_inventory_base:Decimal
    max_abs_inventory_base:Decimal
    max_inventory_utilization:Decimal
    mean_spread_capture_bps:Decimal|None
    mean_mature_markout_bps:Decimal|None
    adverse_fill_rate:Decimal|None
    keep_count:int
    create_count:int
    replace_count:int
    cancel_count:int
    reconciliation_churn_ratio:Decimal
    risk_state_counts:dict[str,int]
    risk_halt_fraction:Decimal
    agent_regime_counts:dict[str,int]
    toxic_flow_state_counts:dict[str,int]
    execution_quality_state_counts:dict[str,int]


class SimulationResult(BaseModel):
    engine_version:str
    run_fingerprint:str
    scenario:str
    dataset_fingerprint:str
    strategy_fingerprint:str
    metrics:SimulationMetrics
    trace:list[SimulationTracePoint]=Field(default_factory=list)
    simulated:bool=True
    limitations:list[str]=Field(default_factory=list)
    orders:list[dict]=Field(default_factory=list)
    fills:list[dict]=Field(default_factory=list)
    vault:VaultSnapshot|None=None
    accounting_ledger:tuple[LedgerEntry,...]=()
    accounting_fingerprint:str|None=None


class ScoreComponents(BaseModel):
    return_contribution:Decimal
    drawdown_penalty:Decimal
    inventory_penalty:Decimal
    adverse_markout_penalty:Decimal
    churn_penalty:Decimal
    halt_penalty:Decimal
    final_score:Decimal


class ScenarioEvaluation(BaseModel):
    scenario:str
    run_fingerprint:str
    metrics:SimulationMetrics
    score:ScoreComponents


class CandidateEvaluation(BaseModel):
    label:str
    strategy_updates:dict[str,object]=Field(default_factory=dict)
    agent_updates:dict[str,object]=Field(default_factory=dict)
    configuration_fingerprint:str
    training:list[ScenarioEvaluation]
    validation:list[ScenarioEvaluation]=Field(default_factory=list)
    training_score:Decimal
    training_aggregate:dict[str,Decimal|None]=Field(default_factory=dict)
    validation_score:Decimal|None=None
    validation_aggregate:dict[str,Decimal|None]=Field(default_factory=dict)
    score_delta:Decimal|None=None
    baseline_delta:dict[str,Decimal|None]=Field(default_factory=dict)


class OptimizationResult(BaseModel):
    engine_version:str
    baseline:CandidateEvaluation
    requested_candidate_count:int
    candidate_count:int
    rejected_candidates:list[dict]=Field(default_factory=list)
    ranked_candidates:list[CandidateEvaluation]
    training_scenarios:list[str]
    validation_scenarios:list[str]
    objective:dict
    simulated:bool=True
