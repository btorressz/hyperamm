from __future__ import annotations

from datetime import datetime,timedelta,timezone
from decimal import Decimal
from enum import StrEnum

from app.market_data.models import MarketConnectionState,MarketDataMode,MarketLevel,MarketSnapshot,OrderBookSnapshot
from app.market_data.perp_context import build_perp_market_context
from .models import SimulationDataset,SimulationFrame,SimulationReferencePrices


BPS=Decimal("10000")


class ScenarioName(StrEnum):
    QUIET="QUIET"
    TREND_UP="TREND_UP"
    TREND_DOWN="TREND_DOWN"
    MEAN_REVERTING="MEAN_REVERTING"
    HIGH_VOLATILITY="HIGH_VOLATILITY"
    BID_HEAVY_BOOK="BID_HEAVY_BOOK"
    ASK_HEAVY_BOOK="ASK_HEAVY_BOOK"
    FLASH_MOVE="FLASH_MOVE"
    ORACLE_DISLOCATION="ORACLE_DISLOCATION"
    REFERENCE_DEGRADATION="REFERENCE_DEGRADATION"
    POSITIVE_FUNDING_STRESS="POSITIVE_FUNDING_STRESS"
    NEGATIVE_FUNDING_STRESS="NEGATIVE_FUNDING_STRESS"
    LIQUIDITY_SHOCK="LIQUIDITY_SHOCK"


DEFAULT_START=datetime(2026,1,1,0,0,0,tzinfo=timezone.utc)


def scenario_catalog()->list[dict]:
    descriptions={
        ScenarioName.QUIET:"Low-volatility balanced market.",
        ScenarioName.TREND_UP:"Deterministic upward price trend.",
        ScenarioName.TREND_DOWN:"Deterministic downward price trend.",
        ScenarioName.MEAN_REVERTING:"Deterministic oscillation around the starting price.",
        ScenarioName.HIGH_VOLATILITY:"Alternating large price moves.",
        ScenarioName.BID_HEAVY_BOOK:"Persistent positive top-book imbalance.",
        ScenarioName.ASK_HEAVY_BOOK:"Persistent negative top-book imbalance.",
        ScenarioName.FLASH_MOVE:"Abrupt downward move followed by partial recovery.",
        ScenarioName.ORACLE_DISLOCATION:"One external oracle diverges while normal policy decides the outcome.",
        ScenarioName.REFERENCE_DEGRADATION:"Primary external oracle is unavailable; fallback consensus is exercised.",
        ScenarioName.POSITIVE_FUNDING_STRESS:"Elevated positive funding with otherwise orderly prices.",
        ScenarioName.NEGATIVE_FUNDING_STRESS:"Elevated negative funding with otherwise orderly prices.",
        ScenarioName.LIQUIDITY_SHOCK:"Order-book depth collapses temporarily without synthetic fill probability.",
    }
    return [{"name":item.value,"description":descriptions[item]} for item in ScenarioName]


def _price_for(scenario:ScenarioName,i:int,start:Decimal,count:int)->Decimal:
    if scenario==ScenarioName.QUIET:
        cycle=(Decimal("0"),Decimal(".2"),Decimal("0"),Decimal("-.2"))
        return start+cycle[i%len(cycle)]
    if scenario==ScenarioName.TREND_UP:
        return start*(Decimal("1")+Decimal(i)*Decimal("0.0005"))
    if scenario==ScenarioName.TREND_DOWN:
        return start*(Decimal("1")-Decimal(i)*Decimal("0.0005"))
    if scenario==ScenarioName.MEAN_REVERTING:
        cycle=(Decimal("-6"),Decimal("-3"),Decimal("0"),Decimal("3"),Decimal("6"),Decimal("3"),Decimal("0"),Decimal("-3"))
        return start+cycle[i%len(cycle)]
    if scenario==ScenarioName.HIGH_VOLATILITY:
        cycle=(Decimal("0"),Decimal("35"),Decimal("-30"),Decimal("45"),Decimal("-40"),Decimal("25"),Decimal("-20"))
        return start+cycle[i%len(cycle)]
    if scenario==ScenarioName.FLASH_MOVE:
        pivot=max(2,count//2)
        if i<pivot:return start+Decimal(i)*Decimal(".5")
        if i==pivot:return start*Decimal(".94")
        return start*Decimal(".94")+Decimal(i-pivot)*Decimal("3")
    if scenario in {ScenarioName.POSITIVE_FUNDING_STRESS,ScenarioName.NEGATIVE_FUNDING_STRESS}:
        return start*(Decimal("1")+Decimal(i)*Decimal("0.00015"))
    return start+Decimal((i%5)-2)*Decimal(".5")


def _depths(scenario:ScenarioName,i:int)->tuple[Decimal,Decimal]:
    if scenario==ScenarioName.BID_HEAVY_BOOK:return Decimal("12"),Decimal("3")
    if scenario==ScenarioName.ASK_HEAVY_BOOK:return Decimal("3"),Decimal("12")
    if scenario==ScenarioName.LIQUIDITY_SHOCK and 4<=i%12<=7:return Decimal(".5"),Decimal(".5")
    return Decimal("6"),Decimal("6")


def _funding(scenario:ScenarioName,i:int)->Decimal:
    if scenario==ScenarioName.POSITIVE_FUNDING_STRESS:return Decimal("0.00045")
    if scenario==ScenarioName.NEGATIVE_FUNDING_STRESS:return Decimal("-0.00045")
    return Decimal((i%5)-2)*Decimal("0.000005")


def _reference_prices(scenario:ScenarioName,mid:Decimal,i:int)->SimulationReferencePrices:
    redstone=mid*(Decimal("1")+Decimal((i%3)-1)*Decimal("0.00002"))
    kraken=mid*(Decimal("1")+Decimal((i%5)-2)*Decimal("0.00001"))
    coingecko=mid*(Decimal("1")+Decimal((i%7)-3)*Decimal("0.00001"))
    if scenario==ScenarioName.ORACLE_DISLOCATION:
        redstone=mid*Decimal("1.015")
    if scenario==ScenarioName.REFERENCE_DEGRADATION:
        redstone=None
    return SimulationReferencePrices(redstone=redstone,kraken=kraken,coingecko=coingecko)


def generate_scenario(
    name:ScenarioName|str,
    *,
    frames:int=120,
    market:str="ETH",
    start_price:Decimal=Decimal("3000"),
    start_time:datetime=DEFAULT_START,
    interval_seconds:int=1,
)->SimulationDataset:
    scenario=ScenarioName(name)
    if frames<2:raise ValueError("scenario requires at least two frames")
    if frames>5000:raise ValueError("scenario exceeds maximum frame count")
    if interval_seconds<=0:raise ValueError("scenario interval must be positive")
    if not start_price.is_finite() or start_price<=0:raise ValueError("scenario start price must be finite and positive")
    if start_time.tzinfo is None:raise ValueError("scenario start time must be timezone-aware")
    result=[]
    for i in range(frames):
        sequence=i+1
        ts=start_time.astimezone(timezone.utc)+timedelta(seconds=i*interval_seconds)
        mid=_price_for(scenario,i,start_price,frames)
        if not mid.is_finite() or mid<=0:raise ValueError("scenario generated invalid mid price")
        spread=max(Decimal(".2"),mid*Decimal("0.0001"))
        best_bid=mid-spread/Decimal("2");best_ask=mid+spread/Decimal("2")
        bid_depth,ask_depth=_depths(scenario,i)
        bids=[];asks=[]
        for level in range(5):
            offset=spread/Decimal("2")+Decimal(level)*max(Decimal(".1"),spread/Decimal("2"))
            bids.append(MarketLevel(price=mid-offset,size=bid_depth/(Decimal(level)+1),order_count=1))
            asks.append(MarketLevel(price=mid+offset,size=ask_depth/(Decimal(level)+1),order_count=1))
        book=OrderBookSnapshot(market=market,bids=bids,asks=asks,timestamp=ts,sequence=sequence)
        snapshot=MarketSnapshot(
            market=market,best_bid=best_bid,best_ask=best_ask,mid_price=mid,book=book,
            latest_valid_update=ts,connection_state=MarketConnectionState.CONNECTED,
            mode=MarketDataMode.DEMO,simulated=True,stale=False,
        )
        oracle=mid*(Decimal("1")+Decimal((i%3)-1)*Decimal("0.00001"))
        mark=mid*(Decimal("1")+Decimal((i%5)-2)*Decimal("0.000015"))
        funding=_funding(scenario,i)
        oi=Decimal("250000")+Decimal(i*10)
        perp=build_perp_market_context(
            market=market,market_mid=mid,provider_mid_price=mid,mark_price=mark,oracle_price=oracle,
            funding_rate=funding,open_interest_base=oi,premium=(mark-oracle)/oracle,
            updated_at=ts,source="DEMO",simulated=True,version=sequence,
        )
        result.append(SimulationFrame(
            sequence=sequence,timestamp=ts,market=snapshot,perp_context=perp,
            reference_prices=_reference_prices(scenario,mid,i),
        ))
    return SimulationDataset(market=market,frames=result,source=f"scenario:{scenario.value}",simulated=True)
