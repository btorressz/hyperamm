from __future__ import annotations
from collections import deque
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.amm.discretizer import normalize_price, normalize_size
from app.amm.models import QuoteLevel
from app.market_data.models import utcnow
from app.references.models import ReferenceSnapshot


class RiskState(StrEnum):
    NORMAL="NORMAL"; WIDEN="WIDEN"; REDUCE="REDUCE"; HALT="HALT"


class RiskFirewallConfig(BaseModel):
    enabled:bool=True
    reference_warn_deviation_bps:Decimal=Decimal("20")
    reference_reduce_deviation_bps:Decimal=Decimal("40")
    reference_halt_deviation_bps:Decimal=Decimal("80")
    source_agreement_bps:Decimal=Decimal("30")
    source_outlier_bps:Decimal=Decimal("75")
    max_projected_long_base:Decimal=Decimal("10")
    max_projected_short_base:Decimal=Decimal("10")
    max_gross_quote_notional:Decimal=Decimal("1000000")
    max_projected_position_notional:Decimal=Decimal("1000000")
    liquidation_warn_distance_bps:Decimal=Decimal("1500")
    liquidation_reduce_distance_bps:Decimal=Decimal("800")
    liquidation_halt_distance_bps:Decimal=Decimal("300")
    max_session_loss_quote:Decimal|None=Decimal("5000")
    drawdown_warn_pct:Decimal|None=Decimal("0.05")
    drawdown_reduce_pct:Decimal|None=Decimal("0.10")
    drawdown_halt_pct:Decimal|None=Decimal("0.15")
    widen_spread_multiplier:Decimal=Decimal("1.25")
    widen_size_multiplier:Decimal=Decimal("0.90")
    reduce_spread_multiplier:Decimal=Decimal("1.60")
    reduce_size_multiplier:Decimal=Decimal("0.50")
    reduce_inventory_increasing_multiplier:Decimal=Decimal("0.20")
    reduce_max_levels:int|None=4
    recovery_ratio:Decimal=Decimal("0.75")
    risk_recovery_confirmations:int=3
    @model_validator(mode="after")
    def bounds(self):
        vals=(self.reference_warn_deviation_bps,self.reference_reduce_deviation_bps,self.reference_halt_deviation_bps,self.source_agreement_bps,self.source_outlier_bps,self.max_projected_long_base,self.max_projected_short_base,self.max_gross_quote_notional,self.max_projected_position_notional,self.liquidation_warn_distance_bps,self.liquidation_reduce_distance_bps,self.liquidation_halt_distance_bps,self.widen_spread_multiplier,self.widen_size_multiplier,self.reduce_spread_multiplier,self.reduce_size_multiplier,self.reduce_inventory_increasing_multiplier,self.recovery_ratio)
        if any(not v.is_finite() for v in vals):raise ValueError("risk firewall decimals must be finite")
        if not (0<=self.reference_warn_deviation_bps<self.reference_reduce_deviation_bps<self.reference_halt_deviation_bps):raise ValueError("reference thresholds require warn < reduce < halt")
        if not (self.liquidation_halt_distance_bps<self.liquidation_reduce_distance_bps<self.liquidation_warn_distance_bps):raise ValueError("liquidation thresholds require halt < reduce < warn distance")
        if self.widen_spread_multiplier<1 or self.reduce_spread_multiplier<self.widen_spread_multiplier:raise ValueError("risk spread multipliers must widen only")
        if not (0<self.reduce_inventory_increasing_multiplier<=self.reduce_size_multiplier<=self.widen_size_multiplier<=1):raise ValueError("risk size multipliers invalid")
        if not (0<self.recovery_ratio<1):raise ValueError("recovery_ratio must be between 0 and 1")
        for a,b,c in [(self.drawdown_warn_pct,self.drawdown_reduce_pct,self.drawdown_halt_pct)]:
            if None not in (a,b,c) and not (Decimal("0")<=a<b<c):raise ValueError("drawdown thresholds require warn < reduce < halt")
        return self


class ExposureMetrics(BaseModel):
    current_position:Decimal
    current_position_notional:Decimal
    bid_quote_notional:Decimal
    ask_quote_notional:Decimal
    gross_quote_notional:Decimal
    bid_quantity:Decimal
    ask_quantity:Decimal
    projected_long_base:Decimal
    projected_short_base:Decimal
    projected_long_notional:Decimal
    projected_short_notional:Decimal
    inventory_utilization:Decimal


class PnlDrawdown(BaseModel):
    realized_pnl:Decimal|None=None
    unrealized_pnl:Decimal|None=None
    session_pnl:Decimal|None=None
    current_equity:Decimal|None=None
    peak_equity:Decimal|None=None
    drawdown_pct:Decimal|None=None
    source:str
    simulated:bool=False


class LiquidationEvidence(BaseModel):
    status:str
    distance_bps:Decimal|None=None
    position_base:Decimal
    mark_price:Decimal
    liquidation_price:Decimal|None=None


class RiskDecision(BaseModel):
    state:RiskState
    allow_quotes:bool
    spread_multiplier:Decimal
    size_multiplier:Decimal
    max_levels:int|None=None
    allow_bids:bool=True
    allow_asks:bool=True
    reasons:list[str]
    reference_version:int
    market_version:int
    inventory_version:int
    perp_version:int
    projected_long_base:Decimal
    projected_short_base:Decimal
    exposure:ExposureMetrics
    liquidation:LiquidationEvidence
    pnl_drawdown:PnlDrawdown
    healthy_confirmation_count:int=0
    created_at:datetime=Field(default_factory=utcnow)
    version:int=0


class RiskEvent(BaseModel):
    timestamp:datetime=Field(default_factory=utcnow)
    previous_state:RiskState
    new_state:RiskState
    reasons:list[str]
    reference_version:int
    risk_version:int


def exposure_metrics(quotes,current_position,reference_price,position_limit)->ExposureMetrics:
    bid_qty=sum((q.size for q in quotes if q.side=="BID"),Decimal("0"))
    ask_qty=sum((q.size for q in quotes if q.side=="ASK"),Decimal("0"))
    bid_ntl=sum((q.price*q.size for q in quotes if q.side=="BID"),Decimal("0"))
    ask_ntl=sum((q.price*q.size for q in quotes if q.side=="ASK"),Decimal("0"))
    long=current_position+bid_qty
    short=current_position-ask_qty
    util=abs(current_position)/position_limit if position_limit>0 else Decimal("1")
    return ExposureMetrics(current_position=current_position,current_position_notional=abs(current_position)*reference_price,bid_quote_notional=bid_ntl,ask_quote_notional=ask_ntl,gross_quote_notional=bid_ntl+ask_ntl,bid_quantity=bid_qty,ask_quantity=ask_qty,projected_long_base=long,projected_short_base=short,projected_long_notional=abs(long)*reference_price,projected_short_notional=abs(short)*reference_price,inventory_utilization=util)


def liquidation_evidence(position,mark,liquidation)->LiquidationEvidence:
    if position==0:return LiquidationEvidence(status="FLAT",position_base=position,mark_price=mark,liquidation_price=liquidation)
    if liquidation is None:return LiquidationEvidence(status="UNAVAILABLE",position_base=position,mark_price=mark)
    if not liquidation.is_finite() or liquidation<=0:raise ValueError("invalid liquidation price")
    d=(mark-liquidation)/mark if position>0 else (liquidation-mark)/mark
    if d<0:return LiquidationEvidence(status="BREACHED",distance_bps=d*Decimal("10000"),position_base=position,mark_price=mark,liquidation_price=liquidation)
    return LiquidationEvidence(status="AVAILABLE",distance_bps=d*Decimal("10000"),position_base=position,mark_price=mark,liquidation_price=liquidation)


def paper_pnl(fills,market,mark)->PnlDrawdown:
    qty=Decimal("0");avg=Decimal("0");realized=Decimal("0")
    for fill in fills:
        if fill.market!=market:continue
        signed=fill.size if fill.side=="BID" else -fill.size
        if qty==0 or (qty>0)==(signed>0):
            new=qty+signed
            avg=(avg*abs(qty)+fill.price*abs(signed))/abs(new) if new else Decimal("0")
            qty=new;continue
        close=min(abs(qty),abs(signed))
        realized+=(fill.price-avg)*close*(Decimal("1") if qty>0 else Decimal("-1"))
        old_sign=Decimal("1") if qty>0 else Decimal("-1")
        qty=qty+signed
        if qty==0:avg=Decimal("0")
        elif (qty>0)!=(old_sign>0):avg=fill.price
    unrealized=(mark-avg)*qty if qty else Decimal("0")
    return PnlDrawdown(realized_pnl=realized,unrealized_pnl=unrealized,session_pnl=realized+unrealized,source="SIMULATED PAPER PNL",simulated=True)


class RiskFirewall:
    def __init__(self,config:RiskFirewallConfig):
        self.config=config;self.state=RiskState.NORMAL;self.version=0;self.confirmations=0;self.changed_at=utcnow();self.events=deque(maxlen=250)
    def _candidate(self,refs:ReferenceSnapshot,exposure:ExposureMetrics,liq:LiquidationEvidence,pnl:PnlDrawdown,venue_uncertain:bool):
        c=self.config;reasons=[];severity=0
        if refs.consensus.confidence_state in {"INSUFFICIENT","CONFLICTED"}:severity=3;reasons.append(f"reference confidence {refs.consensus.confidence_state}")
        elif refs.consensus.confidence_state=="DEGRADED":severity=max(severity,2);reasons.extend(refs.consensus.reasons)
        deviations=[abs(v) for k,v in refs.deviations_bps.items() if k in {"hl_mid_consensus","hl_mark_consensus","hl_oracle_consensus"} and v is not None]
        maxdev=max(deviations,default=Decimal("0"))
        if maxdev>=c.reference_halt_deviation_bps:severity=3;reasons.append(f"reference deviation {maxdev} bps >= halt threshold")
        elif maxdev>=c.reference_reduce_deviation_bps:severity=max(severity,2);reasons.append(f"reference deviation {maxdev} bps >= reduce threshold")
        elif maxdev>=c.reference_warn_deviation_bps:severity=max(severity,1);reasons.append(f"reference deviation {maxdev} bps >= warn threshold")
        if exposure.projected_long_base>c.max_projected_long_base or exposure.projected_short_base<-c.max_projected_short_base:severity=3;reasons.append("projected base exposure exceeds limit")
        if exposure.gross_quote_notional>c.max_gross_quote_notional:severity=3;reasons.append("gross quote notional exceeds limit")
        if max(exposure.projected_long_notional,exposure.projected_short_notional)>c.max_projected_position_notional:severity=3;reasons.append("projected position notional exceeds limit")
        if liq.status=="BREACHED":severity=3;reasons.append("liquidation price breached")
        elif liq.distance_bps is not None:
            if liq.distance_bps<=c.liquidation_halt_distance_bps:severity=3;reasons.append("critical liquidation distance")
            elif liq.distance_bps<=c.liquidation_reduce_distance_bps:severity=max(severity,2);reasons.append("reduced liquidation distance")
            elif liq.distance_bps<=c.liquidation_warn_distance_bps:severity=max(severity,1);reasons.append("liquidation distance warning")
        if pnl.session_pnl is not None and c.max_session_loss_quote is not None and pnl.session_pnl<=-c.max_session_loss_quote:severity=3;reasons.append("maximum session loss reached")
        if pnl.drawdown_pct is not None and c.drawdown_halt_pct is not None:
            if pnl.drawdown_pct>=c.drawdown_halt_pct:severity=3;reasons.append("critical drawdown")
            elif pnl.drawdown_pct>=c.drawdown_reduce_pct:severity=max(severity,2);reasons.append("drawdown reduce threshold")
            elif pnl.drawdown_pct>=c.drawdown_warn_pct:severity=max(severity,1);reasons.append("drawdown warning")
        if venue_uncertain:severity=3;reasons.append("venue exposure is uncertain")
        return [RiskState.NORMAL,RiskState.WIDEN,RiskState.REDUCE,RiskState.HALT][severity],reasons,maxdev
    def evaluate(self,*,refs,quotes,current_position,mark,liquidation,pnl,market_version,inventory_version,perp_version,venue_uncertain=False):
        c=self.config;price=refs.consensus.consensus_price or mark;exp=exposure_metrics(quotes,current_position,price,max(c.max_projected_long_base,c.max_projected_short_base));liq=liquidation_evidence(current_position,mark,liquidation)
        candidate,reasons,maxdev=self._candidate(refs,exp,liq,pnl,venue_uncertain)
        previous=self.state
        if candidate.value==RiskState.HALT.value or [RiskState.NORMAL,RiskState.WIDEN,RiskState.REDUCE,RiskState.HALT].index(candidate)>[RiskState.NORMAL,RiskState.WIDEN,RiskState.REDUCE,RiskState.HALT].index(self.state):
            effective=candidate;self.confirmations=0
        elif candidate==self.state:
            effective=self.state;self.confirmations=0 if self.state==RiskState.NORMAL else self.confirmations
        else:
            recovery_threshold={
                RiskState.WIDEN:c.reference_warn_deviation_bps*c.recovery_ratio,
                RiskState.REDUCE:c.reference_reduce_deviation_bps*c.recovery_ratio,
                RiskState.HALT:c.reference_halt_deviation_bps*c.recovery_ratio,
                RiskState.NORMAL:Decimal("0"),
            }[self.state]
            recovery_ok=maxdev<recovery_threshold and refs.consensus.confidence_state in {"VERIFIED","DEGRADED"}
            if recovery_ok:self.confirmations+=1
            else:self.confirmations=0
            effective=candidate if self.confirmations>=c.risk_recovery_confirmations else self.state
            if effective!=self.state:self.confirmations=0;reasons.append("risk state recovered after healthy confirmations")
            elif recovery_ok:reasons.append(f"recovery pending {self.confirmations}/{c.risk_recovery_confirmations}")
        self.state=effective
        spread=Decimal("1");size=Decimal("1");levels=None
        if effective==RiskState.WIDEN:spread=c.widen_spread_multiplier;size=c.widen_size_multiplier
        elif effective==RiskState.REDUCE:spread=c.reduce_spread_multiplier;size=c.reduce_size_multiplier;levels=c.reduce_max_levels
        elif effective==RiskState.HALT:spread=c.reduce_spread_multiplier;size=Decimal("0");levels=0
        self.version+=1
        if effective!=previous:
            self.changed_at=utcnow();self.events.append(RiskEvent(previous_state=previous,new_state=effective,reasons=reasons,reference_version=refs.version,risk_version=self.version))
        return RiskDecision(state=effective,allow_quotes=effective!=RiskState.HALT,spread_multiplier=spread,size_multiplier=size,max_levels=levels,reasons=reasons or ["risk inputs within configured limits"],reference_version=refs.version,market_version=market_version,inventory_version=inventory_version,perp_version=perp_version,projected_long_base=exp.projected_long_base,projected_short_base=exp.projected_short_base,exposure=exp,liquidation=liq,pnl_drawdown=pnl,healthy_confirmation_count=self.confirmations,version=self.version)
    def transform(self,quotes,decision,*,center,tick_size,size_precision,base_order_size):
        if not decision.allow_quotes:return []
        if decision.state==RiskState.NORMAL or not self.config.enabled:
            return [q.model_copy(update={"pre_risk_price":q.price,"pre_risk_size":q.size,"risk_spread_multiplier":Decimal("1"),"risk_size_multiplier":Decimal("1"),"risk_state":RiskState.NORMAL.value}) for q in quotes]
        out=[]
        for q in quotes:
            if q.side=="BID" and not decision.allow_bids:continue
            if q.side=="ASK" and not decision.allow_asks:continue
            if decision.max_levels is not None and q.level_index>=decision.max_levels:continue
            distance=abs(q.price-center)*decision.spread_multiplier
            price=normalize_price(center-distance if q.side=="BID" else center+distance,tick_size,q.side)
            mult=decision.size_multiplier
            if decision.state==RiskState.REDUCE and q.inventory_intent=="INVENTORY_INCREASING":mult=self.config.reduce_inventory_increasing_multiplier
            size=normalize_size(max(q.size*mult,Decimal(1).scaleb(-size_precision)),size_precision)
            out.append(q.model_copy(update={"price":price,"size":size,"pre_risk_price":q.price,"pre_risk_size":q.size,"risk_spread_multiplier":decision.spread_multiplier,"risk_size_multiplier":mult,"risk_state":decision.state.value}))
        bids=sorted([q for q in out if q.side=="BID"],key=lambda x:x.price,reverse=True);asks=sorted([q for q in out if q.side=="ASK"],key=lambda x:x.price)
        if bids and asks and bids[0].price>=asks[0].price:raise ValueError("risk-authorized quote market is crossed")
        return bids+asks
