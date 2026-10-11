from __future__ import annotations

from datetime import datetime,timezone
from decimal import Decimal
from enum import Enum
import hashlib,json
from typing import Annotated, Literal

from pydantic import BaseModel,ConfigDict,Field,computed_field,model_validator

from app.market_data.models import MarketSnapshot
from app.market_data.perp_context import PerpMarketContext
from app.accounting.models import LedgerEntry, VaultSnapshot
from app.research.ml.shadow_evaluation import ShadowEvaluationResult
from app.market_data.live_models import Evidence, FinancialDecimal, PositiveDecimal, NonnegativeDecimal
from app.simulation.market_profiles import ResearchPerpMarketId
from pydantic import AwareDatetime, StrictInt, field_validator


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
    liquidity_quality_state:str|None=None
    perp_crowding_state:str|None=None
    predictive_state:str|None=None
    bid_adverse_probability:Decimal|None=None
    ask_adverse_probability:Decimal|None=None
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
    liquidity_quality_state_counts:dict[str,int]=Field(default_factory=dict)
    perp_crowding_state_counts:dict[str,int]=Field(default_factory=dict)


class ResearchMarketEvidence(BaseModel):
    research_market:str|None=None
    market_profile_version:str|None=None
    market_profile_fingerprint:str|None=None
    metadata_source:str|None=None
    metadata_status:str|None=None


class ResearchBookLevel(Evidence):
    price: PositiveDecimal
    size: NonnegativeDecimal


Fingerprint = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
BoundedText = Annotated[str, Field(max_length=500)]


class ResearchMarketAssumptions(Evidence):
    """Last consumed dataset frame, independent of trace retention and accounting."""
    contract_version: Literal['phase154-v1'] = 'phase154-v1'
    market: ResearchPerpMarketId
    market_profile_version: Literal['phase146-v1'] | None = None
    market_profile_fingerprint: Fingerprint | None = None
    dataset_fingerprint: Fingerprint
    scenario: Annotated[str, Field(pattern=r'^[A-Z_]{1,64}$')]
    frame_count: StrictInt = Field(ge=2, le=5000)
    simulated: Literal[True] = True
    representative_frame: Literal['LAST_CONSUMED_DATASET_FRAME'] = 'LAST_CONSUMED_DATASET_FRAME'
    representative_frame_sequence: StrictInt = Field(ge=0)
    representative_frame_timestamp: AwareDatetime
    midpoint: PositiveDecimal
    best_bid: PositiveDecimal
    best_ask: PositiveDecimal
    spread_quote: PositiveDecimal
    spread_bps: PositiveDecimal
    mark_price: PositiveDecimal
    oracle_price: PositiveDecimal
    funding_rate: FinancialDecimal
    funding_convention: Literal['RAW_RATE_PER_SAMPLED_RESEARCH_INTERVAL'] = 'RAW_RATE_PER_SAMPLED_RESEARCH_INTERVAL'
    open_interest_base: NonnegativeDecimal | None = None
    bid_levels: tuple[ResearchBookLevel, ...] = Field(min_length=1, max_length=5)
    ask_levels: tuple[ResearchBookLevel, ...] = Field(min_length=1, max_length=5)
    bid_depth_base: NonnegativeDecimal
    ask_depth_base: NonnegativeDecimal
    depth_level_count: StrictInt = Field(ge=1, le=5)
    depth_measurement_method: Literal['TOP_5_LEVELS_PER_SIDE_BASE'] = 'TOP_5_LEVELS_PER_SIDE_BASE'
    reference_source: Annotated[str, Field(pattern=r'^[a-zA-Z0-9:_ -]{1,200}$')]
    assumption_fingerprint: Fingerprint
    limitations: tuple[BoundedText, ...] = Field(default=(), max_length=12)

    @field_validator('simulated', mode='before')
    @classmethod
    def paper_flag(cls, value):
        if value is not True:
            raise ValueError('research evidence requires explicit simulated true')
        return value

    @model_validator(mode='after')
    def consistent_assumptions(self):
        if self.best_bid >= self.best_ask or self.midpoint != (self.best_bid + self.best_ask) / 2:
            raise ValueError('inconsistent research BBO/midpoint')
        if self.spread_quote != self.best_ask - self.best_bid or self.spread_bps != self.spread_quote / self.midpoint * Decimal('10000'):
            raise ValueError('inconsistent research spread')
        if self.bid_levels[0].price != self.best_bid or self.ask_levels[0].price != self.best_ask:
            raise ValueError('research BBO does not match captured levels')
        if any(a.price < b.price for a,b in zip(self.bid_levels, self.bid_levels[1:])) or any(a.price > b.price for a,b in zip(self.ask_levels, self.ask_levels[1:])):
            raise ValueError('research levels are unsorted')
        if self.depth_level_count != min(len(self.bid_levels), len(self.ask_levels)):
            raise ValueError('inconsistent research level count')
        if self.bid_depth_base != sum((x.size for x in self.bid_levels), Decimal(0)) or self.ask_depth_base != sum((x.size for x in self.ask_levels), Decimal(0)):
            raise ValueError('inconsistent research depth sums')
        if (self.market_profile_version is None) != (self.market_profile_fingerprint is None):
            raise ValueError('incomplete research profile identity')
        if self.assumption_fingerprint != stable_fingerprint(self.model_dump(exclude={'assumption_fingerprint'})):
            raise ValueError('research assumptions fingerprint mismatch')
        return self


class SimulationResult(ResearchMarketEvidence):
    research_assumptions: ResearchMarketAssumptions | None = None
    research_configuration:dict|None=None
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
    predictive_evaluation:ShadowEvaluationResult|None=None


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
    dataset_fingerprint:str
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

    @computed_field
    @property
    def training_dataset_fingerprints(self)->list[str]:
        return [item.dataset_fingerprint for item in self.training]

    @computed_field
    @property
    def validation_dataset_fingerprints(self)->list[str]:
        return [item.dataset_fingerprint for item in self.validation]

    @computed_field
    @property
    def validation_overlap(self)->bool:
        return bool(set(self.training_dataset_fingerprints)&set(self.validation_dataset_fingerprints))

    @computed_field
    @property
    def independent_holdout(self)->bool:
        return bool(self.training_dataset_fingerprints and self.validation_dataset_fingerprints) and not self.validation_overlap

    @computed_field
    @property
    def validation_classification(self)->str:
        if not self.validation_dataset_fingerprints:
            return "NOT_EVALUATED"
        if self.validation_overlap:
            return "REUSED_OVERLAPPING"
        return "INDEPENDENT_HOLDOUT" if self.independent_holdout else "NOT_EVALUATED"


class OptimizationResult(ResearchMarketEvidence):
    research_configuration:dict|None=None
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

    @computed_field
    @property
    def training_dataset_fingerprints(self)->list[str]:
        return sorted({fp for candidate in [self.baseline,*self.ranked_candidates]
                       for fp in candidate.training_dataset_fingerprints})

    @computed_field
    @property
    def validation_dataset_fingerprints(self)->list[str]:
        return sorted({fp for candidate in [self.baseline,*self.ranked_candidates]
                       for fp in candidate.validation_dataset_fingerprints})

    @computed_field
    @property
    def validation_overlap(self)->bool:
        return bool(set(self.training_dataset_fingerprints)&set(self.validation_dataset_fingerprints))

    @computed_field
    @property
    def independent_holdout(self)->bool:
        return bool(self.training_dataset_fingerprints and self.validation_dataset_fingerprints) and not self.validation_overlap

    @computed_field
    @property
    def validation_classification(self)->str:
        if not self.validation_dataset_fingerprints:
            return "NOT_EVALUATED"
        if self.validation_overlap:
            return "REUSED_OVERLAPPING"
        return "INDEPENDENT_HOLDOUT" if self.independent_holdout else "NOT_EVALUATED"
